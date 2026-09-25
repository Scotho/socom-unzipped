"""The ONLINE harness's instruments, per revision (Sprint 11 Task 19).

`scripts/parity/env.sh` is sourced by every online script -- the ladder, both mixed-match legs, the
control round -- and it carried `PS2X_PEEK` and `PS2X_CALL_TRACE` as r0001 literals. `s11_r0004_round1`
is what that cost: two r0004 clients logged in against the hosted Horizon, one hosted Frostfire, the
other found it in the list and joined, both went READY and the round played to its clock (1511 and 1491
in-game `[peek]` rows; both HUD clocks read 05:29 in the hold captures) -- and it scored `RESULT NO-DATA`,
because every chain in the spec pointed at somebody else's memory and the call trace never fired.

The defect to hold shut is therefore not "the r0004 round failed". It is a round that reads r0001's
addresses and says nothing. So:

  * the r0001 strings are pinned CHARACTER FOR CHARACTER against what env.sh carried before this existed
    -- an online run's `[peek]` rows are read back by these very chains, and a changed r0001 spec would
    silently re-cut every archived comparison;
  * an r0004 launch gets the r0004 column, and neither render may carry one address of the other's;
  * a revision nothing can establish refuses, rather than handing out r0001's addresses;
  * the one value that rests on a single evidence-twinned referrer is declared unconfirmed and no scorer
    may key a verdict on it.

bash and python only -- no launch, no emulator, no disc assets.
"""
import glob
import os
import re
import subprocess
import tempfile
import unittest

from tools_py.parity import guest_addresses as ga
from tools_py.tests.shell import BASH

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARITY = os.path.join(ROOT, "tools_py", "parity")

# THE PIN. This is the literal `scripts/parity/env.sh` exported, copied here before it was replaced by a
# render. It is 573 characters; test_parity_env.PEEK_LEN has held that length since the block was made
# shared, and this holds the content.
R0001_PEEK = (
    "0x416054:3,*0x408c58:64,*0x408c58+0xc0*:32,*0x408c58+0x400:12,*0x408c58+0x174:1,"
    "*0x408c58+0xF78:24,*0x408c58+0x1044:8,*0x437ce8:64,*0x437ce8+0x100:21,*0x437ce8+0x0c*:2,"
    "*0x437ce8+0x10*:2,*0x437ce8+0x14*:2,*0x437ce8+0x20*:2,*0x437ce8+0x24*:2,*0x437ce8+0x2c*:2,"
    "*0x437ce8+0x58*:2,*0x437ce8+0x5c*:2,*0x437ce8+0x70*:2,*0x43668c:2,0x4365c0:1,0x45a0c0:1,"
    "0x3df1b0:1,0x45a1c8:1,*0x437ce8+0x0c**:3,*0x437ce8+0x10**:3,*0x437ce8+0x14**:3,"
    "*0x437ce8+0x20**:3,*0x437ce8+0x24**:3,*0x437ce8+0x2c**:3,*0x437ce8+0x58**:3,"
    "*0x437ce8+0x5c**:3,*0x437ce8+0x70**:3,*0x43668c*:3,0x408f10:2,0x408c58:4"
)
R0001_CALL_TRACE = "0x553dc0:MoveScale,0x30cd80:NetIdle"

# The same pin for the three mixed-match legs' narrower block, copied from the literal each of them
# exported over env.sh's before the render reached them (review F2). Byte for byte, the three were
# identical to each other.
R0001_PEEK_MIXED = (
    "0x416054:3,*0x408c58:64,*0x408c58+0xc0*:32,*0x408c58+0x400:12,*0x408c58+0x174:1,"
    "*0x408c58+0xF78:24,*0x408c58+0x1044:8,*0x437ce8:64,*0x437ce8+0x100:21,0x4365c0:1,"
    "0x408f10:2,0x408c58:4"
)
MIXED_LEGS = ("mixed_match.sh", "mixed_match2.sh", "mixed_match2_leg2.sh")

BANNERS = {"r0001": b"SOCOM 2 r0001 17:22:21 Oct 11 2003\x00",
           "r0004": b"SOCOM 2 r0004 10:14:38 Nov  3 2004\x00"}


