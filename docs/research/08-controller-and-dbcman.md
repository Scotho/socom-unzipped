# Controller (libpad2) HLE and the DBCMAN config blocker (2026-09-05)

## What was done

SOCOM II reads controllers through Sony's socket-based **libpad2** (`scePad2*`), which normally
RPCs to the `SIO2MAN`/`SIO2D`/`DS2U_S1` IOP drivers (none emulated). All `scePad2*` wrappers were
in `untracked_stubs` (return 0), so the game's per-frame reader `FUN_002da930` saw
`scePad2GetState() != 1` every frame and reported no controller.

Implemented five top-level `scePad2*` functions as recompile-time stubs (bypassing the IOP path),
reporting one connected DualShock2 on port 0 with neutral input:

| Function | Addr | HLE return |
|---|---|---|
| `scePad2Init` | 0x1BD588 | 1 (ok) |
| `scePad2CreateSocket` | 0x1BD630 | 0 (valid socket descriptor) |
| `scePad2GetState` | 0x1BD938 | 1 (connected/ready — the value `FUN_002da930` checks) |
| `scePad2Read` | 0x1BD790 | writes a DS2 report to the a1 buffer, returns 32 (length > 0) |
| `scePad2GetButtonInfo` | 0x1BDA78 | a2=button id: 0x10-0x13 → 0x80 (analog center), 0x00-0x0F → 0 (released) |

Wiring (same pattern as the RSA stub): handler bodies in `game_overrides_socom2.cpp`
(`namespace ps2_stubs`, shared state `g_socom2Pad`), names added to `PS2_STUB_LIST` in
`ps2_call_list.h`, and moved from `untracked_stubs` to the `stubs` array in `recomp/socom2.toml`.
The remaining `scePad2*` helpers (End/DeleteSocket/GetButtonProfile/InitDmaDBuff/LinkDriver/
GetSide/CheckDma/SetButtonOrder) and `sceVibGetProfile`/`sceVibSetActParam` stay as `untracked`
ret0, which the reader accepts (it only requires them `>= 0`). Rebuild needs the full
`./build.sh recomp && ./build.sh runtime` because the recompiler embeds `PS2_STUB_LIST`.

## Effect: the game advanced, then hit a new blocker

With a controller reported connected, the game takes a **different branch** — first-time
controller configuration — and now issues a new IOP RPC, **DBCMAN `rpc=0x8000131a`**, that it did
not send before. Our `DBCMAN` stub (`ps2xIOP/src/modules/dbcman.cpp`) only answers the version RPC
(0x80001363) and returns an untouched receive buffer for everything else.

The game then wedges: the live PC pins at **0x32f174** and frames advance at ~1-3 fps (vs 58 fps
before), rendering nothing (`mscal=0`, `pixels=0`). The stuck call stack is:

```
FUN_00321390 (0x321390)  linked-list walk: for(node = list.head; node != end && FUN_00354670(node+0x14, key)==0; node = node->next)
  -> FUN_00354670 (0x354670)
     -> FUN_0032f0e0 (0x32f0e0)  recursive string-tree search (type-0x04 branch nodes, type-0x03 leaves; FUN_00198f18 = strcmp)
```

This is the game's config/asset lookup grinding over a structure that DBCMAN 0x8000131a was
supposed to populate. Empty reply -> the search never resolves and the config init stalls.

## Next step: DBCMAN 0x8000131a

Reverse the reply format the game expects. DBCMAN (Sony "Database Manager") brokers controller and
config data; 0x8000131a is likely a "read config / connection table" call. To find the expected
layout: locate the sender (a `sceSifCallRpc`-style call with function 0x8000131a writing into the
0x1d62c0 recv buffer), then read how the game parses that buffer to build the list/tree that
`FUN_00321390`/`FUN_0032f0e0` walk. The DBCMAN RPCs seen at this stage are 0x80001301, 0x80001302,
0x80001304, 0x8000131a — implement them together as a small connection/config table describing one
attached DualShock2.

