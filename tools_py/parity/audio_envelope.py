"""Sprint 9: the two symptoms the owner reports in the mission music, as numbers with timestamps.

The owner hears the mission music "getting louder and quieter" and "jumping between tracks / glitched
between different samples". Every measurement we already have -- `audio_corr.py`'s cross-correlation, its
`--repeat` autocorrelation -- scores *one cue's fidelity*, and neither can see either symptom: the first
needs the disc's own PCM for the exact stream being played, and the second only finds a block looping
inside a window. This module is reference-free on purpose, so the same command can be run on our dump and
on a PCSX2 capture of the same mission and the two columns of numbers compared.

Four measurements, each aimed at one thing the owner described:

  envelope()          the loudness curve: window rms in dBFS, one point every 50 ms.
  oscillation_score() "louder and quieter": how many dB the loudness curve swings at wobble speed.
  splices()           "jumping between tracks": abrupt discontinuities, by waveform step and by spectral flux.
  silences()          a stream underrun -- silence then resume -- which is the reference-free view of a gap.

    python -m tools_py.parity.audio_envelope logs/parity/s9_p1_m51_audio2/mission_audio_playable.wav --segment 60

prints one line per segment and a totals line. Output is deterministic: no randomness, no wall clock, and
every threshold is a module constant or a flag.

The WAV is read through `audio_corr.read_wav`, which already handles the dump this is aimed at: the
runtime patches the RIFF and data sizes on a clean close, and a game the drive kills leaves them zero, so
the samples have to be read by file length past the 44-byte header.
"""
import argparse
import math
import sys

import numpy as np

from tools_py.parity.audio_corr import read_wav

FULL_SCALE = 32768.0        # 0 dBFS for 16-bit PCM
FLOOR_DB = -90.0            # 1 LSB of 16-bit is -90.3 dBFS: below this the level is not a measurement
DEFAULT_RATE = 48000
DEFAULT_WINDOW_S = 0.05     # the loudness curve's step: 20 Hz, four times the top of the wobble band
DEFAULT_SEGMENT_S = 60.0

# -- oscillation -------------------------------------------------------------------------------------------
DEFAULT_BAND_LO_HZ = 0.2    # slower than this is a musical arrangement, not a wobble
DEFAULT_BAND_HI_HZ = 3.0    # faster than this is not heard as "louder and quieter" but as texture

# -- splices -----------------------------------------------------------------------------------------------
STEP_LOCAL_S = 0.020        # the sample-difference rms is judged over 20 ms either side
STEP_RATIO = 8.0            # ... and a step must stand 8x above it
STEP_FLOOR = 1500.0         # ... and be at least this many counts (-26.8 dBFS), so dither is never a splice
FLUX_WINDOW = 1024          # 21.3 ms: short enough that a flux event is placed within 11 ms of its cause
FLUX_HOP = 256              # 5.3 ms
FLUX_RATIO = 6.0            # a flux spike must stand 6x above the running median
FLUX_MEDIAN_S = 1.0         # ... which is taken over a centred 1 s window of frames
FLUX_MEDIAN_FLOOR = 0.1     # ... floored at 10% of the sounding frames' median, so a quiet passage's
                            #     near-zero median cannot make every frame a spike
FLUX_MIN_FRACTION = 0.05    # ... and the new content must be 5% of the frame's own magnitude, so that a
                            #     near-steady signal's numerical residue can never clear a relative bar
REFRACTORY_S = 0.050        # one discontinuity is one event, however many detectors saw it
SILENCE_GUARD_S = 0.050     # a gap's own edges belong to the gap, not to the splice count: longer than a
                            #     flux window plus a hop (26.7 ms at 48 kHz), so no frame that straddles
                            #     an edge can be reported as a splice in its own right

# -- silences ----------------------------------------------------------------------------------------------
SILENCE_WINDOW_S = 0.005    # 5 ms resolution: ten windows inside the shortest gap worth reporting
DEFAULT_FLOOR_DB = -60.0
DEFAULT_MIN_SILENCE_S = 0.05