def write_image(directory, revision):
    """A file that names its revision the way a game image does -- which is all `revision_of_image`
    reads. No ELF is needed: `game/` is git-ignored and CI has no images."""
    path = os.path.join(directory, "socom2_game_%s.elf" % revision)
    with open(path, "wb") as f:
        f.write(b"\x7fELF" + b"\0" * 64 + BANNERS[revision] + b"\0" * 16)
    return path


def source_env_sh(script, env=None):
    """Run `script` in bash after sourcing scripts/parity/env.sh. Returns the CompletedProcess -- the
    refusal path is one of the things under test, so a non-zero exit is not an assertion failure here."""
    e = dict(os.environ)
    for k in ("SOCOM_SERVER_IP", "PS2X_SOCOM2_SERVER", "PS2X_PEEK", "PS2X_CALL_TRACE", "SOCOM_GAME_ELF"):
        e.pop(k, None)
    e.update(env or {})
    return subprocess.run([BASH, "-c", ". scripts/parity/env.sh; " + script], cwd=ROOT, env=e,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)


class Specs(unittest.TestCase):
    def test_the_r0001_peek_spec_is_what_env_sh_has_always_carried(self):
        """Character for character. The chains ARE how an archived run's rows are read back."""
        self.assertEqual(ga.peek_spec("r0001"), R0001_PEEK)
        self.assertEqual(len(ga.peek_spec("r0001")), 573)

    def test_the_r0001_call_trace_is_what_env_sh_has_always_carried(self):
        self.assertEqual(ga.call_trace_spec("r0001"), R0001_CALL_TRACE)

    def test_the_r0004_specs_are_the_same_shape_in_other_addresses(self):
        """Same items, same order, same offsets -- only the bases move. Anything else would mean the
        template drifted from the string it replaced."""
        r1, r4 = ga.peek_spec("r0001").split(","), ga.peek_spec("r0004").split(",")
        self.assertEqual(len(r1), len(r4))
        strip = lambda items: [re.sub(r"0x[0-9a-f]{5,8}", "<base>", i, count=1) for i in items]
        self.assertEqual(strip(r1), strip(r4))

    def test_neither_render_carries_one_address_of_the_other_column(self):
        """The silent defect, stated directly: an r0004 launch handed an r0001 chain reads real words of
        the wrong memory and reports a number."""
        for mine, theirs in (("r0001", "r0004"), ("r0004", "r0001")):
            rendered = ga.peek_spec(mine) + "," + ga.call_trace_spec(mine)
            for name in ga.all_names():
                if name == "actor_vtable":
                    continue                    # a VALUE in an object's word 0, never a chain
                other = "0x%x" % ga.address(name, theirs)
                self.assertNotIn(other, rendered, "%s (%s) leaked into the %s spec" % (name, theirs, mine))

    def test_every_name_the_templates_reach_for_has_both_columns(self):
        for name in ga._TEMPLATE_NAMES:
            for revision in ("r0001", "r0004"):
                self.assertIsInstance(ga.address(name, revision), int, "%s/%s" % (name, revision))

    def test_the_online_and_trace_columns_never_share_an_address(self):
        for table in (ga.ONLINE_ADDRESSES, ga.TRACE_ADDRESSES):
            for name, col in table.items():
                self.assertNotEqual(col["r0001"], col["r0004"], name)

    def test_no_two_names_anywhere_answer_with_the_same_address(self):
        """One number under two names in one column is how a rename hides a copy-paste."""
        for revision in ("r0001", "r0004"):
            seen = {}
            for name in ga.all_names():
                a = ga.address(name, revision)
                self.assertNotIn(a, seen, "%s and %s are both 0x%x on %s" % (name, seen.get(a), a, revision))
                seen[a] = name

    def test_an_unknown_revision_refuses_instead_of_answering_r0001(self):
        for fn in (ga.peek_spec, ga.call_trace_spec):
            with self.assertRaises(ValueError) as e:
                fn("r0007")
            self.assertIn("r0007", str(e.exception))


