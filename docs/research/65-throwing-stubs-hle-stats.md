# 65. The twenty throwing stubs: none is reached in the gate's three stages (and HLE leg three's list)

Date: 2026-09-26 (run 01:11-01:26Z). Sprint 13 Task C2, R265 (HLE audit leg three owned; the throwing-stub census),
audit finding F1 (`docs/audits/2026-09-25-project-audit/code-runtime.md`). One instrumented r0001 gate on the main
tree's exe, run from the agent worktree under one loop-lock hold; everything else here is static and lock-free. No
byte of the game is in this note.

**The one-line answer: none of the twenty toml-bound stubs whose handler throws was called in the title, transition or
mission stage. Each has a call count of 0, and no stage log has an `Unimplemented PS2 stub` line. That line comes from
the throwing body itself, so it does not share the stats' tail-call blind spot. Nothing was reached, so no body was
written and no KNOWN row or issue was opened.** The static census agrees: 17 of the 20 have no live call site in the
image, and the 3 that have one sit in code that cannot run under our HLE (§3).

## 1. The derivation of the twenty

Read from the tree at `7b25a378` (a throwaway script outside the tree; the three steps below are all it does):

1. Every handler `void NAME(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)` in
   `third_party/ps2recomp/ps2xRuntime/src/lib/Kernel/Stubs/*.cpp` and `Kernel/Syscalls/*.cpp`: **671** bodies.
2. A body **throws** when, comments stripped, it is exactly `TODO_NAMED("...", rdram, ctx, runtime);` (or
   `TODO(rdram, ctx, runtime);`). `TODO_NAMED` (`Kernel/Stubs/Unimplemented.cpp:11-48`) logs two lines and throws
   `std::runtime_error("Unimplemented PS2 stub called: ...")` for the first `kMaxStubWarningsPerName` calls, then
   returns -1. That gives **129** bodies: the audit's 128 plus `TODO` itself, whose body is `TODO_NAMED("unknown", ...)`.
3. Intersect them with the names of `recomp/socom2.toml`'s `[general].stubs` (223 `name@addr` selectors, 223
   distinct names). The recompiler resolves each name through `resolveHandlerByName`: the syscall list first, then the
   stub list (research/20 §2.1). No override in `game_overrides_socom2.cpp` and no other runtime file names or
   rebinds any of the twenty or their addresses (checked by name and by address).

**Twenty**, the audit's list exactly:

| stub | address | toml line | body |
|---|---|---|---|
| `sceDmaRecv` | `0x001911A8` | 77 | `Kernel/Stubs/DMA.cpp:146` |
| `sceDmaRecvN` | `0x001911F0` | 78 | `DMA.cpp:156` |
| `sceDmaRecvI` | `0x00191270` | 79 | `DMA.cpp:151` |
| `sceDmaWatch` | `0x00191328` | 81 | `DMA.cpp:220` |
| `sceDmaPause` | `0x00191360` | 82 | `DMA.cpp:62` |
| `sceDeci2Open` | `0x001A4B80` | 148 | `Deci2.cpp:36` |
| `sceDeci2Close` | `0x001A4BC8` | 149 | `Deci2.cpp:6` |
| `sceDeci2ReqSend` | `0x001A4BF0` | 150 | `Deci2.cpp:46` |
| `sceDeci2Poll` | `0x001A4C20` | 151 | `Deci2.cpp:41` |
| `sceDeci2ExRecv` | `0x001A4C48` | 152 | `Deci2.cpp:16` |
| `sceDeci2ExSend` | `0x001A4C80` | 153 | `Deci2.cpp:26` |
| `sceDeci2ExReqSend` | `0x001A4CB8` | 154 | `Deci2.cpp:21` |
| `sceDeci2ExLock` | `0x001A4CE8` | 155 | `Deci2.cpp:11` |
| `sceDeci2ExUnLock` | `0x001A4D10` | 156 | `Deci2.cpp:31` |
| `sceTtyHandler` | `0x001A4E08` | 157 | `TTY.cpp:41` |
| `sceTtyWrite` | `0x001A4FA0` | 158 | `TTY.cpp:56` |
| `sceTtyRead` | `0x001A50F0` | 159 | `TTY.cpp:51` |
| `sceTtyInit` | `0x001A51C0` | 160 | `TTY.cpp:46` |
| `sceMpegGetPictureRAW8` | `0x001BB9D8` | 249 | `MPEG.cpp:3281` |
| `sceMpegGetPictureRAW8xy` | `0x001BBA20` | 250 | `MPEG.cpp:3286` |

