# Sprint 10 — "Console players in the same lobby, and it stays up" (design, drafted)

Drafted 2026-09-17 in the audit (`docs/AUDIT-2026-09-17.md` §6, then numbered Sprint 9), carried as a five-line list in
`docs/CURRENT_SPRINT.md` ever since, and written out here on 2026-09-20 at the controller handoff so that it exists as
a spec before someone has to open it. **Drafted, not opened**: the plan is written when the sprint opens, against the
tree as it is then. It opens when Sprint 9's Q8 close-out has merged and `v0.9.0` is tagged.

Markers: **[A]** autonomous; **[O]** the owner's; **[B: x]** blocked on x.

## What the sprint is for

Sprint 9 ends with a stranger able to download, run, fail legibly, report a bug and play a round on a server with a
name. What it does not give them is confidence that the server will be there next week, or anyone to play against who
is not also on this client. This sprint is those two things: the service is watched and survives a restart, and a
player on a real PS2 or PCSX2 can sit in the same lobby as a player on this client -- against OUR server only.

## Goals, in order

### Goal 1 — it stays up: the scheduled ladder (was Sprint 9 Goal 5) [A; the owner names the windows]
- A scheduled job runs N ladder rounds against the hosted server and records the lobby rate, the round-start rate and
  the kill rate per run, with the exe's sha and the server's build. Runs on this host **only in windows the owner is
  away** (it is two game instances -- the owner feels it), under the loop lock, never against a server that is not ours.
- The numbers are published where a person will see them: a line in `docs/STATUS.md` per run at first; then, through
  the site session, a row on s2u.scotho.com beside SERVER STATS. One reader, the site's.
- Bar: seven consecutive scheduled runs with no LOBBY-FAIL and no CRASH (exit 4 and 5 of the ladder contract,
  `docs/KNOWN.md` §4); a failing run files its own HUMAN_TASKS-or-KNOWN row with the log path, not a silent red.
- Stop rule: a run that lags the owner's machine while they are at it is a defect in the scheduling, fixed before the
  next run.

### Goal 2 — the hosted box as a service [A, **through the hosted-server session**; it owns `server/` and the box]
- Backups of the account/persona database off the box, restorable by a written procedure that has been run once.
- A restart and an update procedure that do not orphan personas (the game saves personas per server *name or address*
  -- Sprint 9 Goal 7's measurement says which; this procedure is written from that answer).
- Disk, memory and credit watch: the free-plan credit expires 2027-03-05; a line somewhere the owner reads says how
  much is left and what the box costs after it.
- A health line (`/api/stats` already carries players and games): add "since" (uptime) and the server build.
- This controller does not edit `server/` or `../scotho`. It writes the requirement, the server session does the work,
  and the two agree the contract in a spec section as Goals 8 and 13 did.

### Goal 3 — the mixed match, both directions [A]
- The first leg (2026-09-17) lost its place at boot: PCSX2's cold boot was faster than the recipe's 90 s and the four
  CROSS presses walked into NEW GAME. The PCSX2 side gets screen-verified steps like ours: its 640x480 frame resized to
  640x448 and read with the harness's title-band detectors, pressing on what the screen shows.
- Then leg 1 (ours hosts, PCSX2 joins) and the reverse (PCSX2 hosts, ours joins), each to a round that runs with both
  players seen moving by the other (`motion_diff`). Against our local or hosted Horizon only.
- Also settles a KNOWN §2 row on the way: whether a parked opponent starving the mover matches console behaviour.
- Bar: both legs reach a running round twice in a row. Stop rule: three launches on one leg without a joiner reaching
  the lobby -> file what the screens show and stop.

### Goal 4 — per-map kill routes; the two-instance speed freeze lifted [A]
- Twenty of twenty maps play their control round; only Frostfire has a kill route. Routes for the sweep maps, mirrored
  for swapped spawns (a swapped round is NO-DATA today).
- "The two-instance speed freeze lifted": emulator speed work has been frozen since Sprint 5 because 19-21 fps per
  instance was enough for the harness. Re-measure first -- Sprint 8's texture-cache fix changed the cost -- and lift
  the freeze only for what the two-instance case still needs.

### Goal 5 — the first two-machine match over the internet [O: a second machine or a friend; carried since Sprint 7]
- Everything is ready and has been since Sprint 7: the portable zip, `scripts/parity/two_machine_readout.sh`, the
  four questions no log can answer (HUMAN_TASKS). What it has never had is a second machine.
- If the owner's Sprint 9 playtest includes a friend on another network, this goal is answered there and closes early.

### Goal 6 — math oracles and HLE leg 3 [A, filler]
- Sprint 6 Task 6's exact-oracle math checks and the third HLE audit leg, never started. Taken when the lock is busy.

### Goal 7 — stats and clans across restarts (a real database) [O: wanted?; the server session's work]

### Goal 9 — the ONLINE tab's player name and password reach the game [A; the owner's login is the last check]
- Added 2026-09-20 on the owner's instruction ("scope out adding online name and password and slot it into an
  appropriate section of the ongoing sprint"). Investigation: `docs/research/37-launcher-online-credentials.md`.
  Plan: `docs/superpowers/plans/2026-09-20-sprint-10-goal-9-online-credentials.md`.
- Two fields on ONLINE under PROFILE -- PLAYER NAME and a masked PASSWORD -- stored in `config.json` and handed to
  the game as `PS2X_SOCOM2_LOGIN_NAME` / `_PASS`. In the runtime, an override at the game's on-screen-keyboard
  open routine fills the keyboard's buffer with the matching string before it draws, so the two keyboards open
  already typed and the player presses ENTER (R180: prefill, never submit; R179: the password is plain in the
  player's own file, masked on screen, and blanked out of bug reports and diagnostics zips).
- Bar: a driven login on ours' exe with the fields set reaches the lobby twice in a row on the hosted server
  with the harness pressing ENTER instead of typing (`--prefilled`), plus the owner's own login. The harness win
  is real on its own: the dead-reckoned keyboard typing is the largest lobby-failure class left (research/28 §5).
- Stop rule: if the keyboard-open function cannot be named with both call sites in a day of Ghidra, fall back to
  rewriting the login request in the host crypto path (research/37 Route A) and file the notes.

### Wishlist, unscheduled — the community server [B: the owner's r0004 package AND PSRewired's answer]
- PSRewired runs SOCOM II r0004, a whole replacement of the game's code; playing there needs a second recompilation
  from a package only the owner's memory card can supply, and permission only PSRewired can give
  (`docs/HUMAN_TASKS.md`, "Later / wishlist"). **Until the owner reports that answer, nothing connects to their
  server** -- the launcher's community preset stores the address and that is all.

## What this sprint does not do
An installer, signing, the public README, licences, the repository's cleanup -- all Sprint 11. macOS, ARM.

## Budget and stop rules
Two-instance launches only in away windows; one launch at a time under the lock; every moved default or skipped
measurement gets a numbered ruling; at most two C++-building agents at once.
