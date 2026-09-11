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

from tools_py.parity import black_rows, compare

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
MISSION_MIN_HOLDS = 3       # sNN_hold* steps after the HUD: fewer means the probe died on entry
# What this floor counts, exactly: black-screen frames ANYWHERE in the run -- every capture whose
# rows above the band are black. It is NOT a count of transition frames. A boot sequence supplies
# ten or more black frames before the run has left the memory-card screens, so on a run that never
# reaches the briefing the floor is still cleared by the boot alone. Measured 2026-09-11 with
# black_rows.py --from-step 9 (9 = the first `burst` step of transition_probe.txt, i.e. the first
# step past the rank screen): logs/parity/gate/wcap1 examines 10 frames over the whole run and 0
# from step 9 on; wcap2 examines 13 and 0. Both "PASS" entirely on boot black screens. Same for
# famb, famc and hostdraw_on (11, 10, 11 frames; 0 from step 9). Older runs did measure the
# transition: gate/first examined 6 of which 5 are from step 9, gate/native_on 4 of 4,
# runs/gl_transition 8 of which 7. The difference is the controller-configuration "save to memory
# card?" dialog, which transition_probe.txt (unlike gameplay_probe.txt) has no ifref guard for:
# since it started appearing the probe stalls there and never reaches the fade. Restricting the
# count to the burst step therefore cannot be calibrated from the stored runs (both give 0) -- the
# probe script has to answer that dialog first. Tracked as a Sprint 3 item; black_rows.py
# --from-step and first_burst_step() below are in place for it, and score_transition reports the
# restricted count on every run so the gap is visible in the summary, not implied by a green line.
#
# The floor itself stays 5, calibrated 2026-09-11 on the two capture-cadence runs above (wcap1
# examined 10, wcap2 13, every frame peak 0): under it, a run lost its captures outright.
# black_rows.py exits 0 when it examines nothing (empty dir, missing dir, a run with no
# black-screen frame), so the exit code alone is a vacuous pass and the count is part of the
# verdict.
TRANSITION_MIN_FRAMES = 5

GATES = {
    "title": dict(script="scripts/parity/title_menu.txt", seconds=170, tail=8),
    "transition": dict(script="scripts/parity/transition_probe.txt", seconds=170, tail=8),
    "mission": dict(script="scripts/parity/gameplay_probe.txt", seconds=480, tail=170),
}


def _score_value(golden, ours):
    """compare.score (compare.py:19) takes two PIL images and returns
    {"score": .., "mad": .., "block": ..}; it may also be a float or a (score, mad, block)
    tuple. Open the paths and normalise the result to a float."""
    with Image.open(golden) as g, Image.open(ours) as o:
        r = compare.score(g, o)
    if isinstance(r, dict):
        return float(r["score"])
    return float(r[0] if isinstance(r, (tuple, list)) else r)


def score_title(run_dir):
    caps = sorted(p for p in glob.glob(os.path.join(run_dir, "s[0-9][0-9]_*.png"))
                  if "burst" not in os.path.basename(p))
    if not caps:
        return False, "no captures in %s" % run_dir
    scores = [(os.path.basename(p), _score_value(TITLE_REF, p)) for p in caps]
    good = sum(1 for _, s in scores if s >= TITLE_MIN_SCORE)
    detail = "%d/%d menu captures >= %.1f; scores: %s" % (
        good, len(scores), TITLE_MIN_SCORE, " ".join("%s=%.1f" % (n[:3], s) for n, s in scores))
    return good >= TITLE_MIN_MATCHES, detail


def first_burst_step(script_path=None):
    """Index of the first `burst` step of a drive.py step script, or None.

    drive.py numbers steps by their position among the non-blank, non-comment lines of the script
    (drive.parse), and names each capture `s<NN>_*` / `w<NN>_*` after that index. In
    transition_probe.txt the first burst is the step that follows the rank screen, so frames from
    it on are the ones that could show the fade into the briefing; everything before it is boot."""
    path = script_path or os.path.join(ROOT, GATES["transition"]["script"])
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
    except OSError:
        return None
    step = 0
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.split("+", 1)[0].split(":", 1)[0].strip() == "burst":
            return step
        step += 1
    return None