class MixedProfile(unittest.TestCase):
    """Review F2: the three mixed-match legs sourced env.sh and then exported an r0001 PS2X_PEEK literal
    OVER the render -- a hard assignment, so env.sh's column never reached them. An r0004 leg through any
    of the three would have been `s11_r0004_round1` again: the round plays, the rows are cut at somebody
    else's memory, the score is silence. The narrower block is rendered from the same names now.
    """

    def test_the_r0001_mixed_block_is_what_the_legs_carried(self):
        self.assertEqual(ga.peek_spec("r0001", "mixed"), R0001_PEEK_MIXED)

    def test_the_mixed_block_is_a_subset_of_the_online_one_on_both_columns(self):
        """It drops the valve pairs, the name-bytes items and the mission-abort valve; it adds nothing.
        A leg watches positions, health and the clocks, not the round valves."""
        for revision in ("r0001", "r0004"):
            full = set(ga.peek_spec(revision).split(","))
            self.assertTrue(set(ga.peek_spec(revision, "mixed").split(",")) <= full, revision)

    def test_the_mixed_render_carries_no_address_of_the_other_column(self):
        for mine, theirs in (("r0001", "r0004"), ("r0004", "r0001")):
            rendered = ga.peek_spec(mine, "mixed")
            for name in ga.all_names():
                if name == "actor_vtable":
                    continue
                self.assertNotIn("0x%x" % ga.address(name, theirs), rendered, "%s/%s" % (name, theirs))

    def test_the_mixed_profile_assigns_outright_and_emits_no_call_trace(self):
        """That is what the legs' `export PS2X_PEEK=...` did, and they still need to win over env.sh."""
        lines = ga.instrument_env_lines("r0001", "an image", "mixed")
        self.assertTrue(any(l.startswith('PS2X_PEEK="0x') for l in lines), lines)
        self.assertFalse(any("${PS2X_PEEK:-" in l for l in lines), lines)
        self.assertFalse(any("PS2X_CALL_TRACE" in l for l in lines), lines)

    def test_an_unknown_profile_refuses(self):
        with self.assertRaises(ValueError) as e:
            ga.peek_spec("r0001", "nosuch")
        self.assertIn("nosuch", str(e.exception))
        self.assertIn("mixed", str(e.exception))

    def test_no_leg_sets_ps2x_peek_from_a_literal_any_more(self):
        """The same guard env.sh has, extended to the three scripts that override it -- the seam the
        commit message claimed and did not cover. Scoped to what OUR exe is cut at: `cam_poll --spec
        0x416054:3` on the same legs is the CONSOLE's address through PINE, and PCSX2 in a mixed match
        boots the r0001 disc by definition, so that one is a literal on purpose and says so."""
        for leg in MIXED_LEGS:
            with open(os.path.join(ROOT, "scripts", "parity", leg), encoding="utf-8") as f:
                body = "".join(l for l in f if not l.lstrip().startswith("#"))
            self.assertIn("guest_addresses --env --profile mixed", body, leg)
            for line in body.splitlines():
                if not re.match(r"\s*(export\s+)?PS2X_PEEK=", line):
                    continue
                for name in ga.all_names():
                    for revision in ("r0001", "r0004"):
                        self.assertNotIn("0x%x" % ga.address(name, revision), line,
                                         "%s assigns PS2X_PEEK from a literal again: %s" % (leg, line))

    def test_every_sourcer_either_takes_env_shs_block_or_renders_its_own(self):
        """The boundary, enforced rather than described: a script under scripts/parity/ that sources
        env.sh may not then assign PS2X_PEEK from anything but the renderer."""
        offenders = []
        for path in sorted(glob.glob(os.path.join(ROOT, "scripts", "parity", "*.sh"))):
            with open(path, encoding="utf-8") as f:
                body = "".join(l for l in f if not l.lstrip().startswith("#"))
            if "env.sh" not in body or os.path.basename(path) == "env.sh":
                continue
            for line in body.splitlines():
                if re.match(r"\s*(export\s+)?PS2X_PEEK=", line) and "guest_addresses" not in body:
                    offenders.append("%s: %s" % (os.path.basename(path), line.strip()[:60]))
        self.assertEqual(offenders, [], "these set PS2X_PEEK without going through guest_addresses")


