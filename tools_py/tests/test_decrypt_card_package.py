"""tools_py/decrypt_card_package.py and the card/disc split inside tools_py/decrypt_apache.py.

Everything here runs on bytes this file makes up. There is no game data in it and no fixture:
a fake EE stands in for the Unicorn harness and implements a toy DNAS whose two wrappers can
be undone by hand, so the suite needs neither Unicorn (Linux CI does not install it) nor a
disc nor a memory card. What the fake proves is the *shape* of each path -- which loader
entry points get called, in what order, with which length -- because that shape is the whole
finding: the memory-card path (FUN_001C60B0) runs 0x534848 and 0x535018 and nothing else,
while the disc path (FUN_001C5DA0) runs 0x539D00 and 0x539D50 in front of them.

The one case that touches the real package skips itself unless game/ is on the machine, and
even then it only counts and measures -- it reproduces no byte of it.
"""
import os
import struct
import sys
import tempfile
import types
import unittest
import zlib
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ---- importing the module under test without Unicorn -------------------------------------------
# decrypt_apache does `from ee_unicorn import EE, sext32` and `from unicorn import UC_HOOK_CODE`
# at import time. Both are absent on the Linux runner, so stand them up first. sext32 is the
# real one (decrypt_blob's return-code checks depend on it); EE and UC_HOOK_CODE are only ever
# named, never used, on the paths these cases drive.

def _sext32(v):
    v &= 0xffffffff
    return v - (1 << 32) if v & 0x80000000 else v


if 'unicorn' not in sys.modules:
    try:
        import unicorn  # noqa: F401
    except ImportError:
        fake = types.ModuleType('unicorn')
        fake.UC_HOOK_CODE = 4
        sys.modules['unicorn'] = fake
if 'ee_unicorn' not in sys.modules:
    try:
        import ee_unicorn  # noqa: F401
    except ImportError:
        fake = types.ModuleType('ee_unicorn')
        fake.EE = object
        fake.sext32 = _sext32
        sys.modules['ee_unicorn'] = fake

from tools_py import decrypt_apache, decrypt_card_package  # noqa: E402


# ---- a toy two-wrapper package -----------------------------------------------------------------

CONTENT_MAGIC = b'SYNTHCNT'
OUTER_MAGIC = b'SYNTHOUT'
CONTENT_HEADER = 0x580      # what 0x534848 reads: reaches buf+0x500
OUTER_HEADER = 1024         # what 0x539D00 reads, and what it strips


def card_blob(payload):
    """The shape the memory card holds: content header, then the deflate stream obscured.

    The header carries the inflated stream's length where the toy 0x534848 finds it, which is
    what the real one answers in *out4."""
    comp = zlib.compress(payload)
    head = bytearray(CONTENT_HEADER)
    head[0:8] = CONTENT_MAGIC
    struct.pack_into('<I', head, 0x500, len(comp))
    return bytes(head) + bytes(b ^ 0xA5 for b in comp)


def disc_blob(payload):
    """The shape the disc holds: the same package inside the signed container 0x539D00 checks."""
    inner = card_blob(payload)
    head = bytearray(OUTER_HEADER)
    head[0:8] = OUTER_MAGIC
    return bytes(head) + bytes((b + 0x33) & 0xff for b in inner)


class FakeEE:
    """Enough of tools_py.ee_unicorn.EE for decrypt_blob, plus a toy DNAS behind ee.call()."""

    def __init__(self, fail_at=None):
        self.mem = bytearray(0x1100000)
        self.calls = []
        self.data_reads = set()
        self.fail_at = fail_at or {}

    # --- memory
    def write(self, addr, data):
        self.mem[addr:addr + len(data)] = data

    def read(self, addr, n):
        return bytes(self.mem[addr:addr + n])

    def w32(self, addr, v):
        struct.pack_into('<I', self.mem, addr, v & 0xffffffff)

    def w64(self, addr, v):
        struct.pack_into('<Q', self.mem, addr, v & 0xffffffffffffffff)

    def r32(self, addr):
        return struct.unpack_from('<I', self.mem, addr)[0]

    def r64(self, addr):
        return struct.unpack_from('<Q', self.mem, addr)[0]

    # --- the guest functions decrypt_blob reaches
    def call(self, addr, args, sp=None):
        self.calls.append((addr, tuple(args)))
        if addr in self.fail_at:
            return self.fail_at[addr] & 0xffffffff
        return getattr(self, '_f%06x' % addr)(*args)

    def _f539d00(self, size, buf, out8):            # signed container: parse header
        if self.read(buf, 8) != OUTER_MAGIC:
            return 0xffffffff                       # -1
        self.w64(out8, size - OUTER_HEADER)
        return 0

    def _f539d50(self, size, payload, buf):         # signed container: body, in place, moved down
        if self.read(buf, 8) != OUTER_MAGIC:
            return 0xffffffff
        body = self.read(buf + OUTER_HEADER, payload)
        self.write(buf, bytes((b - 0x33) & 0xff for b in body))
        return payload

    def _f534848(self, size, buf, out4):            # content header -> inflated-stream length
        if self.read(buf, 8) != CONTENT_MAGIC:
            return 0xffffffff
        self.w32(out4, self.r32(buf + 0x500))
        return 0

    def _f535018(self, size, n, buf):               # content body, in place, moved down
        if self.read(buf, 8) != CONTENT_MAGIC:
            return 0xffffffff
        body = self.read(buf + CONTENT_HEADER, n)
        self.write(buf, bytes(b ^ 0xA5 for b in body))
        return 0


