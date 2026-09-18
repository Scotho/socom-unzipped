# Sprint 7 — two strangers, two machines, one hosted server: design

Status: written 2026-09-17 by the controller from `docs/AUDIT-2026-09-17.md` (§1 the gap to the goal, §2 the findings,
§6 the sprint drafts) and `docs/CURRENT_SPRINT.md`'s Sprint 7 block, under the owner's standing instruction of
2026-09-17 ("proceed autonomously") and the owner's 2026-09-17 additions (the launcher's server picker; bounded
mechanical work to Opus subagents). **The owner has not reviewed this document.** Branch `sprint-7` off `develop` at
`8f57cbd` (Sprint 6 merged). Executor: the autonomous loop following
`docs/superpowers/plans/2026-09-17-sprint-7-two-strangers-two-machines.md`. **Goal N here is Task N in the plan.**

**Authority.** `docs/KNOWN.md` wins over this document wherever they disagree. Every bar names a failure class it does
not separate. Every moved default and every skipped measurement gets a numbered ruling (R91 onward) in the plan.

## 1. Where Sprint 6 leaves things

The audit's one-sentence verdict: the game plays and measures well; a stranger cannot play, for plumbing reasons, four of
which were fixed the same day (the ISO handoff, hostname resolution, the server's advertised address as a parameter, the
harness's one server knob) and two of which are the owner's (a hosted machine and two addresses). What remains between
the tree and "two strangers download the zip, point it at their ISOs, and play a round on a hosted server":

- **Nothing has run on a machine that is not this one.** Every online result is two instances on one PC. The GL path
  requires GL 3.3 with dual-source blending and fails silently without it; the command queue is unbounded when the
  back-pressure latch trips (a window drag does it); the native VU1 path is keyed to one disc image; the window is
  640x448 with no DPI flag.
- **Two online-only semantics of ours are unmeasured**: equal-priority time slicing (the PS2 kernel never does it) and
  two clients publishing the same RSA key A (the harness always gives instance B key B).
- **Two numbers a stranger would feel are unmeasured or failing**: the lobby rate (Task 2 Step 4 of Sprint 6 was skipped,
  ruling R85) and the 21k texture decodes a second that fail the ladder's back-pressure bar (a causal hypothesis in the
  audit, untested).
- **The owner's items**: a hosted machine and its public address, the community server's address, the two placeholders
  in the launcher's picker, a second machine for the first real match, the three hands-on checks in
  `docs/HUMAN_TASKS.md`.

## 2. Goals, in order

Each goal lands value on its own; the order is by dependency on the owner (autonomous first) and by what a stranger
notices.

### Goal 1 — the stranger's machine, defensively (autonomous, first)

The runtime tells the truth about a machine it cannot run on, and never balloons memory.

- **1a GL capability probe.** On the first `ensureGl`, probe once for GL 3.3 core and dual-source blending (and the
  `GL_ARB_clip_control` the depth path uses). On failure: latch, print one line naming what is missing, fall back to
  `PS2X_GS_BACKEND=cpu`, and set an exit-code the launcher can show. Test: a forced compile/link failure latches and
  never recompiles per frame; the fallback engages. *Bar:* the mission gate on the GL path unchanged (3/3); the CPU
  fallback reaches the title stage (the title gate scores it, slower).
