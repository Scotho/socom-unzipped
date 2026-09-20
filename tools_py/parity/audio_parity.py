"""An audio parity test against PCSX2, in the shape of the visual gate (owner, 2026-09-20: "an audio parity test
with psx2 like our visual parity test").

The visual gate scores our frames against reference frames at aligned steps. This scores our SOUND against the
console's at aligned steps: the same step script drives both targets (`drive.py --target pcsx2|ours`), a WASAPI
loopback records what each sends to the speaker (`loopback_record.py`), the drive's step times cut each capture
into per-step windows, `audio_envelope` scores every window (level, silences, sub-second holes, splices, envelope
oscillation), and `compare()` fails any window where ours exceeds the console's by more than a tolerance. The
console's scores are pinned as a JSON reference beside the visual refs, so a change in our audio has to move a
number that a person pinned on purpose.

Round four (2026-09-20, the owner's "it doesn't even sound like music"): the level numbers above passed a
capture whose two channels of every stereo VAG stream played OUT OF SYNC -- level, wobble, splices and silences
all read the same on both machines. So each window also carries a CONTENT measure of the stereo pair:
`lr_corr0` (L against R at lag 0), `lr_lag_ms` / `lr_best` (the best lag within +/-2 s and the correlation
there; positive = R lags L) and `side_mid_db` (side/mid energy). The console's music correlates at lag 0
(+0.26..+0.59); ours read ~0 at lag 0 with the best match at +61 / -561 / +674 ms. `compare()` fails a window
where the console is aligned and ours is aligned somewhere else ("stereo desync").

Pure half (this module, tested): windows, scoring, comparison, the JSON. The capture half is the existing drive
and recorder, sequenced by `scripts/parity/audio_parity.sh`.

    python -m tools_py.parity.audio_parity score   <capture.wav> <rate> <drive.stdout> <offset_s> <out.json> [--target T --script S]
    python -m tools_py.parity.audio_parity compare <ref.json> <ours.json>
"""
import json
import re
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

from tools_py.parity import audio_envelope as ae
from tools_py.parity.audio_corr import read_wav

_STEP = re.compile(r"^(s\d+)_\S+\s+t=\s*([0-9.]+)s")

# -- stereo alignment (the content measure) ----------------------------------------------------------------
STEREO_RATE = 4000.0        # L and R are decimated to about this before the lag search (block mean, so the
                            # music below ~2 kHz is what correlates; 48 kHz -> 4000 Hz, 44.1 kHz -> 4009 Hz)
STEREO_MAX_LAG_MS = 2000.0  # the lag search: +/-2 s, capped at half the window
STEREO_MIN_S = 2.0          # a shorter window reports null: too little music for a 2 s lag search
STEREO_FLOOR_DB = -60.0     # a quieter window reports null: silence has no alignment
STEREO_DB_CLAMP = 90.0      # side/mid of an identical pair is -inf; it is reported as -90 (16-bit's floor)
STEREO_KEYS = ("lr_corr0", "lr_lag_ms", "lr_best", "side_mid_db")
STEREO_NULL: Dict[str, Optional[float]] = {k: None for k in STEREO_KEYS}


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


def _decimate(x: np.ndarray, rate: float, target: float = STEREO_RATE) -> Tuple[np.ndarray, float]:
    """`x` block-averaged by the integer factor nearest rate/target; returns (samples, their rate)."""
    n = max(1, int(round(rate / float(target))))
    count = len(x) // n
    if count == 0:
        return np.zeros(0, dtype=np.float64), rate / float(n)
    return x[:count * n].reshape(count, n).mean(axis=1), rate / float(n)


