# Sprint 10 Q3 — The mouse leaves; the keyboard stays, narrowed: plan and record

> **ARCHIVED 2026-09-25 -- a Sprint 10 plan; the sprint is closed and this is its record.**
> Moved here from `docs/superpowers/plans/` in Sprint 13 (Task R1, with the rest of Sprints 7-10's specs and
> plans); nothing below it was edited except citations that pointed at a path that has since moved. It is a
> record, not an instruction.

**Goal (from `docs/CURRENT_SPRINT.md` row Q3; the spec's Goal 9 part 3 in
`docs/archive/sprints-7-12/2026-09-19-sprint-9-a-strangers-first-run-design.md`; owner 2026-09-20).** "Remove mouse
options from the launcher entirely, but permanently persist keyboard support but ONLY for menu navigation and typing
on the keyboard in the game." Two halves: every mouse option out of the launcher (and, decided here, out of the
runtime too), and the keyboard's gameplay half honoured only in developer mode — because the harness plays the game
by posting that half into the window (HANDOFF §6 trap 1), and every harness launch runs in developer mode (R203).

**Branch / tree:** `agent/q3` in the worktree `C:\projects\wt-q3`, off `sprint-10` at `954154a` (Q2's developer mode
proven; Goal 8's mapping data path). Built and tested `--no-runner` there; the controller pays the gate and the online
control round after the merge (§5).

## 1. What went

| where | what | how it is now |
|---|---|---|
| `ps2xLauncher/src/ui/page_controller.cpp` | the "Mouse look" toggle and the "MOUSE SENSITIVITY" slider under DEAD ZONE in SETUP; the no-pad caption that listed WASD/IJKL/QE as a way to play | a KEYBOARD line where the toggle was: "Menus and typing only: arrows, Enter, Backspace, Z/X/C/V. Playing is the controller's."; the no-pad caption says a controller is needed to play |
| `ps2xLauncher/src/ui/focus.cpp` | the `pad.mouselook` and `pad.sensitivity` focus nodes and their place in `adjustsHorizontally` | SETUP's right column is the dead zone alone; down from it is the bar's LAUNCH |
| `ps2xShared/include/launcher/launcher_config.h` | `Config::mouseLook`, `Config::mouseSensitivity` | gone |
| `ps2xShared/src/launcher_config.cpp` | `"mouseLook"` / `"mouseSensitivity"` written by `toJson`, read by `fromJson`; `PS2X_SOCOM2_MOUSE=1` + `PS2X_SOCOM2_MOUSE_SENS=<n>` in `environmentFor` | not written, not sent; on load the two keys fall through the unknown-key skip like any other, so **an old `config.json` still loads** (tested: the keys around them are read, the next save drops them) |
| `ps2xShared/include/ps2x/knobs.h` | the rows `PS2X_SOCOM2_MOUSE` (Shipping, Int) and `PS2X_SOCOM2_MOUSE_SENS` (Shipping, Float) | **deleted, with their code** (§3 says why); 149 names: 18 Shipping, 1 Switch, 122 Dev, 8 Test |
| `ps2xRuntime/src/lib/socom2_host_input.cpp` | the two knob reads, `g_config.mouse` / `mouseSensitivity`, the "Mouse -> right stick + triggers" block (`GetMouseDelta`, `IsMouseButtonDown` -> R1/L1), "mouse on/off" on the startup line | no mouse code in the file |
| `README.md` | "keyboard, mouse look, and Xbox/DirectInput pads" in the Works column | "Xbox/DirectInput pads for play, the keyboard for the menus and typing" (rule 11: a committed sentence made false is corrected where it is written) |
| `docs/KNOBS.md` | the two rows | regenerated (`python -m tools_py.knobs write`) |

Nothing else read the mouse: `tools_py/`, `scripts/`, the drive scripts and the harness never touched it (grep), and
the generic libpad-v1 path (`ps2_pad.cpp`, not SOCOM II's) has no mouse either.

## 2. What stayed, narrowed — the keyboard

The keyboard table is Goal 8's `launcher::mapping::Mapping::keys` (data, not rebindable, the default `kSocom2Keys`;
R195), and the sticks are WASD / IJKL outside the table. `socom2HostInputPoll` used to walk the whole table and the
four stick pairs unconditionally. Now:

- **`KeyboardScope { Menus, Full }`** in `socom2_host_input.h`, and four pure functions beside it:
  `socom2KeyboardScopeFor(bool devMode)` (Full in developer mode, else Menus), `socom2KeyboardDrivesButton(scope,
  ps2Button)`, `socom2KeyboardDrivesSticks(scope)`, and `socom2ApplyKeyboard(mapping, scope, isKeyDown, next)` — the
  keyboard's whole contribution to the pad state, each key read through a predicate (raylib's `IsKeyDown` in the
  game; the suite's own in `ps2x_tests`, which has no window).
- **ONE place decides:** `initialise()` sets `g_config.keyboardScope = socom2KeyboardScopeFor(ps2x::knobs::devMode())`
  once, and the poll calls `socom2ApplyKeyboard(g_config.mapping, g_config.keyboardScope, IsKeyDown, next)` where the
  table walk and `axisFromKeys` used to be. The startup line says which: `[socom2-input] keyboard full, developer
  mode (...)` or `[socom2-input] keyboard menus and typing only (d-pad, Enter=START, Backspace=SELECT,
  ZXCV=Square/Cross/Circle/Triangle; R210)`.
- **Menus** = the d-pad, the four face buttons, START and SELECT: what the game's menus, its pause and its on-screen
  keyboard read (the OSK is driven with the d-pad and CROSS; the lobby's ACCEPT is SQUARE; research/28 and the online
  drive scripts are the record of which buttons the menus take). **Gameplay** = the sticks (move, aim), L1/R1 (crouch,
  fire), L2/R2 (lean), L3/R3 — honoured under Full only. A custom `PS2X_INPUT_MAPPING` key table is gated by the PS2
  button an entry names, not by which key it sits on.
- **The launcher's own keyboard** is untouched: it already was menus and typing (the focus model, the text fields).

## 3. The two knobs: deleted, not kept as Dev

The task left it open: Dev knobs that survive for developer mode, or deleted with their code. **Deleted.** (a) The
owner's words were "remove mouse options entirely", and in-game mouse look is a gameplay input (right stick, R1, L1)
— exactly the class the keyboard is being narrowed away from; keeping it under `--dev` would keep a second gameplay
path that the same ruling removes from the keyboard. (b) No instrument uses it: nothing in `tools_py/parity`,
`scripts/parity` or the gate ever moved the mouse (grep), so unlike the keyboard's gameplay half there is no harness
to protect. (c) The block was untested (raylib deltas, an uncaptured cursor), and a Dev knob is a promise that the
code behind it works in developer mode. `test_knobs_registry` and the Knobs suite stay green: the rows left with the
reads; the Shipping count is 18 (the plan's 17 + `PS2X_INPUT_MAPPING` + the two login knobs − the two mouse knobs),
and the Python test also asserts no `MOUSE` name survives. `knobs_tests.cpp`'s "Shipping, read once" probe name moved
from `PS2X_SOCOM2_MOUSE_SENS` to `PS2X_PAD_DEADZONE`.

## 4. Ruling

- **R210 (Q3; proposed in the sprint file, made real here; the owner can overturn it).** **The keyboard's gameplay
  mapping — the WASD/IJKL sticks and the keys bound to L1/R1/L2/R2/L3/R3 — is honoured only in developer mode
  (`PS2X_DEV=1` / `--dev`), where it is the harness's scripted path; the menu-and-typing keys — d-pad, the four face
  buttons, START, SELECT — are everyone's, always.** This is the spec's option (a). *What it protects:* every gate,
  ladder and control-round result this project has was produced by posting exactly those keys into the window
  (`tools_py/parity/keys.py`, `drive.py`, every `scripts/parity/*.txt` with `hold:W` / `hold:I`, `x11shot.py` on
  Linux), and every harness launch carries `PS2X_DEV=1` (R203: `run.sh`, `hostplatform.dev_env`, `env.sh`), so under
  Full the poll consumes the table byte for byte as before — the suite's "under Full every default key lands as
  before" case compares `socom2ApplyKeyboard` against the pre-Q3 loop, key by key. *What it costs:* **a
  keyboard-only player cannot play** — they can walk every menu, type a name and a password, host or join a game, and
  then stand still; the game window says so on its startup line and the CONTROLLER page says so in words. That stays
  true until the spec's option (b) — the harness moved to the pad path (`PS2X_SOCOM2_INPUT_FILE`, which already
  exists) so the gameplay keys can leave for everyone — which is a sprint of its own and is not scheduled. *Cost if
  wrong:* a developer who wants the old behaviour sets `PS2X_DEV=1`; a player who wants to play on the keyboard
  cannot, and the owner's sentence is what forbids it. A middle road (keep WASD but drop the shoulders, say) was not
  taken: the owner asked for menus and typing, and half a gameplay keyboard is the worst of both.

## 5. Tests and proofs

- `ps2xTest/src/pad_input_tests.cpp`, two new cases in `CrouchShortcut`'s suite beside the keyboard-map case:
  - *the keyboard scope: developer mode is the whole table, a player's game is menus and typing (R210)* — the
    scope function, both `Drives*` predicates for all sixteen ids and the sticks, an id out of range.
  - *the keyboard applied: under Full every default key lands as before; under Menus only the menu keys land (R210)*
    — **the inert-in-developer-mode proof**: for every entry of the default table and each stick key, one at a time,
    `socom2ApplyKeyboard(def, Full, isDown, ·)` is `memcmp`-equal to the pre-Q3 loop written out in the test; under
    Menus the same press lands only on a menu button and never moves a stick; the harness's chord W+E+Enter (forward,
    fire, START) whole under Full and START alone under Menus; nothing down changes nothing; a custom table's entry
    bound to L1 is gameplay whatever key it is on.
