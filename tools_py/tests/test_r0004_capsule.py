"""tools_py/r0004/capsule.py: the PSRewired r0004 capsule's encrypted code stack, decoded.

Everything here runs on SYNTHETIC bytes. There is no capsule byte and no game byte in this file:
the fixtures are built here -- a fake ps2-packer ELF around a fake image, a fake key, and a fake
stack the test encrypts with its own copy of the scheme. The addresses mirror the ranges
docs/research/43-r0004-capsule.md documents so the classes exercised are the real ones, but no
value is taken from the decoded write list.

Two cases pin the scheme to something the module cannot influence:
`test_a_literal_vector_pins_the_key_and_the_by_word_schedule` asserts a hand-computed ciphertext
literal, and `test_a_by_pair_schedule_is_rejected` builds the wrong schedule and demands a raise.
`RealCapsuleTest` skips unless the capsule is on this machine, and even then asserts only a range
and that the version string parses.
"""
import io
import os
import struct
import tempfile
import unittest
import zlib
from unittest import mock

from tools_py.r0004 import capsule


# ---- synthetic fixtures -------------------------------------------------------------------------

# A made-up key. It is not the capsule's key and no part of it comes from any file.
KEY = struct.pack("<8I", 0x11111111, 0x22222222, 0x33333333, 0x44444444,
                  0x55555555, 0x66666666, 0x77777777, 0x88888888)

# The capsule that would be decoded with it, if one existed, in the session's own machine.
CAPSULE_PATH = os.environ.get("R0004_CAPSULE", r"C:\projects\socom_pc\game\r0004\r0004v002.elf")


