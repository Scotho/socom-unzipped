# SOCOM Unzipped — status and roadmap after Sprint 4 (2026-09-12)

Written for the project owner returning after four autonomous sprints. Sources: `docs/STATUS.md`,
`docs/HANDOFF.md`, the four sprint spec/plan pairs, research notes 12–18, the Sprint 4 ledger and
task reports (gitignored, will be deleted at close-out — everything durable from them is in here),
and the run logs on disk as of 17:00 local. Sprint 4 is **not finished**: its close-out task has not
run, its headline online task is one authorised diagnostic from closing, and branch `sprint-4` is
not yet merged into `develop`.

The short version: the renderer work of Sprints 1–3 is done and solid; Sprint 4 fixed every visible
render defect it set out to fix, made the gates unable to pass quietly, and — the part that matters
most — replaced the project's whole mental model of the online blocker with a measured one. The
acceptance test (a two-instance online match driven to a first kill) is still not reached, but it
is now blocked by **one guest-side condition** that is being hunted with cheap single-process
instruments rather than 12-minute two-instance runs, and the search has narrowed by one layer per
run. Several beliefs the project carried for weeks were found to be wrong, and the plan below is
reordered around that.

---

## 1. Sprints 1–3, briefly

### Sprint 1 — hygiene and the first native VU1 program (2026-09-10 → 09-11)

Set out to make the project testable and to prove the N64-recomp pattern on the render path. It
delivered the project's own repo, a unit-test binary under the clang toolchain (428 tests then,
434 now), `dist/vu1_replay.exe --verify` (bit-exact replay of dumped VU1 programs against goldens,
registers and data memory included), one gate command (`python -m tools_py.parity.gate`: title /
transition / mission, PASS or FAIL, non-zero exit), and the first hand-written native VU1 program —
the `0x1b50` command dispatcher's family A (2D/UI) handlers, 76/76 lists bit-exact, on by default.
The two things that mattered: the project gained a **pass/fail definition** it had never had, and
research/12 established that the UI microcode's entry 0 is a trivial stub and the real drawing is
a command dispatcher — the finding every later VU1 task was built on.

### Sprint 2 — host-space drawing and the rest of the dispatcher (2026-09-11)

Set out to let native code draw at host resolution and to finish the dispatcher. It delivered
`GS::submitHostTriangle` and the `PS2X_VU1_HOST_DRAW` knob (default off), families B and C native
(123/166 lists), per-handler loop clamps proven by a synthetic overflow fixture, `--vram-diff` (an
offline oracle that renders each dump through both paths and diffs the VRAM), and gate hardening.
The two things that mattered: the **transition gate had been vacuous** for a whole window of runs
(a save dialog stalled the probe and the scorer counted boot black frames as the transition) and
was made to measure what it claimed; and the render-target-scale spike returned **NO-GO**, which
saved Sprint 3 from a black-screen refactor by forcing a size-field split first.

### Sprint 3 — render-target scale and the fourth VU1 family (2026-09-11 → 09-12)

Set out to add an integer render scale, decode and implement the last command family, and localise
the intro-movie black squares. It delivered `PS2X_GS_SCALE=1..4` (default 1) through a staged
refactor (37 read sites audited one by one), a GPU-resolved native mirror so everything the guest
reads back stays native, the fourth family's `0x70`/`0x40` and the `0x34` sphere-map handler
(**162/166 native**; the 4-program residual is a documented ruling — `0x66` is never dispatched
from `0x1b50` anywhere in the corpus, so a handler could not be verified), `--vram-diff` coverage
for family C and the fourth family (14/14), and research/16 proving the movie decode is clean and
the block loss is in the shadow-VRAM → GL mirror. The two things that mattered: **the spec's
"sharper HUD" expectation was wrong** — 2× sharpens rasterised geometry only (3D-region gradient
5.88 → 3.98, anti-aliasing fraction 0.13 → 0.42) and cannot touch the HUD, menus or title, which are
textured quads at native texel density; and **presentation was proved inert** at the shipped
640×448 window, so the softness people see is render resolution, full stop.

---

## 2. Where we are now

### What plays

