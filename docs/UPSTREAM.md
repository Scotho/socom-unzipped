# Upstream -- the register of bugs to report, by vendor

Class L (owner: controller; `docs/DOC_MAINTENANCE.md` §3). Opened 2026-09-26 on the owner's word: "Please create a
known archive of these issues for future collection and sending by vendor." **What qualifies:** a defect
reproducible in the vendor's `main` as it stands, each located at `path:line` on that `main` by
`gh api repos/<o>/<r>/contents/<path>?ref=main`. **Three kinds, three places:** bugs in a vendor's `main` are here;
feedback that is not a bug (notes to PR authors, a draft where upstream is right, our own divergence) is
`docs/research/assets/63-upstream-drafts/NOT-UPSTREAM.md`; research on what waiting upstream PRs would bring is
`docs/research/assets/63-upstream-drafts/OPEN-PRS.md`. The drafts stay in that folder (its `README.md` orders them);
the owner's row is `docs/HUMAN_TASKS.md` O10.

## 0. The rule, and what every row shares

**The owner's preference, as the rule (2026-09-26).** A patch we are confident in is applied to our local fork
whether or not it is filed. A patch that is not applied says why, in its row. Filing is the owner's act, by vendor,
in batches, when the owner chooses; the loop drafts and verifies, and never posts, comments or files.

- **Status of every row: not filed** (the owner, 2026-09-26: nothing pushed today). A filed row gets its ticked box,
  URL and date in its vendor's "How to file" block.
- **AI assistance.** Every draft was written with AI assistance (Claude agents in this project's loop), from
  measurements made in this tree; each draft's evidence lines name them. The two PS2Recomp patch files also carry a
  `Co-Authored-By: Claude ...` and a `Claude-Session:` trailer in their headers, so a patch attached as it stands
  discloses that by itself. The `Claude-Session:` trailer is a link to a private session on claude.ai: strip it
  before attaching (`git apply` ignores the header). How to disclose the rest -- keep the co-author line, say it in the issue text, or
  neither -- is the owner's decision, per vendor. Each vendor's section records what the vendor says on the subject.
- **Nothing disc-derived goes upstream.** Module names, ordinals, addresses and option strings stay in
  `docs/research/40-upstream-divergence.md` and `docs/research/49-bindiff-crosscheck.md`.
- **The vendors' `main`, read 2026-09-26 15:59Z:** `ran-j/PS2Recomp` `main` = `75d729c` (#244, the IOP emulator,
  merged 2026-09-20); `google/binexport` `main` = `087a035` (2026-09-15). Our PS2Recomp fork is upstream `14b1e5c`
  (#214), vendored as `8736759`, and has never merged #244 (research/40 §1 and §8).
- **Local status words.** "applied in our tree at X"; "applied in a spike only (where), not in the tree";
  "not applicable to our tree (why)"; "not applied (why)". Each was checked against `git log` and `git ls-files` on
  2026-09-26, not taken from the drafts' README.

## 1. ran-j/PS2Recomp

**Stance on AI-assisted reports: no stated policy** (read `README.md`, the root listing and `.github/` on
2026-09-26: there is no `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` or `.github/ISSUE_TEMPLATE/`, and the README says
nothing on AI or on contributions). GPL-3.0, no CLA. A sign of the community's mood, recorded without a judgement:
the fork `Sorachi00/PS2Recomp-Drakengard` says in its README "Usage of AI agents is prohibit. You may use AI to
gather info and so, but you need to understand what you are writing." (`README.md:10`,
read 2026-09-26; research/67 §2). It is a fork's rule, not upstream's.

**The files at `main`.** `git hash-object` of the three #244 files fetched at `main` gives `e5f63a9`
(`iop_emulator.cpp`), `eed2b61` (`iop_stdio.cpp`) and `f13267f` (`iop_imports.cpp`): the pre-image blobs of the
drafts' patches, so both patches below apply to `main` as it stands.

| # | item | the defect at `main` (`75d729c`) | draft / patch (`63-upstream-drafts/`) | local status | confidence | recommendation | status |
|---|---|---|---|---|---|---|---|
| P1 | IRX `_start` ABI | `ps2xIOP/src/emulator/iop_emulator.cpp:617-627`: `loadImage` copies the argument buffer and calls `callFunction(module.entry, argumentSize, args, ...)`, i.e. `_start(byteCount, rawBuffer)` where modload passes `(argc, argv)` | `issue-modload-argv-abi.md` / `ps2recomp-argv.patch` | **applied in a spike only** (`docs/research/assets/40-irx-differential/pr244-spike-patches.diff`, `2accf38d`, on #244 in the IRX differential harness), **not in the tree**: our fork does not carry the code it patches (`git ls-files` finds no `iop_emulator.cpp`; no commit merges #244) | high: 989snd's eighteen unknown-argument errors went with it (research/40:225-229); the draft's reproduction is unrun | **file**, with the patch | not filed |
| P2 | IOP `printf` | `ps2xIOP/src/emulator/imports/iop_stdio.cpp:24-29` (`logString` logs the string read from IOP RAM as it is), used by `printf` at `:33-34` and `fdprintf` at `:51-52`: the format string is logged unrendered and its length returned | `issue-iop-printf.md` / `ps2recomp-printf.patch` | **applied in a spike only** (the same diff, `2accf38d`), **not in the tree**, for the same reason (no `iop_stdio.cpp` in our fork) | high: every 989snd error line was read through it (`docs/research/assets/40-irx-differential/results_run_20260922_150258.md`); the reproduction's expected values are hand-computed, unrun | **file**, with the patch | not filed |

Under the owner's rule: both are confident, and the only reason they are not in our fork is that our fork has no
#244 code to patch. If the fork ever takes #244 (research/40 §8 holds it back), P1 and P2 go in with that merge.

### 1.1 How to file (PS2Recomp)

1. Put the identity to show upstream in each patch's `From:` line (a placeholder, because the leak check refuses a
   personal address in a tracked file), and decide on the trailers (§0). `git apply` ignores the header; `git am`
   uses it.
