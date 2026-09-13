# SOCOM Unzipped — status and roadmap after Sprint 4 (2026-09-12)

Written for the project owner returning after four autonomous sprints. Sources: `docs/STATUS.md`,
`docs/HANDOFF.md`, the four sprint spec/plan pairs, research notes 12–18, the Sprint 4 ledger and
task reports (gitignored, will be deleted at close-out — everything durable from them is in here),
and the run logs on disk, revised the same evening after the online hunt reached its answer.
~~Sprint 4 is **not finished**: its close-out task has not run, its headline online task has a named
cause with one measurement run and one fix still to land, and branch `sprint-4` is not yet merged
into `develop`.~~

> **Superseded 2026-09-13 — the end of Sprint 4.** Sprint 4 is finished (close-out ran; a
> whole-branch review and one fix wave followed). The movement blocker named below was **fixed**
> (`abf35bb`) and **proven by a same-binary A/B in one match** (`5ed29ca`: fix ON, movement scale
> 1.0 on 330/330 calls and 89 distinct player positions; fix OFF, 0.0 on 339/339 and 0.46 units of
> travel) — on Medley. **No kill was reached**: the acceptance test ran end to end, closest true
> 3-D separation 50.0 units on Medley. **Frostfire, the default test map since 2026-09-13, is a
> second, open cause**: neither player moves after round start there. The live facts are in
> `docs/KNOWN.md`; the next sprint is
> `docs/superpowers/specs/2026-09-13-sprint-5-control-readout-and-first-kill-design.md`. The
> summary below is kept as written on 2026-09-12; its "predicted, not confirmed" and "one
> measurement run and one fix" no longer hold.

The short version: the renderer work of Sprints 1–3 is done and solid; Sprint 4 fixed every visible
render defect it set out to fix, made the gates unable to pass quietly, and — the part that matters
most — replaced the project's whole mental model of the online blocker with a measured one, and
then **named the cause**. The acceptance test (a two-instance online match driven to a first kill)
is still not reached, but what blocks it is no longer a hunt: it is a constant-returning stub in
*our* HLE of a PS2 network API, which pins the game's own network-activity movement scale at zero.
That reading is predicted from the disassembly and our source, not yet confirmed at runtime; one
measurement run and one fix stand between it and the first kill. Three of this sprint's bugs turn
out to share one shape — an HLE that hands the guest a constant where it expects a live value —
and the plan below is reordered around that as much as around the fix itself.

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
camera pitch, fire and stance work). That is the one blocker between here and the acceptance test,
and as of this evening it has a named cause (§3.6): our `sceInetInterfaceControl(0x200)` returns a
constant, so the game's network-activity timestamp never resets and the multiplayer movement scale
it drives sits at 0.0. ~~Predicted, not yet measured; a candidate fix is drafted in the working tree.~~

> **Superseded 2026-09-13.** Measured and fixed: the `0x200` fix landed (`abf35bb`) and a
> same-binary A/B proved it (`5ed29ca`) on Medley, where both players now move and met at 50.0
> units without a kill. On **Frostfire neither player moves** after round start — a second, open
> cause (Sprint 5). The last full gate is PASS 3/3 at `logs/parity/gate/20260912_192900` on the
> binary Sprint 4 ends on, title s00–s19 99.8–100.0 run-vs-run against `s3_head_1x`; the `s4_abi`
> figures below are from the earlier run.

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

### ~~Sprint 4 so far (branch `sprint-4`, 22 commits on top of the plan)~~ Sprint 4 at its end

> **Superseded 2026-09-13.** Every task ran: 1–9 plus 2b, 4b and 4c, each reviewed. Task 6's fix
> landed on a third, separately authorised attempt (`abf35bb`) and was A/B-proven (`5ed29ca`);
> Tasks 7 and 8 ran and are honest partials (calibration works; two movers closed Medley to 50.0
> units; no kill; Frostfire loses control at round start); Task 9 closed out, and the required
> retractions below were made in the tree. The outcome, task by task, is the Sprint 4 plan's
> `## Outcome`; STATUS's 2026-09-13 entry is the dated record. The paragraph below is the
> 2026-09-12 snapshot: its "drafted fix … unbuilt", "Not run: Tasks 7 and 8" and "Uncommitted in
> the tree" are all stale.

