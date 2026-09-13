# What we know, what we believe, and what we got wrong

A living list, audited after every task. Entries are **promoted** (believed → proven) when an
artefact settles them, **retired** when they stop mattering, and **retracted** loudly when they
turn out false. Every proven entry names the artefact that proves it; every believed entry names
the experiment that would settle it. If an entry cannot do that, it does not belong here.

Maintained by whoever is running the loop. Last audited: 2026-09-12, after Task 8 closed (Sprint 4).

---

## 1. Proven — with the artefact

| What | Artefact |
|---|---|
| PCSX2 plays a full online round against **our own** Horizon server, advancing to round 2 | `research/18` §1 + tracked contact sheet `docs/research/assets/18-s0-evidence.png` |
| A playing match and a frozen one produce **byte-identical** DME TCP profiles (11 BROADCAST / 30 SINGLE / 7 TOSERVER / 2 aux-UDP, same opcode histograms) | `research/18` §1; recounted from the raw log by review |
| The peer channel carries **zero** application data all match — every datagram decoded | `research/18` §3 |
| The advertised-port and shared-RSA divergences were real, and their fixes reached the wire | `acb603e`; wire bytes `4C-0E` both slots, distinct keys verified by `(m^17)^d mod N == m` |
| Neither of those fixes moved the symptom | Same runs; 3 hypotheses now falsified by measurement |
| The player's **feet** are at the right height (−145.875 vs console −145.8672); the defect is the **camera** | `research/17` §0.1, derived from STATUS:809's own numbers |
| The skeleton root node decays 11.4845 → 0 while its saved copy freezes at the console's 5.50391 | `research/17` §4.1, raw trace `run_20260912_121304.log:3962-6975` |
| `rand()` returned 15 bits over a `_rand_next` frozen at 41 (host CRT's first draw) | `ede2096`; `_rand_next = 0x29` in four of our RDRAM images, live in all three PCSX2 images |
| The disputed mover field could not exceed 4.0000458 under the old mask; console reads 6.3338 | `research/17` §6; two samples a side |
| Five soft-double stubs were bound with the wrong ABI, and were **identity** at 19 of 22 sites (the 3 garbage sites are unreachable) | `db7a992`; delay-slot analysis of every call site |
| The intro-movie macroblocks were a cross-thread race on `m_currentTransfer`, not a byte-accumulator bug | `4a701f1`; deficit 3,748 → 0, MISSING 9 → 0 |
| `--vram-diff` catches a uniform ±1 px shift again after the seam budget (8/15 x, 6/15 y) | `6c017c2`, measured on real renders |
| **One player walking to the other cannot finish inside a round.** Measured closure efficiency is 39 % (758 units gained for 1961 walked) at ~15 s/step, so 1382 units needs ~450 s against a ~360 s round. Two movers is ~700 units each, ~180 s | Task 7 run `wtb2`, `logs/run_A_20260912_211009.log`; arithmetic checked by review |
| **The player actor is at `*0x408c58`** — verified in five of our RDRAM images, the PCSX2 console image, and live online. `HANDOFF.md`'s `*0x488de8+0xbc` is wrong | Task 8, `9c28fe0` |
| **The two-instance approach closes faster than one:** 1359 units in 127 s against Task 7's 758 in 300 s. Rifles fire — 96 R1 injections, ammo 30/30 → 0/30, impacts on the wall ahead of the muzzle | Task 8 run `ours_task8_kill2` (A 1171 rows, B 1055) |
| **They fought at ~90 units, not in contact.** Median 3-D separation over the last 400 rows was 93 (min 34.9, max 138); only 3 % of rows were inside the 45-unit engage threshold in 3-D and **0 %** inside 20. Median elevation 29-44°; the quoted 77° was the single worst row. Range and elevation are co-equal causes | Review of `9c28fe0`, re-derived from both logs and two position sources across ±116 alignment offsets |
| **Open-loop aim resolution is floored at ~20-40°** because `PAD_AXIS` injects only full deflection (0/255); the shortest usable hold already sweeps 35-40°. A body at contact range subtends 15-20° | Task 7 §3.13; 19 timed holds, repeat scatter 99.5 vs 80.8 at the same hold length |
| **The local player's actor is reachable from a STATIC**: `*0x408c58` (also `0x40d744`, `0x440c38`, and `*0x415ff0+0xbc`). HANDOFF's `*0x488de8+0xbc` is **not** the route | Offline scan of five of our RDRAM images **and the PCSX2 console image** for vtable `0x6691a0` keeping the actor whose mover is `0x6694b0`; live in an online match (`logs/run_A_20260912_230022.log`, actor `0x17941d0`, word 0 `006691a0`, 804 rows). `research/18` §4.1. `*0x488de8+0xbc*` resolved 24 times in 1162 rows and to `0xd9d9d9d9` |
| **Two movers plus the mined corridor close the map**: 1392 → **33.0 units** in 23 steps and ~127 s, both players walking, first time two online players have met | `ours_task8_kill2`, `logs/run_A_20260912_231341.log` / `run_B_…` (1172 in-game rows each); `research/18` §4.8. Approach efficiency 57.5 % / 64.7 % against Task 7's 38.6 % |
| **The bursts at contact hit nothing because the two players were stacked, not beside each other**: minimum 2-D separation **10.1** units, minimum 3-D **34.9**, vertical separation **−54.5 to −34.9 (mean −44.8)** over the last 400 rows — 77° of elevation at 10 units of range, and the sweep covered yaw only | Same run, the two instances' position rows aligned row-for-row; `actor+0x204`/`+0x208` unchanged on **both** instances for all 1172 rows, so no damage was dealt either way |
| **The rifles DID fire** — this is a geometry failure, not an input one | `buttons=0800` (bit 11, R1) injected **96 times** in `logs/run_A_20260912_231341.log`; HUD ammo `A_fight04.png` 30/30 → `A_fight07.png` **0/30** with bullet impacts on the stone wall in front of the muzzle, `B_final.png` 13/30 1 MAG (~47 rounds fired) |
| **The online movement blocker was `sceInetInterfaceControl(0x200)` returning a constant** — `msSinceNetActivity` never reset, so the movement scale clamped to 0.0 on frame one. Pitch is not among the three scaled axes, which is why RY survived | `abf35bb`; `DAT_0045a1ca` measured 1 (killing the rival candidate), `MoveScale f12 = 1.0` on all 332/331 calls, instance A 73 distinct x (539.7→337.9) against 1 before, B 80. **Same-binary A/B** (`5ed29ca`, one match, both legs a frame apart): fix ON f12 = 1.0 on 330/330, idle max 1490 ms, activity globals 192/192 distinct, 89 distinct x; fix OFF f12 = 0.0 on 339/339, idle 504,210 ms, globals never written, **0.46 units** of travel. Movement tracks the stick — 1.3 units at neutral vs 28-38 per hold, starting on the hold frame, axes orthogonal. Review verified every figure to 3 dp |

## 2. Believed, unconfirmed — with the experiment that would settle it

| What | What would settle it |
|---|---|
| `actor+0x204` (1.0) and `actor+0x208` (100000.0) are the player's health and max health. They read the same in every RDRAM image, in the PCSX2 console image and in an online match | Watch them across **two separate kills** — the brief's rule, and this task got zero. `--until-kill --health-item 2 --health-word 2` arms the watch once they are confirmed; unset, the run says the signal is off |
| Which of `I`/`K` (right stick up/down) raises the muzzle | One timed pitch hold measured against the elevation of a target of known height difference. The engagement sweeps both ways precisely because this is unknown |
| Whether a parked opponent starving the mover matches **console** behaviour, or is an artefact of feeding the counter from RX bytes only (the game's own source may be richer) | A PCSX2 pair with one player parked and the other walking, same `actor+0x1368` measurement |
| Which of the two skeleton candidates is real — a lerp dropping its `a·w` term, or a second writer | `research/17` §4.3: read the node on return from the blend and again later in the same frame |
| The transition residual strip (~1 in 5 runs) is a `refreshDirtyRows`/`executeClear` ordering artefact | No isolation test has been run; the *pre-existing on both binaries* half is measured |
| The intro-cinematic freeze (seen once, Sprint 1) is a real defect | Not reproduced since |
| The DME aux-UDP channel carries nothing at round start | Rate bound only; `PS2X_SOCOM2_NET_TRACE_ALL` now closes it |
| `sin`/`cos` have no live call sites | Direct-`jal` count only; `0x001D55B8`/`0x001D55BC` hold their addresses in a probable dispatch table |

## 3. Retracted — believed, then killed by measurement

- **"The PCSX2 golden match is the same frozen state"** (`HANDOFF.md:42`). False. That golden was two
  stills of a match with **no input ever sent**. Weeks of server- and protocol-directed reasoning
  were aimed at the wrong body of code.
- **"The actor rests 14.7 above the ground vs the console's 20.1"** (`HANDOFF.md:99`, `STATUS.md:809`).
  Both numbers are camera-eye minus collision-hit. The player's feet are right to 0.008.
- **`HANDOFF.md`'s player actor at `*0x488de8+0xbc`.** Wrong; it is `*0x408c58`, verified across
  six images including the console's.
- **"Frozen at STARTING ROUND 1 OF 11, waiting for a go"** (spec §1 and several STATUS entries).
  The banner is transient on ours too and the round timer runs. The true sentence is *the round
  runs and the local player cannot move*.
- **The `cVar7 == 0` axis-clearing arm is the movement gate** (`4114ad4`'s commit message). Rejected:
  the routine is a generic axis setter, its guard cannot fire because our own IOP module hardcodes
  link-up, and the arm returns before all four axes are written — so pitch would have died too.
  Three calls matching three dead axes was a coincidence.
- **The mover's `4.0` vs `6.3338` is a capsule radius.** It was the 15-bit `rand`.
- **`PS2X_GS_SCALE=2` will sharpen the HUD** (Sprint 3 spec DoD). It cannot: HUD, menus and title
  are textured quads at native texel density. The design doc said so before anyone measured it.

> Retract **on discovery**, not at close-out. All of §3's first three were still false in the tree
> hours after being disproved.

## 4. Standing hazards — things that will bite again

- **The gate proves regression only.** It was blind to the 15-bit `rand`, the skeleton decay and the
  soft-double chain. A green gate means "no worse than the reference", never "correct".
- **Our HLE returning a constant where the guest expects a live value** — three for three this
  sprint (`rand` over a frozen seed; `0x200` never advancing; stale-register math returns). Presume
  remaining gameplay wrongness is this shape until shown otherwise.
- **The title gate passes at 16 of 23.** A pillarboxed run scores 18 — a pass with margin. The crop
  fixed silent score degradation and left the geometry itself unchecked. Assert the client rect.
- **The online harness can produce complete, convincing evidence of nothing.** One run drove sixteen
  stick probes and wrote sixteen screenshots against a lobby keyboard. **Verify `peek @416054` is
  non-zero before believing any movement claim from it.** Three of six runs were unusable.
- **`build.sh test` runs zero Python tests.** `test_compare.py`, `test_pine.py` and `test_winshot.py`
  are pytest-style and have never executed. `movie_blocks.py` has no tests at all.
- **Nothing reaps the loop lock** when an agent exits without releasing it, and `loop_lock.sh take`
  is a non-atomic test-then-write.
- **Task reports live in gitignored `.superpowers/sdd/`** and die with the workspace. Anything
  durable must be copied into a tracked doc before close-out.
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
- **The approach loop's distance is 2-D by construction** (the camera→player reconstruction is a
  ground-plane rotation), so "contact at 33 units" can mean a 45-unit height difference and no line
  of sight at all. Read `dy` before believing a range.
- **The online lobby flow reaches gameplay about 4 times in 10.** Task 7 fixed four harness
  defects and left `host_game`/`join_game` fixed-press navigation untouched. Budget for it.
- **Closure efficiency quoted per side double-counts the same gap** — kill2 recomputes to 107.6 %
  and 119.2 %, impossible for one mover. Use team-closed over team-walked (kill2 ≈ 58 %,
  kill1 ≈ 33 %). A mined corridor's path efficiency is an idealised upper bound, not a closure.
- **Camera+facing reconstruction mis-places a player by up to two orbit radii (~50 units).** The
  actor's own x/y/z are at actor words 7/8/9 and are already peeked — use them. A sim `converge`
  run reported best 16.1 against a simulated true 82.0 under the reconstruction.
- **`MediusPlayerReport` is a periodic stats report, not a round end.** Task 8's acceptance test
  printed `RESULT PASS signal=server` for a round that had not ended, until it caught itself. Any
  round-end signal must require something only a real round end produces.
- **A finished `drive.py` taskkills the *next* run's game.** It voided one of Task 8's probes.
- **A count that matches is not a mechanism.** Three-calls/three-axes, and the `+8 px` bar that
  never tested ±1 px, both looked like evidence and were not.
