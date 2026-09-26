# Sprint 9, P4 — the launcher's small defects (Goal 9, part 2)

> **ARCHIVED 2026-09-25 -- a Sprint 9 plan; the sprint is closed and this is its record.**
> Moved here from `docs/superpowers/plans/` in Sprint 13 (Task R1, with the rest of Sprints 7-10's specs and
> plans); nothing below it was edited except citations that pointed at a path that has since moved. It is a
> record, not an instruction.

Written 2026-09-19 by the controller, at the head of P4. The item is `docs/CURRENT_SPRINT.md` P4; the design is the
Sprint 9 spec, "Goal 9 — the launcher finished, and the game window that follows it". This plan exists because P4 is
five separate defects in one row and the loop's rule is that anything over an hour is planned before it is coded.

**Scope:** the launcher only (`third_party/ps2recomp/ps2xLauncher/`, `third_party/ps2recomp/ps2xTest/src/launcher_tests.cpp`).
No runtime change, so no gate is owed — `./build.sh test` and the launcher build are the bar. `main.cpp` is a file other
launcher sessions edit: `git status` it before every stage.

**Not in this item:** the guide-button toggle (Q4, needs a per-platform measurement), the mouse removal (Q3, after Goal
3's developer mode), the game window's styling (Q4), the profile viewer (Q4, and it is the owner's question).

---

## Task 1 — the one-frame flash at the top left (the owner's "weird graphical bug")

**Root cause, found by reading and stated before any fix was written.** The frame's node list is computed once, from the
page that was current at the top of the frame:

- `main.cpp:1010` — `const std::vector<ui::Node> nodes = ui::layoutFor(nav.page, window, app.layout);`
- the page then changes during input, below that line: `main.cpp:1149-1173` (the pad's and keyboard's `nav.move`,
  `nav.back`, and the shoulder tabs' `nav.goTo`), and `main.cpp:517` (a rail entry clicked, which happens *inside* the
  draw).
- drawing starts at `main.cpp:1190`. `drawPage` (`:1194`) switches on the **new** `nav.page` and is handed the **old**
  page's nodes; `drawBar` (`:1195`, `:580`) looks up `barLaunchId(app.nav.page)` — the new page's id — in that old list.
- `rectOf` answers `Rect{}` for an id it does not hold (`ui/focus.cpp:211-217`). `Rect{}` is the origin with zero size.
  A zero-size rect fills nothing, but `textCenteredIn` on it puts its label at (0,0), which is the top left of the
  window, for exactly one frame. `ui/page_online.cpp:11` already records the same mechanism biting once before.

The suspicion recorded in the spec and the sprint row (`rectOf` returning the origin) is correct and is **half** of it:
the other half is the stale list that makes an unknown id reachable at all. Both are fixed, because the rail-click path
at `:517` changes the page in the middle of a draw and no ordering fix can reach it.

- [x] **Step 1 (RED).** In `launcher_tests.cpp`, a case that hands page A's node list and page B to a new pure
      `ui::nodesForFrame(...)` and asserts every returned node belongs to B and that `rectOf(result, barLaunchId(B))`
      is drawable. Watch it fail to compile/assert before writing the function.
- [x] **Step 2 (RED).** A case asserting `ui::drawable(Rect{})` is false, `ui::drawable(rectOf(nodes, "no.such.id"))`
      is false, and a real node's rect is drawable. Watch it fail.
- [x] **Step 3 (GREEN).** `ui::drawable(Rect)` in `theme.h` (pure); `ui::nodesForFrame` in `focus.h/.cpp` (pure);
      `main.cpp` calls `nodesForFrame` after input and before drawing.
- [x] **Step 4 (GREEN, defence in depth).** Every primitive and control in `widgets.cpp` that places ink from a rect
      returns early when the rect is not drawable. An unknown id then cannot produce a mark anywhere, whatever the
      caller does. This is the "fix the rect discipline at the root" the spec asks for — **not** a cleared frame.
- [x] **Step 5 (evidence).** `--shot-frames N` on the screenshot walk (default 3, unchanged). **`--shot-frames 2**,
      not 1 as this step first said: the page is set after the frame at count 0 is drawn, so 1 is the last frame of
      the OLD page and 2 is the first of the new one. Recipe in the commit message and in `docs/HANDOFF.md` §7.

## Task 2 — the two alignment defects (owner's screenshot)

Both are in the top bar, and both are asserted in the pure top-bar test rather than eyeballed, as the spec's bar says.
The arithmetic moves into `topBarPlaces` (`ui/chrome.h`), which is where the bar's other measured placements already
live and where the tests already reach.

1. **UNZIPPED sits lower than SOCOM II** (`main.cpp:443-446`). The two words are drawn at hard-coded tops — `y=10` at
   size 15, `y=12` at size 13 — and `text()`'s `at` is the top of the line box, so equal tops are *not* equal
   baselines. The baselines are what should line up (spec).
2. **RUNNING sits above its lamp** (`main.cpp:463-467`). `textCenteredIn` centres the *line box* in a bar-height rect,
   and the line box of an all-caps word has the font's whole ascent above the capitals and its descender space below.
   The ink therefore sits high of the geometric centre — which is exactly where the lamp is. Centre the **cap ink** on
   the lamp's centre instead.

- [x] **Step 1 (RED).** Extend `TopBarText` with the caller's measured cap-ink metrics and `TopBarPlaces` with
      `markSubY` and `statusY`; assert equal baselines and ink centred on `lamp.y`, with metrics that are deliberately
      asymmetric so a "both zero" implementation cannot pass. Watch it fail.
- [x] **Step 2 (GREEN).** The arithmetic in `topBarPlaces`; `ui::capInk(ctx, size, face)` in `widgets` to measure a
      capital's ink from the rasterised face; `main.cpp` draws both words at the computed y.
- [x] **Step 3.** The rail's big wordmark (`main.cpp:496-497`) is **stacked**, not side by side, with a rule between
      the two words — there are no shared baselines to be off. Checked, left alone, and said so here so the next reader
      does not re-check it.

## Task 3 — an ADVANCED section, with "Second instance on this machine" in it

`ui/page_online.cpp:82`. There is no advanced section in the launcher today, so this creates one. What else belongs in
it is "the pass's judgment, recorded as a ruling" (spec).

- [x] **Step 1 (RED).** A layout test: the advanced section's rows exist, the focus order reaches them last, and
      `online.second` is inside it.
- [x] **Step 2 (GREEN).** The section in `focus.cpp`'s ONLINE layout and in `page_online.cpp`.
- [x] **Step 3.** The ruling, numbered from `docs/CURRENT_SPRINT.md`: what went into ADVANCED and what did not.

## Task 4 — tooltips, "what is a profile?" first

- [x] **Step 1 (RED).** The help text is data, not drawing: a pure `ui::helpFor(id)` with a test that the ids that
      have help have it and that an id without help answers empty.
- [x] **Step 2 (GREEN).** The affordance and its drawing, through the existing theme and focus model (spec's bar:
      "every new string through the same theme and focus model as Sprint 8 Goal 9").
- [x] **Step 3.** The wording is the owner's to check — `docs/HUMAN_TASKS.md`, and it is already in the playtest script.

## What the plan did not predict (written 2026-09-20, after the fact)

1. **The spec's repro for the flash does not work, and the harness had to change first.** Capturing the first frame
   after a page change in `--screenshot` shows nothing, because the walk changed pages AFTER a frame was drawn --
   a moment no player can produce. The walk now changes them in the input phase; `--shot-frames 2` is the repro.
2. **The caret drew nothing** the first time: this backend culls by winding, and a wrongly-wound triangle emits no
   pixels and no error. The order `fillQuad` documents is the one to copy.
3. **`app.layout.advancedOpen` was first set inside the world-poll block**, which `--screenshot` skips entirely, so
   the ADVANCED capture drew a section marked "in use" over nothing. Derived state does not belong in that block.
4. **CI went red on a commit that touched no Python** -- a threaded simulation test flaking on the runner. It cost
   half an hour of suspicion; it is now a KNOWN hazard row so the next person does not pay it again.

## Close

`./build.sh test` exit 0 with the launcher suite green; a launcher build; the screenshot walk at `--shot-frames 1` and
at the default; commit per task with an explicit pathspec; push; CI. Then `docs/CURRENT_SPRINT.md`'s P4 row, a STATUS
entry, and any KNOWN row this touches.