Complete and reviewed: Tasks 1 (macroblocks), 2 and 2b (gate trust), 3 (vram-diff calibration),
4 (ground height — research only, by design), 4b (rand), 4c (soft-double ABI stubs), 5 (S0, the
PCSX2 experiment). Task 6 (S1) has its cause named but not confirmed: commit `4114ad4` ("the gate
is named") describes a candidate that the gate-naming review then **rejected** — its message is
now a retraction target — and the review found the real cause in the same function (§3.6). The
ruling on the table is one measurement run, then the fix. Uncommitted in the tree: research/18
edits (being brought in line with the review, concurrently), the `PS2X_SOCOM2_NET_TRACE_ALL`
parsing fix, and ~~the **drafted fix itself**~~ — `socom2_libnetb.cpp`'s `case 0x200` now answers a
host RX-byte counter from a new `socom2_hostnet::rxBytes()`, ~~unbuilt and unverified~~ (built,
committed as `abf35bb` and A/B-proven by `5ed29ca`). Not run:
Tasks 7 and 8 (movement calibration, kill detection — gated on S1 by design) and Task 9
(close-out). The close-out carries a list of **required retractions** in STATUS/HANDOFF (§3
below); if Sprint 4 closes without Task 9, they become Sprint 5's first task.

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

**6. The movement blocker has a cause, and it is ours.** Task 6's extension measured, not argued:
the player-update guard in `FUN_00551ec0` is entered online at the same per-player rate as single
player (~14/s); the multiplayer-only snap-back in `FUN_00594cf0` never fires (timestamp difference
max 0.000 over 602 samples against a 0.6 threshold); the actor's stored position is simply never
advanced; and Move 2 (re-run on the soft-double-fixed build) reproduced the symptom unchanged, so
the trig fix is not sufficient. The single-player half of the controller comparison then closed
the line this report was written on: `FUN_00566940` returns 0 in **both** paths (374+345 calls
online, 305 in single player) — it means "a scripted auto-move consumed this frame", 0 is normal,
and "why is it 0 online" was the wrong question.

*The rejected candidate, recorded so nobody re-finds it:* commit `4114ad4` named `FUN_00594cf0`'s
`cVar7 == 0` arm, which calls a routine three times with axis indices 0/1/2 — three calls, three
dead axes, pitch surviving. The review rejected it on three counts. `0x00567340` is a *generic* axis
setter (`*(float*)(this + 8 + 4*idx) = f12`) used in the same clear-0,1,2 idiom in about twelve
places, not a multiplayer clearer. Its guard `DAT_0045a1ca` is initialised to 1 and its only writer
is the "network cable is disconnected" monitor, which cannot fire because **our own IOP module
hardcodes link-up** (`ps2xIOP/src/modules/eznetcnf.cpp` fno 3 replies `reply[2]=1, reply[3]=3`).
And the arm returns *before* `FUN_005966a0`, which writes all four axes — if it fired, camera pitch
would be dead too. The count match was a coincidence.

*The real cause, three lines earlier in the same function, unconditional in multiplayer:*
`FUN_00594cf0` calls `FUN_00553dc0(scale, actor)` → `actor+0x1368` every online frame. `FUN_00551ec0`
copies `actor[0x8f/0x90/0x91] = ctrl[4]/[2]/[3]` and multiplies **exactly those three** by
`actor[0x4da]` (= `+0x1368`), gated on `ctrl->vtbl[0x2c]` = `0x005431f0` = `jr ra; li v0,1`, always
true. Pitch is never copied through there — it lives in `ctrl[0x4c]` — which is why RY survives:
the asymmetry, properly explained. The scale is `clamp((5000 − (msSinceNetActivity − 1500)) × 0.001,
0.0, 1.0)` (constants at `0x650640`/`0x650648`): full movement while the network has been heard
from in the last 1.5 s, holding at full until idle exceeds 5500 ms and reaching zero at 6500 ms
— the console's own lag freeze.
`msSinceNetActivity` resets only when libnetb's `sceInetInterfaceControl(code 0x200)` returns a
**changing** word, and ours returned a constant (`socom2_libnetb.cpp`, `sceInetInterfaceControl`'s
`case 0x200: r(3, 0u)` as of 2026-09-12 — replaced by a live RX-byte counter in `abf35bb`; with
`DAT_00458090` BSS-zero). The bypass, `FUN_003045b0(0x44fe10)` = `"ComeFromLan"`, is false
for a Medius match. So the scale pins at 0.0 from the first frame, every movement input is
multiplied by nothing, the camera still works, and `hud+0xde=1`. Guest-side, ours-only, the exact
symptom — **and the defect is in our HLE of a PS2 network API, not in the game.**

> **Superseded 2026-09-13: confirmed and fixed.** The fix landed as `abf35bb` (code `0x200`
> returns `socom2_hostnet::rxBytes()`; `PS2X_SOCOM2_NET_STATS=0` restores the constant) and was
> proven by a same-binary A/B in one match, `5ed29ca`: fix ON, `MoveScale f12 = 1.0` on 330/330
> calls and 89 distinct player x; fix OFF, 0.0 on 339/339 and 0.46 units of travel
> (research/18 §3.12). Proven on Medley only; on Frostfire neither player moves, a separate open
> cause. The status paragraph below is the 2026-09-12 text.

~~**Status: predicted, not confirmed.**~~ The ruling was one measurement run first — `PS2X_PEEK=
0x45a1ca:1` and `0x45a1c0:1` plus `actor+0x1368`, prediction 1 and 0.0, stop if either reads
otherwise — then the fix: make code `0x200` return a real monotonic counter (host RX packets or
bytes) so the timestamp resets. That is a correctness fix at the right layer, and the opposite of
patching `FUN_00594cf0`, which would make the player move and teach us nothing. ~~A draft of the
fix is in the working tree, unbuilt.~~

**7. "Ground height" was never the ground.** The 14.7-vs-20.1 number quoted for weeks is the
**camera eye** minus the collision hit; the player's feet are correct to 0.008 units. The whole
divergence is one value: the SEAL skeleton's root-node Y, 5.504 on the console and exactly 0 on
ours, which flips the camera into the engine's own "no root node" fallback. A live trace shows the
node decaying from bind pose through the console's value to 0 along a clean `saved × (1 − w)` curve
while the saved copy holds 5.50391. Two candidates remain (the VU0 macro-mode lerp `FUN_001c0768`
dropping a term, or a correct blend followed by a second writer) and research/17 §4.3 gives the one
run that separates them. It hits all four SEALs and all twenty override handles, so the AI aim
point and the stance test are wrong too. **Believed, not proven:** which candidate. ~~HANDOFF and
STATUS still describe this wrongly.~~ **Retracted in the tree 2026-09-13 (Task 9a):** both now
carry a `> Superseded by …` blockquote in place, as does the Sprint 4 spec's own Task 4 bullet,
which had restated the wrong frame as fact.

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

**11. Three of this sprint's defects are one defect class: our HLE returns a constant, or a
wrong-shaped value, where the guest expects a live one.** This is the most valuable thing the
sprint found, and it is the finding the plan should be built on. Line them up:

| Stub | What we returned | What the guest expected | What it looked like |
|---|---|---|---|
| `rand()` | 15 bits over a `_rand_next` frozen at 41 | a 31-bit LCG that advances | every random draw pinned at its minimum: AI, spread, timers — "the game's numbers are a bit off" |
| `sceInetInterfaceControl(0x200)` | the constant 0 | an interface statistics word that changes with traffic | the local player cannot move online — "a missing go packet", for two weeks |
| `sin/cos/tan/fabs/floor` (soft-double) | `$f12`, a stale register that happened to hold the argument | the result of the function | identity at 19 of 22 live sites — "the animation blend is slightly wrong" |

Each one was **invisible to the gate** (the gate looks at pixels the title, transition and mission
HUD produce, and none of these move them), and each one **presented as a game bug** — a network
protocol problem, a physics problem, an animation problem — and absorbed research time aimed at
the game. Each was found only by reading the guest's consumer of the value alongside a trace, and
each fix was one function in our runtime. That is the N64-recomp pattern working as designed: the
recompiled code is right, and the hand-written surface around it is where the bugs live. The
consequence is that the remaining unexplained gameplay wrongness — the skeleton root decay, the
soft-double `exp` chain, whatever the first kill run turns up — should be presumed to be *this
shape until shown otherwise*, and the HLE surface should be audited for it deliberately rather
than one symptom at a time. §5 says what that audit should look like so that it is affordable;
Sprint 5 carries its first pass.

---

## 4. The acceptance test, honestly

> **Superseded 2026-09-13 in its ordering and its "realistic reading".** Item 1 (confirm and land
> the `0x200` fix) was done inside Sprint 4; item 2 (calibration) was done on Medley; the first kill
> was **not** reached (closest true 3-D separation 50.0 units), movement failed on Frostfire, and
> `PASS` cannot print until a health word is confirmed. The current distance to a kill, and the plan
> for it, is `docs/superpowers/specs/2026-09-13-sprint-5-control-readout-and-first-kill-design.md`
> §1 and §6. The text below is kept as written on 2026-09-12.

The user's definition of playable: an automated two-instance online match driven to its end by one
player killing the other, with the kill read from guest memory or the server and both screens
captured. **Not reached.** What stands between here and there, in order:

1. **Confirm the named cause, then land the fix.** The cause (§3.6) is one constant in our
   `sceInetInterfaceControl` HLE; the fix is to return a live counter, and it is drafted. What is
   *not* done: the runtime measurement that the prediction rests on (`DAT_0045a1ca` = 1,
   `actor+0x1368` = 0.0 online), a build, and a two-instance run showing the position peek moving
   under an LX hold on both sides. Cost: one measurement match and one fix match. If the peeks
   read otherwise, the story is wrong and the hunt reopens one layer down — but every prior
   candidate was excluded by measurement, and this one explains the surviving control, which none
   of them did. Confidence: high on the mechanism, unmeasured on the runtime values.
2. **Movement calibrated enough to steer** (S2): pad injection exists and is proven; steering A
   toward B from two position peeks needs a turn-rate calibration against the compass. Cheap once
   movement works — with one caveat: the scale that pins movement is *time-varying by design*
   (full until 5500 ms after the last network activity, gone at 6500 ms), so the calibration must be
   done with the counter feeding at match rate and the scale peeked at 1.0, or it will measure
   the lag freeze instead of the turn rate.
3. **Kill and round-end readout** (S3): per-player health/kills near the actor, and the round-end
   state, from guest memory. The server is useless for this (finding 4). **The health record can
   be found in single player today** — get the player killed in Albania under a peek — and does
   not depend on item 1. The round-end readout probably does (it is only reachable online).
4. **A harness that can be believed**: three of six two-instance runs this sprint were unusable and
   one of them produced sixteen convincing screenshots of a lobby keyboard. A green first-kill run
   from that harness is not evidence. It needs liveness gating on the peek row count, stale-
   screenshot detection, and lock hygiene *before* the kill run, not after.

Realistic reading: the first kill is no longer an unknown away. It is one confirmation, one fix,
and three pieces of bounded engineering away, all of which are named, and the least certain of
them is the confirmation. That is close in the sense of "this sprint", which no earlier report
could honestly say.

---

## 5. How the plan should change

> **Partly superseded 2026-09-13.** "Land the movement fix" is done (`abf35bb`, A/B `5ed29ca`), so
> goal (2) now reads: Frostfire control, the kill readout, then the acceptance test — in the order
> the Sprint 5 spec gives. The HLE audit and the rest of this section stand.

**Reorder the standing goals.** `LOOP_PROMPT.md` still lists native render (goal 3) as the thing to
advance and the acceptance test (goal 4) as "untouched". After Sprint 4 that is backwards. The
render path is at 162/166 with a documented residual, the scale knob is shipped, and no visible
render defect is open; further native VU1 work has diminishing value and no user-visible payoff.
The acceptance test is blocked by one named HLE defect with a drafted fix. Proposed order: (1)
hygiene, unchanged; (2) **land the movement fix, then the acceptance test**; (3) **the HLE
constant-return audit and the gameplay-correctness defects found this sprint** (skeleton root
decay, soft-double chain), which finding 11 says are probably the same class of bug and share
tooling; (4) render, as maintenance only. The speed freeze (goal 2) stays.

**Audit the HLE surface for constant-returning and wrong-width stubs — deliberately, and cheaply.**
Finding 11 is the argument; this is the shape. The surface is about twenty stub families under
`Kernel/Stubs/` (LibC, Pad, CD, SIF, RPC, MemoryCard, …) plus `socom2_libnetb`/`socom2_hostnet`
and the IOP modules — hundreds of return sites, far too many to read one by one, and most of them
*legitimately* constant (`sceInetInterfaceControl` code 8 answering "attached + up" is correct;
code `0x200` answering 0 is not). So the audit has to be mostly mechanical and only expensive
where it flags something. Three legs. **Static census (hours):** a script lists every HLE entry
that returns a literal, a stale register, or a value narrower than the ABI slot it fills, and a
human tags each as *constant by spec*, *constant by omission* or *wrong shape* — the tagging is
the whole cost, and it is bounded by the list. **Dynamic census (one day):** a trace mode that
logs `(entry, args, return)` for every HLE call over the two gameplay windows we already script
(Albania 5-1 and the online round), and a script that flags any entry called many times whose
return never changed while its arguments did, or whose return has bits set outside its declared
width. `0x200` would have been the first row. **Consumer reading (bounded to the flagged list):**
for each flag, read the guest's consumer the way Task 6 did, decide whether the constant matters,
and fix it in our runtime with a unit test asserting the value *moves* — the rand stream advances,
the statistics word changes with traffic, `sin(a0) ≠ a0`. Legs one and two fit in a day and fill
lock time; leg three is the productive backlog they produce. The point is not to find every bug
but to stop meeting this class one two-week symptom at a time.

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
movement? Before this evening that was the diagnostic that would have split "local control never
enabled" from "remote state never applied"; with the cause named it is not needed for the hunt,
and it becomes something better — the standing parity test for the online path once the fix
lands, and the fallback instrument if Sprint 5's Task 1 stop rule fires.

**Fold the correctness findings into the gate story.** The rand bug proves the gate is blind to
whole classes of wrongness, and the `0x200` stub lived under green gates for the project's whole
life. The project needs at least one *gameplay-state* check — a deterministic single-player probe
that reads a handful of guest values (root-node Y, the throttle constant, a rand-derived field,
and now the movement scale at `actor+0x1368`) and compares them to console numbers already on
disk. It is cheap and it would have caught three of this sprint's findings on day one. It is the
gate-side complement of the HLE audit above: the audit finds constants at the source, the probe
notices their effect.

**Keep the per-task "prove the mechanism before fixing" rule, and the review-adversary rule.** They
cost rounds and they were right every time they bit (macroblocks, vram-diff blindness,
movie_blocks monotonicity, the ground-height retarget, the 4c severity).

---

## 6. Next sprints

### Sprint 5 — control on the test map, a kill readout, and the first kill (revised 2026-09-13)

> **Superseded, in full, by `docs/superpowers/specs/2026-09-13-sprint-5-control-readout-and-first-kill-design.md`
> and its plan (`docs/superpowers/plans/2026-09-13-sprint-5-control-readout-and-first-kill.md`).**
> The Sprint 5 that stood here ("land the fix, reach the first kill") was written before Sprint 4's
> Task 8 finished, and the world it planned for ended the same night. Its Tasks 0–2 were done
> inside Sprint 4 (the retractions; the `0x200` cause measured; the fix landed with a same-binary
> A/B), its Task 5 was done on Medley with the pitch sweep since retired, and its Task 6 rested on
> "once the scale is 1.0 the players move", which is false on Frostfire, the owner's chosen map.
> It also did not know that the two-mover approach arrives but has never produced a contact row
> (minimum true 3-D separation 50.0, 0 % of rows in any gate), nor that `PASS` cannot print until a
> health word is confirmed. What still held — the harness gating itself, the single-player health
> search, the HLE audit's first two legs, measure-before-fix with a stop rule — is carried into the
> revision. The spec's §2 has the item-by-item judgement.

**The revised Sprint 5, in order** (each of 0–4 lands value on its own):

0. **Preconditions** (no build, no run): a heartbeat lock reaper that never reaps a live build or
   run; `build.sh test` running the Python tests; the loop prompt pointed at this sprint; a
   stale-driver kill script; a plan preflight.
1. **Frostfire control handover.** Zero-run first: an object-keyed heap diff and the `CZNetGame`
   valve map (`research/19` F2/F3), and a zero-fill guest-allocation knob built before any launch.
   Launch 1 peeks the round-state object, health/life and the clock and traces the move path
   upstream; if the uninitialised ghost flag `ng+0xd2` is set, launch 2 is the same-binary zero-fill
   A/B. Caps: 3 usable matches / 8 launches, then a mandatory map ruling — **Medley is the fallback**.
2. **Confirm the sourced kill readout** (`actor+0x1044` health, `+0xF7A` alive) in one single-player
   run, with partial-deflection yaw and pitch calibrations riding along.
3. **An online harness that cannot spend a match on an uncontrollable or hung player**: pure
   scorers under tests that `build.sh test` runs, the round state read from self-identifying valves.
4. **HLE and heap liveness audit** (leg zero before Task 1's launch; census and `PS2X_HLE_STATS`).
5. **Engagement ladder** — controllable → contact → damage — with partial-deflection aim and a
   cooperative endgame in which both players keep generating traffic (6 usable / 14 launches).
6. **The acceptance run**, attributed by signals from different objects and processes (the victim's
   actor fields, the killer's `total_mp_kills`, alive counts on both instances) and two scorers with
   different primary signals (4 usable / 10 launches).
7. **Close-out.**

**Realism.** A kill this sprint is roughly even odds — somewhat better since `research/19` turned the
health search into a confirmation. It hinges on Frostfire's handover being the uninitialised ghost
flag or otherwise bounded (or the Medley ruling being taken promptly), and on the engagement
reaching contact at matched height, which has never happened; the spec's §6 says why.

### Sprint 6 — the correctness bugs, the lobby, and whatever Sprint 5 left open (outline)

The HLE audit's leg three: consumer readings and fixes for Sprint 5's flagged list. The skeleton
root decay (research/17 §4.3: dump `nodeArray[0]` on return from `FUN_0028e040` and again at
`FUN_0029a950` in the same frame; wrong on return → the VU0 macro-mode lerp `FUN_001c0768`,
correct on return → a second writer; acceptance root Y ≈ 5.5, camera target 15.38) — the last
long-standing visible defect, the AI aim point and the stance test in one. The soft-double chain
(`litodp → dpmul → dpdiv → exp → dptofp`, unit-tested against host `double` on the LUT inputs, first
divergent function fixed). The gameplay-state probe as the gate's first correctness leg. The mixed
match (ours against PCSX2, both directions) as a standing parity test. **Moved here from Sprint 5:**
lobby fixed-press hardening (`host_game`/`join_game` verify-then-act — the 4-in-10 tax), the
remaining process-audit items (1 steps 1–3: client-rect and log-scan gate preconditions; 9:
`gate.py --baseline`; 11; 12: flake policy), and `movie_blocks.py` wiring. **Conditional on Sprint
5's outcome:** if Frostfire was not fixed inside Sprint 5's cap, Sprint 6 opens with a PCSX2
Frostfire pair (splits our runtime from the game/lobby configuration in one match) and the
condition research/21 reached; if `+0x1044` was not written by network damage, it opens with an online
object-keyed diff at contact; if no kill landed, the engagement
ladder resumes from the highest rung reached before anything else in this list.

### Sprint 7 — after the kill (outline)

Unchanged in intent, and still gated on the acceptance test existing: lift the speed freeze for the
two-instance case only (19–21 fps each is a test-rig problem until then, then a product problem);
repeatability of the acceptance test (N consecutive passes, lobby rate measured, run as a nightly
job) — **new**, because Sprint 5's bar is one run; knob retirement (`PS2X_*` is past 80 entries with
revert layers that never retire); the portable package (M6). Optional: a second render-target scale
pass if a stretched window becomes the default. The 4-program VU1 residual stays closed unless a
new dump set dispatches `0x66` from `0x1b50`.

---

## 7. What is proven and what is still believed (a checklist for the next model)

> **`docs/KNOWN.md` is the live copy of this checklist.** It is audited after every task —
> promoted, retired, retracted — and it names the artefact for every proven entry and the
> experiment that would settle every believed one. Read it first. What follows is this sprint's
> snapshot, kept for the narrative; **where the two disagree, KNOWN.md wins**, and a duplicated
> list is one that goes stale.

Proven by measurement, with the artefact named: PCSX2 plays on our server (research/18 §1, tracked
contact sheet); the peer channel carries zero app data (every datagram decoded); the port and RSA
divergences were real and their fixes reached the wire; the player-update guard runs online and
the snap-back never fires; `FUN_00566940` returns 0 on every logged call in **both** paths
(374+345 online, 305 single player) and is therefore not the discriminator; the symptom survives
the soft-double fix (Move 2); the `cVar7 == 0` arm cannot be the gate (generic setter, guard
unwritable under our IOP link-up hardcode, returns before the four-axis write — three static
reads, each sufficient); our `sceInetInterfaceControl(0x200)` returns the constant 0 (our own
source, `socom2_libnetb.cpp` `sceInetInterfaceControl` `case 0x200` as of 2026-09-12 — since
fixed, `abf35bb`); the guest resets its network-activity timestamp only on a
change of that word and `FUN_00551ec0` multiplies exactly the three movement axes by the scale
that timestamp drives (disassembly, cited to the instruction); the player's feet are at the right
height and the root node decays to 0; rand was 15-bit; the macroblock race is closed (deficit 0);
the five ABI stubs were identity at 19 of 22 sites.

> **Superseded 2026-09-13.** This checklist is the 2026-09-12 snapshot and is out of date in both
> directions: the movement fix it lists as believed is **proven** (same-binary A/B, `5ed29ca`, on
> Medley), and the end of Sprint 4 added open items it lacks (no kill; Frostfire loses control at
> round start; the health readout `actor+0x1044` / alive byte `actor+0xF7A` is sourced by
> research/19 and never read live online; `actor+0x204`/`+0x208` retracted). **Do not work from
> this list — `docs/KNOWN.md` is the live one.**

Believed, untested, and marked as such: ~~**that `DAT_0045a1ca` reads 1 and `actor+0x1368` reads
0.0 at runtime online** (the prediction; Sprint 5 Task 1); **that a changing `0x200` word makes
the local player move** (the fix; Task 2); that the counter's feed rate at match traffic keeps
the scale at 1.0 rather than sagging (Task 2's minute-long trace);~~ (settled by Sprint 4's A/B —
see KNOWN.md); which of the two skeleton
candidates is real; that the transition residual strip is a refresh/clear ordering artefact; that
the intro-cinematic freeze is a real defect; the peer UDP packet rate on a playing PCSX2 pair
(never measured — no capture tool); that the DME aux-UDP channel carries nothing (rate bound only,
`NET_TRACE_ALL` now closes it); that a `0x66` handler would be correct; that the remaining
gameplay wrongness is mostly the finding-11 shape (a bet, which the audit prices).

Retired this evening: "`controller+0x170 & 3` is the gate" (it is the auto-move flag, 0 in both
paths); "the `cVar7 == 0` arm zeroes the three axes online" (`4114ad4`, rejected on review);
"the missing half of the condition is one writer away" (there was no condition to complete).

~~Known wrong in the committed docs until close-out fixes them: HANDOFF's open items 0 and 2, the 2026-09-09 01:30 STATUS entry,
every "frozen at STARTING ROUND" description, the Sprint 4 spec's own §1 last bullet, and the
gate claim in `4114ad4`'s commit message (research/18 is being corrected concurrently).~~
**Done 2026-09-13:** close-out (Task 9a/9b) and the final fix wave marked those superseded in
place; a commit message cannot be edited, so `4114ad4`'s gate claim stands retracted in research/18
§3.11 and `docs/KNOWN.md`.
