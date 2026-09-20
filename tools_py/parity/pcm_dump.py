"""Sprint 9 Q0: read a PS2X_AUDIO_PCM_DUMP file -- what the EE wrote into the 989snd PCM ring (the movie audio),
as {u32 ringOffset, u32 bytes, u32 wallMs} records each followed by `bytes` of the ring's 16-bit PCM.

    python -m tools_py.parity.pcm_dump <pcm.bin> [--ring 24576] [--rate 48000]

Per wall-clock second: the bytes written, the fill rate against what the ring plays (rate x 2 ch x 2 B), and the
RMS of the samples written (dBFS). A ring the game keeps full at a healthy level reads ~100% and a level near
the console's; a ring starved of writes or written with quiet samples reads as the parity check found it.
"""
import struct
import sys

import numpy as np


def read(path):
    data = open(path, "rb").read()
    out = []
    at = 0
    while at + 12 <= len(data):
        off, n, ms = struct.unpack_from("<III", data, at)
        at += 12
        chunk = data[at:at + n]
        at += n
        if len(chunk) < n:
            break
        out.append((off, n, ms, chunk))
    return out


def report(records, ring=24576, rate=48000, channels=2):
    if not records:
        return "no records"
    per_s = rate * channels * 2
    lines = [f"{len(records)} writes, {sum(r[1] for r in records)} bytes over {records[-1][2] / 1000:.1f} s; ring {ring} B, plays {per_s} B/s"]
    last = records[-1][2] // 1000
    for sec in range(last + 1):
        rs = [r for r in records if r[2] // 1000 == sec]
        if not rs:
            lines.append(f"  s{sec:03d}: no writes")
            continue
        total = sum(r[1] for r in rs)
        pcm = np.frombuffer(b"".join(r[3] for r in rs), dtype="<i2").astype(np.float32) / 32768.0
        rms = 20 * np.log10(np.sqrt((pcm ** 2).mean()) + 1e-9) if pcm.size else -99.0
        peak = 20 * np.log10(np.abs(pcm).max() + 1e-9) if pcm.size else -99.0
        offs = sorted(set(r[0] for r in rs))
        lines.append(f"  s{sec:03d}: {len(rs):3d} writes {total:7d} B = {100 * total / per_s:5.1f}% of playback  rms {rms:6.1f} dBFS peak {peak:6.1f}  offsets {offs[:4]}{'...' if len(offs) > 4 else ''}")
    sizes = sorted(set(r[1] for r in records))
    lines.append(f"write sizes seen: {sizes[:8]}")
    return "\n".join(lines)


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip().splitlines()[3])
        return 2
    ring = int(argv[argv.index("--ring") + 1]) if "--ring" in argv else 24576
    rate = int(argv[argv.index("--rate") + 1]) if "--rate" in argv else 48000
    print(report(read(argv[1]), ring, rate))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