Title and menus at 59 fps; Albania 5-1 at 36–42 fps with scripted walk/fire/turn and the game
reacting (squad, objectives, help popups); the full online path — login, universe, persona, lobby,
create/join, briefing — on a local Horizon server with two instances of our exe, into gameplay
with HUD and a running round timer. **Online, the local player cannot move** (LX/LY/RX ignored;
camera pitch, fire and stance work). That is the one blocker between here and the acceptance test.

### What the test and gate infrastructure can prove, and what it cannot

- `./build.sh test`: 434/434 unit tests; VU1 fixtures bit-exact on both paths; `--vram-diff`
  **15/15** (prog_182 rejoined at 0.000 % after Sprint 4 recalibrated the buckets — and a uniform
  one-pixel offset now fails again, 8/15 in x, 6/15 in y, after the review caught the first
  widening making the oracle blind to exactly that). Deterministic across repeated runs.
- The parity gate: title / transition / mission, last full run `s4_abi` PASS 3/3 on the newest
  binary (db7a992), title captures 99.6–100.0 run-vs-run. Sprint 4 closed three ways it could pass
  without measuring anything: a window resized from outside degraded the title score *smoothly* to
  the pass floor (now cropped to content: 0/23 → 18/23 on a deliberately pillarboxed run); the
  transition burst was pinned to a step index while the dialog it waits for moves (now `ifburst`
  follows the dialog, and a run with no conditional burst FAILs outright); and the new
  `movie_blocks.py` check went through four review rounds because each version could pass harder as
  the bug got worse (now monotonic, arrangement-invariant, per-screen, loud by construction).
- **What the gates do not prove:** gameplay correctness. The 15-bit `rand()` bug lived under green
  gates for the project's whole life; the soft-double ABI fix changed nothing the gate observes.
  "PASS 3/3" means the title labels, a black transition and the mission HUD look like last time.
  It says nothing about physics, animation, AI or networking. Treat it as a regression fence, not
  as evidence of correctness.
- The online harness (`online_match_ours.py`) is the weakest instrument in the project: three of
  six two-instance runs in Sprint 4 were unusable, one of them ran all sixteen stick probes and
  wrote sixteen screenshots against a lobby keyboard, and screenshots go stale mid-run. The only
  liveness signal is the `[peek] @416054` row count (~210 non-zero rows = a real gameplay window).
  The loop lock has no reaper; one orphan was cleared by hand.

### Native render path

162/166 dispatcher lists native, bit-exact; `PS2X_GS_SCALE` shipped and verified at 2× on both
draw paths; host-draw behind a knob. `PS2X_GS_SCALE=3..4` untested (67 MB targets). No visible
render defect is open: the macroblocks are fixed at the root (see §3), the menu-video strip was
fixed in an earlier session, and the transition residual strip is a ~1-in-5 one-frame flake with an
**unproven** attribution to `refreshDirtyRows`/`executeClear` ordering.

### Sprint 4 so far (branch `sprint-4`, 22 commits on top of the plan)

Complete and reviewed: Tasks 1 (macroblocks), 2 and 2b (gate trust), 3 (vram-diff calibration),
4 (ground height — research only, by design), 4b (rand), 4c (soft-double ABI stubs), 5 (S0, the
PCSX2 experiment). In flight: Task 6 (S1) on its last authorised diagnostic; uncommitted in the tree
are research/18 review edits and a one-line `PS2X_SOCOM2_NET_TRACE_ALL` parsing fix in
`socom2_libnetb.cpp`. Not run: Tasks 7 and 8 (movement calibration, kill detection — gated on S1
by design) and Task 9 (close-out). The close-out carries a list of **required retractions** in
STATUS/HANDOFF (§3 below); if Sprint 4 closes without Task 9, they become Sprint 5's first task.

---

## 3. What the results change — findings that overturn earlier assumptions

This is the section the plan below is built on. Each item says what was believed, what was
measured, and what it means.

**1. The console reference does not freeze — our runtime does.** HANDOFF said "the PCSX2 golden
match is the same frozen state". S0 ran two PCSX2 instances against *our* Horizon stack: the
"STARTING ROUND 1 OF 11" banner is a 6-second transient, all eight analog directions plus fire work
on both clients, and both advanced to round 2 in lockstep. The "golden" that motivated the belief
was two stills of a match with no input ever sent. **Consequence:** the server and the protocol
above it are exonerated for this bug; the defect is in our guest-side execution. That also gives
us, for the first time, a working reference recipe for two PCSX2 clients (research/18 §1, ~40 min
end to end) — and therefore the possibility of a *mixed* match, ours against PCSX2, which no one
has run yet.