class Unconfirmed(unittest.TestCase):
    def test_the_single_twin_value_is_declared(self):
        """0x45a1c8 -> 0x45d58c has 3 materialising sites and ONE evidence-twinned referrer. It is
        carried so the instrument keeps peeking what it always peeked; it is declared so nothing scores
        on it."""
        self.assertIn("r7_flag", ga.UNCONFIRMED)
        self.assertEqual(ga.address("r7_flag", "r0001"), 0x0045A1C8)
        self.assertEqual(ga.address("r7_flag", "r0004"), 0x0045D58C)

    def test_every_unconfirmed_name_is_a_real_name(self):
        for name in ga.UNCONFIRMED:
            self.assertIn(name, ga.all_names())

    def test_no_scorer_mentions_an_unconfirmed_address_at_all(self):
        """The rule is "informational, never a pass/fail". The enforceable proxy is that no module under
        tools_py/parity/ but this table's own home carries the literal: a verdict cannot be keyed on a
        number the scorer never names. If a scorer ever needs it, that is the moment to go and find it a
        second twinned referrer -- not the moment to delete this test."""
        wanted = set()
        for name in ga.UNCONFIRMED:
            for revision in ("r0001", "r0004"):
                a = ga.address(name, revision)
                wanted |= {"0x%x" % a, "0x%X" % a, "0x%08x" % a}
        # ... and the NAMES too (review F12): a scorer that reached the value as
        # `ga.address("r7_flag", rev)` would pass a literals-only grep. Nothing does; this keeps it so.
        wanted |= {'"%s"' % n for n in ga.UNCONFIRMED} | {"'%s'" % n for n in ga.UNCONFIRMED}
        offenders = []
        for path in sorted(glob.glob(os.path.join(PARITY, "*.py"))):
            if os.path.basename(path) == "guest_addresses.py":
                continue
            with open(path, encoding="utf-8") as f:
                text = f.read()
            for lit in wanted:
                if lit in text:
                    offenders.append("%s carries %s" % (os.path.relpath(path, ROOT), lit))
        self.assertEqual(offenders, [], "an unconfirmed address reached a scorer")


class EnvSh(unittest.TestCase):
    def test_the_default_source_is_unchanged(self):
        """No $SOCOM_GAME_ELF: gate.collect_pins' relaxation -- a bare clone has no image and no launch
        to make either -- so the column is r0001 and the strings are the ones env.sh always exported."""
        p = source_env_sh('echo "$PS2X_PEEK"; echo "$PS2X_CALL_TRACE"')
        self.assertEqual(p.returncode, 0, p.stderr)
        peek, trace = p.stdout.splitlines()[:2]
        self.assertEqual(peek, R0001_PEEK)
        self.assertEqual(trace, R0001_CALL_TRACE)

    def test_an_r0004_image_gets_the_r0004_column(self):
        with tempfile.TemporaryDirectory() as d:
            p = source_env_sh('echo "$PS2X_PEEK"; echo "$PS2X_CALL_TRACE"',
                              env={"SOCOM_GAME_ELF": write_image(d, "r0004")})
            self.assertEqual(p.returncode, 0, p.stderr)
            peek, trace = p.stdout.splitlines()[:2]
            self.assertEqual(peek, ga.peek_spec("r0004"))
            self.assertEqual(trace, ga.call_trace_spec("r0004"))
            self.assertNotIn("0x408c58", peek)          # not one r0001 base survived

    def test_an_r0001_image_gets_the_pinned_r0001_strings(self):
        with tempfile.TemporaryDirectory() as d:
            p = source_env_sh('echo "$PS2X_PEEK"', env={"SOCOM_GAME_ELF": write_image(d, "r0001")})
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(p.stdout.splitlines()[0], R0001_PEEK)

    def test_an_image_that_is_not_there_refuses_the_whole_source(self):
        """It must not fall back, and it must not leave the caller running with no instruments -- env.sh
        exits rather than returning, so the script that sourced it stops here."""
        p = source_env_sh('echo "REACHED:$PS2X_PEEK"',
                          env={"SOCOM_GAME_ELF": os.path.join(ROOT, "no", "such", "image.elf")})
        self.assertNotEqual(p.returncode, 0)
        self.assertNotIn("REACHED", p.stdout)
        self.assertIn("SOCOM_GAME_ELF", p.stderr)

    def test_an_image_naming_a_revision_the_table_has_no_column_for_refuses(self):
        """Review F1. r0002 and r0003 are real SOCOM II revisions. The render used to sit OUTSIDE the
        try, so `address()`'s ValueError reached the operator as a traceback -- from the very command
        env.sh's refusal message tells them to run. One sentence, exit 2, no traceback."""
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "r0002.elf")
            with open(path, "wb") as f:
                f.write(b"\x7fELF" + b"\0" * 64 + b"SOCOM 2 r0002 01:02:03 Jan  1 2004\0" + b"\0" * 16)
            p = source_env_sh('echo "REACHED:$PS2X_PEEK"', env={"SOCOM_GAME_ELF": path})
            self.assertNotEqual(p.returncode, 0)
            self.assertNotIn("REACHED", p.stdout)
            self.assertNotIn("Traceback", p.stderr)
            self.assertIn("r0002", p.stderr)
            self.assertIn("r0001, r0004", p.stderr)          # the message names the columns there ARE

    def test_an_image_with_no_banner_refuses(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "nameless.elf")
            with open(path, "wb") as f:
                f.write(b"\x7fELF" + b"\0" * 256)
            p = source_env_sh('echo "REACHED:$PS2X_PEEK"', env={"SOCOM_GAME_ELF": path})
            self.assertNotEqual(p.returncode, 0)
            self.assertNotIn("REACHED", p.stdout)

    def test_the_operators_own_spec_still_wins(self):
        """`VAR="${VAR:-...}"`, as the literals were: an operator's wider spec is left alone."""
        p = source_env_sh('echo "$PS2X_PEEK"; echo "$PS2X_CALL_TRACE"',
                          env={"PS2X_PEEK": "0xdeadbe:1", "PS2X_CALL_TRACE": "0xfeedf0:Mine"})
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.splitlines()[:2], ["0xdeadbe:1", "0xfeedf0:Mine"])

    def test_sourcing_twice_is_still_harmless(self):
        p = source_env_sh('. scripts/parity/env.sh; echo "$PS2X_PEEK"')
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout.splitlines()[0], R0001_PEEK)

    def test_env_sh_carries_no_guest_address_literal_of_its_own_any_more(self):
        """The whole point: one home. A literal creeping back here is the drift this replaced."""
        with open(os.path.join(ROOT, "scripts", "parity", "env.sh"), encoding="utf-8") as f:
            body = "".join(l for l in f if not l.lstrip().startswith("#"))
        for name in ga.all_names():
            for revision in ("r0001", "r0004"):
                self.assertNotIn("0x%x" % ga.address(name, revision), body,
                                 "%s/%s is a literal in env.sh again" % (name, revision))


