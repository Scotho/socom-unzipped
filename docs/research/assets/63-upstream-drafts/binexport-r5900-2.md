# Draft issue for google/binexport: a function entered by fall-through gets no entry block

> Draft for the owner to file (docs/HUMAN_TASKS.md row O10). Nothing here has been posted. The text between the two
> rules is the issue body; the notes after it are for the owner.

---

**Title:** [Ghidra] A function whose entry is reached only by fall-through is exported with entry block index 0, and
BinDiff rejects the file ("flow graph already attached")

**Setup.** The same as our other report: Ghidra 11.0.3, BinExport `v12-20240417-ghidra_11.0.3`, the
ghidra-emotionengine-reloaded extension v2.1.16, `r5900:LE:32:default`, with the function table imposed by script
(explicit bodies). We saw it on R5900. Nothing in it looks processor-specific.

**The instruction.** None in particular. What matters is the function boundary: the last instruction of function A is
not a branch, so execution falls through into function B's first instruction, and nothing references B's entry.
Ghidra's `BasicBlockModel` therefore does not start a block at B's entry. The model block that contains it starts
inside A.

**What BinExport emits.** In `buildFlowGraphs` (lines 790-847 on `main` at `087a035`), B's blocks come from
`getCodeBlocksContaining(B.getBody())`. None of them starts at B's entry, so `setEntryBasicBlockIndex` is never
called and the proto's default, **0**, is written. The flow graph also lists the straddling block, which starts in
A and so belongs to A's flow graph too. BinDiff 8 then refuses the export:

```
AttachFlowGraph: flow graph already attached <address>
```

The `assert flowGraph.getEntryBasicBlockIndex() > 0;` at line 847 would not catch it either. Assertions are off in a
normal Ghidra run, and index 0 is a valid block index for the first block of the program.

**What is right.** A function's entry always starts a basic block in the export: split the model block at the entry.
A flow graph lists only blocks inside its function. If a function still has no entry block, skip its flow graph and
log it, rather than write index 0.

**Our change.** The same `BinExport2Builder.java` patch as our other report, attached. Each model block is
intersected with the function's body and split at the function's entry, and a function with no entry block gets no
flow graph and a counter in the log. On two EE programs (about 9,700 and 14,900 functions) the counter reads 0 after
the patch, and BinDiff 8 accepts both exports. The clip also cut 61 block tails at a function end on the larger
program.

**Minimal reproduction** (not yet run in this form). Raw blob, any MIPS language: at `0x1000` `addiu v0, zero, 1`
(`0x24020001`), and at `0x1004` `jr ra` / `nop` (`0x03E00008`, `0`). Create function A = `[0x1000, 0x1003]` and
function B = `[0x1004, 0x100B]` by script with explicit bodies. Put no reference to `0x1004`. Export, and read B's flow
graph: its `entry_basic_block_index` is 0, and the block it lists starts at `0x1000`.

Related: #76 ("BinExport should never export multiple functions at the same address") is a neighbour, not the same
bug.

---

## Notes for the owner (not part of the issue)

**Evidence in our tree.**
- The defect as measured: `docs/research/49-bindiff-crosscheck.md:100-102` ("entered by fall-through, with no reference
  to the entry ... got no entry block (index 0 by default), and BinDiff refused the export").
- The patch's effect: `docs/research/49-bindiff-crosscheck.md:103-108` (demo and r0001 both "no entry block 0"; r0001
  "block tails clipped at a function end 61"). The function counts: `:134-135` (the table in §1.3: 9,703 and 14,879
  rows).
- Why functions are entered by fall-through at all: our function table is imposed from our recompiler's map, not
  discovered by Ghidra (`docs/research/49-bindiff-crosscheck.md:127-129`, `ghidra_scripts/BinExportBoth.java`).
- The patch: `ghidra_scripts/binexport-r5900-blocks.patch`, from line 31 on (lines 1-30 are our header, with a
  disc-derived address on line 10). It is the same file as issue 1's. File the two issues separately, and attach the
  patch to one of them, referenced from the other.
- The `main` line numbers (790-847) are from `BinExport2Builder.java` fetched at `087a0353` on 2026-09-25. They are not
  in our tree.

**Kept out of the draft.** The address in BinDiff's message (research/49 line 102 has it) and the executables' names.
