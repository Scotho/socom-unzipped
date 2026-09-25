# 64. The four "menu" captures: s19..s22 are the attract sequence, and the count bar hid a different loss

Date: 2026-09-25. Sprint 13 Task V1, issue #30 ("The title gate lost four menu captures (s19-s22 scoring 60-88) and
kept passing"). Read-only over the archived gate stamps (git-ignored, on the build machine) and the tree. Nothing was
built, launched or gated; no loop lock was taken. No byte of the game is in this note or in its test: the test's
images are generated gradients.

**The one-line answer: nothing was lost. `s19`..`s22` are not menu screens -- they are the game's idle attract
sequence (the menu fading to black, then the mission flyovers "KELLSKI EXPERIMENTAL AIR/SEACRAFT FACILITY, KAMCHATKA",
"ABANDONED TOOLWORKS, SHKODER", "SLUMS OF R..."), which starts about two minutes after the menu appears, and it has
sat on `s19`..`s22` since the first archived stamp (`native_on`, 2026-09-10); the gate's own calibration comment of
that day already said so. The issue's "before", `s8_audio_mc_gate2` (23/23), is one of fourteen outlier runs in which
the attract never started inside the window. There is no first fall, no reference change and no render change. The
issue's other half is real, though, and worse than it said: the `>= 16 of 23` bar had three captures of slack INSIDE
the menu, and `s7_cpu_fallback2` (2026-09-17) froze on the menu-over-black from `s16` and passed at 16/23. The scorer
is now positional: every capture in the menu window `s00`..`s18` must score >= 90; the tail is printed, not counted.**

## The commands

```
# A -- the tally over every archived stamp (both archive roots; ~2 min, D: is slow). Prints the counts in §1.
python - <<'EOF'
import glob, re, collections
roots = ["D:/socom_archive/parity/gate", "C:/projects/socom_pc/logs/parity/gate"]
rows = []
for r in roots:
    for f in glob.glob(r + "/*/summary.txt"):
        line = next((l for l in open(f, encoding="utf-8", errors="replace") if l.split(" ")[1:2] == ["title"]), "")
        sc = dict(re.findall(r"(s\d\d)=([\d.]+)", line))
        if len(sc) == 23:
            rows.append((f.replace("\\", "/").split("/")[-2], line.split()[0], {k: float(v) for k, v in sc.items()}))
cnt = collections.Counter(sum(v >= 90 for v in s.values()) for _, _, s in rows)
print(len(rows), "stamps;", sorted(cnt.items()))
flip = [n for n, v, s in rows if (v == "PASS") != (min(s["s%02d" % i] for i in range(19)) >= 90)]
print("verdicts the menu window changes:", flip)
print("lowest s18 on a PASS stamp other than those:", min((s["s18"], n) for n, v, s in rows if v == "PASS" and n not in flip))
EOF
#  -> 165 stamps; [(0, 19), (7, 1), (16, 1), (19, 123), (20, 6), (21, 1), (23, 14)]
#  -> verdicts the menu window changes: ['s7_cpu_fallback2']
#  -> lowest s18 on a PASS stamp other than those: (93.0, 's5_gsbp2c')
#  The appendix table is the same loop printing one row per stamp, sorted by the summary's mtime.

# B -- capture times: s19 lands 114.4-114.7 s after s00 on every stamp, whatever the boot took
python -c "import json; m=json.load(open('<stamp>/title/manifest.json')); print([(e['label'][:3], e['t']) for e in m])"
#  -> s8_audio_mc_gate2 s00=52.1 s19=166.6; s8_close_gate 21.3/135.9; s9_p7_playtest_gate 21.3/135.9;
#     s11_close_gate 35.6/150.3; s6_audio_title7 84.3/198.7; s9_crouch_gate 34.0/148.8

# C -- the reference and the title script are unchanged since the gate existed
git log --format='%h %ad %s' --date=short -- scripts/parity/ref_main_menu_ours.png scripts/parity/title_menu.txt
#  -> newest 87d6d201 2026-09-09 (title_menu.txt), d0caab98 2026-09-08 (the reference)
git log --format='%h %ad' --date=short -S "fade into the attract movie" -- tools_py/parity/gate.py
#  -> 3bc03bad 2026-09-10 (the calibration comment naming s19 the fade and s20..s22 the movie)

# D -- the side by side: the reference and s19..s22 of a stamp in one 1600x240 strip (a scratch file, viewed
#      as an image, not committed). Run from the repo root; STAMP is an archived title directory.
STAMP=D:/socom_archive/parity/gate/s9_p7_playtest_gate/title OUT=strip.png python - <<'EOF'
import os
from PIL import Image
d, W, H = os.environ["STAMP"], 320, 240
row = Image.new("RGB", (W * 5, H))
row.paste(Image.open("scripts/parity/ref_main_menu_ours.png").convert("RGB").resize((W, H)), (0, 0))
for i, n in enumerate(["s19", "s20", "s21", "s22"]):
    p = next(f for f in os.listdir(d) if f.startswith(n + "_"))
    row.paste(Image.open(os.path.join(d, p)).convert("RGB").resize((W, H)), (W * (i + 1), 0))
row.save(os.environ["OUT"])
EOF
#  run for s8_audio_mc_gate2, s8_close_gate, s9_p7_playtest_gate (under D:/socom_archive/parity/gate) and
#  s11_close_gate (under C:/projects/socom_pc/logs/parity/gate); §2 describes the four strips

# G -- the per-root split, the menu-window margin, the literal Step 2 rule, the tail freezes, the groupings
python - <<'EOF'
import glob, re
roots = ["D:/socom_archive/parity/gate", "C:/projects/socom_pc/logs/parity/gate"]
rows = []
for r in roots:
    for f in glob.glob(r + "/*/summary.txt"):
        line = next((l for l in open(f, encoding="utf-8", errors="replace") if l.split(" ")[1:2] == ["title"]), "")
        sc = dict(re.findall(r"(s\d\d)=([\d.]+)", line))
        if len(sc) == 23:
            rows.append((r, f.replace("\\", "/").split("/")[-2], line.split()[0], {k: float(v) for k, v in sc.items()}))
print("per root:", {r: sum(1 for x in rows if x[0] == r) for r in roots})
win = lambda s: [s["s%02d" % i] for i in range(19)]
good = [(n, s) for _, n, v, s in rows if min(win(s)) >= 90]
print("window-clean stamps:", len(good), "lowest window capture:", sorted((min(win(s)), n) for n, s in good)[:5])
lit = [n for n, s in good if any(s["s%02d" % (i - 1)] >= 90 and s["s%02d" % i] < 90 for i in range(1, 23))]
print("literal rule (predecessor >= 90, capture < 90, any of s01..s22) refuses", len(lit), "of", len(good), "window-clean stamps")
tail = lambda s: [s["s%02d" % i] for i in range(19, 23)]
frz = [n for _, n, v, s in rows if max(tail(s)) < 90 and max(tail(s)) - min(tail(s)) <= 0.2]
print("tail frozen (s19..s22 within 0.2, all < 90):", frz)
by = {}
for _, n, v, s in rows:
    k = sum(x >= 90 for x in s.values()); by.setdefault(k, []).append(n)
for k in sorted(by): print(k, len(by[k]), sorted(by[k]) if len(by[k]) < 20 else "")
EOF
#  -> per root: D:/socom_archive/parity/gate 118, C:/projects/socom_pc/logs/parity/gate 47
#  -> window-clean stamps: 144; lowest window capture 92.0 (s6_audio_title15, 17, 18), 92.4 (s6_audio_title9),
#     92.8 (s5_gsbp2c)
#  -> literal rule refuses 130 of 144 window-clean stamps
#  -> tail frozen: s5_gsbp2, s6_audio_title14, s7_cpu_fallback2 and the eighteen s11_r0004_* runs -- every one
#     of them already fails inside the window
#  -> the by-count groups with their stamp names, as in the §1 table (19/23 has 123 names and is not listed)

# H -- the image the issue names under scripts/parity/refs/ is the gate's reference, byte for byte
sha256sum scripts/parity/refs/main_menu.png scripts/parity/ref_main_menu_ours.png
#  -> cc36f23fbc5863cf0b608cf2fe268acd8a33fb46dcb53c99f19233caca3d2a7c for both

# E -- the new verdict on the archived captures themselves (re-scores PNGs, no game)
python -m tools_py.parity.gate --score-title D:/socom_archive/parity/gate/<stamp>/title
#  -> s8_audio_mc_gate2  PASS (23/23 ... window s00..s18: 19/19); attract not reached by s22
#  -> s8_close_gate      PASS (20/23 ... window 19/19)
#  -> s9_p7_playtest_gate PASS (19/23 ... window 19/19)
#  -> s7_cpu_fallback2   FAIL (16/23 ... window 16/19); menu capture(s) under 90.0: s16 s17 s18

# F -- the test (unittest only; this module alone, no lock)
python -m unittest tools_py.tests.test_title_menu_window     # before the scorer change: 3 of 7 FAIL; after: OK
python -m unittest tools_py.tests.test_gate.TitleScoring      # the committed 16-capture fixture still passes
```

