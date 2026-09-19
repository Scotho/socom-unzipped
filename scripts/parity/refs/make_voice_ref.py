#!/usr/bin/env python3
"""Sprint 8 Goal 3 Task 1 Step 5: the reference voice WAV, generated and never recorded.

The proof this goal runs on is a correlation between three files: what PS2X_MIC_FAKE fed in, what the game
actually read through lgaud 0x08 (PS2X_MIC_GAMEREAD_DUMP), and what instance B's headset was asked to play.
All three have to be comparable on any machine, so the input is built from a deterministic formula rather than
recorded -- CI, the Linux VM and the Windows host then produce byte-identical files, and nobody's voice is
committed to the repository.

The signal is built to be easy to correlate and hard to match by accident:
  * a 300 Hz carrier (well inside the 11025 Hz band, and inside what a headset codec keeps),
  * amplitude-modulated by a 3 Hz envelope, so any time shift shows up as a correlation cliff,
  * plus a 40 Hz pseudo-random binary sequence from a fixed seed, which is what stops a pure tone from
    correlating with a delayed copy of itself,
  * scaled to peak 0.6, leaving headroom for the game's own record gain (it drives 0x0e in steps of 5).

The 44-byte header is the layout host_mic.cpp's hostMicWavHeader writes, so runtime/mic_format.h's micWavRead
reads this file with no special case. No numpy: the standard library is all tools_py requires.
"""

import argparse
import math
import os
import struct

SAMPLE_RATE = 11025
DURATION_S = 20
CARRIER_HZ = 300.0
ENVELOPE_HZ = 3.0
PRBS_HZ = 40.0
PEAK = 0.6
PRBS_SEED = 0xACE1


def prbs_bits(count, seed=PRBS_SEED):
    """A 16-bit Fibonacci LFSR (taps 16, 14, 13, 11), seeded from a constant so every machine agrees."""
    state = seed
    for _ in range(count):
        yield 1 if (state & 1) else -1
        bit = ((state >> 0) ^ (state >> 2) ^ (state >> 3) ^ (state >> 5)) & 1
        state = (state >> 1) | (bit << 15)


def build_samples(rate=SAMPLE_RATE, seconds=DURATION_S):
    total = rate * seconds
    chip_frames = max(1, int(round(rate / PRBS_HZ)))
    chips = list(prbs_bits(total // chip_frames + 2))
    out = []
    for i in range(total):
        t = i / float(rate)
        carrier = math.sin(2.0 * math.pi * CARRIER_HZ * t)
        envelope = 0.5 * (1.0 - math.cos(2.0 * math.pi * ENVELOPE_HZ * t))
        chip = chips[i // chip_frames]
        value = PEAK * envelope * (0.75 * carrier + 0.25 * chip)
        sample = int(round(value * 32767.0))
        out.append(max(-32768, min(32767, sample)))
    return out


def wav_header(data_size, rate):
    """The exact 44 bytes host_mic.cpp writes for a 16-bit mono stream."""
    return (
        b"RIFF"
        + struct.pack("<I", 36 + data_size)
        + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
        + b"data"
        + struct.pack("<I", data_size)
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    default = os.path.join(os.path.dirname(os.path.abspath(__file__)), "voice_ref.wav")
    parser.add_argument("--out", default=default, help="where to write the WAV")
    parser.add_argument("--rate", type=int, default=SAMPLE_RATE, help="sample rate (the game asks for 11025)")
    parser.add_argument("--seconds", type=int, default=DURATION_S)
    args = parser.parse_args()

    samples = build_samples(args.rate, args.seconds)
    payload = struct.pack("<%dh" % len(samples), *samples)
    with open(args.out, "wb") as handle:
        handle.write(wav_header(len(payload), args.rate))
        handle.write(payload)
    print("%s: %d Hz mono 16-bit, %d frames, %d bytes" % (args.out, args.rate, len(samples), 44 + len(payload)))


if __name__ == "__main__":
    main()
