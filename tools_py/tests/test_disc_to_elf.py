"""tools_py/disc_to_elf.py: the one command from a stranger's ISO to a buildable ELF.

Everything here runs on synthetic bytes. There is no game data in this file and none in a fixture:
the ISO9660 cases build their own image (a PVD, two directories, a handful of files) and the two
emulation stages are driven through fake `tools_py.decrypt_apache` / `tools_py.dnas_selfdecrypt`
modules, so the suite needs no Unicorn (the Linux workflow does not install it) and no disc.

What is NOT covered here, because only a disc can cover it: that the recorded digests in
tools_py/disc_to_elf_expected.json are the ones the real r0001 disc produces. That was measured by
running the command from nothing -- docs/superpowers/plans/2026-09-21-sprint-10-disc-to-elf.md has
the numbers and the timings.
"""
import io
import json
import os
import shutil
import struct
import sys
import tempfile
import types
import unittest
from unittest import mock

from tools_py import disc_to_elf

SECTOR = 2048
BUILD_ID = "SOCOM 2 r0001 17:22:21 Oct 11 2003"


# ---- a synthetic ISO9660 image -----------------------------------------------------------------

def _record(name, extent, size, flags):
    """One ISO9660 directory record, padded to an even length."""
    length = 33 + len(name)
    length += length % 2
    rec = bytearray(length)
    rec[0] = length
    struct.pack_into("<I", rec, 2, extent)
    struct.pack_into(">I", rec, 6, extent)
    struct.pack_into("<I", rec, 10, size)
    struct.pack_into(">I", rec, 14, size)
    rec[25] = flags
    struct.pack_into("<H", rec, 28, 1)
    struct.pack_into(">H", rec, 30, 1)
    rec[32] = len(name)
    rec[33:33 + len(name)] = name
    return bytes(rec)


