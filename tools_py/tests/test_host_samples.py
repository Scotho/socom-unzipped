import unittest
from tools_py.parity import host_samples

CSV = """2026-09-17T10:00:00.0000000+02:00,12.5,socom2=40.0,socom2=300
2026-09-17T10:00:01.0000000+02:00,90.1,socom2=99.0,socom2=1450
2026-09-17T10:00:02.0000000+02:00,40.0,socom2=50.0,socom2=420
"""

class Parse(unittest.TestCase):
    def test_rows_carry_the_working_set(self):
        rows = host_samples.parse_text(CSV)
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[1]["ws_mb"]["socom2"], 1450.0)
    def test_rise_is_peak_minus_first(self):
        rows = host_samples.parse_text(CSV)
        self.assertAlmostEqual(host_samples.working_set_rise_mb(rows), 1150.0, places=1)
    def test_three_field_rows_still_parse(self):
        rows = host_samples.parse_text("2026-09-17T10:00:00Z,5.0,socom2=1.0\n")
        self.assertEqual(rows[0]["ws_mb"], {})
        self.assertEqual(host_samples.working_set_rise_mb(rows), 0.0)