# ---- the split ---------------------------------------------------------------------------------

class DecryptBlobTest(unittest.TestCase):

    def setUp(self):
        self.payload = b'FTSCore synthetic overlay image ' * 400

    def test_disc_path_runs_all_four_entry_points_in_order(self):
        ee = FakeEE()
        out = decrypt_apache.decrypt_blob(ee, disc_blob(self.payload), name='ftscore')
        self.assertEqual(out, self.payload)
        self.assertEqual([a for a, _ in ee.calls], [0x539d00, 0x539d50, 0x534848, 0x535018])

    def test_card_path_runs_only_the_content_layer(self):
        ee = FakeEE()
        out = decrypt_apache.decrypt_blob(ee, card_blob(self.payload), name='ftscore', card=True)
        self.assertEqual(out, self.payload)
        self.assertEqual([a for a, _ in ee.calls], [0x534848, 0x535018])

    def test_card_path_never_touches_the_signed_container_entry_points(self):
        """The defect the download report hit: the disc path's 0x539D00 answers
        `payload = length` (nothing stripped) on a card package and 0x539D50 then refuses it.
        The card path must not ask either of them anything."""
        ee = FakeEE()
        decrypt_apache.decrypt_blob(ee, card_blob(self.payload), card=True)
        called = {a for a, _ in ee.calls}
        self.assertNotIn(0x539d00, called)
        self.assertNotIn(0x539d50, called)

    def test_card_path_passes_the_blobs_own_length(self):
        """0x534848 gets the byte count the card read returned -- no header subtracted.
        On the disc path it gets 0x539D50's answer instead, which is shorter by the wrapper."""
        blob = card_blob(self.payload)
        ee = FakeEE()
        decrypt_apache.decrypt_blob(ee, blob, card=True)
        sizes = {a: args[0] for a, args in ee.calls}
        self.assertEqual(sizes[0x534848], len(blob))
        self.assertEqual(sizes[0x535018], len(blob))

        dblob = disc_blob(self.payload)
        ee2 = FakeEE()
        decrypt_apache.decrypt_blob(ee2, dblob, card=False)
        sizes2 = {a: args[0] for a, args in ee2.calls}
        self.assertEqual(sizes2[0x539d00], len(dblob))
        self.assertEqual(sizes2[0x534848], len(dblob) - OUTER_HEADER)

    def test_both_paths_hand_the_same_buffer_address_to_every_step(self):
        ee = FakeEE()
        decrypt_apache.decrypt_blob(ee, card_blob(self.payload), card=True)
        self.assertEqual(ee.calls[0][1][1], decrypt_apache.BUF)     # 0x534848(size, buf, &out4)
        self.assertEqual(ee.calls[1][1][2], decrypt_apache.BUF)     # 0x535018(size, n, buf)

    def test_card_path_refuses_a_disc_package(self):
        """A blob that still has the signed container in front of it does not parse as a
        content header, and the tool says so rather than inflating rubbish."""
        ee = FakeEE()
        with self.assertRaises(SystemExit) as cm:
            decrypt_apache.decrypt_blob(ee, disc_blob(self.payload), card=True)
        self.assertIn('step3', str(cm.exception))

    def test_disc_path_refuses_a_card_package(self):
        """The download report's failure, reproduced in miniature."""
        ee = FakeEE()
        with self.assertRaises(SystemExit) as cm:
            decrypt_apache.decrypt_blob(ee, card_blob(self.payload), card=False)
        self.assertIn('step1', str(cm.exception))

    def test_a_negative_return_from_the_content_layer_stops_the_run(self):
        ee = FakeEE(fail_at={0x535018: 0xffffffff})
        with self.assertRaises(SystemExit) as cm:
            decrypt_apache.decrypt_blob(ee, card_blob(self.payload), card=True)
        self.assertIn('step4', str(cm.exception))


# ---- the archive, and the package driver --------------------------------------------------------