# ---- reading ---------------------------------------------------------------------------------------------

def read_mono(path):
    """The WAV's two channels averaged to one float64 array.

    The mean, not the sum: a symptom that is present in both channels must not read as 6 dB of extra level,
    and averaging cannot overflow. `audio_corr.read_wav` does the header work, including the zero-size case.
    """
    left, right = read_wav(path)
    return (left + right) / 2.0


# ---- (a) the loudness curve ------------------------------------------------------------------------------

def envelope(mono_samples, rate, window_s=DEFAULT_WINDOW_S):
    """[(t_s, rms_db)] -- one point per whole non-overlapping `window_s` window, t at the window's start.

    rms_db is dBFS: 20*log10(rms / 32768), floored at FLOOR_DB so that digital silence is a number rather
    than -inf. A trailing part-window is dropped so every point covers the same span.
    """
    x = np.asarray(mono_samples, dtype=np.float64)
    size = int(round(window_s * rate))
    if size <= 0 or len(x) < size:
        return []
    count = len(x) // size
    blocks = x[:count * size].reshape(count, size)
    rms = np.sqrt((blocks * blocks).mean(axis=1))
    db = np.maximum(20.0 * np.log10(np.maximum(rms, 1e-12) / FULL_SCALE), FLOOR_DB)
    times = np.arange(count, dtype=np.float64) * (float(size) / float(rate))
    return list(zip(times.tolist(), db.tolist()))


# ---- (b) "getting louder and quieter" --------------------------------------------------------------------

def oscillation_score(env, band_lo_hz=DEFAULT_BAND_LO_HZ, band_hi_hz=DEFAULT_BAND_HI_HZ):
    """How many dB the loudness curve swings at wobble speed: the rms, in dB, of `env` band-limited to
    [band_lo_hz, band_hi_hz].

    Precisely: take the dB values of `env` (sampled at 1/dt Hz, dt from the first two points), subtract
    their mean, multiply by a Hann window, take the one-sided power spectrum, sum the power in the bins
    whose frequency falls inside the band, undo the window's power loss, and return the square root. The
    result is the standard deviation, in dB, of the part of the loudness curve that moves at 0.2-3 Hz.

    It is read directly: a level that swings +/-6 dB at 1 Hz scores 6/sqrt(2) = 4.24, because that is the
    rms of a 6 dB sine. Steady music scores a fraction of a dB -- its own dynamics are either slower than
    the band (a section change, a fade) or faster than it, and the Hann window keeps the slow ones from
    leaking in. The mean subtraction means absolute level does not enter, so a quiet passage and a loud one
    are scored the same way.

    `env` is one segment's worth of points; the caller decides the segment (the CLI uses one minute).
    Returns 0.0 when there are too few points, or when no spectrum bin falls inside the band -- a segment
    shorter than 1/band_lo_hz cannot show an oscillation that slow.
    """
    if len(env) < 4:
        return 0.0
    times = [float(t) for t, _ in env]
    dt = times[1] - times[0]
    if dt <= 0.0:
        return 0.0
    values = np.array([float(db) for _, db in env], dtype=np.float64)
    count = len(values)
    windowed = (values - values.mean()) * np.hanning(count)
    power = np.abs(np.fft.rfft(windowed)) ** 2
    # one-sided: every bin but DC (and Nyquist, when the count is even) stands for a conjugate pair
    weight = np.full(len(power), 2.0)
    weight[0] = 1.0
    if count % 2 == 0:
        weight[-1] = 1.0
    freqs = np.fft.rfftfreq(count, d=dt)
    band = (freqs >= band_lo_hz) & (freqs <= band_hi_hz)
    window_power = float((np.hanning(count) ** 2).mean())
    if not band.any() or window_power <= 0.0:
        return 0.0
    # Parseval: mean square of the windowed curve is sum(weight*|X|^2) / count^2; dividing by the window's
    # own mean square recovers the variance of the curve itself.
    variance = float((power[band] * weight[band]).sum()) / (count * count) / window_power
    return math.sqrt(max(variance, 0.0))


