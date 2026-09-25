"""The PS2X_* environment a capture ran with, written beside its output in the gate's pin format (issue #38).

KNOWN section 4, "A capture that does not record its own environment cannot prove the 'off' half of an A/B": on
2026-09-23 the W6 A/B took two walking captures, one with `PS2X_GS_NO_TEX_REVALIDATE=1`, and nothing in either run
directory could show which was which. The parity gate pins every `PS2X_*` it scores against (pins.env_pin); the
capture scripts under scripts/parity/ recorded nothing, or (audio_parity.sh, from 2026-09-23) a free-form dump. This
is the one writer they all share now, through scripts/parity/write_env.sh:

  <out>/env_ps2x.txt   every PS2X_* in force, sorted `NAME=value` (PS2X_MC_DIR included -- it is a path worth
                       reading, though the pin leaves it out, as the gate's does); the `PIN env sha256=...` line in
                       the gate's summary shape; SOCOM_EXE and its sha256 (the binary's identity is half an A/B too).
  <out>/env_pins.json  the same `env` pin as a run record (pins.write_record), so pins.load_record reads it and
                       pins.compare can set two captures' halves against each other, or against a gate standard.

The hash is pins.env_pin's, byte for byte: two captures with the same knobs pin the same, a knob more or less moves it.
What the Python drivers add per launch on top (the screenshot path, a card directory, the input file) is plumbing,
not a knob, and is not in the record -- the gate's env pin draws the same line.

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


def write(out_dir, env=None, exe=None, note=""):
    """Write env_ps2x.txt and env_pins.json into `out_dir` (made if absent); return the env Pin."""
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
    with open(os.path.join(out_dir, TEXT_NAME), "w", encoding="utf-8", newline="\n") as f:
        f.write("".join(l + "\n" for l in lines))
    exe_line = "EXE %s" % exe if exe else ""
    pins.write_record(OrderedDict([("env", pin)]), os.path.join(out_dir, RECORD_NAME),
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