def encrypt_pairs(pairs, key=KEY, phase=0):
    """The scheme, written out here so the test owns it independently of the module."""
    out = bytearray()
    words = []
    for address, value in pairs:
        words.append(address)
        words.append(value)
    for i, word in enumerate(words):
        k = struct.unpack_from("<I", key, ((i + phase) % (len(key) // 4)) * 4)[0]
        out += struct.pack("<I", word ^ k)
    return bytes(out)


def make_capsule_header(version, ciphertext):
    head = version.encode("ascii").ljust(8, b"\0")
    head += struct.pack("<III", len(ciphertext), 0, 0)
    return head + ciphertext + b"\0" * 8


def make_image(pairs, version="0000001", filler=b"\xaa", key=KEY):
    """An image with the key, the header and a decoy digit-string at known offsets."""
    body = bytearray(filler * 0x400)
    body[0x080:0x080 + len(key)] = key          # the key, as it sits in the real image
    body[0x100:0x110] = b"mc0:UPDATE.DAT\0\0"
    body[0x120:0x128] = b"9999999\0"            # a decoy: version-shaped, no stack behind it
    blob = make_capsule_header(version, encrypt_pairs(pairs, key))
    offset = 0x200
    body[offset:offset + len(blob)] = blob
    return bytes(body), offset + capsule.HEADER_SIZE


def make_packed_elf(image, load_vaddr=0x00100000, entry=0x001000E0):
    comp = zlib.compress(image, 6)
    stub = struct.pack("<IIIIII", entry, 1, len(image), 0xE072, load_vaddr, len(comp))
    seg = stub + comp + b"\0" * 16
    phoff = 0x34
    off = phoff + 32
    eh = struct.pack("<4s5B7x2H5I6H", b"\x7fELF", 1, 1, 1, 0, 0, 2, 8, 1,
                     0x01D00008, phoff, 0, 0x20, 0x34, 32, 1, 40, 0, 0)
    ph = struct.pack("<8I", 1, off, 0x01CF3400, 0x01CF3400, len(seg), len(seg) + 0x400, 5, 0x10)
    return eh + ph + seg


def make_game_elf(segments):
    """A minimal ELF carrying only program headers: (vaddr, memsz, flags) each."""
    phoff = 0x34
    eh = struct.pack("<4s5B7x2H5I6H", b"\x7fELF", 1, 1, 1, 0, 0, 2, 8, 1,
                     0x100000, phoff, 0, 0x20, 0x34, 32, len(segments), 40, 0, 0)
    phs = b"".join(struct.pack("<8I", 1, 0x1000, va, va, msz, msz, fl, 0x1000)
                   for va, msz, fl in segments)
    return eh + phs


PAIRS = [
    (0x80099000, 0x27BDFFF0),   # resident: a kernel block
    (0x80099004, 0x03E00008),
    (0x000AB000, 0x00000000),   # resident: a user-memory variable block
    (0x000AB004, 0x0000000B),
    (0x00123454, 0xDEADBEEF),   # code patch: inside the game text window
    (0x00600000, 0x41414141),   # data constant: game memory above the text window
    (0x800002FC, 0x0C00C400),   # resident: the kernel hook vector
]


# ---- the unpacker -------------------------------------------------------------------------------

class UnpackTest(unittest.TestCase):
    def test_inflates_the_zlib_payload_at_0x18_of_the_load(self):
        image, _ = make_image(PAIRS)
        packed = capsule.unpack(make_packed_elf(image))
        self.assertEqual(packed.image, image)
        self.assertEqual(packed.load_vaddr, 0x00100000)
        self.assertEqual(packed.entry, 0x001000E0)

    def test_a_plain_elf_is_refused(self):
        eh = struct.pack("<4s5B7x2H5I6H", b"\x7fELF", 1, 1, 1, 0, 0, 2, 8, 1,
                         0x100000, 0x34, 0, 0x20, 0x34, 32, 0, 40, 0, 0)
        with self.assertRaises(ValueError):
            capsule.unpack(eh)

    def test_a_non_elf_is_refused(self):
        with self.assertRaises(ValueError):
            capsule.unpack(b"not an elf at all" * 8)

    def test_an_unpacked_load_before_the_packed_one_is_stepped_over(self):
        image, _ = make_image(PAIRS)
        good = make_packed_elf(image)
        seg = good[0x54:]
        phoff = 0x34
        first = struct.pack("<8I", 1, 0, 0x00090000, 0x00090000, 0x40, 0x40, 5, 0x10)
        second = struct.pack("<8I", 1, phoff + 64, 0x01CF3400, 0x01CF3400, len(seg), len(seg), 5, 16)
        eh = struct.pack("<4s5B7x2H5I6H", b"\x7fELF", 1, 1, 1, 0, 0, 2, 8, 1,
                         0x01D00008, phoff, 0, 0x20, 0x34, 32, 2, 40, 0, 0)
        self.assertEqual(capsule.unpack(eh + first + second + seg).image, image)


# ---- the locator --------------------------------------------------------------------------------

class LocateStackTest(unittest.TestCase):
    def test_finds_the_header_and_skips_the_decoy(self):
        image, cipher_off = make_image(PAIRS, version="0000001")
        offset, length, version = capsule.locate_stack(image)
        self.assertEqual(offset, cipher_off)
        self.assertEqual(length, len(PAIRS) * 8)
        self.assertEqual(version, "0000001")

    def test_no_stack_at_all_raises(self):
        with self.assertRaises(LookupError):
            capsule.locate_stack(b"\xaa" * 0x400)

    def test_two_stacks_raise_and_the_error_names_both(self):
        one, _ = make_image(PAIRS)
        two, _ = make_image(PAIRS[:4], version="0000002")
        with self.assertRaises(LookupError) as caught:
            capsule.locate_stack(one + two)
        self.assertIn("ambiguous", str(caught.exception))
        self.assertIn("'0000001'", str(caught.exception))
        self.assertIn("'0000002'", str(caught.exception))

    def test_a_length_that_does_not_reach_the_terminator_is_named_as_such(self):
        image = bytearray(make_image(PAIRS)[0])
        struct.pack_into("<I", image, 0x208, len(PAIRS) * 8 - 8)  # one pair short
        with self.assertRaises(LookupError) as caught:
            capsule.locate_stack(bytes(image))
        self.assertIn("terminator", str(caught.exception))

    def test_locates_a_bare_eight_byte_header_too(self):
        """The r0005 Patch Compiler's update.dat shape: a version string, four zeros, ciphertext."""
        blob = b"59.0\0\0\0\0" + encrypt_pairs(PAIRS) + b"\0" * 8
        offset, length, version = capsule.locate_stack(blob)
        self.assertEqual(offset, 8)
        self.assertEqual(version, "59.0")
        self.assertEqual(length, len(PAIRS) * 8)


# ---- the key ------------------------------------------------------------------------------------

class LocateKeyTest(unittest.TestCase):
    def test_finds_the_key_wherever_it_sits(self):
        image, cipher_off = make_image(PAIRS)
        blob = image[cipher_off:cipher_off + len(PAIRS) * 8]
        key, offsets = capsule.locate_key(image, blob, pairs=4)
        self.assertEqual(key, KEY)
        self.assertIn(0x080, offsets)

    def test_a_window_of_the_ciphertext_is_never_the_key(self):
        """A ciphertext window one key-period in "decrypts" the stack to plausible nonsense."""
        image, cipher_off = make_image(PAIRS)
        blob = image[cipher_off:cipher_off + len(PAIRS) * 8]
        key, offsets = capsule.locate_key(image, blob, pairs=4,
                                          exclude=(cipher_off, cipher_off + len(blob)))
        self.assertEqual(key, KEY)
        self.assertTrue(all(o + len(KEY) <= cipher_off or o >= cipher_off + len(blob)
                            for o in offsets))

    def test_an_image_without_the_key_raises(self):
        image, cipher_off = make_image(PAIRS)
        blob = image[cipher_off:cipher_off + len(PAIRS) * 8]
        stripped = image[:0x080] + b"\xcc" * len(KEY) + image[0x080 + len(KEY):]
        with self.assertRaises(LookupError):
            capsule.locate_key(stripped, blob, pairs=4)

    def test_no_key_constant_is_exported(self):
        """C1: the capsule's key must never be a literal in this repository."""
        for name in dir(capsule):
            value = getattr(capsule, name)
            if isinstance(value, (bytes, bytearray)) and len(value) >= 8:
                self.fail("capsule.%s is a %d-byte literal -- key material does not belong here"
                          % (name, len(value)))


# ---- the decryptor ------------------------------------------------------------------------------

class DecryptStackTest(unittest.TestCase):
    def test_a_stack_this_test_encrypted_decodes_back(self):
        got = capsule.decrypt_stack(encrypt_pairs(PAIRS), KEY)
        self.assertEqual([(a, v) for _, a, v in got], PAIRS)
        self.assertEqual({t for t, _, _ in got}, {"w"})

    def test_a_literal_vector_pins_the_key_and_the_by_word_schedule(self):
        """Two pairs, hand-computed against KEY, as a hex literal the module cannot influence.

        Pair 0 uses key words 0 and 1; pair 1 uses key words 2 and 3. A schedule that advanced
        once per PAIR would use key word 0 for both halves of pair 0 and key word 1 for pair 1,
        and could not produce these eight words.
        """
        blob = bytes.fromhex("45250311" "cd9c8ffc" "6b072133" "4f444444")
        self.assertEqual(capsule.decrypt_stack(blob, KEY),
                         [("w", 0x00123454, 0xDEADBEEF), ("w", 0x00123458, 0x0000000B)])

    def test_a_by_pair_schedule_is_rejected(self):
        """The same two pairs, encrypted one key word per PAIR: the module must refuse them."""
        words = [0x00123454, 0xDEADBEEF, 0x00123458, 0x0000000B]
        blob = b"".join(struct.pack("<I", w ^ struct.unpack_from("<I", KEY, (i // 2) * 4)[0])
                        for i, w in enumerate(words))
        with self.assertRaises(ValueError):
            capsule.decrypt_stack(blob, KEY)

    def test_a_zero_ciphertext_word_ends_the_stack(self):
        blob = encrypt_pairs(PAIRS) + b"\0" * 8 + encrypt_pairs([(0x00700000, 1)], phase=16)
        self.assertEqual(len(capsule.decrypt_stack(blob, KEY)), len(PAIRS))

    def test_the_key_cycles_over_a_stack_longer_than_the_key(self):
        long_pairs = [(0x00600000 + 4 * i, 0x1000 + i) for i in range(9)]
        self.assertEqual([(a, v) for _, a, v in
                          capsule.decrypt_stack(encrypt_pairs(long_pairs), KEY)], long_pairs)

    def test_a_foreign_key_is_rejected_by_the_plausibility_check(self):
        other = bytes((b + 1) & 0xFF for b in KEY)
        with self.assertRaises(ValueError):
            capsule.decrypt_stack(encrypt_pairs(PAIRS), other)

    def test_a_truncated_stack_raises(self):
        with self.assertRaises(ValueError):
            capsule.decrypt_stack(encrypt_pairs(PAIRS)[:-4], KEY)

    def test_an_empty_key_raises(self):
        with self.assertRaises(ValueError):
            capsule.decrypt_stack(encrypt_pairs(PAIRS), b"")


# ---- the classifier -----------------------------------------------------------------------------

class ClassifyTest(unittest.TestCase):
    def test_the_three_classes(self):
        got = capsule.classify(capsule.decrypt_stack(encrypt_pairs(PAIRS), KEY))
        self.assertEqual([w[1] for w in got["resident"]],
                         [0x80099000, 0x80099004, 0x000AB000, 0x000AB004, 0x800002FC])
        self.assertEqual([w[1] for w in got["code_patch"]], [0x00123454])
        self.assertEqual([w[1] for w in got["data"]], [0x00600000])

    def test_kseg_addresses_are_masked_before_classing(self):
        got = capsule.classify([("w", 0xA0031000, 0), ("w", 0x80123456, 0)])
        self.assertEqual(len(got["resident"]), 1)
        self.assertEqual(len(got["code_patch"]), 1)

    def test_the_high_resident_window_above_the_packer_load(self):
        self.assertEqual(len(capsule.classify([("w", 0x01CF3400, 0)])["resident"]), 1)

    def test_measured_windows_from_an_elf_beat_the_provisional_constants(self):
        """0x00600000 is loaded, executable content -- a code patch, not a data constant."""
        elf = make_game_elf([(0x00100000, 0xD5000, 5),      # text
                             (0x001D5000, 0x11680, 6),      # data
                             (0x001E7000, 0x4A0000, 7)])    # text, past the round number
        windows = capsule.game_windows(elf)
        self.assertFalse(windows.provisional)
        self.assertEqual(windows.end, 0x00687000)
        got = capsule.classify([("w", 0x00600000, 0), ("w", 0x001D6000, 0), ("w", 0x00700000, 0)],
                               windows)
        self.assertEqual([w[1] for w in got["code_patch"]], [0x00600000])
        self.assertEqual([w[1] for w in got["data"]], [0x001D6000])
        self.assertEqual([w[1] for w in got["resident"]], [0x00700000])

    def test_an_elf_with_no_loadable_segment_raises(self):
        with self.assertRaises(ValueError):
            capsule.game_windows(make_game_elf([]))


# ---- the indirect tables ------------------------------------------------------------------------

class PairTableTest(unittest.TestCase):
    def test_a_null_terminated_pair_table_inside_a_resident_block_is_found(self):
        base = 0x80099250
        table = [(0x00ABC670, 0x03E00008), (0x00ABC674, 0x00000000)]
        writes = []
        for i, (a, v) in enumerate(table):
            writes.append(("w", base + i * 8, a))
            writes.append(("w", base + i * 8 + 4, v))
        writes.append(("w", base + len(table) * 8, 0))
        writes.append(("w", base + len(table) * 8 + 4, 0))
        self.assertEqual(capsule.find_pair_tables(writes), [(base, table)])

    def test_a_misaligned_or_unaligned_run_is_not_a_table(self):
        """A version string's tail can read as one game address followed by a zero word."""
        writes = [("w", 0x000AB00C, 0x00313130), ("w", 0x000AB010, 0), ("w", 0x000AB014, 0)]
        self.assertEqual(capsule.find_pair_tables(writes), [])
        odd = [("w", 0x80099240, 0x00ABC672), ("w", 0x80099244, 0x03E00008),
               ("w", 0x80099248, 0), ("w", 0x8009924C, 0)]
        self.assertEqual(capsule.find_pair_tables(odd), [])

    def test_a_run_of_ordinary_code_is_not_a_table(self):
        writes = [("w", 0x80099000 + i * 4, 0x27BDFFF0) for i in range(8)]
        self.assertEqual(capsule.find_pair_tables(writes), [])


# ---- the command --------------------------------------------------------------------------------

class MainTest(unittest.TestCase):
    def test_writes_stack_and_summary(self):
        image, _ = make_image(PAIRS)
        with tempfile.TemporaryDirectory() as tmp:
            elf = os.path.join(tmp, "fake.elf")
            with open(elf, "wb") as fh:
                fh.write(make_packed_elf(image))
            out = os.path.join(tmp, "decoded")
            buf = io.StringIO()
            with mock.patch("sys.stdout", buf):
                rc = capsule.main([elf, "--out", out])
            self.assertEqual(rc, 0)
            with open(os.path.join(out, "stack.txt")) as fh:
                lines = fh.read().splitlines()
            self.assertEqual(len(lines), len(PAIRS))
            self.assertEqual(lines[0], "w 80099000 27BDFFF0")
            with open(os.path.join(out, "summary.txt")) as fh:
                summary = fh.read()
            self.assertIn("version 0000001", summary)
            self.assertIn("writes %d" % len(PAIRS), summary)
            self.assertIn("resident 5", summary)
            self.assertIn("code_patch 1", summary)
            self.assertIn("data 1", summary)
            self.assertIn("000AB000-000AB004", summary)
            self.assertIn("PROVISIONAL", summary)
            self.assertIn("WARNING", buf.getvalue())

    def test_the_elf_option_replaces_the_provisional_windows(self):
        image, _ = make_image(PAIRS)
        with tempfile.TemporaryDirectory() as tmp:
            elf = os.path.join(tmp, "fake.elf")
            with open(elf, "wb") as fh:
                fh.write(make_packed_elf(image))
            game = os.path.join(tmp, "game.elf")
            with open(game, "wb") as fh:
                fh.write(make_game_elf([(0x00100000, 0x586F80, 5)]))
            buf = io.StringIO()
            with mock.patch("sys.stdout", buf):
                capsule.main([elf, "--out", os.path.join(tmp, "d"), "--elf", game])
            self.assertNotIn("PROVISIONAL", buf.getvalue())
            self.assertNotIn("WARNING", buf.getvalue())
            self.assertIn("code_patch 2", buf.getvalue())  # 0x00600000 is loaded text here

    def test_a_capsule_with_no_stack_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as tmp:
            elf = os.path.join(tmp, "fake.elf")
            with open(elf, "wb") as fh:
                fh.write(make_packed_elf(b"\xaa" * 0x400))
            with mock.patch("sys.stdout", io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
                self.assertNotEqual(capsule.main([elf, "--out", os.path.join(tmp, "d")]), 0)

    def test_a_stack_whose_key_is_elsewhere_needs_key_image(self):
        """The r0005 update.dat carries no key; --key-image supplies one."""
        image, _ = make_image(PAIRS)
        blob = b"59.0\0\0\0\0" + encrypt_pairs(PAIRS) + b"\0" * 8
        with tempfile.TemporaryDirectory() as tmp:
            dat = os.path.join(tmp, "update.dat")
            with open(dat, "wb") as fh:
                fh.write(blob)
            src = os.path.join(tmp, "image.bin")
            with open(src, "wb") as fh:
                fh.write(image)
            with mock.patch("sys.stdout", io.StringIO()), mock.patch("sys.stderr", io.StringIO()):
                self.assertNotEqual(capsule.main([dat, "--out", os.path.join(tmp, "a")]), 0)
                self.assertEqual(capsule.main([dat, "--out", os.path.join(tmp, "b"),
                                               "--key-image", src]), 0)

    def test_a_raw_image_is_accepted_without_the_packer(self):
        image, _ = make_image(PAIRS)
        with tempfile.TemporaryDirectory() as tmp:
            raw = os.path.join(tmp, "image.bin")
            with open(raw, "wb") as fh:
                fh.write(image)
            out = os.path.join(tmp, "decoded")
            with mock.patch("sys.stdout", io.StringIO()):
                self.assertEqual(capsule.main([raw, "--out", out]), 0)
            self.assertTrue(os.path.exists(os.path.join(out, "stack.txt")))


# ---- the one case that touches the real capsule, and only if it is here -------------------------

@unittest.skipUnless(os.path.exists(CAPSULE_PATH), "the r0004 capsule is not on this machine")
class RealCapsuleTest(unittest.TestCase):
    """No capsule byte is in this file: the assertions are a range and a string shape."""

    def test_the_real_capsule_decodes_to_plausible_addresses(self):
        with open(CAPSULE_PATH, "rb") as fh:
            packed = capsule.unpack(fh.read())
        offset, length, version = capsule.locate_stack(packed.image)
        blob = packed.image[offset:offset + length]
        key, _offsets = capsule.locate_key(packed.image, blob,
                                           exclude=(offset, offset + length))
        writes = capsule.decrypt_stack(blob, key)
        self.assertTrue(version and version.isprintable() and version.strip())
        self.assertTrue(writes)
        first = writes[0][1] & capsule.ADDR_MASK
        self.assertLess(first, 0x02000000)
        self.assertTrue(any(0x00080000 <= (a & capsule.ADDR_MASK) < 0x02000000
                            for _t, a, _v in writes))


if __name__ == "__main__":
    unittest.main()
