"""Sprint 10 Q4: the harness finds the game window by a title substring (keys.WINDOW_TITLES["ours"]), and the
runner composes its title from ps2x/host_window.h. The two live in different languages, so this is what holds
them together: the key IS the header's suffix, the launcher's own window title does not contain it (or the
harness would post its keystrokes into the launcher when the owner has it open), and PCSX2's does not either.
"""
import os
import re
import unittest

from tools_py.parity import keys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HEADER = os.path.join(ROOT, "third_party", "ps2recomp", "ps2xShared", "include", "ps2x", "host_window.h")
LAUNCHER_MAIN = os.path.join(ROOT, "third_party", "ps2recomp", "ps2xLauncher", "src", "main.cpp")


def _cxx_string(text, name):
    m = re.search(r'constexpr const char \*%s = "([^"]*)";' % re.escape(name), text)
    if m is None:
        raise AssertionError("%s not found in %s" % (name, HEADER))
    return m.group(1)


class HostWindowTitleTest(unittest.TestCase):
    def test_key_is_the_runner_suffix_and_not_the_launcher_title(self):
        with open(HEADER, encoding="utf-8") as f:
            header = f.read()
        suffix = _cxx_string(header, "kTitleSuffix")
        product = _cxx_string(header, "kProduct")
        key = keys.WINDOW_TITLES["ours"]
        self.assertEqual(key, suffix.strip(), "keys.py's key must be the header's suffix (spaces trimmed)")
        self.assertTrue(suffix.endswith(product), "the suffix carries the product name")
        self.assertNotIn(key, product, "the launcher's own title must not contain the key")
        self.assertNotIn(key, keys.WINDOW_TITLES["pcsx2"], "nor may PCSX2's")
        with open(LAUNCHER_MAIN, encoding="utf-8") as f:
            main = f.read()
        m = re.search(r'InitWindow\([^;]*?"([^"]*)"\);', main)
        self.assertIsNotNone(m, "the launcher's InitWindow title literal")
        self.assertEqual(m.group(1), product, "the launcher opens under the product name exactly")
        self.assertNotIn(key.lower(), m.group(1).lower(), "case-insensitively too: find_window lowercases both sides")


if __name__ == "__main__":
    unittest.main()
