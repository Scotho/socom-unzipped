# Handoff — the rest of fix wave A (2026-09-22, ~04:15, Opus → Fable)

You are picking up the tail of the mini sprint that came out of the owner's playthrough. Eight of eleven chunks
are done and on `main`; what is left is mostly **judgment**, which is why it is coming to you rather than being
executed by a bounded agent. Read `docs/superpowers/plans/2026-09-22-fix-wave-playthrough.md` first — it is the
chunk table and the reasoning. This document is only what remains and what will bite you.

## Where things stand, exactly

| | |
|---|---|
| `sprint-10` | `d9ea8a7`, pushed, clean tree |
| `main` | `15e06e1` (PR #23), gated 3/3 on `fixwave_b` |
| Earlier slice | PR #22 (`a36029b`), gated 3/3 on `fixwave_a` |
| Suite | green (`./build.sh test`: 1752+ Python, C++ suite) |
| `dist/socom2.exe` | built from the card fix; the launcher too |

Done and proven: the launcher default 640×448 (R236); the pad-dies-after-a-field regression; the login fields'
accept-set (the audit's finding 1); the unconditional card-failure line; **the virgin-card save bug fixed at the
root** (R238 → finding 3); hold-a-button-to-remap and the pad drawing (W9); the join driver's REFRESH LIST and
`--channel` (R240, code only); the mission-music instrument (W7, instrument only); **R239 cleared by measurement**.

## Do this one first: the endpoint A/B

This is the live lead and the only thing with a real chance of being what the owner actually hears.

**What is known.** A ten-minute capture (`logs/parity/mission_music_ours_20260922_024457`) whose own mix-open line
reads `device Speakers (JBL Flip 6), period 20 ms x 4, engine 48000 Hz`, app session held at 1.00, produced **31
`DEVICE` events** from `tools_py/parity/audio_dips.py` — dips present in the WASAPI loopback recording and absent
from the mixer's own dump at the aligned time. Same class and same speaker as the `docs/KNOWN.md` §1 row where 42
dropouts a mission minute were cut to 2 by the 20 ms × 4 mix device.

**Why it matters more than it looks.** Every capture in this wave, and most of the audio work before it, is
`PS2X_AUDIO_DUMP` — the mix *as rendered*. A dump is written per callback and **cannot see a late callback**. The
owner listens on Bluetooth. This project has already been fooled by exactly this once.

**The experiment, and it is one run:** repeat that capture on a **wired** endpoint and compare the DEVICE count.

```
bash scripts/loop_lock.sh run <owner> --purpose "endpoint A/B" -- \
  bash scripts/parity/mission_music_long.sh --stage briefing --minutes 10
# then: grep -c DEVICE logs/parity/mission_music_ours_<stamp>/dips.txt
```

**The catch you must handle:** Windows routes our executables to endpoints **per executable path** (KNOWN §4 has
the registry key and the current table). You cannot assume changing the default device moves our audio. Read the
run's own `[audio] 989snd mix stream open (... device <name> ...)` line and *refuse to score the A/B* if the two
runs do not name different devices. If you cannot move the routing without the owner, say so and leave it for them
— a mis-attributed endpoint is how three sprints of clean numbers were taken on the wrong speaker.

If the DEVICE events vanish wired, the Bluetooth path is the cause and the question becomes what regressed since
the 20 ms × 4 fix. If they survive, they are ours. **Either way, pin a per-minute DEVICE count into the audio gate**
so this cannot drift back silently a third time.

## W10 — a decision, not a task. This is the one I most want your judgment on.

R237 says the prefilled login leaves the player path, because the supported way in should be the game's own persona
saved on the card with remember-password ticked. **The footing changed after R237 was written.** The reason to
doubt the card path was the owner's failed save — and that failure was the `..` refusal fixed tonight (`152579a`).

So do **not** just execute the removal. The order matters:

1. Prove it: virgin card → create a persona with remember-password → quit → relaunch → does it log in with nothing
   typed? Use an empty `PS2X_MC_DIR` the way `logs/parity/virgin_card5` was driven.
2. Only if that passes, remove the prefill from the player path (the two login fields and their `config.json` keys),
   reclassing `PS2X_SOCOM2_LOGIN_NAME` / `_PASS` to Dev — **and note** that `online_login_ours --prefilled` depends
   on them, so the drive scripts will need `PS2X_DEV=1` (the same fix already applied to `audio_parity.sh`).
3. If it fails, the prefill stays and R237 needs rewriting, because removing it would leave a player with no way in.

There is a wrinkle worth your eye: a knob cannot be class `Shipping` unless the launcher can send it (the C++ Knobs
suite enforces "the Shipping class is exactly what the launcher can send"). Removing the config fields and leaving
the knobs Shipping will fail the suite; that is the correct order-of-operations trap, not a bug.

## W7 follow-up — the capture needs a route, not a longer hold

The instrument is proven (`untilref(ref_hud_ours.png): 3 presses, matched=True`, both captures taken, scored per
minute, aligned). What is **not** true is the assumption under the chunk: a driven *hold* does not capture music.

- Standing at the insertion point: the only streams are 2–4 s voice cues; the mix sits at −51 dBFS.
- `--stage briefing` (added tonight): the score plays ~1 minute at −34.8 dBFS, then the screen sits at −50 dBFS.

The owner's report is the music degrading **while they proceeded**. So the drive has to move. The grammar already
supports it: `hold+<seconds>:W` (see `tools_py/parity/drive.py`, the `hold` mode; stick directions W/A/S/D, fire
R1). Add a `--walk` mode to `scripts/parity/mission_music_long.sh` that emits movement between holds.

**Judgement required:** walking blind into mission 1 will meet hostiles, and a death ends the capture and the music
with it. Decide whether to (a) walk a short safe leg repeatedly, (b) take the owner's own route, or (c) ask them for
one. Do not let a run that died at minute three be scored as "the music stopped".

## W6 — the garbled glyph atlas

The owner saw a garbled HELP popup before Mallard at the church. Q6's latched-stall path is cleared, so R123's
revalidate-by-hash is the standing suspect. The A/B is `PS2X_GS_NO_TEX_REVALIDATE=1` against the same popup.

**Why it did not run:** the church is past a route no standing drive reaches. It is blocked on the same route W7
needs, which is why the two belong together — one walking run can serve both if it captures popup frames.

## W8 — the join driver needs a real lobby

Code is done and unit-tested (28 new tests) but **unproven by a launch**, because no lobby existed to join. Two
unverified pieces, both named in the code:

- The REFRESH LIST press has **no readable mark** — a refresh leaves the same title, banner and menu — so it is
  deliberately not `press_verified`. It is pressed once and the next frame is only checked for "still the BRIEFING
  ROOM". This is the one press on the path with no positive verification.
- `--channel 2+` is written but **unexercised**: every room-list capture we hold shows exactly one room, so the
  list's row pitch has never been observed. `--channel 1` presses nothing and is the old behaviour exactly.

To prove it, host from one instance and join from the other (`--instance B` shifts the UDP ports by 2; the owner's
own game binds 3658). Or wait for the owner to host — they were asked which channel their lobby was in and have not
answered.

One unexplained thing left on the record, worth your eye: `logs/parity/join_owner_lobby/miss_join_list_2.png` shows
the highlight on **WATCH GAME** with the banner reading "…choose a game to watch", and nothing in the driver presses
DOWN there. `join_list_check` now refuses to re-send once the cursor has left JOIN GAME, but the cause is unknown.

## Traps from tonight that will bite you

1. **Check the build's exit code.** A `build.sh runtime` failed silently in a chained command tonight and the next
   game run used the **stale exe**; the absence of a new log line was briefly read as a behavioural finding. Chain
   `build && run` so a failed build cannot hand you yesterday's binary, and put the `rc` capture last.
2. **The Bash tool mangles backslash escapes in heredocs.** `"...\n"` inside `python - <<'PY'` arrives as a real
   newline and produced an unterminated C string. Write files with the Write/Edit tools. This is already in the
   project memory and it still cost an hour.
3. **A histogram over log lines is not a histogram over time.** That is how R239 got charged. If you claim two
   things coincide, measure them on a clock both are on — which is why the play commands now carry the mixer's
   output-frame clock (`[audio] 989snd cmd 0x11/0x12 frame=N`).
4. **A pre-device dump cannot see a device-path fault**, and most of our audio history is pre-device dumps.
5. **Dev knobs are reachable in every build** with `PS2X_DEV=1`. Do not "fix" diagnosability by reclassing.

## What not to do

- Do not reopen R239 (bank `0xa00000`) — it is settled with numbers in `docs/KNOWN.md`.
- Do not hand an implementation agent the ability to open or merge a slice; the controller does that
  (`docs/GIT_STRATEGY.md` §2).
- Do not run anything lock-bound while the owner is at the machine (`scripts/check_quiet_gate.sh`, and the host
  load memory).

## Progress (2026-09-22 midday, Fable) -- the lock-free half is done; the launches are queued

The owner was at the machine for the whole session (input idle 2 s, Teams and Jira open), so by the host-load rule
nothing lock-bound ran. Everything below is code, tests and documents; the runs are exact commands in
`docs/HUMAN_TASKS.md` ("Start here, midday") waiting for a window.

**The A/B's number was wrong before the A/B ran.** Reading the 31 DEVICE rows: the last one was 365 s long (a cue
ending at 581 s, the level never climbing back within 10 dB, its 50 ms dump twin already taken by the endpoint dip
before it) and the first was a 5 s hole whose local offset (2.05 s against a global 2.72 s) put it 2 s from its own
dump twin, which was then listed "dump only". Both are the scorer's start-time, first-unused matching. Fixed in
`tools_py/parity/audio_dips.py`: an endpoint dip matches the dump dip it OVERLAPS most in aligned time, one dump dip
may explain several endpoint dips, a dip that runs to the end of the capture says so, and the report ends with a
**DEVICE count per minute** (the number the A/B compares). Re-scored: **11 DEVICE events, all 50 ms, 10-20 dB, per
minute 1/3/2/4 while the briefing score plays and one at 578 s** (`dips_rescored.txt` beside the capture). The
docs that quoted 31 now say so (KNOWN section 2, CURRENT_SPRINT, the playthrough plan). Eleven is still a lead.

**The A/B is a script now, and it handles the trap.** `tools_py/parity/endpoint_route.py` (pycaw's IPolicyConfig
for the defaults, winreg + `reg export/import` for the per-app key) and `scripts/parity/endpoint_ab.sh`: backup,
remove our two exe paths' routing entries (the JBL pin), make the wired device the default for console and
multimedia (the loopback recorder follows the default; communications is left alone), run the same briefing
capture, `check` the run's own mix-open line and **refuse to score (rc 5) unless it names the device**, print both
DEVICE-per-minute tables, restore on any exit. The only live wired render endpoint is the **HyperX QuadCast S**
headphone output (USB); the HDMI monitor and the Realtek SPDIF are also active but nothing listens on them. The cost
the owner pays: their default output device is the HyperX for ~16 minutes, so the run needs them off a call.
`mission_music_long.sh` now writes the run's mix-open line to `endpoint_device.txt` and takes
`--max-device-per-minute N` (rc 4 over the ceiling) -- the pin, to be set from the A/B's result.

**W7's route: decision (a), a short safe leg.** `mission_music_long.sh --walk`: `hold+8.0:W`, settle, `hold+8.0:S`,
settle, repeated (the pattern `gameplay_damage.txt` already uses), popup guard every 8 legs, the run length
lengthened by the holds' overheads, refused on the briefing stage. Not the owner's route -- nobody has it -- and
the owner is asked for one in stick directions if they want it walked. W6 rides on the same run: the `ifpopup`
guard saves the frame it reads, and the A/B is the same command with `PS2X_GS_NO_TEX_REVALIDATE=1`.

**W10: the order is kept, and both launches are built.** `online_login_ours.py --save-password` ticks SAVE
PASSWORD = YES on the form after the password (DOWN verified on the row lit, then LEFT and CROSS each read back
off the two boxes -- YES x 176-192, NO x 240-254, a tick reads ~100 against 47 for an empty outline on
`blop_c/02_persona.png`; which press the widget answers is unknown, so both are tried and the frame decides), and
walks one DOWN fewer to CONNECT. `--saved-password` is the relaunch: the persona-list CROSS, then the PASSWORD
strip must read glyphs (its own ink floor of 100: the lit row spills 63 into the empty strip, over the keyboard
counter's 60) -- nothing typed, `login:saved-password:empty` / `:no-persona` otherwise. `--mc-dir` boots from a
named card folder, created empty (developer mode lifts the R207 path rule, and run.sh sets it). 16 tests in
`test_saved_password.py`; the 127 login-driver tests unchanged. **Removing the prefill waits for launch two.**

**W8 untouched**: the lobby channel is still the owner's line; the two-instance self-join is the fallback.

**Suite:** Python green on the touched modules (dips 20, mission music 22, endpoint route 8, login 127); the whole
discover run is recorded in the commit message.

## Still owed to the owner

They are told all of this in `docs/HUMAN_TASKS.md` ("Start here (2026-09-22, after your playthrough)"). The two
things genuinely waiting on them: **which channel their lobby was in**, and **ten minutes on a wired endpoint** for
the A/B above. Everything else on that list is machine work.
