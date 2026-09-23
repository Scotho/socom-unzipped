# Sprint 10 close — the road to `v0.10.0`, run autonomously (2026-09-22 evening → 2026-09-23 morning)

**Mandate (the owner, 2026-09-22 ~22:10):** *"save the human tasks for later, agreed on the rest, and proceed with all
remaining sprint 10 work and finish sprint 10 with my authority and your best judgement. Once that's done, formalize
and begin sprint 11 autonomously … You have the computer for the next 12 hours and are free to use as many agents or
workflows as needed."* The owner is away; lock-bound work runs without the host-load rule. Owner-only items stay in
`docs/HUMAN_TASKS.md` and are **not** waited on.

**Spec:** `docs/superpowers/specs/2026-09-20-sprint-10-console-players-and-it-stays-up-design.md`; the road-to-`v0.10.0`
table in `docs/CURRENT_SPRINT.md` is the binding list. **Ledger:** `.superpowers/sdd/2026-09-22-sprint-10-close/progress.md`.

## Global constraints

- Every game run and every C++ build goes through `bash scripts/loop_lock.sh run <who> --purpose "..." -- <cmd>`.
  One thing on the lock at a time; agents' builds queue behind runs, never beside them.
- No agent runs the game. The controller pays every gate, round and ladder run in the main tree.
- Nothing connects to a server that is not ours (`SOCOM_SERVER_IP=3.143.65.100`).
- Commit only idle files; explicit pathspecs; the leak check on every commit (the hooks do it).
- `docs/DOC_MAINTENANCE.md` §5 is a gate on the close: the review runs, the stamp carries "Sprint 10", the
  close-out commit says what it changed. `python -m tools_py.docmaint` exit 0 is enforced by the suite.
- Ruling numbers come from `docs/HANDOFF.md` and that line is bumped in the same commit (tested).

## Tasks

1. **Fix wave A, the queued runs** — chain 1 (`logs/chain1_fixwave.result`): the endpoint A/B, W10 launches 1 and 2,
   the W7 walking capture, the W6 no-revalidate A/B. Then the follow-through each result dictates: W10 pass → remove
   the prefill from the player path (R237 as written; the two login fields and their `config.json` keys, the two
   knobs to Dev, `PS2X_DEV=1` on the drive scripts that use `--prefilled`); W10 fail → R237 rewritten, the prefill
   stays; W6 → read the popup frames from both runs; W7 → the music score against PCSX2; the A/B → the DEVICE-per-
   minute pin (`--max-device-per-minute`). **W8** runs as the two-instance self-join fallback (A `--host`, B `--join
   --channel N`) since the owner's channel line is parked. Lock-bound; the follow-through is code + Python tests.
2. **The ladder streak, 4 of 7 → 7 of 7** — `scripts/ladder_job.sh 4`, one at a time, each ~35 min; a LOBBY-FAIL or
   CRASH resets the streak and the failing class goes to the sprint record. Lock-bound.
3. **Goal 3, tasks 5 and 7** — the peer entity's position read in each guest ("seen by the other", task 7), then the
   parked-opponent row (task 5) as one run with PCSX2 parked. Two mixed-match runs on the hosted server. Lock-bound.
4. **Goal 4, scoped (R242)** — the two-instance speed freeze: re-measure from the ladder runs' `[vu1-stats]`
   `syncv/s` and `[gs-gl stats]` lines (no new run) and record the number. The per-map kill routes **carry to
   Sprint 11 as filler** — see the ruling below.
5. **Q2 Task 8, the VM ring** — `scripts/vm_sync.sh tree`, `build_linux.sh runtime` + `test` in the VM, the four
   knob-line cases on `dist-linux/socom2`. Lock-bound (the VM's 8 cores are the host's). **If the night runs short,
   carry with a ruling: CI already proves the library, the suites and the launcher on Linux (R209).**
