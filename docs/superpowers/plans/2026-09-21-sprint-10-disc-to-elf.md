# Sprint 10 — from a stranger's ISO to a buildable ELF, in one command (record)

Branch `agent/disc` off `sprint-10` at `9f0fcee`, worktree `C:\projects\wt-disc`, 2026-09-21. The brief: make the one
step of the build chain that had never been written down reproducible, and prove it from nothing. Its specification was
the two paragraphs committed hours earlier in `9f0fcee` — `CONTRIBUTING.md`'s "The honest state of the game build" and
`docs/DEVELOPING.md`'s "From your own disc to a buildable ELF — the missing step" — which said plainly that
`./build.sh recomp` starts from files produced once, by hand, on one machine, and that the sequence was not written
down. Proposed rulings are numbered from **R230** (§4).

## 1. What was built

| # | Thing | Commit |
|---|---|---|
| 1 | `decrypt_apache.main(game, out)` and `dnas_selfdecrypt.decrypt(d, variants)`: the two research scripts become callable, with the disc tree, the output folder and the four cipher addresses passed in | `2ad7eed` |
| 2 | `scripts/disc_to_elf.sh` / `python -m tools_py.disc_to_elf` — the command; `tools_py/disc_to_elf_expected.json` — what the r0001 disc produces; `tools_py/tests/test_disc_to_elf.py` — 43 cases | `41eb046` |
| 3 | The three values the from-nothing run measured for the first time, flushed progress output (a redirected stdout showed nothing for eight minutes) and the two "about N minutes" hints replaced by what was measured | `47b03a6` |
| 4 | The docs: `docs/DEVELOPING.md`'s section rewritten as the recipe (and its `unhandled=0` row corrected), `CONTRIBUTING.md`'s paragraph and table row, `README.md`'s developer block given the missing first line, and this record | the commit that carries this file |

### 1.1 The command

```
bash scripts/disc_to_elf.sh "<path to your SOCOM II ISO>" [--out game] [--check] [--force] [--stages ...]
```

Four stages, in order, each skipped when its output is already on disk and already right:

| # | stage | reads | writes | how |
|---|---|---|---|---|
| 1 | `extract` | the ISO | `<out>/disc/` (349 files, 4.1 GB) | a plain ISO9660 reader in `disc_to_elf.py` (the primary volume descriptor, two truncation checks and the extraction, around `iso_lbn.parse_dir`, which already walked the directory records for the CD-read annotator) |
| 2 | `dnas` | `OVERLAY/REL/DNAS.BIN` | `DNAS.dec.bin`, `DNAS.blocks.json` | `dnas_selfdecrypt.decrypt`: the overlay's self-encrypting code blocks, each run through its own cipher under Unicorn |
| 3 | `overlays` | `RUN/RAW/APACHE00.ZDB` | `<out>/overlays/{ftscore,zsealetc}.bin` | `decrypt_apache.main`: the retail loader's own decryption code under Unicorn, then `zlib.decompress` |
| 4 | `elf` | the loader + both overlays | `<out>/overlays/socom2_game.elf` | `make_overlay_elf.build`, with the same `--loader-text-end=recomp/loader_text_end.txt` `build.sh recomp` passes |

Why a bash wrapper around a Python module rather than one or the other: the logic is Python because the ISO reader, the
hashing and the two research scripts are (and because `unittest` can then drive every stage in-process, with no
subprocess and no disc); the documented command is a `bash scripts/*.sh` because that is the shape of the two commands
a newcomer already types (`scripts/bootstrap_windows.sh`, `./build.sh`) and because the wrapper is the one place that
has to find `python` under either name. The wrapper is eleven lines and `python -m tools_py.disc_to_elf` is equivalent.

### 1.2 What it verifies, and what it refuses

Against `tools_py/disc_to_elf_expected.json`: `SCUS_972.75`'s sha256 **before** 4 GB is written; `DNAS.BIN`'s and
`APACHE00.ZDB`'s before they are decrypted; `APACHE00.ZDB`'s entry table (`ftscore` 855920, `zsealetc` 691792); the
number of encrypted DNAS blocks and the plaintext's digest; both overlays' sizes and digests; the build id
`SOCOM 2 r0001 17:22:21 Oct 11 2003` in the decrypted `ftscore.bin` and again in the merged ELF; and the ELF's size,
sha256, entry point and segment count. A value the file does not hold yet is recorded and said so; a value that
disagrees is a refusal that names both sides and says not to edit the record to make it pass.

