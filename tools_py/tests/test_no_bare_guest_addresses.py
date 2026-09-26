"""No bare guest address outside the per-revision table (Sprint 13 Task H6, audit harness-tools H19-H23).

docs/HAZARDS.md recompiler's rule: a guest address is read from `tools_py/parity/guest_addresses.py`'s table BY NAME, one
column per revision, and a value the table lacks for a revision is UNCONFIRMED and refused, never guessed.
A literal written at the place that uses it is how every r0004 silence so far happened (`s11_r0004_round1`
scored NO-DATA on a round both clients played to its clock): an instrument reading another build's memory
does not present as an error, it presents as silence, or as a number.

This test is the gate on NEW ones. It reads every `tools_py/parity/*.py` and every text file under
`scripts/parity/`, finds each `0x` literal of six to eight hex digits that falls in the EE's address ranges
(main RAM 0x00100000-0x01fffffe and its kseg0 / kseg1 / uncached mirrors), and refuses any that is neither
in `guest_addresses.py` nor named, with its reason, in `tools_py/parity/bare_address_allow.txt`.

WHAT COUNTS. In Python, code only: integer literals, and string constants that are not docstrings (a peek
spec is a string, and so is a message that prints an address -- both are allowed only with a reason).
Comments and docstrings are prose and are not scanned: an address in a sentence cannot be read by
anything. In the shell / JSON / pnach files under scripts/parity, every line that is not a comment.
`0x01ffffff` is the 32 MB mask, not an address, and is not counted.

THE ALLOW LIST. One line per survivor, `<path> <literal> <reason>`, matched by (path, value) so a line
moving within its file does not need an edit. An entry that no longer matches anything FAILS too: a list
of reasons nobody can check against the tree is how a list of excuses starts.
"""
import ast
import os
import re
import subprocess
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PARITY_PY = os.path.join(ROOT, "tools_py", "parity")
SCRIPTS = os.path.join(ROOT, "scripts", "parity")
HOME = "tools_py/parity/guest_addresses.py"
ALLOW = os.path.join(PARITY_PY, "bare_address_allow.txt")

HEX_RE = re.compile(r"(?<![0-9A-Za-z_])0[xX]([0-9a-fA-F]{6,8})(?![0-9A-Za-z_])")
RAM_LO, RAM_HI = 0x00100000, 0x01FFFFFF          # [lo, hi): 0x01ffffff itself is the mask
MIRRORS = (0x00000000, 0x20000000, 0x30000000, 0x80000000, 0xA0000000)
BINARY_EXT = (".png", ".wav", ".bin", ".rdram", ".jpg", ".zip")


def is_guest_address(value):
    for base in MIRRORS:
        if RAM_LO <= value - base < RAM_HI:
            return True
    return False


def _docstring_nodes(tree):
    """Every string constant that is a statement on its own: docstrings, and strings used as comments."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) \
                and isinstance(node.value.value, str):
            out.add(id(node.value))
    return out


def python_literals(path):
    """[(line, literal text)] of every guest-address literal in the file's CODE."""
    with open(path, encoding="utf-8") as f:
        src = f.read()
    tree = ast.parse(src, filename=path)
    skip = _docstring_nodes(tree)
    lines = src.splitlines()
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or id(node) in skip:
            continue
        if isinstance(node.value, bool):
            continue
        if isinstance(node.value, int):
            if not is_guest_address(node.value) or node.end_lineno != node.lineno:
                continue
            # The literal as written (col offsets are UTF-8 byte offsets): only a HEX spelling counts.
            seg = lines[node.lineno - 1].encode("utf-8")[node.col_offset:node.end_col_offset].decode("utf-8")
            if HEX_RE.fullmatch(seg):
                out.append((node.lineno, seg))
        elif isinstance(node.value, str):
            for m in HEX_RE.finditer(node.value):
                if is_guest_address(int(m.group(1), 16)):
                    out.append((node.lineno, m.group(0)))
    return out


def _strip_comment(line, path):
    s = line.lstrip()
    if s.startswith("#") or s.startswith("//"):
        return ""
    if path.endswith(".sh"):
        return re.sub(r"(^|\s)#.*$", "", line)
    if path.endswith(".pnach"):
        return re.sub(r"//.*$", "", line)
    return line


def text_literals(path):
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except (UnicodeDecodeError, OSError):
        return []
    out = []
    for i, line in enumerate(lines, 1):
        for m in HEX_RE.finditer(_strip_comment(line, path)):
            if is_guest_address(int(m.group(1), 16)):
                out.append((i, m.group(0)))
    return out


def tracked(prefix):
    """The files git tracks under `prefix` (a build product or a local log is not the tree's business)."""
    p = subprocess.run(["git", "ls-files", "--", prefix], cwd=ROOT, stdout=subprocess.PIPE,
                       stderr=subprocess.DEVNULL, universal_newlines=True)
    if p.returncode != 0:
        return None
    return sorted(l.strip() for l in p.stdout.splitlines() if l.strip())