- `launcher_tests.cpp`: the round trip writes no `mouse` key and **an old `config.json` with `mouseLook` /
  `mouseSensitivity` loads** with the keys around them read and the next save dropping them; `environmentFor` sends no
  `PS2X_SOCOM2_MOUSE*` whatever the config; the focus graph has no `pad.mouselook` / `pad.sensitivity`, down from the
  dead zone is LAUNCH, only two sliders adjust horizontally; SETUP's node list.
- `knobs_tests.cpp`: 18 Shipping; `tools_py/tests/test_knobs_registry.py`: 18 Shipping and no `MOUSE` row;
  `docs/KNOBS.md` held to the header.
- RED / GREEN and the counts: §6.

## 6. Ledger

- [x] Read: HANDOFF §5, §6 trap 1; CURRENT_SPRINT Q3; the spec's Goal 9 part 3; `mapping.h`; the Goal 8 plan; the
      registry; the Goal 3 plan's R203 and R160.
- [x] The runtime: `KeyboardScope` and the four pure functions; the poll's one call; the mouse block, its knobs and
      the two registry rows gone; `kShippingName` moved.
- [x] The launcher: fields, JSON, environment, page, focus nodes, help/caption text; the tests rewritten.
- [x] `docs/KNOBS.md` regenerated; `README.md`'s Works cell corrected.
- [x] `./build.sh runtime --no-runner` and `./build.sh test --no-runner` under the lock — counts below.
- [x] RED shown for the runtime narrowing: with `socom2KeyboardScopeFor` returning Full for everyone (the pre-Q3
      behaviour, a one-line probe), ps2x_tests **748 / 1** -- the one failure "the keyboard scope: developer mode is
      the whole table, a player's game is menus and typing (R210)" at "a player's game: menus and typing". The
      "applied" case stayed green under that probe because it names its scope explicitly -- it proves the two halves,
      not the decision; the decision's test is the scope case. Restored: **749 / 0**. (The launcher's RED is by
      construction: `Config::mouseLook` no longer exists, so the old assertions could not compile; the new ones --
      no `mouse` key written, the old file loading, no `PS2X_SOCOM2_MOUSE*` sent, no `pad.mouselook` node -- were
      written against the new code and passed with it. Not a separately observed RED.)
