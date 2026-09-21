# Sprint 10, Goal 8 (item 8) — the controller mapping: the data path (Sprint 9 Q3b, R174) and the UI

Written 2026-09-21 by the input agent (worktree `C:\projects\wt-input`, branch `agent/input` off `sprint-10`). The
items are `docs/CURRENT_SPRINT.md` Q3b (the data path) and Sprint 10 item 8 (the page); the design is the Sprint 9
spec's "Goal 12 — the controller mapping UI" and the ruling R174 that split it. This plan is the record of what was
done, what was measured, and the rulings proposed for the controller to number.

**Scope:** `third_party/ps2recomp/ps2xShared` (the mapping, the config), `ps2xRuntime/src/lib/socom2_host_input.*`
(the runtime reads the table as data), `ps2xLauncher/src/ui` (the CONTROLLER page), `ps2xTest` (every pure half).
No harness script changes: the harness posts the keyboard's defaults, which are byte for byte what they were.

**The bar for this agent:** `./build.sh test --no-runner` green; the inert-defaults test; the launcher's screenshot
set of the page, looked at. **The bar that is the controller's, after the merge:** a full gate AND an online control
round on the rebuilt exe (the same bar as Q3, for the same reason: these are the files the instrument runs
through), then the owner rebinding one button on a real pad. The exact commands are at the end of this file.

---

## Half 1 — Q3b, the mapping DATA PATH (R174)

### What was there