class RevisionAgnosticReaders(unittest.TestCase):
    """The OTHER half of the round: with the right chains in PS2X_PEEK, the rows come back at r0004's
    addresses -- and the readers were still asking for r0001's. `verdict_core`'s row readers and the match
    driver's actor identification now take the SET of every revision's value. That is safe precisely
    because the columns are disjoint (Specs, above): a row carries one revision's numbers, so membership
    cannot read an r0001 row as r0004 or the other way round.
    """

    @staticmethod
    def row(revision):
        """One synthesised `[peek]` row's items, in `revision`'s addresses: the actor block (at a heap
        address, as the real one is -- it is found by its vtable, never by where it sits), the round
        clock, the clock string, the R6 flag word and the camera record."""
        import struct
        a = lambda n: ga.address(n, revision)
        clock = list(struct.unpack("<2I", b"05:29\x00\x00\x00"))
        return [(0x01A2B000, [ga.address("actor_vtable", revision)] + [0] * 47),
                (a("guest_clock"), [0x41200000]),          # 10.0f
                (a("clock_string"), clock),
                (a("mp_flag_word"), [0x00000100]),
                (a("camera_record"), [0, 0, 0])]

    def test_the_round_clock_is_read_on_both_revisions(self):
        from tools_py.parity import verdict_core as vc
        for revision in ("r0001", "r0004"):
            self.assertEqual(vc.row_static_any(self.row(revision), vc.ROUND_TIME_ADDRS), 0x41200000,
                             revision)

    def test_the_clock_string_is_read_on_both_revisions(self):
        from tools_py.parity import verdict_core as vc
        for revision in ("r0001", "r0004"):
            self.assertEqual(vc.row_clock_string(self.row(revision)), "05:29", revision)

    def test_the_actor_block_is_identified_on_both_revisions(self):
        from tools_py.parity import verdict_core as vc
        from tools_py.parity import online_match_ours as M
        for revision in ("r0001", "r0004"):
            items = self.row(revision)
            self.assertIsNotNone(next((a for a, w in items if w and w[0] in vc.ACTOR_VTABLES), None),
                                 revision)
            self.assertEqual(M.ACTOR_VTABLES, vc.ACTOR_VTABLES)

    def test_an_explicit_address_still_selects_exactly_that_item(self):
        """The `addr=` argument is unchanged: a caller that names one address gets that one only."""
        from tools_py.parity import verdict_core as vc
        r4 = self.row("r0004")
        self.assertEqual(vc.row_clock_string(r4, ga.address("clock_string", "r0004")), "05:29")
        self.assertIsInstance(vc.row_clock_string(r4, ga.address("clock_string", "r0001")), vc.NoData)

    def test_a_row_of_one_revision_is_never_read_as_the_other(self):
        """The safety argument, made into a test: asking an r0001 row for r0004's statics finds nothing,
        and the reverse. Membership is only safe while that holds."""
        from tools_py.parity import verdict_core as vc
        for mine, theirs in (("r0001", "r0004"), ("r0004", "r0001")):
            items = self.row(mine)
            self.assertIsNone(vc.row_static_any(items, {ga.address("guest_clock", theirs)}), mine)
            self.assertIsNone(next((a for a, w in items if w and w[0] == ga.address("actor_vtable", theirs)),
                                   None), mine)

    def test_the_valve_chains_spell_their_bases_the_way_chain_for_expects(self):
        """Review F10. `verdict_core.chain_for` re-renders a chain by `str.replace` of three base
        literals, so it is coupled to how `VALVES` spells them: lowercase, exactly `"%#x"`. A spelling
        change on either side would make the replace a silent no-op and the r0004 pre-launch checks
        would then refuse a correct spec. This holds the coupling directly, where the docstring names
        it -- the way out is to make the valve chains templates over the names."""
        from tools_py.parity import verdict_core as vc
        bases = {"player_actor", "net_game", "mission_abort_valve"}
        for name, v in vc.VALVES.items():
            for chain in (v.value_item, v.name_item):
                hit = [b for b in bases if "%#x" % ga.address(b, "r0001") in chain]
                self.assertEqual(len(hit), 1, "%s: %r names no base in %s" % (name, chain, sorted(bases)))
                moved = vc.chain_for(chain, "r0004")
                self.assertNotEqual(moved, chain, "%s: chain_for was a no-op on %r" % (name, chain))
                self.assertIn("%#x" % ga.address(hit[0], "r0004"), moved)

    def test_the_match_drivers_position_item_takes_every_column(self):
        from tools_py.parity import verdict_core as vc
        from tools_py.parity import online_match_ours as M
        self.assertEqual(M.POSITION_ADDRS, vc.CAMERA_RECORD_ADDRS)
        for revision in ("r0001", "r0004"):
            self.assertIn(ga.address("camera_record", revision), M.POSITION_ADDRS)


