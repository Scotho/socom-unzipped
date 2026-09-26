"""The two Claude Code agent definitions every Sprint 14+ brief dispatches by name (Sprint 14 G4).

`.claude/agents/implementer.md` and `.claude/agents/reviewer.md`: YAML frontmatter with `name` (equal to the
filename stem, so a dispatch by name finds the file it reads as), `description`, `model` and `tools`; the reviewer
is read-only by its tool list (no Edit, no Write); the implementer's body names the worktree script and the
reviewer's the `file:line` finding form. Field names per https://code.claude.com/docs/en/sub-agents.
"""
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AGENTS = os.path.join(ROOT, ".claude", "agents")


def parse_agent(path):
    """Return (frontmatter dict, body) for a `---`-fenced markdown agent file; flat `key: value` lines only."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("%s: no opening frontmatter fence" % path)
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise ValueError("%s: no closing frontmatter fence" % path)
    meta = {}
    for line in lines[1:end]:
        if ":" in line and not line.startswith((" ", "\t", "#")):
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta, "\n".join(lines[end + 1:])


class TestAgentDefinitions(unittest.TestCase):
    NAMES = ("implementer", "reviewer")

    def load(self, name):
        path = os.path.join(AGENTS, name + ".md")
        self.assertTrue(os.path.isfile(path), "missing %s" % path)
        return parse_agent(path)

    def test_frontmatter_fields(self):
        for name in self.NAMES:
            with self.subTest(agent=name):
                meta, _ = self.load(name)
                self.assertEqual(meta.get("name"), name)
                for field in ("description", "model", "tools"):
                    self.assertTrue(meta.get(field), "%s: empty or missing %s" % (name, field))

    def test_reviewer_cannot_edit(self):
        meta, _ = self.load("reviewer")
        tools = [t.strip() for t in meta["tools"].split(",")]
        self.assertNotIn("Edit", tools)
        self.assertNotIn("Write", tools)

    def test_implementer_body_names_the_worktree_script(self):
        _, body = self.load("implementer")
        self.assertIn("agent_worktree.sh", body)

    def test_reviewer_body_names_file_line(self):
        _, body = self.load("reviewer")
        self.assertIn("file:line", body)


class TestParserCatchesAMissingFence(unittest.TestCase):
    """The parser against a planted file with no frontmatter."""

    def test_no_fence_raises(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "x.md")
            with open(path, "w", encoding="utf-8") as f:
                f.write("name: x\n")
            with self.assertRaises(ValueError):
                parse_agent(path)


if __name__ == "__main__":
    unittest.main()
