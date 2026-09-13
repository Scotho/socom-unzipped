# What we know, what we believe, and what we got wrong

A living list, audited after every task. Entries are **promoted** (believed → proven) when an
artefact settles them, **retired** when they stop mattering, and **retracted** loudly when they
turn out false. Every proven entry names the artefact that proves it; every believed entry names
the experiment that would settle it. If an entry cannot do that, it does not belong here.

Maintained by whoever is running the loop. Last audited: 2026-09-13, after the Sprint 4 whole-branch review.

---

## 1. Proven — with the artefact

| What | Artefact |
|---|---|
| PCSX2 plays a full online round against **our own** Horizon server, advancing to round 2 | `research/18` §1 + tracked contact sheet `docs/research/assets/18-s0-evidence.png` |
| A playing match and a frozen one produce **byte-identical** DME TCP profiles (11 BROADCAST / 30 SINGLE / 7 TOSERVER / 2 aux-UDP, same opcode histograms) | `research/18` §1; recounted from the raw log by review |
| The peer channel carries **zero** application data all match — every datagram decoded | `research/18` §3 |
| The advertised-port and shared-RSA divergences were real, and their fixes reached the wire | `acb603e`; wire bytes `4C-0E` both slots, distinct keys verified by `(m^17)^d mod N == m` |
| Neither of those fixes moved the symptom | Same runs; 3 hypotheses now falsified by measurement |
| The player's **feet** are at the right height (−145.875 vs console −145.8672); the defect is the **camera** | `research/17` §0.1, derived from `STATUS.md`'s 2026-09-09 01:30 entry's own camera y values |
| The skeleton root node decays 11.4845 → 0 while its saved copy freezes at the console's 5.50391 | `research/17` §4.1, raw trace `run_20260912_121304.log:3962-6975` |
| `rand()` returned 15 bits over a `_rand_next` frozen at 41 (host CRT's first draw) | `ede2096`; `_rand_next = 0x29` in four of our RDRAM images, live in all three PCSX2 images |
| The disputed mover field could not exceed 4.0000458 under the old mask; console reads 6.3338 | `research/17` §6; two samples a side |
| Five soft-double stubs were bound with the wrong ABI, and were **identity** at 19 of 22 sites (the 3 garbage sites are unreachable) | `db7a992`; delay-slot analysis of every call site |
| The intro-movie macroblocks were a cross-thread race on `m_currentTransfer`, not a byte-accumulator bug | `4a701f1`; deficit 3,748 → 0, MISSING 9 → 0 |
| `--vram-diff` catches a uniform ±1 px shift again after the seam budget (8/15 x, 6/15 y) | `6c017c2`, measured on real renders |
| **One player walking to the other cannot finish inside a round.** Measured closure efficiency is 39 % (758 units gained for 1961 walked) at ~15 s/step, so 1382 units needs ~450 s against a ~360 s round. Two movers is ~700 units each, ~180 s | Task 7 run `wtb2`, `logs/run_A_20260912_211009.log`; arithmetic checked by review |
| ~~**The two-instance approach closes faster than one:** 1359 units in 127 s against Task 7's 758 in 300 s~~ **SUPERSEDED — derived from the camera+facing reconstruction that was later proven wrong by up to 50 units. Use the actor-row generation below (1485.5 → 50.0 in ~127 s).** The rifle facts stand: 96 R1 injections, ammo 30/30 → 0/30, impacts on the wall ahead of the muzzle | Task 8 run `ours_task8_kill2` |
| ~~**They fought at ~90 units** (median 93, min 34.9, 3 % inside 45)~~ **SUPERSEDED by the actor-row generation below (min 50.0, median 67.9, 0 % inside 45).** Same conclusion, better instrument | Review of `9c28fe0`; superseded once `true_pos()` read the actor's own coordinates |
| **Player health is `actor+0x1044`** (float; 1.0 full, <= 0 dead) and **`actor+0xF7A` is the alive byte** (1 = alive), on SCUS_972.75 **r0001** | `research/19` (two community memory tools agree, one matched to our ELF by patch bytes); decomp compares `+0x1044 <= 0.0` for three teammates in a row, then `< 0.2` and `< 0.5`; every image reads 1.0 and 1, the console's included. **Not yet read live in an online match** |
| **The multiplayer round-state object is `*0x437ce8`**: `total_mp_kills`, `mp_round_count`, `mp_game_over`, rounds won and alive per team (each value a short 4 bytes into its record), and the major/minor/"my" round-state bytes at `+0x113..+0x115` | `research/19`; decomp references `DAT_00437ce8` in the round code. Separates a kill from a round ending on its clock without a screenshot |
| **Open-loop aim resolution is floored at ~20-40° by the HARNESS, not the runtime.** The harness's `PAD_AXIS` sends only full deflection (0/255); the shortest usable hold already sweeps 35-40°, against a body that subtends 15-20° at contact range. **The pad file itself accepts 0-255 per axis**, so partial-stick aim is available for the cost of one re-calibration | Task 7 §3.13 (19 timed holds, repeat scatter 99.5 vs 80.8 at one hold length); pad-file range confirmed by the Sprint 5 planning pass |
| **The local player's actor is reachable from a STATIC: `*0x408c58`** (also `0x40d744`, `0x440c38`, and `*0x415ff0+0xbc`). Full chain: `@408c58` word0 = `017941d0`; `@17941d0` word0 = `006691a0` (actor vtable); `*(actor+0xc0)` = mover `006694b0`. The `*0x488de8+0xbc` route is **not** it — that route is recorded in `STATUS`'s 2026-09-09 01:30 entry, not HANDOFF, and `0x488de8` is the *camera* | Offline scan of five of our RDRAM images **and the PCSX2 console image** for vtable `0x6691a0` keeping the actor whose mover is `0x6694b0`; live in an online match (`logs/run_A_20260912_230022.log`, actor `0x17941d0`, 804 rows); `*0x488de8+0xbc` resolved 24 times in 1162 rows and to `0xd9d9d9d9`. `research/18` §4.1; route written into `HANDOFF.md` "Open items" item 0 |
| **Two movers close the map four and a half times faster than one**: `ours_task8_kill2` closed the true 3-D gap **1485.5 → 50.0 units in ~127 s** (11.3 units/s) against Task 7's 757.8 in 300 s (2.5 units/s), both players walking — the first time two online players have been in the same place | `ours_task8_kill2`, `logs/run_A_20260912_231341.log` / `run_B_…` (1172 / 1055 in-game rows). Team-closed over team-walked **61.0 %** vs `wtb2`'s 38.6 %; `kill1` was **36.5 %**, i.e. no better than one mover. Per-side efficiencies double-count the same gap and must not be quoted |
| **The bursts hit nothing because the players were never in range at all, in three dimensions**: on the ACTOR rows the minimum true 3-D separation for the whole run was **50.0 units**, the last 400 rows had a median of **67.9** and a median elevation of **43.3°**, and **0 %** of them were inside 45 units in 3-D, inside 25, or within 10 of each other's height. Range and elevation are co-equal causes; the 77° figure is the single worst row | Same run, actor positions (words 7/8/9). ~~`actor+0x204`/`+0x208` unchanged, so no damage was dealt~~ **Whether damage was dealt is UNKNOWN** — those were not the health field (`research/19`); the geometry conclusion stands on its own |
| **The loop's own distance was wrong by tens of units**, because it reconstructed each player as `camera + 24.9 * facing`: a facing wrong by tens of degrees misplaces a player by up to two orbit radii (~50 units), and placing the OTHER player needed the other side's facing | Reproduced in a **flat** simulated world: reported-best vs ground truth was 40.3/64.3, 23.4/30.7 and 157.6/204.7 before the fix, and **18.1/18.1** after `true_pos()` read the actor's own x/y/z. `research/18` §4.11 |
| **The camera record orbits the actor at ground radius 20.65 (sd 5.17), 19.73 above it** — i.e. the camera looks down on the player from ~44°, which is a free pitch readout | 1172 paired rows of `ours_task8_kill2`; the actor's own position is at `actor+0x1c/+0x20/+0x24` |
| **The rifles DID fire** — this is a geometry failure, not an input one | `buttons=0800` (bit 11, R1) injected **96 times** in `logs/run_A_20260912_231341.log`; HUD ammo `A_fight04.png` 30/30 → `A_fight07.png` **0/30** with bullet impacts on the stone wall in front of the muzzle, `B_final.png` 13/30 1 MAG (~47 rounds fired) |
| **The online movement blocker was `sceInetInterfaceControl(0x200)` returning a constant** — `msSinceNetActivity` never reset, so the movement scale clamped to 0.0 on frame one. Pitch is not among the three scaled axes, which is why RY survived | `abf35bb`; `DAT_0045a1ca` measured 1 (killing the rival candidate), `MoveScale f12 = 1.0` on all 332/331 calls, instance A ~~73 distinct x (539.7→337.9)~~ **65** distinct x (first→last 539.68→471.01; the struck figures were a miscount and min/max) against 1 before, B **80** (1145.28→981.87) — `research/18` §3.12 "Verified" holds the numbers to quote. **Same-binary A/B** (`5ed29ca`, one match, both legs a frame apart): fix ON f12 = 1.0 on 330/330, idle max 1490 ms, activity globals 192/192 distinct, 89 distinct x; fix OFF f12 = 0.0 on 339/339, idle 504,210 ms, globals never written, **0.46 units** of travel. Movement tracks the stick — 1.3 units at neutral vs 28-38 per hold, starting on the hold frame, axes orthogonal. Review verified every figure to 3 dp |

## 2. Believed, unconfirmed — with the experiment that would settle it

| What | What would settle it |
|---|---|
| Which of `I`/`K` (right stick up/down) raises the muzzle | One timed pitch hold measured against the elevation of a target of known height difference. The engagement sweeps both ways precisely because this is unknown |
| **Frostfire's lost control may be UNINITIALISED MEMORY, not a movement defect.** Bytes the game never initialises in the round-state object read `0xAF` on ours and `0x00` on the console — among them `+0xd2`, the flag behind "You are a ghost. You will play the next round as a real player", tested by five online routines. The object is allocated per map from our replacement heap, so the garbage can differ by map, which would explain Medley working and Frostfire not. The difference is verified; the causation is inference, and new-round code does clear the flag | One Frostfire relaunch peeking `*0x437ce8:84`: is `+0xd2` set when the move path stops? If yes, a same-binary A/B with zero-filled allocations |
| **On Frostfire the local move path ran for 0.6 s at round start and never ticked again** — 18 calls (`#0`-`#17`) between t=371.4 and t=372.0 s while 2634 peek rows kept arriving (Medley's kill2 runs ~5560 calls over 293.6 s = 18.9/s), with the pad reaching the guest, the movement scale at 1.0 and the round clock running. Reads as control never being handed over, not as a slow map. **Two leads from the same logs:** both actors read `+0xd0/+0xd4` = **1/1** and `+0x20c` = **0** for the whole run, where every Medley actor reads 8/5 and 4/7 — a *state* difference; and in `FUN_00594cf0` the move-scale call sits inside `if (cVar7 == 0)`, so the multiplayer snap-back — **excluded only on Medley** — would produce exactly this picture. reCOM names the likely state: `mp_major_game_state`, `late_joiner` (`research/11`). Frostfire spawns are 692 units apart (Medley 1485) with a 42-unit height difference. **One run; §3.12's movement fix is proven on Medley only** | A zero-launch pass mapping reCOM's round-state names onto the round-start path, then one relaunch with `PS2X_CALL_TRACE_EVERY=1`, a trace on the **caller** of `0x553dc0`, the snap-back timestamp pair, and the `0x200` idle counter |
| Whether a parked opponent starving the mover matches **console** behaviour, or is an artefact of feeding the counter from RX bytes only (the game's own source may be richer) | A PCSX2 pair with one player parked and the other walking, same `actor+0x1368` measurement |
| Which of the two skeleton candidates is real — a lerp dropping its `a·w` term, or a second writer | `research/17` §4.3: read the node on return from the blend and again later in the same frame |
| The transition residual strip (~1 in 5 runs) is a `refreshDirtyRows`/`executeClear` ordering artefact | No isolation test has been run; the *pre-existing on both binaries* half is measured |
| The intro-cinematic freeze (seen once, Sprint 1) is a real defect | Not reproduced since |
| The DME aux-UDP channel carries nothing at round start | Rate bound only; `PS2X_SOCOM2_NET_TRACE_ALL` now closes it |
| `sin`/`cos` have no live call sites | Direct-`jal` count only; `0x001D55B8`/`0x001D55BC` hold their addresses in a probable dispatch table |

## 3. Retracted — believed, then killed by measurement

- **"The PCSX2 golden match is the same frozen state"** (`HANDOFF.md` "Open items" item 0). False. That golden was two
  stills of a match with **no input ever sent**. Weeks of server- and protocol-directed reasoning
  were aimed at the wrong body of code. *Retracted in the tree 2026-09-13 (Task 9a): `HANDOFF.md`
  item 0 and `STATUS.md` 2026-09-10 20:10.*
- **"The actor rests 14.7 above the ground vs the console's 20.1"** (`HANDOFF.md` "Open items" item 2; `STATUS.md` 2026-09-09 01:30).
  Both numbers are camera-eye minus collision-hit. The player's feet are right to 0.008.
  *Retracted in the tree 2026-09-13 (Task 9a): `HANDOFF.md` item 2 and `STATUS.md` 2026-09-09 01:30,
  which prints the two camera y values it was differencing.*
- **The player actor at `*0x488de8+0xbc`.** Wrong; it is `*0x408c58`, verified across
  six images including the console's. Retracted in place 2026-09-13 (Task 9a): the correct chain is
  now in `HANDOFF.md` item 0 and the misreading is marked at `STATUS.md`'s 2026-09-09 01:30 entry.
  **Attribution correction:** this was never written in `HANDOFF.md`. `0x488de8` is the *camera*
  singleton; `STATUS.md` 2026-09-09 01:30 said `+0xbc` is "the camera's follow pointer … null in
  the spawn images", and later work read a warning as a route. HANDOFF's own peeks use
  `*0x488de8+0x320`, the camera position, which is correct and stays.
- **`actor+0x204`/`+0x208` are the player's health and max health.** Wrong — health is `+0x1044`
  with an alive byte at `+0xF7A` (`research/19`). The candidates were never confirmed (zero kills to
  confirm across), which is exactly why they were kept disarmed; the one row that leaned on them
  ("no damage was dealt") is withdrawn.
- **"Frozen at STARTING ROUND 1 OF 11, waiting for a go"** (spec §1 and several STATUS entries).
  The banner is transient on ours too and the round timer runs. The true sentence is *the round
  runs and the local player cannot move* — and that is fixed (`abf35bb`, `5ed29ca`).
  *Retracted in the tree 2026-09-13 (Task 9a): `HANDOFF.md` item 0, `STATUS.md` 2026-09-10 20:10,
  and the Sprint 4 spec's own §1 bullet.* The entry that recorded the symptom also recorded "the HUD
  timer runs regardless" and that RY worked while RX/LX/LY did not — a transport failure cannot
  deliver pitch and withhold yaw. Both refutations sat in the same paragraph as the claim.
- **The `cVar7 == 0` axis-clearing arm is the movement gate** (`4114ad4`'s commit message). Rejected:
  the routine is a generic axis setter, its guard cannot fire because our own IOP module hardcodes
  link-up, and the arm returns before all four axes are written — so pitch would have died too.
  Three calls matching three dead axes was a coincidence.
- **The mover's `4.0` vs `6.3338` is a capsule radius.** It was the 15-bit `rand`.
- **`PS2X_GS_SCALE=2` will sharpen the HUD** (Sprint 3 spec DoD). It cannot: HUD, menus and title
  are textured quads at native texel density. The design doc said so before anyone measured it.

> Cite **item names and dated entries, never `file:NN`** — line numbers rot the moment anyone
> edits above them, and a dangling citation is how the actor-pointer mis-attribution happened.
>
> Retract **on discovery**, not at close-out. All of §3's first three were still false in the tree
> hours after being disproved — and in the end they were retracted **at close-out anyway**
> (2026-09-13, Task 9a), which is the outcome this note exists to prevent. The elapsed time between
> "a reviewer proved this sentence false" and "the sentence stopped being read by fresh sessions"
> was about a day for the first three and two weeks for the freeze description. The rule is in
> `docs/process-audit.md`: a review finding that a committed sentence is false produces a same-hour
> edit, and close-out *verifies* retractions rather than performing them.

## 4. Standing hazards — things that will bite again

- **The gate proves regression only.** It was blind to the 15-bit `rand`, the skeleton decay and the
  soft-double chain. A green gate means "no worse than the reference", never "correct".
- **Our HLE returning a constant where the guest expects a live value** — three for three this
  sprint (`rand` over a frozen seed; `0x200` never advancing; stale-register math returns). Presume
  remaining gameplay wrongness is this shape until shown otherwise. **Widened by `research/19`:**
  the same class includes memory the game never initialises and our replacement heap fills
  differently from the console's (`0xAF` against `0x00`) — a stub need not be called at all to hand
  the guest a wrong value. The cheap test that caught all
  three costs no run: dump the suspect word from several of our RDRAM images **and** the PCSX2
  console image — identical across all of ours and different on the console's is the signature.
  Written up in full at `STATUS.md` 2026-09-13, with the per-defect detail in `research/17` §5.1
  (soft doubles) and §6.1 (`rand`).
- **The title gate passes at 16 of 23.** A pillarboxed run scores 18 — a pass with margin. The crop
  fixed silent score degradation and left the geometry itself unchecked. Assert the client rect.
- **The online harness can produce complete, convincing evidence of nothing.** One run drove sixteen
  stick probes and wrote sixteen screenshots against a lobby keyboard. **Verify `peek @416054` is
  non-zero before believing any movement claim from it.** Three of six runs were unusable.
- **`build.sh test` runs zero Python tests.** `test_compare.py`, `test_pine.py` and `test_winshot.py`
  are pytest-style and have never executed.
- **Nothing reaps the loop lock** when an agent exits without releasing it, and `loop_lock.sh take`
  is a non-atomic test-then-write.
- **`git add X && git commit` commits the whole index, not X.** With several agents sharing one
  working tree, that sweeps another agent's staged files under your message — it happened to
  `872d8d6`, which carries five of Task 8's files under a `docs(known)` subject. Always commit
  with an explicit pathspec (`git commit -- <paths>`), never a bare commit after an add.
- **Task reports live in gitignored `.superpowers/sdd/`** and die with the workspace. Anything
  durable must be copied into a tracked doc before close-out. *Sprint 4's carry was done
  2026-09-13 (Task 9a):* the HLE hazard and the Tasks 6-8 harness rules → `STATUS.md` 2026-09-13;
  Task 4c → `research/17` §5.1; Task 4b → `research/17` §6.1; Task 1's `movie_blocks.py` limits →
  `research/16` §9.1.1. Everything else in those reports is accepted as lost.
- **`movie_blocks.py` is wired into nothing** — not `build.sh`, not the gate, not any committed
  script — so four review rounds of hard-won properties (monotonicity, arrangement-invariance,
  per-screen furniture) are held in place by no automation at all, and its `--furniture-baseline`
  guard, the only thing that catches corruption being learned as furniture, is opt-in with no
  saved baseline in the repo. `research/16` §9.1.1.
- **This harness costs about two runs per result.** Four of Task 6's runs failed to reach gameplay,
  three of them consecutively; each had written a full set of convincing screenshots first. Budget
  for it when planning, and never skip the liveness check.
- **An instrument that emits zero rows is a failed run, not a quiet one.** Task 6's idle-ms trace
  logged nothing for a whole session because it pointed at `0x30be80` while the guest calls the
  thunk at `0x30cd80` — inside the very task that wrote the warning about checks attesting to
  nothing.
- **A parked opponent starves a *stuck* mover.** The movement scale is fed by received bytes, so
  when A is pinned on geometry and B is parked, A's own scale decays to 0.0 — 19 of 821 rows,
  all inside two windows where A moved 2.5 units. It forbids "stall against geometry while the
  target is parked", not long approaches as first written. Keeping both players moving removes it
  under either causal reading.
- **`respawn` is a ROUND END, not a kill, and an acceptance test must not call it PASS.** A round
  ends on its clock too, so a timeout longer than the round turns "the round ended" into a pass for
  a test whose acceptance is a kill — the same defect as the `MediusPlayerReport` one, one level
  down. `PASS` is now reserved for `health`; a bare `respawn` prints
  `ROUND-END (unattributed -- NOT a kill)` and exits non-zero.
- **An index into `PS2X_PEEK` is not a stable address.** The first health-arming path guarded on
  word 0 of the *health* item, so `--health-item 2 --health-word 2` checked `0000ff00` against the
  actor vtable, could never be true, and would have reported "health never moved" from an
  instrument that never read. Find the actor block by its **vtable**, then resolve offsets against
  that block's own address.
- **A `MediusPlayerReport` in the Medius log is NOT a round end.** It is a periodic client stats
  report: in `ours_task8_kill1` exactly one arrived, at T+156.7 s, with the two players 603 units
  apart, both still walking and no respawn in either position record — and the harness printed
  `RESULT PASS signal=server` for it. `KillWatch` now records it and never fires on it.
- **A finished `drive.py` kills the NEXT run's game.** Its cleanup runs
  `taskkill /F /IM socom2.exe`, so an earlier driver reaching its own end takes down whatever is
  running now: `run_t8probe2` died 66 s in, the log froze at 127 sampler rows, and `drive.py` went
  on screenshotting a dead game for another four minutes. Kill the previous driver, not just the
  game, before starting anything.
- **The liveness rule counts non-zero position rows, not DISTINCT ones**, so it passes while the
  player is in-game and not yet controllable. `ours_task8_kill3` lost its second mover exactly
  there: 161 in-game rows, movement scale 1.0, and the record moving **0.00** units across a
  forward hold, a turn and a second forward hold.
- ~~**The approach loop's distance is 2-D by construction**~~ **Superseded by `d75ff33`**, which reads
  the actor's own x/y/z and gates contact on 3-D range AND `|dy|`. Kept for the lesson it carried:
  "contact at 33 units" once meant a 45-unit height difference and no line of sight at all.
- **The online lobby flow reaches gameplay about 4 times in 10.** Task 7 fixed four harness
  defects and left `host_game`/`join_game` fixed-press navigation untouched. Budget for it.
- **Closure efficiency quoted per side double-counts the same gap** — kill2 recomputes to 107.6 %
  and 119.2 %, impossible for one mover. Use team-closed over team-walked (kill2 ≈ 58 %,
  kill1 ≈ 33 %). A mined corridor's path efficiency is an idealised upper bound, not a closure.
- **Camera+facing reconstruction under-reports separation by 25-47 units, consistently.** Measured
  on the committed sim, whose world has **no vertical dimension at all**, so the error is purely
  the orbit reconstruction: reported-best vs ground truth `converge` 40.3 vs 64.3, `route` 23.4 vs
  30.7, `caps` 157.6 vs 204.7 — the same failure the live match showed (believed 33, true 45-93 in
  3-D), reproduced offline. The actor's own x/y/z are at actor words 7/8/9 and are already peeked.
- **`sim_walk_to_b.py` is wall-clock-timed, so its per-scenario numbers vary run to run.** One
  reviewer run gave `maze` 29 steps/206 s against a report's 14/102, and `route` 30.7/58.2 %
  against 40.9/65.1 %. Read those tables as illustrative; do not tune against them as constants
  or a slow machine reads as a regression.
- **A stale number is more dangerous than a false sentence.** A false claim reads as something a
  reader can challenge; a superseded measurement carries no visible sign at all. This sprint's own
  retraction task quoted a retracted figure into a tracked document, and this list carried two
  contradictory generations of the same measurement for hours.
- **Striking a claim's headline leaves its consequences standing** — and the consequences are the
  half a skimming reader acts on. `HANDOFF`'s ground-height item had three live restatements of a
  frame whose headline had already been struck.
- **`PS2X_CALL_TRACE` logs the first 300 calls unconditionally, then 1-in-`EVERY`**
  (`callTraceShouldLog`: `n < 300u || (n % every) == 0u`). A short
  trace never reaches the sampling regime, so dividing its line count by `EVERY` over-states the
  rate — it made an 18-call, 0.6-second burst read as "about one a second for six minutes".
- **Existing research notes go unread unless they are put in the dispatch.** `research/11`
  (2026-09-07) named reCOM's `MP_MAJOR_GAME_STATE` and `CZNetGame` round valves — plausibly the
  round-state machine behind Frostfire and the structures behind a kill readout — and sat unused
  for six days while four agents worked the round-start blocker. Name the relevant notes in every
  dispatch, not only the obvious ones.
- **An ARMED instrument that reads nothing is not a quiet one.** The health watch fills only when
  some peeked block covers `actor+offset`, so a too-narrow `PS2X_PEEK` makes "health never moved"
  indistinguishable from "never read". The run now counts reads/misses per instance, prints them on
  the RESULT line, and fails when an armed watch read zero.
- **A test harness can manufacture a regression.** Twice in one hour the simulator failed in a way
  indistinguishable from a bug in the loop under test: two suites interleaved into one fixed-name
  temp log (`pkill` is a no-op in Git Bash, hidden by `2>/dev/null`), and the simulated world let
  back-steps and strafes pass through walls. Name temp files per process, and check the harness
  before the code under test.
- **Community absolute addresses are for PCSX2's memory layout, not ours.** Our counter table sits
  exactly 0x20 lower than the console's, so an address like `0x69xxxx` from a cheat or trainer is
  right in PCSX2 and wrong for us. Always resolve through a pointer (`*0x437ce8`, `*0x408c58`), and
  record which game build and region an address was found for.
- **A green run of a timing-dependent test is a sample, not a verdict.** The acceptance harness's
  simulator was reported passing and then failed 2 of 2 for the next person to run it. After the
  race fix it passes 4 of 5 full suites, with two genuine residual loop defects (players circling
  just outside contact range; an oscillation when the only same-height ground lies away from the
  target), parked into Sprint 5's engagement ladder. Report pass counts over repeated solo runs.
- **A default threshold can manufacture a pass — and fixing the default was not the fix.**
  `--health-range` defaulted to `-0.5:0.5`, counting a player on 40 % health as dead. Changing it to
  `-1e9:0.0` did **not** close the false PASS: the check still fired on the *first* value read, so
  an uninitialised read of `0.0` or of heap fill `0xAFAFAFAF` (≈ −3.2e-10) counted as a death. The
  real fix (`42447e5`) counts a death only as an alive-then-dead **transition** on the same actor
  address, locked by `tools_py/tests/test_kill_watch.py`, which fails against the pre-fix code.
  **Residual, parked into Sprint 5:** an actor freed back to heap fill after a genuine alive read
  still looks like a death on this one signal — which is why Sprint 5's acceptance requires three
  signals from different objects and processes. Audit the defaults *and* the first-read behaviour
  of any instrument that can declare success.
  **Two further residuals, also parked into Sprint 5**, both erring toward a false FAIL rather than a
  false PASS: a read that is neither alive nor dead (NaN, 5000.0) between a real alive read and a
  real death clears the alive state and suppresses that kill; and a respawn that re-points the actor
  address at the moment of death also misses it.
- **A count that matches is not a mechanism.** Three-calls/three-axes, and the `+8 px` bar that
  never tested ±1 px, both looked like evidence and were not.