- [x] The CONTROLLER page's screenshots (`dist/socom_unzipped_launcher.exe --screenshot ../logs/parity/launcher_ui_q3`,
      49 PNGs, in the worktree's git-ignored `logs/`), looked at: `controller_1100x700.png` and `_800x520.png` -- SETUP
      with the pad list, the DEAD ZONE slider and, where the Mouse look toggle was, a KEYBOARD label with "Menus and
      typing only: arrows, Enter, Backspace, Z/X/C/V." / "Playing needs a controller."; the caption line under it
      all in its old place. The first capture ran the keyboard line off the panel's right edge at both sizes (one
      line in a 340-unit column); it is two lines now and fits at both. `controller_buttons_1100x700.png`: BUTTONS
      unchanged -- sixteen cells, RESTORE, the crouch row.
- [x] Committed on `agent/q3` with explicit pathspecs: `8ff45e7` (the code, the tests, `docs/KNOBS.md`, `README.md`), then this record.

Counts (2026-09-21, the worktree, `--no-runner`): `./build.sh runtime --no-runner` exit 0 (the library and the
launcher); `./build.sh test --no-runner` exit 0 — Python **1658 OK** (100 skipped), ps2x_tests **749 / 0** (747 before
Q3 + the two new cases), vu1_replay's verify runs all OK; `python -m tools_py.knobs check` clean; `test_knobs_registry`
11/11.

