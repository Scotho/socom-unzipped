# Sprint 10, Q4 — Goal 9, part 4: the rest of the launcher

> **ARCHIVED 2026-09-25 -- a Sprint 10 plan; the sprint is closed and this is its record.**
> Moved here from `docs/superpowers/plans/` in Sprint 13 (Task R1, with the rest of Sprints 7-10's specs and
> plans); nothing below it was edited except citations that pointed at a path that has since moved. It is a
> record, not an instruction.

Written 2026-09-21 by the Q4 agent (worktree `C:\projects\wt-q4`, branch `agent/q4` off `sprint-10` at `8d6e5c3`).
The item is `docs/CURRENT_SPRINT.md` row Q4; the design is the Sprint 9 spec's "Goal 9 — the launcher finished, and
the game window that follows it". Four parts, in the order the brief gave them: (a) the guide button toggles between
the launcher and the running game, (b) the game window styled like the launcher, (c) the launcher's menu sounds from
the game's HUDUI bank, decoded from the player's own ISO, (d) the profile viewer — an owner question, one paragraph.
This file is the record: the measurements, what was built and tested, the rulings proposed (numbered from R211, for
the controller to confirm), and the owner's tries.

**Scope:** `ps2xLauncher` (the switch, the sounds, the AUDIO and CONTROLLER pages, the icon), `ps2xShared`
(`launcher_config`, `ps2x/host_window.h`, the embedded icon), `ps2xRuntime` (the window's title, icon and caption
colours; the 989snd mixer split into its own library), `ps2xTest`, `tools_py/parity/keys.py` (one string, pinned by a
new Python test). No game was run: this worktree has no `game/`.

**The bar for this agent:** `./build.sh test --no-runner` green with counts; the screenshot set of every page
touched, looked at; the measurements written down. **The bar that is the controller's, after the merge:** the
runtime changed (the window's title and chrome; the mixer's library split), so a full gate on the rebuilt exe — and
the harness's window key moved with the title, so the FIRST stage of that gate is the proof the key is right.

---

## (a) The window switch — the guide button

### The measurement, per platform

The launcher reads the pad through raylib 5.5's GLFW desktop platform, and the runtime reads it through the same.
What each backend delivers for the guide/home button, read off the sources in the build tree
(`build-clang/_deps/raylib-src`):

- **raylib** maps `GLFW_GAMEPAD_BUTTON_GUIDE` to `GAMEPAD_BUTTON_MIDDLE` (`rcore_desktop_glfw.c:1212`), which is
  raylib button 14 = `launcher::mapping::kHostGuide` (asserted once, `socom2_host_input.cpp:381`). So wherever GLFW
  delivers the guide, the launcher already sees it as a plain button, and the mapping's default table binds NO PS2
  button to it (`mapping.cpp:16-25`): by default the game never reads it.
- **Windows, an XInput pad (every Xbox pad; every DualShock/DualSense through DS4Windows or Steam Input):** GLFW polls
  `XInputGetState` (`win32_joystick.c:703`) and maps ten buttons from `wButtons` (`:690-700`: A B X Y LB RB Back
  Start LThumb RThumb) — the documented `XINPUT_GAMEPAD_*` set has no guide bit, and GLFW's XInput mapping rows
  (`mappings.h:422-425`) carry no `guide:` entry. **Not readable through raylib.** The undocumented ordinal 100 of
  `xinput1_4.dll` / `xinput1_3.dll` (`XInputGetStateEx`, the same signature, the guide as `wButtons & 0x0400`) does
  report it; SDL, Dolphin and every emulator read it that way, and GLFW simply never imports it
  (`win32_init.c:134` imports "XInputGetState" by name only).
