# Draft issue for google/binexport: a `sync` ends the program-wide block iteration, and the export dies with an NPE

> Draft for the owner to file (docs/HUMAN_TASKS.md row O10). Nothing here has been posted. The text between the two
> rules is the issue body; the notes after it are for the owner.

---

**Title:** [Ghidra] Export throws NullPointerException in `buildFlowGraphs` when `getCodeBlocks()` returns fewer blocks
than the functions contain (R5900 `sync`)

**Setup.** Ghidra 11.0.3, BinExport release `v12-20240417-ghidra_11.0.3`, the ghidra-emotionengine-reloaded extension
v2.1.16, language `r5900:LE:32:default`. The program is a PlayStation 2 EE executable whose function table is created
by a script, with explicit bodies, before analysis runs.

**The instruction.** R5900 `sync` (encoding `0x0000000F`, MIPS `SYNC`), which is ordinary straight-line code in
EE programs.

**What BinExport emits.** Nothing: the export fails. `buildBasicBlocks` indexes the blocks that the program-wide
`bbModel.getCodeBlocks(monitor)` returns (line 716 on `main` at `087a035`). `buildFlowGraphs` then walks each
function's blocks with `bbModel.getCodeBlocksContaining(func.getBody(), monitor)` (line 790) and unboxes
`basicBlockIndices.get(bbAddress)` into an `int` (line 798). On our program, the program-wide iteration stopped at
the first `sync`. It returned 4,818 blocks, while the functions' bodies hold 119,015. So the first function past that
point looks up a block that was never indexed, `get` returns `null`, and the unboxing throws:

```
NullPointerException at BinExport2Builder.buildFlowGraphs(BinExport2Builder.java:318)   (line number at the v12 tag)
```

**What is right.** Build the block index from the same iteration the flow graphs use: per function, with
`getCodeBlocksContaining(func.getBody())`. Or at least do not unbox a missing index. Then the export no longer
depends on two different iterators agreeing. We did not establish why the program-wide iterator ends at `sync`
(Ghidra's `BasicBlockModel` or the EE extension's SLEIGH flow for that instruction). BinExport's crash follows from
the assumption, whatever the cause.

**Our change.** It is a patch to `BinExport2Builder.java` against the v12 tag, attached. It builds blocks per
function (each model block intersected with the function's body), keyed by start address. With it the same program
exports 119,015 blocks and 9,713 flow graphs, and BinDiff 8 reads the result. The same patch also carries the fix for
the second issue we are filing (a function entered by fall-through gets no entry block). The patch drops a flow edge
whose target is outside the function, which is a policy choice you may not want. On a second, larger program it
dropped 68 edges of 159,294 blocks.

**Minimal reproduction** (not yet run in this form; we saw it on a commercial executable). Load a raw little-endian
blob as `r5900:LE:32:default` with three small functions in a row, the middle one containing a `sync` (`0x0000000F`)
before its `jr ra`. Create the three functions by script with explicit bodies. Then compare the number of blocks from
`BasicBlockModel.getCodeBlocks()` with the sum over functions of `getCodeBlocksContaining(body)`, and run the export.
If the counts differ, the export throws as above.

On `main`: the Ghidra 12.x compatibility commit and the two `BinExport2Builder` fixes since the tag do not change
these lines (checked at `087a035`, 2026-09-15). The two open issues that mention MIPS or sync (#76, #91) are about
other things.

---

## Notes for the owner (not part of the issue)

**Evidence in our tree.**
- The defect as measured: `docs/research/49-bindiff-crosscheck.md:97-99` (the stop at the first `sync`; "4,818 blocks
  where the functions hold 119,015"; the NPE at `BinExport2Builder.buildFlowGraphs(…:318)`).
- The patch's effect: `docs/research/49-bindiff-crosscheck.md:103-108` (demo "blocks 119015, flow graphs 9713";
  r0001 "edges dropped (target outside the function) 68" of 159,294 blocks). The setup: `:76-79` and `:83-85`.
- The patch: `ghidra_scripts/binexport-r5900-blocks.patch` (committed in `f9237f91`). Attach it from line 31
  (`diff --git ...`) on. Lines 1-30 are our header, and line 10 carries an address from the disc's executable, which
  must not go upstream. The diff is against the v12 tag, not `main`, so it will need rebasing if they ask for a PR.
  `docs/audits/2026-09-25-project-audit/external.md:44` (finding 19) says the same.
- Not reported before: `docs/audits/2026-09-25-project-audit/external.md:45` (finding 20: the search found only #76
  and #91). Re-checked 2026-09-25 with `gh api "search/issues?q=repo:google/binexport+sync+OR+r5900+OR+mips+OR+fallthrough"`:
  #76 (open, "BinExport should never export multiple functions at the same address") and #91 (closed, a
  Ghidra 10.1 packaging issue).
- The `main` line numbers (716, 790, 798) are from `BinExport2Builder.java` fetched at `087a0353` on 2026-09-25. They
  are not in our tree.

**Kept out of the draft.** The address of the first `sync` and the name of the executable. The block counts are
counts, not bytes, and the same counts are already public in research/49.