**2. The symptom was misdescribed for two weeks.** "Frozen at the round-start banner waiting for a
go" is wrong twice: the banner is transient on ours too, and the round timer runs (05:25 one minute
in). The correct sentence is **the round runs and the local player cannot move.** Every plan that
looked for a missing "go" packet was aimed at a symptom that does not exist.

**3. The two oldest network hypotheses are dead — by fixing them.** Both S0 divergences were real
and were fixed in S1: instance B advertised its internal peer port as 3658 instead of 3660 (the
`UDP_SHIFT` only shifted the host bind, never the guest's config object — now patched the way the
PCSX2 pnach does it), and both instances published the same RSA key (now instance-selectable).
Verified on the wire at byte level. **Neither moved the symptom.** Keep both fixes; stop citing
either theory.

**4. The server log cannot see this bug.** Over the full join→end window, a *playing* PCSX2 pair
and a *frozen* ours pair produce byte-profile-identical DME TCP logs (11 broadcast / 30 single /
7 to-server / 2 aux-UDP each, identical opcode histograms). Every earlier server-log comparison in
this project was uninformative. The discriminator is the peer UDP channel and guest state.
(Proven for DME TCP only; the DME log has zero UDP lines.)

**5. The peer channel is healthy and carries no application data, and the inbound side looks like
a playing match.** Every one of ~300 peer datagrams per instance over a 10-minute match was decoded:
SCE-RT control and clock-sync only, zero player-state updates. But the inbound DME records — spawn
broadcasts, player records — arrive exactly as they do on the playing PCSX2 pair. So "the game has
nothing to say" and "the game receives the enabling record and mishandles it" are both still live.

**6. The gate is one layer below where we looked, and the search is now cheap.** Task 6's
extension measured, not argued: the player-update guard in `FUN_00551ec0` is entered online at the
same per-player rate as single player (~14/s); the multiplayer-only snap-back in `FUN_00594cf0`
never fires (timestamp difference max 0.000 over 602 samples against a 0.6 threshold); the actor's
stored position is simply never advanced. The controller's input method (`FUN_00566940`,
`controller->vtbl[0x8c]`) **returns 0 on every one of 719 logged calls online**, and its return is
the value that selects a multiplayer-only "zero the three input axes" arm. Move 2 (re-run on the
soft-double-fixed build) reproduced the symptom unchanged, so the trig fix is not sufficient. The
single-player half of that comparison (`logs/s4_task6_ctl.sh`, tracing `controller+0x170`, whose
low two bits are what `FUN_00566940` tests) **is the run in flight right now**. If it returns 1 in
single player, the missing half of the condition is named and the next step is the writer of those
two bits. This is proven up to `FUN_00566940`; the `+0x170` reading is still a hypothesis.

**7. "Ground height" was never the ground.** The 14.7-vs-20.1 number quoted for weeks is the
**camera eye** minus the collision hit; the player's feet are correct to 0.008 units. The whole
divergence is one value: the SEAL skeleton's root-node Y, 5.504 on the console and exactly 0 on
ours, which flips the camera into the engine's own "no root node" fallback. A live trace shows the
node decaying from bind pose through the console's value to 0 along a clean `saved × (1 − w)` curve
while the saved copy holds 5.50391. Two candidates remain (the VU0 macro-mode lerp `FUN_001c0768`
dropping a term, or a correct blend followed by a second writer) and research/17 §4.3 gives the one
run that separates them. It hits all four SEALs and all twenty override handles, so the AI aim
point and the stance test are wrong too. **Believed, not proven:** which candidate. HANDOFF:99 and
STATUS:809 still describe this wrongly.

