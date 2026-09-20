"""Sprint 9 Q0: the PCM ring dump reader (tools_py/parity/pcm_dump.py)."""
import os
import struct
import tempfile
import unittest

import numpy as np

from tools_py.parity import pcm_dump


def record(offset, samples, ms):
    pcm = np.asarray(samples, dtype="<i2").tobytes()
    return struct.pack("<III", offset, len(pcm), ms) + pcm


class PcmDumpTests(unittest.TestCase):
    def test_reads_records_and_reports_fill_and_level(self):
        loud = [16384, -16384] * 256    # -6 dBFS square, 512 samples = 1024 B
        quiet = [1638, -1638] * 256     # -26 dBFS
        blob = b"".join([record(0, loud, 10), record(1024, loud, 20), record(0, quiet, 1500)])
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "pcm.bin")
            open(path, "wb").write(blob)
            recs = pcm_dump.read(path)
        self.assertEqual([(r[0], r[1], r[2]) for r in recs], [(0, 1024, 10), (1024, 1024, 20), (0, 1024, 1500)])
        text = pcm_dump.report(recs, ring=24576, rate=48000)
        self.assertIn("3 writes, 3072 bytes", text)
        self.assertIn("s000:   2 writes    2048 B", text)
        self.assertIn("rms   -6.0 dBFS", text)
        self.assertIn("s001:   1 writes    1024 B", text)
        self.assertIn("rms  -26.0 dBFS", text)

    def test_truncated_tail_is_dropped_and_empty_is_said(self):
        blob = record(0, [1, -1] * 4, 0) + struct.pack("<III", 0, 100, 5) + b"\x00" * 10
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "pcm.bin")
            open(path, "wb").write(blob)
            recs = pcm_dump.read(path)
        self.assertEqual(len(recs), 1)
        self.assertEqual(pcm_dump.report([]), "no records")


if __name__ == "__main__":
    unittest.main()