Reproduce: `PS2X_PC_SAMPLER=4 ./run.sh 60` — main thread pins at 0x32f174; the DBCMAN RPCs print
from the IOP.

## Note on the fork

Without the pad HLE the game instead runs a 58 fps loop drawing only black clears (an
attract/"waiting for controller" state that cannot advance without input — see
`07-render-pipeline-diagnosis.md`). The pad HLE is the correct direction (a real console has a
controller); it simply surfaced DBCMAN config as the true next prerequisite. Both the pad HLE and
DBCMAN are required for a navigable menu.

## Resolution (2026-09-05) — it was heap corruption, not a config loop

**Corrections to the section above.**
1. `untracked_stubs` in `recomp/socom2.toml` is *informational only and ignored by the recompiler*
   (`third_party/ps2recomp/ps2xAnalyzer/Readme.md`). Everything listed there runs natively. So
   `scePad2GetButtonProfile` (0x1bd868), `scePad2DeleteSocket` (0x1bd738), `sceVibGetProfile`
   (0x1be530) and `sceVibSetActParam` (0x1be5b0) were executing, and they are the libdbc callers.
2. The RPC names come from the libdbc error strings (0x1d0630..0x1d0810): 0x1304 SetWorkAddr,
   0x1301 CreateSocket, 0x1302 DeleteSocket, 0x1303 GetDepNumber, 0x1315 InitSocket, 0x1316
   ResetSocket, 0x1317 GetDeviceStatus, 0x1318 SRData, 0x1319 SendData, 0x131a ReceiveData,
   0x131b SendData2, 0x131c SendData3, 0x1363 CheckVersion. libpad2 is a thin layer over libdbc:
   `scePad2CreateSocket` → sceDbcCreateSocket, `scePad2LinkDriver` (0x1bdbd0) → GetDepNumber,
   `scePad2GetState`/`sceVibGetProfile` → ReceiveData (cmd words 0x0101800c / 0x01038002),
   `sceVibSetActParam` → SendData2 (0x0103400b).
3. The wedge was **not** a lookup grinding on an empty config table. The main thread was in a
   *silent fault-retry loop*: `PS2Runtime::Load32` catches the memory exception, raises a COP0
   address error, returns 0, and the scheduler re-dispatches the faulting function from `ctx->pc`.

**The chain, as observed with lldb** (`tools/llvm-mingw/bin/lldb.exe`; host frames are named after
guest functions, so the host stack is the guest call chain):

```
break on runtime_error::runtime_error →
  PS2Memory::translateAddress  "TLB miss for address …"     (a garbage pointer ≥ 0xC0000000)
  PS2Runtime::Load32
  sub_00354670  FUN_00354670   texture lookup in one asset-library record (record+0x14 collection)
  sub_00321390  FUN_00321390   walk the global asset-library list at 0x45c3c0
  sub_003197E0  FUN_003197e0   load the "textures" section of run/<dir>/<name><suffix>.zed
  sub_003199C0  FUN_003199c0   asset-library loader (renderphase/textures/…)
```

Peeking guest memory (`memory read -f x '$rcx + …'` at a `sub_*` entry, rcx = rdram, rdx = context)
showed the list at 0x45c3c0 healthy (its static ctor `FUN_00402a00` had run; 1 record at 0x8668b0)
but the record's collection words `{count, data}` at 0x8668c8 = `0x0220102d 0xdfbf0020 0x7bb10010`
— **MIPS instructions** (`move v0,s1; ld ra,0x20(sp); lq s1,0x10(sp)`), i.e. code bytes had been
copied over the heap. A hardware watchpoint on that word
(`watchpoint set expression -s 4 -w write -- $rcx+0x8668c8`) caught the writer:

```
sub_00190AB0  sceDbcReceiveData (FUN_00190ab0)
FUN_001be530  sceVibGetProfile
sub_002DA930  per-frame pad reader
sub_002DBA60 / sub_002D9E00 / FUN_001f4860 / FUN_002ce9e0 / FUN_001e7040 (FTSCore main)
```

