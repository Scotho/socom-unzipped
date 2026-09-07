# Parity harness notes

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