**8. Two libc stubs were wrong, one of them everywhere.** `rand()` returned 15 bits where the guest
scales by 2⁻³¹ at 249 sites, so **every random draw in the game was pinned within 1/65536 of its
minimum** — enemy behaviour, spread, timers, the lot. Fixed by running newlib's own LCG over the
guest's `_rand_next`; the disputed field moved from 4.000021 (at a 4.0000458 arithmetic ceiling) to
5.53 against the console's 6.33. Side effect: **the RNG is no longer reproducible run to run**
(seeded from the host clock), which the gate absorbs but any future A/B must account for; a fixed
`sceCdReadClock` knob pins the seed, not the stream. The five soft-double ABI stubs
(sin/cos/tan/fabs/floor read `$f12` where the guest passes `$a0`) were also fixed, but the review
showed the old behaviour had degenerated to *identity* at 19 of 22 live sites — a latent defect,
less severe than rand. **Still open and unowned:** the EE soft-double chain itself is broken (the
`exp` LUT at 0x451090 is garbage from entry 2; `1/(exp(1)−1)` reads 0.034 vs 0.58), which is a
64-bit integer recompilation defect, not a stub, and it feeds the movement throttle curve.

**9. The macroblocks were not the suspected mechanism.** research/16's candidate 1 (partial
delivery) accounted for zero of the 3,748-block deficit. The real cause was a cross-thread race on
`m_currentTransfer` between the game thread and the render thread; the fix is one deleted line, and
the deficit went to 0 with the stored capture reproduced exactly. Lesson the ledger records twice:
a plan that says "prove the mechanism, then fix" earns its keep when the mechanism is wrong.

**10. A check that can pass quietly is the project's recurring defect class.** Sprint 4 found it in
the title gate (resize), the transition gate (pinned burst), `movie_blocks.py` (three separate
silent-pass paths over four review rounds), `--vram-diff` (blind to ±1 px after the first
widening), the online harness (probes against a lobby keyboard), and the loop lock (no reaper).
It is now the first thing reviewers are told to attack, and it should stay that way.

---

## 4. The acceptance test, honestly

The user's definition of playable: an automated two-instance online match driven to its end by one
player killing the other, with the kill read from guest memory or the server and both screens
captured. **Not reached.** What stands between here and there, in order:

1. **One guest-side condition** that keeps `FUN_00566940` returning 0 online (or something one layer
   below it). Each diagnostic so far has excluded a real candidate rather than wandered, and the
   remaining instruments are single-process. Cost to name: probably one to three more bounded runs.
   Cost to fix once named: unknown — it could be a one-line HLE/recomp defect (the pattern of every
   bug found this sprint) or a missing subsystem.
2. **Movement and aim** (S2): pad injection exists and is proven; steering A toward B from two
   position peeks needs a turn-rate calibration. Cheap once movement works.
3. **Kill detection** (S3): reading per-player health/kills near the actor. The server is useless
   for this (finding 4). **This can be researched in single player today** — find the health record
   by getting the player killed in Albania — and does not depend on item 1.
4. **A harness that can be believed**: liveness gating, stale-screenshot detection, lock hygiene.
   Without it, a green first-kill run cannot be trusted either.

Realistic reading: the first kill is one unknown away, and the unknown has been shrinking by a
layer per run. It is not close in the sense of "next run"; it is close in the sense that nothing
else is in the way.

---

## 5. How the plan should change

**Reorder the standing goals.** `LOOP_PROMPT.md` still lists native render (goal 3) as the thing to
advance and the acceptance test (goal 4) as "untouched". After Sprint 4 that is backwards. The
render path is at 162/166 with a documented residual, the scale knob is shipped, and no visible
render defect is open; further native VU1 work has diminishing value and no user-visible payoff.
The acceptance test is blocked by one condition with cheap instruments pointed at it. Proposed
order: (1) hygiene, unchanged; (2) **the online movement gate, then the acceptance test**;
(3) **gameplay-correctness defects found this sprint** (skeleton root decay, soft-double chain),
which are the same class of bug as the online one and probably share tooling; (4) render, as
maintenance only. The speed freeze (goal 2) stays.

**Retire "no decompilation of EE game logic" as a non-goal for the online work.** Every result in
S1 came from reading `FUN_0055…`/`FUN_0059…` alongside live traces. The non-goal was written when
the blocker was assumed to be network-shaped; it is not, and pretending otherwise slows the work.
Keep the ban on *rewriting* game logic natively — the fixes so far have all been HLE/recomp
correctness, which is exactly the N64-recomp model.