## 1. The record (A)

165 archived stamps carry a title line with 23 scores (A): 118 under `D:/socom_archive/parity/gate` (2026-09-10 ..
2026-09-21) and 47 under the main tree's `logs/parity/gate` (2026-09-22 .. 2026-09-25) (G's `per root`; the date
ranges are the appendix's first and last mtimes per root). By the old count (A's counter; the stamp names in the
second column are G's by-count listing; the third column's descriptions come from D on the named stamps and from the
scores, not from viewing all 165):

| menu captures >= 90 | stamps | what the captures show |
|---|---|---|
| 19/23 | 123 | s00..s18 the menu, s19 the menu fading to black (83-90), s20..s22 black or a flyover (49-74) |
| 20/23, 21/23 | 7 | the same, one capture later (s8_close_gate, s8_empty_card_title, s9_crouch_gate, s6_revert_gate, s6_task8_gate, s5_gsbp3, s5_gsbp2c) |
| 23/23 | 14 | no attract inside the window: s5_gsbp2b, s6_audio_title7..13/15..18, s6_audio_gate7, s8_audio_mc_gate2 |
| 16/23 | 1 | s7_cpu_fallback2: frozen on the menu-over-black from s16 (s16..s22 = 82.7-82.9) -- PASSED |
| 7/23 | 1 | s6_audio_title14: every capture from s07 on 83.5 -- FAILED |
| 0/23 | 19 | s5_gsbp2 and eighteen s11_r0004_* runs: one screen at 60.2-62.1 throughout (the r0004 boot) -- FAILED |

The issue's sequence -- 23/23, then 20/23, then 19/23 "every gate since" -- is real but reads backwards: 19/23 is the
standing shape from the very first stamp, `s8_audio_mc_gate2` is the fourteenth no-attract outlier, and
`s8_close_gate` (20/23) is the attract a capture late. The gates the issue names after it (`s9_g1_gate`,
`s9_g2_release_gate`, `s9_p1_gate`, `s9_p7_playtest_gate`) have the same s19..s22 as `native_on` eight days earlier.
**There is no first-fall stamp and no commit to blame.** The reference (`scripts/parity/ref_main_menu_ours.png`) and
the title script have not changed since 2026-09-09 (C). `09d9ec0` (the Sprint 8 close-out) touches the mic ring, the
WAV reader and the card path (`git show --stat 09d9ec0`), nothing on the menu. `s8_audio_mc_gate2` itself was run at
02:21 on 2026-09-19, a minute before `54d77a2` (the menu-stream first-fill fix) was committed, i.e. on a working-tree
build; the KNOWN row that credits that fix with "19-20/23 to 23/23" (KNOWN §1, the row citing `54d77a2`) read the
outlier as the fix.

