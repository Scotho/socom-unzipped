# Parity harness — design (2026-09-07)

## Why
The autonomous loop has been grading itself on "navigated further". That is blind to what the
user sees: the home screen never matched the original, captions are missing, the logo is off
centre, controls are mispositioned. The user cannot be present to report these warts, so the loop
needs an oracle that stands in for them. Visual parity with the original game, measured per screen
against PCSX2 running the same ISO, becomes the project's grade.

## Goal and grading rule
- Every autonomous session ends by producing the parity report and picking the worst-scoring
  screen on the path launch → mission as the next task, unless a hard blocker (thread death,
  crash, no frame) prevents reaching the screens at all.
- A change that lowers any screen's score is a regression: revert or fix before moving on.
- Shell screens first (they are what a player sees first and the same UI code draws the HUD),
  then the mission.
- Escalation beyond screenshots (memory probes, GS dumps) is used only on the triggers below,
  never speculatively.

## Components

### 1. Screen-keyed input script (shared by both sides)
File: `scripts/parity/launch_to_mission.txt`. One step per line:

```
<dialog>[#<n>]+<seconds>:<BTN>[+<BTN>][:<hold>]
```

Meaning: `<seconds>` after the `<n>`-th appearance (default 1st) of dialog `<dialog>`, press the
buttons. Dialog names are the SwitchMenu / rdr names the game already uses (`dlgMenu`,
`dlgSelectRank`, `dlg_Brief_Alb51`…). A leading `boot+<s>` step keys off process start for the
pre-dialog popups. Both drivers accept the same file:

- **Our runtime**: `PS2X_SOCOM2_INPUT_SCRIPT_FILE=<path>`. The host-input code
  (`socom2_host_input.cpp`) already has a time-based script runner; it gains a dialog-event source
  fed by the SwitchMenu hook (`FUN_0027e720`) and the boot clock. The time-based format keeps
  working.
- **PCSX2**: `tools_py/parity/pcsx2_driver.py` polls the current dialog name through PINE and
  injects presses.

### 2. Current-dialog probe
Both sides need "which dialog is showing now". On our side it is the SwitchMenu trace. On PCSX2
it is a PINE memory read of the shell's current-dialog name. The address is found once from a
guest RAM dump on our side (`PS2X_RDRAM_DUMP` at dlgMenu, search for the pointer to the "dlgMenu"
string held by the shell object at 0x4085d0 or the menu state) and recorded in
`tools_py/parity/addresses.py`. If no stable pointer exists, fall back to the rdr root pointer
that SwitchMenu stores.

### 3. Focus-free window capture
`tools_py/parity/winshot.py`: captures a top-level window by title substring using
`PrintWindow` (ctypes, `PW_RENDERFULLCONTENT`), crops to the client area, saves PNG. Used for both
windows. No focus change, no desktop capture.

### 4. PCSX2 input injection (spike first)
Attempt A: post `WM_KEYDOWN`/`WM_KEYUP` to PCSX2's main Qt window using its keyboard pad bindings
from `inis/PCSX2.ini` `[Pad1]`. Success = the shell reacts (dialog name changes over PINE).
Attempt B (fallback): a one-time assisted capture: the user plays through once in PCSX2 while the
driver labels screenshots by dialog name over PINE. The golden set is then fixed until the ISO or
script changes. Which attempt won is recorded in the plan and HANDOFF.

### 5. PINE client
`tools_py/parity/pine.py`: minimal client for PCSX2's PINE protocol (TCP on Windows, port from
`PINESlot`, default 28011): read8/16/32/64, write8/32, status, game title. No third-party package.

### 6. Comparison and report
`tools_py/parity/compare.py`:
- Inputs: golden dir `logs/parity/golden/<screen>.png`, run dir `logs/parity/runs/<stamp>/<screen>.png`.
- Both resized to 320x224 (nearest for the PS2 frame, box filter for the host frame).
- Metrics per screen: `mad` = mean absolute RGB difference normalised to 0..1; `block` = fraction
  of 16x16 blocks whose mean colour differs by more than a threshold (structure score). Score =
  100·(1 − 0.5·mad − 0.5·block), clamped.
- Outputs: side-by-side PNG (golden | ours | diff heat) per screen, and `docs/parity/REPORT.md`
  with a table: screen, score, delta vs previous report, note. Only the markdown is committed.
- Dependencies: Pillow + numpy (`pip install`), recorded in `tools_py/parity/requirements.txt`.

### 7. Runner
`tools_py/parity/run_parity.py [--golden]`:
- `--golden`: launch PCSX2 (`-batch -nogui -fastboot <iso>`), drive the script, capture each
  screen after its settle delay, write to `logs/parity/golden/`.
- default: launch our exe with `PS2X_SOCOM2_INPUT_SCRIPT_FILE`, `PS2X_HOST_SCREENSHOT` disabled
  (the harness captures on dialog events instead, via the run log's SwitchMenu lines and
  winshot), then compare and write the report.
- Never two game instances at once; refuses to start if `socom2.exe` or `pcsx2-qt.exe` is running.

### 8. Escalation triggers (HANDOFF rule)
- **Option 2, PINE memory probe** (`tools_py/parity/probe.py <screen> <addr-set>`): when a screen
  scores below target and the diff image does not show why. Compare known structures first: the
  17 dlgMenu 2D nodes (XPOS/YPOS at +0x30/+0x34), the shell's screen origin, GS DISPLAY/DISPFB
  registers. Report the first differing field.
- **Option 3, GS dump diff**: when the same primitives exist on both sides but land in different
  places or with different textures — a renderer bug. PCSX2's GS dump (`GSDump*`) for the frame vs
  our `PS2X_GS_TRACE_CMDS`. Not before option 2 has excluded a game-state difference.

## Data flow
```
launch_to_mission.txt ──► our exe (runtime script runner) ──► run log (SwitchMenu t) + winshot ─┐
                     └──► PCSX2 (pcsx2_driver via PINE + keys) ──► golden PNGs by dialog name   ├─► compare.py ─► REPORT.md + diff PNGs
```

## Error handling
- Missing golden for a screen: reported as "no golden", not scored.
- Dialog never appears within its timeout on either side: the run stops, report marks the path
  broken at that screen (a hard blocker for the loop).
- PINE not reachable: driver exits with instructions (enable PINE, port).
- Capture returns a black/empty image: retried twice, then flagged.

## Testing
- `pine.py`: read the ELF CRC / game title from a running PCSX2.
- `winshot.py`: capture Notepad-like known window, verify non-empty and dimensions.
- Script parser: unit test in `tools_py/parity/test_script.py` (time and event forms).
- `compare.py`: identical images score 100; a shifted logo scores lower than an unshifted one.
- End to end: golden set captured, our run compared, report produced, committed.

## Out of scope
Audio parity, frame-timing parity, mission gameplay parity beyond the first mission frame,
automatic fixing of anything the report finds.