| exit | when | the taxonomy row |
|---|---|---|
| 66 | the path is not a file | `kDiscNotFound` |
| 67 | not an ISO9660 image; a logical block that is not 2048; no `SCUS_972.75`; a boot ELF that is not r0001's; a `DNAS.BIN` or `APACHE00.ZDB` that is not the recorded one; a ZDB entry table that differs | `kDiscNotR0001` |
| 68 | the merged ELF's size, digest, entry point, segment count or build id is wrong | `kElfMissing` ("missing or damaged") |
| 2 | no Unicorn (with the `pip install` line), no python, a bad argument or an unknown stage | none — the shape `build.sh` uses for "your machine is missing something" |
| 1 | a truncated image (the descriptor's size against the file's, and every file's extent against the file's end), an output the decryption never wrote, or any recorded value that disagrees | `kFailed` |

The numbers come from `tools_py/exit_codes.py`, which parses `ps2x/exit_codes.h`, so none of them is copied here.

## 2. The from-nothing run

2026-09-21, 17:41-18:10, in `C:\projects\wt-disc` under the loop lock (`disc-agent`, purpose recorded).
Nothing was pre-existing: no `game/` at all, no `tools/`, no build tree, no `recomp/output`. The input was the owner's
own `C:\projects\socom_pc\game\SOCOM II - U.S. Navy SEALs (USA).iso`, opened read-only and never written; the main
tree was not built in, not written to, and only read. The transcript of each step is in the session's scratchpad; the
numbers below are from `TIMINGS.txt` and the step logs.

| # | step | wall | what it printed |
|---|---|---|---|
| 0 | `bash scripts/bootstrap_windows.sh` | 9 s, then **it failed** (§5 finding 1) and was finished by hand | `clang version 23.1.0`, `cmake version 4.4.3`, `ninja 1.13.2` |
| 1 | `bash scripts/disc_to_elf.sh "<the ISO>"` | **483 s** | `extract: ... volume 'SOCOM_II', 349 files, 4173 MB` / `extract: SCUS_972.75 is the r0001 boot ELF` / `extract: 349 files written, 0 already there` (8 s, 554 MB/s) / `dnas: 131 blocks, 667136 bytes` (2 s) / `overlays: ftscore.bin + zsealetc.bin written, build id 'SOCOM 2 r0001 17:22:21 Oct 11 2003'` (473 s) / `elf: game\overlays\socom2_game.elf: 4835072 bytes, 4 segments, entry 0x180008` (0.0 s) |
| 2 | the same command again | **1 s** | four "already there and matches -- skipped" lines, `extract: 0 files written, 349 already there`, `done in 0s` |
| 3 | `bash scripts/disc_to_elf.sh --check` | 1 s, exit 0 | five `ok` rows |
| 4 | `./build.sh recomp` | **273 s** | `recomp: 14882 files, unhandled=114399` (§5 finding 2) |
| 5 | `./build.sh runtime` | **983 s** | `built dist/socom2.exe` -- 236852224 bytes, and `socom_unzipped_launcher.exe` beside it |

**29 minutes from an empty worktree to `dist/socom2.exe`** (1741 s of step time: 483 + 1 + 1 + 273 + 983), on 28
cores, with the toolchain fetch and the two dependency clones inside the two build steps. Nothing in it was hand-held
except the bootstrap repair in §5.

**What it proves.** Six of the recorded values were written from the owner's 2026-09-04 hand-run chain before this run
started, so the run **verified** rather than recorded them: `SCUS_972.75`, `DNAS.BIN` and `APACHE00.ZDB` as read off
the image, `ftscore.bin` (2233472, `cf09a7fa...`), `zsealetc.bin` (1723520, `cdb3fa8e...`) and `socom2_game.elf`
(4835072, `06b83684...`, entry `0x180008`). Every one matched. The command reproduced, from an ISO and an empty
folder, byte for byte, what had only ever been produced by hand. Three values nobody had measured were recorded by
this run and are committed: `dnas.blocks` 131, `dnas.output` 667136 / `b0937163...`, `elf.segments` 4.

Independently of the digests: the 349 files the ISO9660 reader wrote are identical in name and size to the 349 in the
owner's own `game/disc/` (a `find -printf "%p %s"` diff of the two trees is empty), and that tree was extracted months
ago with a different tool. Sizes, not digests, for the 346 files this chain does not read -- hashing both trees would
have been ~8 GB of reading for a check the game's own CD reads and the gate already make (R233).