Timing is not the difference (B): s19 lands 114.4-114.7 s after s00 in every stamp checked, including the 23/23 ones, and
the boot's length (s00 at 21 s, 35 s, 52 s or 84 s) moves the attract with it, so the attract counts from the menu.

## 2. The side by side (D)

The comparison uses `scripts/parity/ref_main_menu_ours.png`, the file the gate scores against. The image the issue
names under `scripts/parity/refs/` (`main_menu.png`) was not used separately because it is the same file byte for byte
(H: one sha256 for both, both added in `d0caab98`) -- it is our own capture, not a console-side image, so comparing
against it would repeat these numbers exactly.

The reference is the main menu: the SOCOM II logo and the trident badge over an amber photograph (a harbour skyline, a
soldier bottom left), LOAD GAME / NEW GAME / ONLINE, the credit lines, and -- only in the reference -- the runtime's
"Runtime Debugg..." overlay tab at the bottom right.

- **`s8_audio_mc_gate2` s19..s22 (96.0-96.5):** four copies of the menu, background still the dim amber photograph.
  The attract never began.
- **`s8_close_gate` s19..s22 (92.6, 83.5, 62.2, 62.3):** s19 the menu with its background faded to black (the logo
  and the three items still lit), s20 the same further down, s21 a green night-vision wireframe flyover typing
  "KELLSKI EXPERIMENTAL AIR/SEACRAFT FACILITY, KAMCH", s22 a daylight flyover captioned "ABANDONED TOOLWORKS,
  SHKODER" with a soldier on a gantry.
- **`s9_p7_playtest_gate` s19..s22 (87.8, 60.2, 63.5, 63.3):** s19 the menu on black, s20 all black (the cut), s21 the
  snowy Kamchatka container yard, caption complete, s22 a motion-blurred zoom into the next flyover.
- **`s11_close_gate` s19..s22 (83.5, 58.8, 55.3, 64.9):** s19 the menu on black, s20 the green wireframe, s21 the blur,
  s22 "SLUMS OF R..." (a night street).

**Verdict: a timing -- the phase of the idle attract sequence -- not a screen, a render or a card state.** Every run
shows the same sequence at a slightly different point; nothing in the four captures is a broken menu. The menu part of
the pictures is the same in all of them: s00..s18 score 92.0-99.4 on every stamp whose window is whole (G; the
lowest, 92.0 on s6_audio_title15/17/18, is the real margin, 2.0 over the 90 bar).

Why fourteen runs never reached the attract is not settled here. Twelve of them (G's 23/23 group, grouped by hand
by name) are the Sprint 6 audio-experiment
series of 2026-09-17 11:41-13:38 (s6_audio_title7..18, s6_audio_gate7) and one is the audio working tree above, which
suggests the attract's start waits on the title music stream's state; that is a hypothesis from the grouping only, and
the console's own behaviour (does the attract always start at ~114 s?) has not been measured.

## 3. What the count bar hid (A, E)

The count bar was written for "19 menu captures, then the attract", with three captures of headroom. The headroom is
not at the tail, where it was meant to be: a run whose menu breaks at s16 still has s00..s15, sixteen matches, and
passes. `s7_cpu_fallback2` did exactly that: its s16..s22 are the menu logo over black, frozen, 82.7-82.9 each, and
its line reads `PASS title (16/23 ...)`. That is the "kept passing" defect, on the record, in a different run than
the issue names.

The fix (`tools_py/parity/gate.py`, `score_title`): the verdict is positional.

**Why a fixed window and not the task's literal rule.** Task V1 Step 2 asked that "the title stage refuses a capture
under 90 when the reference matches its own previous capture within tolerance". Applied at run time to every capture,
that rule refuses every clean run at the fade: s18 matches and s19 (the menu fading to black) scores 83-89. G counts
it: it refuses 130 of the 144 stamps whose menu window is whole (the 123 standing 19/23 runs plus the 7 with the
attract one capture late). So the predecessor evidence is used where it holds -- on the record, not at run time:
s00..s18 are the positions that matched, each after a matching predecessor, on every clean stamp, and that fixed
window is what the verdict checks.

- `TITLE_MENU_WINDOW = 19`: s00..s18 are the menu. Every capture the run wrote in that window must score >=
  `TITLE_MIN_SCORE` (90.0); a lost one fails the stage and is named in the detail (`menu capture(s) under 90.0: s16
  s17 s18`). On the record each of those positions matched the reference, and so did the capture before it. The
  lowest window capture on a clean stamp is 92.0 (G), so the margin over the bar is 2.0 points; the lowest s18 alone
  is 93.0 (`s5_gsbp2c`, A), and the fade that follows it scores 83-92, so 90 still separates them.
- The tail s19..s22 is scored and printed but not counted. When the whole tail matches the menu the detail says
  `attract not reached by s22`, so the no-attract outlier is visible without failing a run whose menu is whole.
- `TITLE_MIN_MATCHES = 16` remains as the floor on how many window captures a run must have written (the committed
  fixture `tests/fixtures/gate/title` holds s00..s15 and still passes).

Replayed over the 165 stamps (A) this changes exactly one verdict: `s7_cpu_fallback2`, PASS -> FAIL. Every other
PASS stays PASS, every FAIL stays FAIL.

