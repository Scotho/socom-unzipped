"""Build the committed fixtures under tests/fixtures/gate/ so tools_py/tests/test_gate.py's
positive cases run on a fresh clone (no logs/ dir required).

Sources (all git-ignored, kept locally from real runs -- see STATUS 2026-09-10/09-09):
  title:      logs/parity/runs/vr_title/s00_none.png .. s15_none.png  (known clean, 19/23 >= 90.0)
  transition: five frames of logs/parity/gate/wcap2/transition (one step capture and four wait
              captures, all peak 0 in black_rows.py's rows 396-448 band, confirmed by running
              black_rows.py on that run; gate.TRANSITION_MIN_FRAMES is 5)
  mission:    logs/parity/drive_gameplay_probe5.txt (HUD matched=True, known good) and
              logs/parity/vr_gameplay.drive.log (HUD matched=False, known bad)

Mission fixtures are written as good.drive.txt / bad.drive.txt, not *.drive.log: .gitignore has
a blanket "*.log" rule, and a .log fixture would silently fail to be picked up by a plain
`git add` on a future regeneration (it would need `git add -f` every time). .txt is not
git-ignored, so a plain `git add tests/fixtures/gate/mission` just works.

Title and transition images are resized to 320x224 with Image.BOX -- compare.score (compare.py)
resizes to that size anyway, so storing at that size costs it nothing. Resized title PNGs still
ran ~80-95 KB each (16 of them blew the 1 MB budget) because the menu art doesn't compress well
as 24-bit RGB, so they're additionally quantized to a 256-colour palette (PNG P mode), which cuts
each to ~25-35 KB for a <0.5-point score change. Each title fixture is checked -- after quantizing
and reloading the saved file -- against scripts/parity/ref_main_menu_ours.png with compare.score;
if any drops below 90 this script falls back to saving all title fixtures unquantized at their
native 640x448 (and says so) rather than silently shipping a fixture that can't pass its own
gate's threshold.

Usage (from the repo root):
  python -m tools_py.parity.make_gate_fixtures

Re-run any time the source runs change; it always overwrites tests/fixtures/gate/*.
"""
import os
import re
import shutil

from PIL import Image

from tools_py.parity import compare

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURES = os.path.join(ROOT, "tests", "fixtures", "gate")
TITLE_REF = os.path.join(ROOT, "scripts", "parity", "ref_main_menu_ours.png")

TITLE_SRC_DIR = os.path.join(ROOT, "logs", "parity", "runs", "vr_title")
TITLE_NAMES = ["s%02d_none.png" % i for i in range(16)]  # s00..s15: the TITLE_MIN_MATCHES floor

TRANSITION_SRC_DIR = os.path.join(ROOT, "logs", "parity", "gate", "wcap2", "transition")
# (source name in that run, fixture name) -- all confirmed peak 0 in black_rows.py's default band.
# Five frames, because gate.TRANSITION_MIN_FRAMES is 5; taken from wcap2 rather than the older
# `first` run so the fixture is a real slice of a post-Task-8 run: one settled step capture and
# four of the w<step>_<k>.png frames drive.py now takes during its settle waits (the fade into
# the briefing shows up almost entirely in those). Names are kept as they were in the run.
TRANSITION_PAIRS = [(n, n) for n in ("s02_CROSS.png", "w00_000.png", "w00_001.png",
                                     "w01_001.png", "w03_000.png")]

MISSION_GOOD_SRC = os.path.join(ROOT, "logs", "parity", "drive_gameplay_probe5.txt")
MISSION_BAD_SRC = os.path.join(ROOT, "logs", "parity", "vr_gameplay.drive.log")
# What score_mission_log actually reads: the untilref(...ref_hud_ours.png...) line and any
# sNN_hold* lines (gate.py's MISSION_MIN_HOLDS is 3).
MISSION_LINE_RE = re.compile(r"^untilref\(.*ref_hud_ours\.png.*\):.*matched=(?:True|False)\s*$|^s\d\d_hold\w*\b")


def _trim_mission_log(src):
    with open(src, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    return [ln.strip() for ln in lines if MISSION_LINE_RE.match(ln.strip())]


def _save_quantized(im, dst):
    im.quantize(colors=256, method=Image.MEDIANCUT).save(dst, optimize=True)


def build_title_fixtures():
    out_dir = os.path.join(FIXTURES, "title")
    os.makedirs(out_dir, exist_ok=True)
    for name in TITLE_NAMES:
        src = os.path.join(TITLE_SRC_DIR, name)
        dst = os.path.join(out_dir, name)
        with Image.open(src) as im:
            _save_quantized(im.convert("RGB").resize((320, 224), Image.BOX), dst)
    # Re-open the saved files (not the pre-save in-memory images) so the check reflects exactly
    # what a fresh clone will read.
    scores = {}
    with Image.open(TITLE_REF) as ref:
        for name in TITLE_NAMES:
            with Image.open(os.path.join(out_dir, name)) as fixture:
                scores[name] = float(compare.score(ref, fixture)["score"])
    worst = min(scores.values())
    use_native = worst < 90.0
    if use_native:
        for name in TITLE_NAMES:
            shutil.copyfile(os.path.join(TITLE_SRC_DIR, name), os.path.join(out_dir, name))
        with Image.open(TITLE_REF) as ref:
            for name in TITLE_NAMES:
                with Image.open(os.path.join(out_dir, name)) as fixture:
                    scores[name] = float(compare.score(ref, fixture)["score"])
        worst = min(scores.values())
    size_note = "640x448 (native, quantized 320x224 dropped a fixture below 90)" if use_native else "320x224 (256-colour palette)"
    print("title: %d fixtures at %s; scores %.1f..%.1f (need >= 90.0, target >= 95)"
          % (len(TITLE_NAMES), size_note, worst, max(scores.values())))
    for name in TITLE_NAMES:
        print("  %-16s %.1f" % (name, scores[name]))
    return use_native, scores


def build_transition_fixtures():
    out_dir = os.path.join(FIXTURES, "transition")
    os.makedirs(out_dir, exist_ok=True)
    for src_name, dst_name in TRANSITION_PAIRS:
        with Image.open(os.path.join(TRANSITION_SRC_DIR, src_name)) as im:
            im.convert("RGB").resize((320, 224), Image.BOX).save(os.path.join(out_dir, dst_name))
    print("transition: %d fixtures at 320x224 (from %s)" % (len(TRANSITION_PAIRS), TRANSITION_SRC_DIR))


def build_mission_fixtures():
    out_dir = os.path.join(FIXTURES, "mission")
    os.makedirs(out_dir, exist_ok=True)
    good = _trim_mission_log(MISSION_GOOD_SRC)
    bad = _trim_mission_log(MISSION_BAD_SRC)
    with open(os.path.join(out_dir, "good.drive.txt"), "w", newline="\n", encoding="utf-8") as f:
        f.write("\n".join(good) + "\n")
    with open(os.path.join(out_dir, "bad.drive.txt"), "w", newline="\n", encoding="utf-8") as f:
        f.write("\n".join(bad) + "\n")
    print("mission: good.drive.txt (%d lines, from %s), bad.drive.txt (%d lines, from %s)"
          % (len(good), MISSION_GOOD_SRC, len(bad), MISSION_BAD_SRC))


def main():
    build_title_fixtures()
    build_transition_fixtures()
    build_mission_fixtures()
    total = sum(os.path.getsize(os.path.join(dp, fn))
                for dp, _, fns in os.walk(FIXTURES) for fn in fns)
    print("total fixture size: %.1f KB" % (total / 1024.0))


if __name__ == "__main__":
    main()
