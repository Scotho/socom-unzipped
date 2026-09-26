"""The PS2X_* environment a capture ran with, written beside its output in the gate's pin format (issue #38).

docs/HAZARDS.md harness, "A capture that does not record its own environment cannot prove the 'off' half of an A/B": on
2026-09-23 the W6 A/B took two walking captures, one with `PS2X_GS_NO_TEX_REVALIDATE=1`, and nothing in either run
directory could show which was which. The parity gate pins every `PS2X_*` it scores against (pins.env_pin); the
capture scripts under scripts/parity/ recorded nothing, or (audio_parity.sh, from 2026-09-23) a free-form dump. This
is the one writer they all share now -- the shell scripts through scripts/parity/write_env.sh, the Python launchers
by calling write() the moment before their launch:

  <out>/env_ps2x.txt   every PS2X_* in force, sorted `NAME=value` (PS2X_MC_DIR included -- it is a path worth
                       reading, though the pin leaves it out, as the gate's does); the `PIN env sha256=...` line in
                       the gate's summary shape; SOCOM_EXE and its sha256 (the binary's identity is half an A/B too).
  <out>/env_pins.json  the same `env` pin as a run record (pins.write_record), so pins.load_record reads it and
                       pins.compare can set two captures' halves against each other.

It is the gate's FORMAT (pins.env_pin's hashing, pins.write_record's file), not the gate's HASH: the record holds
the environment the launcher had at the moment it wrote it, BEFORE the driver's own additions -- drive.py and
online_login_ours.launch add the screenshot path, the input file, the CD image and a card directory on top, and
the gate's env pin is taken over gate.launch_env, which adds PS2X_HOST_GAMEPAD and the mission stage's PS2X_PEEK.
So two captures compare with each other; a capture's hash is not expected to equal a gate standard's.

Who writes it. Every script under scripts/parity/ that launches the game (tools_py/tests/test_capture_env holds the
rule), and the two Python modules that launch it on their own: sp_death_probe (the drive it starts) and scale_shot
(the exe it starts, one record per shot). Exempt, each covered by its caller's record:
  * drive.py, online_login_ours.py, online_match_ours.py (which launches through online_login_ours.launch) -- the
    DRIVERS. Every launch that produces evidence runs
    them from a launcher that has already written the record (the shell scripts above, sp_death_probe, the gate);
    run by hand they are a developer's session, not a capture.
  * gate.py -- it pins its own environment into the stamp's pins.json (and refuses on a drift), which is stronger.

    python -m tools_py.parity.capture_env <out_dir> [--exe PATH] [--note TEXT]
"""
import argparse
import hashlib
import os
import sys
from collections import OrderedDict

from tools_py.parity import pins

TEXT_NAME = "env_ps2x.txt"
RECORD_NAME = "env_pins.json"


def _exe_lines(exe):
    if not exe:
        return ["# no SOCOM_EXE named"]
    try:
        digest = hashlib.sha256()
        with open(exe, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                digest.update(chunk)
        return ["SOCOM_EXE=%s" % exe, "SOCOM_EXE_SHA256=%s" % digest.hexdigest()]
    except OSError:
        return ["SOCOM_EXE=%s" % exe, "# no executable at %s to hash" % exe]


def write(out_dir, env=None, exe=None, note="", prefix=""):
    """Write env_ps2x.txt and env_pins.json into `out_dir` (made if absent); return the env Pin. `prefix` names
    them `<prefix>env_ps2x.txt` / `<prefix>env_pins.json`, for a launcher that starts several games into one
    directory (scale_shot --both)."""
    env = os.environ if env is None else env
    os.makedirs(out_dir, exist_ok=True)
    pin = pins.env_pin(env)
    every = sorted("%s=%s" % (k, v) for k, v in env.items() if k.startswith("PS2X_"))
    lines = ["# the PS2X_* environment this capture ran with (tools_py/parity/capture_env.py, issue #38)"]
    if note:
        lines.append("# " + note)
    lines += every or ["# no PS2X_* in the environment"]
    lines.append("PIN env sha256=%s recorded%s" % (pin.sha256, "; " + " ".join(pin.detail) if pin.detail else ""))
    lines += _exe_lines(exe)
    with open(os.path.join(out_dir, prefix + TEXT_NAME), "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(l + "\n" for l in lines))
    exe_line = "EXE %s" % exe if exe else ""
    pins.write_record(OrderedDict([("env", pin)]), os.path.join(out_dir, prefix + RECORD_NAME),
                      verdict="RECORDED", exe=exe_line)
    return pin


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("out_dir")
    ap.add_argument("--exe", default="", help="the executable the capture launches, hashed into the record")
    ap.add_argument("--note", default="", help="a comment line: which script, at which moment")
    args = ap.parse_args(argv)
    pin = write(args.out_dir, exe=args.exe or None, note=args.note)
    print("env: %s -> %s" % (pin.sha256[:16], os.path.join(args.out_dir, TEXT_NAME)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