**Stop treating the online harness as evidence until it gates itself.** Screens are illustration.
A movement claim needs the peek row count, and a two-instance run that reports probes without
having reached gameplay is a harness bug, not a data point.

**Use the PCSX2 pair as a live reference, not just a verdict.** A mixed match (ours hosting, PCSX2
joining, and the reverse) is now one recipe away and answers two questions no ours-vs-ours run can:
does a working client see our player's state at all, and does our client apply a working client's
movement? That splits "local control never enabled" from "remote state never applied" in one run.

**Fold the correctness findings into the gate story.** The rand bug proves the gate is blind to
whole classes of wrongness. Sprint 5 should add at least one *gameplay-state* check — a
deterministic single-player probe that reads a handful of guest values (root-node Y, the throttle
constant, a rand-derived field) and compares them to console numbers already on disk. It is cheap
and it would have caught three of this sprint's findings on day one.

**Keep the per-task "prove the mechanism before fixing" rule, and the review-adversary rule.** They
cost rounds and they were right every time they bit (macroblocks, vram-diff blindness,
movie_blocks monotonicity, the ground-height retarget, the 4c severity).

---

## 6. Next sprints

### Sprint 5 — the movement gate, and the correctness bugs beside it (proposed in detail)

Theme: name and fix the one condition that stops the local player moving online, and clear the two
gameplay-correctness defects found on the way, with a harness that cannot attest to nothing.

**Task 0 — Sprint 4 carry-over (only if Task 9 did not run).** Merge `sprint-4`; commit the pending
research/18 edits and the `NET_TRACE_ALL` fix; apply the required retractions: HANDOFF:42 ("same
frozen state"), HANDOFF:99 and STATUS:809 (ground height → camera), every "frozen at the banner"
sentence, the 20:10 closing bullet; carry the ledger's durable findings into STATUS (4c's three
live divergence sites and latent severity, 4b's seed-not-stream caveat, Task 1's furniture-map
limitations, the harness liveness hazard). Half a day, and it is the difference between the next
model starting right and starting wrong.

**Task 1 — Harness you can believe (cheap, do first).** `online_match_ours.py` refuses to run the
probe phase, and prints a hard FAIL, unless both instances show non-zero `[peek] @416054` rows; it
detects a stale screenshot (identical bytes with a non-advancing HUD timer) and says so; it
releases the loop lock in a `finally`, and `loop_lock.sh` gains a reaper for a holder whose process
is gone. Unit-tested with the lobby-keyboard run's logs as the negative fixture. One day. Every
later task in this sprint depends on it.

**Task 2 — Name the gate (the headline).** Start from the live run: `controller+0x170 & 3` in
single player vs online. If it separates, trace the writer of those bits in both paths under
`PS2X_CALL_TRACE_DUMP` and name the condition sentence in full. If it does not, the next
instruments in order are: the inbound DME app-data handler (finding 5 says the enabling record may
*arrive* and be mishandled — trace the `0x04`/`0x0f` record consumers with the same tool); and the
**mixed match** (ours A + PCSX2 B, then PCSX2 A + ours B) to split local-enable from remote-apply.
Stop rule: a written condition sentence with both halves, or three excluded candidates with the
measurements. Budget three bounded runs before the controller re-plans.

**Task 3 — Fix it, if bounded.** One hypothesis, one build, the pad-injection probe on both
instances with the Task 1 liveness gate, `PS2X_PEEK` x changing during LX/LY holds on both sides.
Full gate. If the fix is not one bounded step, a research note saying why and Sprint 6 opens with
it.

**Task 4 — Skeleton root decay (research/17 §4.3, one run then a fix).** Dump `nodeArray[0]` on
return from `FUN_0028e040` and again at `FUN_0029a950` in the same frame. Wrong on return → audit
`FUN_001c0768` (VU0 macro-mode lerp) against the interpreter; correct on return → find the second
writer. Acceptance: root Y settles near 5.5, camera target height 15.38, gate green. This fixes the
last long-standing visible defect (camera 5.4 low), the AI aim point and the stance test — and the
"one bug not several" reading predicts the non-unit bone quaternions fix with it. Medium cost,
high value; independent of Task 2.

