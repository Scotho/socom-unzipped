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

Real-run fixtures (Sprint 13 H7), for the test_gate cases that used to skip without logs/:
  mission/frozen(.drive.txt), mission/failed(.drive.txt), mission/probe5 (beside good.drive.txt) and
  transition_runs/tfix3, transition_runs/wcap2 -- see REAL_MISSION_RUNS / REAL_TRANSITION_RUNS below. Each is
  scored after it is written and must reach its source's verdict.

Usage (from the repo root):
  python -m tools_py.parity.make_gate_fixtures [--only BUILDER ...] [--search DIR ...]
  e.g. the H7 set from the archives, 2026-09-25:
  python -m tools_py.parity.make_gate_fixtures --only real_mission real_transition
      --search D:/socom_archive/parity --search D:/socom_archive          (one line)

Re-run any time the source runs change; it overwrites what the builders it runs write.
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


# Sprint 13 H7: the test_gate cases that skipped unless a real run sat under logs/ (harness audit #35). Their
# runs live on only in archives, so the source is looked up under SEARCH -- logs/parity first, then every
# --search directory, each standing in for logs/parity (D:/socom_archive/parity and D:/socom_archive held them
# on 2026-09-25). Each fixture is scored after it is written and must reach the verdict its full-size source
# reaches, or this script stops rather than ship a fixture that says something the run did not.
SEARCH = [os.path.join(ROOT, "logs", "parity")]

# fixture name: (drive log, capture dir) relative to a search root; the captures are every hold plus final.png.
# Captures at 320x224 in a 64-colour palette, as small as the verdict allows -- except a capture that shows the MISSION
# FAILURE banner, which mission_fail.detect does not find at 320x224 (measured 2026-09-25): it keeps the source's own
# size (640x451 for s5_head_1x_b), and identical captures are stored once (shared.txt, materialize()).
REAL_MISSION_RUNS = {
    "frozen": ("gate/s5_gatefix/mission.drive.log", "gate/s5_gatefix/mission"),     # R34: 0 live hold pairs
    "failed": ("gate/s5_head_1x_b/mission.drive.log", "gate/s5_head_1x_b/mission"),  # the MISSION FAILURE screen
    # the known-good run whose trimmed log is already mission/good.drive.txt: only its captures are new
    "probe5": ("drive_gameplay_probe5.txt", "runs/gameplay_probe5"),
}
# fixture name: transition capture dir relative to a search root. Kept: every black-screen frame of the run (the
# boot's included -- they are what the burst-step filter must drop) and the first capture of the observed burst.
REAL_TRANSITION_RUNS = {
    "tfix3": "gate/tfix3/transition",   # clean: 18 black-screen frames at/after s11
    "wcap2": "gate/wcap2/transition",   # stalled on the memory-card dialog: every black frame is the boot's
}


def find_source(rel):
    for base in SEARCH:
        path = os.path.join(base, rel)
        if os.path.exists(path):
            return path
    raise SystemExit("make_gate_fixtures: %s is under none of %s (pass --search <dir standing in for logs/parity>)"
                     % (rel, SEARCH))


SHARED = "shared.txt"


