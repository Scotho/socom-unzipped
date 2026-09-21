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
| A clone, Windows (Git Bash, Python 3) | the runtime library, the C++ suite, the launcher, the tools; the Python suite | `bash scripts/bootstrap_windows.sh` (fetches llvm-mingw, CMake and Ninja into `tools/`, each pinned by sha256; ~245 MB once), then `./build.sh runtime --no-runner` and `./build.sh test --no-runner`. The `windows` workflow does exactly this on a bare runner. |
| Your own r0001 disc as well | the game | `pip install unicorn`, then `bash scripts/disc_to_elf.sh "<your ISO>"` (eight minutes and 4.2 GB: it extracts the disc and decrypts the overlays), then `./build.sh recomp`, `./build.sh runtime`, `./build.sh test` (Windows, Git Bash) or `scripts/build_linux.sh`; the recipe is `docs/DEVELOPING.md` "From your own disc to a buildable ELF". |

**The state of the game build (2026-09-21).** `./build.sh recomp` starts from files this repository does not and must not contain: the extracted disc tree (`game/disc/`) and the plaintext overlays merged into one ELF (`game/overlays/socom2_game.elf`). Producing them from your own disc is now one command -- `bash scripts/disc_to_elf.sh "<your ISO>"` -- which extracts the ISO9660 filesystem, decrypts the DNAS overlay and the `RUN/RAW/APACHE00.ZDB` code package by running the game's own code under Unicorn, merges the result into the ELF, and verifies every step against the digests recorded in `tools_py/disc_to_elf_expected.json`. It is idempotent: a second run is a no-op that still verifies. **What is proven:** the whole path a newcomer is told to walk, run end to end on 2026-09-21 from a genuine `git clone` of this repository into an empty directory on Windows -- clone, `install_hooks.sh`, `bootstrap_windows.sh` (a real 245 MB download from no cache), `build.sh runtime --no-runner`, `build.sh test --no-runner` (764/764), the Python suite, `disc_to_elf.sh` against an r0001 ISO, `build.sh recomp`, `build.sh runtime` -- **42 minutes from `git clone` to a `dist/socom2.exe` of 236,852,224 bytes**, with the overlays and the merged ELF hashing to the recorded digests on the third independent reproduction of them. The numbers are in `docs/superpowers/plans/2026-09-21-sprint-10-disc-to-elf.md`. **What is not:** any other disc image of that revision (the command says clearly which check failed if yours differs), and the same chain on Linux, where only `scripts/build_linux.sh` has been run and never from an ISO. If either fails for you, open an issue with the line it refused on -- that is exactly the report this needs.

Not sure your disc is r0001? The launcher checks it and says so (exit code 67 is "not r0001").

## Before you open a pull request

0. **Install the hooks, once per clone:** `bash scripts/install_hooks.sh`. It points git at `scripts/hooks/`, where a
   leak check (`python -m tools_py.release.leakcheck`) runs over what you are about to commit and, again, over every
   commit you are about to push: key material, tokens, a home directory with your user name in it, an address, a
   file the `.gitignore` refuses. CI runs the same check plus gitleaks on every push. If it stops you, fix the hit;
   if the hit is a reviewed non-secret (a test fixture, a version string it misread), add one line with its reason
   to `tools_py/release/leak_allow.txt` in the same PR. Do not bypass it with `--no-verify` -- the push hook and CI
   will refuse the same thing, and a secret in a pushed commit means rewriting history.
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
