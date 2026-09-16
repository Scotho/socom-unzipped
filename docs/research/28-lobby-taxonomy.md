# 28 — Lobby failure taxonomy, measured from the launches on disk (Sprint 6 Task 2 Step 1)

Read-only research, 2026-09-15. No launch, build or gate was run. Every count is marked [verified]
with the command that produced it, or [inference]. Paths are repo-relative.

**Population.** Every two-instance launch since 2026-09-12 with both `logs/run_A_*.log` and
`logs/run_B_*.log` on disk: 30 launches (31 A logs, 30 B logs; the A-only `run_A_20260913_002659.log`
is `task8_mapscan`, single instance — `grep -c " B_" logs/parity/drive_task8_mapscan.txt` = 0). Earlier
09-12 launches (task6_fix/fix2/scale3/ab) have drive logs but their run logs were archived
(`logs/ARCHIVED_TO_D.txt`), so they are outside the table. [verified: `ls -la --time-style=long-iso logs/run_[AB]_*.log`]

**Pairing.** Each launch's `logs/<name>.done` mtime equals its run logs' mtime to the minute for 28 of
30; `s5_t1_launch1b`/`1c` are one minute off and are pinned by docs/research/21 §6.1 instead. [verified:
loop over `date -r logs/<name>.done` vs `date -r logs/run_[AB]_*.log`]

**Where the evidence lives.** The game's own logs carry no lobby or network line at all: their tag
vocabulary is `INFO:` (raylib), `[peek`, `[pc`, `[ps2xIOP]` (sound/MCSERV), `[socom2-input]`, `[sceCd*]`
(histogram of `run_A_20260912_195859.log`; a message histogram of cal3-A vs cal1-A differs only in
frame-save and input counts). The classification below therefore rests on the drive logs
(`logs/parity/drive_<name>.txt`), the capture directories, and the `.done` markers.

## 1. Launch table

Outcome key: **GP** = gameplay reached (`A_liveness OK`). Stage/class names are those of
`tools_py/parity/online_login_ours.py` (`CLASS_*`, lines 136-138); a class in *italics* is the
retroactive class for a launch that predates the check that would have printed it. Exit = `mpexit`
in the drive log (the era before `LOBBY_FAIL_EXIT=4` used 0/1/3 only).