- **Windows, a DirectInput pad (a DualShock 4 / DualSense on Sony's own driver, most third-party pads):** GLFW's
  DirectInput path uses the SDL-style mapping table; 190 of its 365 Windows rows carry `guide:b<n>`, including every
  PS4 and PS5 Controller row (`mappings.h:314-317`, `guide:b12`). **Readable through raylib.** GLFW sets no
  cooperative level on the device (no `SetCooperativeLevel` call in `win32_joystick.c`), so whether an unfocused
  launcher still receives a DirectInput pad's PS button is the owner's try below, not a measurement.
- **Linux:** GLFW reads evdev (`linux_joystick.c:193-198` maps every `EV_KEY` code from `BTN_MISC` up to a button
  index, so `BTN_MODE` is one), and 245 of the 396 Linux mapping rows carry `guide:`, every Xbox (xpad) and
  DualShock (hid-sony) row among them. **Readable through raylib.** Reading the file descriptor needs no focus.
- **The runtime does not check focus:** there is no `IsWindowFocused` anywhere in `ps2xRuntime/src`, so the game reads
  the pad whether or not its window is in front — the mirror image of the P3 defect. This bounds what the switch
  may do (R211).

### What was built

- **The gate opens one button wide** (`ui/pad_input.h`, `PadNav::Toggle`, `PadIntent::toggle`): while the game runs,
  `padIntent` answers ONLY the switch's press; the rest of the pad stays the game's (P3), and with no game running the
  press is not a swap (nothing to swap to). Tested.
- **The guide, read both ways** (`main.cpp`, once a frame): raylib's `GAMEPAD_BUTTON_MIDDLE` OR
  `win32glue::xinputGuideDown()` — ordinal 100 over the four XInput users (a disconnected user is re-asked every 120
  frames, XInput's own guidance), loaded once and absent-tolerant (`win32_glue.cpp`). Its edges feed the bind loop
  and the switch alike. POSIX answers false to both and leaves the guide to raylib.
- **The second binding** (`Config::focusToggle`, a host-button NAME as `mapping.h` spells them, `"guide"` by default,
  `"none"` off; `normalizeFocusToggle`, `focusToggleHost`; JSON both ways; launcher-only, no environment variable):
  a seventeenth cell in the CONTROLLER page's BUTTONS section, `SWITCH`, on the section row between the section
  switch and RESTORE, with an `OFF` radio cell beside it. Bound through Goal 8's press-the-button flow
  (`bind_flow.h`, `kSwitchTarget = 0xFF`): a free host button binds; a host button the mapping already drives is a
  Conflict with a two-answer dialog — REPLACE (that PS2 button loses its pad button, because the game must not read
  the switch) or CANCEL, opening on CANCEL; SWAP is refused (there is nothing to swap the switch with). Help on both
  cells. Tested (the flow, the config, the layout, the help).
- **The swap itself** (`win32glue::toggleForeground`): Windows finds the game's window by its process id
  (`EnumWindows`, the first visible unowned titled top-level window) and takes the foreground with the standard
  `AttachThreadInput` + `SetForegroundWindow` sequence — the only way a process that is not in front may take it
  without a change to the game; Linux finds both windows by `_NET_WM_PID` in the root's `_NET_CLIENT_LIST`, reads the
  front one from `_NET_ACTIVE_WINDOW` and asks for the other with the ClientMessage a pager sends (source 2, which
  focus-stealing prevention honours), all through `dlopen("libX11.so.6")` so the link line and the portable folder's
  closure do not change (`posix_glue.cpp`; `${CMAKE_DL_LIBS}` on the launcher for glibc < 2.34). On Wayland there is
  no X display and the status line says so. **Neither swap could be exercised here** (no game to run; no Linux build);
  see "Unverified".

### The tests (launcher_tests.cpp, "Launcher", +4 cases)

- the window switch is the one button the pad gate passes while the game runs, and nothing when it does not
- the window switch is a config field: the guide by default, a host button name, none, and nonsense heals
- the window switch binds through the press-the-button flow: a free button binds, a button the game reads is a
  two-answer conflict
- CONTROLLER: the window switch's cell and its OFF sit on BUTTONS' section row, clear of the section switch and
  RESTORE; the switch's conflict lays out two buttons

The first suite run (log `logs/q4/test_a.log`, 753 cases) found the one thing the tests were for: the switch cell's
first id, `pad.bind.switch`, fell inside the `pad.bind.*` namespace Goal 8's layout test walks as "the sixteen cells"
(`launcher_tests.cpp:1653`, "sixteen cells emitted" — 17). Renamed `pad.switch.bind`.

---

## (b) The game window styled like the launcher

### The measurement: what the runtime owns of its window

- The window is raylib's, opened by `PS2Runtime::initialize` (`ps2_runtime.cpp:769`, `InitWindow(w, h, title)`)
  with the title composed by the runner (`ps2xRuntime/src/main.cpp:282-297`): it was `"PS2-Recomp | <game name> |
  <elf>"`, and since the game database does not know the project's ELF (`games_database.cpp` has no SOCOM row;
  `normalizeGameId("socom2_game.elf")` is `SOCOM2-GAMEELF`), the owner's window read **"PS2-Recomp | socom2_game.elf"**.
  No `SetWindowIcon` anywhere in the runtime; the launcher set none either.
- The runtime owns the TITLE and the ICON on every platform (raylib: `SetWindowTitle`, `SetWindowIcon` → GLFW's
  `WM_SETICON` on Windows, `_NET_WM_ICON` on X11). On **Windows 11 (build 22000+)** it also owns the colours of the
  caption the system draws: `DwmSetWindowAttribute` with `DWMWA_CAPTION_COLOR` (35), `DWMWA_TEXT_COLOR` (36),
  `DWMWA_BORDER_COLOR` (34); Windows 10 answers `E_INVALIDARG` and draws its own. On Linux the window manager draws
  the decorations from the title and the icon and nothing else is reachable.
- Everything inside the frame is the game's: the client area IS the presented frame, and the parity gate captures
  it at 640x448 and compares it pixel for pixel against the references (HANDOFF §6 trap 1; `keys.py`,
  `winshot.py`). The runtime can draw over it (the FPS overlay does), but a HEADER BAR — the owner's "button on the
  game client's header that focuses options" — would either sit on the game's pixels or grow the client area by
  its height, and either moves every capture the gate makes. Not done in this pass: **R214**.
- The harness finds the game window by a title substring — `keys.WINDOW_TITLES["ours"] = "PS2-Recomp"` — used by
  `drive.py`, `frame_burst.py` and `online_login_ours.py` (instance B by its `PS2X_WINDOW_TITLE` tag instead). A
  title with the launcher's name in it therefore moves the harness's key with it, and the key must not appear in the
  launcher's own title (`"SOCOM Unzipped"`), or an open launcher would receive the harness's keystrokes.

### What was built

- `ps2x/host_window.h` (pure, ps2x_shared): `title(tag, gameName, elfName)` — **`"SOCOM II U.S. Navy SEALs -- SOCOM
  Unzipped"`** for the project's ELF, `"<name or elf> -- SOCOM Unzipped"` otherwise, `"<tag> | ..."` in front when
  `PS2X_WINDOW_TITLE` is set (instance B is still found by `SOCOM-B`); `kTitleSuffix = " -- SOCOM Unzipped"`, the
  harness's key; the three chrome colours as the launcher's top bar (`theme::mix(panel, ground, 0.5)`), its text
  and its rule, as COLORREF.
- The runner composes its title through it (`ps2xRuntime/src/main.cpp`); `keys.py`'s key is now `"-- SOCOM
  Unzipped"`, and `tools_py/tests/test_host_window_title.py` reads the header and the launcher's `InitWindow` literal
  and holds the three together (the key is the suffix; the launcher's title does not contain it; PCSX2's does not).
- `runtime/host_window_chrome.h` + `host_window_chrome.cpp` (raylib: the icon) + `host_window_chrome_win32.cpp`
  (dwmapi, loaded by hand — no new link line; the two files because windows.h and raylib.h cannot share one),
  called once after `InitWindow`; one `[window] chrome: icon set, caption colours set|not on this system` line.
- The icon: the crest of the project's own logo, cut to 64x64 (`ps2xLauncher/assets/logo/socom_unzipped_icon.png`,
  7.3 KB; the source art is the s2u site's), embedded as `ps2x/app_icon_embedded.h` for BOTH executables — the
  launcher's window now wears it too (`main.cpp`, `SetWindowIcon`).
- Tests: `host_config_tests.cpp` (the title's forms, the suffix on every one, the launcher's and PCSX2's titles clear
  of it, COLORREF), `launcher_tests.cpp` (the three colours ARE the theme's, and the caption text reads on the
  caption at 4.5:1), the Python pin above.

---

## (c) The launcher's menu sounds, from the player's own disc

### The bank and the cues

HUDUI is the bank the game loads with `snd_BankLoadByLoc` at sector 2010461 of the r0001 disc (research/32 §1; handle
`0x00a00000`): a FileAttributes header (type 3, two chunks), chunk 0 the "SBlk" v3 block (3472 bytes), chunk 1 the raw
VAG data (60928 bytes). Its 24 sounds are NAMED in the block's name table (`SFXBlockNames`, the 989snd decomp's
`types.h:322`), which nothing in the tree had read before; read on 2026-09-21 off the fixture:
`0 DINK 1 BACK 2 THUNK 3 SLIDE 4 NEG 5 COUNT 6 TYPE_1 7 TYPE 8 METAL 9 SKB_ENTER 10 SKB_TYPE 11 SFX_VOL_SLIDER
12 TCM_SLIDE 13 TCM_SELECT 14 NV_GOGGLES_ON 15 NV_GOGGLES_OFF 16 SKB_NAV 17 BOMB_BEEP 18 SPLASHSCROLL_1 19-23
COUNTDOWN..COUNTDOWN5`. The four cues: **Move = SLIDE (3)**, **Select = METAL (8)** — the "HUD click" research/32 §2
saw the game play 515 times in a match, `[0x00a00000, 8, 0x400, -1, 0, 0]` — **Back = BACK (1)**, **Refuse = NEG (4)**
(LAUNCH pressed while blocked). Which of these the game itself plays on a focus move was not measured (no game
here); the names are the evidence, and swapping a cue is one line of `cueSound()`.