The test (`tools_py/tests/test_title_menu_window.py`, F) builds 23 generated frames per case against a generated
reference: the standing 19/23 shape, the attract a capture late, the no-attract shape (PASS, named), a lost s18 at
18/23 and the cpu-fallback freeze at 16/23 (both refused, captures named), and the short-run floor. Before the scorer
change 3 of its 7 cases failed (the two refusals and the no-attract note); after it all pass.

## 4. What this means for the task

- **Closing bar, first half (side by side, difference named): met** -- §2; the difference is the attract's phase.
- **Closing bar, second half ("a fix that brings the four back to 90 or above on a gate, or a deliberate
  re-reference"): AMENDED, not met.** Neither applies, because the four are the attract sequence, not menu captures,
  and should not match the menu. The reference is right for the menu and stays as it is; no re-reference. The bar is
  replaced by "the menu window s00..s18 is scored capture by capture and a lost one fails the stage", which `79aad10c`
  does. **The close comment on #30 must say the bar was amended and why** (§2's verdict, §3's `s7_cpu_fallback2`),
  not that it was met, and the issue's title premise should be corrected when it is closed.
- **Open gap: a freeze that starts inside the tail passes.** If the game froze at s19 or later, the window is whole
  and s19..s22 are only printed, so the stage passes. On the record no such run exists: G's tail-frozen list (s19..s22
  within 0.2 of each other and all under 90) is 21 stamps, and every one already fails inside the window. A cheap
  guard, not built here: name or fail a run whose s19..s22 scores are all under 90 and within 0.2 of each other; or,
  sharper, reuse the mission stage's liveness idea (`MISSION_LIVE_PAIR_DIFF`) and require at least one tail pair to
  differ by a mean absolute RGB difference over a floor -- a real attract moves between every capture (§2), a frozen
  frame does not. The 14 no-attract runs are untouched by the score form of the guard: their tails are the static
  menu at >= 90.
- **The scorer change is the fix for the "kept passing" half**, and it is a `tools_py/parity/` change, so HANDOFF §5
  rule 5 owes a green three-stage gate on it before it reaches the sprint branch. That run is lock-bound and was not
  done here; the re-score of the archived captures (E) is the evidence available without the lock.
- **Doc rows to correct at close:** KNOWN §2's #30 row (s19..s22 "the last four menu screens" -> the attract; the
  `s7_cpu_fallback2` pass is the real instance), KNOWN §1's `54d77a2` row ("the gate's title stage went from its
  standing 19-20/23 to 23/23" -> that 23/23 was a no-attract run on a working-tree build).
- **Open, not this task:** why fourteen runs never started the attract (§2, last paragraph); a console measurement of
  when the attract starts would say whether "no attract by s22" should become a failure.

## Appendix: every stamp (A, one row per stamp)

