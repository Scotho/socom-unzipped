# 20 — HLE liveness: uninitialised fields, and what the guest does with each stub's return

Sprint 5 Task 4. §1 is Leg 0 (Step 1, `tools_py/parity/object_diff.py`). §2–§4 are Step 2's static
census (`tools_py/hle_constants.py`, `0cdb9a1`): every stub bound in `recomp/socom2.toml`, every
static call site, what the guest does with the return value, and whether our C++ can hand it a
constant or a wrongly shaped value. Zero game runs. Every claim is marked **[verified]** (read in
the ELF bytes, the C++ or an RDRAM image) or **[inference]**.

Why this exists: three defects in a row were an HLE value the guest consumed as if it moved —
`rand` over a frozen seed, `sceInetInterfaceControl(0x200)` returning a constant
(`research/18` §3.12), and soft-double stubs bound with the wrong ABI (`KNOWN.md` §1). The census
ranks the remaining stubs by that shape before a match is spent finding the next one.

---

## 1. Leg 0 — object-keyed uninitialised-field diff reproduces (most of) F3, with three corrections

`tools_py/parity/object_diff.py` (Sprint 5 Task 4 Step 1) makes research/19 F3's by-hand
methodology into a repeatable tool: follow a static pointer to its block independently in every
image, then diff byte-by-byte, flagging any offset that is a single nonzero constant on every
`ours` image and zero on every `console` image. Run against the same four images F3 used
(`title_ours`/`spawn_ours3` vs `title_pcsx2`/`spawn_pcsx2`), the round-state block resolves to
the addresses F3 reports (`0x869360` ours, `0xc496b0` console) and reproduces almost all of F3's
flagged list, but **not exactly** **[verified]**:

- Four ranges F3 did not list are genuinely flagged: `+0x38`, `+0x3a..+0x3c`, `+0x3e..+0x3f`,
  and `+0x14b` (the block's last byte). Add these to F3's list.
- F3's `+0x6C..+0x83` is too wide: `+0x6c..+0x7b` holds real, structured, differing data (not
  `0xAF`) — only `+0x7c..+0x83` is uninitialised. F3's list should read `+0x7C..+0x83`.
- F3's `+0xFC..+0x10F` has an undocumented 4-byte hole at `+0x100..+0x103`, where both sides
  already read zero (not even a diff). The real range is `+0xFC..+0xFF` and `+0x104..+0x10F`.

**The flagged counts are a lower bound.** The flag rule needs *one* constant across *all* of our
images, so a recycled byte that happens to differ between two of our sessions (two different
earlier tenants of the heap block) is not flagged even when it is uninitialised in both. Adding
images can only shrink the flagged set; it never proves the unflagged bytes clean **[verified
from the rule; the size of the undercount is unknown]**.

Extended to the actor (`*0x408c58`, `0x1100` bytes) and camera (`*0x415ff0`, `0x200` bytes)
objects using five independent "ours" sessions against two "console" sessions (spawn-state
only — the title images have a NULL actor pointer, which the tool correctly treats as
non-resolving rather than silently skipping): **71 fields flagged on each object** **[verified]**.
Neither `+0xd0`/`+0xd4`/`+0x20c` (the peek-verified frost1/Medley actor-state fields, below) nor
`+0x204`/`+0x208` (the disputed health/max-health floats) are in the flagged set — both are live
or agreed-upon values, not recycled bytes, which is the negative control this instrument needed.

A methodological finding along the way: this technique requires same-context samples on both
sides for objects whose content legitimately varies by game state (camera, actor). Mixing title
and spawn-state camera images together produced **zero** false flags but also suppressed all 71
true ones, because the "constant across every ours image" test fails once the images disagree
with each other for a legitimate reason **[verified]**. F3's own methodology (title-vs-title,
spawn-vs-spawn) already avoided this; it is worth stating explicitly so the next static doesn't
get run over a mismatched image set and reported clean by mistake.

The tool's second mode reads the runtime's `PS2X_PEEK` text logs directly, keying the actor block
by its vtable word (`0x6691a0`) rather than by row position or address — both shift: item indices
shift when an earlier `*static` chain hasn't resolved yet (2 blocks per row early in a match, 5
once the actor and its dependents resolve), and the actor's own heap address differs run to run.
Run over the real `frost1` (`run_A/B_20260913_004754.log`) and `kill2` (Medley;
`run_A/B_20260912_231341.log`, the same run `KNOWN.md` already cites) logs, it reproduces the
`KNOWN.md` "believed" entry **[verified]**: on Frostfire, actor `+0xd0`/`+0xd4` are constant `1`
(B settles to `1` after one early `0` — a minor nuance, not a contradiction) and `+0x20c` is
constant `0` for the *entire* run on both instances; on Medley, all three vary throughout, touching
every value `KNOWN.md` quotes for it (`8/5`, `4/7`). One relaunch with a live peek on
`+0xCC`/`+0xd2` (per F3's own "what it would take") is still the next step to learn WHY
Frostfire's actor state is frozen there; this leg only confirms the divergence is real and
reproducible without one.

---

## 2. Static census — every bound stub, every static call site

### 2.1 Method

```
python -m tools_py.hle_constants --summary          # one line per stub
python -m tools_py.hle_constants --stub strcmp      # every site of one stub
python -m tools_py.hle_constants --extra NAME@0xADDR  # a binding that is not in the toml
```

1. **Sites [verified].** Parse the toml's `stubs = [...]` list (223 entries); scan every 32-bit
   word of the ELF's four `PT_LOAD` segments for `jal ADDR` (direct call) and `j ADDR` (tail call).
   A site inside a bound stub's own body (from its address to the next function start or stub
   address) is **dead**: that body never runs. A data word equal to a stub address is counted as
   **addr-taken** (a `jalr` through it is invisible to the scan).
2. **Consumers [verified per instruction, heuristic as a whole].** From the return point
   (`site + 8`) follow `$v0` (`$f0` for `__kernel_cosf`/`__kernel_sinf`) for up to 12
   instructions: **ignored** (overwritten or clobbered by a call before any read), **zero-test**
   (`beqz`/`bnez`/`bltz`/…, `sltiu 1`, `slti 0/1`, `slt(u)` against `$zero`, the condition of a
   `movz`/`movn`), **const-compare** (against an immediate or a register just loaded with one),
   **var-compare**, **arithmetic**, **stored** (`sw`/`sd`/`sh`/`sb`/`swc1`), **deref** (used as a
   base address). Anything that reaches a register copy, a conditional branch, a call, `jr ra` or the
   budget first is **unresolved**, with the copy's own first use printed only as a hint. Masks and
   sign-extends are followed; an unconditional `b` is followed. The strongest use wins
   (arithmetic > var-compare > stored > deref > const-compare > zero-test).
3. **Implementation and tag.** Each toml name resolves to a handler through
   `ps2_game_overrides::resolveHandlerByName`: syscall list first, then stub list, with a
   leading-underscore alias (`_malloc_r` → `ps2_stubs::malloc_r`) **[verified]**. The generated
   wrapper for each address names the handler it calls **[verified]**. Tags: *constant by spec*,
   *constant by omission*, *wrong shape* (width, sign, register, argument ABI) or *faithful*.
   Return registers follow the EE EABI: `int`/pointer in `$v0` sign-extended from 32 bits, `double`
   as a 64-bit pattern in `$v0`, `float` in `$f0`, arguments 5–8 in `$t0`–`$t3` **[known ABI]**
   unless a row says **[inference]**.

The classifier was checked by hand against the disassembly at about 40 sites. They include
eight first-pass arithmetic or const-compare sites of `strcmp`, all four unresolved `strcmp`
sites, the pad-function sites of `scePad2GetButtonInfo`/`scePad2GetState`/`scePad2Read`, the
compare sites of `sceCdSync`, `sceCdGetDiskType`, `sceSifCheckStatRpc` and `sceMcSync`, both
`__ieee754_rem_pio2f` consumers, and three soft-double sites. Every `scePad2GetButtonInfo` site was
also matched to its button id. Three first-pass misreads were found and fixed in the tool before
these numbers were taken: `xor v0,v0,$zero;
sltiu v0,v0,1` counted as arithmetic (it is `== 0`), `movz` condition counted as arithmetic, and
a copy overwritten after its use reported as ignored.

### 2.2 Totals [verified]

