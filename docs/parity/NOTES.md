# Parity harness notes

> **SNAPSHOT, append-only.** Dated spike notes about the parity harness, oldest first; each section says when it was written. Nothing here is kept current -- the live harness is `tools_py/parity/` and its tests. See `docs/DOC_MAINTENANCE.md` (class S).


## 2026-09-07 spike: key injection into PCSX2 without focus
`PostMessageW(WM_KEYDOWN/WM_KEYUP)` to PCSX2's main window (title "SOCOM II - U.S. Navy SEALs",
no child windows in `-batch -nogui` mode) works: CROSS advanced the first-boot popup from
"Select MEMORY CARD slot" to the unformatted-card notice (mean pixel change 6.2 vs 0.02 idle).
So `tools_py/parity/pcsx2_keys.press(hwnd, "CROSS")` drives the game; no assisted capture needed.

Observations from PCSX2 (2.8.1, software renderer, 640x480 window):
- The first-boot popups are real dialogs with text ("Select MEMORY CARD slot:", slot 1 / slot 2,
  then "The memory card (8MB) ... is unformatted ... CONTINUE"). PCSX2's Mcd001.ps2 is unformatted;
  our mc0 folder mapping may take a different branch here — the golden set records whatever PCSX2
  shows, keyed by dialog name, so a missing screen on one side shows up as "not reached".
- The PCSX2 loading screen shows the SOCOM II logo centred with "LOADING..." bottom-right.
- Window client area is 640x480 (4:3 presentation of the 640x448 frame); ours is 640x448. The
  comparer resizes both to 320x224.

## 2026-09-21 reading a gate result: `logs/parity/gate/<stamp>/summary.txt` (Sprint 10 Q1b)
One line per stage, `PASS|FAIL <stage> (<detail>)`, then what the score was computed against:

    EXE dist/socom2.exe bytes=... sha256=...                          the binary under test (Sprint 9 Goal 2)
    PIN scripts/parity/ref_main_menu_ours.png sha256=... ok           one per pinned input, in stage order
    PIN card sha256=... ok; game/disc/mc0_parity, 12 files            the card the run booted from (contents)
    PIN env sha256=... ok; PS2X_HOST_GAMEPAD=0 PS2X_PC_SAMPLER=1 ...  the PS2X_* the launch got (minus the card path)
    PIN harness sha256=... recorded (git 48f8e12, clean; ...; not compared)
    PIN mapping absent (not compared)                                 Q3b's hash, once the runtime prints it
    PINS MATCH scripts/parity/pins.json (13 compared)                 or ACCEPTED (the standard was rewritten) or DRIFTED

A PIN line's state is `ok`, `DRIFTED (expected <hex>)`, `accepted (was <hex>)` (the run was launched with
`--accept-pins`, which rewrote `scripts/parity/pins.json`), `recorded (...)` (harness: never compared) or `absent`.
`PINS DRIFTED` means the gate REFUSED to score: exit 7, no stage lines when the drift was known before the launch
(nothing was launched), stage lines kept when it was the mapping hash (only known after the run). A refusal is not a
FAIL: restore the input, or accept it deliberately with `--accept-pins`, then run again. `pins.json` beside the
summary is the same record as JSON (with the environment's lines and the card's source), and it is what
`--baseline <stamp>` compares before re-scoring: the run must have been made under the standard, and today's
reference files must still be the standard. `python -m tools_py.parity.gate --pins` is the lock-free dry check.
The exact set of pinned files is `gate.pinned_files()`: each stage's drive script, the references that script
names, and the files its scorer reads (`gate.STAGE_INPUTS`).