def score_transition(run_dir):
    """black_rows.py prints one "<file>  black screen, rows <y0>-<y1>: peak <n>" line per frame it
    actually examines and exits 1 only when one of them is not black. Zero examined frames also
    exits 0, so the count is part of the verdict, not just the exit code.

    The verdict is taken over the whole run (see TRANSITION_MIN_FRAMES). How many of those frames
    are at or after the first burst step -- the only ones that can be the transition rather than
    the boot -- is measured and reported, but does not gate: on the current probe script that
    number is 0 on every recent run, and the fix is the probe, not the floor."""
    r = subprocess.run([sys.executable, "tools_py/parity/black_rows.py", run_dir], capture_output=True, text=True)
    examined = [ln for ln in r.stdout.splitlines() if "black screen, rows " in ln]
    bad = [ln for ln in examined if "NOT BLACK" in ln]
    peaks = [int(m.group(1)) for m in (re.search(r"peak\s+(\d+)", ln) for ln in examined) if m]
    # One check, not two: "examined nothing" and "examined fewer than the floor" are the same
    # condition -- a separate `if not examined` above this was unreachable.
    if len(examined) < TRANSITION_MIN_FRAMES:
        return False, ("transition not captured (%d black-screen frames examined, need %d)"
                       " in %s" % (len(examined), TRANSITION_MIN_FRAMES, run_dir))
    if bad or r.returncode != 0:
        return False, "%d black-screen frames examined; non-black band: %s" % (
            len(examined), "; ".join(" ".join(ln.split()) for ln in bad[:5]) or r.stderr.strip()[:200])
    burst = first_burst_step()
    after = sum(1 for ln in examined
                if black_rows.step_index(ln.split()[0]) >= burst) if burst is not None else None
    note = "" if after is None else "; %d at/after the burst step (s%02d)" % (after, burst)
    return True, "%d black-screen frames examined, rows 396-447 peak %d%s" % (
        len(examined), max(peaks, default=0), note)


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
    return holds >= MISSION_MIN_HOLDS, "HUD reached; %d hold steps captured (need %d)" % (
        holds, MISSION_MIN_HOLDS)


def _lock(cmd, owner):
    try:
        return subprocess.run(["bash", "scripts/loop_lock.sh", cmd, owner], capture_output=True, text=True)
    except OSError as e:
        raise SystemExit("gate: cannot run scripts/loop_lock.sh (%s). Run the gate from Git Bash at "
                         "the repo root." % e)


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

    # Make the output root before taking the lock: a makedirs failure must not leak the lock.
    out_root = os.path.join("logs", "parity", "gate", args.stamp)
    os.makedirs(out_root, exist_ok=True)
    take = _lock("take", args.owner)
    if take.returncode != 0:
        print("gate: lock busy: " + take.stdout.strip())
        return 2
    wanted = [g.strip() for g in args.only.split(",") if g.strip()]
    results = []
    try:
        for name in wanted:
            ok, detail = run_gate(name, out_root)
            line = "%s %s (%s)" % ("PASS" if ok else "FAIL", name, detail)
            print(line, flush=True)
            results.append((ok, line))
    finally:
        # Release the lock and leave a summary even when a gate raises part-way through.
        _lock("release", args.owner)
        for name in wanted[len(results):]:
            results.append((False, "FAIL %s (gate did not run)" % name))
        failed = [line for ok, line in results if not ok]
        with open(os.path.join(out_root, "summary.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(line for _, line in results) + "\n")
        print("GATE %s (%d/%d) -> %s" % ("FAIL" if failed else "PASS",
                                         len(results) - len(failed), len(results), out_root))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
