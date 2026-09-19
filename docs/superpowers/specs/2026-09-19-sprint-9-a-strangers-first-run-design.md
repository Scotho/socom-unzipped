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

## 3. Owner-gated, unchanged
The listens, the pad pick, the mic meter, the launcher verdict, the Linux tarball on a real GPU, the first
two-machine match, the domain and AWS credit decisions (`docs/HUMAN_TASKS.md`). r0004 and the community server
stay on the wishlist until the owner brings the package and PSRewired's answer.

## 4. Budget and stop rules
Launches: one gate per runtime commit; Goal 2 two extra; Goal 4 at most two; Goal 5 only in away windows.
Every moved default or skipped measurement gets a numbered ruling (next: R126). At most two C++-building agents.

## 5. What this sprint does not do
An installer; macOS; ARM; signing; PCSX2 mixed matches (they follow Goal 5 if time remains, as drafted); r0004.
