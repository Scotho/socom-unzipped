"""Sprint 7 Task 1e: how faithful the mixed audio is to the disc's own PCM.

research/32 section 7.1's final check, as a tool: the mixed WAV (`PS2X_AUDIO_DUMP`) is cut into windows and each
window is located in the disc's PCM by cross-correlation. A faithful playback correlates at 0.99 with the window
sitting at the same place in the reference as in the mix -- `offset_samples` constant. A *step* in
`offset_samples` between neighbouring windows is a slip: that many samples of the track were lost or repeated
(research/32 section 7.1's 0.26 s at 120 s).

The reference is the concatenated private-stream-1 payloads of the CD stream the game played
(`logs/title_disc_audio.bin`): an `SShd` header of 40 bytes, then 16-bit little-endian PCM in 512-byte blocks,
left block then right block, one continuous byte stream across packets.

    python -m tools_py.parity.audio_corr logs/s7_audio.wav logs/title_disc_audio.bin --window-s 4 --bar 0.99

prints one row per window and `min_corr=<x>`, and exits 1 when a window that carries sound falls below the bar.
Windows whose RMS is under `--silent-rms` carry no sound to match (the stage before a stream starts); they are
printed as `silent` and left out of `min_corr`.

Task 12 Step 2 adds a second mode that needs no reference at all:

    python -m tools_py.parity.audio_corr logs/s7_audio_online.wav --repeat --repeat-bar 0.9

Each window's own autocorrelation is taken at lags 256..4096 samples. A 512-byte PCM block looping in the
989snd ring is 128 stereo frames, so it repeats the left channel at 128 and at every multiple of it, and a
decoded chunk replayed instead of the next one repeats at its own length; either reads as r near 1.0, which
is what the owner hears as a buzz. Real music at a 4 s window sits well under 0.9 at lags this short. The
mode prints `repeat lag=<n> r=<x>` per window and `max_repeat=<x>`, and exits 1 above the bar.
"""
import argparse
import sys
import wave

import numpy as np

DEFAULT_RATE = 48000
DEFAULT_WINDOW_S = 4.0
DEFAULT_BAR = 0.99
DEFAULT_DECIMATE = 6        # the search runs at 8 kHz; the peak is then refined at the full rate
DEFAULT_SILENT_RMS = 200.0
SUB_BLOCK_S = 0.25          # a window is scored only if it carries sound all the way through
DISC_HEADER_BYTES = 40      # the SShd header in front of the payload concatenation
DISC_BLOCK_BYTES = 512      # 512 bytes of left, then 512 of right


# ---- reading ---------------------------------------------------------------------------------------------