- **1b Bounded command queue.** When the back-pressure latch trips, `m_pending` is capped: whole guest frames are
  dropped, uploads are kept (they carry state), and the cap is reported in the gs-gl stats. Test: with the latch forced,
  recording N frames leaves at most K pending and the uploads intact. *Bar:* a 30 s title-bar drag during the mission
  gate does not raise the working set by more than 200 MB (measured by the CPU sampler's memory column, to be added).
  Does not separate: a drag that also stalls the audio thread (out of scope).
- **1c Window and DPI.** `FLAG_WINDOW_HIGHDPI`; the launcher's Video default becomes 1280x896 (2x) with the gate still
  running its own 640x448. Render targets sized from `usedHeight` and `fbw` rather than 1024x1024 at every scale.
  *Bar:* the title gate at the default 640x448 unchanged; a 1280x896 launch's frame is the 640x448 frame scaled (the
  launcher's `--screenshot` compared against the gate capture at a 2x nearest resample, mean |diff| < 3).
- **1d Native VU1 mismatch warning.** One line at first gameplay when no native program matched in the last second;
  the launcher's disc panel names the supported disc (r0001) already, so the warning names the hash it saw.
- **1e Audio I/O off the callback** (from the audit's runtime review): stream chunks pre-decoded on a worker into a
  ring; `render` touches memory only. Test: a mixer render with the file handle closed still plays the ring's contents.
  *Bar:* the title mix's correlation with the disc stays 0.99 (research/32 §7.1's measurement, re-run once).

### Goal 2 — online correctness before scale (autonomous)

- **2a Equal-priority time slicing removed.** Log SOCOM's thread priorities once (the pc-sampler table); the slice
  expires only for a strictly higher-priority ready thread; a test pins the semantics (two equal-priority threads do not
  interleave; a higher one preempts). *Bar:* a Frostfire control round and one ladder launch on the new exe reach the
  same results as `s6_ladder12` (the control bar holds; the kill lands on 3 of 4 rounds). Does not separate: a
  corruption that needed the slice to show up (that is the point: it should not appear).
- **2b Same-key control round.** One control round with both instances on RSA key A (unset `PS2X_SOCOM2_RSA_KEY_B`).
  If it fails where key B passes, derive the key from the profile name in the launcher (`PS2X_SOCOM2_RSA_KEY` from a
  hash of `profile`). Result to KNOWN §1.
- **2c CD stream cursor.** A separate stream cursor so `sceCdRead` cannot advance it; the test "StRead after Read
  resumes at the stream LBN" (fails today). *Bar:* the title mix's correlation unchanged; the 0.26 s slip at 120 s in
  `s6_audio_title19` either gone or attributed elsewhere.
- **2d Lobby rate, measured.** Ten `online_control_round.sh` launches on one map (Frostfire), pinned harness, counted as
  reached-gameplay / total with the failure class of each miss. *Bar:* 8 of 10. Does not separate: a server-side stall
  from a client-side one (the failure class does).
- **2e Freeze shape 2.** research/29's `waitReadable` blocking 10 s: the sampler fields (`m_vsyncTick`, host time) in
  the pc-sampler line, one loaded and one quiet launch from the same exe, the condition sentence in research/29.

### Goal 3 — the 21k decodes (autonomous)

Settle the audit's hypothesis (page-row marking with no x-extent plus whole-span re-stamping on RT download) with
`PS2X_GS_TRACE_PAGES` on a HUD texture page during an online round: download lines preceding decode lines each frame
confirms it. Then: mark only the downloaded rows, include `dsax/rrw` in the upload span, compare per-page generations
only for pages the write touched, reuse GL texture objects when dimensions match. A decodes-per-present budget on the
console-replay GL test (`ps2_gs_tests.cpp`, `PS2X_CONSOLE_REPLAY_GL`). *Bar:* the ladder's RUNG0 back-pressure bar
passes (waits < 100 per instance) on a ladder launch; texture decodes under 2k/s in `PS2X_GS_STATS`. Does not separate:
a decode storm from a different mechanism (the trace names the pages).

### Goal 4 — the hosted server (owner for the machine and the addresses; autonomous for the rest)

- The owner names a machine and a public address or DNS name, and supplies the community server's address
  (`docs/HUMAN_TASKS.md`).
- Autonomous, once named: `start-servers.ps1 -PublicIp <addr>` verified with `-ShowIp`; the router's forwards per
  `server/README.md`; the picker's two placeholders replaced and the default preset switched to SOCOM Unzipped (ruling
  R89 lifted); `server/` packaged as a zip with a README (`scripts/make_server_zip.sh`, tested like the portable
  folder); one client on this machine logs in against the hosted address through the launcher (the picker, not the
  harness).
- *Bar:* the launcher's SOCOM Unzipped preset reaches the lobby from the portable zip on this machine. Does not
  separate: a NAT problem only a second machine would show.

### Goal 5 — the first two-machine match (owner hands-on; scripts and readout autonomous)

Both directions of hosting, from the portable zip, over the internet: the owner or a friend on a second PC. Autonomous
beforehand: a readout the owner can run (`scripts/parity/two_machine_readout.py`: from the two run logs, the lobby
class, whether each saw the other move via the position peek, the clock skew from the round clocks). *Bar:* a lobby
reached and both players seen moving on both machines; findings (NAT, advertised address, key sharing, clock skew) to
KNOWN §1 or §2. Does not separate: the internet path from the LAN path unless the two machines are on different
networks (the owner says which).