| | count |
|---|---|
| bound stubs in the toml | **223** |
| stubs with at least one live static site | **150** |
| stubs with none (dead-only, addr-taken-only or nothing) | **73** |
| live direct sites | **4,081** |
| live tail sites | **37** over **17** stubs |
| dead sites (inside a bound stub's body) | **277** |
| addr-taken data words | **5** (one table, §3.3) |

Live direct sites by consumer class: ignored **1,855**, zero-test **1,218**, unresolved **507**,
arithmetic **411**, const-compare **51**, stored **31**, var-compare **8**, deref **0**.

The 411 arithmetic sites are `rand` 288, `strlen` 90, `scePad2GetButtonInfo` 18, `strstr` 8,
`__kernel_cosf`/`__kernel_sinf` 2 each, `memchr` 2, `__ieee754_rem_pio2f` 1. The 31 stored sites
are `strlen` 9, `malloc` 4, `sceDmaGetChan` 4, `scePad2GetButtonInfo` 4, `sceOpen` 3,
`scePad2CreateSocket` 2, `ftell` 2, `scePad2GetState`, `sceLseek`, `sceSifAllocIopHeap` 1 each.

**Headline [verified for the return channel; inference for the rest]:** no toml stub returns a
*constant by omission* into an arithmetic or stored `$v0` consumer. Every arithmetic or stored
return consumer sits on a faithful stub. The one exception is `scePad2GetButtonInfo`'s pressure ids,
which are harmless (§4). The findings sit one step off the `$v0` channel: an **argument** ABI
mismatch whose output struct diverges from the console (`sceGsSetDefDBuff`, §4.1; the part
actually consumed is the display environment, §4.3), **out-parameter** constants
(`socom2_LumReadPixel`), and the layers this census cannot see (§3). That last group is where `0x200` lived.

### 2.3 Ranked table

Tiers: **A** wrong shape or constant by omission, with a live arithmetic/stored consumer of the
return *or* of an output written through a pointer argument. **B** wrong shape whose consumers
are all sign/zero tests or dead. **C** constant by spec, with compare or stored consumers.
**D** faithful, with arithmetic or stored consumers. **E** everything else with a live site.
"direct / tail / dead" counts sites; consumer classes count live direct sites only. Impl paths are
relative to `third_party/ps2recomp/ps2xRuntime/src/lib/`.

| # | tier | stub | address | direct / tail / dead | consumers (live direct sites) | tag | return, guest ABI | impl | note |
|---|---|---|---|---|---|---|---|---|---|
| 1 | A | `sceGsSetDefDBuff` | `0x001A1E78` | 2 / 0 / 0 | ignored 2 | wrong shape | v0 s32 | `Kernel/Stubs/GS.cpp:ps2_stubs::sceGsSetDefDBuff` | args 5-7 (ztest, zpsm, clear) read from sp+16/20/24; both live callers pass them in t0/t1/t2 = 2, 0x3a, 1 [verified]; the DBuff written through a0 differs from the console in 15/15 of our images (ZBUF, TEST, missing clear packet, display env) [verified]; only +0x0/+0x18/+0x40 appear consumed, section 4.1 |
| 2 | A | `scePad2GetButtonInfo` | `0x001BDA78` | 47 / 0 / 0 | arithmetic 18, stored 4, zero-test 9, unresolved 16 | constant by omission | v0 s32 [inference] | `game_overrides_socom2.cpp:ps2_stubs::scePad2GetButtonInfo` | all 18 arithmetic sites are pressure ids 0x14-0x1f, which return only 0 or 0xFF; FUN_00594cf0, FUN_002964f0, FUN_002c6350 and FUN_002da930 divide them by 255.0 [verified]. Stick ids are the 4 stored sites; digital ids are the 16 unresolved (forwarded to FUN_002d9ff0). Retired: FUN_00594cf0 reads them only after the button is pressed and uses them only in a threshold test, section 4 |
| 3 | A | `__ieee754_rem_pio2f` | `0x001B04F8` | 3 / 0 / 0 | arithmetic 1, const-compare 2 | wrong shape | v0 s32 n; y[0], y[1] via a0 | `Kernel/Stubs/LibC.cpp:ps2_stubs::__ieee754_rem_pio2f` | y[1] is always 0 and the reduction uses a single-float pi/2, where fdlibm splits pi/2 and returns a non-zero y[1] [verified code]; the error is about n x 4.4e-8 rad; Sprint 6 port, section 4.5 |
| 4 | A | `socom2_LumReadPixel` | `0x003B24C0` | 2 / 0 / 0 | ignored 2 | constant by omission | v0 s32 + RGBA via a1 | `game_overrides_socom2.cpp:ps2_stubs::socom2_LumReadPixel` | returns 0 and writes a constant 0x80 grey pixel (exposure readback) [verified code] |
| 5 | A | `_sceRpcGetFPacket` | `0x001A65F8` | 2 / 0 / 2 | unresolved 2 | wrong shape | v0 u32 ptr | `Kernel/Stubs/RPC.cpp:ps2_stubs::sceRpcGetFPacket` | TODO_NAMED returns -1 where the guest dereferences a packet pointer [verified]; both callers have no static jal, so reachable only via a callback [inference] |
| 6 | A | `_sceRpcGetFPacket2` | `0x001A6628` | 1 / 0 / 1 | unresolved 1 | wrong shape | v0 u32 ptr | `Kernel/Stubs/RPC.cpp:ps2_stubs::sceRpcGetFPacket2` | as _sceRpcGetFPacket |
| 7 | A | `vsprintf` | `0x0019E7E8` | 1 / 0 / 0 | ignored 1 | wrong shape | v0 s32 | `Kernel/Stubs/LibC.cpp:ps2_stubs::vsprintf` | writes at most 255 chars and returns the truncated length [verified code] |
| 8 | B | `strcmp` | `0x00198F18` | 602 / 0 / 0 | zero-test 597, ignored 1, unresolved 4 | wrong shape | v0 s32 | `Kernel/Stubs/LibC.cpp:ps2_stubs::strcmp` | host UCRT strcmp returns -1/0/1; newlib returns the byte difference [verified] |
| 9 | B | `strcasecmp` | `0x00198B80` | 265 / 0 / 0 | zero-test 265 | wrong shape | v0 s32 | `Kernel/Stubs/LibC.cpp:ps2_stubs::strcasecmp` | prefix case returns the length difference, not the next char; clipped at 1024 [verified code]; sign preserved |
| 10 | B | `strncmp` | `0x00199648` | 57 / 0 / 0 | zero-test 56, ignored 1 | wrong shape | v0 s32 | `Kernel/Stubs/LibC.cpp:ps2_stubs::strncmp` | as strcmp |
| 11 | B | `sceSifSendCmd` | `0x001A6110` | 5 / 0 / 10 | zero-test 4, ignored 1 | wrong shape | v0 s32 | `Kernel/Syscalls/RPC.cpp:ps2_syscalls::sceSifSendCmd` | reads sp+0x10/0x14 for args 5-6 (EABI puts them in t0/t1); the address is runtime-replaced by socom2_SifSendCmd |
| 12 | B | `_sceSifSendCmd` | `0x001A5FD8` | 1 / 0 / 1 | unresolved 1 | wrong shape | v0 s32 | `Kernel/Syscalls/RPC.cpp:ps2_syscalls::sceSifSendCmd` | guest passes 7 args in a0-a3, t0-t2 [verified FUN_001a6150]; handler reads a1-a3 and sp+0x10/0x14 |
| 13 | C | `scePad2GetState` | `0x001BD938` | 2 / 0 / 1 | stored 1, const-compare 1 | constant by spec | v0 s32 | `game_overrides_socom2.cpp:ps2_stubs::scePad2GetState` | 1 = connected; the guest compares == 1 [verified] |
| 14 | C | `sceCdSync` | `0x0018E768` | 8 / 0 / 1 | const-compare 2, zero-test 2, ignored 3, unresolved 1 | constant by spec | v0 s32 | `Kernel/Stubs/CD.cpp:ps2_stubs::sceCdSync` | 0 = done; the HLE is synchronous |
| 15 | C | `sceCdGetDiskType` | `0x0018F428` | 4 / 0 / 0 | const-compare 4 | constant by spec | v0 s32 | `Kernel/Stubs/CD.cpp:ps2_stubs::sceCdGetDiskType` | 0x14; the guest compares == 0x14 [verified] |
| 16 | D | `rand` | `0x00197740` | 300 / 0 / 0 | arithmetic 288, zero-test 10, ignored 1, unresolved 1 | faithful | v0 s32, 31 bits | `Kernel/Stubs/LibC.cpp:ps2_stubs::rand` | newlib LCG over _rand_next (ede2096) |
| 17 | D | `strlen` | `0x00199288` | 255 / 0 / 2 | arithmetic 90, var-compare 8, stored 9, const-compare 39, zero-test 45, ignored 17, unresolved 47 | faithful | v0 u32 | `Kernel/Stubs/LibC.cpp:ps2_stubs::strlen` |  |
| 18 | D | `strstr` | `0x00199A10` | 38 / 0 / 0 | arithmetic 8, zero-test 30 | faithful | v0 u32 ptr | `Kernel/Stubs/LibC.cpp:ps2_stubs::strstr` |  |
| 19 | D | `malloc` | `0x00194C30` | 20 / 1 / 0 | stored 4, zero-test 1, unresolved 15 | faithful | v0 u32 ptr | `Kernel/Stubs/LibC.cpp:ps2_stubs::malloc` | guestMalloc; the block CONTENT is the leg 0 blind spot |
| 20 | D | `sceDmaGetChan` | `0x00190D20` | 7 / 0 / 0 | stored 4, unresolved 3 | faithful | v0 u32 ptr | `Kernel/Stubs/DMA.cpp:ps2_stubs::sceDmaGetChan` | channel base |
| 21 | D | `sceOpen` | `0x001A7CC0` | 11 / 0 / 1 | stored 3, zero-test 1, unresolved 7 | faithful | v0 s32 | `Kernel/Stubs/FileIO.cpp:ps2_stubs::sceOpen` | fd |
| 22 | D | `__kernel_cosf` | `0x001B1F40` | 5 / 0 / 0 | arithmetic 2, unresolved 3 | faithful | f0 single | `Kernel/Stubs/LibC.cpp:ps2_stubs::__kernel_cosf` | cosf(x+y) |
| 23 | D | `__kernel_sinf` | `0x001B28F8` | 5 / 0 / 0 | arithmetic 2, unresolved 3 | faithful | f0 single | `Kernel/Stubs/LibC.cpp:ps2_stubs::__kernel_sinf` | sinf(x + (iy ? y : 0)) |
| 24 | D | `memchr` | `0x00195688` | 4 / 0 / 0 | arithmetic 2, zero-test 1, unresolved 1 | faithful | v0 u32 ptr | `Kernel/Stubs/LibC.cpp:ps2_stubs::memchr` |  |
| 25 | D | `scePad2CreateSocket` | `0x001BD630` | 2 / 0 / 0 | stored 2 | faithful | v0 s32 | `game_overrides_socom2.cpp:ps2_stubs::scePad2CreateSocket` | incrementing socket |
| 26 | D | `ftell` | `0x00193FA0` | 2 / 0 / 0 | stored 2 | faithful | v0 s32 | `Kernel/Stubs/LibC.cpp:ps2_stubs::ftell` | host |
| 27 | D | `sceLseek` | `0x001A80C8` | 11 / 0 / 0 | stored 1, zero-test 2, ignored 3, unresolved 5 | faithful | v0 s32 | `Kernel/Stubs/FileIO.cpp:ps2_stubs::sceLseek` | offset |
| 28 | D | `sceSifAllocIopHeap` | `0x001AAB00` | 1 / 0 / 0 | stored 1 | faithful | v0 u32 ptr | `Kernel/Stubs/SIF.cpp:ps2_stubs::sceSifAllocIopHeap` | emulated IOP heap address |
| 29 | E | `memcpy` | `0x00195800` | 627 / 9 / 12 | ignored 538, unresolved 89 | faithful | v0 u32 ptr | `Kernel/Stubs/LibC.cpp:ps2_stubs::memcpy` | returns a0 |
| 30 | E | `memset` | `0x001959B8` | 444 / 5 / 4 | ignored 317, unresolved 127 | faithful | v0 u32 ptr | `Kernel/Stubs/LibC.cpp:ps2_stubs::memset` | returns a0 |
| 31 | E | `strcpy` | `0x00199060` | 223 / 2 / 1 | ignored 200, unresolved 23 | faithful | v0 u32 ptr | `Kernel/Stubs/LibC.cpp:ps2_stubs::strcpy` | returns a0 |
| 32 | E | `strncpy` | `0x00199800` | 203 / 2 / 11 | ignored 183, unresolved 20 | faithful | v0 u32 ptr | `Kernel/Stubs/LibC.cpp:ps2_stubs::strncpy` | returns a0 |
| 33 | E | `printf` | `0x00196C20` | 96 / 0 / 0 | ignored 84, unresolved 12 | faithful | v0 s32 | `Kernel/Stubs/LibC.cpp:ps2_stubs::printf` | rendered length, clipped at 2048 |
| 34 | E | `sceSifCallRpc` | `0x001A6C78` | 91 / 0 / 43 | zero-test 75, ignored 15, unresolved 1 | faithful | v0 s32 | `Kernel/Syscalls/RPC.cpp:ps2_syscalls::sceSifCallRpc` | 0 ok; the data comes back in the reply buffer, see section 3.4 |
| 35 | E | `strcat` | `0x00198C58` | 75 / 0 / 0 | ignored 62, unresolved 13 | faithful | v0 u32 ptr | `Kernel/Stubs/LibC.cpp:ps2_stubs::strcat` | returns a0 |
| 36 | E | `sceMcSync` | `0x001B4390` | 75 / 0 / 1 | const-compare 1, zero-test 1, ignored 60, unresolved 13 | faithful | v0 s32 | `Kernel/Stubs/MemoryCard.cpp:ps2_stubs::sceMcSync` | -1 idle / 1 done with live out-params; never 0 (busy) |
| 37 | E | `strncat` | `0x00199498` | 71 / 0 / 0 | ignored 71 | faithful | v0 u32 ptr | `Kernel/Stubs/LibC.cpp:ps2_stubs::strncat` | returns a0 |
| 38 | E | `scePrintf` | `0x001A5BC0` | 68 / 1 / 42 | ignored 67, unresolved 1 | faithful | void | `Kernel/Stubs/TTY.cpp:ps2_stubs::scePrintf` |  |
| 39 | E | `memmove` | `0x001958B0` | 23 / 1 / 0 | ignored 17, unresolved 6 | faithful | v0 u32 ptr | `Kernel/Stubs/LibC.cpp:ps2_stubs::memmove` | returns a0 |
| 40 | E | `free` | `0x00194C88` | 21 / 4 / 0 | ignored 17, unresolved 4 | faithful | void | `Kernel/Stubs/LibC.cpp:ps2_stubs::free` |  |
| 41 | E | `sceSifCheckStatRpc` | `0x001A6E68` | 18 / 1 / 6 | const-compare 2, zero-test 16 | faithful | v0 s32 | `Kernel/Stubs/SIF.cpp:ps2_stubs::sceSifCheckStatRpc` | busy flag |
| 42 | E | `memcmp` | `0x00195768` | 17 / 0 / 0 | zero-test 17 | faithful | v0 s32 | `Kernel/Stubs/LibC.cpp:ps2_stubs::memcmp` | byte difference |
| 43 | E | `sceDmaSync` | `0x001912F0` | 16 / 0 / 0 | ignored 12, unresolved 4 | faithful | v0 s32 | `Kernel/Stubs/DMA.cpp:ps2_stubs::sceDmaSync` |  |
| 44 | E | `sceFsInit` | `0x001A79F0` | 15 / 0 / 2 | ignored 14, unresolved 1 | constant by spec | v0 s32 | `Kernel/Stubs/FileIO.cpp:ps2_stubs::sceFsInit` | 0 |
| 45 | E | `sceGsSyncPath` | `0x001A21A8` | 14 / 0 / 0 | ignored 7, unresolved 7 | faithful | v0 s32 | `Kernel/Stubs/GS.cpp:ps2_stubs::sceGsSyncPath` | busy bitmask / 0 / -1 |
| 46 | E | `sceSifBindRpc` | `0x001A6AA8` | 14 / 0 / 5 | zero-test 14 | faithful | v0 s32 | `Kernel/Stubs/SIF.cpp:ps2_stubs::sceSifBindRpc` | 0 ok |
| 47 | E | `sceClose` | `0x001A7F48` | 14 / 0 / 1 | ignored 11, unresolved 3 | faithful | v0 s32 | `Kernel/Stubs/FileIO.cpp:ps2_stubs::sceClose` |  |
| 48 | E | `fabs` | `0x001B2DB0` | 14 / 0 / 0 | unresolved 14 | faithful | v0 64-bit double | `Kernel/Stubs/LibC.cpp:ps2_stubs::fabs` | db7a992 |
| 49 | E | `sceSifWriteBackDCache` | `0x001A62B8` | 12 / 0 / 27 | ignored 11, unresolved 1 | constant by spec | void | `Kernel/Stubs/SIF.cpp:ps2_stubs::sceSifWriteBackDCache` | 0 |
| 50 | E | `sceSifInitRpc` | `0x001A6368` | 12 / 0 / 5 | ignored 12 | constant by spec | void | `Kernel/Stubs/SIF.cpp:ps2_stubs::sceSifInitRpc` |  |
| 51 | E | `sceMcGetInfo` | `0x001B44C8` | 12 / 0 / 0 | zero-test 6, ignored 6 | constant by spec | v0 s32 | `Kernel/Stubs/MemoryCard.cpp:ps2_stubs::sceMcGetInfo` | as sceMcOpen |
| 52 | E | `fflush` | `0x00192DA8` | 11 / 1 / 5 | zero-test 11 | faithful | v0 s32 | `Kernel/Stubs/LibC.cpp:ps2_stubs::fflush` | host |
| 53 | E | `sceRead` | `0x001A8300` | 11 / 0 / 1 | zero-test 1, ignored 4, unresolved 6 | faithful | v0 s32 | `Kernel/Stubs/FileIO.cpp:ps2_stubs::sceRead` | count |
| 54 | E | `sceGsSyncV` | `0x001A2110` | 10 / 0 / 0 | zero-test 3, ignored 4, unresolved 3 | constant by spec | v0 s32 [inference] | `Kernel/Stubs/GS.cpp:ps2_stubs::sceGsSyncV` | field parity from the vsync tick when interlaced, else constant 1 |
| 55 | E | `sceCdInit` | `0x0018EA98` | 8 / 0 / 0 | ignored 8 | constant by spec | v0 s32 | `Kernel/Stubs/CD.cpp:ps2_stubs::sceCdInit` | 1 |
| 56 | E | `sceCdMmode` | `0x0018F610` | 8 / 0 / 0 | ignored 8 | constant by spec | v0 s32 | `Kernel/Stubs/CD.cpp:ps2_stubs::sceCdMmode` | 1 |
| 57 | E | `sceMcGetDir` | `0x001B46B8` | 8 / 0 / 0 | zero-test 5, ignored 3 | constant by spec | v0 s32 | `Kernel/Stubs/MemoryCard.cpp:ps2_stubs::sceMcGetDir` | as sceMcOpen |
| 58 | E | `floor` | `0x001B2DE8` | 7 / 0 / 0 | unresolved 7 | faithful | v0 64-bit double | `Kernel/Stubs/LibC.cpp:ps2_stubs::floor` | db7a992 |
| 59 | E | `fseek` | `0x00193A90` | 5 / 0 / 0 | zero-test 4, ignored 1 | faithful | v0 s32 | `Kernel/Stubs/LibC.cpp:ps2_stubs::fseek` | host |
| 60 | E | `_malloc_r` | `0x00194F28` | 5 / 0 / 6 | unresolved 5 | faithful | v0 u32 ptr | `Kernel/Stubs/Compatibility.cpp:ps2_stubs::malloc_r` | as malloc |
| 61 | E | `sceMcOpen` | `0x001B3D40` | 5 / 0 / 1 | zero-test 4, ignored 1 | constant by spec | v0 s32 | `Kernel/Stubs/MemoryCard.cpp:ps2_stubs::sceMcOpen` | 0 = queued; the result comes back through sceMcSync |
| 62 | E | `sceMcClose` | `0x001B3EA0` | 5 / 0 / 0 | zero-test 4, ignored 1 | constant by spec | v0 s32 | `Kernel/Stubs/MemoryCard.cpp:ps2_stubs::sceMcClose` | as sceMcOpen |
| 63 | E | `sceMcRead` | `0x001B40C0` | 5 / 0 / 0 | zero-test 2, ignored 3 | constant by spec | v0 s32 | `Kernel/Stubs/MemoryCard.cpp:ps2_stubs::sceMcRead` | as sceMcOpen |
| 64 | E | `sceMcWrite` | `0x001B41D8` | 5 / 0 / 0 | zero-test 5 | constant by spec | v0 s32 | `Kernel/Stubs/MemoryCard.cpp:ps2_stubs::sceMcWrite` | as sceMcOpen |
| 65 | E | `sceDmaSend` | `0x00191050` | 4 / 0 / 0 | ignored 4 | faithful | v0 s32 | `Kernel/Stubs/DMA.cpp:ps2_stubs::sceDmaSend` |  |
| 66 | E | `exit` | `0x00192BF8` | 4 / 0 / 0 | ignored 2, unresolved 2 | constant by spec | void | `Kernel/Stubs/System.cpp:ps2_stubs::exit` | stops the runtime |
| 67 | E | `strchr` | `0x00198D88` | 4 / 0 / 0 | zero-test 4 | faithful | v0 u32 ptr | `Kernel/Stubs/LibC.cpp:ps2_stubs::strchr` |  |
| 68 | E | `sceSifExitCmd` | `0x001A5F18` | 4 / 0 / 0 | ignored 4 | constant by spec | v0 s32 | `Kernel/Stubs/SIF.cpp:ps2_stubs::sceSifExitCmd` | 0 |
| 69 | E | `sceMcSeek` | `0x001B3F58` | 4 / 0 / 0 | zero-test 3, ignored 1 | constant by spec | v0 s32 | `Kernel/Stubs/MemoryCard.cpp:ps2_stubs::sceMcSeek` | as sceMcOpen |
| 70 | E | `sceCdReadClock` | `0x0018F6E0` | 3 / 0 / 0 | zero-test 1, ignored 2 | faithful | v0 s32 | `Kernel/Stubs/CD.cpp:ps2_stubs::sceCdReadClock` | host clock |
| 71 | E | `_calloc_r` | `0x00191630` | 3 / 0 / 0 | unresolved 3 | faithful | v0 u32 ptr | `Kernel/Stubs/Compatibility.cpp:ps2_stubs::calloc_r` | guestCalloc |
| 72 | E | `__malloc_lock` | `0x00195A78` | 3 / 0 / 7 | ignored 3 | faithful | void | `Kernel/Stubs/Compatibility.cpp:ps2_stubs::__malloc_lock` |  |
| 73 | E | `__malloc_unlock` | `0x00195AF8` | 3 / 0 / 12 | ignored 3 | faithful | void | `Kernel/Stubs/Compatibility.cpp:ps2_stubs::__malloc_unlock` |  |
| 74 | E | `sceGsSetDefLoadImage` | `0x001A2520` | 3 / 0 / 0 | ignored 3 | constant by spec | v0 s32 | `Kernel/Stubs/GS.cpp:ps2_stubs::sceGsSetDefLoadImage` | 0 |
| 75 | E | `sceGsSetDefStoreImage` | `0x001A2708` | 3 / 0 / 0 | ignored 3 | constant by spec | v0 s32 | `Kernel/Stubs/GS.cpp:ps2_stubs::sceGsSetDefStoreImage` | 0 |
| 76 | E | `sceGsExecLoadImage` | `0x001A2848` | 3 / 0 / 0 | ignored 3 | constant by spec | v0 s32 | `Kernel/Stubs/GS.cpp:ps2_stubs::sceGsExecLoadImage` | 0 / -1 |
| 77 | E | `sceWrite` | `0x001A8560` | 3 / 0 / 0 | unresolved 3 | faithful | v0 s32 | `Kernel/Stubs/FileIO.cpp:ps2_stubs::sceWrite` | count |
| 78 | E | `sceMcInit` | `0x001B3970` | 3 / 0 / 0 | zero-test 2, ignored 1 | constant by spec | v0 s32 | `Kernel/Stubs/MemoryCard.cpp:ps2_stubs::sceMcInit` | 0 |
| 79 | E | `sceMcChdir` | `0x001B4888` | 3 / 0 / 0 | zero-test 1, ignored 2 | constant by spec | v0 s32 | `Kernel/Stubs/MemoryCard.cpp:ps2_stubs::sceMcChdir` | as sceMcOpen |
| 80 | E | `sceMcDelete` | `0x001B4A98` | 3 / 0 / 0 | zero-test 2, ignored 1 | constant by spec | v0 s32 | `Kernel/Stubs/MemoryCard.cpp:ps2_stubs::sceMcDelete` | as sceMcOpen |
| 81 | E | `sceMpegAddStrCallback` | `0x001BAE20` | 3 / 0 / 0 | ignored 2, unresolved 1 | constant by spec | v0 s32 | `Kernel/Stubs/MPEG.cpp:ps2_stubs::sceMpegAddStrCallback` | 0 |
| 82 | E | `sceMpegAddCallback` | `0x001BBB88` | 3 / 0 / 0 | ignored 3 | faithful | v0 s32 | `Kernel/Stubs/MPEG.cpp:ps2_stubs::sceMpegAddCallback` | handle |
| 83 | E | `scePad2Init` | `0x001BD588` | 2 / 0 / 0 | ignored 2 | constant by spec | v0 s32 | `game_overrides_socom2.cpp:ps2_stubs::scePad2Init` | 1 when the pad is enabled |
| 84 | E | `scePad2Read` | `0x001BD790` | 2 / 0 / 0 | unresolved 2 | constant by spec | v0 s32 | `game_overrides_socom2.cpp:ps2_stubs::scePad2Read` | constant 32; its only consumer is beqz [verified FUN_002da930] |
| 85 | E | `sceCdSyncS` | `0x0018E808` | 2 / 0 / 1 | zero-test 2 | constant by spec | v0 s32 | `Kernel/Stubs/CD.cpp:ps2_stubs::sceCdSyncS` | 0 |
| 86 | E | `sceCdStStop` | `0x0018F8A0` | 2 / 0 / 0 | ignored 2 | constant by spec | v0 s32 | `Kernel/Stubs/CD.cpp:ps2_stubs::sceCdStStop` | 1 |
| 87 | E | `sceDmaReset` | `0x00190D48` | 2 / 0 / 0 | ignored 2 | constant by spec | v0 s32 | `Kernel/Stubs/DMA.cpp:ps2_stubs::sceDmaReset` | 0 |
| 88 | E | `sceDmaSendN` | `0x001910B8` | 2 / 0 / 0 | ignored 2 | faithful | v0 s32 | `Kernel/Stubs/DMA.cpp:ps2_stubs::sceDmaSendN` |  |
| 89 | E | `sceDmaPause` | `0x00191360` | 2 / 0 / 0 | ignored 2 | constant by spec | v0 s32 | `Kernel/Stubs/DMA.cpp:ps2_stubs::sceDmaPause` | TODO_NAMED -1 |
| 90 | E | `_free_r` | `0x00193628` | 2 / 0 / 12 | ignored 2 | faithful | void | `Kernel/Stubs/Compatibility.cpp:ps2_stubs::free_r` |  |
| 91 | E | `_mbtowc_r` | `0x00195650` | 2 / 0 / 0 | unresolved 2 | faithful | v0 s32 | `Kernel/Stubs/Compatibility.cpp:ps2_stubs::mbtowc_r` | C locale, single byte |
| 92 | E | `_realloc_r` | `0x00197870` | 2 / 0 / 0 | unresolved 2 | faithful | v0 u32 ptr | `Kernel/Stubs/Compatibility.cpp:ps2_stubs::realloc_r` | guestRealloc |
| 93 | E | `strrchr` | `0x001999C0` | 2 / 0 / 0 | zero-test 2 | faithful | v0 u32 ptr | `Kernel/Stubs/LibC.cpp:ps2_stubs::strrchr` |  |
| 94 | E | `sceGsResetGraph` | `0x001A13D0` | 2 / 0 / 0 | ignored 1, unresolved 1 | constant by spec | v0 s32 | `Kernel/Stubs/GS.cpp:ps2_stubs::sceGsResetGraph` | 0 |
| 95 | E | `sceGsResetPath` | `0x001A1570` | 2 / 0 / 0 | ignored 2 | constant by spec | v0 s32 | `Kernel/Stubs/GS.cpp:ps2_stubs::sceGsResetPath` | 0 |
| 96 | E | `sceGsPutDispEnv` | `0x001A1A00` | 2 / 0 / 0 | ignored 2 | constant by spec | v0 s32 | `Kernel/Stubs/GS.cpp:ps2_stubs::sceGsPutDispEnv` | 0 / -1 |
| 97 | E | `sceGsExecStoreImage` | `0x001A29C8` | 2 / 0 / 0 | ignored 2 | constant by spec | v0 s32 | `Kernel/Stubs/GS.cpp:ps2_stubs::sceGsExecStoreImage` | 0 / -1 |
| 98 | E | `InitThread` | `0x001A48F8` | 2 / 0 / 0 | ignored 2 | constant by spec | v0 s32 | `Kernel/Syscalls/Thread.cpp:ps2_syscalls::InitThread` | main thread id |
| 99 | E | `sceSifAddCmdHandler` | `0x001A5F80` | 2 / 0 / 6 | ignored 2 | constant by spec | void | `Kernel/Stubs/SIF.cpp:ps2_stubs::sceSifAddCmdHandler` | 0 |
| 100 | E | `sceFsReset` | `0x001A7C88` | 2 / 0 / 0 | ignored 2 | constant by spec | v0 s32 | `Kernel/Stubs/FileIO.cpp:ps2_stubs::sceFsReset` | 0 |
| 101 | E | `sceIoctl` | `0x001A8820` | 2 / 0 / 0 | ignored 2 | constant by spec | v0 s32 | `Kernel/Stubs/FileIO.cpp:ps2_stubs::sceIoctl` | 0; cmd 1 writes 0 to *a2 |
| 102 | E | `sceSifInitIopHeap` | `0x001AAA78` | 2 / 0 / 0 | ignored 2 | constant by spec | v0 s32 | `Kernel/Stubs/SIF.cpp:ps2_stubs::sceSifInitIopHeap` | 0 |
| 103 | E | `sceSifLoadFileReset` | `0x001AB158` | 2 / 0 / 0 | ignored 2 | constant by spec | v0 s32 | `Kernel/Stubs/SIF.cpp:ps2_stubs::sceSifLoadFileReset` | 0 |
| 104 | E | `_sceSifLoadModuleBuffer` | `0x001AB190` | 2 / 0 / 0 | unresolved 2 | faithful | v0 s32 | `Kernel/Syscalls/System.cpp:ps2_syscalls::sceSifLoadModuleBuffer` | module id |
| 105 | E | `_sceSifLoadModule` | `0x001AB7A0` | 2 / 0 / 0 | unresolved 2 | faithful | v0 s32 | `Kernel/Syscalls/System.cpp:ps2_syscalls::sceSifLoadModule` | module id |
| 106 | E | `sceSifSyncIop` | `0x001ABE90` | 2 / 0 / 0 | zero-test 2 | constant by spec | v0 s32 | `Kernel/Stubs/SIF.cpp:ps2_stubs::sceSifSyncIop` | 1 = IOP ready |
| 107 | E | `sceSifRebootIop` | `0x001ABEC8` | 2 / 0 / 0 | zero-test 2 | constant by spec | v0 s32 | `Kernel/Stubs/SIF.cpp:ps2_stubs::sceSifRebootIop` | 1 |
| 108 | E | `sceMpegReset` | `0x001BBAD8` | 2 / 0 / 1 | ignored 2 | constant by spec | v0 s32 | `Kernel/Stubs/MPEG.cpp:ps2_stubs::sceMpegReset` |  |
| 109 | E | `_sceMpegFlush` | `0x001BC1C0` | 2 / 0 / 0 | ignored 2 | constant by spec | v0 s32 | `Kernel/Stubs/MPEG.cpp:ps2_stubs::sceMpegFlush` | 0 |
| 110 | E | `scePad2GetButtonProfile` | `0x001BD868` | 1 / 0 / 0 | unresolved 1 | constant by spec | v0 s32 | `game_overrides_socom2.cpp:ps2_stubs::scePad2GetButtonProfile` | 5 / -1 |
| 111 | E | `sceVibGetProfile` | `0x001BE530` | 1 / 0 / 0 | unresolved 1 | constant by spec | v0 s32 | `game_overrides_socom2.cpp:ps2_stubs::sceVibGetProfile` | 0 actuators, by choice |
| 112 | E | `sceVibSetActParam` | `0x001BE5B0` | 1 / 0 / 0 | unresolved 1 | constant by spec | v0 s32 | `game_overrides_socom2.cpp:ps2_stubs::sceVibSetActParam` | 1 |
| 113 | E | `sceCdDiskReady` | `0x0018EF70` | 1 / 0 / 0 | ignored 1 | constant by spec | v0 s32 | `Kernel/Stubs/CD.cpp:ps2_stubs::sceCdDiskReady` | 2 = ready |
| 114 | E | `sceCdRead` | `0x0018F178` | 1 / 0 / 0 | unresolved 1 | faithful | v0 s32 | `Kernel/Stubs/CD.cpp:ps2_stubs::sceCdRead` | 1 / 0 |
| 115 | E | `sceCdGetError` | `0x0018F4C0` | 1 / 0 / 0 | unresolved 1 | faithful | v0 s32 | `Kernel/Stubs/CD.cpp:ps2_stubs::sceCdGetError` | last error |
| 116 | E | `sceCdStInit` | `0x0018F7D8` | 1 / 0 / 0 | ignored 1 | constant by spec | v0 s32 | `Kernel/Stubs/CD.cpp:ps2_stubs::sceCdStInit` | 1 / 0 on bad args |
| 117 | E | `sceCdStStart` | `0x0018F808` | 1 / 0 / 0 | ignored 1 | constant by spec | v0 s32 | `Kernel/Stubs/CD.cpp:ps2_stubs::sceCdStStart` | 1 |
| 118 | E | `sceCdStSeek` | `0x0018F870` | 1 / 0 / 0 | zero-test 1 | constant by spec | v0 s32 | `Kernel/Stubs/CD.cpp:ps2_stubs::sceCdStSeek` | 1 |
| 119 | E | `sceCdStRead` | `0x0018F8D8` | 1 / 0 / 0 | unresolved 1 | faithful | v0 s32 | `Kernel/Stubs/CD.cpp:ps2_stubs::sceCdStRead` | sectors |
| 120 | E | `fread` | `0x00193508` | 1 / 0 / 0 | zero-test 1 | faithful | v0 u32 | `Kernel/Stubs/LibC.cpp:ps2_stubs::fread` | host |
| 121 | E | `_memalign_r` | `0x00194A68` | 1 / 0 / 0 | unresolved 1 | faithful | v0 u32 ptr | `Kernel/Stubs/Compatibility.cpp:ps2_stubs::memalign_r` | guestMalloc(align) |
| 122 | E | `sceGsSetDefDispEnv` | `0x001A1688` | 1 / 0 / 2 | ignored 1 | constant by spec | v0 s32 | `Kernel/Stubs/GS.cpp:ps2_stubs::sceGsSetDefDispEnv` | 0 |
| 123 | E | `sceIpuStopDMA` | `0x001A31A8` | 1 / 0 / 0 | ignored 1 | constant by spec | v0 s32 | `Kernel/Stubs/IPU.cpp:ps2_stubs::sceIpuStopDMA` | 0 |
| 124 | E | `sceIpuRestartDMA` | `0x001A3290` | 1 / 0 / 0 | ignored 1 | constant by spec | v0 s32 | `Kernel/Stubs/IPU.cpp:ps2_stubs::sceIpuRestartDMA` | 0 |
| 125 | E | `write` | `0x001A40E8` | 1 / 0 / 0 | unresolved 1 | faithful | v0 s32 | `Kernel/Stubs/FileIO.cpp:ps2_stubs::write` | fioWrite |
| 126 | E | `read` | `0x001A4168` | 1 / 0 / 0 | unresolved 1 | faithful | v0 s32 | `Kernel/Stubs/FileIO.cpp:ps2_stubs::read` | fioRead |
| 127 | E | `_sceSDC` | `0x001A4370` | 1 / 1 / 0 | unresolved 1 | constant by spec | v0 s32 [inference] | `Kernel/Stubs/System.cpp:ps2_stubs::sceSDC` | 0; the primitive under a cache-sync wrapper [inference] |
| 128 | E | `_sceIDC` | `0x001A44B0` | 1 / 1 / 0 | unresolved 1 | constant by spec | v0 s32 [inference] | `Kernel/Stubs/System.cpp:ps2_stubs::sceIDC` | 0; interrupt-context twin of _sceSDC [inference] |
| 129 | E | `iWakeupThread` | `0x001A49D0` | 1 / 4 / 0 | ignored 1 | faithful | v0 s32 | `Kernel/Syscalls/Thread.cpp:ps2_syscalls::iWakeupThread` | scheduler result |
| 130 | E | `sceDeci2Close` | `0x001A4BC8` | 1 / 0 / 0 | ignored 1 | constant by spec | v0 s32 | `Kernel/Stubs/Deci2.cpp:ps2_stubs::sceDeci2Close` | TODO_NAMED -1 |
| 131 | E | `sceDeci2ReqSend` | `0x001A4BF0` | 1 / 0 / 1 | unresolved 1 | constant by spec | v0 s32 | `Kernel/Stubs/Deci2.cpp:ps2_stubs::sceDeci2ReqSend` | TODO_NAMED -1 |
| 132 | E | `_printf` | `0x001A5598` | 1 / 0 / 1 | unresolved 1 | faithful | v0 s32 | `Kernel/Stubs/LibC.cpp:ps2_stubs::printf` | as printf |
| 133 | E | `sceSifRemoveCmdHandler` | `0x001A5FB0` | 1 / 0 / 0 | unresolved 1 | constant by spec | void | `Kernel/Stubs/SIF.cpp:ps2_stubs::sceSifRemoveCmdHandler` | 0 |
| 134 | E | `_sceFsSemInit` | `0x001A7898` | 1 / 0 / 0 | ignored 1 | constant by spec | v0 s32 | `Kernel/Stubs/FileIO.cpp:ps2_stubs::sceFsSemInit` | TODO_NAMED -1 |
| 135 | E | `_sceSifLoadElfPart` | `0x001ABA08` | 1 / 0 / 1 | unresolved 1 | faithful | v0 s32 | `Kernel/Syscalls/System.cpp:ps2_syscalls::sceSifLoadElfPart` |  |
| 136 | E | `InitAlarm` | `0x001ACFB0` | 1 / 0 / 0 | ignored 1 | constant by spec | v0 s32 | `Kernel/Syscalls/Sync.cpp:ps2_syscalls::InitAlarm` | KE_OK |
| 137 | E | `tan` | `0x001B3138` | 1 / 0 / 0 | unresolved 1 | faithful | v0 64-bit double | `Kernel/Stubs/LibC.cpp:ps2_stubs::tan` | db7a992 |
| 138 | E | `sceMcEnd` | `0x001B3B40` | 1 / 0 / 0 | ignored 1 | constant by spec | v0 s32 | `Kernel/Stubs/MemoryCard.cpp:ps2_stubs::sceMcEnd` | 0 |
| 139 | E | `sceMcMkdir` | `0x001B3E68` | 1 / 0 / 0 | zero-test 1 | constant by spec | v0 s32 | `Kernel/Stubs/MemoryCard.cpp:ps2_stubs::sceMcMkdir` | as sceMcOpen |
| 140 | E | `sceMcFormat` | `0x001B49C8` | 1 / 0 / 0 | zero-test 1 | constant by spec | v0 s32 | `Kernel/Stubs/MemoryCard.cpp:ps2_stubs::sceMcFormat` | as sceMcOpen |
| 141 | E | `sceMcFlush` | `0x001B4BB0` | 1 / 0 / 0 | zero-test 1 | constant by spec | v0 s32 | `Kernel/Stubs/MemoryCard.cpp:ps2_stubs::sceMcFlush` | as sceMcOpen |
| 142 | E | `sceMpegDemuxPssRing` | `0x001BAB08` | 1 / 0 / 0 | unresolved 1 | faithful | v0 s32 | `Kernel/Stubs/MPEG.cpp:ps2_stubs::sceMpegDemuxPssRing` | bytes consumed |
| 143 | E | `sceMpegInit` | `0x001BB688` | 1 / 0 / 0 | ignored 1 | constant by spec | v0 s32 | `Kernel/Stubs/MPEG.cpp:ps2_stubs::sceMpegInit` | 0 |
| 144 | E | `sceMpegCreate` | `0x001BB738` | 1 / 0 / 0 | ignored 1 | faithful | v0 u32 ptr | `Kernel/Stubs/MPEG.cpp:ps2_stubs::sceMpegCreate` |  |
| 145 | E | `sceMpegGetPicture` | `0x001BB990` | 1 / 0 / 0 | zero-test 1 | constant by spec | v0 s32 | `Kernel/Stubs/MPEG.cpp:ps2_stubs::sceMpegGetPicture` | 0 |
| 146 | E | `GetRomName` | `0x001BDE40` | 1 / 0 / 0 | ignored 1 | faithful | v0 u32 ptr | `Kernel/Syscalls/System.cpp:ps2_syscalls::GetRomName` | buffer |
| 147 | E | `socom2_RsaGenerateKeyPair` | `0x0062B168` | 0 / 1 / 0 | - | constant by spec | void | `game_overrides_socom2.cpp:ps2_stubs::socom2_RsaGenerateKeyPair` | fixed key pair by design |
| 148 | E | `sceCdSeek` | `0x0018F358` | 0 / 1 / 0 | - | constant by spec | v0 s32 | `Kernel/Stubs/CD.cpp:ps2_stubs::sceCdSeek` | 1 |
| 149 | E | `sceIpuSync` | `0x001A33E0` | 0 / 1 / 0 | - | constant by spec | v0 s32 | `Kernel/Stubs/IPU.cpp:ps2_stubs::sceIpuSync` | 0 |
| 150 | E | `InitTLB` | `0x001AC2B0` | 0 / 1 / 0 | - | constant by spec | v0 s32 | `Kernel/Syscalls/System.cpp:ps2_syscalls::InitTLB` | KE_OK |

**No live static site (73) [verified]:** `sceCdDelayThread` (dead 3), `sceCdCallback`, `sceCdInitEeCB`, `sceCdNcmdDiskReady` (dead 2), `sceCdStSeekF`, `sceCdStPause`, `sceCdStResume`, `sceCdStStat`, `sceCdStream` (dead 10), `memclr` (dead 1), `sceDmaPutEnv` (dead 1), `sceDmaGetEnv`, `sceDmaSendI`, `sceDmaRecv`, `sceDmaRecvN`, `sceDmaRecvI`, `sceDmaWatch`, `fclose`, `_malloc_trim_r` (dead 1), `fwrite`, `malloc_extend_top` (dead 1), `_printf_r`, `__divdi3` (dead 1), `sceGszbufaddr` (dead 3), `sceGsSetDefDrawEnv` (dead 2), `sceGsSetDefClear` (dead 2), `sceIpuInit` (dead 1), `iRotateThreadReadyQueue`, `sceDeci2Open` (dead 1), `sceDeci2Poll` (dead 1), `sceDeci2ExRecv` (dead 1), `sceDeci2ExSend` (dead 1), `sceDeci2ExReqSend`, `sceDeci2ExLock`, `sceDeci2ExUnLock`, `sceTtyHandler`, `sceTtyWrite` (dead 1), `sceTtyRead` (dead 1), `sceTtyInit` (dead 2), `sceSifInitCmd` (dead 1), `_sceSifCmdIntrHdlr`, `sceSifGetOtherData`, `sceSifSetRpcQueue`, `sceSifRegisterRpc`, `sceSifRemoveRpc`, `sceSifRemoveRpcQueue`, `sceSifGetNextRequest` (dead 1), `sceSifExecRequest` (dead 1), `sceSifRpcLoop`, `sceSifAllocSysMemory`, `sceSifLoadIopHeap`, `sceSifLoadElf`, `sceSifGetIopAddr`, `sceSifSetIopAddr`, `sceSifResetIop` (dead 1), `sceSifIsAliveIop`, `cos` (addr-taken 1), `sin` (addr-taken 1), `sceMcChangeThreadPriority`, `sceMcGetSlotMax`, `mceIntrReadFixAlign`, `mceGetInfoApdx`, `mceStorePwd`, `sceMcSetFileInfo`, `sceMcRename`, `sceMcUnformat`, `sceMcGetEntSpace`, `sceMpegAddBs`, `sceMpegGetPictureRAW8`, `sceMpegGetPictureRAW8xy`, `sceMpegGetDecodeMode`, `sceMpegClearRefBuff` (dead 1), `sceVpu0Reset`.

---

## 3. What this census cannot see

### 3.1 Tail calls — 37 live sites over 17 stubs [verified]

`PS2X_HLE_STATS` and `PS2X_CALL_TRACE` count calls that go through
`PS2Runtime::dispatchGuestBranch`. A recompiled `j` to a stub becomes a direct C++ call to the
generated wrapper (`sub_00194C30_0x194c30(rdram, ctx, runtime); return;`) and skips it
**[verified in `sub_00243298`]**. The ELF has **37 live `j` sites over 17 stubs**: `memcpy` 9,
`memset` 5, `free` 4, `iWakeupThread` 4, `strcpy` 2, `strncpy` 2, and one each for `malloc`,
`memmove`, `fflush`, `scePrintf`, `sceSifCheckStatRpc`, `sceCdSeek`, `sceIpuSync`, `_sceSDC`,
`_sceIDC`, `InitTLB`, `socom2_RsaGenerateKeyPair`. Seven more are inside stubbed bodies (dead).

`KNOWN.md` §4's "~50 sites over 19 stubs (memcpy 10, iWakeupThread 7, free 5, memset 5)" counts
**generated** call sites. The generated tree has **45** tail calls over 17 stubs because Ghidra's
overlapping function entries are recompiled twice: `0x62c178` appears in both `FUN_0062c168` and
`sub_0062C070`, `0x63dc88` in `FUN_0063dc78` and `sub_0063DB68` **[verified]**. The 37 unique
ELF sites equal the set of generated sites exactly (no ELF-only or generated-only live site)
**[verified]**. So HLE_STATS undercounts per *execution*, not per site, and the undercounted
stubs are the 17 above.

For a tail site the consumer is the caller's caller: every `j` site above is marked
"consumer upstream" and not classified.

### 3.2 Declared but never reached [verified]

The nine names `KNOWN.md` §4 lists (`sceCdInitEeCB`, `sceDmaGetEnv`, `fclose`,
`sceDeci2ExReqSend`, `sceSifRegisterRpc`, `sceSifLoadElf`, `sceMpegAddBs`,
`sceMpegGetDecodeMode`, `sceVpu0Reset`) have **no generated wrapper**, **zero** `jal`/`j` sites
and **zero** data references. A further **64** bound stubs have a wrapper but no live static
site (the §2.3 list). 24 of those have only dead sites inside other stubbed bodies; `cos` and
`sin` have only the table entry in §3.3. The rest are reachable, if at all, through `jalr`.

### 3.3 Indirect calls

- **Data words [verified]:** one five-entry table at `0x1d55ac` holds `free`, `memset`, `memcpy`,
  `cos`, `sin`, in that order (the function map files it under `FUN_001d4ff0`; it is in the
  `0x1d5000` data segment). Calls through it are invisible to the site scan and, like tail calls,
  may bypass HLE_STATS **[inference]**.
- **Code-constructed pointers:** `lui`/`addiu` pairs loading a stub address into a register are
  **not** counted.
- **Callbacks:** `_sceRpcGetFPacket`/`_sceRpcGetFPacket2` are called from `FUN_001a6780` and
  `FUN_001a69f8`, and `_sceSifSendCmd` from `FUN_001a6150` → `FUN_001a6720`/`FUN_001a6780`;
  none of those has a static caller **[verified]**. They look like SIF command handlers
  registered by address, which our SIF HLE does not invoke **[inference]**.

### 3.4 Values that do not come back in `$v0` — the `0x200` class itself

The `0x200` defect would **not** appear in this census. `sceInetInterfaceControl` is recompiled
guest code (`FUN_002465e8`). It calls `FUN_00245ad8`, which calls the runtime-replaced msifrpc
transport (`socom2_MsifCall` at `0x1bd320`) **[verified]**, and the value the guest differenced came back **in the RPC
reply buffer**, written by `socom2_libnetb::call` **[verified]**. The same holds for every
`sceSifCallRpc` (91 live sites): its `$v0` is 0 for success, and its data is the reply payload.

Reply words that `socom2_libnetb::call` answers with a constant **[verified]**:

| fno | guest routine | constant | consumer |
|---|---|---|---|
| 8 | `sceInetGetInterfaceList` | count 1, id `kIfId` | not censused |
| 9 code 8 | `sceInetInterfaceControl` (link state) | `3` (attached + up), constant by spec while the link is up | bit tests in `FUN_00246d10` and `FUN_0062e7e0`; stored in `FUN_0030bd40` |
| 9 code 2 / 3 | interface name / description | `"smap0"`, `"SCE Ethernet (Network Adaptor)"` | strings |
| 9 code 0xb | netmask | `255.255.255.0` | not censused |
| 9 other codes | — | all-zero payload | the guest calls only 2, 3, 8, 0xb, 0x200 **[verified in the decomp]** |
| 4 / 0xd / 5 / 0xe | `sceInetRecv`/`RecvFrom`/`Send`/`SendTo` | `flags` word `0` (Recv: `4` on EOF) | not censused |
| 0x1e–0x20, 0x32–0x34 | (unnamed) | `0` | not censused |
| 0x21 / 0x22 | wait attached / started | `1` / `4`, id, `0` | not censused |
| 0x23 | event poll | `kErrNoEvent`, `-1`: never an event | wrapper `FUN_00246f90` is dead code (no callers) |
| 0x35 | `sceInetCtlGetState` | `3` | wrapper `FUN_002469c0` is dead code (no callers) |
| 0x64 / 0x65 | ex async start | `0` | EE path replaced |

The same applies to plain **out-parameters** of toml stubs **[verified code]**:
`socom2_LumReadPixel` writes a constant grey `0x80808080` pixel; `sceVibGetProfile` a zero
profile; `sceIoctl(cmd 1)` a zero word; `scePad2GetButtonProfile` a constant DS2 profile;
`__ieee754_rem_pio2f` a zero `y[1]`; and `sceGsSetDefDBuff` a whole display/draw environment built
from wrong arguments and missing its clear packets (§4.1). PS2X_HLE_STATS (Step 4) watches `$v0` only, so it is blind to all of
these.

### 3.5 Runtime bindings outside the toml [verified]

`applySocom2` binds 27 more addresses with `PS2Runtime::replaceFunction` or
`bindAddressHandler`; one of them (`0x1a6110`) is also a toml stub. Running the census over the
other 26 with `--extra` (the argument list is in the Step 2 report) finds no arithmetic or stored `$v0` consumer. `ret0` at `0x247c98` (the "descriptor DMA helper")
has 3 live zero-test sites in `FUN_002457f0`. `socom2_DnasTickDone` at `0x2cc670` is reached
only through one data word. `exAvailable`'s one caller copies the value and does arithmetic on the
copy after a branch (unresolved by rule). These bindings also make more toml sites dead than the toml-only rule
sees: with them included, `sceSifSendCmd` has 0 live sites (not 5), `strncat` 60 (not 71), and
`scePrintf` 64 (not 68).

### 3.6 Classifier limits

507 direct sites (12 %) are unresolved, mostly register copies (`memcpy`/`memset` results kept in
callee-saved registers, and soft-double results forwarded into the next `__muldf3`-style call).
A value can also be consumed after the 12-instruction budget. "Ignored" is exact for the window
walked, but a value can still be read later through a copy made before it was overwritten; the
tool reports such copies as unresolved, not ignored **[verified by unit test]**.

**Arithmetic is undercounted.** The classifier treats every shift by a constant as a transparent
mask. `sll v0,v0,11` at `0x30ba08` after `sceCdStRead` is x2048 arithmetic, but it is followed as if
the value were unchanged, and the site takes the class of the next use. The 411 arithmetic count
is therefore a lower bound **[verified by review]**.

---

## 4. Top five suspects, and the experiment that settles each

This ranking comes after an independent review of the draft. The review's corrections are listed in the Step 2 report.

### 4.1 `sceGsSetDefDBuff`: wrong argument ABI and a missing clear packet — **divergence [verified], visible effect likely none [inference]**

**What the stub does.** `ps2_stubs::sceGsSetDefDBuff` (`Kernel/Stubs/GS.cpp`) reads `ztest`, `zpsm` and `clear` with `readStackU32(ctx, 16/20/24)` and then discards `clear`.

**What the house convention is.** Trailing arguments are passed in registers. `sceGsSetDefDBuffDc` reads them with `decodeGsTrailingArgs3` (`$t0`/`$t1`/`$t2`, `Helpers/Support.h`), and `ps2_gs_tests` has a register-ABI test for it.

**What both live callers pass [verified]:**

- `$t0 = 2` (ztest GEQUAL);
- `$t1 = 0x3a` (zpsm);
- `$t2 = 1` (clear), loaded in the delay slot.

The sites are `0x1c680c` in `FUN_001c67c0` (DBuff `0x1e6410`) and `0x3b16c8` in `FUN_003b14a0` (DBuff `0x4a4180`).

The DBuff at `0x1e6410` in existing RDRAM images (zero runs) **[verified]**:

| field | ours (**15 of 15** images) | PCSX2 (`title`, `spawn`, `postload`) |
|---|---|---|
| `ZBUF_1` (+0x70) | psm 0, zmsk 1, zbp `0x118` | psm `0xa`, zmsk 0, zbp `0x8c` |
| `TEST_1` (+0xD0) | ztst 1 (ALWAYS) | `0x50000` (ztst 2, GEQUAL) |
| clear packet (+0xE0..+0x13F, and again at +0x1D0) | all zero | `TEST 0x30000`, `PRIM 6`, `RGBAQ` q = 1.0, `XYZ2` (0x6c00, 0x7200) / (0x9400, 0x8e00), then `TEST 0x50000` |
| `disp[1].display` (+0x40) | DX 640, DY 33, MAGH 0, DW 639 | DX 640, DY 51, MAGH 3, DW 2559 |
| `PMODE` (+0x00) | `0x8007` | `0x66` |

The review decoded DY as 32 / 50; either way the gap is 18 lines. The guest's own `FUN_001a1e78` seeds both clear packets by calling `FUN_001a1d70` twice, both times in context 1. Our stub never writes them.

**Which of it is consumed.** An ELF scan for `lui`/immediate references into the DBuff finds only offsets +0x0, +0x18 and +0x40. There is no `sceGsSwapDBuff`, and `FUN_001c67c0` is a boot-splash init **[verified by review]**.

- **Not sent:** the ZBUF, TEST and clear bytes appear never to be sent. The likely visible effect of the ABI bug is therefore **none** **[inference]**. No depth symptom is recorded in `STATUS.md` or `research/17`.
- **Sent every flip:** +0x40 `disp[1].display`, which becomes `REG_GS_DISPLAY1/2`. It differs from the console (table above, and §4.3).

**The fix.**

- Read args 5–7 with `decodeGsTrailingArgs3`.
- Seed both clear packets as `FUN_001a1d70` does, in context 1.
- Add a unit test with `t0 = 2, t1 = 0x3a, t2 = 1` and garbage on the stack.

**Acceptance.** One title image after the fix must show:

- ZBUF psm `0xa` and zmsk 0;
- TEST `0x50000`;
- a clear packet byte-identical to `title_pcsx2` +0xE0..+0x13F.

**zbp is excluded** (§4.4). This is one fix, it can land now, and the risk is low.

### 4.2 Heap block content behind `malloc` (Leg 0) — **under review [inference]**

The allocators (`malloc`/`_malloc_r`/`_calloc_r`/`_realloc_r`/`_memalign_r`) return faithful addresses. `malloc` has 4 stored sites, 15 unresolved and 1 tail site.

The problem is the *content* of the block, which is the Leg 0 finding. `CZNetGame` comes from bound `malloc@0x00194C30` (`KNOWN.md` §2). Its `+0xd2` ghost flag reads `0xAF` on ours and `0x00` on the console.

**Under review.** Task 1's launch 1 found the ghost flag cleared before its reader runs. So heap zero-fill is no longer the leading explanation for Frostfire **[inference, pending verification in research/21]**. The uninitialised-byte divergence itself (§1) stands.

**Experiment.** If research/21 leaves the question open, the `PS2X_GUEST_MALLOC_ZERO` 0/1 A/B on Frostfire still shows whether heap content matters.

### 4.3 The consumed display environment — **divergence [verified], Sprint 6**

`disp[1].display` (DBuff +0x40) reaches `REG_GS_DISPLAY1/2` on every flip, and it differs from the console on three fields **[verified, 15/15 vs 3/3]**:

- DY: 33 vs 51;
- MAGH: 0 vs 3;
- DW: 639 vs 2559.

`PMODE` at +0x00 differs as well: `0x8007` vs `0x66`.

`sceGsSetDefDBuff` builds these with `makeDisplay(636, 32, 0, 0, w-1, h-1)` and `makePmode(1, 1, 0, 0, 0, 0x80)` **[verified code]**. The guest's own values carry the 4× horizontal magnification and a different vertical offset. Presentation code may overwrite DISPLAY afterwards, so the effect on screen is **[inference]**.

**Experiment (Sprint 6).**

1. Port the guest's display and PMODE values from the `FUN_001a1e78` path.
2. Check a title image against `title_pcsx2` +0x00..+0x4F.
3. Run `--vram-diff` to catch a change in vertical offset or scale.

### 4.4 `sceGszbufaddr` zbp — **divergence [verified], Sprint 6**

The Z-buffer base page is `0x118` on ours and `0x8c` on PCSX2. The value comes from `sceGszbufaddr`, not from the argument ABI, which is why the §4.1 acceptance excludes it. It may be unread, since §4.1 found no sign that ZBUF is ever sent.

**Experiment (Sprint 6).** Compare the formula in `ps2_stubs::sceGszbufaddr` with guest `FUN_001a1ac0` for the title parameters, and correct it if they differ.

### 4.5 `__ieee754_rem_pio2f` — **precision loss [verified code], Sprint 6**

**Who uses it.** `FUN_001b3548`/`FUN_001b3720`/`FUN_001b3808` look like fdlibm `sinf`/`cosf`/`tanf` by structure **[inference]**. They are recompiled and have **151** static call sites between them. They call `__ieee754_rem_pio2f` for |x| > π/4 and use `n & 3`, `n & 1` and `y[0]` **[verified]**.

**What ours does.** The handler computes `n = nearbyint(x·2/π)` and `y0 = x − n·(π/2)` with a single-float π/2, and sets `y[1] = 0`.

**Why that is wrong.** This is **not** fdlibm behaviour. fdlibm computes a non-zero `y[1]` for |x| > π/4 from the split `pio2_1`/`pio2_1t` constants **[known]**. The single-float π/2 is off by about 4.4e-8, so the error grows as about n·4.4e-8 rad **[inference, arithmetic]**:

- about 3.5e-7 rad at 4π;
- about 2.8e-4 rad at 1e4.

A "≤ 2 ulp" retirement test would fail.

**Action (Sprint 6).** Port fdlibm `__ieee754_rem_pio2f` faithfully. Add a reference test over |x| ≤ 1e4 and the multiples of π/4.

### Optional

- **`strcmp`/`strncmp` byte difference.** Both return the host UCRT's −1/0/1 **[verified]**, and `strcasecmp` preserves only the sign. There is no known victim.
  - All 918 classified direct consumers are sign or zero tests **[verified]**.
  - Four `strcmp` sites are unresolved. Three copy the result and zero-test the copy (`FUN_003352f0`, `FUN_003357c0`, `FUN_00335e20`). One loops back before any use (`FUN_0053bef0`).
  - The fix is one line: return the byte difference.

### Parked

- **`sceSifSendCmd`/`_sceSifSendCmd` argument ABI.** Both read args 5–6 from the stack, but no live caller reaches them.
  - `0x1a6110` is runtime-replaced.
  - `_sceSifSendCmd`'s callers are callbacks with no static caller (§3.3, §3.5).
  - Fixing it is hygiene only.

### Retired or downgraded

- **libnetb reply constants (§3.4): downgraded [verified by review].**
  - The fno `0x23` wrapper `FUN_00246f90` and the `0x35` wrapper `FUN_002469c0` have zero callers, data words or constructions. They are dead code.
  - `InterfaceControl` code 8 is constant by spec while the link is up.
  - Code 8's consumers are bit tests (`FUN_00246d10` `& 2`, `FUN_0062e7e0` `(v & 3) == 3`) and a stored record (`FUN_0030bd40`). It matters only for link-loss handling.
- **`scePad2GetButtonInfo` pressure ids: retired statically [verified by review].**
  - In `FUN_00594cf0`, ids `0x15`/`0x14` are read only after LEFT/RIGHT are pressed, so the value is `0xFF` → 1.0.
  - The result feeds only a `c.ole.s` test against 0.03 that chooses between `0x596d60` and `0x57dc80`. It never scales the move vector.
  - The other 16 arithmetic sites are in the pad-report function `FUN_002da930` and in `FUN_002964f0`/`FUN_002c6350`.
- **`socom2_LumReadPixel`** writes a constant grey pixel into auto-exposure (constant by omission). The effect is visual only.
- **`vsprintf`** clips its output at 255 characters. The one direct site ignores the return value.

---

## 5. Proposed Step 5 one-liners (not applied)

Each needs a moves test, `build.sh test` and a green gate.

1. **`sceGsSetDefDBuff`:** read args 5–7 with `decodeGsTrailingArgs3` and seed both clear packets (§4.1 acceptance; zbp excluded).
2. **Optional:** make `strcmp`/`strncmp` return the byte difference.

Deferred to Sprint 6:

- display/PMODE seeding (§4.3);
- `sceGszbufaddr` zbp (§4.4);
- a faithful `__ieee754_rem_pio2f` port (§4.5).

Parked: `sceSifSendCmd` ABI hygiene.