**Cost, measured:** the tree and the overlays are 4184 MB; the toolchain 1.2 GB; `recomp/output` 576 MB (14882 files);
the two build trees 1377 MB (`build-tools`) and 2107 MB (`build-clang`), plus 283 MB in `dist/`. Free space on C: fell from 22 GB to 9.1 GB (the disc tree, two dependency clones, the generated code, the objects and a 226 MB exe) over the run.

## 3. Tests

`python -m unittest tools_py.tests.test_disc_to_elf` — 43 cases, 0.3 s, no Unicorn and no disc. The reader cases build
their own ISO9660 image (a PVD, a root directory, a subdirectory to prove the walk recurses, three files) and the two
emulation stages run against fake `tools_py.decrypt_apache` / `tools_py.dnas_selfdecrypt` modules injected into
`sys.modules` — which also means the Linux workflow, which installs numpy, pillow and zstandard and not Unicorn, runs
all 43 rather than skipping them.

RED before GREEN for each refusal, by planting the wrong value: a truncated image both ways round, a non-ISO file, a
missing path, a 800-byte logical block, a boot ELF of another revision, an image with no `SCUS_972.75`, a `DNAS.BIN`
that is not the recorded one, a ZDB entry table that differs, an overlay that decrypts to something without the build
id, an overlay the decryption never wrote, a planted wrong ELF digest, a planted wrong entry point. Idempotence is
asserted for all three re-runnable stages by counting calls into the fakes and by an `os.utime` marker on the ELF: a
second call decrypts nothing, rebuilds nothing, and still verifies. `--force`, `--check`, a partially written file
re-extracted by size, and that the shipped expectations file's boot-ELF digest equals the launcher's
`kSocom2R0001ElfSha256` (a test that fails if the two ever drift) are covered too.

The whole Python suite after the change: `Ran 1712 tests ... OK` (1669 before, 43 new), twice -- `skipped=109` before the from-nothing run and `skipped=85` after it, because this worktree then had a `game/` and the two dozen cases that need the disc ran too.

## 4. Rulings made on the owner's behalf

**R230 — the expectations file holds sha256 digests of whole game files, in the tree.** `tools_py/disc_to_elf_expected.json`
records the digests and sizes of `SCUS_972.75`, `DNAS.BIN`, `APACHE00.ZDB`, both overlays and the merged ELF. A digest
is a fact *about* the disc and cannot be turned back into a byte of it, and the project already does exactly this:
`launcher::kSocom2R0001ElfSha256` has been the pinned digest of `SCUS_972.75` since 2026-09-17 and a new test fails if
the two ever disagree. The alternative — a git-ignored file — would mean a stranger's first run verifies nothing at
all, which is the whole point of the command. Cost: anyone can now tell whether an ISO they hold is this disc without
having the disc. The owner can overturn this by moving the file to `.gitignore` and accepting that first runs only
record.