(The audit cites `socom2.toml:67` and `:239`. The file has since grown ten lines above the stub list, so these are now
`:77` and `:249`. The selectors are unchanged.) The other 109 throwing bodies belong to libraries SOCOM does not bind.
No toml selector can reach them.

## 2. The run

- **Stamp** `s13_c2_hle_stats` (git-ignored, under the worktree's `logs/parity/gate/`). **Date** 2026-09-26, lock
  granted 01:11:14Z (after 4,669 s in the queue), gate ended 01:26:04Z.
- **Exe** the main tree's `dist/socom2.exe`, sha256 `f90eeec0ec72d16269d266943ec4ea439967864780306f2264561e9e9e94746e`,
  236,940,288 bytes. The same hash was measured before and after the run, and it is the exe V4's three gates ran.
  **ELF** r0001 `06b83684...`.
- **Environment** the gate's own (`PS2X_PEEK`, `PS2X_PC_SAMPLER=1`, `PS2X_HOST_GAMEPAD=0`) plus `PS2X_HLE_STATS=1`,
  `PS2X_HLE_STATS_PERIOD=10` and `PS2X_HLE_STATS_TOML` naming the tree's `recomp/socom2.toml`, which is byte-identical
  to the main tree's. Each stage printed `223 bound stubs from ..., 214 wrapped`.
- **Verdict** GATE PASS 3/3: title 19/23 (window 19/19), transition 14 black frames peak 0, mission HUD reached with
  6/7 gameplay holds and all four probes PASS; `FRAME mean=21.78 worst1s=28.57 n=3079`.
- **Pins** every file pin, the card and the mapping `ok`. Only `env` drifted, and it drifted by the three HLE-stats
  knobs alone.

**A ruling of this task's own, on the pin.** The instrumented environment cannot match the standard. It adds three
`PS2X_*` names, and `pins.env_pin` hashes every one of them. So the run used `--accept-pins`, which rewrote
`scripts/parity/pins.json` after the 3/3 pass (S13-R5). The wrapper script restored it from git the moment the gate
returned (`logs/c2_lockrun.txt`: "pins.json restored"), and the standard in the tree is unchanged. An instrument run is
not a standard. The next instrumented gate should do the same, or should grow a documented instrument-knob exemption
in `env_pin`. That is a harness choice for another task, not this one.

**The worktree's game data.** An agent worktree has no `game/` directory (`scripts/agent_worktree.sh`: tools only).
The run set `SOCOM_GAME_ELF` and `SOCOM_ISO` to the main tree's image and disc, read-only. It copied the pristine card
`game/disc/mc0_parity` into the worktree's git-ignored `game/disc/`, and its card pin read `ok` (`682ad80b...`).

### 2.1 The table: the last periodic table of each stage (cumulative calls)

Title t=160 s, transition t=160 s, mission t=470 s. None of the stages exits through `atexit` (the drive stops the
exe), so the last periodic table is the stage's total to within its 10 s period.

| stub | title | transition | mission | `Unimplemented` lines |
|---|---|---|---|---|
| `sceDmaRecv`, `sceDmaRecvN`, `sceDmaRecvI`, `sceDmaWatch`, `sceDmaPause` | 0 each | 0 each | 0 each | 0 |
| `sceDeci2Open`, `Close`, `ReqSend`, `Poll`, `ExRecv`, `ExSend`, `ExLock`, `ExUnLock` | 0 each | 0 each | 0 each | 0 |
| `sceDeci2ExReqSend` | unbound | unbound | unbound | 0 |
| `sceTtyHandler`, `sceTtyWrite`, `sceTtyRead`, `sceTtyInit` | 0 each | 0 each | 0 each | 0 |
| `sceMpegGetPictureRAW8`, `sceMpegGetPictureRAW8xy` | 0 each | 0 each | 0 each | 0 |

The stage totals were `called=96/98/101`, `zero-call=127/125/122` and `unbound=9`. The nine unbound stubs are research/20
§3.2's nine names with no generated wrapper (`sceCdInitEeCB`, `sceDmaGetEnv`, `fclose`, `sceDeci2ExReqSend`,
`sceSifRegisterRpc`, `sceSifLoadElf`, `sceMpegAddBs`, `sceMpegGetDecodeMode`, `sceVpu0Reset`).