# ---- (d) underruns ---------------------------------------------------------------------------------------

def silences(mono_samples, rate, floor_db=DEFAULT_FLOOR_DB, min_s=DEFAULT_MIN_SILENCE_S,
             window_s=SILENCE_WINDOW_S):
    """[(t_start, duration)] for every run of `window_s` windows whose rms is under `floor_db`, lasting at
    least `min_s`.

    A stream underrun is silence then resume; with no reference to compare against, the gap itself is the
    evidence. The window is 5 ms so the shortest reportable gap (50 ms) is ten windows wide and its start
    and length are placed to within one window.
    """
    x = np.asarray(mono_samples, dtype=np.float64)
    size = max(1, int(round(window_s * rate)))
    count = len(x) // size
    if count == 0:
        return []
    blocks = x[:count * size].reshape(count, size)
    rms = np.sqrt((blocks * blocks).mean(axis=1))
    db = 20.0 * np.log10(np.maximum(rms, 1e-12) / FULL_SCALE)
    quiet = (db < floor_db).astype(np.int8)
    edges = np.flatnonzero(np.diff(np.concatenate(([0], quiet, [0]))))
    found = []
    for start, stop in zip(edges[0::2], edges[1::2]):
        duration = (stop - start) * size / float(rate)
        if duration >= min_s - 1e-9:
            found.append((start * size / float(rate), duration))
    return found


# ---- (c) "jumping between tracks / glitched between different samples" -------------------------------------

def _step_candidates(mono_samples, rate, ratio=STEP_RATIO, floor=STEP_FLOOR, local_s=STEP_LOCAL_S):
    """[(t, 'step', magnitude)] where one sample-to-sample difference towers over the recent ones.

    Two choices here, both forced by real captures:

    The comparison is against the rms of the *difference* signal over `local_s`, not of the signal itself.
    A loud smooth tone has a large rms and tiny differences, so judging a discontinuity against the
    signal's own rms would hide every splice inside loud music.

    And the local difference rms is taken over `local_s` on *both* sides, the larger of the two winning.
    Looking only backwards, the first sample of any sound that starts after a quiet passage towers over
    near-silence and reads as a discontinuity: on mission_audio_playable.wav that one-sided rule returned
    210 'splices' that were, on inspection, all onsets -- the jump was smaller than the differences in the
    20 ms that followed it. A genuine join is anomalous against what comes after it as well as before.

    `magnitude` is the ratio of the difference to that local difference rms (inf when both sides are
    digital silence, which only an isolated single-sample spike can produce).
    """
    x = np.asarray(mono_samples, dtype=np.float64)
    if len(x) < 2:
        return []
    diff = np.diff(x)
    span = max(1, int(round(local_s * rate)))
    squares = np.concatenate(([0.0], np.cumsum(diff * diff)))
    index = np.arange(len(diff))
    low = np.maximum(index - span, 0)
    counted = index - low
    before = np.where(counted > 0, (squares[index] - squares[low]) / np.maximum(counted, 1), 0.0)
    high = np.minimum(index + 1 + span, len(diff))
    after_count = high - (index + 1)
    after = np.where(after_count > 0,
                     (squares[high] - squares[index + 1]) / np.maximum(after_count, 1), 0.0)
    local = np.sqrt(np.maximum(np.maximum(before, after), 0.0))
    size = np.abs(diff)
    hit = (size > floor) & (size > ratio * local)
    at = np.flatnonzero(hit)
    with np.errstate(divide="ignore", invalid="ignore"):
        strength = np.where(local[at] > 0.0, size[at] / np.where(local[at] > 0.0, local[at], 1.0), np.inf)
    # diff[i] is x[i+1]-x[i]: the discontinuity is at sample i+1
    return [(float((i + 1) / float(rate)), "step", float(s)) for i, s in zip(at.tolist(), strength.tolist())]