def build_zdb(entries, token=b'r0001'):
    """A synthetic APACHE00.ZDB: the 0xA0-byte header (count at 0x98), then one 0x5C row per
    entry, then the blobs. The shape tools_py.decrypt_apache.zdb_entries walks."""
    head = bytearray(0xa0)
    struct.pack_into('<I', head, 0x00, 0xfc)
    struct.pack_into('<I', head, 0x04, 1)
    head[0x14:0x14 + len(token)] = token
    struct.pack_into('<I', head, 0x98, len(entries))
    row_size = 0x5c
    off = 0xa0 + row_size * len(entries)
    rows = bytearray()
    body = bytearray()
    for name, blob in entries:
        row = bytearray(row_size)
        struct.pack_into('<I', row, 0, row_size)
        row[4:4 + len(name)] = name.encode()
        struct.pack_into('<II', row, 0x44, off + len(body), len(blob))
        rows += row
        body += blob
    return bytes(head) + bytes(rows) + bytes(body)


class ZdbEntriesTest(unittest.TestCase):

    def test_two_named_entries_come_back_whole_and_in_order(self):
        a, b = b'\x01' * 300, b'\x02' * 700
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'APACHE00.ZDB')
            with open(path, 'wb') as f:
                f.write(build_zdb([('ftscore', a), ('zsealetc', b)]))
            got = decrypt_apache.zdb_entries(path)
        self.assertEqual(list(got), ['ftscore', 'zsealetc'])
        self.assertEqual(got['ftscore'], a)
        self.assertEqual(got['zsealetc'], b)


class DecryptPackageTest(unittest.TestCase):

    def setUp(self):
        self.fts = b'ftscore image ' * 500
        self.zse = b'zsealetc image ' * 500

    def _run(self, card):
        blob = card_blob if card else disc_blob
        ee = FakeEE()
        with tempfile.TemporaryDirectory() as d:
            zdb = os.path.join(d, 'APACHE00.ZDB')
            with open(zdb, 'wb') as f:
                f.write(build_zdb([('ftscore', blob(self.fts)), ('zsealetc', blob(self.zse))]))
            out = os.path.join(d, 'out')
            with mock.patch.object(decrypt_apache, 'build_harness', return_value=ee) as bh:
                written = decrypt_apache.decrypt_package('/no/such/tree', zdb, out, card=card)
                self.assertEqual(bh.call_count, 1, 'the harness is booted once for both blobs')
            self.assertEqual([os.path.basename(p) for p in written],
                             ['ftscore.bin', 'zsealetc.bin'])
            return ee, [open(p, 'rb').read() for p in written]

    def test_card_package_writes_both_overlays(self):
        ee, (fts, zse) = self._run(card=True)
        self.assertEqual(fts, self.fts)
        self.assertEqual(zse, self.zse)
        self.assertEqual([a for a, _ in ee.calls], [0x534848, 0x535018] * 2)

    def test_disc_package_still_writes_both_overlays(self):
        """The refactor must not move the disc path: this is what build_revision.sh step 1 runs."""
        ee, (fts, zse) = self._run(card=False)
        self.assertEqual(fts, self.fts)
        self.assertEqual(zse, self.zse)
        self.assertEqual([a for a, _ in ee.calls],
                         [0x539d00, 0x539d50, 0x534848, 0x535018] * 2)

    def test_the_card_module_is_the_card_path(self):
        with mock.patch.object(decrypt_card_package, 'decrypt_package') as dp:
            decrypt_card_package.main('tree', 'zdb', 'out')
        dp.assert_called_once_with('tree', 'zdb', 'out', card=True)


class CliTest(unittest.TestCase):

    def test_a_missing_input_is_refused_before_any_emulation(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(SystemExit) as cm:
                decrypt_card_package.cli([d, os.path.join(d, 'nope.zdb'), d])
        self.assertEqual(cm.exception.code, 2)


# ---- the one case that looks at the real package -------------------------------------------------

CARD_ZDB = os.path.join(ROOT, 'game', 'r0004', 'card', 'APACHE00.ZDB')


@unittest.skipUnless(os.path.isfile(CARD_ZDB), 'game/r0004/card/APACHE00.ZDB is not on this machine')
class RealCardPackageTest(unittest.TestCase):
    """Counts and lengths only -- no byte of the package is asserted or reproduced."""

    def test_the_downloaded_package_is_the_same_archive_shape(self):
        entries = decrypt_apache.zdb_entries(CARD_ZDB)
        self.assertEqual(sorted(entries), ['ftscore', 'zsealetc'])
        total = os.path.getsize(CARD_ZDB)
        self.assertEqual(sum(len(v) for v in entries.values()) + 0xa0 + 2 * 0x5c, total,
                         'the two blobs plus the header and rows account for the whole file')
        for name, blob in entries.items():
            self.assertGreater(len(blob), CONTENT_HEADER, name)


if __name__ == '__main__':
    unittest.main()
