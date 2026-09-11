"""One command for the three screenshot gates. PASS/FAIL per gate, exit 1 on any FAIL.

  python -m tools_py.parity.gate                     # all three (title ~3 min, transition ~3 min, mission ~11 min)
  python -m tools_py.parity.gate --only title,mission
  python -m tools_py.parity.gate --score-title logs/parity/runs/vr_title     # re-score, no game run
  python -m tools_py.parity.gate --score-mission logs/parity/drive_gameplay_probe5.txt

Runs go to logs/parity/gate/<stamp>/<gate>/ with the drive log beside them and a summary.txt.
Must be run from the repo root (drive.py uses relative paths). Takes scripts/loop_lock.sh.
"""
import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import time

from PIL import Image

from tools_py.parity import compare

TITLE_REF = os.path.join("scripts", "parity", "ref_main_menu_ours.png")
# Calibrated 2026-09-10 on the four stored clean title runs (vr_title, rt_title, gl_title,
# xg_title): the 19 menu captures s00..s18 score 93.2..99.4 against the reference, s19 is the
# fade into the attract movie (83.7..85.1) and s20..s22 are the movie itself (49.5..67.8).
# Every clean run scores exactly 19/23 >= 90.0, so 90.0 sits ~3 points under the menu band and
# ~5 points over the fade, and 16 leaves three captures of headroom. A mission run scored as a
# title run gives 1/36 (negative control, logs/parity/runs/gameplay_probe5).
TITLE_MIN_SCORE = 90.0      # compare.score of a capture vs the main-menu reference
TITLE_MIN_MATCHES = 16      # of the 23 captures s00..s22 (19 are at the menu on a clean run, then the attract movie)
HUD_REF_NAME = "ref_hud_ours.png"

GATES = {
    "title": dict(script="scripts/parity/title_menu.txt", seconds=170, tail=8),
    "transition": dict(script="scripts/parity/transition_probe.txt", seconds=170, tail=8),
    "mission": dict(script="scripts/parity/gameplay_probe.txt", seconds=480, tail=170),
}


def _score_value(golden, ours):
    """compare.score (compare.py:19) takes two PIL images and returns
    {"score": .., "mad": .., "block": ..}; it may also be a float or a (score, mad, block)
    tuple. Open the paths and normalise the result to a float."""
    r = compare.score(Image.open(golden), Image.open(ours))
    if isinstance(r, dict):
        return float(r["score"])
    return float(r[0] if isinstance(r, (tuple, list)) else r)


def score_title(run_dir):
    caps = sorted(p for p in glob.glob(os.path.join(run_dir, "s[0-9][0-9]_*.png")) if "burst" not in p)
    if not caps:
        return False, "no captures in %s" % run_dir
    scores = [(os.path.basename(p), _score_value(TITLE_REF, p)) for p in caps]
    good = sum(1 for _, s in scores if s >= TITLE_MIN_SCORE)
    detail = "%d/%d menu captures >= %.1f; scores: %s" % (
        good, len(scores), TITLE_MIN_SCORE, " ".join("%s=%.1f" % (n[:3], s) for n, s in scores))
    return good >= TITLE_MIN_MATCHES, detail


def score_transition(run_dir):
    r = subprocess.run([sys.executable, "tools_py/parity/black_rows.py", run_dir], capture_output=True, text=True)
    bad = [ln for ln in r.stdout.splitlines() if "NOT BLACK" in ln]
    return r.returncode == 0, ("rows 396-447 black on every black-screen frame" if r.returncode == 0
                               else "non-black band: " + "; ".join(bad[:5]))


def score_mission_log(drive_log):
    try:
        with open(drive_log, encoding="utf-8", errors="replace") as f:
            text = f.read()
    except OSError as e:
        return False, str(e)
    m = re.search(r"untilref\([^)]*%s[^)]*\):.*matched=(True|False)" % re.escape(HUD_REF_NAME), text)
    if not m:
        return False, "no HUD untilref result in %s" % drive_log
    if m.group(1) != "True":
        return False, "HUD never matched (mission not reached)"
    holds = len(re.findall(r"^s\d\d_hold", text, re.M))
    return holds >= 3, "HUD reached; %d hold steps captured" % holds


def _lock(cmd, owner):
    return subprocess.run(["bash", "scripts/loop_lock.sh", cmd, owner], capture_output=True, text=True)


def run_gate(name, out_root):
    cfg = GATES[name]
    out_dir = os.path.join(out_root, name)
    os.makedirs(out_dir, exist_ok=True)
    for p in glob.glob(os.path.join("logs", "parity", "latest_frame.png*")):
        os.remove(p)
    drive_log = os.path.join(out_root, name + ".drive.log")
    with open(drive_log, "w", encoding="utf-8") as log:
        subprocess.run([sys.executable, "-m", "tools_py.parity.drive", "--target", "ours",
                        "--script", cfg["script"], "--out", out_dir,
                        "--seconds", str(cfg["seconds"]), "--tail", str(cfg["tail"])],
                       stdout=log, stderr=subprocess.STDOUT)
    newest = sorted(glob.glob(os.path.join("logs", "run_*.log")), key=os.path.getmtime)
    if newest:
        shutil.copyfile(newest[-1], os.path.join(out_root, name + ".game.log"))
    subprocess.run([sys.executable, "-m", "tools_py.parity.montage", out_dir,
                    os.path.join(out_root, name + "_sheet.png")], capture_output=True)
    if name == "title":
        return score_title(out_dir)
    if name == "transition":
        return score_transition(out_dir)
    return score_mission_log(drive_log)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="title,transition,mission")
    ap.add_argument("--owner", default="gate")
    ap.add_argument("--stamp", default=time.strftime("%Y%m%d_%H%M%S"))
    ap.add_argument("--score-title")
    ap.add_argument("--score-mission")
    args = ap.parse_args()

    if args.score_title:
        ok, detail = score_title(args.score_title)
        print("%s title (%s)" % ("PASS" if ok else "FAIL", detail))
        return 0 if ok else 1
    if args.score_mission:
        ok, detail = score_mission_log(args.score_mission)
        print("%s mission (%s)" % ("PASS" if ok else "FAIL", detail))
        return 0 if ok else 1

    take = _lock("take", args.owner)
    if take.returncode != 0:
        print("gate: lock busy: " + take.stdout.strip())
        return 2
    out_root = os.path.join("logs", "parity", "gate", args.stamp)
    os.makedirs(out_root, exist_ok=True)
    results = []
    try:
        for name in [g.strip() for g in args.only.split(",") if g.strip()]:
            ok, detail = run_gate(name, out_root)
            line = "%s %s (%s)" % ("PASS" if ok else "FAIL", name, detail)
            print(line, flush=True)
            results.append((ok, line))
    finally:
        _lock("release", args.owner)
    with open(os.path.join(out_root, "summary.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(line for _, line in results) + "\n")
    failed = [line for ok, line in results if not ok]
    print("GATE %s (%d/%d) -> %s" % ("FAIL" if failed else "PASS", len(results) - len(failed), len(results), out_root))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
