# Draft for ran-j/PS2Recomp: the export-table walk and a function at module offset 0

> Draft for the owner (docs/HUMAN_TASKS.md row O10). Nothing here has been posted.
>
> **Recommendation: do not file this one as a bug.** research/40 lists it as the third of the "three #244
> patches". Reading it again for this draft, upstream's behaviour matches the IOP's, and our patch is the riskier of
> the two. The owner can file the short note below as a test suggestion, or skip it. Either choice closes O10's third
> item.

## What upstream does

`IopImportRegistry::registerExportTable` in `ps2xIOP/src/emulator/imports/iop_imports.cpp` at `main` = `75d729c`
walks the function words after the 20-byte header and stops at the **first zero word** (line 120,
`if (function == 0u) break;`). It is reached from loadcore's `RegisterLibraryEntries` (exports 6 and 10,
`iop_loadcore.cpp:39-41`), which a module calls from its own `_start`, after it has been relocated.

## What the IOP does

An IRX export table is a header followed by function addresses and ends with a single zero word. Upstream's own
test builds one that way (`ps2xIOP/tests/iop_import_tests.cpp:116-121`, the terminator at `table + 20`). Once a
module is relocated, a function at module offset 0 has the value `base + 0`, which is not zero. So the first-zero
rule is correct for every table registered after relocation.

## What our patch did, and why it is not proposed

During our IRX differential run (research/40 §9), one module's table had a function at module offset 0. We changed
the walk so that it ends at **two** consecutive zeros, as a guard against the case where that entry reads 0. The
note records that, in the event, the table was correctly relocated and the patch "was not the fix". It changed
nothing we could observe. It also reads past a correctly terminated table whenever the word after the terminator is
non-zero, and would register that word as an export.

## The note the owner could file instead (optional)

> **Title:** ps2xIOP: a test pinning the export-table terminator for a function at module offset 0
>
> `registerExportTable` ends a table at its first zero word, which is the IOP's format. One edge is worth a test: a
> module that exports a function at offset 0 has a table entry of `base + 0`. This is fine after relocation, but it
> would end the table early if the table were ever registered from an unrelocated image. A test that loads a
> synthetic relocatable IRX with an offset-0 export, then imports an ordinal after it from a second module (as
> `writeExportProviderIrx` / `writeExportConsumerIrx` do in `iop_emulator_tests.cpp`), would pin the behaviour.
> We hit this while debugging, and the table turned out to be fine. No code change is suggested.

## Evidence in our tree

- `docs/research/40-upstream-divergence.md:232-234`: patch 3, "the walk stopped at the first zero word. Kept as a
  guard (two consecutive zeros end the table); in the event the ... table was correctly relocated ... and this patch
  was not the fix".
- The patch as it ran: `docs/research/assets/40-irx-differential/pr244-spike-patches.diff`, the first file section
  (`iop_imports.cpp`), committed in `2accf38d`. Its pre-image blob `f13267f` is upstream's `iop_imports.cpp` at
  `75d729c` (checked 2026-09-25 with `git hash-object`).
- `ps2recomp-export-table.patch` in this folder: `git format-patch` output, code identical to the spike's section,
  with a comment that says "REFERENCE ONLY, not proposed". It exists so that the choice not to propose it can be
  checked, and it should not be attached.
- Upstream's line numbers above (`iop_imports.cpp:120`, `iop_loadcore.cpp:39-41`, `iop_import_tests.cpp:116-121`) were
  read from those files at `75d729c`, fetched with `gh api .../contents/<path>?ref=75d729c` on 2026-09-25. They are not
  in our tree, because the fork never merged #244 (`docs/research/40-upstream-divergence.md:200`).

The module, the ordinal numbers and the function's name come from the disc's IRX. They are in research/40, not here.