6. **H7's two decisions** — the owner's; already Sprint 11 decision material. Carried, nothing moved.
7. **Q8, the close** — in this order: the KNOWN audit (every §1/§2 row this sprint touched: promote, retire, retract);
   STATUS's Current state rewritten and a dated Sprint 10 entry; the sprint's rulings R181–R24x reconciled into one
   list in CURRENT_SPRINT; the DOC_MAINTENANCE §5 review with its stamp; `PS2X_TEST_REPEAT=3 ./build.sh test`; a full
   gate on the close commit (`s10_close_gate`); the CURRENT_SPRINT close-out block; the PR `sprint-10 -> main` as a
   merge commit with that block as its body, required checks green; the annotated tag `v0.10.0` on the merge
   commit (the release-draft workflow makes a **draft**, never publishes); `sprint-10` left in place (the `sprint-*`
   ruleset forbids deletion, R182 — a HUMAN_TASKS line for the sweep). Lock-bound at the suite and the gate.
8. **Sprint 11 opened** — `sprint-11` off `main` at the merge; the plan written from the three inputs (the
   release-hardening spec, the r0004 spec, milestone U) with `superpowers:writing-plans`; CURRENT_SPRINT's header
   turned over; then execution begins per that plan.

## Rulings made on the owner's behalf (this plan's; numbered from HANDOFF)

- **R241 — the four external-repo items (upstream PR #244's real-IRX IOP, the cherry-pickable GS/VIF/SIF PRs, the
  SOCOM 1 demo symbols, the MrCoolTheCucumber fork) become Sprint 11 milestone U, early, not their own sprint.**
  Why: the owner's motive is the unresolved audio, the divergence audit gates two of the four, and Sprint 10 is
  closing tonight — nothing external lands on `sprint-10`. Item 1's step zero (the divergence audit) and the PR #244
  spike are assigned to session socom-pc-09 in worktree `wt-upstream` (branch `agent/upstream`, merged forward onto
  `sprint-11`); items 2–4 queue behind the audit, item 3 ahead of the r0004 matcher because the symbols feed it.
  Cost if wrong: the owner wanted it separate — a branch is cheap to re-home.
- **R242 — Goal 4's per-map kill routes carry to Sprint 11 as [A] filler; the speed-freeze half is re-measured from
  existing logs.** Why: "it stays up" is proven by the ladder streak on the map with a route, not by route coverage;
  the sweep already proved 20/20 maps play a control round (research/33); nineteen routes is days of runs against a
  twelve-hour night that also has to close the sprint and open the next. Cost if wrong: the owner wanted every map
  killable at the tag — the work is not lost, only later, and the tag says so.
- **R243 — milestone U item 1's step (b) is redefined as a differential test, not a music-parity number.** The
  divergence audit (socom-pc-09, `agent/upstream` 83c02d9, `docs/research/40-upstream-divergence.md`) established
  that upstream since our base `14b1e5c` is exactly one commit, PR #244, and that #244 has **no SPU2** — its
  `0x1F900000` range is a register bag, so the real 989SND.IRX would sequence correctly into silence and the brief's
  number is zero by construction. Step (b) becomes: build #244's `ps2xIOP` standalone, load the disc's own
  LIBSD/989SND/989DSTRM into it, feed them the RPC sequences `socom2_audio_tests.cpp` feeds our `snd989.cpp`, and
  count the answers where the real IRX and our model disagree. That count sizes "option B" (a native libsd provider
  on a voice-level model over our mixer's VAG decoder, est. 1,500–2,500 lines) as a Sprint 11 goal. Prerequisite for
  any #244 adoption, recorded for the plan: a prefer-HLE load policy — #244 loads physical IRXs first and would take
  the real LIBNETB/INET/DEV9/MCMAN over our network and card HLE. Cost if wrong: a day of the peer's time on a test
  whose count turns out uninformative — the table it produces is wanted regardless.
- **R244 — W8's fallback run is not run separately: the ladder streak proves the join driver's R240 path.** The
  ladder's joiner is `online_match_ours.py:4679` → `join_game(B.sh, …)` with REFRESH LIST on by default (the post-R240
  path; `--no-refresh` is the old one), against the hosted server's real lobby, so ladder runs 5–7 exercise exactly
  what W8's self-join would have, three times. The owner's channel line stays parked. Cost if wrong: the owner's
  lobby was on another channel and `--channel 2+` is unexercised (the driver says so) — one run when the line comes.
- Further rulings are appended here and in the ledger as they are made.

## Outcome

*(written at the close)*
