"""Sprint 13 Task V8 (with S2): the launcher's wording held to the code it describes.

The stranger-player audit (docs/audits/2026-09-25-project-audit/stranger-player.md rows 9-15) and the code-runtime
audit's F53 found sentences that disagreed with each other or with the tree: a page the install guide never
mentions, an exit code the play-test asked for from a place it cannot come from, voice described three ways, a
keyboard sentence the key map contradicts, and a config comment one render scale short. Each check below reads the
source of truth (a C++ table, the key map, the exit-code header) and the words that describe it, so the next edit
to one without the other fails here. The C++ halves (LAUNCH's blocked reason, the sample reference id, exit 75)
are in ps2xTest: launcher_tests.cpp, bug_report_tests.cpp, socom2_libnetb_tests.cpp.
"""
import os
import re
import unittest

from tools_py import exit_codes

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PS2R = os.path.join(ROOT, "third_party", "ps2recomp")
LAUNCHER_UI = os.path.join(PS2R, "ps2xLauncher", "src", "ui")


def read(*parts):
    with open(os.path.join(*parts), encoding="utf-8") as fh:
        return fh.read()


def doc(name):
    return read(ROOT, *name.split("/"))


def faq_sections():
    """{code: section text} for every '### <code> -- ...' heading in FAQ.md's exit table."""
    text = doc("docs/FAQ.md")
    out = {}
    for m in re.finditer(r"^### (\d+) — .*?(?=^### |^---|\Z)", text, re.M | re.S):
        out[int(m.group(1))] = m.group(0)
    return out


def default_keys():
    """mapping.cpp's kDefaultKeys, the printable ones: {'Q': 'L1', '2': 'L3', ...}."""
    text = read(PS2R, "ps2xShared", "src", "mapping.cpp")
    block = re.search(r"kDefaultKeys\[\]\s*=\s*\{(.*?)\};", text, re.S).group(1)
    return {k: b.upper() for k, b in re.findall(r"\{'(.)',\s*kPs2(\w+)\}", block)}


class GameVersionRowIsExplained(unittest.TestCase):
    """Row 9: PLAY and ONLINE both draw GAME VERSION (pages.h, gameVersionRow) with a greyed cell for a build that
    is not installed; the install guide and the FAQ must name the row and every cell's label as the code spells it."""

    def labels(self):
        text = read(PS2R, "ps2xShared", "include", "launcher", "launcher_config.h")
        block = re.search(r"kGameRevisions\[\]\s*=\s*\{(.*?)\};", text, re.S).group(1)
        found = re.findall(r'\{"(r\d{4})",\s*"([^"]+)"', block)
        self.assertGreaterEqual(len(found), 2, block)
        return [label for _, label in found]

    def test_install_and_faq_name_the_row_and_each_cell(self):
        self.assertIn('"GAME VERSION"', read(LAUNCHER_UI, "pages.h"), "the row the documents describe")
        for name in ("docs/INSTALL.md", "docs/FAQ.md"):
            text = doc(name)
            with self.subTest(doc=name):
                self.assertIn("GAME VERSION", text)
                for label in self.labels():
                    self.assertIn(label, text, f"{name} does not name the cell {label!r}")


class ExitCodesSayWhereTheyAreMet(unittest.TestCase):
    """Row 11: exit 66 cannot come from the launcher's LAUNCH (it greys out first), yet the play-test asked for it
    that way. Every code the header defines past 3 has an FAQ entry, and each entry says where it can be met."""

    def test_every_code_has_an_entry_that_says_where_it_is_met(self):
        sections = faq_sections()
        for row in exit_codes.table():
            if row["code"] in (0, 1, 3):
                continue
            with self.subTest(code=row["code"]):
                self.assertIn(row["code"], sections, f"FAQ.md has no '### {row['code']} —' entry")
                body = sections[row["code"]]
                self.assertIn(row["sentence"], body, "the entry quotes the launcher's sentence word for word")
                self.assertIn("Where you meet it", body, "the entry says where the code can be met")

    def test_the_playtest_asks_only_for_what_can_happen(self):
        step = re.search(r"^4\. \*\*A failure that explains itself\*\*.*?(?=^5\. )", doc("docs/PLAYTEST.md"), re.M | re.S).group(0)
        live = re.sub(r"\*\(Superseded.*?\)\*", "", step, flags=re.S)
        self.assertNotIn("that file is not SOCOM II", live, "LAUNCH's reason for a missing file is the DISC page's sentence")
        self.assertIn("cannot open the file", live)
        self.assertRegex(live, r"with the launcher still open, rename your ISO", "66 is met by a disc that goes away after the check")