def build_iso(path, files, volume_id="SOCOM_II", block_size=SECTOR):
    """A minimal two-level ISO9660 image. `files` is {"NAME": b"bytes"} where a name with one slash
    ("SUB/DEEP.BIN") lands in a subdirectory, which is what proves the walk recurses.

    Returns {"/NAME": (lbn, bytes)}. Sector 16 is the PVD, 17 the root directory, one sector per
    subdirectory after it, then the file data, one file per sector boundary (as a real disc does)."""
    dirs = sorted({name.split("/")[0] for name in files if "/" in name})
    root_lbn = 17
    dir_lbn = {d: root_lbn + 1 + i for i, d in enumerate(dirs)}
    lbn = root_lbn + 1 + len(dirs)
    placed = {}
    for name in sorted(files):
        placed[name] = lbn
        lbn += max(1, (len(files[name]) + SECTOR - 1) // SECTOR)
    total_sectors = lbn

    def directory(self_lbn, parent_lbn, entries):
        out = bytearray()
        out += _record(b"\x00", self_lbn, SECTOR, 2)
        out += _record(b"\x01", parent_lbn, SECTOR, 2)
        for name, extent, size, flags in entries:
            out += _record(name, extent, size, flags)
        assert len(out) <= SECTOR, "the synthetic directory outgrew one sector"
        return bytes(out) + bytes(SECTOR - len(out))

    root_entries = [(name.encode() + b";1", placed[name], len(files[name]), 0)
                    for name in sorted(files) if "/" not in name]
    root_entries += [(d.encode(), dir_lbn[d], SECTOR, 2) for d in dirs]
    image = bytearray(total_sectors * SECTOR)
    pvd = bytearray(SECTOR)
    pvd[0] = 1
    pvd[1:6] = b"CD001"
    pvd[6] = 1
    pvd[40:72] = volume_id.encode().ljust(32)
    struct.pack_into("<I", pvd, 80, total_sectors)
    struct.pack_into(">I", pvd, 84, total_sectors)
    struct.pack_into("<H", pvd, 128, block_size)
    struct.pack_into(">H", pvd, 130, block_size)
    pvd[156:156 + 34] = _record(b"\x00", root_lbn, SECTOR, 2)
    image[16 * SECTOR:17 * SECTOR] = pvd
    image[root_lbn * SECTOR:(root_lbn + 1) * SECTOR] = directory(root_lbn, root_lbn, root_entries)
    for d in dirs:
        entries = [(name.split("/", 1)[1].encode() + b";1", placed[name], len(files[name]), 0)
                   for name in sorted(files) if name.startswith(d + "/")]
        image[dir_lbn[d] * SECTOR:(dir_lbn[d] + 1) * SECTOR] = directory(dir_lbn[d], root_lbn, entries)
    for name, data in files.items():
        start = placed[name] * SECTOR
        image[start:start + len(data)] = data
    with open(path, "wb") as fh:
        fh.write(image)
    return {"/" + name: (placed[name], data) for name, data in files.items()}


class SyntheticIsoTest(unittest.TestCase):
    """The reader, against an image the test builds. No 7z, no game bytes."""

    FILES = {
        "SCUS_972.75": b"boot elf bytes" * 7,
        "SYSTEM.CNF": b"BOOT2 = cdrom0:\\SCUS_972.75;1\r\n",
        "SUB/DEEP.BIN": bytes(range(256)) * 12,
    }

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="disc_to_elf_iso_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.iso = os.path.join(self.tmp, "synthetic.iso")
        self.placed = build_iso(self.iso, dict(self.FILES))

    def test_every_file_comes_back_with_its_lbn_and_size(self):
        files, volume_id, sectors = disc_to_elf.read_tree(self.iso)
        self.assertEqual(volume_id, "SOCOM_II")
        self.assertEqual(sectors, os.path.getsize(self.iso) // SECTOR)
        self.assertEqual(sorted(name for _, _, name in files),
                         ["/SCUS_972.75", "/SUB/DEEP.BIN", "/SYSTEM.CNF"])
        by_name = {name: (lbn, size) for lbn, size, name in files}
        for name, (lbn, data) in self.placed.items():
            self.assertEqual(by_name[name], (lbn, len(data)), name)

    def test_extract_writes_the_bytes_and_builds_the_directories(self):
        files, _, _ = disc_to_elf.read_tree(self.iso)
        dest = os.path.join(self.tmp, "disc")
        written, kept, total = disc_to_elf.extract(self.iso, files, dest, log=lambda *a: None)
        self.assertEqual((written, kept), (3, 0))
        self.assertEqual(total, sum(len(d) for d in self.FILES.values()))
        for name, (_, data) in self.placed.items():
            with open(os.path.join(dest, *name.strip("/").split("/")), "rb") as fh:
                self.assertEqual(fh.read(), data, name)
        self.assertFalse([p for p in os.listdir(dest) if p.endswith(".part")])

    def test_a_second_extract_keeps_every_file_and_force_rewrites_them(self):
        files, _, _ = disc_to_elf.read_tree(self.iso)
        dest = os.path.join(self.tmp, "disc")
        disc_to_elf.extract(self.iso, files, dest, log=lambda *a: None)
        self.assertEqual(disc_to_elf.extract(self.iso, files, dest, log=lambda *a: None)[:2], (0, 3))
        self.assertEqual(disc_to_elf.extract(self.iso, files, dest, log=lambda *a: None, force=True)[:2], (3, 0))

    def test_a_file_of_the_wrong_size_is_written_again(self):
        files, _, _ = disc_to_elf.read_tree(self.iso)
        dest = os.path.join(self.tmp, "disc")
        disc_to_elf.extract(self.iso, files, dest, log=lambda *a: None)
        with open(os.path.join(dest, "SYSTEM.CNF"), "wb") as fh:
            fh.write(b"half")
        self.assertEqual(disc_to_elf.extract(self.iso, files, dest, log=lambda *a: None)[:2], (1, 2))
        with open(os.path.join(dest, "SYSTEM.CNF"), "rb") as fh:
            self.assertEqual(fh.read(), self.FILES["SYSTEM.CNF"])

    def test_a_truncated_image_is_refused_before_anything_is_written(self):
        with open(self.iso, "r+b") as fh:
            fh.truncate(os.path.getsize(self.iso) - SECTOR)
        with self.assertRaises(disc_to_elf.Refusal) as caught:
            disc_to_elf.read_tree(self.iso)
        self.assertEqual(caught.exception.code, disc_to_elf.EXIT_MISMATCH)
        self.assertIn("truncated", caught.exception.sentence)
        self.assertIn("2048 bytes short", caught.exception.sentence)

    def test_a_file_that_runs_past_the_end_is_refused_even_when_the_descriptor_agrees(self):
        # A dump that lost its tail AND was re-described: the volume size matches the file, so only
        # the per-file check can see it.
        short = os.path.getsize(self.iso) - SECTOR
        with open(self.iso, "r+b") as fh:
            fh.truncate(short)
            fh.seek(16 * SECTOR + 80)
            fh.write(struct.pack("<I", short // SECTOR))
        with self.assertRaises(disc_to_elf.Refusal) as caught:
            disc_to_elf.read_tree(self.iso)
        self.assertEqual(caught.exception.code, disc_to_elf.EXIT_MISMATCH)
        self.assertIn("truncated", caught.exception.sentence)
        self.assertIn("/SYSTEM.CNF", caught.exception.sentence)   # the last file on the image

    def test_a_file_that_is_not_an_iso_is_refused_by_name(self):
        junk = os.path.join(self.tmp, "not.iso")
        with open(junk, "wb") as fh:
            fh.write(b"PK\x03\x04" + bytes(100000))
        with self.assertRaises(disc_to_elf.Refusal) as caught:
            disc_to_elf.read_tree(junk)
        self.assertEqual(caught.exception.code, disc_to_elf.EXIT_DISC_NOT_R0001)
        self.assertIn("ISO9660", caught.exception.sentence)

    def test_a_missing_path_is_disc_not_found(self):
        with self.assertRaises(disc_to_elf.Refusal) as caught:
            disc_to_elf.read_tree(os.path.join(self.tmp, "nothing-here.iso"))
        self.assertEqual(caught.exception.code, disc_to_elf.EXIT_DISC_NOT_FOUND)

    def test_a_cd_sized_logical_block_is_refused(self):
        odd = os.path.join(self.tmp, "odd.iso")
        build_iso(odd, dict(self.FILES), block_size=800)
        with self.assertRaises(disc_to_elf.Refusal) as caught:
            disc_to_elf.read_tree(odd)
        self.assertEqual(caught.exception.code, disc_to_elf.EXIT_DISC_NOT_R0001)
        self.assertIn("800", caught.exception.sentence)


class StageExtractTest(unittest.TestCase):
    """The stage around the reader: the revision gate, the layout note, the recording."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="disc_to_elf_stage_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.boot = b"a synthetic boot elf" * 100
        self.iso = os.path.join(self.tmp, "synthetic.iso")
        build_iso(self.iso, {"SCUS_972.75": self.boot, "RUN/RAW/APACHE00.ZDB": b"zdb" * 500})
        self.expected = {"inputs": {"SCUS_972.75": {"size": len(self.boot),
                                                    "sha256": disc_to_elf.sha256_bytes(self.boot)}}}
        self.lines = []

    def log(self, line):
        self.lines.append(line)

    def test_the_stage_extracts_and_records_the_shape_it_had_never_seen(self):
        disc_to_elf.stage_extract(self.iso, os.path.join(self.tmp, "disc"), self.expected, log=self.log)
        self.assertEqual(self.expected["disc"]["files"], 2)
        self.assertEqual(len(self.expected["disc"]["manifest_sha256"]), 64)
        self.assertTrue(any("recorded disc.files" in line for line in self.lines), self.lines)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "disc", "SCUS_972.75")))

    def test_a_boot_elf_of_another_revision_is_refused_as_not_r0001(self):
        self.expected["inputs"]["SCUS_972.75"]["sha256"] = "0" * 64
        with self.assertRaises(disc_to_elf.Refusal) as caught:
            disc_to_elf.stage_extract(self.iso, os.path.join(self.tmp, "disc"), self.expected, log=self.log)
        self.assertEqual(caught.exception.code, disc_to_elf.EXIT_DISC_NOT_R0001)
        self.assertIn("r0001", caught.exception.sentence)
        self.assertFalse(os.path.isdir(os.path.join(self.tmp, "disc")), "it refused before writing 4 GB")

    def test_an_image_without_a_boot_elf_is_refused_as_not_r0001(self):
        other = os.path.join(self.tmp, "other.iso")
        build_iso(other, {"SLES_123.45": b"a european disc"})
        with self.assertRaises(disc_to_elf.Refusal) as caught:
            disc_to_elf.stage_extract(other, os.path.join(self.tmp, "disc"), self.expected, log=self.log)
        self.assertEqual(caught.exception.code, disc_to_elf.EXIT_DISC_NOT_R0001)
        self.assertIn("SCUS_972.75", caught.exception.sentence)

    def test_a_differently_laid_out_image_of_the_same_disc_is_a_note_and_not_a_refusal(self):
        # R231: the layout is recorded, the bytes are pinned. A re-built image goes through with a note.
        self.expected["disc"] = {"files": 99, "manifest_sha256": "1" * 64, "volume_sectors": 12345}
        disc_to_elf.stage_extract(self.iso, os.path.join(self.tmp, "disc"), self.expected, log=self.log)
        notes = [line for line in self.lines if "NOTE" in line]
        self.assertTrue(notes, self.lines)
        self.assertIn("disc.files: recorded 99, yours is 2", notes[0])
        self.assertEqual(self.expected["disc"]["files"], 99, "a note does not rewrite the record")


class RecordAndRefuseTest(unittest.TestCase):
    """check_value: record what nobody measured, refuse what disagrees."""

    def test_a_value_nobody_has_measured_is_recorded_and_said_so(self):
        expected = {"elf": {"size": None}}
        lines = []
        self.assertTrue(disc_to_elf.check_value(expected, "elf", "size", 4835072, "the ELF's size",
                                                log=lines.append))
        self.assertEqual(expected["elf"]["size"], 4835072)
        self.assertIn("recorded elf.size = 4835072", lines[0])

    def test_a_section_the_file_has_never_seen_is_created(self):
        expected = {}
        disc_to_elf.check_value(expected, "dnas", "blocks", 130, "the block count", log=lambda *a: None)
        self.assertEqual(expected["dnas"]["blocks"], 130)

    def test_a_planted_wrong_hash_is_a_refusal_that_names_both_values(self):
        expected = {"overlays": {"ftscore.bin": {"size": 1, "sha256": "dead" * 16}}}
        with self.assertRaises(disc_to_elf.Refusal) as caught:
            disc_to_elf.check_value(expected, "overlays", "ftscore.bin", {"size": 2, "sha256": "beef" * 16},
                                    "the decrypted ftscore.bin", log=lambda *a: None)
        self.assertEqual(caught.exception.code, disc_to_elf.EXIT_MISMATCH)
        self.assertIn("dead" * 16, caught.exception.sentence)
        self.assertIn("beef" * 16, caught.exception.sentence)
        self.assertIn("do not edit the record", caught.exception.sentence)

    def test_a_refusal_keeps_the_code_its_caller_chose(self):
        expected = {"inputs": {"OVERLAY/REL/DNAS.BIN": {"size": 1}}}
        with self.assertRaises(disc_to_elf.Refusal) as caught:
            disc_to_elf.check_value(expected, "inputs", "OVERLAY/REL/DNAS.BIN", {"size": 2},
                                    "DNAS.BIN on your disc",
                                    code=disc_to_elf.EXIT_DISC_NOT_R0001, log=lambda *a: None)
        self.assertEqual(caught.exception.code, disc_to_elf.EXIT_DISC_NOT_R0001)

    def test_a_recorded_value_that_agrees_changes_nothing(self):
        expected = {"elf": {"entry": "0x180008"}}
        self.assertFalse(disc_to_elf.check_value(expected, "elf", "entry", "0x180008", "the entry point",
                                                 log=lambda *a: None))


# ---- the ELF stage, on synthetic overlays ------------------------------------------------------

def _loader_elf(vaddr, text):
    """A 32-bit little-endian ELF with one PT_LOAD, the shape make_overlay_elf.elf_segments reads."""
    phoff, phentsize = 52, 32
    hdr = bytearray(bytes.fromhex("7f454c46010101") + bytes(9))
    hdr += struct.pack("<HHIIIIIHHHHHH", 2, 8, 1, vaddr + 8, 52, phoff, 0, 52, phentsize, 1, 0, 0, 0)
    hdr += struct.pack("<8I", 1, phoff + phentsize, vaddr, vaddr, len(text), len(text), 5, 0x1000)
    return bytes(hdr) + text


def _mwo3(load, name, body, bss=0x100):
    head = bytearray(0x40)
    head[0:4] = b"MWo3"
    struct.pack_into("<7I", head, 4, 3, load, 0x80, 0x40, bss, 0, 0)
    head[0x20:0x20 + len(name)] = name.encode()
    return bytes(head) + body


class ElfStageTest(unittest.TestCase):
    """stage_elf: make_overlay_elf as build.sh recomp calls it, then the four checks on the result."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="disc_to_elf_elf_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.disc = os.path.join(self.tmp, "disc")
        self.overlays = os.path.join(self.tmp, "overlays")
        os.makedirs(self.disc)
        os.makedirs(self.overlays)
        with open(os.path.join(self.disc, disc_to_elf.SCUS), "wb") as fh:
            fh.write(_loader_elf(0x100000, b"loader text" * 64))
        with open(os.path.join(self.overlays, "ftscore.bin"), "wb") as fh:
            fh.write(_mwo3(0x200000, "ftscore", BUILD_ID.encode() + b"\0" + b"ftscore body" * 32))
        with open(os.path.join(self.overlays, "zsealetc.bin"), "wb") as fh:
            fh.write(_mwo3(0x300000, "zsealetc", b"zsealetc body" * 32))
        self.expected = {"elf": {"build_id": BUILD_ID, "entry": None, "segments": None,
                                 "size": None, "sha256": None}}
        self.lines = []

    def run_stage(self, **kw):
        return disc_to_elf.stage_elf(self.disc, self.overlays, self.expected, log=self.lines.append, **kw)

    def test_the_merged_elf_is_written_and_its_facts_recorded(self):
        out = self.run_stage()
        self.assertTrue(os.path.isfile(out))
        self.assertEqual(self.expected["elf"]["entry"], "0x100008")
        self.assertEqual(self.expected["elf"]["segments"], 3)
        self.assertEqual(self.expected["elf"]["size"], os.path.getsize(out))
        self.assertEqual(self.expected["elf"]["sha256"], disc_to_elf.sha256_file(out))

    def test_a_second_run_is_a_no_op_that_still_verifies(self):
        out = self.run_stage()
        os.utime(out, (1000000, 1000000))
        self.lines.clear()
        self.run_stage()
        self.assertEqual(int(os.path.getmtime(out)), 1000000, "it rebuilt a file that was already right")
        self.assertTrue(any("skipped" in line for line in self.lines), self.lines)

    def test_a_planted_wrong_sha256_is_refused_as_a_damaged_elf(self):
        self.expected["elf"]["sha256"] = "f00d" * 16
        with self.assertRaises(disc_to_elf.Refusal) as caught:
            self.run_stage()
        self.assertEqual(caught.exception.code, disc_to_elf.EXIT_ELF_BAD)
        self.assertIn("f00d" * 16, caught.exception.sentence)

    def test_a_planted_wrong_entry_point_is_refused(self):
        self.expected["elf"]["entry"] = "0x1c4cc0"
        with self.assertRaises(disc_to_elf.Refusal) as caught:
            self.run_stage()
        self.assertEqual(caught.exception.code, disc_to_elf.EXIT_ELF_BAD)
        self.assertIn("entry point", caught.exception.sentence)

    def test_an_elf_without_the_build_id_is_refused(self):
        self.expected["elf"]["build_id"] = "SOCOM 2 r0005 00:00:00 Jan 01 2004"
        with self.assertRaises(disc_to_elf.Refusal) as caught:
            self.run_stage()
        self.assertEqual(caught.exception.code, disc_to_elf.EXIT_ELF_BAD)
        self.assertIn("build id", caught.exception.sentence)

    def test_force_rebuilds_what_was_already_right(self):
        out = self.run_stage()
        os.utime(out, (1000000, 1000000))
        self.run_stage(force=True)
        self.assertNotEqual(int(os.path.getmtime(out)), 1000000)


# ---- the two emulation stages, through fake emulators ------------------------------------------

class FakeEmulatorTest(unittest.TestCase):
    """The stages that need Unicorn, driven by fakes: what this proves is the orchestration -- the
    order, the refusals, the verification and the skipping -- not the ciphers."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="disc_to_elf_fake_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.disc = os.path.join(self.tmp, "disc")
        self.overlays = os.path.join(self.tmp, "overlays")
        os.makedirs(os.path.join(self.disc, "OVERLAY", "REL"))
        os.makedirs(os.path.join(self.disc, "RUN", "RAW"))
        self.dnas_bin = b"DNAS.BIN bytes" * 64
        self.zdb = b"APACHE00.ZDB bytes" * 64
        with open(os.path.join(self.disc, disc_to_elf.DNAS_BIN), "wb") as fh:
            fh.write(self.dnas_bin)
        with open(os.path.join(self.disc, disc_to_elf.APACHE), "wb") as fh:
            fh.write(self.zdb)
        self.plain_dnas = b"DNAS plaintext" * 64
        self.ftscore = BUILD_ID.encode() + b"\0" + b"ftscore" * 64
        self.zsealetc = b"zsealetc" * 64
        self.calls = []
        self.expected = {
            "inputs": {
                "OVERLAY/REL/DNAS.BIN": {"size": len(self.dnas_bin),
                                         "sha256": disc_to_elf.sha256_bytes(self.dnas_bin)},
                "RUN/RAW/APACHE00.ZDB": {"size": len(self.zdb),
                                         "sha256": disc_to_elf.sha256_bytes(self.zdb)},
            },
            "dnas": {"variants": {"0x4ee9e8": {"keytab": "0x4efac8", "core": "0x4ef348"}},
                     "blocks": None, "output": None},
            "zdb": {"entries": {"ftscore": 7, "zsealetc": 9}},
            "overlays": {"ftscore.bin": None, "zsealetc.bin": None},
            "elf": {"build_id": BUILD_ID},
        }
        self.lines = []
        self._install_fakes()

    def _install_fakes(self):
        dnas = types.ModuleType("tools_py.dnas_selfdecrypt")

        def decrypt(data, variants):
            self.calls.append(("dnas", len(data), sorted(variants)))
            print("fake dnas chatter")
            return self.plain_dnas, [{"start": 0x4c5380, "size": 16}] * 3
        dnas.decrypt = decrypt

        apache = types.ModuleType("tools_py.decrypt_apache")

        def zdb_entries(path):
            return {"ftscore": b"f" * 7, "zsealetc": b"z" * 9}

        def main(game=None, out=None):
            self.calls.append(("overlays", game, out))
            print("fake apache chatter")
            os.makedirs(out, exist_ok=True)
            for name, body in (("ftscore.bin", self.ftscore), ("zsealetc.bin", self.zsealetc)):
                with open(os.path.join(out, name), "wb") as fh:
                    fh.write(body)
        apache.zdb_entries = zdb_entries
        apache.main = main
        patch = mock.patch.dict(sys.modules, {"unicorn": types.ModuleType("unicorn"),
                                              "tools_py.dnas_selfdecrypt": dnas,
                                              "tools_py.decrypt_apache": apache})
        patch.start()
        self.addCleanup(patch.stop)

    # -- the missing dependency -------------------------------------------------------------------

    def test_a_missing_unicorn_is_refused_with_the_command_that_fixes_it(self):
        with mock.patch.dict(sys.modules, {"unicorn": None}):
            with self.assertRaises(disc_to_elf.Refusal) as caught:
                disc_to_elf._import_emulator("decrypt_apache")
        self.assertEqual(caught.exception.code, disc_to_elf.EXIT_ENVIRONMENT)
        self.assertIn("pip install unicorn", caught.exception.sentence)

    # -- stage 2 ----------------------------------------------------------------------------------

    def test_the_dnas_stage_writes_the_plaintext_and_records_it(self):
        disc_to_elf.stage_dnas(self.disc, self.tmp, self.expected, log=self.lines.append)
        dest = os.path.join(self.disc, disc_to_elf.DNAS_DEC)
        with open(dest, "rb") as fh:
            self.assertEqual(fh.read(), self.plain_dnas)
        self.assertEqual(self.expected["dnas"]["blocks"], 3)
        self.assertEqual(self.expected["dnas"]["output"],
                         {"size": len(self.plain_dnas), "sha256": disc_to_elf.sha256_bytes(self.plain_dnas)})
        self.assertEqual(self.calls, [("dnas", len(self.dnas_bin), [0x4ee9e8])],
                         "the recorded hex addresses reach the cipher as integers")
        with open(os.path.join(self.disc, disc_to_elf.DNAS_JSON), "r", encoding="utf-8") as fh:
            self.assertEqual(len(json.load(fh)), 3)
        self.assertTrue(os.path.isfile(os.path.join(self.tmp, "disc_to_elf-dnas.log")),
                        "the emulator's chatter went to a log, not to the terminal")

    def test_the_dnas_stage_is_skipped_on_a_second_run(self):
        disc_to_elf.stage_dnas(self.disc, self.tmp, self.expected, log=self.lines.append)
        self.calls.clear()
        self.lines.clear()
        disc_to_elf.stage_dnas(self.disc, self.tmp, self.expected, log=self.lines.append)
        self.assertEqual(self.calls, [], "it decrypted again a file that was already right")
        self.assertTrue(any("skipped" in line for line in self.lines), self.lines)

    def test_a_dnas_bin_that_is_not_the_recorded_one_is_refused_as_not_r0001(self):
        with open(os.path.join(self.disc, disc_to_elf.DNAS_BIN), "wb") as fh:
            fh.write(b"another revision's DNAS")
        with self.assertRaises(disc_to_elf.Refusal) as caught:
            disc_to_elf.stage_dnas(self.disc, self.tmp, self.expected, log=self.lines.append)
        self.assertEqual(caught.exception.code, disc_to_elf.EXIT_DISC_NOT_R0001)
        self.assertEqual(self.calls, [], "it ran the cipher on bytes it had already refused")

    def test_a_block_count_that_disagrees_is_refused(self):
        self.expected["dnas"]["blocks"] = 130
        with self.assertRaises(disc_to_elf.Refusal) as caught:
            disc_to_elf.stage_dnas(self.disc, self.tmp, self.expected, log=self.lines.append)
        self.assertEqual(caught.exception.code, disc_to_elf.EXIT_MISMATCH)
        self.assertIn("130", caught.exception.sentence)

    # -- stage 3 ----------------------------------------------------------------------------------

    def test_the_overlay_stage_writes_both_overlays_and_records_them(self):
        disc_to_elf.stage_overlays(self.disc, self.overlays, self.expected, log=self.lines.append)
        self.assertEqual(self.calls, [("overlays", self.disc, self.overlays)])
        self.assertEqual(self.expected["overlays"]["ftscore.bin"],
                         {"size": len(self.ftscore), "sha256": disc_to_elf.sha256_bytes(self.ftscore)})
        self.assertEqual(self.expected["overlays"]["zsealetc.bin"],
                         {"size": len(self.zsealetc), "sha256": disc_to_elf.sha256_bytes(self.zsealetc)})

    def test_the_overlay_stage_is_skipped_on_a_second_run(self):
        disc_to_elf.stage_overlays(self.disc, self.overlays, self.expected, log=self.lines.append)
        self.calls.clear()
        self.lines.clear()
        disc_to_elf.stage_overlays(self.disc, self.overlays, self.expected, log=self.lines.append)
        self.assertEqual(self.calls, [])
        self.assertTrue(any("skipped" in line for line in self.lines), self.lines)

    def test_a_zdb_whose_entries_do_not_match_is_refused_before_seven_minutes_of_emulation(self):
        self.expected["zdb"]["entries"] = {"ftscore": 855920, "zsealetc": 691792}
        with self.assertRaises(disc_to_elf.Refusal) as caught:
            disc_to_elf.stage_overlays(self.disc, self.overlays, self.expected, log=self.lines.append)
        self.assertEqual(caught.exception.code, disc_to_elf.EXIT_DISC_NOT_R0001)
        self.assertIn("855920", caught.exception.sentence)
        self.assertEqual(self.calls, [])

    def test_an_overlay_that_decrypts_to_the_wrong_game_is_refused_by_its_build_id(self):
        self.ftscore = b"some other game entirely" * 64
        with self.assertRaises(disc_to_elf.Refusal) as caught:
            disc_to_elf.stage_overlays(self.disc, self.overlays, self.expected, log=self.lines.append)
        self.assertEqual(caught.exception.code, disc_to_elf.EXIT_MISMATCH)
        self.assertIn("build id", caught.exception.sentence)

    def test_an_overlay_the_decryption_never_wrote_is_refused_with_the_log_to_read(self):
        apache = sys.modules["tools_py.decrypt_apache"]
        apache.main = lambda game=None, out=None: os.makedirs(out, exist_ok=True)
        with self.assertRaises(disc_to_elf.Refusal) as caught:
            disc_to_elf.stage_overlays(self.disc, self.overlays, self.expected, log=self.lines.append)
        self.assertEqual(caught.exception.code, disc_to_elf.EXIT_MISMATCH)
        self.assertIn("disc_to_elf-overlays.log", caught.exception.sentence)


# ---- the command itself ------------------------------------------------------------------------

class CommandTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="disc_to_elf_cmd_")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.expected_path = os.path.join(self.tmp, "expected.json")
        shutil.copyfile(disc_to_elf.EXPECTED_PATH, self.expected_path)

    def call(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with mock.patch("sys.stdout", out), mock.patch("sys.stderr", err):
            code = disc_to_elf.main(argv + ["--expected", self.expected_path])
        return code, out.getvalue(), err.getvalue()

    def test_a_missing_iso_leaves_with_the_disc_not_found_code_and_a_sentence(self):
        code, _, err = self.call([os.path.join(self.tmp, "no.iso"), "--out", os.path.join(self.tmp, "game")])
        self.assertEqual(code, disc_to_elf.EXIT_DISC_NOT_FOUND)
        self.assertIn("no file at", err)

    def test_no_iso_and_no_check_is_a_usage_error(self):
        with self.assertRaises(SystemExit) as caught:
            self.call([])
        self.assertEqual(caught.exception.code, 2)

    def test_check_lists_every_stage_as_todo_on_an_empty_folder(self):
        code, out, _ = self.call(["--check", "--out", os.path.join(self.tmp, "game")])
        self.assertEqual(code, 1)
        for stage in disc_to_elf.STAGES:
            self.assertIn(stage, out)
        self.assertIn("todo", out)
        self.assertNotIn("ok  ", out)

    def test_an_unknown_stage_is_refused_by_name(self):
        code, _, err = self.call([os.path.join(self.tmp, "no.iso"), "--stages", "extract,decompile"])
        self.assertEqual(code, disc_to_elf.EXIT_ENVIRONMENT)
        self.assertIn("decompile", err)

    def test_a_run_that_records_nothing_leaves_the_expectations_file_alone(self):
        before = open(self.expected_path, "rb").read()
        self.call([os.path.join(self.tmp, "no.iso")])
        self.assertEqual(open(self.expected_path, "rb").read(), before)


class TheRecordedExpectationsTest(unittest.TestCase):
    """The tracked file itself: its shape, and that it cannot drift from the launcher's digest."""

    def setUp(self):
        self.expected = disc_to_elf.load_expected()

    def test_the_boot_elf_digest_is_the_one_the_launcher_pins(self):
        header = os.path.join(disc_to_elf.ROOT, "third_party", "ps2recomp", "ps2xShared", "include",
                              "launcher", "launcher_config.h")
        with open(header, "r", encoding="utf-8") as fh:
            text = fh.read()
        marker = "kSocom2R0001ElfSha256 = \""
        digest = text[text.index(marker) + len(marker):].split('"')[0]
        self.assertEqual(self.expected["inputs"]["SCUS_972.75"]["sha256"], digest,
                         "the disc-to-ELF chain and the launcher's disc check must pin the same r0001 bytes")

    def test_the_four_dnas_variants_are_hex_addresses_in_the_overlay(self):
        variants = self.expected["dnas"]["variants"]
        self.assertEqual(len(variants), 4)
        for decryptor, pair in variants.items():
            for value in (decryptor, pair["keytab"], pair["core"]):
                self.assertTrue(value.startswith("0x"), value)
                self.assertGreaterEqual(int(value, 16), 0x4c5380, "an address below the DNAS load address")

    def test_every_digest_recorded_is_a_sha256(self):
        for section in ("inputs", "overlays"):
            for key, value in self.expected[section].items():
                self.assertEqual(len(value["sha256"]), 64, key)
                self.assertGreater(value["size"], 0, key)
        self.assertEqual(len(self.expected["elf"]["sha256"]), 64)

    def test_the_file_round_trips_through_the_writer(self):
        path = os.path.join(tempfile.mkdtemp(prefix="disc_to_elf_rt_"), "expected.json")
        self.addCleanup(shutil.rmtree, os.path.dirname(path), ignore_errors=True)
        disc_to_elf.save_expected(self.expected, path)
        self.assertEqual(disc_to_elf.load_expected(path), self.expected)


if __name__ == "__main__":
    unittest.main()
