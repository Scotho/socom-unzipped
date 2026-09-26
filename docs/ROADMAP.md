# SOCOM Unzipped — roadmap (rewritten 2026-09-22)

This file was a Sprint 4 report (2026-09-12) with supersession blockquotes layered on it through Sprint 7's close-out
(`df65444`, 2026-09-18). It was never updated for Sprints 8, 9 or 10, and `docs/HANDOFF.md:215` had already been
reduced to telling readers *"`docs/ROADMAP.md` is a Sprint 4-7 document: read its §3 and §7, not its sprint lists."*
That document is kept verbatim at **`docs/archive/ROADMAP-sprint-4-to-sprint-7.md`**, because fifteen files reference
it and several cite it by section — **every `ROADMAP.md §N` reference written before 2026-09-22 means the archived
copy**. This rewrite keeps the same §1–§7 skeleton so the shape of those citations still reads true.

**What this file is for.** The narrative layer: how the project got here, which beliefs were overturned and by what,
and what the shape of the next work is. It deliberately does **not** duplicate live state — a duplicated list is one
that goes stale, which is exactly what happened here. The live documents are `docs/STATUS.md` (Current state),
`docs/KNOWN.md` (proven vs believed, audited after every task, **it wins on any disagreement**),
`docs/CURRENT_SPRINT.md` (what is being worked, and the road to the next tag) and `docs/HUMAN_TASKS.md` (the owner's).
*(Superseded 2026-09-25, Sprint 13 R2: this said "the road to `v0.10.0`", a tag cut on 2026-09-23 -- documents audit
row 46.)*

---

## 0. The audit that produced this rewrite (2026-09-22)

Every checkable claim in the archived roadmap, verified against the tree. Twenty-five rows: **nine still hold, two
were plainly wrong, the rest were overtaken.** The two wrong ones are the interesting result — one had been wrong
since 2026-09-20 and was load-bearing for anybody reading the document as instructions.

### Still true, verified

| Claim | Evidence checked 2026-09-22 |
|---|---|
| `--vram-diff` at **15/15** | `checked=15 skipped=0` on the 2026-09-21 clean-clone run (`065bdcc`) |
| VU1 dispatcher **162/166 native**, a 4-program documented residual, `0x66` never dispatched from `0x1b50` in the corpus | `vu/native/socom2_dispatch_0x1b50.cpp:32`, `:318`, `:331` |
| `sceInetInterfaceControl` code `0x200` answers a live RX-byte counter | `socom2_libnetb.cpp:466-469`, behind `netStatsEnabled()`; `PS2X_SOCOM2_NET_STATS` covered in `knobs_tests.cpp:140` |
| Our IOP module hardcodes link-up, which is why the "cable disconnected" monitor can never fire | `ps2xIOP/src/modules/eznetcnf.cpp:132-133` (`reply[2]=1`, `reply[3]=3`) |
| §3.8's **"still open and unowned: the EE soft-double chain"** (`exp` LUT at `0x451090` garbage from entry 2) | `docs/audits/2026-09-17-audit-and-code-review.md` §3: *"6 exact-oracle math, HLE leg 3 — not started"*; still listed in `STATUS.md:474` and `:550`. **Two sprints on, still nobody's** |
| "The transition residual strip is a refresh/clear ordering artefact" — *believed* | `KNOWN.md` §2, "The transition residual strip", unchanged: *"No isolation test has been run"* |
| "The intro-cinematic freeze is a real defect" — *believed* | `KNOWN.md` §2, "The intro-cinematic freeze", unchanged: *"Not reproduced since"* |
| §7's rule that **`KNOWN.md` is the live checklist and wins** | Still the project's practice, and still the right instruction |
| Every commit hash cited (`abf35bb`, `5ed29ca`, `db7a992`, `4114ad4`, `b625291`, `ebf13be`, `8281254`) and every path (`tools_py/parity/gate.py`, `.../online_match_ours.py`, `dist/vu1_replay.exe`, `D:/socom_archive`, research notes 12–22 by number) | All resolve |

### Wrong, not merely stale

| Claim | What is actually true |
|---|---|
| §5: *"Reorder the standing goals. `LOOP_PROMPT.md` still lists native render (goal 3) … The speed freeze (goal 2) stays."* | **`LOOP_PROMPT.md` has no goals.** It was rewritten on 2026-09-20 to carry no state at all — its own words: *"This file therefore carries **no state at all**: no sprint, no goal, no number."* It is now seven process steps. An agent following §5's instruction would have gone looking for a numbered list that does not exist, in the one file every loop iteration opens first |
| §2/§5: *"`PS2X_*` is past 80 entries with revert layers that never retire"* | A registry of every name, **counted in the generated `docs/KNOBS.md`'s first lines** (150 on 2026-09-22, the day of this audit -- the count is KNOBS'; this row held it as if live until 2026-09-25, by which day KNOBS read 152), with one accessor, developer-mode gating, and `test_knobs_registry.py` failing on a stale row, an unregistered read or a row nothing reads. Retirement is no longer a wish: Sprint 10 Q2/Goal 3 classified all of them, deleted five dead knobs and two ghosts, and proved a poisoned environment inert (`s9_g3_gating_gate`) |