class OneSentenceForVoice(unittest.TestCase):
    """Row 12: the MICROPHONE page says the game does not send your voice yet; README, INSTALL and KNOWN said
    'untested end to end' and 'untested'. One sentence, the code's, everywhere."""

    SENTENCE = "does not send your voice yet"

    def test_the_code_and_the_documents_say_the_same_thing(self):
        self.assertIn("The game " + self.SENTENCE, read(LAUNCHER_UI, "page_microphone.cpp"))
        for name in ("README.md", "docs/INSTALL.md", "docs/KNOWN.md"):
            text = doc(name)
            with self.subTest(doc=name):
                self.assertIn(self.SENTENCE, text)
                self.assertNotRegex(text, r"[Vv]oice(?: chat)? is untested")


class KeyboardSentencesAgreeWithTheMap(unittest.TestCase):
    """Row 13: CONTROLLER said the keyboard is 'arrows, Enter, Backspace, Z/X/C/V' while the crouch hint sends fire
    mode to 'the keyboard's 2 key' -- which the default map binds to L3. Both sentences are held to mapping.cpp."""

    def caption_lines(self):
        """The string literals from the KEYBOARD label through 'Playing needs a controller.'."""
        text = read(LAUNCHER_UI, "page_controller.cpp")
        start = text.index('"KEYBOARD"')
        end = text.index("Playing needs a controller.", start) + len("Playing needs a controller.") + 1
        return re.findall(r'"([^"]*)"', text[start:end])[1:]

    def captions(self):
        return " ".join(self.caption_lines())

    def test_the_keyboard_caption_names_every_letter_and_digit_the_map_binds(self):
        keys = default_keys()
        self.assertEqual(keys["2"], "L3", "the audit's premise: 2 is L3")
        shown = self.captions()
        for key in keys:
            with self.subTest(key=key):
                self.assertRegex(shown, r"(?<![A-Za-z0-9])" + re.escape(key) + r"(?![a-z0-9])", f"the caption never names {key}")
        pairs = re.search(r"((?:[A-Z0-9]/)+[A-Z0-9]): ((?:[LR][123]/)+[LR][123])", shown)
        self.assertIsNotNone(pairs, f"no 'keys: buttons' pairing in {shown!r}")
        for key, button in zip(pairs.group(1).split("/"), pairs.group(2).split("/")):
            with self.subTest(key=key):
                self.assertEqual(keys.get(key), button, f"the caption says {key} is {button}; the map says {keys.get(key)}")

    def test_the_crouch_hints_name_the_key_the_map_gives_the_displaced_button(self):
        text = read(PS2R, "ps2xShared", "src", "launcher_config.cpp")
        keys = default_keys()
        displaced = {"l3": "L3", "l2": "L2"}   # the shortcut takes that pad button; its old job moves to a key
        for shortcut, button in displaced.items():
            with self.subTest(shortcut=shortcut):
                hint = re.search(r'v == "' + shortcut + r'"\)\s*return "([^"]+)";', text.split("crouchShortcutHint", 1)[1]).group(1)
                key = re.search(r"keyboard's (\S) key", hint).group(1)
                self.assertEqual(keys.get(key), button, f"{shortcut}: the hint names {key}, which the map binds to {keys.get(key)}")

    def test_install_quotes_the_page(self):
        install = doc("docs/INSTALL.md")
        for line in self.caption_lines():
            with self.subTest(line=line):
                self.assertIn(line, install, "INSTALL quotes the CONTROLLER page's keyboard lines word for word")


class RenderScaleComment(unittest.TestCase):
    """F53: Config::gsScale's comment is the persisted field's only documentation; it must name every DETAIL cell
    the VIDEO page offers."""

    def test_the_comment_names_every_scale_the_page_offers(self):
        page = read(LAUNCHER_UI, "page_video.cpp")
        cells = re.search(r"detail = \{([^}]*)\}", page).group(1)
        labels = re.findall(r'"([^"]+)"', cells)
        self.assertEqual(len(labels), 4, labels)
        header = read(PS2R, "ps2xShared", "include", "launcher", "launcher_config.h")
        comment = re.search(r"int gsScale = 1;\s*//([^\n]*)", header).group(1).lower()
        for n, label in enumerate(labels, start=1):
            word = label.split()[0].lower()
            with self.subTest(scale=n):
                self.assertIn(f"{n} {word}", comment, f"the comment does not name {n}x as {label!r}")


if __name__ == "__main__":
    unittest.main()