### Goal 6 — the owner's checks reported (owner)

The four `docs/HUMAN_TASKS.md` items. The loop does not wait on them.

### Goal 8 — the launcher a player expects (owner request 2026-09-18; autonomous, hands-on checks to the owner)

Added mid-sprint on the owner's words: "controller and microphone selection and functionality within the launcher (both in
single player and multiplayer, test what you are capable of and leave the rest to human tasks). A FPS overlay toggle in the
launcher. Detail/resolution selector, whatever else that would be feasible and useful." Four tasks (plan Tasks 8-11), each a
launcher panel change plus the runtime knob it drives, every new knob off by default so the gate's 640x448 launch is untouched:

- **8, controller selection**: the Controller panel lists the connected pads by index and name, the test area follows the
  selected one, a dead-zone slider; the runtime takes `PS2X_HOST_GAMEPAD_INDEX` and `PS2X_PAD_DEADZONE` through one tested
  selector used by all three pad readers (today each is pinned to pad 0 and only one has a dead zone). Bar: the selector's
  unit tests and the launcher's environment test; the pad in single player and one online round is the owner's check.
- **9, microphone**: a Microphone panel listing capture devices with a live level meter (miniaudio, which raylib already
  links); the runtime opens the chosen device into a ring (`PS2X_MIC_DEVICE`, `PS2X_MIC_DUMP` for a playback check). The
  game's headset module (`lgaud`, the Logitech USB headset) is a stub that answers "no device", so *voice reaching the other
  player* is not in this sprint: Task 9c is a bounded spike that writes what the game asks the headset module for into KNOWN
  §2, and Sprint 8 decides. Bar: the meter moves for the owner; the ring and level tests; the KNOWN row.
- **10, FPS overlay**: `PS2X_FPS_OVERLAY=1` draws one line (host fps, guest vsync Hz, frame ms) at the top-left of the window;
  a Video-panel checkbox. Bar: the formatter test; one title-stage gate launch with the overlay on still passes (the line
  stays inside the top-left 200x14 px, clear of every detector box) and the window capture's corner differs from the exported
  frame.
- **11, detail and resolution**: Sharpest (4x, the backend's own clamp), Match display, a master volume slider
  (`PS2X_AUDIO_VOLUME`), and the two game-side detail knobs as sliders only if reading them shows they are user-safe. Bar:
  the config and environment tests; no default moves (a ruling if one must).

Stop rule: any of these that needs a runtime change the gate cannot cover (the microphone's headset path) stops at the
KNOWN row and a HUMAN_TASKS item rather than shipping an untested path.

### Goal 7 — close-out

`PS2X_TEST_REPEAT=3 ./build.sh test`, a full gate, STATUS entry, KNOWN audit, ROADMAP §6, CURRENT_SPRINT → Sprint 8,
merge `sprint-7` into `develop` and `main`.

## 3. Budget and stop rules

Launches: Goal 1 two gates (GL, CPU fallback) plus one drag measurement; Goal 2 one control round and one ladder (2a),
one control round (2b), ten control rounds (2d), two launches (2e); Goal 3 one traced online round plus one ladder;
Goal 4 one launcher login; Goal 8 one title-stage gate with the FPS overlay on. About 27 launches over the sprint (R94 added
one, Goal 8 one, the page trace moved to the offline mission stage and re-ran twice); each through `scripts/run_detached.sh`,
one at a time.

Stop rules: Goal 2a's ladder failing the control bar on the new exe reverts the slice change and files the finding
(the semantics were load-bearing, which is itself a KNOWN §1 row). Goal 3's trace not showing the download-then-decode
pattern stops the fix and re-opens the hypothesis (the trace names what it does show). Goal 2d under 6 of 10 opens a
lobby-hardening task before anything else online.

## 4. What this sprint does not do

Window policy beyond the DPI flag, the 2x default and Goal 8's selectors (Sprint 8); audio residuals beyond the I/O move (Sprint 8); the
release build, exit-code taxonomy, `SHA256SUMS`, signing (Sprint 8); knob retirement pass 2 (Sprint 8); the mixed match
with PCSX2 (Sprint 9); stats, clans, the legal text (Sprint 9, owner).