Two compile-time tables: `socom2_host_input.cpp:315-324`, a `{GAMEPAD_BUTTON_*, kPad*}` array of sixteen rows walked
once per poll, and `socom2_host_input.h:50-54`, `kSocom2Keys`, eighteen `{raylib key, kPad*}` entries. The sticks
(WASD / IJKL, the pad's two axes) are not tables and are not part of this item: an axis is read into an analogue
field, there is nothing to rebind it TO.

### What is there now

- `ps2xShared/include/launcher/mapping.h`, `ps2xShared/src/mapping.cpp` — pure (no raylib, no environment, no
  file). `Mapping` is one struct: `pad`, sixteen `{host, button}` rows in the OLD TABLE'S ORDER (so the default is the
  old array's bytes, `memcmp`-equal), and `keys`, the keyboard entries in the old order. `defaults()` IS the old two
  tables. Names for every PS2 button (`triangle`), every host button by POSITION (`face_up`, never a family's letter)
  and every key (`enter`, `x`, `key:300`); `toEnv`/`fromEnv` (the whole table, never a patch); `toJson`/`fromJson`
  (config.json's block, a patch over the defaults); `rebind` with `Ask`/`Swap`/`Replace` and a `Conflict` answer;
  `restoreDefaults`; `hash`/`hashHex` (FNV-1a 64, ordered) and the pinned `kDefaultHashHex`.
- `launcher_config.h`: `Config::mappings`, a list of `{profile, Mapping}` — the mapping is SAVED PER PROFILE (the
  "per-profile presets" of the spec's list: a profile is one player's save and persona, and two people sharing a
  machine hold their pads differently). `activeMapping(config)` is the current profile's, or the defaults;
  `setActiveMapping` keeps the list clean (a profile back at the defaults loses its entry).
- config.json: a `"mappings": {"<profile>": {"pad": {...}, "keys": {...}}}` block, written only for profiles that
  changed something (a fresh file writes `"mappings": {}`); an old file with no block loads as before; a block that is
  not JSON is a malformed file like any other field's; a block that is JSON but not a mapping is that profile at the
  defaults with the rest of the file kept; an unknown name inside changes nothing (a file from a newer build must not
  lose the rows this build knows).
- The environment: `PS2X_INPUT_MAPPING=pad:up=dpad_up,...;keys:enter=start,...` from `environmentFor`, ONLY when the
  profile's mapping is not the default. The default environment is byte for byte what it was.
- The runtime: `socom2_host_input.cpp` resolves the table once from `PS2X_INPUT_MAPPING` (unset: the defaults; a
  value it cannot read whole: the defaults, said on the log) and walks `mapping.pad` / `mapping.keys` as data. The
  two literal tables are gone from the runtime. It prints, once, `[socom2] input mapping hash=<16 hex> (default|custom)`.
  `socom2HostInputMapping()` exposes the resolved table (the tests read it).
- `json_reader.h` (internal to ps2x_shared): the config reader that lived inside launcher_config.cpp, moved so the
  mapping block reads nested objects with the same reader rather than a second one. Behaviour unchanged.

### The tests (ps2xTest/src/mapping_tests.cpp, "InputMapping", 7 cases)

1. **inert by construction** — the resolved default equals the two OLD arrays, copied literally into the test (not
   derived from anything mapping.h exports), row for row AND `memcmp` byte for byte.
2. the hash: sixteen hex digits, the pinned literal, and a moved pad row / a moved key / a shorter table / two rows
   swapped each change it.
3. names read back for every PS2 button, every host button and every default key; a family's letter is not a name.
4. the environment string round-trips; unset/empty is the defaults; junk, an unknown name, a table with fewer than
   sixteen rows and a row named twice are refused whole.
5. config.json per profile: absent, not-an-object, junk names, a profile name that is not a name, a partial patch, a
   keys block, the setter's honesty, and the round trip through the launcher's own writer.
6. the environment: the default sends nothing; a custom mapping sends exactly one variable, the whole table; another
   profile without one sends nothing.
7. rebinding: free / taken (Ask, Swap, Replace) / same again / out of range / none, and restoreDefaults.

Plus `pad_input_tests.cpp`'s keyboard-map case now reads the runtime's resolved table and asserts it is the default.

### Steps

- [x] Step 1 (RED): mapping_tests.cpp written against a header that did not exist; the suite does not compile.
- [x] Step 2 (GREEN): mapping.h/.cpp, launcher_config's block and environment, the runtime reading the table.
- [x] Step 3: RED `Passed: 706 Failed: 2` (the hash pin, `computed: c393b87b99732a1f`; the round trip, which the
      grouped keys block explains -- see the commit); GREEN `ps2x_tests Passed: 708 Failed: 0`; the Python suite
      unchanged. The full `./build.sh test --no-runner` runs at the end of Half 2.
- [x] Step 4: commit `3d7dd22`.

---

## Half 2 — Goal 8, the CONTROLLER page

### The shape

The page keeps the drawn pad (262 tall now, 20 less; its legend under it) and splits what is under it into two
sections behind a switch at body + 300 -- the same row in both, so the pad never moves:

- **SETUP** (`pad.section.0`): the pad picker, DEAD ZONE, Mouse look, MOUSE SENSITIVITY, the one caption line (the
  crouch trade while a shortcut is on; else what the drawing is for). What the page was, minus the crouch row.
- **BUTTONS** (`pad.section.1`): RESTORE DEFAULTS at the row's right end; sixteen cells four across and four down
  (`pad.bind.<ps2 name>`: the face buttons, the shoulders and triggers, the d-pad, then select/start and the stick
  clicks), each "the game's button = the pad's own name for what drives it" (Y / LB / LT / VIEW / MENU / LS CLICK on
  an Xbox pad; the shapes, drawn, on a PlayStation one; 1-4 on anything else; NOT BOUND for an unbound row; a gold dot
  on a row that is not the default); and the crouch row (R139) last, labelled "CROUCH = LIGHT △", because the shortcut
  IS a binding -- of the light Triangle no pad button can make -- and belongs beside the others.

**Press-the-button-to-bind** (`ui/bind_flow.h/.cpp`, pure, in the tested core): a cell activated LISTENS for five
seconds with a countdown in the cell and a band across the drawing ("PRESS THE BUTTON FOR TRIANGLE  4"); the next host
button RELEASED binds (released, not pressed, so that B can mean two things: a tap of B binds B, B held half a second
cancels); Escape cancels; the countdown running out cancels. While listening the pad navigates nothing and the bar's
prompts say ANY BIND / HOLD B CANCEL / ESC CANCEL. The button that started the session (A on the cell) is still down
on that frame and is ignored until it comes back up. **Conflict:** when the released button already drives another
PS2 button the flow stops and a dialog replaces the section's controls -- "LS CLICK is already L3. Swap it with
TRIANGLE's button, replace it (L3 loses its button), or cancel?" with SWAP / REPLACE / CANCEL, the focus on SWAP.
**Restore:** RESTORE DEFAULTS (disabled while already at the defaults) opens a two-button confirm whose focus lands
on CANCEL, so a second press of the same button cannot wipe a layout. A dialog's buttons are the ONLY controls on the
page while it is open (`LayoutInputs::padDialogButtons`): nothing behind it can be focused or activated.

**On the drawing:** in BUTTONS every row that is not the default gets a gold pill with the game's shape or word on
the control that now drives it, the binding just made is ringed for two seconds, and R139's CROUCH mark follows the
mapping (it rings whichever host control is bound to PS2 L3 / L2). `padAnchor()` (pure, pad_geometry.cpp) is the one
table of where a host button sits; the test holds every anchor inside the pad.

**The analogue truth (R139), on the same page:** the Triangle cell's help (shown in the title strip where the
focus is) says the game reads how hard Triangle is pressed, a pad button is always firm, and crouch is the CROUCH row
below; each crouch cell's help is its trade (the line the caption used to carry).

**Pad-only:** the rail opens onto the section switch; down is the first cell; A on a cell listens; any button binds;
the conflict's focus is on SWAP; RESTORE's confirm is reached by moving right from CANCEL; every id is reachable from
the rail (the existing walk asserts it for whichever section the inputs name, and the new cases for BUTTONS and the
dialogs).

### The tests (launcher_tests.cpp, "Launcher", +8 cases)

layout of the two sections and the grid; the dialogs replacing the controls; the flow (bind, time out, Escape, B
held, B tapped, the same button again, an id out of range); the conflict's three answers and its sentence; the restore
two-step and its CANCEL focus; the pad's own names per family and the game's words and shapes; the Triangle help and
the crouch cells' help; every host button's anchor on the drawing. The existing focus-model case's CONTROLLER block
and the help-ids case were updated for the sections.

### Steps

- [x] Step 1 (RED): the eight cases and the two updated ones, against a core that has no bind_flow: 20 compile errors
      (`no member named 'padButtons' in 'ui::LayoutInputs'`, `padDialogButtons`, `ui::padAnchor`).
- [x] Step 2 (GREEN): bind_flow, focus.cpp's sections and help, pad_render's anchors/callouts/mark, page_controller,
      main.cpp's listening input phase and the bind request, the screenshot walk's seven new shots. First run
      `Passed: 715 Failed: 1` -- "every host button has a label in every family": a PlayStation pad's face buttons
      had a shape and no word; the label now carries the shape's word too. Then `Passed: 716 Failed: 0`.
- [x] Step 3: the screenshot walk (`dist/socom_unzipped_launcher.exe --screenshot logs/parity/launcher_ui_g8`, 47
      PNGs), looked at. What each of the new ones shows:
      - `controller_1100x700.png` / `_800x520.png`: SETUP -- the pad, the legend, the switch, the list, the three knobs, the
        caption. The first pass drew the old "CONTROLLER" label over the SETUP cell; dropped.
      - `controller_buttons_1100x700.png` / `_800x520.png`: BUTTONS at the defaults -- sixteen cells "X = A", "L1 = LB",
        "SELECT = VIEW"..., RESTORE DEFAULTS dim (nothing to restore), the crouch row "CROUCH = LIGHT △" with OFF.
      - `controller_buttons_custom_1100x700.png`: Triangle swapped onto the stick click, Select on the guide button:
        gold dots on the three rows that moved, the △ pill ringed on the left stick, "L3" on Y, "SELECT" on the
        guide button, the Triangle cell focused and the band reading the R139 help.
      - `controller_buttons_listening_1100x700.png`: the Triangle cell reading "PRESS...  4", the band across the pad
        "PRESS THE BUTTON FOR TRIANGLE  4", the bar's prompts ANY BIND / HOLD B CANCEL / ESC CANCEL.
      - `controller_buttons_conflict_1100x700.png`: the dialog over the section -- "LS CLICK is already L3. Swap it
        with TRIANGLE's button, replace it (L3 loses its button), or cancel?" -- SWAP focused.
      - `controller_buttons_restore_1100x700.png`: "Every button back to the defaults for this profile?" with the
        focus on CANCEL; the drawing shows the △ pill on the guide button that RESTORE would undo.
      - `controller_buttons_playstation_1100x700.png`: the same custom layout on a DualShock: the cells' right side
        draws the shapes, SHARE/OPTIONS/PS for the centre buttons, L1/L2 rather than LB/LT.
      - The four crouch shots and the plain PlayStation shot are as they were, with the CROUCH mark now placed by
        `padAnchor` (the ring on the left stick, the box on L2, the plate for the touchpad).
- [x] Step 4: `./build.sh test --no-runner` exit 0 -- Python `Ran 1571 tests ... OK (skipped=96)`, ps2x_tests
      `Passed: 716 Failed: 0`, the VU1 verify runs all OK; then one more ps2x_tests build+run after the cell-order
      assertion joined the layout case, 716/0 again. Commit `384dd0d`.

### Left undone, plainly

- The bar the spec sets for the whole goal that this agent cannot pay: the gate and the online control round on the
  rebuilt exe (below), and the owner rebinding one button on a real pad and playing with it. Nothing here was tried
  on a physical pad: the flow's pad half (`main.cpp`'s release tracking, the ignored starting press, the B hold) is
  reasoned and screenshot-driven, not played. First thing to try on a pad: A on a cell, press Y -> "TRIANGLE is now Y"
  in the bar; A on a cell, hold B -> "binding cancelled"; A on a cell, tap B -> the conflict dialog.
- "Presets" beyond per-profile: no named layouts (a "copy from profile X", a "southpaw") -- the spec's phrase was read
  as per-profile saved layouts, which is what a player switching profiles gets. A ruling below.
- The site's setup guide ("if remapping ships, the site's setup guide says so") is the hosted-server session's wording.
- Q3 (the mouse leaving, the keyboard narrowed to developer mode) is untouched: SETUP still carries Mouse look and
  MOUSE SENSITIVITY exactly as before, and the keyboard's gameplay table is the runtime's default.
- Linux: the launcher and the runtime changes are plain C++20 in the shared library and the pure core; CI's Linux
  workflow builds both, but no VM run was made.

### Suite sizes now

Python 1571 OK (skipped 96); ps2x_tests 716/0 (was 706 at the start: +7 InputMapping, +8 Launcher, the rest unchanged
in count); the VU1 verify runs OK.

---

## What the controller must run after the merge, and what must come out

The runtime changed (`socom2_host_input.cpp` walks the mapping as data), so the gate and an online control round are
owed, on the rebuilt exe, in the main tree:

1. `./build.sh runtime` (the real one, with generated code) — `dist/socom2.exe` rebuilt.
2. The gate, as Q3's row says: `bash scripts/parity/gate.sh <stamp>` (or whatever the current three-stage gate entry
   is; `docs/HANDOFF.md` §7). Expected: 3/3, AND in the run's log one line
   `[socom2] input mapping hash=<kDefaultHashHex> (default)` — the literal in `launcher/mapping.h`. If the line says
   `(custom)` or another number, something set `PS2X_INPUT_MAPPING` and the run is not a measurement.
