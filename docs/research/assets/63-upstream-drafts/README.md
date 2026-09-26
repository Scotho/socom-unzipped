# Upstream drafts for O10

Sprint 13 Task U4, 2026-09-25. These are drafts for the owner to file (`docs/HUMAN_TASKS.md` row O10). Nothing in
this folder has been posted anywhere. Filing is a public act under the owner's account, so the loop only prepares
the text (the Sprint 13 plan's Global Constraints: "Nothing that is the owner's ... is performed").

Each draft has the issue text between two horizontal rules. The notes for the owner come after the second rule and
are not meant to be posted. Every claim in the notes cites a file and line or a commit in this tree. Upstream line
numbers were read from GitHub on 2026-09-25 and are marked as such. No draft carries anything taken from the
disc's bytes. The module names, ordinals, addresses and option strings stay in research/40 and research/49.

The register is `docs/UPSTREAM.md` (2026-09-26): the bugs in a vendor's `main`, with local status and filing state.
What is not a bug is `NOT-UPSTREAM.md` here; the research on open PRs is `OPEN-PRS.md` here.

| file | for | what it is | recommendation |
|---|---|---|---|
| `issue-modload-argv-abi.md` | ran-j/PS2Recomp, issue | #244's `loadImage` starts an IRX as `_start(byteCount, rawBuffer)`, where modload passes `(argc, argv)` | **file**, with `ps2recomp-argv.patch` |
| `ps2recomp-argv.patch` | attach to the issue above | `git format-patch` output against upstream `75d729c` (applies with `git apply --check`) | attach |
| `issue-iop-printf.md` | ran-j/PS2Recomp, issue | stdio `printf`/`fdprintf` log the bare format string | **file**, with `ps2recomp-printf.patch` |
| `ps2recomp-printf.patch` | attach to the issue above | `git format-patch` output against `75d729c` | attach |
| `issue-export-table-walk.md` | ran-j/PS2Recomp, optional note | the third "#244 patch": on a second reading, upstream is right and our guard over-reads | **do not file as a bug**; optionally post the short test suggestion inside it |
| `ps2recomp-export-table.patch` | not for upstream | the guard as it ran, marked "REFERENCE ONLY" in its own comment, kept so that the choice not to propose it can be checked | do not attach |
| `keep-notes.md` | ran-j/PS2Recomp, one comment on each of ten PRs | "gated 3/3 on SOCOM II" for #231, #229, #243, #230, #237, #232, #227, #240, #241, #246, each with what we saw | post one comment per PR |
| `binexport-r5900-1.md` | google/binexport, issue | a `sync` ends `getCodeBlocks()` early, and `buildFlowGraphs` throws an NPE on the unindexed block | **file**, attach `ghidra_scripts/binexport-r5900-blocks.patch` from line 31 |
| `binexport-r5900-2.md` | google/binexport, issue | a function entered by fall-through is exported with entry block 0, and BinDiff rejects the file | **file**, and point at the patch attached to issue 1 |

**How the three PS2Recomp patches were made.** The fork never merged #244
(`docs/research/40-upstream-divergence.md:200`), so no commit in this tree carries these changes. The code as it ran
is `docs/research/assets/40-irx-differential/pr244-spike-patches.diff` (commit `2accf38d`). Its three pre-image blobs
(`e5f63a9`, `eed2b61`, `f13267f`) are the blobs of upstream's files at `75d729c`, checked with `git hash-object` on
the files fetched from GitHub. Each file section was applied to those three files in a scratch repository and
committed with a neutral comment in place of ours. Then `git format-patch -1` was run. The code lines are
byte-identical to the spike's, and only the comments differ. That is why the `From <sha>` lines are not commits in
this repository. The author line reads `Craig Smith <replace-me@example.com>` because the leak check refuses a
personal address in a tracked file. Before anyone runs `git am`, the owner puts in the identity they want upstream
to see. `git apply` ignores the line.

**Sources.** The audit's rows: `docs/audits/2026-09-25-project-audit/external.md:34` (X9, the three #244 patches),
`:35` (X10, the ten KEEP picks), `:44-45` (X19/X20, BinExport), summarised as E5 in
`docs/audits/2026-09-25-project-audit.md:139`. The triage these follow: `docs/research/63-upstream-triage-2026-09-25.md`.

**Not covered here.** The three picks Sprint 13 U7 took from open PRs #221, #223 and #224 (`ab6d7ff3`). Those were
adapted rather than taken as written, so a note on them would say what we changed. That is a later draft if the owner
wants one.