### What was built

- **`ps2x_snd989`**, a new static library in `ps2xRuntime/CMakeLists.txt`: the three files ps2_runtime carried
  (`ps2_audio_vag.cpp`, `socom2_bank.cpp`, `snd989_mixer.cpp`) with the same flags; ps2_runtime links it PUBLIC, so
  the runner is the same objects in a different archive, and the launcher's core links it without the runtime.
- **`launcher/menu_sounds.h`** (pure, in ps2x_launcher_core): `readBank` (the FileAttributes header and both chunks
  through `iso9660::Reader`, the block parsed and its name checked — a bank that is not HUDUI is refused by name);
  `isoKey` (sixteen hex of SHA-256 over the PVD sector and the bank's first sector — cheap, content-derived);
  `renderCue` (the runtime's own `snd989::Mixer`, `play(bank, sound, 0x400, -1, 0, 0)` exactly as the game asks for
  a HUD click, rendered at 48 kHz stereo until the mixer is quiet, capped at 3 s, trimmed to 10 ms past the last
  loud sample); `wavBytes`; the cache at `<home>/cache/menu_sounds/<key>/{move,select,back,refuse}.wav`,
  `cacheComplete`, `buildCache`.
- **The launcher** (`main.cpp`): raylib's audio device (not under `--screenshot`); the cues (re)loaded at startup
  after the disc check, after every verify, and when the toggle moves; played at `kMenuSoundVolume = 0.45` on: a
  refused LAUNCH, back (Escape / B), select (Enter / Space / A, or a click that took the focus), a focus that moved
  — one per frame, in that order, so opening a page is one click, not two. **Silent** with no disc, an unverified
  disc, no audio device, the bank absent from the image, or the setting off — and the AUDIO page's line under the
  toggle says which.
- **The setting:** `Config::menuSounds` (true by default, launcher-only), a toggle on the **AUDIO** page ("LAUNCHER —
  Menu sounds from the game (this window's clicks, not the game's mix)") with help. AUDIO, not CONTROLLER: it is a
  sound, it sits under the game's volume so the two are read together, and a player looking to silence the launcher
  looks where the volume is. Nothing is sent to the game.

### The tests (menu_sounds_tests.cpp, "MenuSounds", 4 cases)

- the four cues render from the HUDUI fixtures through the game's own mixer: short, loud, and ending
- wavBytes is a 48 kHz stereo 16-bit RIFF with the sizes right
- readBank finds HUDUI at the r0001 sector of a synthetic image, and refuses anything else there (the test builds a
  sparse image: a PVD at 16, the bank's header and chunks at 2010461; then no bank, a renamed bank, no reader)
- the cache is keyed by the image's own bytes, lives under the home's cache/, and is built whole from the image

The first run measured the cues before the bars were set: `.BACK` peaks at 1383 (vol 83 × tone 100: the quietest),
`.NEG` ends where its sample ends (no fade), `.BACK` is under 40 ms. The bars are the measured values.

---

## (d) The profile viewer — the owner's question, not built

What it would show: one row per directory under `cards/` (the profiles that exist on this machine), each with the
card's size and last-write time, the personas the card holds (the game's own save format, which the simulated cards
of Sprint 8 Goal 11 already parse on the runtime side), which server each persona was created on (NOT recorded
anywhere today — the persona is keyed by the server's advertised endpoint at login, so the viewer could only show it
after one more field is written at login), and a REMOVE that deletes a card directory after a confirm. What it would
cost: a page (the rail is nine entries; a tenth fits), a pure card reader shared with the runtime's simulated-card
code so the launcher does not grow a second save-format parser, the "which server" field written by the runtime at
login (a runtime change, a gate), and the confirm dialog the RESTORE two-step already models — two to three days,
most of it the card reader and its tests on real cards, which this worktree cannot see. Not started: the owner asked
whether it is wanted at all.

---

## Proposed rulings (numbered from R211; the controller confirms)

- **R211 — while the game runs the pad drives the launcher NEVER, in front or behind; the switch is the one button
  the gate passes.** The runtime reads the pad whether or not its window is in front (no `IsWindowFocused` in
  `ps2xRuntime/src`), so a launcher that took the pad back when brought forward would recreate the P3 defect from
  the other side. In front, the launcher is driven by mouse and keyboard (which follow the focus), and the switch
  sends the game forward again. Cost: no pad navigation of the launcher mid-game. The fix that lifts it is a runtime
  focus gate on the PAD path only (the keyboard path is the harness's, trap 1) — a small change that needs a gate, so
  it is the controller's to schedule, not this pass's.
- **R212 — the switch is a binding, in BUTTONS, with OFF beside it; the guide by default.** A host button the mapping
  drives is a conflict resolved only by REPLACE or CANCEL: the game must never read the switch. Launcher-only, per
  machine (config.json's top level, not per profile: which button swaps windows is the pad's, not the persona's).
  RESTORE DEFAULTS leaves it alone for the same reason.
- **R213 — an Xbox pad's guide button is read from XInput's ordinal 100 on Windows.** Undocumented, present in
  xinput1_4 and 1_3 since Windows 7, what SDL reads; absent, the launcher says so in the status line and the player
  binds another button. Cost: four `XInputGetStateEx` calls a frame on top of GLFW's own (a disconnected user is
  re-asked every 120 frames).
- **R214 — no header bar on the game window in this pass.** The client area is the gate's capture; a bar over or
  above it moves every comparison. The pair of the pad switch for the mouse is, for now, the taskbar. A later pass
  can draw a bar the runtime owns above the frame IF the harness's capture is taught the offset in the same change.
- **R215 — the game window's title is `"<game> -- SOCOM Unzipped"` and the harness's key moved with it.**
  `keys.WINDOW_TITLES["ours"]` is the suffix, pinned to the header by `test_host_window_title.py`; the launcher's
  own title stays `"SOCOM Unzipped"` (no dashes) so the key cannot pick it. Cost: the first gate after the merge is
  the proof; a gate that finds no window at its title stage is this ruling failing loudly, not silently.
- **R216 — the launcher's cues play at 0.45 of their rendered level, and the setting lives on AUDIO.** "Quietly" was
  the brief; the game's own HUD level is 0x400 = unity, which is loud next to a desktop. One constant
  (`kMenuSoundVolume`), the owner's ear decides.
- **R217 — the cache is keyed by content, not by path.** SHA-256 over the PVD and the bank's first sector: two
  images cannot share a key by accident, a re-pointed ISO path finds its own cache, and nothing about the player's
  file system is in the key.

---

## What the controller must run after the merge

1. `./build.sh runtime` (with generated code): the title line `[window] chrome: icon set, caption colours ...` in the
   run log; the window titled `SOCOM II U.S. Navy SEALs -- SOCOM Unzipped` with the crest as its icon.
2. The gate: its title stage finds the window by the new key (R215). Expected 3/3 as before — nothing inside the
   frame changed.
3. Linux CI: `posix_glue.cpp` gained the X11 half (dlopen; `<X11/Xlib.h>` for the types, which raylib's X11 platform
   already needs) — a compile the Windows worktree could not make.

## The owner's tries (for HUMAN_TASKS)

1. **The switch, Xbox pad, Windows:** launch the game from the launcher; press the XBOX button — the launcher should
   come in front (the bottom bar reads "switched windows"); press it again — the game comes back. If nothing
   happens: CONTROLLER → BUTTONS → the SWITCH cell shows what it is bound to; press it and press another button (say
   VIEW) to bind that instead — the REPLACE/CANCEL dialog appears because VIEW is SELECT's, and REPLACE takes it.
2. **The same with a DualShock / DualSense on Sony's driver (no DS4Windows, no Steam):** the PS button. Whether it
   reaches an unfocused launcher is the one thing the measurement could not settle.
3. **The game window:** its title, its icon in the taskbar, and on Windows 11 the caption in the launcher's teal
   with off-white text. On Windows 10 the caption is the system's; say which you have.
4. **The sounds:** with the disc verified, move the focus (a click), press Enter on a control (the METAL click),
   Escape (BACK), and LAUNCH while the game is already running (NEG). Then AUDIO → the toggle off → silence, and
   `cache/menu_sounds/<key>/` next to the launcher holds four WAVs you can play in anything. Say whether 0.45 is the
   right level, and whether SLIDE is what the game uses when the menu focus moves (the names were the evidence).

## Unverified, plainly

- The swap on Windows: written from the documented rules, not exercised (no game in this worktree). The
  `AttachThreadInput` sequence is the standard one; if Windows still refuses, the status line says "Windows refused
  to bring the launcher forward" and nothing else happens.
- The swap on Linux and the X11 half's compile: no Linux build here; CI compiles it, the VM (X11) would run it.
- A DirectInput pad's PS button while the launcher is unfocused (above).
- The DWM colours on the owner's Windows 11: written from the documented attribute ids, exercised only on the launcher
  side of nothing — the runtime's window is the game's.
- The cues through speakers: rendered and measured, not heard.

---

## Result (2026-09-21, the Q4 agent)

- Commits on `agent/q4`: `0acf90b` (a), `283130c` (b), `0162d71` (c) + this plan. Not pushed.
- Suite: `./build.sh test --no-runner` (`logs/q4/build2.log`, then `tests3.log` after the one fix): Python 1655 OK
  (96 skipped), ps2x_tests **753/753** (was 743 at `8d6e5c3`: +4 Launcher, +1 Launcher chrome, +1 HostConfig,
  +4 MenuSounds). RED first: the first suite run with the new cases had 2 failures -- the switch cell's id inside
  Goal 8's `pad.bind.*` walk (17 "sixteen cells"), and the cue bars set before the cues were measured (.BACK peak
  1383, .NEG's tail); the second run 1 -- Goal 8's focus walk `BUTTONS -> RESTORE`, now `-> SWITCH -> OFF ->`.
  The rest of the new cases were written with their code in the same pass and passed on their first run.
- Screenshots (`logs/q4/shots/`, 51 PNGs, the walk on the rebuilt launcher; the four looked at):
  `controller_buttons_1100x700.png` -- the section row reads SETUP | BUTTONS | SWITCH XBOX | OFF | RESTORE
  DEFAULTS above the sixteen cells, nothing moved. `controller_buttons_switch_1100x700.png` -- the SWITCH cell
  focused, bound to VIEW with the custom dot, the ring on the drawing's VIEW button, SELECT reading NOT BOUND with
  its dot (as REPLACE leaves it), the band carrying the switch's help. `controller_buttons_switch_conflict_1100x700.png`
  -- the two-answer dialog, "VIEW is already SELECT, and the game must not read the window switch. Replace it
  (SELECT loses its button), or cancel?", the focus on CANCEL. `audio_1100x700.png` / `audio_800x520.png` -- the
  LAUNCHER row under the volume's captions, the toggle on, the line "from your disc: cache/menu_sounds/<key>".
- Not committed: `scripts/q4_syntax_check.py` (an agent-local `-fsyntax-only` helper, deleted).