**R231 — a difference in the image's *shape* is a note, not a refusal.** `disc.files`, `disc.manifest_sha256` (one
digest over "`<path> <size> <lbn>`" a line) and `disc.volume_sectors` are recorded, and a run whose image differs
prints two NOTE lines and goes on. A re-built or differently padded dump of the same disc holds the same bytes at other
LBNs, and the three files this chain reads are each pinned by digest, so refusing would turn away discs that build the
game correctly. Cost: a rebuilt ISO that happens to hold the right three files and a wrong fourth is not caught here
(the launcher's own disc check and the gate are downstream). The owner can overturn this by making the manifest a
refusal.

**R232 — the four DNAS cipher addresses are recorded rather than derived.** `dnas_selfdecrypt.py`'s research path
derives the four (key table, cipher core) pairs from `game/analysis/DNAS.BIN.decomp.c`, a Ghidra decompilation no
contributor has and which is not in the tree. Without recording them the second stage could not run on any other
machine, so the command passes the four pairs from the expectations file — after `DNAS.BIN`'s digest has been checked,
so the addresses can never be applied to bytes they do not describe. Cost: if a future disc revision is ever supported,
its four pairs have to be derived once with Ghidra and recorded. The owner can overturn this by requiring the
decompilation, which would make the chain un-runnable for a stranger.

**R233 — the extracted tree is verified by size against the image's own directory records, not re-hashed.** The
extraction skips a file that is already there at exactly the right size, and a second run therefore costs seconds
rather than the ~8 GB of reading a full re-hash would cost. The bytes come from the image by LBN, so a wrong size is
the only thing that can differ short of a damaged filesystem, and the three files that matter are hashed anyway. Cost:
a file silently corrupted in place, at the same size, after extraction is not detected by the command (the game's own
CD reads and the gate are what see that). The owner can overturn this with a `--recheck` pass.

**R234 — `CONTRIBUTING.md` now says the game build is supported, on the evidence of one disc image on one machine.**
The paragraph and the table row were rewritten to say the chain works and to name the command; the same paragraph says
in as many words what is *not* proven — any other image of the revision, and Linux, where `scripts/build_linux.sh`
has never been run from an ISO. The alternative was to keep saying "not a documented, runnable step" until a second
person had run it, which would leave the repository claiming less than it can do and give a newcomer nothing to try.
Cost: if a second r0001 dump differs in a way the digests catch, the first stranger to try meets a refusal instead of
a build — which is why the refusal names both values and asks for an issue. The owner can overturn this by reverting
the two documents to the 2026-09-21 wording in `9f0fcee`.

**R235 — the from-nothing run reused the toolchain archives already in the main tree's bootstrap cache.**
`scripts/bootstrap_windows.sh` downloads three archives pinned by version and sha256; the run copied them out of
`C:\projects\socom_pc\tools\.bootstrap\` instead of fetching 245 MB again over the owner's connection. Bootstrap
re-hashes every archive and refuses a mismatch, so the installed toolchain is bit-identical to a fresh download and
the step is still a real test of the extraction half. Cost: the *download* half (the URLs, the retries) was not
exercised by this run; it was exercised on this machine at 01:56 the same day. The owner can overturn this by asking
for a run with an empty cache.

## 5. Findings for the controller

**1. `scripts/bootstrap_windows.sh` cannot finish in a second working tree on this machine — its final `mv` is
refused.** Reproduced three times: `mv: cannot move '/c/projects/wt-disc/tools/llvm-mingw.new' to
'/c/projects/wt-disc/tools/llvm-mingw': Permission denied`, with the destination absent, no reparse point, no
read-only bit and no reserved name anywhere in the tree (9314 entries; cmake's 2900 failed the same way, ninja's
single file succeeded). PowerShell's `Rename-Item` on the identical path succeeded immediately, so this is Git Bash's
`mv` on a large freshly written directory, not a permission the script is missing. It stopped the from-nothing run at
step 0 and a stranger on Windows can meet it. The obvious repair is to stop renaming: extract into `$TOOLS/$name`
after removing it (the `.new` directory only exists so a failed extraction cannot leave a half toolchain, which a
`.part`-style marker file would also give), or fall back to `cp -r` when the `mv` is refused. Not fixed here: it is
another sprint's file, the same script has worked in the main tree on this machine, and a fix wants its own test.

**2. `./build.sh recomp` prints `unhandled=114399`, and `docs/DEVELOPING.md` said the line that means success is
`unhandled=0`.** Measured twice on 2026-09-21 — 14882 files and 114399 `unhandled-instruction` lines in
`recomp/recomp_run.log`, identically in the main tree (17:07, the controller's own run) and in this worktree (17:54,
from an ELF this chain built from the ISO) — so the number is a property of the recompiler and the disc, not of
anything here, and the exe the gate passes 3/3 on is built from exactly this generated code. The row in the
five-command table has been corrected to say what it prints and why it is not a failure. Someone should decide what
the real bar is: a count that must not grow, a whitelist, or nothing at all.

**3. `tools_py/decrypt_apache.py` still stops with a bare `SystemExit("step1 failed")` when a decryption step
returns an error.** The chain's own refusals all carry an exit code and a sentence; this one path does not, because
it is inside the research script. It cannot be reached with the recorded disc (every input is digest-checked first),
so it is a cosmetic gap, but it is the one place a stranger could get a message that does not say what to do.

## 6. What a stranger still needs

Python 3 and `pip install unicorn` (2.1.4 measured); about 4.2 GB of free disk for the tree and the overlays, on top of
the toolchain's 1.2 GB and the build trees; their own NTSC r0001 disc image; and the minutes in §2. No 7z and no other
extractor. Nothing in the chain reaches the network.
