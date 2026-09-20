# Sprint 10, Goal 1 — "it stays up": the scheduled ladder

Written 2026-09-20 ~09:20 by the controller, opening Sprint 10 while the owner is dark ("proceed on with the next
sprint and leave detailed records of where you left off and what the gates are"). The spec is
`docs/superpowers/specs/2026-09-20-sprint-10-console-players-and-it-stays-up-design.md`, Goal 1.

**The goal, in the spec's words:** a scheduled job runs N ladder rounds against the hosted server and records the
lobby rate, the round-start rate and the kill rate per run, with the exe's sha and the server's build; runs on this
host only in windows the owner is away, under the loop lock, never against a server that is not ours; the numbers
published where a person will see them -- a line in STATUS first, then a row on the site through the server session.
**Bar:** seven consecutive scheduled runs with no LOBBY-FAIL and no CRASH; a failing run files its own row, never a
silent red. **Stop rule:** a run that lags the owner while they are at the machine is a defect in the scheduling.

## What exists (built test-first tonight)

- [x] `tools_py/parity/ladder_ledger.py` (+ `tests/test_ladder_ledger.py`, 5): reads a run's `<run>.done` line and its
      `A_LADDER-SUMMARY` into one record (outcome, lobby class, rounds/asked, usable, kills, best rung, harness commit,
      exe sha256, server, when, rc); appends to `logs/ladder/ledger.jsonl`; computes the three rates and the clean streak;
      renders `docs/LADDER.md`.
- [x] `scripts/ladder_job.sh [rounds]`: the scheduler's entry. Refuses when the quiet gate says no, the loop lock is held,
      a game is running, or under 6 GB free; exports `SOCOM_SERVER_IP=3.143.65.100` (ours, fixed); launches
      `scripts/parity/ladder_frostfire.sh` pinned and detached as always; waits for the done marker (an hour at most);
      appends the ledger and re-renders the table. Its own log: `logs/ladder/job_<ts>.log`.
- [x] The Task Scheduler entry `SOCOM Unzipped ladder`, created **DISABLED**, 03:30 daily as a placeholder. Enabling it
      and naming the window is the owner's (HUMAN_TASKS).
- [x] The first run, by hand, 2026-09-20 04:32 local (`ladder_20260920_043246`): **LOBBY-FAIL create-game:create** --
      and its own capture (`A_lobby_fail_create-game_create.png`) shows the GAME LOBBY up behind the 30 s READY notice.
      The verifier missed it: the title band's reference was cut with the channel name "Channel 1" beside the words,
      and the hosted box now says "US East (Ohio)" there (distance 0.225 against a 0.15 bar; the words alone 0.011).
      Fixed the same morning: GAME LOBBY and BRIEFING ROOM compare the title words only (`LOBBY_TITLE_COLS`), calibrated
      on the 106 s7+/ladder captures (worst true 0.011, nearest wrong 0.573), a fixture cut from the failing frame and
      two tests. Two more defects the run exposed, both fixed: the job waited on `logs/parity/<stamp>.done` where the
      ladder writes `logs/<stamp>.done` (it waited its hour), and the ledger read neither that nor
      `logs/parity/drive_<stamp>.txt` (the row said UNKNOWN 0/0; re-ledgered as what it was). The double FROSTFIRE in
      the play list is the map-CROSS check's first read (0.70 < 1.0) re-sending a press that had landed -- the same on
      `s8_hosted_kill`, harmless, noted.
- [x] The second run, through `scripts/ladder_job.sh 4` exactly as the scheduler would, 10:07 local
      (`ladder_20260920_100713`): **LOBBY-FAIL create-game:create again, as expected** -- the job pins the harness at
      launch and it launched on `9596f51`, before the matcher fix (`8a1c7de`); the row IS right this time (the job
      waited on the right marker, the ledger read the right files). The pinned copy in the run dir has no
      `LOBBY_TITLE_COLS`: the proof that the fix was not in the run, not that it failed.
- [x] The third run, on the fixed harness, 10:17 local (`ladder_20260920_101741`, harness `32ba0d12`, exe `b3abebd5`):
      **KILL, 4/4 usable, 1 kill, best rung 3** -- the first row that counts. Streak 1 of 7. Rounds 3 and 4 were
      NO-KILL "aim-exhausted" and round 1's RUNG0 back-pressure wait read 119 >= 100 -- the ladder's own residuals,
      not lobby or crash classes, so the row is clean by the bar's definition.

## What is left

1. **Six more clean runs** for the bar. At one a night in the owner's window that is a week; the owner can name a
   second window.
2. **The STATUS line per run** -- the job writes `docs/LADDER.md`; a person commits it. A one-line STATUS entry per
   run is cheap and is the spec's first publication; automate it only if the owner wants commits from a job (they
   should not: a scheduled job that commits is how a working tree gets a stranger's commit).
3. **The site row** (through the hosted-server session, which owns `../scotho`): a contract for a JSON the site can
   read -- `logs/ladder/ledger.jsonl` is already the shape; agree the path and the field names in a spec section, as
   Goals 8 and 13 did.
4. **The server's build** in each record: the spec asks for it; the ledger has a `server` field (the address) and no
   build id yet. The hosted-server session knows where the box says its version; ask for one line.

## Rulings

None yet. If the job is ever changed to commit, that is a ruling; if the window is chosen by the controller rather
than the owner, that is a ruling (the spec says the owner names it).
