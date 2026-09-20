"""An audio parity test against PCSX2, in the shape of the visual gate (owner, 2026-09-20: "an audio parity test
with psx2 like our visual parity test").

The visual gate scores our frames against reference frames at aligned steps. This scores our SOUND against the
console's at aligned steps: the same step script drives both targets (`drive.py --target pcsx2|ours`), a WASAPI
loopback records what each sends to the speaker (`loopback_record.py`), the drive's step times cut each capture
into per-step windows, `audio_envelope` scores every window (level, silences, sub-second holes, splices, envelope
oscillation), and `compare()` fails any window where ours exceeds the console's by more than a tolerance. The
console's scores are pinned as a JSON reference beside the visual refs, so a change in our audio has to move a
number that a person pinned on purpose.

Pure half (this module, tested): windows, scoring, comparison, the JSON. The capture half is the existing drive
and recorder, sequenced by `scripts/parity/audio_parity.sh`.

    python -m tools_py.parity.audio_parity score   <capture.wav> <rate> <drive.stdout> <offset_s> <out.json> [--target T --script S]
    python -m tools_py.parity.audio_parity compare <ref.json> <ours.json>
"""
import json
import re
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from tools_py.parity import audio_envelope as ae

_STEP = re.compile(r"^(s\d+)_\S+\s+t=\s*([0-9.]+)s")


@dataclass
class Window:
    label: str
    start: float
    end: Optional[float]   # None: to the end of the capture


def step_windows(drive_stdout_text: str, capture_offset_s: float = 0.0) -> List[Window]:
    """One window per drive step, from that step's time to the next step's, shifted by how long the capture
    started before the drive (`capture_offset_s`, positive when the recorder started first)."""
    times = []
    for line in drive_stdout_text.splitlines():
        m = _STEP.match(line.strip())
        if m:
            times.append((m.group(1), float(m.group(2)) + capture_offset_s))
    out: List[Window] = []
    for i, (label, t) in enumerate(times):
        end = times[i + 1][1] if i + 1 < len(times) else None
        out.append(Window(label, t, end))
    return out


def score_window(mono: np.ndarray, rate: int) -> Dict[str, float]:
    """The five numbers a window is judged on. All reference-free; all from audio_envelope."""
    if len(mono) < rate // 10:
        return {"rms_db": -90.0, "silences": 0, "silence_s": 0.0, "holes": 0, "splices": 0, "osc": 0.0}
    rms = float(np.sqrt(np.mean(mono.astype(np.float64) ** 2)))
    rms_db = 20.0 * np.log10(rms / 32768.0 + 1e-12)
    sil = ae.silences(mono, rate)
    holes = sum(1 for _, d in sil if d < 0.6)
    env = ae.envelope(mono, rate)
    osc = float(ae.oscillation_score(env)) if len(env) > 4 else 0.0
    spl = ae.splices(mono, rate)
    return {"rms_db": round(float(rms_db), 2), "silences": len(sil), "silence_s": round(float(sum(d for _, d in sil)), 2),
            "holes": holes, "splices": len(spl), "osc": round(osc, 2)}


def score_capture(mono: np.ndarray, rate: int, windows: List[Window]) -> Dict[str, Dict[str, float]]:
    total = len(mono) / rate
    out = {}
    for w in windows:
        a = max(0.0, w.start)
        b = total if w.end is None else min(total, w.end)
        if b - a < 0.5:
            continue
        out[w.label] = score_window(mono[int(a * rate):int(b * rate)], rate)
    return out


# Tolerances: what "the same as the console" means per metric. Absolute slack plus a proportion of the
# reference, so a window the console fills with gunfire (many splices) is judged on its own scale.
TOLERANCE = {
    "rms_db": 6.0,          # ours may sit within 6 dB of the console (different mixes, same shape)
    "silences": (2, 0.5),   # count: ref + 2 + 50%
    "silence_s": (1.0, 0.5),
    "holes": (2, 0.5),      # sub-second holes are the device-path signature: 41 against 0 fails at once
    "splices": (5, 0.5),
    "osc": (3.0, 0.5),      # dB of envelope wobble in the 0.2-3 Hz band
}


@dataclass
class Verdict:
    passed: bool
    lines: List[str] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)


def compare(ref: Dict[str, Dict[str, float]], ours: Dict[str, Dict[str, float]], tolerance=TOLERANCE) -> Verdict:
    v = Verdict(True)
    for label, r in ref.items():
        o = ours.get(label)
        if o is None:
            v.failures.append(f"{label}: missing on our side")
            v.lines.append(f"FAIL {label}: no window scored on our side")
            continue
        bad = []
        for k, tol in tolerance.items():
            if k not in r or k not in o:
                continue
            if k == "rms_db":
                if abs(o[k] - r[k]) > tol:
                    bad.append(f"{k} {o[k]} vs {r[k]} (+/-{tol})")
            else:
                slack, frac = tol
                limit = r[k] + slack + frac * r[k]
                if o[k] > limit:
                    bad.append(f"{k} {o[k]} > {limit:.1f} (ref {r[k]})")
        if bad:
            v.failures.append(f"{label}: " + "; ".join(bad))
            v.lines.append(f"FAIL {label}: " + "; ".join(bad))
        else:
            v.lines.append(f"PASS {label}: holes {o['holes']}/{r['holes']} splices {o['splices']}/{r['splices']} "
                           f"osc {o['osc']}/{r['osc']} rms {o['rms_db']}/{r['rms_db']}")
    v.passed = not v.failures
    return v


def save_scores(scores, path, meta=None):
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"meta": meta or {}, "scores": scores}, fh, indent=1, sort_keys=True)


def load_scores(path):
    with open(path, encoding="utf-8") as fh:
        d = json.load(fh)
    return d["scores"], d.get("meta", {})


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[-2:]); return 2
    cmd = argv[1]
    if cmd == "score":
        wav, rate, stdout, offset, out = argv[2], int(argv[3]), argv[4], float(argv[5]), argv[6]
        meta = {}
        for flag in ("--target", "--script"):
            if flag in argv:
                meta[flag[2:]] = argv[argv.index(flag) + 1]
        mono = ae.read_mono(wav)
        windows = step_windows(open(stdout, encoding="utf-8", errors="replace").read(), offset)
        scores = score_capture(mono, rate, windows)
        meta.update({"wav": wav, "rate": rate, "windows": len(scores)})
        save_scores(scores, out, meta)
        for label, s in scores.items():
            print(f"{label}: rms {s['rms_db']} dB, silences {s['silences']} ({s['silence_s']} s), holes {s['holes']}, splices {s['splices']}, osc {s['osc']}")
        return 0
    if cmd == "compare":
        ref, _ = load_scores(argv[2]); ours, _ = load_scores(argv[3])
        v = compare(ref, ours)
        print("\n".join(v.lines))
        print(f"AUDIO PARITY {'PASS' if v.passed else 'FAIL'}: {len(ref) - len(v.failures)}/{len(ref)} windows within tolerance")
        return 0 if v.passed else 1
    print("unknown command", cmd); return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
