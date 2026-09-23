"""`tools_py.story.timeline` rebuilds docs/story/timeline.json from the document and nothing else."""
import json
import os
import unittest

from tools_py.story import cite, timeline

ROOT = cite.ROOT

_DOC = """# A story

## 2026-09-02 .. 2026-09-03 - The first era

*Standing.*

### 2026-09-02 - The first thing

**The hook of the first thing.**

A body.

![A caption.](docs/story/img/2026-09-02-x.png)

`Cited:` `abc1234` a subject fragment · docs/README.md · run some_run · gate some_gate · logs/some.log
"""


class FakeResolver(object):
    def commit(self, ref):
        if ref == "abc1234":
            return ("abc1234" + "0" * 33, "2026-09-02", "feat: a subject fragment, the rest of the line")
        return None


class TestBuild(unittest.TestCase):
    def test_one_entry_becomes_one_row_with_every_field(self):
        doc = timeline.build(_DOC, FakeResolver(), "2026-09-22", "deadbee")
        self.assertEqual(doc["schema"], 1)
        self.assertEqual(doc["head"], "deadbee")
        row = doc["entries"][0]
        self.assertEqual(row["id"], "2026-09-02-the-first-thing")
        self.assertEqual(row["era"], "2026-09-02 .. 2026-09-03 - The first era")
        self.assertEqual(row["hook"], "The hook of the first thing.")
        self.assertEqual(row["picture"], {"path": "docs/story/img/2026-09-02-x.png", "caption": "A caption."})
        kinds = [c["kind"] for c in row["citations"]]
        self.assertEqual(kinds, ["commit", "path", "run", "gate", "log"])
        self.assertEqual(row["citations"][0]["date"], "2026-09-02")
        self.assertEqual(row["citations"][2]["path"], "logs/parity/some_run")
        self.assertEqual(row["citations"][3]["path"], "logs/parity/gate/some_gate")

    def test_a_hash_that_does_not_resolve_stops_the_build(self):
        with self.assertRaises(ValueError):
            timeline.build(_DOC.replace("abc1234", "fffffff"), FakeResolver(), "2026-09-22", "deadbee")

    def test_the_slug_is_the_sites_anchor_shape(self):
        self.assertEqual(timeline.slug("It says why it won't start, and it weighs less"),
                         "it-says-why-it-won-t-start-and-it-weighs-less")


class TestTheTrackedFileIsInStep(unittest.TestCase):
    """The tracked timeline.json is what the document says, on a clone that can ask git."""

    def test_tracked_timeline_matches_the_document(self):
        story = os.path.join(ROOT, "docs", "STORY.md")
        out = os.path.join(ROOT, "docs", "story", "timeline.json")
        if not (os.path.exists(story) and os.path.exists(out)):
            self.skipTest("no story or no timeline in this tree")
        resolver = cite.GitResolver(root=ROOT)
        if resolver.shallow():
            self.skipTest("a shallow clone cannot resolve the cited commits")
        with open(story, encoding="utf-8") as f:
            markdown = f.read()
        with open(out, encoding="utf-8") as f:
            tracked = json.load(f)
        built = timeline.build(markdown, resolver, tracked.get("generated", ""), tracked.get("head", ""))
        self.assertEqual(built["entries"], tracked["entries"])


if __name__ == "__main__":
    unittest.main()