class ArchivedRows(unittest.TestCase):
    """Review F5. The four ADDRESS sets are safe by disjointness, which `Specs` holds in both
    directions. `ACTOR_VTABLES` is not an address set -- it is a VALUE read out of word 0, and
    `0x00668B20` is -0x680 from `0x006691A0`, i.e. inside r0001's own vtable region, so nothing in the
    table rules out some other r0001 object carrying it. What protects it is item order and the fact
    that it does not happen. This holds the fact, on the checked-in corpus, instead of asserting it.
    """

    ITEM = re.compile(r"@([0-9a-fA-F]+):((?:\s+[0-9a-fA-F]{8}\([^)]*\))+)")
    WORD = re.compile(r"([0-9a-fA-F]{8})\(")

    @classmethod
    def rows(cls):
        """[(item address, [words])] over every `[peek]` row in the checked-in r0001 fixtures."""
        out = []
        for path in sorted(glob.glob(os.path.join(ROOT, "tools_py", "tests", "fixtures", "online", "*.txt"))):
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    if "[peek]" not in line:
                        continue
                    for m in cls.ITEM.finditer(line):
                        out.append((int(m.group(1), 16), [int(w, 16) for w in cls.WORD.findall(m.group(2))]))
        return out

    def test_the_corpus_is_big_enough_to_mean_something(self):
        items = self.rows()
        self.assertGreater(len(items), 3000, "the online fixtures stopped carrying [peek] rows")
        r0001 = ga.address("actor_vtable", "r0001")
        self.assertGreater(sum(1 for _a, w in items if w and w[0] == r0001), 500,
                           "no actor block in the corpus -- this test would prove nothing")

    def test_no_archived_r0001_row_carries_the_r0004_vtable(self):
        r0004 = ga.address("actor_vtable", "r0004")
        for a, words in self.rows():
            self.assertNotEqual(words[0] if words else None, r0004,
                                "an r0001 row's item @%08x has the r0004 vtable as word 0 -- "
                                "ACTOR_VTABLES membership is no longer safe, pass the revision in" % a)

    def test_no_archived_r0001_row_carries_an_r0004_item_address(self):
        r0004 = {ga.address(n, "r0004") for n in ga.all_names() if n != "actor_vtable"}
        for a, _words in self.rows():
            self.assertNotIn(a, r0004, "an r0001 row carries an r0004 item address")


