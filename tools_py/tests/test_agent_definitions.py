"""The two Claude Code agent definitions every Sprint 14+ brief dispatches by name (Sprint 14 G4).

`.claude/agents/implementer.md` and `.claude/agents/reviewer.md`: YAML frontmatter with `name` (equal to the
filename stem, so a dispatch by name finds the file it reads as), `description`, `model` and `tools`; the reviewer's
tool list holds no editor (it keeps Bash, so this is a tool-list bar, not a proof it cannot write); the implementer's
body names the worktree script and the reviewer's the `file:line` finding form. Field names per
https://code.claude.com/docs/en/sub-agents, whose `tools` is "a comma-separated string ... or a YAML list".
"""
import os
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
AGENTS = os.path.join(ROOT, ".claude", "agents")
EDITORS = ("Edit", "Write", "MultiEdit", "NotebookEdit")


def _unquote(value):
    return value.strip().strip('"').strip("'")


def parse_agent(path):
    """Return (frontmatter dict, body) for a `---`-fenced markdown agent file.

    Flat `key: value` lines, plus YAML list items (`- item`) under the last key, which are joined into a
    comma string so both `tools:` forms read the same."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError("%s: no opening frontmatter fence" % path)
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise ValueError("%s: no closing frontmatter fence" % path)
    meta, key = {}, None
    for line in lines[1:end]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- ") and key is not None:
            item = _unquote(stripped[2:])
            meta[key] = item if not meta.get(key) else meta[key] + ", " + item
        elif ":" in line and not line[:1].isspace():
            key, _, value = line.partition(":")
            key = key.strip()
            meta[key] = _unquote(value)
    return meta, "\n".join(lines[end + 1:])


def tool_list(meta):
    """`tools:` as a list, from the comma-string form, a flow list `[A, B]`, or the YAML block-list form."""
    value = meta.get("tools", "").strip()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    return [_unquote(t) for t in value.split(",") if t.strip()]


def parse_text(text):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "x.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        return parse_agent(path)


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

    def test_reviewer_tools_exclude_editors(self):
        meta, _ = self.load("reviewer")
        tools = tool_list(meta)
        self.assertTrue(tools, "reviewer: no tools parsed")
        for editor in EDITORS:
            self.assertNotIn(editor, tools)

    def test_implementer_body_names_the_worktree_script(self):
        _, body = self.load("implementer")
        self.assertIn("agent_worktree.sh", body)

    def test_reviewer_body_names_file_line(self):
        _, body = self.load("reviewer")
        self.assertIn("file:line", body)


class TestParserCatchesPlantedDefects(unittest.TestCase):
    """The parser against planted files: no frontmatter, and an editor hidden in either `tools:` form."""

    def test_no_fence_raises(self):
        with self.assertRaises(ValueError):
            parse_text("name: x\n")

    def test_yaml_list_tools_with_an_editor_is_caught(self):
        meta, _ = parse_text("---\nname: x\ntools:\n  - Read\n  - Edit\nmodel: opus\n---\nbody\n")
        self.assertEqual(tool_list(meta), ["Read", "Edit"])
        self.assertEqual(meta["model"], "opus")
        self.assertIn("Edit", set(tool_list(meta)) & set(EDITORS))

    def test_comma_and_flow_forms_with_each_editor_are_caught(self):
        for editor in EDITORS:
            for line in ("tools: Read, %s, Bash" % editor, "tools: [Read, %s]" % editor):
                with self.subTest(line=line):
                    meta, _ = parse_text("---\nname: x\n%s\n---\n" % line)
                    self.assertIn(editor, tool_list(meta))


if __name__ == "__main__":
    unittest.main()
