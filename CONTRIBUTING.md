# Contributing to SOCOM Unzipped

SOCOM Unzipped is a static recompilation of SOCOM II: U.S. Navy SEALs (NTSC, SCUS-97275, disc revision r0001) into a
native PC program, with online play on a hosted Horizon server. **No game code or game data is in this repository, and
none may be added**: not the ISO, not the ELF, not the recompiler's generated C++, not textures, audio or movies cut from
the disc, not memory-card saves. A pull request that contains any of it is closed unread.

## What you can build without the disc

The playable executable needs code generated from your own disc, so a fresh clone cannot build the game. It **can**
build and test everything else, which is where most contributions land:

| You have | You can build | How |
|---|---|---|
| A clone, Linux (Ubuntu 24.04 is what CI uses) | the runtime library, the C++ suite, the launcher, the tools; the Python suite | `bash scripts/build_linux.sh --no-runner`, then `bash scripts/build_linux.sh test --no-runner`. The package list is in `.github/workflows/linux.yml`. |
| A clone, Windows | the Python suite: `python -m unittest discover -s tools_py/tests -t .` | A disc-less C++ build on Windows is a tracked gap (Sprint 11 Goal 0): `build.sh` assumes a portable toolchain under `tools/` that is not in the repository. |
| Your own r0001 disc as well | the game | `./build.sh recomp`, `./build.sh runtime`, `./build.sh test` (Windows, Git Bash) or `scripts/build_linux.sh`; see the README's "For developers" and `docs/DEVELOPING.md`. |

Not sure your disc is r0001? The launcher checks it and says so (exit code 67 is "not r0001").

## Before you open a pull request

1. **Branch from `main`**, named `fix/<slug>`, `feat/<slug>` or `docs/<slug>`. One topic per PR. (`sprint-N` branches
   are the maintainers' integration branches; do not target them.) The whole scheme is `docs/GIT_STRATEGY.md`.
2. **A failing test first** for any change to behaviour. C++ cases live in `third_party/ps2recomp/ps2xTest/src/`,
   Python ones in `tools_py/tests/` (unittest only, no pytest). Say in the PR what the test failed with before your fix.
3. **Both suites green.** CI runs them on Linux. A change that touches the runtime, `recomp/`, `tools_py/parity/`,
   `scripts/parity/` or `build.sh` also has to pass the three-stage in-game gate (`python -m tools_py.parity.gate`),
   which needs the disc -- if you do not have one, say so and a maintainer runs it.
4. **Say what you measured.** This project does not accept "should be faster" or "looks right": give the number, the
   command that produced it, and what it was before. If you moved a default or skipped a measurement, say that too.
5. **Commits:** `type(scope): what changed and why`, types `feat fix refactor test docs build ci chore`. Outside PRs
   are squash-merged, so a tidy history is welcome but not required.
6. **New environment knobs** (`PS2X_*`) need a reason and a row in the knob table (`docs/KNOBS.md`, once Sprint 9
   Goal 3 lands); a knob that names a path must stay inside the portable folder.
7. **Third-party code** needs its licence text under `LICENSES/` and a row in the notices file in the same PR. The
   vendored recompiler (`third_party/ps2recomp`) is GPL-3.0 and the executable links it, so contributions are accepted
   under GPL-3.0-compatible terms.

## What is most useful

Reproducible bug reports, fixes with a test, Linux and Steam Deck results on real GPUs, controller mappings, and
documentation that a stranger followed successfully. Large refactors and new features: open an issue first.

## Reporting a bug

- **As a player:** use REPORT A BUG in the launcher (or on https://s2u.scotho.com). It goes to a private inbox, can
  attach a scrubbed log if you tick the box, and gives you a `BR-` id. Nothing is sent until you press SEND.
- **As a contributor:** open a GitHub issue with the bug template. If you also sent a launcher report, put its `BR-`
  id in the issue instead of pasting your log in public. SAVE DIAGNOSTICS in the launcher writes a zip with your home
  directory and credentials removed; attach that if a maintainer asks.
- **Security problems:** not in a public issue -- see `SECURITY.md`.

## Conduct

Be civil and specific. This is a preservation project run by one person and a set of AI agents working under that
person's direction (`docs/HANDOFF.md` and `docs/LOOP_PROMPT.md` describe how); agent-written commits carry a
`Co-Authored-By` trailer. Cheats, exploits against other players, and anything aimed at a server the project does not
run are out of scope and unwelcome. SOCOM, PlayStation and related marks belong to their owners; this project is not
affiliated with or endorsed by Sony Interactive Entertainment.