class PreLaunchChecks(unittest.TestCase):
    """The third half. The round is refused BEFORE it launches when the instruments cannot attest to
    anything -- and those checks compared a correct r0004 spec against r0001's chains, so they refused
    it. `s11_r0004_round2` died there: `MOVE-PATH WATCH REFUSES: PS2X_PEEK has no actor block
    (*0x408c58:10 or wider)`, against a spec whose actor block is at 0x435618. They read the column off
    the spec now (guest_addresses.revision_of_peek_spec -- the chains ARE the addresses).
    """

    @staticmethod
    def env(revision):
        return {"PS2X_PEEK": ga.peek_spec(revision), "PS2X_CALL_TRACE": ga.call_trace_spec(revision),
                "PS2X_CALL_TRACE_EVERY": "10"}

    def test_each_columns_own_spec_passes_every_pre_launch_check(self):
        from tools_py.parity import online_match_ours as M
        for revision in ("r0001", "r0004"):
            e = self.env(revision)
            self.assertEqual(M.spec_revision(e["PS2X_PEEK"]), revision)
            self.assertEqual(M.move_path_preconditions(e), [], revision)
            self.assertEqual(M.health_peek_problems(e["PS2X_PEEK"], 0x1044), [], revision)
            self.assertEqual(M.peek_spec_problems(e["PS2X_PEEK"]), [], revision)
            # The fourth check, found by the ladder's own dry run during fix round 1: it compared an
            # r0004 spec against r0001's CZNetGame and clock chains, so an r0004 ladder would have been
            # refused for carrying exactly the right instruments.
            self.assertEqual(M.endgame_preconditions(e), [], revision)

    def test_all_ten_valves_are_requested_on_both_columns(self):
        from tools_py.parity import online_match_ours as M
        from tools_py.parity import verdict_core as vc
        for revision in ("r0001", "r0004"):
            self.assertEqual(sorted(M.requested_valves(ga.peek_spec(revision))), sorted(vc.VALVES),
                             revision)

    def test_the_checks_still_refuse_a_spec_that_is_missing_something(self):
        """Revision-aware, not permissive: an r0004 spec with the actor block cut still refuses, and the
        message names the r0004 base rather than r0001's."""
        from tools_py.parity import online_match_ours as M
        actor = "*%#x:64," % ga.address("player_actor", "r0004")
        e = self.env("r0004")
        e["PS2X_PEEK"] = e["PS2X_PEEK"].replace(actor, "")
        problems = M.move_path_preconditions(e)
        self.assertTrue(any("no actor block" in p for p in problems), problems)
        self.assertTrue(any("%#x" % ga.address("player_actor", "r0004") in p for p in problems), problems)
        self.assertFalse(any("%#x" % ga.address("player_actor", "r0001") in p for p in problems), problems)

    def test_a_spec_that_names_no_column_falls_back_to_r0001_and_refuses(self):
        from tools_py.parity import online_match_ours as M
        self.assertEqual(M.spec_revision(""), "r0001")
        self.assertTrue(M.move_path_preconditions({"PS2X_PEEK": "", "PS2X_CALL_TRACE_EVERY": "10"}))


if __name__ == "__main__":
    unittest.main()