**The last column is the stronger evidence.** A throwing body writes `Warning: Unimplemented PS2 stub called.
name=...` to stderr on every one of its first calls, before it throws, and `run.sh` sends stderr to the stage log.
`grep -c` over the three stage logs gives 0 each. The same grep over the main tree's whole `logs/` archive gives the
same answer: 386 `run_*.log` files and 166 gate `*.game.log` files hold no such line. The only hits
are the `ps2x_tests` outputs, where the unit test calls `TODO_NAMED` on purpose.

### 2.2 The limits of this evidence

- **The stats' tail-call blind spot (issue #40, closed by Task C4 on `agent/s13-c4`, not merged when this ran).** The
  exe gated is `f90eeec0`, which is from before C4. On it a stub reached only through a recompiled `j` bypasses the
  counting entry, so the stats can undercount. None of the twenty is a tail-call target: research/20 §3.1's 37 live `j`
  sites cover 17 other stubs, and a rescan of the tree's image gives `tail=0` for all twenty. The stderr line in §2.1
  is emitted by the body itself, so it would catch a tail-reached call anyway.
- **The unbound stub.** `sceDeci2ExReqSend` has no function entry at `0x001A4CB8`, so the stats cannot wrap it. It
  also has no generated wrapper, zero `jal`/`j` sites and zero data references (research/20 §3.2), so nothing can
  reach it.
- **Coverage.** The run covers the title menu, the boot-to-briefing transition and one scripted walk on one map, all
  offline. Online play, other maps, the attract movies and the in-game cinematics after the first briefing were not
  run. The historical grep in §2.1 covers far more (online rounds, the ladder, other maps). It is still not
  exhaustive.

## 3. The static reading, stub by stub

These come from `python -m tools_py.hle_constants --elf <r0001 image> --stub <name>`, and for callers from
`--extra FUN@addr`. Names are from `recomp/socom2_names.csv`.

- **`sceDmaRecv`, `sceDmaRecvN`, `sceDmaRecvI`, `sceDmaWatch`:** no live site of any kind (research/20 §2.3's
  "no live static site" list). Not reached.
- **`sceDmaPause`:** 2 live sites, one in `WaitDma` (`0x00190bc8`) and one in `WatchDma` (`0x00190c38`), both
  ignoring `$v0`. But every caller of `WaitDma` (7 sites) and of `WatchDma` (1) is inside a bound `sceDma*` stub's own
  body (`sceDmaSend`, `sceDmaSendN`, `sceDmaSendI`, `sceDmaRecv`, `sceDmaRecvN`, `sceDmaRecvI`, `sceDmaSync`,
  `sceDmaWatch`), and our HLE replaces those bodies. So the two live sites are dead one level up. Not reached.