def read_wav(path):
    """(left, right) as float64 from a 16-bit PCM WAV. A mono file gives the same array twice."""
    channels, nframes = 2, 0
    try:
        with wave.open(str(path), "rb") as w:
            if w.getsampwidth() != 2:
                raise ValueError(f"{path}: expected 16-bit PCM, got {8 * w.getsampwidth()}-bit")
            channels = w.getnchannels()
            nframes = w.getnframes()
    except (wave.Error, EOFError):
        nframes = 0          # a zero-size header the wave module refuses outright: same fallback
    if nframes == 0:
        # The runtime patches the size fields on a clean close; a game the drive kills leaves them 0. The data
        # is there: read it by file length past the 44-byte header (research/32's dumps are always this shape).
        with open(path, "rb") as f:
            raw = f.read()[44:]
        frames = np.frombuffer(raw[: len(raw) // 2 * 2], dtype="<i2")
    else:
        with wave.open(str(path), "rb") as w:
            frames = np.frombuffer(w.readframes(nframes), dtype="<i2")
    if channels == 1:
        mono = frames.astype(np.float64)
        return mono, mono
    frames = frames[: len(frames) // channels * channels].reshape(-1, channels)
    return frames[:, 0].astype(np.float64), frames[:, 1].astype(np.float64)


def read_disc_pcm(path, header_bytes=DISC_HEADER_BYTES, block_bytes=DISC_BLOCK_BYTES):
    """(left, right) as float64 from the concatenated private-stream-1 payloads (research/32 section 7.1)."""
    with open(path, "rb") as fp:
        data = fp.read()[header_bytes:]
    pair = 2 * block_bytes
    data = data[: len(data) // pair * pair]
    samples = block_bytes // 2
    blocks = np.frombuffer(data, dtype="<i2").reshape(-1, 2, samples)
    return (blocks[:, 0, :].reshape(-1).astype(np.float64),
            blocks[:, 1, :].reshape(-1).astype(np.float64))


# ---- the correlation -------------------------------------------------------------------------------------

def _decimate(x, factor):
    n = len(x) // factor * factor
    if n == 0:
        return np.zeros(0)
    return x[:n].reshape(-1, factor).mean(axis=1)


def _scorable(seg, rate, silent_rms):
    """True when every part of the window carries sound.

    A window that is silent, or that straddles the moment a stream starts, has nothing in the reference to match
    and would sink the bar for a reason that is not a fault. Such windows are reported (`silent`) and counted, not
    dropped quietly: a capture that is mostly silence must not read as a pass.
    """
    block = max(1, int(round(SUB_BLOCK_S * rate)))
    if len(seg) < block:
        return float(np.sqrt((seg * seg).mean())) >= silent_rms
    whole = seg[: len(seg) // block * block].reshape(-1, block)
    return bool(np.all(np.sqrt((whole * whole).mean(axis=1)) >= silent_rms))


def _normalised(x):
    x = x - x.mean()
    norm = float(np.sqrt((x * x).sum()))
    return x, norm


# A tone repeats: a window of one correlates just as well a whole number of periods away, and the difference
# between those places is floating-point dust. Tied places are resolved towards `prefer` -- where the window sits
# in the mix -- so a playback that is running together is reported as running together, and an offset is reported
# only when the samples actually say so.
_TIE = 1e-9
# The decimated search only nominates a place for the refinement to check, and its FFT sums carry more rounding
# than the direct correlation does, so its ties are read with a looser tolerance.
_COARSE_TIE = 1e-6


def _search(seg, ref, decimate, prefer):
    """The index in `ref` where `seg` sits best, coarse (decimated FFT cross-correlation, the whole reference)."""
    segd = _decimate(seg, decimate)
    refd = _decimate(ref, decimate)
    positions = len(refd) - len(segd) + 1      # inclusive: a window may sit at the very end of the reference
    if positions <= 0 or len(segd) == 0:
        return None
    segd = segd - segd.mean()
    energy = np.concatenate([[0.0], np.cumsum(refd * refd)])
    size = 1 << int(np.ceil(np.log2(len(refd) + len(segd))))
    corr = np.fft.irfft(np.fft.rfft(refd, size) * np.conj(np.fft.rfft(segd, size)), size)[:positions]
    window = np.sqrt(np.maximum(energy[len(segd):len(segd) + positions] - energy[:positions], 0.0) *
                     float((segd * segd).sum())) + 1e-9
    ratio = corr / window
    tied = np.flatnonzero(ratio >= ratio.max() - _COARSE_TIE)
    return int(tied[np.argmin(np.abs(tied - prefer / float(decimate)))]) * decimate


def _refine(seg, ref, around, span, prefer):
    """The best (index, correlation) within +/- span of `around`, at the full sample rate."""
    seg0, segNorm = _normalised(seg)
    scored = []
    for at in range(max(0, around - span), min(len(ref) - len(seg), around + span) + 1):
        ref0, refNorm = _normalised(ref[at:at + len(seg)])
        denom = segNorm * refNorm
        if denom > 0.0:
            scored.append((at, float(np.dot(seg0, ref0) / denom)))
    if not scored:
        return around, -1.0
    best = max(r for _, r in scored)
    tied = [at for at, r in scored if r >= best - _TIE]
    return min(tied, key=lambda at: abs(at - prefer)), best


def correlate_arrays(mix, ref, window_s=DEFAULT_WINDOW_S, rate=DEFAULT_RATE,
                     decimate=DEFAULT_DECIMATE, silent_rms=DEFAULT_SILENT_RMS):
    """One (t_s, corr, offset_samples) row per whole window of `mix`.

    `t_s` is where the window starts in the mix; `corr` its best normalised cross-correlation with `ref`
    (nan for a window too quiet to match); `offset_samples` where it was found in `ref` *relative* to where it
    sits in the mix -- 0 when the two run together, constant while playback advances 1:1, and a step when it slips.
    """
    mix = np.asarray(mix, dtype=np.float64)
    ref = np.asarray(ref, dtype=np.float64)
    size = int(round(window_s * rate))
    rows = []
    if size <= 0:
        return rows
    for index in range(len(mix) // size):
        start = index * size
        seg = mix[start:start + size]
        t_s = start / float(rate)
        if not _scorable(seg, rate, silent_rms):
            rows.append((t_s, float("nan"), 0))
            continue
        coarse = _search(seg, ref, decimate, prefer=start)
        if coarse is None:
            rows.append((t_s, float("nan"), 0))
            continue
        at, corr = _refine(seg, ref, coarse, decimate, prefer=start)
        rows.append((t_s, corr, at - start))
    return rows


def correlate(wav_path, pcm_path, window_s=DEFAULT_WINDOW_S, rate=DEFAULT_RATE,
              decimate=DEFAULT_DECIMATE, silent_rms=DEFAULT_SILENT_RMS, from_s=None, to_s=None):
    """The mixed WAV's left channel against the disc PCM's left channel, window by window. `from_s`/`to_s`
    restrict the mix to a span: a title-stage dump carries three streams (the logos, the intro, the title loop)
    and the bar applies to the span the reference stream plays in; rows keep their absolute t_s."""
    mix_left, _ = read_wav(wav_path)
    start = int(round((from_s or 0.0) * rate))
    stop = int(round(to_s * rate)) if to_s is not None else len(mix_left)
    mix_left = mix_left[start:stop]
    ref_left, _ = read_disc_pcm(pcm_path)
    rows = correlate_arrays(mix_left, ref_left, window_s=window_s, rate=rate,
                            decimate=decimate, silent_rms=silent_rms)
    return [(t + start / float(rate), c, o) for t, c, o in rows]


def min_corr(rows):
    """The worst correlation of the windows that carried sound; 0.0 when none of them did."""
    scored = [r[1] for r in rows if not np.isnan(r[1])]
    return float(min(scored)) if scored else 0.0


# ---- the repeat detector (Task 12 Step 2) ------------------------------------------------------------------

# A 512-byte PCM block is 128 stereo frames, so a block looping in the ring repeats the left channel every 128
# samples and the autocorrelation of the window is ~1.0 at 128 and at every multiple of it. A decoded chunk
# replayed instead of the next one repeats at its own length. The search starts at 256 so a window is never
# scored on the pitch of the sound itself (a 200 Hz tone repeats every 240 samples at 48 kHz); real music at a
# 4 s window sits well under 0.9 at every lag this short.
DEFAULT_REPEAT_BAR = 0.9
DEFAULT_MIN_LAG = 256
DEFAULT_MAX_LAG = 4096


def autocorr_peak(seg, min_lag=DEFAULT_MIN_LAG, max_lag=DEFAULT_MAX_LAG):
    """(best_lag, r) of the mean-removed window over lags `min_lag..max_lag`, (0, nan) when there are none.

    r(lag) = sum(x[t]*x[t+lag]) / sqrt(sum x[t]^2 * sum x[t+lag]^2), both sums over the overlap, so a window
    whose energy rises or falls across it is still scored on shape rather than on loudness. The numerators come
    from one FFT (3840 lags x 192000 samples is minutes in a Python loop and milliseconds here); the two
    denominators from a prefix sum of the squares.
    """
    x = np.asarray(seg, dtype=np.float64)
    n = len(x)
    top = min(max_lag, n - 1)
    if n == 0 or top < min_lag:
        return 0, float("nan")
    x = x - x.mean()
    size = 1 << int(np.ceil(np.log2(2 * n)))
    spectrum = np.fft.rfft(x, size)
    corr = np.fft.irfft(spectrum * np.conj(spectrum), size)[: top + 1]
    energy = np.concatenate([[0.0], np.cumsum(x * x)])      # energy[k] = sum of the first k squares
    lags = np.arange(min_lag, top + 1)
    head = energy[n - lags]                                  # sum x[t]^2   for t in [0, n-lag)
    tail = energy[n] - energy[lags]                          # sum x[t+lag]^2 for t in [0, n-lag)
    denom = np.sqrt(np.maximum(head, 0.0) * np.maximum(tail, 0.0))
    ratio = np.where(denom > 0.0, corr[min_lag:top + 1] / np.where(denom > 0.0, denom, 1.0), 0.0)
    top_r = float(ratio.max())
    # A block that loops peaks at its length and at every multiple of it, all tied to the last bit. The shortest
    # tied lag is the one that names the loop, so ties go to it rather than to wherever argmax happens to land.
    best = int(np.flatnonzero(ratio >= top_r - _TIE)[0])
    return int(lags[best]), float(ratio[best])


def repeat_rows(mix, window_s=DEFAULT_WINDOW_S, rate=DEFAULT_RATE, silent_rms=DEFAULT_SILENT_RMS,
                min_lag=DEFAULT_MIN_LAG, max_lag=DEFAULT_MAX_LAG):
    """One (t_s, r, lag) row per whole window of `mix`; r is nan (and lag 0) for a window carrying no sound.

    The silence rule is `_scorable`, the same one the correlation bar uses: a window that is quiet, or that
    straddles the moment a stream starts, has no loop to find and must not be scored as if it had.
    """
    mix = np.asarray(mix, dtype=np.float64)
    size = int(round(window_s * rate))
    rows = []
    if size <= 0:
        return rows
    for index in range(len(mix) // size):
        start = index * size
        seg = mix[start:start + size]
        t_s = start / float(rate)
        if not _scorable(seg, rate, silent_rms):
            rows.append((t_s, float("nan"), 0))
            continue
        lag, r = autocorr_peak(seg, min_lag=min_lag, max_lag=max_lag)
        rows.append((t_s, r, lag))
    return rows


def max_repeat(rows):
    """The strongest repeat of the windows that carried sound; 0.0 when none of them did."""
    scored = [r[1] for r in rows if not np.isnan(r[1])]
    return float(max(scored)) if scored else 0.0


# ---- CLI -------------------------------------------------------------------------------------------------

def _repeat_main(args):
    """`--repeat`: the mix on its own, window by window. Exit 1 when any scored window repeats above the bar."""
    mix_left, _ = read_wav(args.wav)
    start = int(round((args.from_s or 0.0) * args.rate))
    stop = int(round(args.to_s * args.rate)) if args.to_s is not None else len(mix_left)
    rows = repeat_rows(mix_left[start:stop], window_s=args.window_s, rate=args.rate,
                       silent_rms=args.silent_rms, min_lag=args.min_lag, max_lag=args.max_lag)
    offset = start / float(args.rate)
    for t_s, r, lag in rows:
        if np.isnan(r):
            print(f"mix {t_s + offset:7.1f} s: silent")
            continue
        print(f"mix {t_s + offset:7.1f} s: repeat lag={lag} r={r:.3f}")
    worst = max_repeat(rows)
    silent = sum(1 for _, r, _ in rows if np.isnan(r))
    print(f"max_repeat={worst:.4f} repeat_bar={args.repeat_bar:.2f} windows={len(rows)} "
          f"scored={len(rows) - silent} silent={silent}")
    return 1 if worst > args.repeat_bar else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Correlate a mixed WAV against the disc's PCM (research/32 section 7.1)")
    ap.add_argument("wav", help="the mixed WAV (PS2X_AUDIO_DUMP)")
    ap.add_argument("pcm", nargs="?", default=None,
                    help="the disc PCM: the stream's private-stream-1 payloads concatenated "
                         "(not needed with --repeat)")
    ap.add_argument("--window-s", type=float, default=DEFAULT_WINDOW_S)
    ap.add_argument("--rate", type=int, default=DEFAULT_RATE)
    ap.add_argument("--decimate", type=int, default=DEFAULT_DECIMATE)
    ap.add_argument("--silent-rms", type=float, default=DEFAULT_SILENT_RMS)
    ap.add_argument("--bar", type=float, default=DEFAULT_BAR, help="exit 1 below this (default 0.99)")
    ap.add_argument("--from-s", type=float, default=None, help="score the mix from this second (a title dump carries three streams)")
    ap.add_argument("--to-s", type=float, default=None, help="... up to this second")
    ap.add_argument("--repeat", action="store_true",
                    help="look for a looping block or chunk in the mix alone; no reference needed")
    ap.add_argument("--min-lag", type=int, default=DEFAULT_MIN_LAG)
    ap.add_argument("--max-lag", type=int, default=DEFAULT_MAX_LAG)
    ap.add_argument("--repeat-bar", type=float, default=DEFAULT_REPEAT_BAR,
                    help="with --repeat, exit 1 above this (default 0.9)")
    args = ap.parse_args(argv)

    if args.repeat:
        return _repeat_main(args)
    if args.pcm is None:
        ap.error("pcm is required unless --repeat is given")

    rows = correlate(args.wav, args.pcm, from_s=args.from_s, to_s=args.to_s, window_s=args.window_s, rate=args.rate,
                     decimate=args.decimate, silent_rms=args.silent_rms)
    previous = None
    for t_s, corr, offset in rows:
        if np.isnan(corr):
            print(f"mix {t_s:7.1f} s: silent")
            continue
        step = "" if previous is None else f"  step {(offset - previous) / float(args.rate):+.3f} s"
        print(f"mix {t_s:7.1f} s: ref {(t_s + offset / float(args.rate)):8.3f} s  corr {corr:.3f}  "
              f"offset_samples {offset:+d}{step}")
        previous = offset
    worst = min_corr(rows)
    silent = sum(1 for _, corr, _ in rows if np.isnan(corr))
    print(f"min_corr={worst:.4f} bar={args.bar:.2f} windows={len(rows)} scored={len(rows) - silent} silent={silent}")
    return 0 if worst >= args.bar else 1


if __name__ == "__main__":
    sys.exit(main())