## 7. The controller's part, after the merge (Q3's bar: BOTH must pass)

From `C:\projects\socom_pc`, one chain under the lock, the shape of `logs/s9_g3_flip_chain.sh`:

```
./build.sh runtime                                       # the full generated rebuild: socom2_host_input.cpp is a runner source
FORCE_QUIET=1 ./build.sh test                            # Python + ps2x_tests + vu1_replay
python -m tools_py.knobs check                           # 0 problems
python -m tools_py.parity.gate --stamp s10_q3_gate --owner gate
bash scripts/parity/online_control_round.sh "foxhunt" logs/parity/s10_q3_control
```

What must show:

- **The gate:** `GATE PASS (3/3)` in `logs/parity/gate/s10_q3_gate/summary.txt` with `PINS MATCH` — no pin moves:
  the mapping hash is still `c393b87b99732a1f (default)` (the table is untouched; only who reads it changed), the env
  pin never held `PS2X_SOCOM2_MOUSE*` (the launcher sent it only with the toggle on, and the harness never did), and
  the harness pin is unchanged because no file under `tools_py/parity` or `scripts/parity` changed. The three
  `*.game.log`s carry `[socom2-input] keyboard full, developer mode (arrows/WASD/IJKL, ...)` — **that line is the
  proof the instrument survived**; `menus and typing only` on a gate log means `PS2X_DEV` did not reach the game and
  the run is not a measurement. The mission stage's holds (`hold:W`, `hold:I`, R1) still reach the HUD as before.
- **The control round:** `CONTROL-ROUND round_ended=yes` in `logs/s10_q3_control.log`, both instances' logs with the
  same `keyboard full, developer mode` line and `input mapping hash=c393b87b99732a1f (default)`.
- **The player's side, one cheap launch if wanted** (no harness): `dist/socom2.exe` from the launcher with no
  `PS2X_DEV` — the log's `[socom2-input]` line reads `keyboard menus and typing only (...)`, arrows and Enter walk the
  title menu, and W does nothing in a mission. This is the half the gate cannot see, by design.

If the gate fails on the mission stage with the HUD never reached, the first thing to check is that line: the scope
is decided once in `initialise()`, from `ps2x::knobs::devMode()`, which the runner's `--dev` and `PS2X_DEV=1` both set.

## 8. Not done here, on purpose

- No document under `docs/` other than this one and `docs/KNOBS.md`. Sentences that are now stale and belong to the
  controller's sprint-file pass: `docs/DEVELOPING.md:123` (`PS2X_SOCOM2_MOUSE=1 adds mouse look`) and `:249` (the
  CONTROLLER page's "mouse look and its sensitivity"), `:89`'s "151 names" (149 now); `docs/HANDOFF.md:285`'s
  "Recorded, NOT implemented"; `docs/STORY.md:491`'s "scheduled to be deleted" (done); `docs/CURRENT_SPRINT.md` row Q3
  and the R210 numbering line. The s2u site's keyboard/mouse claim is the site session's (HANDOFF §8), still owed.
- The launcher's own mouse (clicking the launcher's controls, dragging its window) is not in scope: the owner's
  sentence is about the game's mouse options, and the launcher's focus model was built for pad, keyboard and mouse
  alike.
