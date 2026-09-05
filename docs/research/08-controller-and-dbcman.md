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