def scan():
    """{(path, value): [(line, literal)]} over the scanned tree, `guest_addresses.py` excluded."""
    files = tracked("tools_py/parity")
    if files is None:                                   # no git: walk the directories instead
        files = sorted("tools_py/parity/" + n for n in os.listdir(PARITY_PY))
        for d, _dirs, names in os.walk(SCRIPTS):
            files += sorted(os.path.relpath(os.path.join(d, n), ROOT).replace(os.sep, "/") for n in names)
    else:
        files += tracked("scripts/parity") or []
    found = {}
    for rel in files:
        if rel == HOME:
            continue
        full = os.path.join(ROOT, rel)
        if not os.path.isfile(full) or rel.lower().endswith(BINARY_EXT):
            continue
        if rel.startswith("tools_py/parity/"):
            if not rel.endswith(".py") or "/" in rel[len("tools_py/parity/"):]:
                continue
            hits = python_literals(full)
        else:
            hits = text_literals(full)
        for line, lit in hits:
            found.setdefault((rel, int(lit, 16)), []).append((line, lit))
    return found


def load_allow(path=ALLOW):
    """{(path, value): reason}; a malformed line raises."""
    out = {}
    with open(path, encoding="utf-8") as f:
        for n, raw in enumerate(f, 1):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(None, 2)
            if len(parts) < 3 or not HEX_RE.fullmatch(parts[1]):
                raise ValueError("%s:%d: want `<path> <0x literal> <reason>`, got %r" % (path, n, line))
            key = (parts[0], int(parts[1], 16))
            if key in out:
                raise ValueError("%s:%d: %s %s is listed twice" % (path, n, parts[0], parts[1]))
            out[key] = parts[2]
    return out


class NoBareGuestAddresses(unittest.TestCase):
    def test_every_guest_address_literal_is_in_the_table_or_allowed_with_a_reason(self):
        found, allow = scan(), load_allow()
        bare = sorted((p, v) for (p, v) in found if (p, v) not in allow)
        self.assertEqual(bare, [], "bare guest addresses outside tools_py/parity/guest_addresses.py -- move "
                         "each into the table (by name, one column per revision) or allow it in "
                         "tools_py/parity/bare_address_allow.txt with its reason:\n" + "\n".join(
                             "  %s:%d %s" % (p, found[(p, v)][0][0], found[(p, v)][0][1]) for p, v in bare))

    def test_every_allow_entry_still_names_a_literal_in_the_tree(self):
        found, allow = scan(), load_allow()
        stale = sorted("%s %#x" % k for k in allow if k not in found)
        self.assertEqual(stale, [], "allow-list entries that match nothing any more -- delete them")

    def test_every_allow_entry_gives_a_reason(self):
        for (p, v), reason in load_allow().items():
            self.assertGreaterEqual(len(reason.split()), 3, "%s %#x: a reason is a sentence" % (p, v))


class TheScannerSeesWhatItMust(unittest.TestCase):
    """The scanner's own contract, on synthetic sources -- a scan that sees nothing passes every tree."""

    def _py(self, text):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as f:
            f.write(text)
        try:
            return [lit for _l, lit in python_literals(f.name)]
        finally:
            os.remove(f.name)

    def test_code_literals_and_spec_strings_count(self):
        self.assertEqual(self._py("A = 0x49e150\nS = '*0x488de8+0x120:96'\n"), ["0x49e150", "0x488de8"])
        self.assertEqual(self._py("X = f'{Y:#x} at 0x4365c0'\n"), ["0x4365c0"])

    def test_docstrings_comments_and_non_addresses_do_not(self):
        self.assertEqual(self._py('"""0x49e150 in prose"""\n# 0x49e150\nM = 0x1FFFFFF\nK = 0xFFFFFFFF\n'
                                  'F = 0x42480000\nL = 0x0ee89a\nR = 0x2000000\n'), [])

    def test_the_mirrors_count(self):
        self.assertTrue(is_guest_address(0x2049E150))
        self.assertTrue(is_guest_address(0x8049E150))
        self.assertFalse(is_guest_address(0xC0000001))
        self.assertFalse(is_guest_address(0x000FFFFF))


class TheServerDefaultIsTheHostedBox(unittest.TestCase):
    """H19: a bare `online_control_round.sh` targeted a private LAN address -- the owner's machine. The
    default is the hosted box, by the name the launcher's default preset and the README use."""

    def test_env_sh_defaults_to_the_hosted_name_and_carries_no_private_address(self):
        with open(os.path.join(SCRIPTS, "env.sh"), encoding="utf-8") as f:
            text = f.read()
        self.assertTrue('SOCOM_SERVER_IP="${SOCOM_SERVER_IP:-socom.scotho.com}"' in text,
                        "scripts/parity/env.sh's SOCOM_SERVER_IP default is not the hosted box's name")
        self.assertIsNone(re.search(r"\b(192\.168|10\.\d+\.\d+\.\d+\b|172\.(1[6-9]|2\d|3[01])\.)", text),
                          "a private LAN address is in scripts/parity/env.sh")


if __name__ == "__main__":
    unittest.main()