def lr_alignment(left: np.ndarray, right: np.ndarray, rate: float,
                 max_lag_ms: float = STEREO_MAX_LAG_MS) -> Tuple[float, float, float]:
    """(corr0, lag_ms, best): L against R decimated to ~4 kHz, the normalised cross-correlation at lag 0, and
    the lag within +/-`max_lag_ms` (capped at half the window) where it is largest, with its value.

    Sign convention: `lag_ms` is POSITIVE when R LAGS L -- when R[t] = L[t - lag], i.e. the right channel plays
    what the left played `lag` earlier. corr(k) = sum_t L[t] * R[t + k] over the samples the two overlap at
    that lag, divided by the square root of the product of their energies over the same overlap (means
    removed first), so every value is in [-1, 1] and a lag near the search edge is not penalised for the
    samples it cannot overlap. One channel digitally silent reads as 0.0 everywhere (nothing to align).
    """
    dl, drate = _decimate(np.asarray(left, dtype=np.float64), rate)
    dr, _ = _decimate(np.asarray(right, dtype=np.float64), rate)
    n = min(len(dl), len(dr))
    if n < 2:
        return 0.0, 0.0, 0.0
    l = dl[:n] - dl[:n].mean()
    r = dr[:n] - dr[:n].mean()
    if not (l * l).sum() > 0.0 or not (r * r).sum() > 0.0:
        return 0.0, 0.0, 0.0
    max_lag = min(int(round(max_lag_ms / 1000.0 * drate)), n // 2)
    size = 1
    while size < 2 * n:
        size *= 2
    # c[k] = sum_t l[t] r[t+k] for k >= 0 at index k; the negative lags sit at the tail (index size + k).
    # Zero-padding to 2n makes the circular product linear.
    c = np.fft.irfft(np.fft.rfft(r, size) * np.conj(np.fft.rfft(l, size)), size)
    lags = np.arange(-max_lag, max_lag + 1)
    values = np.concatenate((c[size - max_lag:size] if max_lag > 0 else c[:0], c[:max_lag + 1]))
    # The overlap at lag k >= 0 is l[0:n-k] against r[k:n]; at k < 0 it is l[-k:n] against r[0:n+k]. Their
    # energies come from the two cumulative sums.
    cl = np.concatenate(([0.0], np.cumsum(l * l)))
    cr = np.concatenate(([0.0], np.cumsum(r * r)))
    pos = lags >= 0
    energy_l = np.where(pos, cl[n - np.abs(lags)], cl[n] - cl[np.abs(lags)])
    energy_r = np.where(pos, cr[n] - cr[np.abs(lags)], cr[n - np.abs(lags)])
    scale = np.sqrt(energy_l * energy_r)
    corr = np.where(scale > 0.0, values / np.where(scale > 0.0, scale, 1.0), 0.0)
    corr = np.clip(corr, -1.0, 1.0)     # rounding only: Cauchy-Schwarz bounds the exact value
    best = int(np.argmax(corr))
    return float(corr[max_lag]), float(lags[best]) * 1000.0 / drate, float(corr[best])


def side_mid_db(left: np.ndarray, right: np.ndarray) -> float:
    """10*log10 of side energy over mid energy, side = (L-R)/2 and mid = (L+R)/2, clamped to +/-90 dB.

    An identical pair is -90 (no side); an uncorrelated pair of equal power is 0; the console's music reads
    about -2 dB where ours' desynced pair read ~0.
    """
    l = np.asarray(left, dtype=np.float64)
    r = np.asarray(right, dtype=np.float64)
    mid = (l + r) * 0.5
    side = (l - r) * 0.5
    em = float(np.mean(mid * mid))
    es = float(np.mean(side * side))
    db = 10.0 * np.log10(max(es, 1e-12) / max(em, 1e-12))
    return float(min(STEREO_DB_CLAMP, max(-STEREO_DB_CLAMP, db)))


def stereo_window(left: np.ndarray, right: np.ndarray, rate: int) -> Dict[str, Optional[float]]:
    """The content measure of one window's stereo pair, or every key null when the window is shorter than
    STEREO_MIN_S or its mix is quieter than STEREO_FLOOR_DB."""
    n = min(len(left), len(right))
    if n < STEREO_MIN_S * rate:
        return dict(STEREO_NULL)
    mono = (np.asarray(left[:n], dtype=np.float64) + np.asarray(right[:n], dtype=np.float64)) * 0.5
    rms = float(np.sqrt(np.mean(mono * mono)))
    if 20.0 * np.log10(rms / 32768.0 + 1e-12) < STEREO_FLOOR_DB:
        return dict(STEREO_NULL)
    corr0, lag_ms, best = lr_alignment(left[:n], right[:n], rate)
    return {"lr_corr0": round(corr0, 3), "lr_lag_ms": round(lag_ms, 1), "lr_best": round(best, 3),
            "side_mid_db": round(side_mid_db(left[:n], right[:n]), 2)}


def score_capture(mono: np.ndarray, rate: int, windows: List[Window],
                  stereo: Optional[Tuple[np.ndarray, np.ndarray]] = None) -> Dict[str, Dict[str, float]]:
    """Every window's scores. `stereo` is the (left, right) pair the mono was averaged from; without it (a
    mono capture) the stereo keys are present and null."""
    total = len(mono) / rate
    out = {}
    for w in windows:
        a = max(0.0, w.start)
        b = total if w.end is None else min(total, w.end)
        if b - a < 0.5:
            continue
        lo, hi = int(a * rate), int(b * rate)
        s = score_window(mono[lo:hi], rate)
        s.update(stereo_window(stereo[0][lo:hi], stereo[1][lo:hi], rate) if stereo is not None else STEREO_NULL)
        out[w.label] = s
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

# The stereo-desync rule: the console's pair is aligned (lag-0 correlation at least REF_ALIGNED) and ours has
# lost that alignment (under OURS_LOST at lag 0) but is aligned SOMEWHERE ELSE (at least OURS_ELSEWHERE at a
# lag beyond LAG_MS) -- the signature of two channel cursors that started apart. Ours simply decorrelated
# everywhere is not this fault and is left to the other numbers.
STEREO_RULE = {"ref_aligned": 0.15, "ours_lost": 0.05, "ours_elsewhere": 0.15, "lag_ms": 20.0}


@dataclass
class Verdict:
    passed: bool
    lines: List[str] = field(default_factory=list)
    failures: List[str] = field(default_factory=list)
    stereo_skipped: int = 0     # windows where the stereo rule had no lr_corr0 on one side


def stereo_desync(r: Dict[str, float], o: Dict[str, float], rule=STEREO_RULE) -> Tuple[bool, Optional[str]]:
    """(evaluated, failure). Not evaluated when either side lacks `lr_corr0` (an older reference, a mono
    capture, a window under STEREO_MIN_S or STEREO_FLOOR_DB); the failure text when the rule trips."""
    rc, oc = r.get("lr_corr0"), o.get("lr_corr0")
    if rc is None or oc is None:
        return False, None
    best = o.get("lr_best") or 0.0
    lag = o.get("lr_lag_ms") or 0.0
    if rc >= rule["ref_aligned"] and oc < rule["ours_lost"] and best >= rule["ours_elsewhere"] \
            and abs(lag) > rule["lag_ms"]:
        return True, f"stereo desync: ours best {lag:+.0f} ms (corr {best:.2f}, lag0 {oc:.2f}) vs ref lag0 {rc:.2f}"
    return True, None


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
        evaluated, desync = stereo_desync(r, o)
        if not evaluated:
            v.stereo_skipped += 1
        elif desync:
            bad.append(desync)
        if bad:
            v.failures.append(f"{label}: " + "; ".join(bad))
            v.lines.append(f"FAIL {label}: " + "; ".join(bad))
        else:
            lr = f" lr0 {o['lr_corr0']}/{r['lr_corr0']}" if evaluated else ""
            v.lines.append(f"PASS {label}: holes {o['holes']}/{r['holes']} splices {o['splices']}/{r['splices']} "
                           f"osc {o['osc']}/{r['osc']} rms {o['rms_db']}/{r['rms_db']}{lr}")
    if v.stereo_skipped:
        v.lines.append(f"NOTE stereo alignment rule skipped on {v.stereo_skipped}/{len(ref)} windows: no lr_corr0 "
                       f"on one side (a reference pinned before the measure, a mono capture, or a window under "
                       f"{STEREO_MIN_S:.0f} s / {STEREO_FLOOR_DB:.0f} dBFS)")
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
        # The same read as ae.read_mono (header handling included), kept apart so the pair is scored too. A
        # mono file comes back as the one array twice; its stereo keys are null.
        left, right = read_wav(wav)
        mono = (left + right) / 2.0
        stereo = None if right is left else (left, right)
        with open(stdout, encoding="utf-8", errors="replace") as fh:
            windows = step_windows(fh.read(), offset)
        scores = score_capture(mono, rate, windows, stereo)
        meta.update({"wav": wav, "rate": rate, "windows": len(scores), "channels": 1 if stereo is None else 2})
        save_scores(scores, out, meta)
        for label, s in scores.items():
            lr = (f", lr0 {s['lr_corr0']} best {s['lr_best']} @ {s['lr_lag_ms']:+.0f} ms, side/mid {s['side_mid_db']} dB"
                  if s.get("lr_corr0") is not None else ", lr n/a")
            print(f"{label}: rms {s['rms_db']} dB, silences {s['silences']} ({s['silence_s']} s), holes {s['holes']}, "
                  f"splices {s['splices']}, osc {s['osc']}{lr}")
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
