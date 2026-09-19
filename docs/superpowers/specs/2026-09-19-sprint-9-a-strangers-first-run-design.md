# Sprint 9 — "A stranger's first run" (design)

Opened 2026-09-19 by the controller under the owner's standing instruction ("proceed autonomously through the
sprint(s) at your discretion"). The owner reviews this file when convenient; nothing in it spends owner money or
identity, and nothing in it connects to a server that is not ours.

## 1. Where Sprint 8 leaves things

The client builds and runs on Windows and Linux, the launcher is redesigned, saves persist on a simulated memory
card, the hosted server at 3.143.65.100 is the default preset and has carried a driven match with kills, the menus
hold 60 fps under host load (R123, R125), and the headset opens in a match. What a stranger would still trip on is
not a feature: it is what happens when something goes wrong on a machine that is not this one, and how much they
have to download and trust. Sprint 8's drafted items 3-8 were never started because the owner's additions (the
launcher, memory cards, the hosted server) rightly went first; they are this sprint, re-ordered by what a stranger
meets first.

## 2. Goals, in order

> **Order superseded 2026-09-20 (controller handoff).** The goals below keep their numbers and their text; the ORDER
> they are worked in is `docs/CURRENT_SPRINT.md`'s: milestone P (what the owner hears and sees, ending in the tag
> `playtest-1`) is Goal 10's fixes, Goal 9's pad-focus defect and small launcher defects, Goal 8's close-out, Goal 7,
> then the playtest candidate; milestone Q is Goal 10's instrument, Goal 3, Goal 9's mouse/keyboard change (after
> Goal 3, because its proposed ruling rests on Goal 3's developer mode), the rest of Goal 9, Goal 4, Goal 11, Goal 6.
> **Goal 5 moved to Sprint 10** (it is that sprint's title, serves no part of a first run, and had not started).
> **Goal 11 is new:** a latched render stall must not grow the working set without bound (`GsPendingCap::admit`,
> `gs_gl_backend.cpp:771,789`; promoted from a KNOWN section 2 row that named a Sprint 8 goal and was never scheduled).
> Goal 6's "per-stage sound regression fixture" is built under Goal 10. Goal 9's open debugger question (does the
> release build carry imgui?) is answered by a size measurement inside Goal 3.

### Goal 1 — a failure explains itself (autonomous)
- An exit-code taxonomy in one header (65 "no usable GL" exists; add: disc not found / not r0001, ELF missing,
  config unreadable, card directory unwritable, audio device absent (non-fatal, reported), crash (the handler's
  code), out of memory). Each code has one sentence the launcher shows instead of "the game closed".
- `socom2` with no argument reads `config.json` beside it (the launcher's own file), so a double-click works.
- The diagnostics zip: the launcher's "Save diagnostics" writes one zip (last log, config with the password field
  removed, the GL caps line, the crash record if any, versions). Today it is a folder copy.
- Bar: a test per code that drives the failing condition and asserts the code and the sentence; the launcher's
  selftest shows each sentence; the zip is opened by a test and contains no credential.

### Goal 2 — a smaller, checkable download (autonomous; signing is the owner's)
- A release configuration (`-O2`/`-Os` measured, LTO where the link time allows, stripped, harness-only DLLs
  dropped from the portable folder), on both platforms' packaging scripts. `SHA256SUMS` written beside each
  archive and verified by a test.
- Bar: the three-stage gate 3/3 on the release exe; the archive's size recorded before/after; stop rule: if LTO
  pushes the runner's link past 30 minutes or changes a gate score, ship without it and record why.

### Goal 3 — knob retirement, pass 2 (autonomous)
- 190 distinct `PS2X_*` names are read today. Classify every one (shipping setting / developer probe / dead),
  delete the dead, move the shipping ones into `config.json` with the env var kept as an override, and put the
  probes behind one `--dev` switch so a stranger's environment cannot change behaviour by accident.
- Bar: a generated table in `docs/KNOBS.md` checked by a test against the source (a knob read in code and absent
  from the table fails the suite); the gate 3/3 with an empty environment.

**The exposure question (owner 2026-09-20: "we are exposing quite a few PS2X options that may be security issues...
maybe split a private dev build that is gitignored... unless you agree otherwise"). Answered here, because this goal
already owns the knobs and a second mechanism would fight it.** Measured surface: **126** distinct `getenv("PS2X_*")`
call sites in the runtime, shared and IOP code, of which **29** name a path or a dump. What the reading says:
- **An environment variable is not a privilege boundary.** Whoever can set one already runs code as the player, so
  a knob is not a way *in*; and hiding a knob does not remove it — the strings stay in the binary and the variable
  still works. A private build whose only difference is that the options are *less visible* buys obscurity, not
  safety. Compiling them **out** is a real reduction; that is a different and more expensive thing than hiding.
- **The one real vector is a config file, not the environment, and it was open.** `config.json` is the file a player
  is most likely to be *sent* by someone else (it is in the diagnostics zip, and "send me your config" is how support
  works), and the runner applies a fixed, code-written list of variables from it — no arbitrary keys, so no
  `PATH`/`LD_PRELOAD` injection, which is the right design and worth keeping. But one *value* was a path: the profile
  is free text and becomes `PS2X_MC_DIR=cards/<profile>`, which the runner resolves under its home
  (`bare_run.cpp`), so `"profile": "../../.."` put the game's memory-card writes anywhere the player can write.
  **Fixed under a test** (`normalizeProfile`: a name, not a path; refused whole, never patched up).
- **Do not gitignore a build configuration.** This sprint's own precedent is better: R140 made the release tree a
  committed CMake option, default off, so CI can build it and `ninja: no work to do` proves the developer build is
  untouched. An untracked build option cannot be built by CI, cannot be reviewed, rots, and — the part that matters
  here — means the binary players run is one nobody can reproduce.
- **What a public build should actually drop is the heavy diagnostics, and that is a size decision with a
  measurement, not a security one:** the dump/trace families (29 knobs) and the imgui debug panel
  (`PS2X_ENABLE_DEBUG_UI`, `option(... ON)` today) are dead weight in a 55.7 MB download. Measure what compiling them
  out saves, the way R151 measured `-O2`, and decide on the number.
- **What must stay in the shipped build is the ability to diagnose it.** Goal 1 exists because a stranger's failure
  has to explain itself; a runner that cannot be instrumented on the machine that failed makes every bug report a
  dead end, and a gate that scores a differently-built binary is not scoring what shipped (R148, R151). So:
  classify, constrain, and compile out the heavy ones — do not build a second secret product.
- **The hardening that is worth doing, in order:** every knob that names a path is constrained to the portable folder
  (the dumps, `PS2X_MC_DIR`, the input script) or refused; `config.json` values stay typed and validated at the edge
  as the profile now is; and the `--dev` switch above gates the probes so an environment a player did not set cannot
  change behaviour. **If the owner still wants a private build after that, it should be a committed option with a
  default, not an untracked file.**

### Goal 4 — voice: the headset's own button (autonomous up to the two-machine check)
- Sprint 8 proved no pad button talks. Read the lgaud function table for what reports a button: the status
  word's bits above bit 1, the device-info block's 0x00-0x61 span, GetMixer's u16 at reply +0x2c. Then a
  launcher-bound push-to-talk key/pad button that drives that report.
- Bar: `PS2X_MIC_GAMEREAD_DUMP` from a driven match correlates with the fake source while the key is held and is
  silent otherwise; then instance B's playback dump carries A's voice. Stop rule: two listing passes and two
  launches without the talk flag moving -> file what was read and stop.

### Goal 5 — it stays up (autonomous; the owner names any second machine)
- From the drafted Sprint 9: a scheduled job that runs N ladder rounds against the hosted server and publishes
  the lobby rate and kill rate; per-map kill routes for the sweep maps. Runs on this host in windows the owner
  is away, under the loop lock, never against a server that is not ours.

### Goal 6 — residuals, as filler
- Audio: the stream-start underfill, the aside-cap parity fix, the scratch leak, the per-stage sound regression
  fixture. Window policy: fullscreen at desktop resolution scored by the gate. The VU0 flag latency, the readback
  PBO ring, the invocation stack pool, the stub-state header into a `.cpp`. The pixel-identity console-replay
  test that has never run (KNOWN hazard): regenerate its dump or delete the test.

### Goal 7 — the server by name: `socom.scotho.com` (owner 2026-09-20)
- The owner creates the A record (HUMAN_TASKS). Then: measure whether the game keys saved personas on the name or on
  the resolved address (one driven login by name against a card holding a by-address persona); switch the launcher's
  default preset and the server's DNS answers to the name; keep the raw address as a fallback only if personas survive.

### Goal 8 — a bug report section in the launcher, and the server's status (owner request, relayed 2026-09-20 by the hosted-server session)
- The owner, to that session: "include a bug report section in the launcher that queries the same api endpoints the
  site does and reports in the same way." Recorded here as relayed; the contract is that session's and lives with the
  site (`../scotho`, `sites/s2u`): `GET https://s2u.scotho.com/api/stats` (live; the hosted server's snapshot, safe to
  poll every 5 s or slower) and `POST https://s2u.scotho.com/api/bugs` (being built; JSON, <= 96 KB: title 4..120,
  description 10..4000, optional contact, source "launcher", version, platform, up to 16 short context pairs, an
  optional log <= 65,536 bytes, an empty honeypot field; 201 with a `BR-YYYYMMDD-xxxxxx` id, 400/413/429/5xx).
- The launcher: an ONLINE-page status line from `/api/stats` ("SOCOM Unzipped: online, N players, M games"), parsed
  defensively, never blocking the UI, silent when unreachable. A REPORT A BUG page with the site's own fields and
  wording (TITLE, WHAT HAPPENED, CONTACT (OPTIONAL), an "attach the last run's log" checkbox that is OFF by default,
  SEND, then the id). Nothing leaves the machine until SEND is pressed; what would be sent is shown first.
- Privacy is Goal 1's machinery, not new code: the context comes from the allowlisted config (the ISO cut to its file
  name, never card contents, never a password), the log is `diagnostics::clipLog` then `scrub` with the home directory
  removed and cut to the contract's 65,536 bytes from the tail. On any failure to send, the report is written to
  `logs/bugreport_<stamp>.json` and the player is told where, so nothing typed is lost.
- Transport: HTTPS with certificate checks ON and no new vendored dependency -- WinHTTP in the Windows glue, a `curl`
  subprocess in the POSIX glue (absent curl = the save-to-file path, stated plainly). The request body is a pure
  function of Config + the form, tested against the contract's limits (lengths, 16 pairs, 96 KB, the honeypot); the
  call runs off the UI thread.
- Bar: the pure builder's tests; a loopback test server (plain HTTP, test-only seam) driving 201/400/429/5xx through
  the page's state machine; one real report sent to the live endpoint from each platform once that session says it is
  up, its id recorded. **Owner check:** the wording and that the default-off log checkbox is what was wanted.

### Goal 9 — the launcher finished, and the game window that follows it (owner 2026-09-20)
The owner's list, after living with the redesigned launcher. One defect in it is not cosmetic and leads: **the pad
drives both windows at once.**

- **Pad focus (defect, first).** "When the game is active, both the game and the launcher receive input commands from
  the controller. When the game is active the launcher should not receive focus." So: while `App::running`, the
  launcher takes no pad input at all (and does not steal the foreground). "Pressing the XBOX or PLAYSTATION button
  should toggle the launcher focus if possible, and again should swap back to the game" — the guide button becomes the
  switch between the two windows. The launcher reads the pad through raylib/GLFW, which reads it whether or not the
  window has focus; the guide button is not a standard GLFW button on every backend, so what it costs is a measurement
  before it is a promise (Windows: XInput's guide bit is not exposed by XInput itself — `raylib`'s mapping, SDL's
  `SDL_GAMEPAD_BUTTON_GUIDE`, or the raw HID report; Linux: `BTN_MODE` through evdev). If the guide button cannot be
  read on a platform, say so and give the toggle a second binding rather than pretending.
- **Live server stats.** Already Goal 8's ONLINE status line; the owner points at the site session's work
  (`../scotho`, the SERVER STATS screen). Same endpoint, `GET https://s2u.scotho.com/api/stats` (the owner wrote
  "s2u.socom.com"; the host is `s2u.scotho.com`). Goal 8 owns the transport — this goal only asks that the launcher
  show what the site shows, not that a second reader be written.
- **The debugger must not be open at launch** (owner, 2026-09-20, answering the question below: *"it can stay a
  debugger build. just don't want players to have the debugger open on launch."*). It was worse than a missing
  checkbox: `PS2X_ENABLE_DEBUG_UI` is an `option(... ON)` (`ps2xRuntime/CMakeLists.txt:18`), so the shipped runner
  carries the panel, and `m_visible = true` (`include/ps2_debug_panel.h:19`) opened the Runtime Debugger window over
  the game on every launch. **Done:** the default is now `false`; F1 still toggles it
  (`ps2_debug_panel.cpp:2176`). What is left for this goal: (a) whether the release configuration should build with
  `PS2X_ENABLE_DEBUG_UI=OFF` — imgui and rlImGui are in the 55.7 MB download for a window players must not see, so
  this is a size ruling as much as a UI one (R151's measurements are the precedent); (b) if a launcher switch is
  still wanted after (a), it is a named runtime knob, not a new stray one (Goal 3 is retiring 190 names).
- **The game window styled like the launcher.** "Stylize the actual game client window if possible like the client.
  Use the same UI." The game's window chrome, its title and its borders follow the launcher's theme (`ui/theme.h`);
  what is reachable depends on how much of the window the runtime owns versus raylib.
- **A button on the game client's header that focuses options**, if the header can carry one — the pair of the pad
  toggle above, for the mouse.
- **Two alignment defects, from the owner's screenshot.**
  1. "In the title, the UNZIPPED part after SOCOM II is lower than the SOCOM II text." The top bar draws
     `SOCOM II` at `y=10.0` size 15 and `UNZIPPED` at `y=12.0` size 13 (`ps2xLauncher/src/main.cpp:443-446`); the
     baselines, not the tops, are what should line up (the rail's big wordmark, `main.cpp:496-497`, is the other
     candidate — the screenshot decides which one the owner means; fix both if both are off).
  2. "The running text is not aligned with the yellow circle, it appears higher." The lamp is a circle of radius 5 at
     `places.lamp` and the word is `textCenteredIn(..., places.status, 14.0f)` (`main.cpp:463-467`, placed by
     `topBarPlaces`) — centre the text on the lamp's centre, and let the top-bar test assert it.
- **Tooltips where the launcher is unclear**, "what is a profile?" first: the profile names the memory-card directory
  under `cards/` and the persona the server sees. The owner also asks whether the launcher should have a **profile
  viewer** (what is saved, which server each persona belongs to, how to remove one) — an open question, not a
  decision; the simulated cards (Sprint 8 Goal 11) are what it would read.
- **Move "Second instance on this machine (for testing)" into an advanced section** (`ui/page_online.cpp:82`). There
  is no ADVANCED page or section in the launcher today, so this goal creates one; what else belongs there
  (`fpsOverlay`, the debugger switch above, `gsScale`'s experimental 3) is the pass's judgment, recorded as a ruling.

- **A flash at the top left when the page changes** (owner 2026-09-20): "changing between menus causes a weird
  graphical bug that's visible for a moment somewhere around the top left of the page." Prime suspect, from reading:
  `rectOf(nodes, id)` returns a default `Rect{}` — the origin — when the id is not in the node list
  (`ui/focus.cpp:211-217`), and on the first frame after a page change the nodes are the NEW page's while several
  callers still hold an id from the OLD one (e.g. `main.cpp:579`, the bottom bar's LAUNCH rect). Anything drawn from
  such a rect lands at (0,0) for exactly one frame, which is where and how long the owner sees it. The page-change
  veil itself (`main.cpp:1203-1211`, 0.12 s over `app.frame.content`) is the other candidate and is easy to rule in
  or out. **Method:** reproduce it in `--screenshot` mode by capturing the first frame after a page change (the
  launcher can already drive itself), fix the rect discipline at the root — an unknown id must not produce a drawable
  rect — and keep the capture as the regression test. Do not "fix" it by clearing the frame.
- **The launcher speaks with the game's own voice** (owner 2026-09-20): sound effects for focus movement and
  selection, "drawn directly from the game sound for menu sounds. Feel free to extract them and render them to a
  usable modern format." The bank is already identified: HUDUI, cut from the r0001 disc at sector 2010461, and the
  readers exist (`runtime/socom2_bank.h`, `runtime/ps2_vag.h`; the test fixtures `tests/fixtures/audio/hudui_block.bin`
  and `hudui_vag.bin` are chunks 0 and 1 of it — research/32 §1). **One constraint the owner should weigh:** the
  project ships no game assets ("the game's disc image is not included"; the portable README and LICENSES say so), and
  baking extracted SOCOM II audio into the launcher binary would put the game's audio in the download. The design that
  keeps that promise: the launcher already knows the player's ISO, so it decodes the cues it wants from **their** disc
  on first run, caches them beside the config (WAV or Ogg), and runs silent — never with a substitute — when no ISO is
  set yet. Which cues (move, select, back, error) and their level are part of the pass; raylib's audio is already in
  the launcher, so nothing new is vendored.

- **The mouse leaves; the keyboard stays, narrowed** (owner 2026-09-20): "remove mouse options from the launcher
  entirely, but permanently persist keyboard support but ONLY for menu navigation and typing on the keyboard in the
  game." The whole mouse surface, located: the CONTROLLER page's "Mouse look" toggle and "MOUSE SENSITIVITY" slider
  (`ui/page_controller.cpp:15`, `:72-78`), their focus nodes (`ui/focus.cpp:151`, and the graph's down/up chain), the
  two config fields (`launcher/launcher_config.h:39-40`), their JSON both ways (`launcher_config.cpp:202-205`,
  `:284-291`), the two environment variables they set (`:439-445` — `PS2X_SOCOM2_MOUSE`, `PS2X_SOCOM2_MOUSE_SENS`),
  and the tests that assert all of it (`ps2xTest/src/launcher_tests.cpp:229`, `:238`, `:264`, `:567-569`). A config
  file that still holds the old keys must load without complaint (they are simply ignored), so the round-trip test
  gains a case rather than losing one.
- **The keyboard's narrowing needs a decision before it is coded, because the harness plays the game with it.** Today
  the keyboard is always on and mapped to the whole pad — WASD/arrows to the sticks, ZXCV to the face buttons, Enter
  to START (`ps2xRuntime/src/lib/socom2_host_input.cpp:234`, `:304-414`) — and the driven runs that produce every
  gate, ladder and control-round result post exactly those keystrokes into the window. "Keyboard for menu navigation
  and typing only" therefore means one of: (a) the gameplay mapping stays but becomes harness-only, behind the
  scripted-input path that already exists, so players get menus and text and the gate keeps its instrument; or (b) it
  is removed for everyone and the harness moves to the pad path first, which is a Sprint-sized change to prove. **(a)
  unless the owner says otherwise** — record it as a ruling with this cost written down, and do not silently break the
  instrument the project measures itself with.
- **Relay to the site session** (`../scotho`, `sites/s2u`): the s2u.scotho.com page advertises keyboard/mouse support;
  the owner wants that claim removed. Not this repository's file — passed on, and recorded here so it is not lost.

**Bar:** the pad-focus defect proven with the game running (the launcher's own `--screenshot` proof cannot show it —
it needs a driven launch and a pad); the two alignment fixes asserted in the top-bar tests, not eyeballed; every new
string through the same theme and focus model as Sprint 8 Goal 9. **Owner checks:** the guide-button toggle on their
own pad, the tooltip wording, and whether the profile viewer is wanted at all.

### Goal 10 — the music, fixed where it breaks for everyone (owner 2026-09-20)
**The report.** A play session: first mission, X through the dialog, walking toward the first two targets — "the music
sounded like it was getting louder and quieter and jumping between different tracks. It was not coherent. Glitched
between different samples it sounds like." Voice and sound effects are fine. It also happens between menus, and once
on first entering an online lobby. The owner's instruction: research why, read what we have already tried, and
**target a fix that resolves this universally instead of these particular segments.**

**What is already fixed, so no one spends a day re-finding it** (the full timeline is in research/32 and the commits):
the title music's packet-order, delivery and refusal faults (`4478bff`, `75fe03d`) — that path now correlates 1.000
against the disc (`6ea9520`); the ring's fill/play interlock, R97 (`b3e3797`); two stream-slot leaks and
`sceSifInitRpc` wiping the sound model mid-mission (`23a860d`); a double-closed `FILE*` on a refused stream
(`8f8981c`); and the most recent one, the `snd_AutoVol` fade that was applied instantly and never reached streams at
all, plus the menu stream's discarded first fill (`54d77a2`, gate 3/3 `s8_audio_mc_gate2`). **No audio source file has
changed since.**

**Why none of that explains this report.** Every measurement the project has made is either the fidelity of ONE cue
decoded in isolation (sample-exact, drift < 2.1 ppm — `KNOWN.md:32`) or a correlation of ONE stream against a
reference (the title path). Nothing has ever measured *what the game asked for* against *what was mixed*. The four
things that could produce "louder and quieter + jumping between samples" all sit in that blind spot, and three are
already written down as unmeasured:
1. **Two live cues summing.** Mission music is 210 short stereo cues fired adaptively (`KNOWN.md:32`); the per-stream
   sum is unclamped and every stream shares master group 16 — named as a hazard, never measured
   (`snd989_mixer.cpp:1255`, `:1294`; the Sprint 8 spec says explicitly that a cutscene ring opening over live music
   streams is covered by no measurement).
2. **`pcmStreamStart` after a Stop with no Open replays old blocks** — filed in the Sprint 8 branch review
   (`KNOWN.md:110(e)`) as a consequence of the very fix in `54d77a2`. That is, precisely, "glitched between different
   samples", and it would fire on every screen change that restarts the menu stream — which is where the owner also
   hears it.
3. **The AutoVol curve.** The ramp added in `54d77a2` is linear and its fourth argument (always 2) is recorded as
   **unverified** (`KNOWN.md:33`). A ramp of the wrong shape, or one re-triggered per tick, is "getting louder and
   quieter" exactly.
4. **Cue selection itself.** Nothing checks that the cue the game asked for is the cue that played, or that a cue is
   not restarted from the wrong offset — the fidelity work proved the opposite thing.

**The code sweep then found it — and it is not in the blind spot's fourth corner, it is two concrete bugs that
explain both halves of the owner's sentence together.** Both are in the stream path, both are small, and each one
alone would have survived every measurement made so far, because every measurement drove one cue through a handle the
test chose.

1. **`parentHandle` means QUEUE; we start immediately and keep the parent's handle.** The protocol note is explicit
   (`research/06-989snd-rpc.md:142`): *"if `parentHandle` != 0 the stream is queued after that stream instead."*
   `Snd989Service::playVagStream` (`ps2xIOP/src/modules/snd989.cpp:1555-1587`) instead finds the parent's slot, and
   when that slot is live (`reused == true`) it leaves the handle unchanged and notifies the host with the **parent's**
   handle. The mixer treats a play on a live handle as a replacement: `Mixer::playStream`
   (`snd989_mixer.cpp:1378-1386`) closes the old stream and pushes the new one. **So the moment the adaptive score
   queues the next segment, the one that is playing is cut dead mid-sample and the next starts.** That is "jumping
   between different tracks... glitched between different samples", literally, and with 210 short cues it happens
   constantly. Second failure of the same code: if the parent slot was already reaped, the queued cue takes a fresh
   slot and plays *concurrently* — two cues summing, which was candidate 1 above.
2. **A new stream inherits the dead one's AutoVol ramp.** `Mixer::stop` clears the handle's ramp
   (`snd989_mixer.cpp:1045`) and `setVolPan` clears it (`:1090-1091`); **`playStream` does not**, and `dropDeadRamps`
   (`:683-694`) deliberately keeps a ramp alive while any stream carries the handle. So the game fades the current cue
   with `snd_AutoVol(h, 0, 0x168, 2)` — the exact call in `KNOWN.md:33` — then queues the next cue on `h`; the new cue
   arrives on the same handle, is never `stop`ped, and inherits a ramp already at 0.4 and still heading for 0. The
   next segment starts quiet and keeps fading; the one after starts full. **"Getting louder and quieter", with no
   single cue misbehaving** — which is exactly why the 0.998-1.000 per-cue fidelity measurement passed and the owner
   still hears it.

Two more the sweep found, which is why this is a universal fix and not a mission-only one:
3. **The stream decoder cannot loop.** It ends on any block whose flag carries bit 0 (`snd989_mixer.cpp:447-451`),
   while the bank decoder on the same format correctly separates end from loop-end (`ps2_audio_vag.cpp:166-169`);
   `Stream` has no loop-start field and the play call's `flags` word is dropped at `ps2_audio.cpp:481`. A looping cue —
   the likely shape of **menu and lobby** music — is truncated at its first loop point and re-fired by the game. That
   is the same symptom in the two places the mission bugs cannot reach.
4. **Nothing caps concurrency and the sum hard-clips.** Voices and streams are unbounded vectors
   (`snd989_mixer.cpp:487, 735, 491, 1385`), `Tone::priority` and `Sound::instanceLimit` are parsed and never used,
   and `snd_SetGroupVoiceRange` — the console's cap of music to 24 voices — is recorded and dropped
   (`snd989.cpp:1003-1013`). Two live copies of one cue at slightly different offsets comb-filter, which swells; three
   full-scale streams clip on an accumulator with no headroom (`:1293-1294`).

**Fixed, 2026-09-20, strictly test-first — each RED watched failing as an assertion, not as a compile error. In the
tree for the controller's review, not committed.**
- **R169 — `parentHandle` is a queue, and the wire says so.** The module keeps reusing the parent's slot and handle
  (right: that is what the game polls) and now sends a **tenth word** on the `snd_PlayVAGStreamByLoc` notify saying
  the play is a queue (`reused`). The mixer holds queued segments as a chain on the playing `Stream` (`next`), decodes
  them ahead like any stream, and promotes at the seam **inside the render loop, on the output frame after the
  parent's last sample** — sample-accurate, not block-aligned: the per-stream loop was changed to walk by index with
  a rebindable pointer so the entry in `streams` can change mid-block. A `stop` takes the whole chain (a stop is a
  stop, not "skip to the next"); a play with **no** parent still replaces, and now says so in the log. RED seen:
  *"queueing does not cut the parent dead (peak 2 against 2413)"* — the defect itself, in a unit test.
- **R170 — a fade belongs to the cue, not to the handle.** `playStream` clears the handle's AutoVol ramp on a
  replace, as `stop()` and `setVolPan()` already did, and the **seam** clears it at promotion — so a queued segment
  cannot inherit the fade that ended its parent, while the parent keeps fading normally while it waits. RED seen:
  *"peak 1206 against 2413"* (half a fade inherited) and *"peak 0 against 2413"* (a completed fade inherited: music
  that simply vanishes).
- **R171 — the stream decoder reads the VAG flags the bank decoder always read.** Bit 2 marks the loop start, bit 0
  ends the run, **bit 1 says the run repeats**; a repeating run returns to the mark (chunk-grid, which is the
  producer's unit) instead of ending the stream. The play call's `flags` word stays unused and is still worth a look.
  RED seen: the looping fixture stopped after one pass and fell silent.

**R172 — PROPOSED, not taken: the concurrency cap and the clip.** This one needs a decision, so it stopped here.
`snd_SetGroupVoiceRange(group, 0x18, 0x2F)` caps music to 24 voices on the console and we record and drop it;
`Tone::priority` and `Sound::instanceLimit` are parsed and unused; the accumulator hard-clips with no headroom.
Three ways: **(A)** enforce the group range with an eviction policy — closest to the console, but the policy is a
guess and a wrong guess cuts a live cue; **(B)** leave the count alone and change only headroom — but the SPU clips
too, so "fixing" the clip may be less faithful, not more; **(C)** cap **streams** at the six slots the game itself
asks for (`snd_InitVAGStreamingEx(6, ...)`) — the number is the game's, not ours, the IOP model already keeps six,
and it bounds exactly the thing that swells (two copies of one music cue comb-filtering). **Recommended: (C) now,
(A) deferred behind a measurement, (B) not until the instrument says the mission mix reaches the ceiling.** Changing
what the mix sounds like should follow a number, not a hunch.

**The cheapest discriminating experiment, before any fix:** one trace line in `playVagStream` printing `parent`,
`reused`, the handle and the sector, and one in `Mixer::playStream` printing the ramp scale in force when it replaces
a live stream. If `reused == true` appears during mission music, 1 and 2 are confirmed together — and they are roughly
ten lines each (honour the queue instead of replacing; clear the handle's ramp in `playStream`).

**Method — the instrument still gets built, because a fix nobody can see return is how this defect keeps coming back.** A per-segment
patch is what the owner has refused, and three appearances (mission, menu change, lobby entry) with one description
say the fault is in the shared path, not in any one caller.
- **Make the defect a number.** `tools_py/parity/audio_corr.py` can correlate against a reference and can detect a
  repeating block (`--repeat`, the buzz). It cannot see either half of this report. Add, reference-free: an **envelope**
  track (short-window RMS) whose oscillation is scored, so "louder and quieter" has a threshold; and a **splice**
  detector (sample-step and spectral-flux spikes at block and chunk boundaries), so "glitched between different
  samples" has a count and a timestamp. Both belong with the existing tool and its tests, and both run on any dump.
- **Log what the game asked for.** A mixer-side event trace (cue start/stop with handle, bank and offset, every
  AutoVol call with its arguments and the ramp it produced, every stream open/start/stop, every ring fill and miss),
  timestamped on the same clock as the dump, so an anomaly the instrument finds can be read against the call that
  caused it. Much of this already exists behind `PS2X_AUDIO_TRACE`/`PS2X_MPEG_TRACE` — this is one trace with one
  clock, not a new subsystem.
- **Then reproduce, driven:** M51 to the first contact (the owner's own path), a menu-to-menu sweep, and a lobby
  entry — each with dump plus trace. The fix is whatever the pair shows, at the root, once, for all three.
- **Bar:** the envelope and splice numbers inside their thresholds on all three captures, the trace showing no cue
  played that was not asked for; the gate's title stage staying 23/23 (`s8_audio_mc_gate2` is the standing figure);
  and the regression fixture the audio residuals list has wanted since Sprint 8 — *a per-stage sound check on every
  gate dump* — finally built, so this cannot silently return. **Owner check:** the same play session, by ear. Until
  they say it is right, it is not.
- **If the instrument says the mix is clean and the ear still says it is not,** the next suspect is the host side (the
  callback's own timing and the mixer mutex the disk I/O shares — `AUDIT-2026-09-17.md:80`), and that is where the
  next pass goes. Say so rather than declaring victory on a number.

## 3. Owner-gated, unchanged
The listens, the pad pick, the mic meter, the launcher verdict, the Linux tarball on a real GPU, the first
two-machine match, the domain and AWS credit decisions (`docs/HUMAN_TASKS.md`). r0004 and the community server
stay on the wishlist until the owner brings the package and PSRewired's answer.

## 4. Budget and stop rules
Launches: one gate per runtime commit; Goal 2 two extra; Goal 4 at most two; Goal 5 only in away windows.
Every moved default or skipped measurement gets a numbered ruling (next: R126). At most two C++-building agents.

## 5. What this sprint does not do
An installer; macOS; ARM; signing; PCSX2 mixed matches (they follow Goal 5 if time remains, as drafted); r0004.