def _flux_candidates(mono_samples, rate, window=FLUX_WINDOW, hop=FLUX_HOP, ratio=FLUX_RATIO,
                     median_s=FLUX_MEDIAN_S):
    """[(t, 'flux', magnitude)] where the spectral flux spikes above its running median.

    Spectral flux is the half-wave rectified difference of successive short-window magnitude spectra summed
    over bins: it answers "how much new content appeared", which is what a cut to a different sample does
    and what a smooth passage never does. The threshold is `ratio` times a centred running median over
    `median_s` of frames -- a median, not a mean, so the spike cannot raise its own bar -- floored at
    FLUX_MEDIAN_FLOOR of the whole capture's median so a near-silent stretch does not make every frame a
    spike. `magnitude` is flux / threshold-basis. A frame is timestamped at its own centre, so an event is
    placed within half a window (11 ms) of its cause.
    """
    x = np.asarray(mono_samples, dtype=np.float64)
    if len(x) < window + hop:
        return []
    frames = 1 + (len(x) - window) // hop
    taper = np.hanning(window)
    flux = np.zeros(frames, dtype=np.float64)
    bulk = np.zeros(frames, dtype=np.float64)      # each frame's own total magnitude, to size its flux
    previous = None
    block = 4096                                        # a whole-file STFT would not fit in memory
    for first in range(0, frames, block):
        last = min(first + block, frames)
        starts = np.arange(first, last) * hop
        patch = x[np.add.outer(starts, np.arange(window))] * taper
        magnitude = np.abs(np.fft.rfft(patch, axis=1))
        if previous is not None:
            flux[first] = float(np.maximum(magnitude[0] - previous, 0.0).sum())
        flux[first + 1:last] = np.maximum(np.diff(magnitude, axis=0), 0.0).sum(axis=1)
        bulk[first:last] = magnitude.sum(axis=1)
        previous = magnitude[-1]
    # Frame 0 has no predecessor, so its flux is undefined rather than zero. Carrying a zero here would
    # drag the running median down at the start of every capture and make the first second of any file
    # look like a burst of splices, so it is dropped: `flux[j]` now belongs to frame j+1.
    flux = flux[1:]
    bulk = bulk[1:]
    if len(flux) == 0:
        return []
    # The floor is the median of the *sounding* frames. Taken over every frame it would move with how
    # much silence the capture happens to contain -- the mission dump is 52% digital zero, which put the
    # median at zero and swung the detector by two orders of magnitude depending on where the analysis
    # started. A capture is only comparable with another if this does not depend on its silent stretches.
    sounding = flux[flux > 0.0]
    if len(sounding) == 0:
        return []
    scale = float(np.median(sounding))
    if scale <= 0.0:
        return []
    span = max(3, int(round(median_s * rate / hop)))
    if span % 2 == 0:
        span += 1
    padded = np.pad(flux, (span // 2, span // 2), mode="edge")
    running = np.empty(len(flux), dtype=np.float64)
    for first in range(0, len(flux), 8192):             # the sliding window is materialised in slices
        last = min(first + 8192, len(flux))
        view = np.lib.stride_tricks.sliding_window_view(padded[first:last + span - 1], span)
        running[first:last] = np.median(view, axis=1)
    basis = np.maximum(running, FLUX_MEDIAN_FLOOR * scale)
    # Two conditions, and a splice must meet both: the flux stands out against its neighbours, *and* the
    # new content is a real share of what the frame contains. The ratio alone is not enough -- a steady
    # passage's flux is near zero, and the ratio of one near-zero number to another says nothing.
    share = np.where(bulk > 0.0, flux / np.where(bulk > 0.0, bulk, 1.0), 0.0)
    hit = np.flatnonzero((flux > ratio * basis) & (basis > 0.0) & (share > FLUX_MIN_FRACTION))
    centre = ((hit + 1) * hop + window / 2.0) / float(rate)
    return [(float(t), "flux", float(flux[i] / basis[i])) for t, i in zip(centre.tolist(), hit.tolist())]


def splices(mono_samples, rate, refractory_s=REFRACTORY_S, floor_db=DEFAULT_FLOOR_DB,
            min_silence_s=DEFAULT_MIN_SILENCE_S, guard_s=SILENCE_GUARD_S):
    """[(t, kind, magnitude)] -- one entry per abrupt join, sorted by time. kind is 'step' or 'flux'.

    Both detectors see the same cut, so the candidates are clustered: a cluster opens at its first
    candidate and swallows everything within `refractory_s` of it, and reports one event. A cluster that
    holds a step reports the step, because a sample-exact discontinuity is both the more specific finding
    and the better timestamp; otherwise it reports its first flux frame.

    Candidates inside a reported silence, or within `guard_s` of one of its edges, are dropped. An underrun
    is one event and `silences()` already reports it with a duration; counting its fade-out and fade-in as
    two more splices would triple-count the same fault. This is also why a windowed gap in a test signal
    produces exactly one silence and no splice.
    """
    candidates = _step_candidates(mono_samples, rate) + _flux_candidates(mono_samples, rate)
    if not candidates:
        return []
    gaps = silences(mono_samples, rate, floor_db=floor_db, min_s=min_silence_s)
    blocked = [(t0 - guard_s, t0 + duration + guard_s) for t0, duration in gaps]
    # 'step' before 'flux' at the same instant, so a cluster's representative never depends on input order
    candidates = sorted((t, 0 if kind == "step" else 1, kind, size) for t, kind, size in candidates)
    candidates = [(t, kind, size) for t, _, kind, size in candidates
                  if not any(lo <= t <= hi for lo, hi in blocked)]
    found = []
    index = 0
    while index < len(candidates):
        opened = candidates[index][0]
        cluster = [candidates[index]]
        index += 1
        while index < len(candidates) and candidates[index][0] <= opened + refractory_s:
            cluster.append(candidates[index])
            index += 1
        steps = [c for c in cluster if c[1] == "step"]
        found.append(steps[0] if steps else cluster[0])
    return found


# ---- (e) CLI ---------------------------------------------------------------------------------------------

def _clock(seconds):
    whole = int(round(seconds))
    return "%02d:%02d" % (whole // 60, whole % 60)


def analyse(mono_samples, rate, segment_s=DEFAULT_SEGMENT_S, window_s=DEFAULT_WINDOW_S,
            band_lo_hz=DEFAULT_BAND_LO_HZ, band_hi_hz=DEFAULT_BAND_HI_HZ,
            floor_db=DEFAULT_FLOOR_DB, min_silence_s=DEFAULT_MIN_SILENCE_S, offset_s=0.0):
    """One dict per segment: the four measurements cut to the same minute so they can be read across."""
    x = np.asarray(mono_samples, dtype=np.float64)
    total_s = len(x) / float(rate)
    env = envelope(x, rate, window_s=window_s)
    found = splices(x, rate, floor_db=floor_db, min_silence_s=min_silence_s)
    gaps = silences(x, rate, floor_db=floor_db, min_s=min_silence_s)
    rows = []
    count = max(1, int(math.ceil(total_s / segment_s))) if total_s > 0 else 0
    for index in range(count):
        low = index * segment_s
        high = min((index + 1) * segment_s, total_s)
        inside = [p for p in env if low <= p[0] < high]
        levels = [db for _, db in inside]
        cut = [s for s in found if low <= s[0] < high]
        # A gap is counted in the segment it starts in, so the counts sum to the number of gaps; its
        # seconds are split across the segments it actually covers, so a segment can never report more
        # silence than it is long (the 96 s gap over the briefing used to be billed whole to one minute)
        # and the seconds still sum to the true total.
        holes = [g for g in gaps if low <= g[0] < high]
        covered = sum(max(0.0, min(t0 + duration, high) - max(t0, low)) for t0, duration in gaps)
        rows.append({
            "from_s": low + offset_s,
            "to_s": high + offset_s,
            "osc": oscillation_score(inside, band_lo_hz=band_lo_hz, band_hi_hz=band_hi_hz),
            "step": sum(1 for s in cut if s[1] == "step"),
            "flux": sum(1 for s in cut if s[1] == "flux"),
            "splices": len(cut),
            "silences": len(holes),
            "silence_s": covered,
            "rms_db": (sum(levels) / len(levels)) if levels else FLOOR_DB,
        })
    return rows


def _line(row):
    return ("t=%s-%s  osc=%.2f  splices=%d (step=%d flux=%d)  silences=%d total=%.2fs  rms_db=%.1f"
            % (_clock(row["from_s"]), _clock(row["to_s"]), row["osc"], row["splices"], row["step"],
               row["flux"], row["silences"], row["silence_s"], row["rms_db"]))


def main(argv=None, stream=None):
    ap = argparse.ArgumentParser(
        description="Reference-free audio symptoms: level oscillation, splices and underruns, per segment")
    ap.add_argument("wav", help="a 16-bit PCM WAV (zero RIFF/data sizes are handled)")
    ap.add_argument("--from", dest="from_s", type=float, default=None, help="start at this second")
    ap.add_argument("--to", dest="to_s", type=float, default=None, help="stop at this second")
    ap.add_argument("--segment", dest="segment_s", type=float, default=DEFAULT_SEGMENT_S,
                    help="seconds per reported line (default 60)")
    ap.add_argument("--rate", type=int, default=DEFAULT_RATE)
    ap.add_argument("--window-s", type=float, default=DEFAULT_WINDOW_S, help="the loudness curve's step")
    ap.add_argument("--band-lo-hz", type=float, default=DEFAULT_BAND_LO_HZ)
    ap.add_argument("--band-hi-hz", type=float, default=DEFAULT_BAND_HI_HZ)
    ap.add_argument("--floor-db", type=float, default=DEFAULT_FLOOR_DB, help="a gap is quieter than this")
    ap.add_argument("--min-silence-s", type=float, default=DEFAULT_MIN_SILENCE_S)
    args = ap.parse_args(argv)
    out = stream if stream is not None else sys.stdout

    mono = read_mono(args.wav)
    start = int(round((args.from_s or 0.0) * args.rate))
    stop = int(round(args.to_s * args.rate)) if args.to_s is not None else len(mono)
    rows = analyse(mono[start:stop], args.rate, segment_s=args.segment_s, window_s=args.window_s,
                   band_lo_hz=args.band_lo_hz, band_hi_hz=args.band_hi_hz, floor_db=args.floor_db,
                   min_silence_s=args.min_silence_s, offset_s=start / float(args.rate))
    for row in rows:
        print(_line(row), file=out)
    if rows:
        worst = max(rows, key=lambda r: r["osc"])
        print("TOTAL segments=%d  osc_max=%.2f at %s  osc_mean=%.2f  splices=%d (step=%d flux=%d)  "
              "silences=%d total=%.2fs  rms_db=%.1f"
              % (len(rows), worst["osc"], _clock(worst["from_s"]),
                 sum(r["osc"] for r in rows) / len(rows),
                 sum(r["splices"] for r in rows), sum(r["step"] for r in rows),
                 sum(r["flux"] for r in rows), sum(r["silences"] for r in rows),
                 sum(r["silence_s"] for r in rows),
                 sum(r["rms_db"] for r in rows) / len(rows)), file=out)
    else:
        print("TOTAL segments=0", file=out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
