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

## Owner-gated
The project's licence; what of the development record is published; the landing page's deploy; signing; the
wording about the community server.