def _share_duplicates(out_dir):
    """Keep one file per identical capture and list the others in shared.txt as `<name> <kept name>` (a symlink is not
    portable to a Windows checkout). s5_head_1x_b's s38, s40 and final.png are the same full-size MISSION FAILURE
    frame, 101 KB each."""
    seen, lines = {}, []
    for n in sorted(os.listdir(out_dir)):
        with open(os.path.join(out_dir, n), "rb") as f:
            data = f.read()
        if data in seen:
            os.remove(os.path.join(out_dir, n))
            lines.append("%s %s" % (n, seen[data]))
        else:
            seen[data] = n
    if lines:
        with open(os.path.join(out_dir, SHARED), "w", newline="\n", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


def materialize(fixture_dir, dest):
    """The fixture as a run directory the scorer can read: every file copied into dest, and each shared.txt line
    `<name> <kept name>` written as its own copy. Returns dest."""
    os.makedirs(dest, exist_ok=True)
    for n in os.listdir(fixture_dir):
        if n != SHARED:
            shutil.copyfile(os.path.join(fixture_dir, n), os.path.join(dest, n))
    shared = os.path.join(fixture_dir, SHARED)
    if os.path.isfile(shared):
        with open(shared, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    name, kept = line.split()
                    shutil.copyfile(os.path.join(fixture_dir, kept), os.path.join(dest, name))
    return dest


def build_real_mission_fixtures():
    import tempfile
    out_root = os.path.join(FIXTURES, "mission")
    from tools_py.parity import mission_fail
    for name, (log_rel, caps_rel) in REAL_MISSION_RUNS.items():
        src_log, src_caps = find_source(log_rel), find_source(caps_rel)
        want_ok, want_detail = gate.score_mission_log(src_log, src_caps)
        caps = sorted(n for n in os.listdir(src_caps) if re.match(r"^s\d\d_hold\w*\.png$", n))
        if os.path.isfile(os.path.join(src_caps, "final.png")):
            caps.append("final.png")
        log = os.path.join(out_root, name + ".drive.txt") if name != "probe5" else os.path.join(out_root, "good.drive.txt")
        if name != "probe5":
            with open(log, "w", newline="\n", encoding="utf-8") as f:
                f.write("\n".join(_trim_mission_log(src_log)) + "\n")
        out_dir = os.path.join(out_root, name)
        if os.path.isdir(out_dir):
            shutil.rmtree(out_dir)
        os.makedirs(out_dir)
        for cap in caps:
            banner = mission_fail.detect(os.path.join(src_caps, cap))[0]
            with Image.open(os.path.join(src_caps, cap)) as im:
                rgb = im.convert("RGB")
                rgb = rgb if banner else rgb.resize((320, 224), Image.BOX)
                rgb.quantize(colors=64, method=Image.MEDIANCUT).save(os.path.join(out_dir, cap), optimize=True)
        _share_duplicates(out_dir)
        with tempfile.TemporaryDirectory() as tmp:
            ok, detail = gate.score_mission_log(log, materialize(out_dir, os.path.join(tmp, name)))
        failed_screen = "MISSION FAILED on screen" in want_detail
        if ok != want_ok or failed_screen != ("MISSION FAILED on screen" in detail):
            raise SystemExit("mission fixture %s: the source says (%s, %s) and the fixture (%s, %s)"
                             % (name, want_ok, want_detail, ok, detail))
        print("mission/%s: %d captures (%d files) from %s; verdict %s as the source's: %s"
              % (name, len(caps), len(os.listdir(out_dir)), src_caps, "PASS" if ok else "FAIL", detail.split("; CONSOLE")[0]))


def build_real_transition_fixtures():
    for name, rel in REAL_TRANSITION_RUNS.items():
        src = find_source(rel)
        want_ok, want_detail = gate.score_transition(src)
        burst = gate.observed_burst_step(src)
        keep = []
        for n in sorted(os.listdir(src)):
            if not gate.CAPTURE_RE.match(n):
                continue
            if black_rows.examine(os.path.join(src, n))[0] or n == "s%02d_burst_000.png" % burst:
                keep.append(n)
        out_dir = os.path.join(FIXTURES, "transition_runs", name)
        if os.path.isdir(out_dir):
            shutil.rmtree(out_dir)
        os.makedirs(out_dir)
        for n in keep:
            with Image.open(os.path.join(src, n)) as im:
                im.convert("RGB").resize((320, 224), Image.BOX).save(os.path.join(out_dir, n), optimize=True)
        ok, detail = gate.score_transition(out_dir)
        count = lambda d: re.search(r"(\d+) black-screen frames examined", d).group(1)
        if ok != want_ok or count(detail) != count(want_detail):
            raise SystemExit("transition fixture %s: the source says (%s, %s) and the fixture (%s, %s)"
                             % (name, want_ok, want_detail, ok, detail))
        print("transition_runs/%s: %d of the run's captures (burst s%02d); %s as the source's: %s"
              % (name, len(keep), burst, "PASS" if ok else "FAIL", detail))


BUILDERS = {
    "title": build_title_fixtures,
    "transition": build_transition_fixtures,
    "mission": build_mission_fixtures,
    "mission_frames": build_mission_frame_fixtures,
    "real_mission": build_real_mission_fixtures,
    "real_transition": build_real_transition_fixtures,
}


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="rebuild tests/fixtures/gate from real runs")
    ap.add_argument("--only", nargs="+", choices=sorted(BUILDERS), help="these builders only (default: all)")
    ap.add_argument("--search", action="append", default=[],
                    help="a directory standing in for logs/parity for the real_* builders (repeatable)")
    args = ap.parse_args(argv)
    SEARCH.extend(args.search)
    for name in args.only or list(BUILDERS):
        BUILDERS[name]()
    total = sum(os.path.getsize(os.path.join(dp, fn))
                for dp, _, fns in os.walk(FIXTURES) for fn in fns)
    print("total fixture size: %.1f KB" % (total / 1024.0))


if __name__ == "__main__":
    main()