- **`sceDeci2Close`:** 1 live site in `FUN_0029e080`, whose one caller is `CConsole_dtor` (`0x0029d690`), reached only
  through the `CConsole` vtable (one data word). `sceDeci2ReqSend`: 1 live site in `CConsole_Send` (`0x0029de90`), via
  `FUN_0029d3c0` <- `FUN_0029dfa0` <- `FUN_002ce9e0`. `CConsole` is the game's development-host console over DECI2.
  Its socket comes from `sceDeci2Open`, whose only site is dead (inside `sceTtyInit`'s body), so a retail boot never
  opens one. Not reached in the run.
- **`sceDeci2Open`, `Poll`, `ExRecv`, `ExSend`, `ExLock`, `ExUnLock`, `sceTtyHandler`, `sceTtyWrite`, `sceTtyRead`,
  `sceTtyInit`:** only dead sites (inside other bound stubs' bodies: the libtty/DECI2 layer calls itself) or none.
  Not reached.
- **`sceDeci2ExReqSend`:** no wrapper and no reference of any kind (§2.2). Not reachable.
- **`sceMpegGetPictureRAW8`, `sceMpegGetPictureRAW8xy`:** no site of any kind. The movies go through
  `sceMpegGetPicture` (`0x001BB990`, 2,335 calls in the mission stage). Not reached.

**Step 2 therefore has nothing to implement.** No stub was reached, so none gets a body, a KNOWN row or an issue. If
one is ever hit, the throw names it in the log. A body for the DECI2/TTY family would most likely be an error
return with no host attached, and the two RAW8 calls would go through the MPEG decoder's existing picture path. Writing
them now would be code with no caller to test it against, and S13-R1's order puts visible defects first.

## 4. HLE leg three: the consumers of research/20's flagged rows

"Flagged" here means research/20 §2.3's tiers A and B: the twelve rows tagged *wrong shape* or *constant by
omission*. Tiers C to E are faithful or constant by specification. Consumers are the functions holding each live
direct site, with the classes of the sites. The run column is mission-stage calls (title / transition in brackets).

| tier | stub | live consumers (function: site classes) | calls in the run |
|---|---|---|---|
| A | `sceGsSetDefDBuff` | `FUN_001c67c0` ignored 1; `FUN_003b14a0` ignored 1 (the output struct is the live part: research/20 §4.1, §4.3) | 2 (2 / 2) |
| A | `scePad2GetButtonInfo` | `FUN_001c6390` zero-test 1; `FUN_002964f0` arithmetic 2; `FUN_002c6350` arithmetic 2; `FUN_002da930` stored 4, zero-test 4, arithmetic 12, unresolved 16; `FUN_0030af40` zero-test 1; `FUN_00594cf0` zero-test 3, arithmetic 2 | 456,228 (166,212 / 192,924); 4 distinct values |
| A | `__ieee754_rem_pio2f` | `cosf` (`0x001b3548`) const-compare 1; `sinf` (`0x001b3720`) const-compare 1; `tanf` (`0x001b3808`) arithmetic 1 | 425,793 (8,932 / 24,847) |
| A | `socom2_LumReadPixel` | `FUN_003b1dd0` ignored 2 (the constant grey pixel written through `a1` is the live part) | 282,283 (0 / 0) |
| A | `_sceRpcGetFPacket` | `_request_rdata` (`0x001a6780`) unresolved 1; `_request_bind` (`0x001a69f8`) unresolved 1 | 0 |
| A | `_sceRpcGetFPacket2` | `_request_rdata` unresolved 1 | 0 |
| A | `vsprintf` | `FUN_0029d340` ignored 1 (beside the `CConsole` methods of §3) | 0 |
| B | `strcmp` | 231 functions, 602 sites: zero-test 597, unresolved 4 (`FUN_003352f0`, `FUN_003357c0`, `FUN_00335e20`, `FUN_0053bef0`, each a copy that is zero-tested or a branch), ignored 1 | 7,084,059 (3,825,842 / 4,838,062); 3 distinct values |
| B | `strcasecmp` | 130 functions, 265 sites, all zero-test | 8,811,424 (2,373,119 / 3,340,021) |
| B | `strncmp` | 32 functions, 57 sites: zero-test 56, ignored 1 | 28,571 (40 / 46) |
| B | `sceSifSendCmd` | `sceSifMInitRpc` ignored 1; `sceSifMBindRpcParam` zero-test 1; `sceSifMUnBindRpc` zero-test 1; `sceSifMCallRpc` zero-test 2 | 0 (the address and `sceSifMCallRpc` are runtime-replaced: research/20 §3.5) |
| B | `_sceSifSendCmd` | `isceSifSendCmd` (`0x001a6150`) unresolved 1 | 0 |

What the list says, without re-deciding research/20's findings:

- **Five of the twelve are never called** in the three stages (`_sceRpcGetFPacket`, `_sceRpcGetFPacket2`,
  `vsprintf`, `sceSifSendCmd`, `_sceSifSendCmd`). Their wrong shapes cannot show in the gate's scope.
- **The three string compares are hot**, 16 million calls in the mission stage. Every consumer tests only the sign or
  zero, which is the reason research/20 put them in tier B. `strcmp` returns 3 distinct values (-1/0/1), and any
  ordering consumer would need the byte difference. None exists among the resolved sites. The four unresolved sites
  are zero-tests through a copy.
- **`scePad2GetButtonInfo`** returns 4 distinct values over 456k calls, consistent with research/20 §4's retirement
  (pressure ids return 0 or 0xFF).
- **`__ieee754_rem_pio2f`** is hot (425k calls, more than 64 distinct `n` values). R265 declined it until a defect
  points at it, and nothing here does.
- **`socom2_LumReadPixel` is live in the mission and nowhere else** (282k calls). Its `$v0` is ignored. The constant
  grey pixel it writes is the exposure readback research/20 already names (§2.3 row 4, §3.4). This run adds only that
  the readback is exercised once gameplay starts. No defect has been traced to it, so it stays a research/20 row and
  gets no new issue.
- **`sceGsSetDefDBuff`** is called twice per stage; it has two live sites.

Leg three, as R265 bounded it (the consumer list for the flagged rows, together with the census), is done by this
note. Reading each consumer's disassembly further was research/20 §4's work, and its findings stand.