| # | launch (date, out dir) | A / B log (`logs/run_[AB]_…`) | outcome | class | exit | evidence line (drive log) |
|---|---|---|---|---|---|---|
| 1 | task7_cal1 (09-12 19:58) | `20260912_195859` | failed, host stage; both READY presses fired on the wrong screen; died on liveness at 793 s | *host-not-reached* | 1 | `370.3s A_lobby cursor -1 -> down` … `613.1s A_LIVENESS FAILED: 0 in-game peek rows of 2467`; `A_19_ready.png` is the CREATE GAME name keyboard reading `test;p` |
| 2 | task7_cal2 (20:19) | `20260912_201915` | harness crash in `login` (A's keyboard walk) | crash (harness) | 1 | `PermissionError: [WinError 5] Access is denied: …pad_A.txt.tmp -> …pad_A.txt` at `online_login_ours.py:83 write_pad_file` |
| 3 | task7_cal3 (20:23) | `20260912_202355` | **GP** | ok | 0 | `413.2s A_liveness OK: 202 in-game peek rows` |
| 4 | task7_wtb1 (20:41) | `20260912_204128` | **GP** | ok | 0 | `407.2s A_liveness OK: 202 in-game peek rows` |
| 5 | task7_wtb2 (21:10) | `20260912_211009` | **GP** | ok | 0 | `429.8s A_liveness OK: 202 in-game peek rows` |
| 6 | task7_wtb3 (21:26) | `20260912_212637` | failed, host stage; liveness at 793 s | *host-not-reached* | 1 | `370.6s A_lobby cursor -1 -> down`; `A_19_ready.png` = CREATE GAME menu, cursor on RANK RESTRICTIONS; `B_19_ready.png` = "There are no games to join." |
| 7 | task7_wtb4 (21:40) | `20260912_214021` | failed, login stage: A never saw the LOGIN screen, every later wait timed out | login-keyboard (pre-login root) | 1 | `148.8s A_TIMEOUT waiting for login` … `A_on-screen keyboard never opened for 'socom'` |
| 8 | task7_wtb5 (21:46) | `20260912_214637` | failed, host stage; liveness at 787 s | *host-not-reached* | 1 | `371.0s B_lobby cursor -1 -> down`; `B_19_ready.png` = "There are no games to join."; `require_game_lobby` docstring: CHOOSE GAMES CROSS eaten, "You must create a playlist" |
| 9 | task7_wtb6 (22:00) | `20260912_220017` | **GP** (after one keyboard recovery in host) | ok | 0 | `283.1s A_on-screen keyboard up after recovery 1`; `477.4s A_liveness OK: 201` |
| 10 | task8_kill1 (23:00) | `20260912_230022` | **GP** | ok | 0 | `461.0s A_liveness OK: 160 in-game peek rows` |
| 11 | task8_kill2 (23:13) | `20260912_231341` | **GP** | ok | 1 | `453.7s A_liveness OK: 161` (exit 1 = no kill) |
| 12 | task8_kill3 (23:28) | `20260912_232834` | **GP** | ok | 1 | `454.1s A_liveness OK: 161` |
| 13 | task8_kill4 (23:41) | `20260912_234138` | failed, host stage, fast-fail at ~260 s | host-not-reached | 1 | `A_CREATE GAME did not reach the GAME LOBBY (game_lobby band distance 0.521, threshold 0.45)` |
| 14 | task8_kill5 (23:47) | `20260912_234751` | failed, ready stage; both in the lobby, A's READY dropped; liveness at 805 s | *ready-dropped* | 1 | `408.4s A_lobby cursor 2 for READY` then `624.9s A_LIVENESS FAILED: 0 in-game peek rows of 2514`; `A_19_ready.png`: socomc dot red, socome green |
| 15 | task8_kill6 (09-13 00:01) | `20260913_000141` | failed, host stage: CREATE GAME's name keyboard never opened | login-keyboard (in host) | 1 | `280.8s A_on-screen keyboard still not up after 12s` … `A_on-screen keyboard never opened for 'test'` |
| 16 | task8_kill7 (00:13) | `20260913_001324` | failed, host stage, fast-fail | host-not-reached | 1 | `A_CREATE GAME did not reach the GAME LOBBY (game_lobby band distance 0.521…)` |
| 17 | task8_frost1 (00:47) | `20260913_004754` | **GP** | ok | 1 | `407.1s A_liveness OK: 163` |
| 18 | s5_t1_launch1 (07:23) | `20260913_072321` | failed, join stage, fast-fail | join-not-reached | 1 | `B_JOIN GAME did not reach the GAME LOBBY (game_lobby band distance 0.577…)`; `B_17_game_lobby_ok.png` = games list still showing `test 1/16` |
| 19 | s5_t1_launch1b (07:29) | `20260913_072922` | failed, join stage, same distance | join-not-reached | 1 | `B_JOIN GAME did not reach the GAME LOBBY (… 0.577 …)`; doc 21 §6.1: Medius answered B's join with MediusSuccess, DME sent CONNECT_COMPLETE |
| 20 | s5_t1_launch1c (07:35) | `20260913_073548` | **GP** | ok | 1 | `415.4s A_liveness OK: 163` |
| 21 | s5_t1_launch2 (10:06) | `20260913_100624` | **GP**, then NO-CONTROL | ok | 3 | `428.6s A_liveness OK: 164`; `496.5s A_RESULT NO-CONTROL` |
| 22 | s5_t1_launch3 (11:45) | `20260913_114538` | failed, map_select stage | map-list-search | 1 | `302.9s A_map search 14: no highlighted row -- pressing on` … `A_map 'frostfire' was never highlighted in 30 presses of DOWN` |
| 23 | s5_t1_launch3b (11:51) | `20260913_115148` | failed, login stage on **both** instances | login-keyboard (pre-login root) | 1 | `111.3s B_TIMEOUT waiting for login`, `149.1s A_TIMEOUT waiting for login` … `A_on-screen keyboard never opened for 'socom'` |
| 24 | s5_t1_launch3c (11:58) | `20260913_115809` | **GP** | ok | 1 | `428.7s A_liveness OK: 163` |
| 25 | s5_t1_launch8_medley (12:47) | `20260913_124726` | failed, ready stage; A's READY dropped; liveness at 751 s | *ready-dropped* | 1 | `354.7s A_lobby cursor 2 for READY` … `571.2s A_LIVENESS FAILED: 0 in-game peek rows of 2296`; `A_19_ready.png`: socomc red, socome green |
| 26 | s5_t1_launch8b_medley (13:20) | `20260913_132036` | failed, host stage, fast-fail | host-not-reached | 1 | `A_CREATE GAME did not reach the GAME LOBBY (… 0.521 …)` |
| 27 | s5_t1_launch8c_medley (13:28) | `20260913_132843` | **GP** (verified map CROSS and READY patched in) | ok | 0 | `454.0s A_liveness OK: 159`; `RESULT CONTROL-ROUND round_ended=yes` |
| 28 | s5_t5_ladder1 (21:24) | `20260913_212452` | failed; root: A's CROSS to BRIEFING ROOMS dropped, the fixed presses drifted into IGNORE LIST | map-list-search (root: rooms press dropped) | 4 | `225.0s A_TIMEOUT waiting for rooms`, `266.5s A_TIMEOUT waiting for briefing_room`, then `322.8s A_RESULT LOBBY-FAIL map-list-search` |
| 29 | s5_t5_ladder1b (21:30) | `20260913_213048` | **GP**, after one map-CROSS re-send | ok (1 resend) | 1 | `254.8s A_LOBBY RESEND map-cross-dropped attempt=1`; `416.1s A_LOBBY class=ok` |
| 30 | s5_t5_ladder2 (23:04) | `20260913_230442` | **GP**, after one map-CROSS re-send; 3 kills | ok (1 resend) | 0 | `305.8s A_LOBBY RESEND map-cross-dropped attempt=1`; `466.2s A_LOBBY class=ok` |

## 2. Counts

Base: 30 launches. `S=logs/parity/drive_{task7_*,task8_kill*,task8_frost1,s5_t1_*,s5_t5_*}.txt` (30 files).

| class | n | launches | how counted |
|---|---|---|---|
| gameplay reached | **14** | cal3 wtb1 wtb2 wtb6 kill1 kill2 kill3 frost1 1c 2 3c 8c ladder1b ladder2 | [verified] `grep -l "A_liveness OK" $S \| wc -l` |
| host-not-reached | **6** | kill4 kill7 8b (fast-fail, `CREATE GAME did not reach` = 3) + cal1 wtb3 wtb5 (pre-check, liveness) | [verified] 3 by grep; 3 [inference] from `lobby cursor -1` + the `*_19_ready.png` captures listed above |
| login-keyboard | **3** | wtb4 3b (root: `TIMEOUT waiting for login`, both) + kill6 (in host: game-name keyboard) | [verified] `grep -l "keyboard never opened" $S` = 3; `grep -l "TIMEOUT waiting for login" $S` = 2 |
| join-not-reached | **2** | launch1 launch1b | [verified] `grep -l "JOIN GAME did not reach" $S` |
| ready-dropped | **2** | kill5 launch8 | [inference] `LIVENESS FAILED` with both `lobby cursor 2 for READY` and `B_teams (143, 144)`; captures show A not ready, B ready |
| map-list-search | **2** | launch3 ladder1 | [verified] `grep -l "was never highlighted" $S` |
| harness crash | **1** | cal2 | [verified] `grep -l Traceback $S` |
| liveness failures total | 5 | cal1 wtb3 wtb5 kill5 launch8 | [verified] `grep -l "LIVENESS FAILED" $S` |
| resend rescues (would have failed pre-R47) | 2 | ladder1b ladder2 | [verified] `grep -l "LOBBY RESEND" $S` |
| keyboard recoveries (would have been login-keyboard) | 1 | wtb6 | [verified] `grep -l "keyboard up after recovery" $S` |

Gameplay-reached rate: **14/30 = 47 %** overall [verified]; 9/17 (53 %) for the task7/task8 era and
5/13 (38 %) for Sprint 5; the "4 in 10" of KNOWN.md §4 is the Sprint 5 figure. Exit tally
[verified: `grep -h "^mpexit=" $S | sort | uniq -c`]: 0 ×7, 1 ×21, 3 ×1, 4 ×1 — only one launch ever
exited 4, because 26 of the 30 predate `LOBBY_FAIL_EXIT`. Class printed (`LOBBY class=`): 3 launches only
(ladder1 fail, ladder1b/2 ok).

Cost: the five pre-check liveness failures each ran 751-805 s before failing; the fast-fails 260-330 s.

## 3. Unclassified failures — the earliest line that shows what went wrong

All five are exit 1 with no class; each was placed above from its own capture.

| launch | earliest divergence | what the screen shows |
|---|---|---|
| cal1 | `134.4s A_keyboard in accent mode -> toggling` is normal; the first abnormal line is `370.3s A_lobby cursor -1 -> down` (READY search on a screen that has no lobby cursor). The 8 up/down presses and CROSS "for READY" were typed into the name keyboard | `A_19_ready.png`: CREATE GAME, "Enter Game Name" keyboard, text `test;p` — the walk that types `test` then ENTER lost a press and the later up/down/cross presses appended `;p` |
| wtb3 | `370.6s A_lobby cursor -1 -> down` | `A_19_ready.png`: CREATE GAME settings menu, cursor on RANK RESTRICTIONS, PLAY LIST empty — the `up, cross` to CHOOSE GAMES (`open_choose_games` 826-827) landed elsewhere; `B_19_ready.png`: "There are no games to join." |
| wtb5 | `371.0s B_lobby cursor -1 -> down` (A's cursor read 2, so A *was* on a lobby-like screen) | `B_19_ready.png`: "There are no games to join." — A never created the world; the `require_game_lobby` docstring records the CHOOSE GAMES CROSS as eaten and the "You must create a playlist" notice |
| kill5 | none before liveness: `406.5s B_lobby cursor 2 for READY`, `408.4s A_lobby cursor 2 for READY`, then `624.9s A_LIVENESS FAILED` | `A_19_ready.png`: GAME LOBBY, cursor still on READY, socomc (A) red dot, socome (B) green — A's READY CROSS was dropped |
| launch8 | same shape: `352.8s B_lobby cursor 2 for READY`, `354.7s A_lobby cursor 2 for READY`, `571.2s A_LIVENESS FAILED` | `A_19_ready.png` identical in content to kill5's |

The two login-stage failures deserve the same note: in wtb4 and 3b the first abnormal line is
`TIMEOUT waiting for login` right after `main menu after 2 presses`; the `login-keyboard` class they
end in is 120-180 s downstream of the real miss (the press from the main menu to the LOGIN screen, or
the `login` reference not matching). In 3b **both** instances missed it at once.

## 4. Fix order, by frequency, with the fixed presses that own each class

| rank | class (n of 30) | stage function, `tools_py/parity/online_login_ours.py` | the blind presses |
|---|---|---|---|
| 1 | host-not-reached (6) + kill6's keyboard (1) = **7** | `open_choose_games` 817-829, `host_game` 832-846, `require_game_lobby` 661-680 | `press("up",2.0)`, `press("cross",6.0)` CREATE GAME, `press("cross",5.0)` name keyboard, `type()`, `press("up",2.5)`, `press("cross",6.0)` CHOOSE GAMES, `press("square",5.0)` ACCEPT, `press("square",25.0)` CREATE, `press("cross",4.0)` CONTINUE. Only the map CROSS (`press_map_cross_verified` 265-276) is verified today; the check at the end (`require_game_lobby`) names the stage but not which press. The captures say the miss is before CHOOSE GAMES (cal1: name keyboard; wtb3: settings menu; wtb5/kill4/kill7/8b: empty play list) |
| 2 | login-keyboard, pre-login root (**2**: wtb4, 3b) | `boot_to_online` 565-589, `login` 590-650, `Shell.wait_for` 421-431 | `wait_for` logs `TIMEOUT waiting for <screen>` and **returns False; every caller presses on** (`login` 592-597: `press_until_gone("cross","login")`, `wait_for("universe",60)`, `wait_for("persona",60)`, then fixed `press("cross",4.0)` ×2-3). The class is only raised 120 s later by `type()` 508-512 |
| 3 | join-not-reached (**2**) | `join_game` 884-898 | `press("cross",8.0)` JOIN GAME, `press("cross",25.0)` first game, `press("cross",3.0)` CONTINUE, then `require_game_lobby`. Both misses read 0.577 with the games list still up (transport joined per doc 21) |
| 4 | ready-dropped (**2**, both pre-R47) | `ready` 901-932, `lobby_select` 864-881, `verify_resend` 252-262 | Now verified: `READY check` + re-send (R47/R69). Zero occurrences since; keep as regression class only |
| 5 | map-list-search (**2**) | `choose_map` 781-815; root of ladder1 is `to_briefing_room` 651-659 | `press("down",2.0)`, `press("cross",3.0)` BRIEFING ROOMS, `wait_for("rooms",30)` (timeout ignored), `press_until_gone("cross","rooms")`, `wait_for("briefing_room",40)` (timeout ignored). launch3's list showed no highlighted row at DOWN 14 and 20 (scroll state), a different mechanism from ladder1's drift |
| 6 | map-cross-dropped (0 failures, 2 re-sends) | `press_map_cross_verified` 265-276 | fixed already; the re-send worked both times |
| 7 | harness crash (**1**) | `write_pad_file` 101-121 | fixed (40-try retry on WinError 5, comment at 112-115) |

Suggested first move (rank 1 and 2 share it): make `Shell.wait_for`'s timeout a stage failure
(`lobby_fail(sh, f"screen:{name}")`) instead of a log line, and add a screen check after each CREATE
GAME press (`12_create_game`, `13_game_name`, `14_choose_games`, `15_play_list` are already captured;
`game_lobby` is the only one with a reference). That converts every rank-1/2 launch into a fast-fail
with the press named, and stops the 750-800 s liveness burn.

## 5. Blind classes — what the logs could not tell, and the logging that would have

1. **Which press was dropped, in every class.** The drive log records presses only as stage
   lines (`screen X after Ns`, `X gone after N cross`); the fixed presses inside `open_choose_games`,
   `host_game`, `join_game`, `to_briefing_room` write nothing. A one-line `PRESS <button> stage=<s> step=<k>`
   per `Shell.press`, plus a frame hash before/after (the `LOBBY_FRAME_MAX_AGE_S` machinery exists),
   would name the miss instead of the stage. Six of the sixteen failures were classified here only
   by opening captures by hand.
2. **Pre-login misses (wtb4, 3b).** `TIMEOUT waiting for login` is logged and ignored; no class, no
   capture beyond `timeout_login.png`. In 3b both instances missed at the same moment, which the logs
   cannot distinguish from a server or window-focus event. Log the window title/focus and the server
   reachability at each timeout.
3. **Server-side ground truth is unusable per launch.** `server/logs/console-Medius.log` covers exactly
   this window (server start 2026-09-12 18:03, file mtime 2026-09-13 23:25:23 = ladder2's end
   [verified]) and holds 66 `MediusAccountLoginRequest`, 21 `MediusCreateGameRequest`, 41
   `MediusJoinGameRequest` (21 host self-joins + 20 guest joins), 20 `MediusServerEndGameRequest`
   [verified: grep counts], but **no line has a timestamp**, so no world can be pinned to a launch and
   the 21 creates cannot be split between the 30 launches and the four task6 launches in the same
   window. Enable timestamps in the Horizon console logger (or have the harness log its own wall clock
   at each stage) and the create/join/end triple becomes a free per-launch classifier: "host never
   created" vs "guest never joined" vs "joined, never started".
4. **Mistyped keyboard walks.** The server log shows three logins with `PASS:socoj` (a keyboard walk
   that landed one key off) [verified: `grep -c 'PASS:socoj'` = 3], all before cal1 by position; cal1's
   `test;p` is the same class on the game-name keyboard. The harness never reads back what it typed.
   A capture-and-compare of the text field after `type()` (the field box is fixed) would classify these.
5. **ready-dropped before R47** (kill5, launch8) was blind by construction — no READY read-back
   existed; it is not blind now.
6. **The game log itself.** It has no lobby, Medius or DME line; the runtime's net trace
   (`build_nettrace`) exists but was not on in any of these launches. A single `[net] Medius <msg>`
   line per request would have made section 3 a grep.

## 6. First launches on the block-pointer exe (2026-09-15 evening, harness `6ff0335`/`c5cfa78`, exe `1cfef9af…`)

Three two-instance launches, 0/3 gameplay, two distinct causes — neither the lobby stages this note's §4 ranked first.

| launch | outcome | what actually happened | evidence |
|---|---|---|---|
| `s6_ladder1` (new harness) | `LOBBY-FAIL pre-login` after 9 boot presses, both instances | **the runtime barely ran**: 34 `[gs-gl stats]` present windows in 490 s (the next two launches: 175 in 258 s, 173 in 274 s), thread 1 parked at VSync on every sample, 216 frame exports vs ~6/s expected; the 8 CROSS presses reached the input layer (`[socom2-input] state buttons=4000`) but the guest never advanced past the memory-card slot dialog. A single-instance boot with the same environment two minutes later, and `s6_ladder2` on the same harness, both booted normally (main menu after 2 presses) — a **transient host condition on the first two-instance launch of the freshly built exe**, cause not identified (Defender scanning the new 236 MB binary is the guess). [verified: the counts; inference: the cause] | `logs/run_A_20260915_210946.log`, `logs/parity/s6_ladder1/A_lobby_fail_pre-login.png` |
| `s6_ladder_oldharness` (Sprint 5's harness `171290b` pinned, as a bisect) | `LOBBY-FAIL timeout:login`, both | boot fine; the OSK opened in **accent mode** on both instances (`osk_ref_dists` (6.3, 0.0); in Sprint 5 only B did), the old harness's toggle detection read (43, 39) — neither mode — and it typed the password as `xmfû` | `logs/parity/s6_ladder_oldharness/A_lobby_fail_timeout_login.png` |
| `s6_ladder2` (new harness) | `LOBBY-FAIL timeout:login`, both | boot fine; accent mode detected and toggled; then **B's password reached the server as `ocom`** (`MediusAccountLoginRequest USERNAME:socome PASS:ocom` → `MediusInvalidPassword` — the first character was lost) and **A pressed CONNECT with an empty password** and landed on the "Choose a different persona" dialog. The guest ran at **32 fps** in the stats window where the OSK opened (Sprint 5: 60), and the pad walk is dead-reckoned with 0.09 s holds. | `server/logs/console-Medius.log`, `logs/parity/s6_ladder2/A_05_password.png`, `B_04_pw_kbd.png` |

Consequences: (1) the OSK typing is the blind class §5 named, and it now costs launches — fix: read back the typed length from the OSK text row (cursor block at ~30 + 11.3 px per character) and retype slower, class `login:keyboard-typing`; (2) `timeout:login` is too coarse a class — the stage timed out at the persona dialog / the invalid-password prompt, which the login flow does not recognise; (3) the accent-mode toggle must re-read the mode after toggling; (4) launch 1's starved runtime is a hazard to watch for: a launch whose `[gs-gl stats]` cadence collapses should be classified as such, not as a lobby failure.

**Launch 4, `s6_ladder3` (harness `b8d2410`, with the OSK read-back):** login PASSED on both instances — `[osk] mode accent -> toggling`, `mode normal`, `typed 5 of 5 (attempt 1)` on A and B, Medius accepted — then `LOBBY-FAIL map-list-search` on A: the AVAILABLE MAPS walk read "no highlighted row" at presses 9, 15 and 20 and pressed on; Sprint 5's same code found FROSTFIRE highlighted at row 4 after exactly 15 DOWN. The luminance model still holds on today's captures (highlighted 125, pale 170, empty 110), so the misses were frames read mid-scroll at today's lower two-instance frame rate, and the loop walked past the target to the last entry (THE RUINS). Fix in flight: re-read instead of pressing through an unreadable frame, and score all six visible rows so the target is found whether or not it is highlighted. [verified from `drive_s6_ladder3.txt` and `A_14_map_frostfire_NOT_FOUND.png`]

**Launches 5–6, `s6_ladder4` and `s6_ladder5` (harness `cc94efb`, both lobby fixes):** the lobby reached gameplay on
both instances in both launches — the map walk logged `visible at row 5, cursor at 4 -> down` / `-> up` and accepted
FROSTFIRE at row 3, with one verified re-send each for `create-game:choose-games-select` and `map-cross-dropped`.
`s6_ladder4` then ended `NO-CONTROL side=B`: B spawned **already zoomed 3.0×** (its first in-game capture shows the
scope) and moved at scope speed (18–25 units per 2 s hold vs 54); research/30 traces the zoom to D-pad UP edges
reaching the player update, and B's READY search had pressed DOWN/UP eight times after the host readied (class to add:
`ready:cursor-not-found`; the wiggle must stop when the game lobby is gone). `s6_ladder5` (normal READY): both sides
controllable (B 54.7), round 1 played, the mover stuck at wp8 with 0 bursts and the round ended on its clock; round 2
restarted (00:00 → 05:59 after ~130 sampler rows) but the ladder's 45 s next-round wait had given up (now 120 s). The
mover's slowness (per-row move p50 1.5 vs 4.9 in Sprint 5) is **confounded**: a decomp-reading agent was grepping the
host during the round, against KNOWN §4's quiet-host rule; back-pressure waits (357/384) match Sprint 5's round 1
(443/3) and do not by themselves show a slower replay. Re-measure on a quiet host. [verified: the log lines and
captures; inference: the confound]

**Launches 7–9, `s6_ladder6`–`s6_ladder8`:** `s6_ladder6` failed at login on both sides on two more blind presses (a DOWN
before CONNECT dropped → CROSS on GENDER; a step of the ENTER walk dropped → keyboard still up); `s6_ladder7` on the
main menu's ONLINE CROSS (menu still up, ONLINE lit). Each was made verify-then-act (`[login] connect focus`, `[osk]
enter`, `[login] online`, `[login] persona list`), and `Shell.press` now writes the pad file instead of posting keys.
**`s6_ladder8` (harness `d6e417f`) reached gameplay on both instances with every stage verified on the first attempt
and killed on 4 of 4 rounds** (KNOWN §1). Tally for the evening: 8 launches, 3 reached gameplay; of the 5 that did
not, one was the starved runtime and four were blind presses that are now verified. [verified from the drive logs]