2. P1: the issue body is the text between the two rules of `issue-modload-argv-abi.md`; attach
   `ps2recomp-argv.patch`. The notes after the second rule are not posted. Optionally run the reproduction first.
3. P2: the same from `issue-iop-printf.md`, attaching `ps2recomp-printf.patch`. Run the reproduction, or drop its two
   `cpu.gpr[2]` expectations, which were computed by hand.
4. If `main` has moved past `75d729c`, re-locate the lines and re-run `git apply --check` before filing.

| done | item | filed URL | date |
|---|---|---|---|
| [ ] | P1 argv issue + `ps2recomp-argv.patch` | | |
| [ ] | P2 printf issue + `ps2recomp-printf.patch` | | |

## 2. google/binexport

**Stance on AI-assisted reports: no stated policy** (read `README.md`, `CONTRIBUTING.md` and `.github/` on
2026-09-26; there is no `CODE_OF_CONDUCT.md` and no `.github/ISSUE_TEMPLATE/`). **A CLA applies to code**: "Before
we can use your code, you must sign the Google Individual Contributor License Agreement (CLA)" (`CONTRIBUTING.md:4-6`);
the same file says the signature may come after review. Apache-2.0. Our reading: an issue with a diff attached is a
report; if they ask for a pull request, the CLA is the owner's to sign.

The file is `java/src/main/java/com/google/security/binexport/BinExport2Builder.java` at `main` = `087a035`.

| # | item | the defect at `main` (`087a035`) | draft / patch | local status | confidence | recommendation | status |
|---|---|---|---|---|---|---|---|
| B1 | `sync` ends the block walk | `:716` indexes the blocks of the program-wide `bbModel.getCodeBlocks(monitor)`; `:790` walks each function's `getCodeBlocksContaining(func.getBody(), ...)`; `:798` unboxes `basicBlockIndices.get(bbAddress)` into an `int`, which throws when the first walk stopped early (at an R5900 `sync`) | `binexport-r5900-1.md` / `ghidra_scripts/binexport-r5900-blocks.patch` (`f9237f91`), from line 31 | **applied in a spike only**: the patched `BinExport.jar` of the Sprint 12 research install (Ghidra 11.0.3, EE extension v2.1.16), outside this repository (research/49 §1.2), **not in the tree**. The tree tracks the diff, no BinExport source or build; this host's Ghidra 12.1.3 has no BinExport extension, so no pipeline runs with the patch today. KNOWN's BinDiff row (issue #58) owns building BinExport `main` on 12.1.3; the patch is rebased and applied there | high for the defect (the NPE; 119,015 blocks exported with the patch where the walk found 4,818); medium for the patch as upstream's fix (it drops a flow edge whose target is outside the function, a policy choice) | **file**, the patch attached | not filed |
| B2 | fall-through entry | `:799-800` set the entry block only when a model block starts at the function's entry; a function entered by fall-through has none, so the proto's default 0 is written, and `:847`'s `assert ... > 0` is off in a normal run. BinDiff 8 then refuses the export | `binexport-r5900-2.md` / the same patch | as B1 | high: "no entry block 0" on both programs after the patch, and BinDiff 8 read both exports (research/49 §1.2) | **file**, pointing at B1's attachment | not filed |

The cause of B1's early stop (Ghidra's `BasicBlockModel` or the EE extension's `sync` flow) was never established;
that open question is in `NOT-UPSTREAM.md`, not here.

### 2.1 How to file (BinExport)

1. File B1 and B2 as two issues. Each body is the text between the two rules of its draft; the notes after it are not
   posted.
2. Attach `ghidra_scripts/binexport-r5900-blocks.patch` **from line 31 on** (the `diff --git` line) to B1 only, and
   point B2 at it. Lines 1-30 are our header, and one of them carries an address from the disc's executable.
3. The diff is against the tag `v12-20240417-ghidra_11.0.3`, not `main`; say so, and expect to rebase it if a pull
   request is asked for (then the Google CLA, above). Both reproductions in the drafts are unrun.

| done | item | filed URL | date |
|---|---|---|---|
| [ ] | B1 issue + the patch from line 31 | | |
| [ ] | B2 issue, pointing at B1's patch | | |

## 3. Keeping this file true

A row enters only with its `path:line` on the vendor's `main`, read that day. A filed item gets its box ticked, its
URL and date, and its status becomes "filed". A patch that enters our tree changes its row's local status to the
commit. When a vendor's `main` moves, its rows are re-located (a fixed defect leaves the register with the fixing
commit named) and each patch is re-checked with `git apply --check`.
