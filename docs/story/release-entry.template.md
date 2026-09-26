# The release entry — template (Sprint 11 Goal 6, spec §1 and §10 Phase D)

There is no release yet, so `docs/STORY.md` cannot truthfully carry a release entry; what it carries instead is the
uncited "Where it stands tonight" section, which this entry replaces when the release exists. Everything in braces is a
field the release run stamps — from the run, never from the directory (`docs/HAZARDS.md` build: a failed packaging leaves
the previous archive in place). `tools_py/story/cite.py` fails the suite if a `{{` or `}}` survives in `STORY.md`, so a
pasted-but-unfilled template cannot ship.

Paste this as the last `###` entry, then delete the "Where it stands tonight" section and its introductory italic line.

```markdown
### {{date}} — {{title: what a player can do now that they could not before}}

**{{hook: one sentence, the release's single most important fact for a player}}**

{{body: 2-5 sentences. What ships, for whom, and what it took to get from playtest-1 to here — in the order it happened.
Name the tag, the archive size, and the checksum file. Say what a stranger does: point the launcher at their own r0001
disc, and what happens next. No sentence a player would not understand.}}

*How:* {{one line at most, e.g. the gate id and its 3/3 on the exe inside the archive, and the release workflow that cut it}}

*But:* {{the honest edge: what has never been tried (a second network? a stranger's machine? a real Linux GPU?), what is
unsigned, what is believed rather than proven — read docs/HAZARDS.md at the release commit and quote it}}

`Cited:` `{{release commit short sha}}` {{a fragment of its subject} · gate {{gate id on the released exe}} · docs/PLAYTEST.md · docs/KNOWN.md
```

Then, for the same pass (spec §1, the four things the later pass must add):

1. **Pictures** — `docs/story/PICTURES.md` gets a row for anything new; the release itself rarely needs one.
2. **D1 reconciliation** — if the history was rewritten before the flip, `python -m tools_py.story.remap --map
   .git/filter-repo/commit-map` first, then `python -m tools_py.story.cite` must be clean; if the public repository is a
   fresh import, follow spec §4.4 decision 4 and put the one-sentence header note in `STORY.md`'s preface.
3. **The site page** — the hosted-server session takes a fresh copy of `docs/STORY.md`, `docs/story/timeline.json` and
   `docs/story/img/` at deploy (spec §6.2); `docs/story/index.html` is the reference rendering.
4. **The preface** — "The ending is open" comes out; the two-clocks note stays.

Witness the new run citation with `python -m tools_py.story.witness --captured {{YYYY-MM-DD}}` before running the check.