3. An online control round (the no-kill control on the hosted server, as the Q3 row and item 8 say). Expected: the
   same as before the change, with the same hash line in both instances' logs.
4. Q1b's refusal (another agent): pin `kDefaultHashHex` in the gate's summary and refuse to score a run whose log
   carries a different hash.

---

## Proposed rulings (the controller numbers them)

- **P-A — the mapping is per profile, and a default mapping is not written and not sent.** config.json carries a
  mapping only for a profile that changed one; `environmentFor` adds `PS2X_INPUT_MAPPING` only for a non-default
  mapping. Why: the default environment and the default file stay byte for byte what they were, which is what
  "inert by construction" has to mean for the harness (trap 1) and for a stranger's first run. Cost: a player who
  wants to SEE the defaults in the file cannot; the CONTROLLER page shows them instead. The owner can overturn it.
- **P-B — the environment string is the whole table or nothing.** A `PS2X_INPUT_MAPPING` with fewer than sixteen pad
  rows, a row named twice, or a name the build does not know is refused whole and the runtime plays the defaults and
  says so. Why: a truncated value that silently left rows at their defaults would look like a deliberate mapping.
- **P-C — the keyboard table is data but not rebindable from the page.** The keyboard is menus and typing (Q3) and
  the harness's scripted path (trap 1); the page rebinds the pad only. config.json may carry a `keys` patch for a
  hand edit, and the hash covers it, so a changed keyboard is loud on the log.