**Task 5 — The soft-double chain.** The `exp` LUT is wrong from entry 2 while the single-precision
tables from the same loop are bit-correct, so the defect is in the 64-bit integer recompilation of
`litodp → dpmul → dpdiv → exp → dptofp`. Bounded: unit-test each of the five against host `double`
on the LUT's inputs through `vu1_replay`-style harnessing of the recompiled functions, find the
first divergent one, fix the instruction pattern. It feeds `throt_exp` — the movement throttle
curve — so it plausibly matters for S2's calibration. Medium cost; do it after Task 2 unless Task 2
stalls, in which case it is the productive thing to do while waiting.

**Task 6 — Kill readout, in single player.** Find the player health/kills record near the actor
(vtable `0x6691a0`) by getting the player killed in Albania under `PS2X_TRIGGER` and a peek, and
commit a `--until-dead`-style reader. This is S3's guest-memory half and does not wait on the
online gate. One day.

**Task 7 — Determinism knob and gameplay-state probe.** `PS2X_CD_CLOCK=<fixed>` in
`sceCdReadClock` (seed only; documented as such), and a single-player probe that reads root-node Y,
the throttle constant and one rand-derived field at a fixed trigger and compares them to the console
numbers in research/17. Cheap, and it is the gate's first gameplay-correctness leg.

**Task 8 — Close-out**, with the same retraction discipline as Sprint 4.

Ordering rationale: Task 1 first because every measurement after it is otherwise suspect; Task 2
is the sprint's reason to exist and is cheap per iteration now; Tasks 4–7 are independent of
Task 2 and fill the loop lock while Task 2's runs are in flight; Task 3 only if Task 2 lands.
Not in scope: native VU1, render scale, speed, widescreen, the transition residual strip (flake,
not a defect), the intro-cinematic freeze (seen once, never reproduced).

### Sprint 6 — the first kill (outline)

S2 and S3 proper: turn-rate calibration against the compass, position-driven steering from the two
peeks, fire-until-dead, both screens captured, the kill read from guest memory (Task 6's reader),
the whole thing one command with the liveness gate in front of it. Then the retractions of every
"playable" claim that predates it and a re-grade of the in-mission parity report. If Sprint 5's
Task 2 did not land, Sprint 6 *is* Task 2 with a mixed match and the inbound handler trace as its
first two tasks, and nothing else.

### Sprint 7 — after the kill (outline)

Lift the speed freeze for the two-instance case only (19–21 fps each is a test-rig problem until
the acceptance test exists; then it is a product problem). Knob retirement (`PS2X_*` is past 80
entries with revert layers that never retire; every knob without a test is a liability). The
portable package (M6). Optional: a second render-target scale pass if a stretched window becomes
the default (`integer` present filter, HUD texture upscaling — the only way the HUD gets sharper).
The 4-program VU1 residual stays closed unless a new dump set dispatches `0x66` from `0x1b50`.

---

## 7. What is proven and what is still believed (a checklist for the next model)

Proven by measurement, with the artefact named: PCSX2 plays on our server (research/18 §1, tracked
contact sheet); the peer channel carries zero app data (every datagram decoded); the port and RSA
divergences were real and their fixes reached the wire; the player-update guard runs online and
the snap-back never fires; `FUN_00566940` returns 0 online on all 719 calls, on the soft-double
build; the player's feet are at the right height and the root node decays to 0; rand was 15-bit;
the macroblock race is closed (deficit 0); the five ABI stubs were identity at 19 of 22 sites.

Believed, untested, and marked as such: that `controller+0x170 & 3` is the gate (run in flight);
which of the two skeleton candidates is real; that the transition residual strip is a
refresh/clear ordering artefact; that the intro-cinematic freeze is a real defect; the peer UDP
packet rate on a playing PCSX2 pair (never measured — no capture tool); that the DME aux-UDP
channel carries nothing (rate bound only, `NET_TRACE_ALL` now closes it); that a `0x66` handler
would be correct.

Known wrong in the committed docs until close-out fixes them: HANDOFF:42, HANDOFF:99, STATUS:809,
every "frozen at STARTING ROUND" description, and the Sprint 4 spec's own §1 last bullet.