`s00..s18 min` is the lowest of the nineteen menu-window scores (the full 23 are in each stamp's `summary.txt`);
`old` is the verdict the stamp printed; `new` is the positional verdict on the same scores.

| summary mtime | stamp | old | >=90 | s00..s18 min | s19 | s20 | s21 | s22 | new |
|---|---|---|---|---|---|---|---|---|---|
| 2026-09-10 23:43 | native_on | PASS | 19/23 | 93.2 | 84.1 | 59.9 | 61.6 | 61.6 | PASS |
| 2026-09-11 02:28 | famb | PASS | 19/23 | 93.4 | 84.1 | 60.4 | 59.6 | 59.6 | PASS |
| 2026-09-12 03:52 | s3a | PASS | 19/23 | 93.4 | 84.2 | 61.2 | 62.4 | 62.4 | PASS |
| 2026-09-12 05:10 | s3b3 | PASS | 19/23 | 93.4 | 84.2 | 61.2 | 61.8 | 61.8 | PASS |
| 2026-09-12 07:36 | s3d_2x_host | PASS | 19/23 | 93.6 | 84.2 | 66.4 | 62.2 | 62.2 | PASS |
| 2026-09-12 11:11 | s4_mb | PASS | 19/23 | 93.2 | 83.7 | 59.4 | 49.5 | 65.4 | PASS |
| 2026-09-12 13:15 | s4_rand | PASS | 19/23 | 93.2 | 83.9 | 60.6 | 50.2 | 68.1 | PASS |
| 2026-09-12 13:50 | s4_rand2 | PASS | 19/23 | 93.2 | 87.4 | 60.2 | 64.1 | 60.8 | PASS |
| 2026-09-12 13:55 | s4_rand3 | PASS | 19/23 | 93.2 | 84.1 | 59.0 | 49.8 | 64.8 | PASS |
| 2026-09-12 15:06 | s4_abi | PASS | 19/23 | 93.2 | 83.9 | 59.7 | 49.5 | 65.4 | PASS |
| 2026-09-13 04:50 | s5_task0 | PASS | 19/23 | 93.2 | 84.0 | 60.5 | 50.2 | 67.6 | PASS |
| 2026-09-13 06:56 | s5_task1_knob | PASS | 19/23 | 93.2 | 87.3 | 60.2 | 66.9 | 61.2 | PASS |
| 2026-09-13 10:00 | s5_task4_dbuff | PASS | 19/23 | 93.2 | 87.4 | 60.2 | 64.8 | 62.0 | PASS |
| 2026-09-13 11:19 | s5_task1_vf0 | PASS | 19/23 | 93.2 | 87.3 | 60.2 | 66.1 | 61.0 | PASS |
| 2026-09-13 12:37 | s5_gatefix | PASS | 19/23 | 93.2 | 84.0 | 61.2 | 52.0 | 68.1 | PASS |
| 2026-09-13 13:20 | s5_gatefix2 | PASS | 19/23 | 93.2 | 84.2 | 60.4 | 49.8 | 67.9 | PASS |
| 2026-09-13 14:35 | s5_gsbp | PASS | 19/23 | 93.0 | 87.7 | 60.2 | 66.9 | 61.6 | PASS |
| 2026-09-13 16:00 | s5_gsbp2b | PASS | 23/23 | 94.2 | 98.2 | 98.2 | 98.0 | 97.8 | PASS |
| 2026-09-13 16:23 | s5_gsbp2c | PASS | 21/23 | 92.8 | 95.2 | 97.9 | 87.4 | 60.2 | PASS |
| 2026-09-13 16:52 | s5_hygiene | PASS | 19/23 | 93.0 | 89.7 | 83.5 | 63.9 | 60.1 | PASS |
| 2026-09-13 17:43 | s5_gsbp3 | PASS | 20/23 | 93.2 | 98.6 | 84.0 | 66.4 | 56.7 | PASS |
| 2026-09-14 00:44 | s5_head_1x | PASS | 19/23 | 93.2 | 84.2 | 60.5 | 49.9 | 67.6 | PASS |
| 2026-09-14 13:04 | s6_depth | PASS | 19/23 | 93.4 | 85.4 | 60.4 | 61.6 | 67.1 | PASS |
| 2026-09-15 19:42 | s6_blockptr | PASS | 19/23 | 93.2 | 83.9 | 60.6 | 51.3 | 68.0 | PASS |
| 2026-09-16 01:12 | s6_gamepad | PASS | 19/23 | 93.2 | 87.3 | 60.2 | 66.9 | 61.0 | PASS |
| 2026-09-16 01:32 | s6_gamepad2 | PASS | 19/23 | 93.2 | 87.3 | 60.2 | 66.1 | 60.5 | PASS |
| 2026-09-16 02:17 | s6_gamepad3 | PASS | 19/23 | 93.2 | 87.3 | 60.2 | 66.3 | 60.8 | PASS |
| 2026-09-16 02:38 | s6_gamepad4 | PASS | 19/23 | 93.2 | 87.9 | 60.2 | 65.9 | 62.2 | PASS |
| 2026-09-16 03:18 | s6_gamepad5 | PASS | 19/23 | 93.2 | 87.4 | 60.2 | 66.1 | 62.2 | PASS |
| 2026-09-16 09:52 | s6_blend | PASS | 19/23 | 93.2 | 87.7 | 60.2 | 66.3 | 61.2 | PASS |
| 2026-09-16 10:16 | s6_lum | PASS | 19/23 | 93.2 | 87.3 | 60.2 | 65.9 | 60.5 | PASS |
| 2026-09-16 10:50 | s6_lum3 | PASS | 19/23 | 93.2 | 84.2 | 60.4 | 51.4 | 66.1 | PASS |
| 2026-09-16 11:18 | s6_lum4 | PASS | 19/23 | 93.2 | 84.2 | 60.7 | 52.0 | 67.9 | PASS |
| 2026-09-16 11:35 | s6_lum5 | PASS | 19/23 | 93.2 | 84.1 | 59.7 | 49.9 | 67.6 | PASS |
| 2026-09-16 12:42 | s6_lum8 | PASS | 19/23 | 93.4 | 85.3 | 60.2 | 62.0 | 62.1 | PASS |
| 2026-09-16 14:31 | s6_commit2 | PASS | 19/23 | 93.2 | 87.9 | 60.2 | 67.7 | 61.0 | PASS |
| 2026-09-16 19:05 | s6_vifwait_gate | PASS | 19/23 | 93.5 | 84.2 | 61.2 | 52.0 | 68.1 | PASS |
| 2026-09-16 19:22 | s6_vifwait_gate2 | PASS | 19/23 | 93.2 | 87.7 | 60.2 | 67.5 | 61.0 | PASS |
| 2026-09-16 19:59 | s6_flags_gate | PASS | 19/23 | 93.5 | 84.2 | 61.1 | 53.0 | 67.1 | PASS |
| 2026-09-16 20:27 | s6_flags_gate2 | PASS | 19/23 | 93.2 | 84.2 | 60.5 | 49.9 | 67.6 | PASS |
| 2026-09-16 20:58 | s6_revert_gate | PASS | 20/23 | 93.0 | 97.9 | 85.7 | 60.2 | 62.2 | PASS |
| 2026-09-17 00:09 | s6_clutfix_gate | PASS | 19/23 | 93.2 | 83.7 | 59.7 | 56.7 | 64.8 | PASS |
| 2026-09-17 05:21 | s6_clock_gate | PASS | 19/23 | 93.2 | 88.4 | 60.2 | 64.1 | 62.2 | PASS |
| 2026-09-17 05:51 | s6_clockdef_gate | PASS | 19/23 | 93.5 | 85.4 | 61.2 | 52.1 | 67.8 | PASS |
| 2026-09-17 06:58 | s6_audio_gate | PASS | 19/23 | 93.0 | 89.7 | 60.2 | 66.3 | 60.8 | PASS |
| 2026-09-17 07:40 | s6_audio_gate2 | PASS | 19/23 | 93.4 | 85.4 | 62.6 | 53.1 | 67.1 | PASS |
| 2026-09-17 07:57 | s6_audio_gate3 | PASS | 19/23 | 93.4 | 85.2 | 63.9 | 52.1 | 67.5 | PASS |
| 2026-09-17 08:21 | s6_audio_gate4 | PASS | 19/23 | 93.0 | 88.9 | 60.2 | 65.9 | 60.5 | PASS |
| 2026-09-17 08:38 | s6_audio_gate5 | PASS | 19/23 | 93.2 | 89.1 | 60.2 | 64.8 | 62.0 | PASS |
| 2026-09-17 09:28 | s6_audio_gate6 | PASS | 19/23 | 93.2 | 89.1 | 60.2 | 64.8 | 62.2 | PASS |
| 2026-09-17 10:03 | s6_launcher_gate | PASS | 19/23 | 93.0 | 89.1 | 60.2 | 63.0 | 62.4 | PASS |
| 2026-09-17 10:42 | s6_audio_title | PASS | 19/23 | 93.2 | 84.1 | 59.4 | 56.6 | 64.9 | PASS |
| 2026-09-17 10:59 | s6_audio_title2 | PASS | 19/23 | 93.2 | 87.4 | 60.2 | 62.7 | 61.9 | PASS |
| 2026-09-17 11:07 | s6_audio_title3 | PASS | 19/23 | 93.2 | 83.9 | 57.4 | 56.7 | 65.4 | PASS |
| 2026-09-17 11:17 | s6_audio_title4 | PASS | 19/23 | 93.2 | 84.2 | 59.9 | 52.1 | 67.5 | PASS |
| 2026-09-17 11:24 | s6_audio_title5 | PASS | 19/23 | 93.2 | 87.4 | 60.2 | 63.1 | 62.0 | PASS |
| 2026-09-17 11:29 | s6_audio_title6 | PASS | 19/23 | 93.2 | 87.8 | 60.2 | 63.1 | 62.8 | PASS |
| 2026-09-17 11:41 | s6_audio_title7 | PASS | 23/23 | 98.4 | 98.9 | 98.9 | 98.9 | 98.9 | PASS |
| 2026-09-17 11:57 | s6_audio_gate7 | PASS | 23/23 | 95.7 | 96.2 | 96.2 | 96.2 | 96.2 | PASS |
| 2026-09-17 12:20 | s6_audio_title8 | PASS | 23/23 | 95.5 | 97.5 | 96.6 | 96.2 | 96.9 | PASS |
| 2026-09-17 12:34 | s6_audio_title9 | PASS | 23/23 | 92.4 | 98.0 | 98.2 | 98.2 | 98.2 | PASS |
| 2026-09-17 12:44 | s6_audio_title10 | PASS | 23/23 | 93.0 | 96.2 | 96.2 | 96.2 | 96.2 | PASS |
| 2026-09-17 12:50 | s6_audio_title11 | PASS | 23/23 | 98.5 | 98.5 | 98.5 | 98.5 | 98.5 | PASS |
| 2026-09-17 12:56 | s6_audio_title12 | PASS | 23/23 | 98.5 | 98.9 | 98.9 | 98.9 | 98.9 | PASS |
| 2026-09-17 13:00 | s6_audio_title13 | PASS | 23/23 | 93.1 | 97.6 | 98.0 | 98.0 | 98.0 | PASS |
| 2026-09-17 13:10 | s6_audio_title14 | FAIL | 7/23 | 83.5 | 83.5 | 83.5 | 83.5 | 83.5 | FAIL |
| 2026-09-17 13:19 | s6_audio_title15 | PASS | 23/23 | 92.0 | 97.3 | 98.2 | 93.4 | 93.2 | PASS |
| 2026-09-17 13:25 | s6_audio_title16 | PASS | 23/23 | 95.9 | 98.3 | 98.3 | 98.3 | 98.3 | PASS |
| 2026-09-17 13:32 | s6_audio_title17 | PASS | 23/23 | 92.0 | 98.1 | 97.8 | 95.6 | 94.6 | PASS |
| 2026-09-17 13:38 | s6_audio_title18 | PASS | 23/23 | 92.0 | 98.2 | 98.1 | 98.1 | 97.6 | PASS |
| 2026-09-17 13:45 | s6_audio_title19 | PASS | 19/23 | 93.0 | 87.9 | 60.2 | 67.9 | 61.3 | PASS |
| 2026-09-17 13:53 | s6_audio_title20 | PASS | 19/23 | 93.2 | 88.3 | 73.8 | 65.8 | 63.8 | PASS |
| 2026-09-17 14:08 | s6_audio_gate20 | PASS | 19/23 | 93.0 | 83.7 | 57.4 | 56.6 | 65.9 | PASS |
| 2026-09-17 16:39 | s6_task8_gate | PASS | 20/23 | 93.2 | 91.0 | 80.5 | 64.7 | 61.2 | PASS |
| 2026-09-17 16:42 | s6_movie_dump | PASS | 19/23 | 93.2 | 88.3 | 60.2 | 63.1 | 61.9 | PASS |
| 2026-09-17 16:46 | s6_movie_dump2 | PASS | 19/23 | 93.2 | 87.4 | 60.2 | 63.3 | 61.9 | PASS |
| 2026-09-17 16:49 | s6_movie_dump3 | PASS | 19/23 | 93.0 | 88.4 | 60.2 | 67.5 | 61.6 | PASS |
| 2026-09-17 18:12 | s6_fixwave_gate | PASS | 19/23 | 93.2 | 87.8 | 60.2 | 62.7 | 61.9 | PASS |
| 2026-09-17 19:36 | s7_gl_gate | PASS | 19/23 | 93.2 | 88.5 | 60.2 | 63.5 | 62.8 | PASS |
| 2026-09-17 19:47 | s7_cpu_fallback2 | PASS | 16/23 | 82.7 | 82.7 | 82.7 | 82.7 | 82.7 | FAIL |
| 2026-09-17 21:00 | s7_gl_gate2 | PASS | 19/23 | 93.4 | 83.5 | 57.3 | 62.8 | 64.2 | PASS |
| 2026-09-18 00:39 | s7_2f_gate | PASS | 19/23 | 93.2 | 87.8 | 60.2 | 63.3 | 62.8 | PASS |
| 2026-09-18 02:09 | s7_fps_overlay | PASS | 19/23 | 93.2 | 87.8 | 60.2 | 63.3 | 61.9 | PASS |
| 2026-09-18 05:27 | s7_audio_title | PASS | 19/23 | 93.2 | 84.1 | 60.6 | 51.3 | 68.0 | PASS |
| 2026-09-18 05:50 | s7_closeout_gate | PASS | 19/23 | 93.2 | 87.4 | 60.2 | 63.5 | 62.8 | PASS |
| 2026-09-18 06:37 | s7_final_gate | PASS | 19/23 | 93.2 | 87.8 | 60.2 | 63.3 | 62.0 | PASS |
| 2026-09-18 10:50 | s8_mixer_gate | PASS | 19/23 | 93.5 | 84.2 | 66.3 | 53.1 | 67.8 | PASS |
| 2026-09-18 12:42 | s8_review_gate | PASS | 19/23 | 93.2 | 88.1 | 60.2 | 62.3 | 62.5 | PASS |
| 2026-09-19 00:58 | s8_goal2_gate | PASS | 19/23 | 93.2 | 84.1 | 59.5 | 49.8 | 66.1 | PASS |
| 2026-09-19 02:00 | s8_audio_mc_gate | PASS | 19/23 | 93.2 | 88.3 | 60.2 | 63.5 | 63.3 | PASS |
| 2026-09-19 02:03 | s8_empty_card_title | PASS | 20/23 | 92.8 | 98.7 | 83.3 | 59.9 | 62.9 | PASS |
| 2026-09-19 02:21 | s8_audio_mc_gate2 | PASS | 23/23 | 95.1 | 96.0 | 96.5 | 96.5 | 96.5 | PASS |
| 2026-09-19 05:20 | s8_voice_gate | PASS | 19/23 | 93.2 | 87.9 | 60.2 | 63.3 | 61.9 | PASS |
| 2026-09-19 06:42 | s8_voice_gate2 | PASS | 19/23 | 93.2 | 83.5 | 59.4 | 56.6 | 64.9 | PASS |
| 2026-09-19 08:36 | s8_texreval_gate | PASS | 19/23 | 93.2 | 83.7 | 59.5 | 56.6 | 64.9 | PASS |
| 2026-09-19 09:32 | s8_close_gate | PASS | 20/23 | 93.2 | 92.6 | 83.5 | 62.2 | 62.3 | PASS |
| 2026-09-19 11:54 | s9_g1_gate | PASS | 19/23 | 93.2 | 87.4 | 60.2 | 62.7 | 61.9 | PASS |
| 2026-09-19 13:22 | s9_crouch_gate | PASS | 20/23 | 93.2 | 98.7 | 60.2 | 65.3 | 61.8 | PASS |
| 2026-09-19 15:04 | s9_g2_release_gate | PASS | 19/23 | 93.5 | 83.5 | 56.8 | 58.7 | 65.6 | PASS |
| 2026-09-19 19:30 | s9_p1_gate | PASS | 19/23 | 93.4 | 87.7 | 60.2 | 61.7 | 57.5 | PASS |
| 2026-09-20 01:08 | s9_p7_playtest_gate | PASS | 19/23 | 93.2 | 87.8 | 60.2 | 63.5 | 63.3 | PASS |
| 2026-09-20 02:30 | s9_q0_trace_gate | PASS | 19/23 | 93.2 | 83.5 | 57.4 | 55.3 | 64.8 | PASS |
| 2026-09-20 03:18 | s9_q0_device_gate | PASS | 19/23 | 93.2 | 87.9 | 60.2 | 63.1 | 63.0 | PASS |
| 2026-09-20 04:12 | s9_q0_prefill_gate | PASS | 19/23 | 93.2 | 87.9 | 60.2 | 63.3 | 62.8 | PASS |
| 2026-09-20 05:49 | s9_q0_children_gate | PASS | 19/23 | 93.3 | 85.7 | 56.7 | 65.7 | 66.3 | PASS |
| 2026-09-21 00:25 | s10_h6_scrub_gate | PASS | 19/23 | 93.0 | 88.6 | 63.1 | 67.3 | 61.3 | PASS |
| 2026-09-21 01:54 | s10_q1b_pins_gate | PASS | 19/23 | 93.2 | 83.5 | 59.5 | 49.9 | 66.1 | PASS |
| 2026-09-21 02:53 | s10_q6_gate | PASS | 19/23 | 93.2 | 87.4 | 60.2 | 64.1 | 62.4 | PASS |
| 2026-09-21 03:52 | s10_g8_gate | PASS | 19/23 | 93.2 | 83.7 | 59.7 | 49.5 | 66.1 | PASS |
| 2026-09-21 04:58 | s10_g9_gate | PASS | 19/23 | 93.2 | 87.4 | 60.2 | 64.8 | 62.2 | PASS |
| 2026-09-21 11:55 | s9_g3_batches_gate | PASS | 19/23 | 93.2 | 83.5 | 59.6 | 49.6 | 65.4 | PASS |
| 2026-09-21 12:53 | s9_g3_gating_gate | PASS | 19/23 | 93.2 | 83.5 | 58.4 | 49.6 | 64.9 | PASS |
| 2026-09-21 13:51 | s10_q4_gate | PASS | 19/23 | 93.0 | 83.5 | 59.7 | 49.5 | 66.2 | PASS |
| 2026-09-21 14:18 | s10_q3_gate | PASS | 19/23 | 93.0 | 83.5 | 57.0 | 56.7 | 65.4 | PASS |
| 2026-09-21 15:58 | s10_q7_gate | PASS | 19/23 | 93.2 | 87.8 | 60.2 | 63.1 | 62.5 | PASS |
| 2026-09-21 16:22 | s10_q7b_gate | PASS | 19/23 | 93.2 | 87.4 | 60.2 | 66.3 | 60.5 | PASS |
| 2026-09-21 17:36 | s10_playtest2_gate | PASS | 19/23 | 93.2 | 83.5 | 59.7 | 49.8 | 66.1 | PASS |
| 2026-09-22 02:10 | fixwave_a | PASS | 19/23 | 93.4 | 83.5 | 59.0 | 49.6 | 64.7 | PASS |
| 2026-09-22 03:57 | fixwave_b | PASS | 19/23 | 93.0 | 83.5 | 59.5 | 49.5 | 64.8 | PASS |
| 2026-09-23 01:51 | s10_close_gate | PASS | 19/23 | 93.2 | 87.8 | 60.2 | 63.3 | 62.8 | PASS |
| 2026-09-23 02:29 | s11_open_gate | PASS | 19/23 | 93.2 | 87.4 | 60.2 | 64.8 | 62.2 | PASS |
| 2026-09-23 13:54 | s11_u_translators_gate | PASS | 19/23 | 93.0 | 83.5 | 59.5 | 49.9 | 66.1 | PASS |
| 2026-09-23 17:21 | s11_savestate_gate | PASS | 19/23 | 93.5 | 84.2 | 66.4 | 54.1 | 67.1 | PASS |
| 2026-09-23 20:05 | s11_addr_gate | PASS | 19/23 | 93.5 | 83.5 | 56.5 | 59.6 | 65.6 | PASS |
| 2026-09-24 01:01 | s11_cfa_gate | PASS | 19/23 | 93.2 | 87.4 | 60.2 | 63.1 | 60.5 | PASS |
| 2026-09-24 03:08 | s11_merge19_gate | PASS | 19/23 | 93.2 | 88.3 | 60.2 | 63.3 | 61.9 | PASS |
| 2026-09-24 06:09 | s11_override_gate | PASS | 19/23 | 93.0 | 83.5 | 60.5 | 49.5 | 64.8 | PASS |
| 2026-09-24 08:59 | s11_rtstate_gate | PASS | 19/23 | 93.2 | 87.8 | 60.2 | 64.1 | 62.2 | PASS |
| 2026-09-24 09:33 | s11_r0004_reg2 | PASS | 19/23 | 93.2 | 88.0 | 60.2 | 63.1 | 62.2 | PASS |
| 2026-09-24 10:07 | s11_r0004_probe1 | PASS | 19/23 | 93.0 | 83.5 | 59.5 | 56.7 | 65.4 | PASS |
| 2026-09-24 10:40 | s11_r0004_reg3 | PASS | 19/23 | 93.0 | 83.5 | 58.4 | 49.9 | 65.4 | PASS |
| 2026-09-24 11:35 | s11_r0004_probe2 | PASS | 19/23 | 93.4 | 83.5 | 58.0 | 58.7 | 65.2 | PASS |
| 2026-09-24 18:10 | s11_pr231_gate | PASS | 19/23 | 93.4 | 83.5 | 56.8 | 56.7 | 65.2 | PASS |
| 2026-09-24 19:13 | s11_pr229_gate | PASS | 19/23 | 93.2 | 87.8 | 60.2 | 63.0 | 62.5 | PASS |
| 2026-09-24 20:35 | s11_pr243_gate | PASS | 19/23 | 93.2 | 87.9 | 60.2 | 63.3 | 62.0 | PASS |
| 2026-09-24 21:28 | s11_pr230_gate | PASS | 19/23 | 93.2 | 84.1 | 60.6 | 52.0 | 67.9 | PASS |
| 2026-09-24 22:00 | s11_pr237_gate | PASS | 19/23 | 93.2 | 87.9 | 60.2 | 63.1 | 62.0 | PASS |
| 2026-09-24 22:31 | s11_pr232_gate | PASS | 19/23 | 93.2 | 87.9 | 60.2 | 63.1 | 62.0 | PASS |
| 2026-09-24 23:00 | s11_pr227_gate | PASS | 19/23 | 93.4 | 83.5 | 57.0 | 56.7 | 66.0 | PASS |
| 2026-09-24 23:20 | s11_pr240_gate | PASS | 19/23 | 93.2 | 83.5 | 60.4 | 49.9 | 66.1 | PASS |
| 2026-09-24 23:52 | s11_pr241_gate | PASS | 19/23 | 93.2 | 88.3 | 60.2 | 64.8 | 61.2 | PASS |
| 2026-09-25 00:25 | s11_pr246_gate | PASS | 19/23 | 93.4 | 83.5 | 56.8 | 63.7 | 65.6 | PASS |
| 2026-09-25 01:19 | s11_picks_keep_gate | PASS | 19/23 | 93.2 | 83.7 | 60.4 | 49.9 | 67.6 | PASS |
| 2026-09-25 01:47 | s11_r0004_rebuild1 | PASS | 19/23 | 93.2 | 87.8 | 60.2 | 63.0 | 62.4 | PASS |
| 2026-09-25 02:37 | s12_names_gate | PASS | 19/23 | 93.0 | 83.5 | 59.4 | 56.7 | 64.7 | PASS |
| 2026-09-25 03:32 | s11_close_gate | PASS | 19/23 | 93.2 | 83.5 | 58.8 | 55.3 | 64.9 | PASS |

Not in the table, every capture of these the same screen at 60.2-62.1 (0/23, FAIL both ways): s5_gsbp2, s11_r0004_gate, s11_r0004_gate2, s11_r0004_gate3, s11_r0004_loop1, s11_r0004_loopc1, s11_r0004_loopc2, s11_r0004_loopd1, s11_r0004_trace1, s11_r0004_heapmeas, s11_r0004_heap1, s11_r0004_heap2, s11_r0004_node2, s11_r0004_node1, s11_r0004_node3, s11_r0004_node4, s11_r0004_node5, s11_r0004_node6, s11_r0004_reg1