`sceVibGetProfile(socket, buf)` passes an **uninitialised stack word** as the max-length, which
`sceDbcReceiveData` stores at reply +0x08 before the RPC. On a real IOP DBCMAN overwrites +0x08 with
the received count. Our stub left the buffer untouched, so the wrapper read the garbage back as the
count and did `memcpy(buf, 0x1d62cc, count)` — copying the loader's data/code (0x1d62cc… runs into
FTSCore text at 0x1e7000) over the pad object and everything after it in the heap, including the
texture registry. Five such calls happened per boot; the third one hit 0x8668c8.

**Fix (commit db51455).** `ps2xIOP/src/modules/dbcman.cpp` now writes a reply for every RPC (the
table in the file header lists request/reply offsets). Essentials: ReceiveData count 0 at +0x08 and
status 0 at +0x20c; SRData count 0 at +0x0c, status at +0x410; SetWorkAddr publishes a 32-word link
table (word[socket]==1 = connected, socket 0 only) at the address in request +0x04 and returns 1;
CreateSocket returns an incrementing socket at +0x24; Delete/Init/Reset/GetDeviceStatus return 1 at
+0x04; GetDepNumber/SetActParam return 0 at +0x04. With that the game loads its asset libraries,
plays the intro video and streams sound banks (`PS2X_SOCOM2_PAD=1 ./run.sh 45`: 2445 frames, ~250k of
287k pixels non-black, no `[guest-fault]`).

Also in that commit: a rate-limited `[guest-fault]` log in the runtime's Load*/Store* fault
handlers (this bug was invisible without it), and `0x3b7cf0` added to `recomp/extra_functions.txt`
— an element constructor for a 0x30-byte object array at 0x4b4ef0, called through the C++ runtime's
array-construct helper from 0x181fb4, that Ghidra never made a function (the lone
`[guest-branch:missing-target]` at every boot).

**Step 2 — keep libpad2 off libdbc entirely.** `scePad2GetButtonProfile` can never succeed
natively because it reads the DMA double buffer that only the *native* `scePad2CreateSocket`
registers in the libpad2 socket table (0x1e0e58 + socket*0x334), and our CreateSocket is HLE.
Without it the per-frame reader's state never leaves 0 and no input is read. So
`scePad2GetButtonProfile` (writes a 5-byte DS2 profile FF FF FF FF 00, returns 5),
`sceVibGetProfile` (0 actuators, returns 0) and `sceVibSetActParam` (returns 1) are now
recompile-time stubs (`PS2_STUB_LIST` + `stubs` array in the TOML), like the first five.

**lldb batch recipes used** (run from `socom_pc/`, `PS2X_SOCOM2_PAD=1` in the environment):

```
# first guest fault with full chain + message
lldb.exe --batch -o "breakpoint set -r runtime_error::runtime_error" -o run -o "bt 40" \
  -o "memory read -s1 -c48 -f c *(char**)($rdx+16)" -o kill -- dist/socom2.exe game/disc/socom2_game.elf
# peek guest memory at a guest function entry (rcx = rdram, rdx = ctx; a0 = *(uint*)($rdx+0x40))
lldb.exe --batch -o "breakpoint set -n sub_00354670_0x354670" -o run \
  -o "memory read -s4 -c8 -f x '$rcx+0x45c3c0'" -o kill -- dist/socom2.exe game/disc/socom2_game.elf
# who writes a guest word
lldb.exe --batch -o "breakpoint set -n sub_00354670_0x354670" -o run \
  -o "watchpoint set expression -s 4 -w write -- $rcx+0x8668c8" -o "breakpoint delete 1" \
  -o continue -o "bt 30" -o kill -- dist/socom2.exe game/disc/socom2_game.elf
```
(`breakpoint command add` scripts read from a `-s file` work too; shell heredocs mangle backslashes
on this machine, so keep lldb command files free of them.)