- **P-D — the sticks and Triangle's pressure are not in the table.** Sticks are axes; Triangle's pressure is R139's
  crouch shortcut, which works on the PS2 mask AFTER the table ("l3" there means whichever host control the table
  binds to PS2 L3). The page says both, and the CROUCH mark on the drawing follows the mapping.
- **P-E — "per-profile presets" is read as the mapping saved per profile, nothing more.** A profile is one player's
  save and persona; two people sharing a machine hold their pads differently, so each profile keeps its own layout
  and RESTORE DEFAULTS restores that profile's. No named presets (no "southpaw", no "copy from"): every layout the
  page can express is sixteen rows, and a stranger's first run needs none of them. Cost: a player with two profiles
  who wants the same custom layout on both binds it twice. The owner can overturn it; a "copy from profile" row is
  an afternoon on top of setActiveMapping.
- **P-F — bind on RELEASE, B held cancels, a tap of B binds B.** The spec says "Escape or B to cancel"; B is also a
  bindable button, and a rule that reserved it would leave Circle's own pad button unbindable by pressing. Half a
  second is the hold. Cost: a binding lands on release rather than on press, which nobody will feel; a player who
  holds a button for effect has to let go. The owner can overturn it (a pure constant, `kCancelHoldSeconds`).
- **P-G — the section switch is launcher state, not a setting.** Which of SETUP / BUTTONS was open is not written to
  config.json (like the ADVANCED drawer, P4): the page opens on SETUP every time.
