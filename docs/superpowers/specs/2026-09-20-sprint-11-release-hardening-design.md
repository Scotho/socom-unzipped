# Sprint 11 — "Release hardening: a public repository a stranger can trust" (design, drafted)

Requested by the owner on 2026-09-20, to sit at the END of the sprint stack (after Sprint 9 "A stranger's first
run" and Sprint 10 "Console players in the same lobby"). Drafted, not opened: the goals below are the owner's
five points in the owner's order, each with what "done" means. The plan is written when the sprint opens, against
the tree as it is then.

## Goals

### Goal 1 — the GitHub repository, cleaned for a public release
- Remove the immediately visible agent bloat: the README's agent-facing material, loop prompts, sprint ledgers,
  handoff notes and session records move out of the top level (to `docs/dev/` or out of the published tree), so the
  first screen a visitor sees is the project, not its scaffolding. Decide per file: publish under `docs/dev/`,
  keep private, or delete; record the decision in one table.
- Audit history and tree for what must not be public: keys (`vm/keys` is git-ignored — verify nothing leaked into
  history), server credentials, the hosted box's agent instructions, IPs that should be names, any disc-derived
  bytes (no Sony code or assets may be in the repository: the generated code, the ELF and the ISO stay out; verify
  test fixtures and reference screenshots against that rule and decide each).
- Branch hygiene (stale sprint branches), issue/PR templates, a CONTRIBUTING and a SECURITY file, CI badges.
- Bar: a fresh clone's top level reads as a product; a secrets scan over full history is clean; the owner reads
  the front page and says so.

### Goal 2 — the project and the agentic loop, explained
- A README that says what this is (a static recompilation of the player's own SOCOM II r0001 disc into a native
  PC program, with online play on a hosted Horizon server), what it is not (no game data shipped, not an
  emulator fork), its state, and how to get it.
- A separate document on how it was built: the controller/subagent loop, sprints, specs and plans, TDD with a
  watched RED, the three-stage parity gate, numbered rulings, the human-tasks file — honest about what the agents
  did and what the owner did. Linked from the README, not in it.

### Goal 3 — the landing page, and a full build from a fresh install
- Revise `../scotho` `sites/s2u` (s2u.scotho.com) with current, accurate material: what works today, platforms
  (Windows, Linux), the hosted server and its name (socom.scotho.com), screenshots from the current build, the
  download, and the aspiration for the SOCOM community r0004 patch in the future — stated as an aspiration,
  with nothing implying PSRewired's endorsement. Deploy stays the owner's action unless the owner says otherwise.
- Test a full build from a fresh install: a clean Windows machine or VM and the Linux VM from a wiped state,
  following only the written instructions, from clone to a running game — every missing step found this way is a
  documentation defect fixed in Goal 4. The same for the portable download: a fresh machine, the archive, the
  player's ISO, a round online.

### Goal 4 — foolproof install instructions and FAQs
- One page per audience: players (download, point at your own disc, play; controller, microphone, saves, online
  account, what each launcher error sentence means and what to do) and builders (toolchain, the recompile step,
  the build, the tests). Every command copy-pasteable and verified by Goal 3's fresh-install run.
- FAQ from real failure modes: which disc revision and how to check it, why the ISO is not included, antivirus and
  SmartScreen on an unsigned exe, GPU/driver requirements (exit 65), Linux dependencies, ports and firewalls,
  where saves and logs live, how to send diagnostics.

### Goal 5 — licences and accreditations, in git
- An inventory of every third-party component in the tree and in the shipped archives (ps2recomp and its
  dependencies, raylib, SDL2, FFmpeg libraries and their LGPL/GPL build configuration, the fonts (Saira Stencil
  One, Rajdhani — OFL), toolchain runtime DLLs, the Horizon server and its licence, anything vendored under
  `third_party/`), with each licence text in `LICENSES/` and a `THIRD_PARTY_NOTICES` shipped inside every archive.
- The project's own licence chosen by the owner (compatible with what it links); trademark and non-affiliation
  notices (SOCOM, Sony, Zipper, PlayStation); credits for the community work this stands on.
- Bar: a test that fails when a DLL or vendored directory ships without an inventory row.

### Goal 6 — the progress story (owner, 2026-09-20)
- A linear, readable timeline of the project from the first commit (2026-09-02) to the release: the first render,
  then each improvement and milestone in order -- the first menu, the first mission, sound, the first online
  login, the first lobby, the first kill between two instances, the water and terrain fixes, the launcher, Linux,
  memory cards, the hosted server, the redesign, voice -- told as a story a player enjoys, with the complicated
  details buried (a one-line "how" per entry at most, each linking to the commit or research note for the curious).
- Sources, read by a script and not by memory: this repository's commit history (677 commits at the time of the
  request) and the read-only monitor project at `../socom_monitor`, which indexes every run under `logs/parity/`
  and `logs/parity/gate/` with verdicts, contact sheets and A/B screenshots. The script proposes the timeline's
  candidate entries (first passing gate, first ladder kill, score jumps, new stages) with the screenshot that shows
  each; the editorial pass chooses and writes. Every dated claim carries its commit or run id, so the story is
  checkable, and a test fails if an entry cites something that does not exist.
- One picture per milestone where a run captured one (before/after pairs for the visual fixes), checked against
  Goal 1's rule that no disc-derived asset ships beyond what fair illustration of our own output needs -- the
  owner decides that line.
- Delivered as a page on the landing site (Goal 3) and a `docs/STORY.md` linked from the README (Goal 2).
- Bar: the owner reads it start to finish and it is fun; a stranger can tell what happened and in what order
  without knowing what a GS or an IOP is.

## Owner-gated
The project's licence; what of the development record is published; the landing page's deploy; signing; the
wording about the community server.
