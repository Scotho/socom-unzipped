"""Build the committed fixtures under tests/fixtures/gate/ so tools_py/tests/test_gate.py's
positive cases run on a fresh clone (no logs/ dir required).

Sources (all git-ignored, kept locally from real runs -- see STATUS 2026-09-10/09-09):
  title:      logs/parity/runs/vr_title/s00_none.png .. s15_none.png  (known clean, 19/23 >= 90.0)
  transition: five frames of logs/parity/gate/tfix4/transition taken from AT OR AFTER that run's
              first burst step (gate.first_burst_step() = 11), i.e. real frames of the black
              screen before the mission briefing rather than of the boot; all peak 0 in
              black_rows.py's rows 396-448 band; gate.TRANSITION_MIN_FRAMES is 5
  mission:    logs/parity/drive_gameplay_probe5.txt (HUD matched=True, known good) and
              logs/parity/vr_gameplay.drive.log (HUD matched=False, known bad)
  mission frames (gate.score_mission_log checks the hold captures, R30 2026-09-13):
              s3a/   -- logs/parity/gate/s3a: HUD after 4 presses, s30/s32/s34 holds are live gameplay
              dbuff/ -- logs/parity/gate/s5_task4_dbuff: HUD "matched" after 0 presses on the
                        letterboxed intro cinematic; s30/s32/s34 holds are that cinematic, and
                        final.png is gameplay behind a HELP pop-up (band test must accept it)

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

from tools_py.parity import black_rows, compare, gate

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURES = os.path.join(ROOT, "tests", "fixtures", "gate")
TITLE_REF = os.path.join(ROOT, "scripts", "parity", "ref_main_menu_ours.png")

TITLE_SRC_DIR = os.path.join(ROOT, "logs", "parity", "runs", "vr_title")
TITLE_NAMES = ["s%02d_none.png" % i for i in range(16)]  # s00..s15: the TITLE_MIN_MATCHES floor

TRANSITION_SRC_DIR = os.path.join(ROOT, "logs", "parity", "gate", "tfix4", "transition")
# (source name in that run, fixture name) -- all confirmed peak 0 in black_rows.py's default band.
# Five frames, because gate.TRANSITION_MIN_FRAMES is 5, so the fixture test also pins the floor.
# Every one is at or after tfix4's first burst step (11), which is what score_transition examines:
# four of the 5 fps burst frames spread across the fade and one of the 1 Hz w<step>_<k>.png wait
# captures that follow it. Names are kept as they were in the run -- the step index in the name is
# load-bearing now, a fixture named s02_* would be filtered out as boot. build_transition_fixtures
# re-checks that below and refuses to write a fixture from before the burst step.
TRANSITION_PAIRS = [(n, n) for n in ("s11_burst_002.png", "s11_burst_006.png",
                                     "s11_burst_010.png", "s11_burst_015.png", "w13_000.png")]

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
    # The fixture has to be able to pass the gate it is a fixture for, and the gate only examines
    # frames from the burst step on, so a fixture from before it would be silently filtered out
    # and the "5 frames examined" assertion would fail with no explanation. Check it here instead.
    burst = gate.first_burst_step()
    early = [n for n, _ in TRANSITION_PAIRS
             if burst is not None and black_rows.step_index(n) < burst]
    if early:
        raise SystemExit("transition fixtures %s are before the probe's burst step (%s): "
                         "score_transition would not examine them" % (early, burst))
    for name in os.listdir(out_dir):        # drop fixtures of a previous, differently-named set
        if name.endswith(".png") and name not in {d for _, d in TRANSITION_PAIRS}:
            os.remove(os.path.join(out_dir, name))
    for src_name, dst_name in TRANSITION_PAIRS:
        with Image.open(os.path.join(TRANSITION_SRC_DIR, src_name)) as im:
            im.convert("RGB").resize((320, 224), Image.BOX).save(os.path.join(out_dir, dst_name))
    print("transition: %d fixtures at 320x224, all at/after burst step %s (from %s)"
          % (len(TRANSITION_PAIRS), burst, TRANSITION_SRC_DIR))


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


MISSION_FRAME_RUNS = {
    # fixture name: (source run dir, captures to copy)
    "s3a": (os.path.join(ROOT, "logs", "parity", "gate", "s3a"),
            ["s30_holdW.png", "s32_holdR1.png", "s34_holdR1.png"]),
    "dbuff": (os.path.join(ROOT, "logs", "parity", "gate", "s5_task4_dbuff"),
              ["s30_holdW.png", "s32_holdR1.png", "s34_holdR1.png", "final.png"]),
}


def build_mission_frame_fixtures():
    """<name>.drive.txt (the trimmed drive log) + <name>/ (hold captures at 320x224, palette PNG)
    for each run in MISSION_FRAME_RUNS. The log keeps only the sNN_hold lines whose capture is copied:
    the scorer checks the capture count against the logged hold count (R34), so a fixture that ships
    3 of 6 captures must also log 3 holds. The band test (screen_bands.py) scales its rows with the
    frame height, and palette quantization keeps pure-black letterbox rows at 0, so the verdicts
    are checked on the saved files here rather than assumed."""
    from tools_py.parity import screen_bands
    out_root = os.path.join(FIXTURES, "mission")
    for name, (src_run, caps) in MISSION_FRAME_RUNS.items():
        kept = {c.split(".")[0] for c in caps}
        lines = [ln for ln in _trim_mission_log(os.path.join(src_run, "mission.drive.log"))
                 if not re.match(r"^s\d\d_hold", ln) or ln.split()[0] in kept]
        with open(os.path.join(out_root, name + ".drive.txt"), "w", newline="\n", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        out_dir = os.path.join(out_root, name)
        os.makedirs(out_dir, exist_ok=True)
        for cap in caps:
            dst = os.path.join(out_dir, cap)
            with Image.open(os.path.join(src_run, "mission", cap)) as im:
                _save_quantized(im.convert("RGB").resize((320, 224), Image.BOX), dst)
            with Image.open(os.path.join(src_run, "mission", cap)) as full, Image.open(dst) as small:
                print("  %s/%-16s %5.1f KB  band %.2f (full %.2f)" % (
                    name, cap, os.path.getsize(dst) / 1024.0,
                    screen_bands.gameplay_band(small)[1], screen_bands.gameplay_band(full)[1]))


def main():
    build_title_fixtures()
    build_transition_fixtures()
    build_mission_fixtures()
    build_mission_frame_fixtures()
    total = sum(os.path.getsize(os.path.join(dp, fn))
                for dp, _, fns in os.walk(FIXTURES) for fn in fns)
    print("total fixture size: %.1f KB" % (total / 1024.0))


if __name__ == "__main__":
    main()