### Overtaken by Sprints 5–10

| Claim | Now |
|---|---|
| "428 tests then, **434** now" | **764** C++ and **1723** Python, measured 2026-09-21 from a genuine `git clone`. (The newcomer doc's own row said `500` until the same day — three sprints of cases after it stopped being true) |
| "Title and menus at 59 fps; Albania 5-1 at **36–42 fps**" | Mission **43–45 fps** after the CLUT-serial fix; lobby **52 → 57** and the login screen **58–60 under a four-core host load** after the texture-cache root fix (`759e218`, R123/R125) |
| "Online, the local player cannot move" — the whole spine of the document | Fixed `abf35bb`, A/B-proven `5ed29ca`, 2026-09-12 |
| §4: "the acceptance test … **Not reached**" | **Passed 2026-09-13** (ladder launch 2, rounds 1–3 KILL on two independent scorers) and since made repeatable — the scheduled ladder's streak is `docs/LADDER.md`'s (it read **4 of 7** when this row was written on 2026-09-22 and **7 of 7** by 2026-09-25; this row carried the 4 as if live until then -- documents audit row 45) |
| §2: *"The online harness is the weakest instrument in the project … the loop lock has no reaper"* | A heartbeat reaper landed in Sprint 5 Task 0; scorers are pure and under tests; the gate now **pins every input it scores against and refuses to score on drift** (Q1b, `s10_q1b_pins_gate`, `PINS MATCH` / `PINS DRIFTED`); the ladder is a scheduled job with a ledger (`docs/LADDER.md`) |
| §6 Sprint 6 items 10–12 (replay cost, display-env A/B, VU aliasing) | Dropped, not deferred — as the archived file's own note says (`docs/audits/2026-09-17-audit-and-code-review.md` §3) |
| §6 Sprint 6 item 6 (exact-oracle math) and item 8 (HLE audit leg 3) | **Never started.** They are the only Sprint 6 items still owed, and they are carried in §6 below |
| §6 Sprint 6 item 5a, the Seeding Chaos grey water shards | **Fixed** 2026-09-16/17 — VU1 chunk truncation, closed by the VIF wait plus the brighten/exposure HLEs (`3d37abc`, `545b85a`, `c63729d`, research/31 §15–17), not by the `0x34` env-map theory the roadmap carried |
| §6 Sprint 6 item 3, single-player teleports: *"a PCSX2 run of the same `rx`-hold script first, then trace the root-motion accumulate"* | **Fixed 2026-09-15 (`a81eb74`), and not by that route.** Our `sceGsExecLoadImage`/`StoreImage` HLE multiplied the BITBLTBUF block pointer by 8, so the motion-pack restore wrote `[6,5,6,5,6]` over chunks 0–4. Another finding-A case, and another plan aimed at the wrong mechanism. Still owed: the live `rx`-hold teleport count |
| §6 "Sprint 7 — after the kill (outline)" | Closed 2026-09-18. **Sprints 8, 9 and 10 are absent from the archived document entirely** — the Linux client, the hosted server, the launcher, packaging, the public repository and the credential path all happened after its last edit. That gap is the single largest inaccuracy in it |

*Noted in passing, not a roadmap error:* `docs/research/35-*.md` does not exist — the research sequence runs 34, then 36.
Recorded 2026-09-25 (Sprint 13 Task R3): 35 was never written on this line. Sprint 8's voice plan promised it as
`35-voice-path.md` (Task 3 Step 3 of `docs/archive/sprints-7-12/2026-09-19-sprint-8-voice-headset.md`), and no
commit on any branch ever created that file. Two notes numbered 35 exist only on branches never merged here: `35-browser-recreation-scoping.md` on
`feat/web-map-viewer` (`6cddd16`, beside a second 36) and `35-android-apk-feasibility.md` on
`origin/claude/mobile-github-cc-test-n7wyt7` (`d2035cb`). The number stays vacant, and nothing is renumbered.

---

## 1. How we got here

Sprints 1–3 (2026-09-10 → 09-12) are described in the archived file and the summary stands: a testable project with a
pass/fail definition it had never had, host-space drawing, the VU1 command dispatcher decoded and taken to 162/166
native, an integer render scale, and two saved mistakes — a **vacuous transition gate** caught before it could bless a
window of runs, and a render-target-scale spike that returned **NO-GO** and prevented a black-screen refactor.

**Sprint 4 (09-12 → 09-13)** replaced the project's mental model of the online blocker with a measured one and named
the cause; §3 below keeps what that changed. **Sprint 5 (09-13)** reached the acceptance test. **Sprint 6 (09-15 →
09-17)** took the gate from "the mission loaded" to something that can see a failure screen and compare against the
console, fixed the water shards and the root decay, and swept the online maps. **Sprint 7 (09-17 → 09-18)** defended a
stranger's machine and made the lobby reliable. **Sprint 8 (09-18 → 09-19)** shipped the Linux client and stood up the
hosted Horizon server, with a real internet match on it. **Sprint 9 (09-19 → 09-20)** made failures explain
themselves, cut the portable download, and produced `playtest-1` — which the owner failed on the music, opening four
rounds of audio work. **Sprint 10 (09-20 → 09-23)** turned the repository public and hardened it, retired the knobs,
proved a stranger's clone-to-game path at 42 minutes, and ran eleven agent chunks in their own worktrees; the owner
played its portable build on 09-22. **Sprint 11 (09-23 → 09-25)** bounded the chat receive path a community moderator
reported, on the client and the server, rebuilt the community revision r0004 from PSRewired's package and played it
online on the project's server, and gave the bug pipeline its GitHub half. **Sprint 12 (09-24 → 09-25)**, run beside
it in a cloud session, gave the generated code 1,771 readable names, each with its provenance, without changing what
a player sees. Both merged to `main` on 09-25 (`v0.11.0`, `v0.12.0`). Which sprint is open now is
`docs/CURRENT_SPRINT.md`'s to say.
*(Superseded 2026-09-25, Sprint 13 R2: this paragraph ended at "Sprint 10 (09-20 → open)", two sprints behind --
documents audit row 46.)*

---

## 2. Where we are now

**Read `docs/STATUS.md`'s "Current state" block — it is kept current and this section is not a copy of it.** The
one-paragraph version, and it is deliberately the kind of sentence that does not go stale: the game boots, plays
single-player missions and plays online against another instance on a hosted server over the internet, on Windows and
Linux, from the player's own disc; the repository is public; and a stranger can clone it and reach a running game in
well under an hour. Which sprint is open, what is in flight and what the current numbers are belong to
`docs/CURRENT_SPRINT.md` and `docs/STATUS.md`. (This paragraph named a fix wave "in flight on `sprint-10`" until
2026-09-23; the wave had closed the day it was written. Live state in a narrative document rots on its own.)

What is *not* true and should not be claimed: that it is finished, that multiplayer is safe against a hostile peer
(see `SECURITY.md`, and the Sprint 11 r0004 spec's Goal A), or that the gate proves correctness. That last point is
the one §3 item below that has never stopped being true.

---

## 3. Findings that overturned assumptions

The archived §3's eleven findings are the record of Sprint 4 and should be read there. Three of them are durable and
belong in any roadmap; the rest are history now.

**A. Our HLE returns a constant where the guest expects a live value — the project's most productive defect class.**
Sprint 4 lined up three (`rand()` at 15 bits, `sceInetInterfaceControl(0x200)` at zero, five soft-double stubs
returning a stale register) and observed that each was invisible to the gate, each presented as a *game* bug, and each
fix was one function in our runtime. That prediction has kept paying: the texture-cache generation bump (R123), the
CLUT snapshot serial, the MPEG picture-count gate starving the PCM ring, the stereo VPK interleave, the scheduler
unwinding a `replaceFunction` wrap mid-open — all the same shape. **The audit it prescribed is still only two-thirds
done: legs one and two ran (research/20), leg three — reading the guest's consumer for each flagged row — never did.** *(Superseded 2026-09-25 by R265,
`docs/audits/2026-09-25-project-audit.md` §4: leg three is owned by Sprint 13 Task C2, with the throwing-stub census;
the plan's C2 row has its state.)*

**B. A check that can pass quietly is the recurring defect class on our side of the fence.** Sprint 4 found six.
Sprints 5–10 kept finding them: the mission gate scoring the intro cinematic, the console-spawn score riding inside a
PASS line so `grep FAIL` reddens a clean gate (`docs/HAZARDS.md` harness, the `grep FAIL` hazard), a ruling in prose that no test could fail so
`build.sh` quietly kept shipping `-O2` against R151, and a screenshot walk that changed pages at a moment no player
could produce. It is the first thing reviewers are told to attack and it should stay that way.

**C. The gate is a regression fence, not evidence of correctness.** The 15-bit `rand()` bug lived under green gates
for the project's whole life. The gate has since grown real teeth — mission-failure detection, a console-vs-ours
comparison, input pinning that refuses to score on drift — but the sentence still holds, and the **gameplay-state
correctness leg** the archived §5 asked for (root-node Y, a rand-derived field, MoveScale `+0x1368`, the heading
matrix, a teleport count, all against console numbers already on disk) is still the cheapest unbuilt instrument in
the project. *(Superseded 2026-09-25 by R265: the probe is declined as a gate leg -- the ladder, the twenty-map queue
and the online verdict are the correctness legs built instead -- and its one live number, the `rx`-hold teleport
count, is a `docs/BACKLOG.md` matter; `docs/backlog_ruled_out.txt` row `gameplay-state-probe`.)*

Two Sprint 4 rulings worth restating because they were right and are easy to drift back from: **prove the mechanism
before fixing** (it earned its keep every time it bit — the macroblocks were not the suspected mechanism, the water
shards were not the `0x34` theory, the depth-precision water theory died to one disconfirming run), and **decompiling
EE game logic is allowed for diagnosis, rewriting it natively is not**.

---

## 4. The acceptance test, honestly

**Passed 2026-09-13** — an automated two-instance online match driven to a kill, scored by two independent scorers on
different signals (`KNOWN.md` §1, "THE ACCEPTANCE TEST PASSED"; `logs/parity/s5_t5_ladder2`; evidence archived with hashes).

**Repeatability is the bar, and this document does not hold the number.** The bar is seven consecutive clean
scheduled-ladder runs; **the streak is in `docs/LADDER.md`**, which is generated from the run ledger and has never
been wrong, with the sprint's reading of it in `docs/CURRENT_SPRINT.md`. What is worth saying here, because it is
narrative rather than a number: the failures that break a streak have been lobby-stage, not gameplay-stage, which is
the good kind of remaining failure.

What a green ladder still does not prove: that a *stranger* can do it. Every online result so far is two instances on
one host -- two of ours, or one of ours against a console client in PCSX2 -- and no match between two machines has
been run. *(Superseded 2026-09-25, Sprint 13 R2: this said "or the owner's two machines"; the two-machine match has
never been run -- documents audit row 47, `docs/HUMAN_TASKS.md` O6.)* And a repeatability number says nothing about the security of the
path it exercises — see `SECURITY.md`.

---

## 5. How the plan should change

The archived §5's advice has mostly been taken. What is left, plus what this audit adds:

- **Superseded 2026-09-25 by R265 (`docs/audits/2026-09-25-project-audit.md` §4); the live list is `docs/BACKLOG.md`
  and the Sprint 13 plan's C2 row.** R265 owned leg three (Task C2), declined the gameplay-state probe as a gate leg,
  and declined the soft-double chain until a defect points at it. The three items as written:
  > **Finish the HLE audit's leg three.** Finding A says the remaining unexplained wrongness is probably this shape;
  > legs one and two produced the list and nobody has read the consumers. It is bounded by a list that already exists.
  > **Build the gameplay-state probe.** Finding C. Asked for on 2026-09-12, agreed on 2026-09-14, never built.
  > **Own the soft-double chain, or write down that we are not going to.** It has been "open and unowned" for ten days
  > across three sprints. Either is an acceptable answer; drifting is not.
- **New, from this audit: a document that tells agents what to do must be audited like code.** The archived roadmap
  sent readers to a numbered goal list in `LOOP_PROMPT.md` for two days after that list was deleted. `KNOWN.md` is
  audited after every task and stayed true; `ROADMAP.md` was audited by nobody and went two sprints and two wrong
  instructions past its usefulness. The cheap fix is the rule this rewrite adopts: **the roadmap carries narrative
  and pointers, never live state**, so there is less in it that *can* rot. The less cheap fix is the link-and-claim
  check Sprint 11 Goal 1 already wants — it should cover claims about the tree, not only paths.
- **Retire the archived §6 sprint lists rather than maintain them.** Sprint planning lives in
  `docs/CURRENT_SPRINT.md` and `docs/superpowers/specs/`. The roadmap duplicating it is what produced a Sprint 6 task
  list still being read as current in Sprint 10.

---

## 6. Where the work is planned

**The live answer is `docs/CURRENT_SPRINT.md`** — which sprint is open, what stands between here and the next tag,
and who owns each item. This section holds no queue and no task list, by this document's own rule.

> **Superseded 2026-09-23.** What stood here until the Sprint 10 close is kept as the worked example of why the rule
> exists: *"**Sprint 10 is open** on branch `sprint-10`. Its autonomous stack is done and on `main` in four slices;
> fix wave A (the owner's playtest notes) closed at **eight of eleven chunks** with two slices on `main` — W6 and
> W10 did not run, and W10 is explicitly to be **re-decided rather than executed** … `v0.10.0` waits on the sprint's
> close."* Within a day of being written it was wrong three ways: Sprint 10 closed, and W6 and W10 both **ran** —
> W10 was executed rather than re-decided, and it failed, which is what rewrote R237.

> Superseded 2026-09-25 (the Sprint 12 close): Sprint 11 ran and closed on 2026-09-25 (`v0.11.0`), and Sprint 12,
> "the readable image", closed the same day (`v0.12.0`); this paragraph is kept as the record of what was planned.
> The open sprint is always `docs/CURRENT_SPRINT.md`'s `branch:` line; this file holds no queue.
>
> *(The paragraph below was left outside this blockquote at the Sprint 12 close, so it read as current; it is quoted
> here verbatim -- Sprint 13 R2, 2026-09-25, documents audit row 48.)*
>
> **Sprint 11 is drafted, in two independent specs**, and its plan
> (`docs/superpowers/plans/2026-09-23-sprint-11.md`) is where its tasks actually live:
> - `specs/2026-09-20-sprint-11-release-hardening-design.md` — a public repository a stranger can trust: git and
>   releases, the history and disc-derived-bytes audit, the progress story, the bug pipeline, the PII gate, owner
>   decisions D1–D6.
> - `specs/2026-09-21-sprint-11-r0004-and-the-community-server-design.md` — r0004 and the community server. Its Goal A
>   (bounding the chat receive path a PSRewired moderator reported) is blocked on nothing and should run first; Goals
>   B–D are provable without the r0004 package; E–G are blocked on the owner's memory card and on PSRewired.

**The standing backlog no sprint owns** lives in `docs/CURRENT_SPRINT.md`, under "Standing backlog, carried from the
roadmap 2026-09-23" — its eight items were written here until that date, which was a task list in a narrative
document and is the very thing §5 above says to retire.

---

## 7. What is proven and what is still believed

**`docs/KNOWN.md` is the live checklist.** It names the artefact for every proven entry and the experiment that would
settle every believed one, and it is audited after every task. **Read it first; where it and any other document
disagree, KNOWN wins.** The archived roadmap's §7 is a 2026-09-12 snapshot and is wrong in both directions — it is
kept there for the narrative only, under a blockquote saying exactly that.

The one thing this file adds to KNOWN: **the difference between the two documents is itself the finding.** KNOWN was
audited after every task and stayed true for ten days across six sprints. The roadmap was audited by nobody, and by
the time anyone checked it was instructing readers to reorder goals in a file that no longer has any. When a document
is written to be followed, either give it an audit cadence or give it nothing that can go out of date.
