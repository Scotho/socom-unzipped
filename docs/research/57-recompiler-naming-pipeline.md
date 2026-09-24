# 57. The recompiler's naming pipeline, end to end

Date: 2026-09-24. Sprint 12 research wave, question 12 of the handoff §4
(`docs/superpowers/plans/2026-09-24-sprint-12-cloud-handoff.md`). Tests the spec's S12-R4 default (Goal 6, D6:
"the csv plus the sidecar are the one home of a name"). Read-only: the recompiler's sources, the tracked
`recomp/` inputs, the synthetic ELF and the proposals files under `game/`. No recompiler was built or run,
`recomp/output` is not on this machine, and nothing tracked was changed except this note and its script.

**The one-line answer: the toml's names stop at the stub list because `ps2_recomp` never names a function from
it. A stub's `name@addr` selects the runtime handler (`ps2_recompiler.cpp:1165-1181`); the C identifier comes
from the function's own name, and that name is `sub_*` because the recompiler's JAL scan outlives Ghidra's row
(6,750 times). The csv route (write the name into the csv's `Name` column) cannot carry a name without changing
the code: in this recompiler a real name is semantic. Written into the csv, Goal 1's 485 names change 237
functions' extents and turn 19 functions into HLE stubs, including 17 `sceVu0*` stubs that `daa1eda`
removed, at the same addresses, because they broke rendering. Goal 6's 338 names drop 2 functions and cut 3 bodies short where a branch
still jumps into the cut part. The smallest pure change is in the recompiler: `ps2_recomp` reads the sidecar's
`Address,Name` and uses it only where it builds the output name (`makeName`, `ps2_recompiled_stubs.h` follows).
Every function keeps its csv name for discovery, so a rename is only a rename. This reaches the same 823
functions as the csv route (485 + 338). Neither route can name the 41 toml addresses where the recompiler emits
no function.**

Every number below names the command that produces it:

```
# A -- the pipeline replayed, the toml census, the proposals, the hazards, the CHCR check (blocks [A]..[J])
python tools_py/research/symbols/toml_names.py

# B -- the tracked csv is already its own fix_ghidra_csv output (content identical; line endings differ)
python tools_py/fix_ghidra_csv.py recomp/socom2_ghidra.csv recomp/extra_functions.txt --out /tmp/fixed.csv
diff <(tr -d '\r' < recomp/socom2_ghidra.csv) <(tr -d '\r' < /tmp/fixed.csv)

# C -- the synthetic ELF's shape
readelf -hl game/disc/socom2_game.elf

# D -- provenance and callers
git log --format='%h %ad %s' --date=short -- recomp/socom2.toml | tail -1
git grep -n importGhidraMap -- third_party/ps2recomp
wc -l recomp/socom2.toml recomp/extra_functions.txt

# E -- the stubs daa1eda removed (29), against the 17 sceVu0* addresses [H] would re-stub (all 17 among them)
git show daa1eda -- recomp/socom2.toml | grep '^-' | grep -o '"[^"]*@0x[0-9A-Fa-f]*"'
```

Command A reads `game/disc/socom2_game.elf`: this is the copy `build.sh:46` makes of `game/overlays/socom2_game.elf`,
which is the file the toml's `input` names. Only the copy is on this machine. The script is a Python replay of
the C++ rules cited below, not the recompiler itself. **What checks it:** the replay gives 14,882 files,
7,958 `FUN_` and 6,750 `sub_`, the same numbers `tools_py/research/symbols/README.md`'s `toml_overlap.py` row
measured on a real `recomp/output` on the local machine. A number marked *(row)* comes from that README row
and is not re-derived here.

## 0. Four corrections to the spec's §1.1 map (the recompiler row)

1. **`importGhidraMap` is dead code.** It is declared at `ps2xAnalyzer/include/ps2recomp/elf_analyzer.h:42` and
   defined at `elf_analyzer.cpp:1786`, and nothing calls it (command D). `build.sh:37` builds `ps2_analyzer`,
   but the recomp step (`build.sh:40-56`) never runs it. The csv's only reader in the build is
   **`ElfParser::loadGhidraFunctionMap`** (`ps2xRecomp/src/lib/elf_parser.cpp:959-1123`), which
   `PS2Recompiler::initialize` calls at `ps2_recompiler.cpp:805-808`. The toml itself is analyzer output that
   was run once and then committed (`40b7c55 2026-09-04 design spec + analyzer TOML for socom2_game.elf`,
   command D), and people have edited it by hand since then.
2. **The sanitiser that names the output is `PS2Recompiler::sanitizeFunctionName`** (`ps2_recompiler.cpp:2190-2209`,
   using its own `sanitizeIdentifierBody` at `:49-79`), not `CodeGenerator::sanitizeFunctionName`
   (`code_generator.cpp:181-201`). The CodeGenerator one names only functions that have an ELF symbol
   (`getFunctionName`, `:164-179`), and the synthetic ELF has **0 section headers** (command C), so it has no
   symbols. The two sanitisers differ: CodeGenerator puts `ps2` in front of any leading underscore, while
   PS2Recompiler adds `ps2_` only in front of a keyword or a reserved spelling (`__x`, `_X`) and leaves `_foo`
   as it is. Of the toml's 656 names, 88 would get the `ps2_` prefix ([G]).
3. **A repeated name is not a duplicate symbol.** The identifier and filename are `<sanitised name>_0x<start>`
   (`makeName`, `ps2_recompiler.cpp:1105-1106`). The csv already has 17 names at more than one address
   (`RFU116_SetSyscall` ×5, `caseD_0` ×5, `AddDmacHandler` ×2 …, [C]), and today's tree
   links. Keeping names unique helps a reader; the linker does not need it.
4. **The filename is capped at 100 characters** (`getOutputPath` → `clampFilenameLength(safeName, ".cpp", 100)`,
   `ps2_recompiler.cpp:2150`, `:2155-2188`). Every r0001 start is 6 hex digits (csv starts
   `0x180008..0x669f40`, [C]), so a name longer than 100 − 4 − 9 = **87** characters is truncated in the filename
   but kept whole in the identifier. Spec 1.2's cap of 96 should be 87 if the filename is to carry the whole name.

Research/46 (the name-consumer map, written beside this note) reaches 1, 4 and the 237 / 19 counts of §4
independently.

## 1. Where each name class in the output comes from

The recomp step (`build.sh:40-56`) runs in this order: `fix_ghidra_csv.py` rewrites the tracked csv in place
(`build.sh:47`), then `ps2_recomp socom2.toml` runs (`:50`). Command B shows that the tracked csv is already a
fixed point of the fixer ("0 ranges fixed, 0 forced entries added, 0 rows merged, 14879 functions").

| class in `recomp/output` | count | where it comes from |
|---|---|---|
| `sub_XXXXXXXX_0x…` | **6,750** ([D]; 6,750 *(row)*) | `ElfParser::parse` → `loadDebugFunctions` (`elf_parser.cpp:1151`, `:1348`). The ELF has no DWARF, so `ScanJalTargetsFallback` (`:456-533`) makes one `sub_%08X` (`MakeAutoFunctionName`, `:213-218`) for the entry point and for every JAL target in a PF_X segment: **9,514 starts** ([D]). Each one runs until the next JAL target. `loadGhidraFunctionMap` then drops every auto-named start that is not a csv row (`:1065-1071`). Both remaining names are "auto" (`IsAutoGeneratedName`: `sub_`, `FUN_`, `LAB_`, `DAT_`, `:28-34`), so the sort at `:1073-1094` keeps the **longer** range. Of the csv's 14,708 `FUN_` rows, 9,392 are also JAL targets. For 6,750 of those the JAL span is longer, so `sub_` wins; for 2,633 the spans are equal and `FUN_` wins on name order; for 9 the csv span is longer ([D]). |
| `FUN_xxxxxxxx_0x…` | **7,958** ([D]; 7,958 *(row)*) | Ghidra's auto name from the csv: a row that is not a JAL target (5,316 = 14,708 − 9,392, [D]) or that wins the tie-break (2,642 = 2,633 + 9, [D]). |
| real names | **70** ([C], [D]) | Ghidra's own names in the csv (`ExportPS2Functions.java`'s syscall-wrapper labels: `AddDmacHandler`, `WaitSema`, `RFU116_SetSyscall`, `_EnableIntc` …). 43 of them are among the 54 runtime-known names in `recomp/socom2_ghidra.toml` ([C]), a file `build.sh` does not read. **None of the toml's 656 names is in the csv** ("csv name already equal 0", [B]). The row's "~120 real names" *(row)* is `toml_overlap.py`'s `named` bucket, meaning every `.cpp` not starting `FUN_`/`sub_`/`caseD_`. By the replay that bucket is 70 real names + 58 `thunk_FUN_` + `entry` + `register_functions.cpp` = 130. |
| `thunk_FUN_…`, `caseD_…` | 58, 42 ([C]) | Ghidra's names. To the recompiler these are **not** auto (`:28-34`), so their ranges are authoritative (`:604-628`). |
| `entry_0x180008` | 1 | The csv's `entry` row (Ghidra's name for the ELF entry). It is non-auto, so it beats `sub_00180008`. It also becomes the bootstrap name (`ps2_recompiled_functions.h`, `register_functions.cpp`). The production recompiler no longer makes `entry_<hex>` functions: resume targets are registered against their owners (`ps2_recompiler.cpp:1787-1902`, comment at `:2211-2215`). The replay's total matches with none (research/04's "plus synthetic `entry_XXXXXXXX`" is out of date). |
| total files | **14,882** ([D]; 14,882 *(row)*) | 14,879 functions (every csv row that lies in a code segment, none dropped, [D]), plus `register_functions.cpp`, `ps2_recompiled_functions.h` and `ps2_recompiled_stubs.h`. Every function produces one file, because `shouldGenerateCodeForFunction` is `isRecompiled \|\| isStub \|\| isSkipped` (`ps2_recompiler.cpp:81-84`). |

**`recomp/extra_functions.txt` does not produce `sub_`.** It has 1,619 lines (command D), 1,619 distinct addresses,
and **all 1,619 are already csv rows, all named `FUN_`** ([C]): `fix_ghidra_csv.py:57-79` adds each forced entry as
a `FUN_%08x` row, and the tracked csv already holds them. `recomp/merge_ranges.txt` has 1 range ([C]) and
`recomp/loader_text_end.txt` holds one address for `make_overlay_elf.py`. Neither affects naming. Spec 1.3's
default stands: `sub_*` names are the recompiler's placeholders and get no sidecar row. Note that the
recompiler's auto set (`sub_`, `FUN_`, `LAB_`, `DAT_`) is narrower than spec 1.3's list, which also counts
`thunk_FUN_`, `caseD_` and `entry`.

## 2. The toml's keys, and what reads them

`recomp/socom2.toml` has 2,618 lines (command D). `ConfigManager::loadConfig` (`ps2xRecomp/src/lib/config_manager.cpp`) is the only
reader in the build ([A], and the code lines below):

| key | entries ([A]) | read by the recompiler? | what happens to it |
|---|---|---|---|
| `general.input` / `ghidra_output` / `output` / `single_file_output` / `patch_syscalls` / `patch_cop0` / `patch_cache` | scalars | yes, `:40-66` | paths and switches |
| `general.stubs` | **223** `name@addr` | yes, `:68-75` | `parseFunctionSelector` (`ps2_recompiler.cpp:237-273`) splits at the last `@`. The address goes into `m_stubFunctionStarts` and the name into `m_stubHandlerBindingsByStart[addr]` (`:768-794`). **The name also goes into `m_stubFunctions`** (`:773`), and `isStubFunction` matches every function against that set **by name** (`:2030`). |
| `general.untracked_stubs` | **433** `name@addr` | **no**: no line in `config_manager.cpp` reads it | read by no program. `HleStats::parseTomlStubs` (`ps2xRuntime/src/lib/Kernel/HleStats.cpp:149`) parses the `stubs` array only (`ps2_runtime_kernel_tests.cpp:1007`: "only the stubs array is parsed"). `tools_py/revision_toml.py:105` carries its addresses over to r0004. |
| `general.skip` | 0 | yes, `:77-84` | skip by name or address; empty |
| `[mmio]` | 233 | yes, `:129-146` | instruction → MMIO address hints |
| `[[jump_tables.table]]` | 31 tables, 1,019 entries | yes, `:148-250` | `JR` targets |
| `[patches].instructions` | 46 | yes, `:86-127` | instruction patches |
| `[performance].critical` | 460 (names, not addresses) | **no** | analyzer output (`ps2xAnalyzer/src/toml_generator.cpp:204-210`). `revision_toml.py:33` leaves it untouched. |

**Is the NAME part of a `stubs` entry ever used to name the function? No.** It is used in exactly four places,
none of which is the name:
(1) the stub body's dispatch: `dispatchName = binding` → `ps2_stubs::<name>` / `ps2_syscalls::<name>` / `TODO_NAMED`
(`ps2_recompiler.cpp:1165-1190`). All 223 names resolve to a handler ([F]: "no runtime handler 0").
(2) the by-name stub set (`:773`, `:2030`).
(3) `hasResolvedStubHandler` for correctness-critical initialisers (`:2062-2069`), and the synthesised
`manual_initializer_<name>` (`:958`).
(4) at run time, as labels in the HLE statistics and the scheduler trace (`HleStats.cpp:149`, `SchedTrace.cpp:256-267`,
knobs `PS2X_HLE_STATS_TOML`/`PS2X_SCHED_TRACE_TOML`, `ps2xShared/include/ps2x/knobs.h:109,147`).

**How `sceCdDelayThread@0x0018DBB8` becomes `sub_0018DBB8` in the stub header** ([D] gives each value):
1. `ScanJalTargetsFallback` makes `sub_0018DBB8`, running to the next JAL target at **0x18df80** (`elf_parser.cpp:501-531`).
2. `loadGhidraFunctionMap` adds `FUN_0018dbb8` with the csv range, ending at **0x18dc20** (`:1024-1033`). Both
   names are auto, so the sort keeps the longer range, `sub_0018DBB8` (`:1073-1107`). `extractFunctions` keeps it
   (`:663-763`).
3. The stub selector puts 0x18dbb8 into `m_stubFunctionStarts` and binds `"sceCdDelayThread"` (`ps2_recompiler.cpp:768-793`).
   `recompile()` marks the function `isStub` (`:984-991`) through `isStubFunction`'s start check (`:2025`).
4. `generateOutput`'s `makeName` takes **`function.name`**: `sanitizeFunctionName("sub_0018DBB8") + "_0x18dbb8"`
   (`:1085-1107`) goes into `m_functionRenames` → `CodeGenerator::setRenamedFunctions` (`:1110-1121`).
5. The stub body calls `ps2_stubs::sceCdDelayThread` (binding, `:1165-1181`) inside `void sub_0018DBB8_0x18dbb8(…)` (`:1149-1152`).
6. `generateStubHeader` writes `void sub_0018DBB8_0x18dbb8(uint8_t* rdram, R5900Context* ctx, PS2Runtime* runtime);`
   (`:1709-1720`). The same `getFunctionName` names it in `ps2_recompiled_functions.h` (`:1763`) and in the
   function table (`function_table_emitter.cpp:65`). The exact identifier has the `_0x18dbb8` suffix, which the
   spec's and research/44's `sub_0018DBB8` leave out.

Where the toml's names come from: the analyzer's SCE signature scanner (`elf_analyzer.cpp:133-170`, over the
embedded `sce_symbol_database_data.h`) names the SDK functions it recognises. `toml_generator.cpp:131-146` then
sorts them into `stubs` (a runtime handler exists) and `untracked_stubs`. This origin is **inferred** from the
code and from commit `40b7c55`'s message; the analyzer's run log is not tracked. It explains why 7 names sit at
more than one address ([B]: `__dt__Q23std9exceptionFv` ×8, `kCopy` ×5, `__sbprintf`, `__sprint`, `_request_end`,
`_start`, `setD4_CHCR` ×2). A signature matched several identical small bodies, so at most one address per name
can be the real one.

## 3. The 656: which are csv rows, and the 272/1 overlap

| | selectors | csv rows | not csv rows (in a row's range / in no row) |
|---|---|---|---|
| `stubs` | 223 | 214 (all `FUN_`) | 9 (2 / 7) |
| `untracked_stubs` | 433 | 401 (400 `FUN_` + `entry`) | 32 (6 / 26) |
| all | **656** (656 distinct addresses) | **615** | **41** (8 / 33) |

(All from [B].) In today's output, the 214 bound stubs are named `FUN_` 104 times and `sub_` 110 times; the
untracked ones are `FUN_` 219, `sub_` 181 and `entry` 1 ([D]).

**The 41 that no csv row starts at are not functions in the output at all.** None of the 41 is a JAL target
([D]: "0 of 41"). No route can name them: a name needs a function to be attached to, and
`loadGhidraFunctionMap` removes every start that is not a csv row (`elf_parser.cpp:1065-1071`). Neither an
added name file, nor the analyzer's symbol table (the analyzer is not in the build), nor a sidecar row can reach
them. Only a *function-discovery* change reaches them: an `extra_functions.txt` entry becomes a `FUN_` row, and
if it falls inside a parent row the parent is truncated (`fix_ghidra_csv.py:57-79`). That is a boundary change
for the gate to prove, not a rename, and it is outside Goal 6. **Nine of these are live `stubs` selectors
that bind nothing today**: `sceCdInitEeCB@0x18ddf8`, `sceDmaGetEnv@0x191000`, `fclose@0x192ca8`,
`sceDeci2ExReqSend@0x1a4cb8`, `sceSifRegisterRpc@0x1a6f40`, `sceSifLoadElf@0x1abb30`, `sceMpegAddBs@0x1bb950`,
`sceMpegGetDecodeMode@0x1bba98`, `sceVpu0Reset@0x1c08e8` ([B]). A reader of the toml would assume these nine
are HLE'd; they are not. This belongs in research Q1's consumer map.

**The overlap with the proposals.** Of the 479 Task 7 proposals, 273 sit on toml addresses (185 `exact`, 87
`relinked-body`, 1 `hash+callees`; 103 of the 273 in the `stubs` list). **272 agree name for name and 1 differs**
([E]; 272/1 *(row)* re-derived). Task 7b's 6 add 3 more toml addresses, all agreeing ([E]). That leaves **380 toml
addresses that no proposal names**: 339 csv rows (338 auto-named, plus `entry`) and the 41 above ([E]). The
spec's "~384" is 380.

**The one that differs: `0x001a3448`.** The toml says `setD4_CHCR`; Task 7 proposes `setD3_CHCR` (`hash+callees`,
0.95). The toml is right. Each body's only DMA-channel store identifies it ([J]): the retail function at
0x1a3448 stores to **D4_CHCR (0x1000B400)**, and so do both of the demo's `setD4_CHCR` (0x15aaa0 and 0x15ada8,
100 B each). The demo's `setD3_CHCR` (0x15aa38) stores to **D3_CHCR (0x1000B000)**, and so does the retail
function the toml calls `setD3_CHCR` (0x1a30b8). The three demo bodies have the same shape and differ only in
that constant, so the pair `hash+callees` chose is **false**. The toml's own
`setD4_CHCR` also sits at two retail addresses (0x1a3130, 0x1a3448), which matches the demo's two static copies.

## 4. The smallest change that carries every known name into `recomp/output`

**Why the csv route is not a rename in this recompiler.** Four rules read `function.name`:
- *Extent.* A non-auto name wins the sort against the JAL span (`elf_parser.cpp:1073-1094`) and makes its csv range
  authoritative. Auto-named starts strictly inside an authoritative range are dropped (`:604-628`, `:675-682`).
- *Stub by name.* `isStubFunction` is true for a stubs-list name, or for any `PS2_STUB_LIST` name, including the
  leading-underscore alias (`ps2_recompiler.cpp:2023-2035`, `ps2_runtime_calls.h:33-85`; 552 stub names, [F]).
- *Correctness-critical.* A name beginning `__ct__`, `__sinit_`, `_GLOBAL__sub_I_`, … changes how skips, stubs and
  decode failures are treated (`:2037-2060`, `:986-1035`).
- *`entry_`.* A name beginning `entry_` is left out of entry analysis (`control_flow_analyzer.cpp:64`,
  `ps2_recompiler.cpp:281`, `:1805`) and gets `makeName`'s end-address suffix (`:1093-1102`). `main` → `ps2_main`.

Block [H] replays the recompiler with the candidate names written into the csv:

| written into the csv | files renamed | ends shortened (JAL span → csv span) | of them, a branch from inside into the cut tail | functions dropped | newly stubbed by name | correctness-critical |
|---|---|---|---|---|---|---|
| Goal 1: 479 + 6, readable form | 485 | **237** | 1 (`_doMC` → `_copyRefImage`'s start) | 0 | **19** | 6 (the `__sinit_*`, only under `readable_names.py`'s sketch; spec 1.2's `sinit_` rule makes this 0) |
| Goal 6: the 338 auto rows | 338 | **161** | **3**, all into the middle of the next row (`__unexpected`, `__svfscanf`, `_getpic`) | **2** (`FUN_001ac600`, `FUN_001ac83c`, now inside `_kTLBException`/`_kDebugException`) | 0 | 0 |
| both | 823 | 398 | 4 | 2 | 19 | 6 |

The 19 names that would become stubs are `sceCdDiskReady`, `sceSifFreeSysMemory` and 17 `sceVu0*` functions
([F], [H]). All 17 `sceVu0*` addresses are among the 29 HLE stubs commit `daa1eda` removed (command E), because "the HLE MulMatrix multiplied in
the wrong order … main-menu roller never drawn". A csv rename would silently bring them back. The branch check
uses the script's own static decoder (conditional branches, `J`, BC0/1/2), not `ControlFlowAnalyzer`, and it
ignores jump tables. Its counts are a lower bound on the control-flow changes.

**(a) The csv route (S12-R4 as written).** It reaches 485 + 338 = 823 functions, and 824 if `entry` is renamed
`_start` (which D2 forbids). It cannot reach the 41. To cost only a rename, the applier would have to refuse
every name whose replay shows a behaviour change: 237 + 19 of Goal 1's 485, and 161 + 2 of Goal 6's 338. The
applier would then need the game's ELF to decide, and more than half of Goal 1 would be lost. Applied without
those refusals, it is a codegen change on about 400 functions, and a failure in the proof bar would have 400
suspects.

**(b) A recompiler change: a display-name file.** ps2xRecomp would take a new optional key,
`[general] names = "socom2_names.csv"`, which is the spec 1.3 sidecar. It would read the sidecar's first two
columns (`Address,Name`) into an address → name map, and `makeName` (`ps2_recompiler.cpp:1085-1108`) would use
that name when the start is in the map, and `function.name` otherwise. Nothing else changes. `function.name`
keeps the csv's auto name, so extent, stub, correctness-critical and `entry_` behave exactly as today.
`getOutputPath`, `ps2_recompiled_stubs.h`, `ps2_recompiled_functions.h`, `register_functions.cpp` and the
direct-jump call sites (`control_flow_emitter.cpp:217`) all read `m_functionRenames` through
`getFunctionName`, so they follow without further edits.
- It reaches the same 823 functions (824 with `entry`) and none of the 41.
- It changes these files: `ps2xRecomp/include/ps2recomp/types.h` (one field in `RecompilerConfig`, `:176-192`),
  `src/lib/config_manager.cpp` (one `find_or` next to `ghidra_output` at `:41`, and the write-back at `:269`),
  `include/ps2recomp/ps2_recompiler.h` and `src/lib/ps2_recompiler.cpp` (the loader after `:805-808`, the lookup
  in `makeName`, and a static `MakeOutputName` helper so tests can call it, as they already call
  `ClampFilenameLength`), plus one line each in `recomp/socom2.toml` and `recomp/socom2_r0004.toml`
  (`revision_toml.py` would want a `--set-names` beside `--set-ghidra-output`, `:923-925`). That is about 40
  lines of C++.
- **The synthetic-ELF tests exist and are the model to extend.** `ps2xTest/src/ps2_recompiler_tests.cpp:879-947`
  ("ghidra map replaces JAL fallback-only auto starts") writes a minimal MIPS ELF with a JAL-fallback target and a
  csv, then asserts which name and start survive. Add one case in which the sidecar names a start whose JAL span
  is longer than its csv span and gives it a `PS2_STUB_LIST` name (`sceVu0MulMatrix`). The case asserts that
  the extent and `isStub` do not change and that the output name is `sceVu0MulMatrix_0x…`. The tests build in CI
  on both platforms (`ps2xTest/CMakeLists.txt:63`; `.github/workflows/linux.yml:89`, `windows.yml:85`), so the
  cloud meets the code bar.
- The sidecar parser must read only the first two fields, because `Evidence` holds commas. Spec 1.3 already puts
  `Address, Name` first.

**(c) Both.** Using the csv for the "pure" subset and the recompiler for the rest gives a name two homes and two
rules. That is worse than either route alone.

**Recommendation: (b).** The csv's `Name` column is function identity for this recompiler. The sidecar should be
the one home of a name, and the recompiler should read it only for output names. This keeps D6's substance: one
home, the toml's stub list stays the handler selector, and a test holds each toml name equal to the sidecar's
name at that address. It changes S12-R4's letter: **the applier writes the sidecar, and does not write new names
into the csv's `Name` column.** The 171 existing non-auto csv rows stay where they are; moving them would change
behaviour. The spec 1.3 audit becomes "every sidecar row's `Address` is a csv row start; every non-auto csv
`Name` has a sidecar row with the same name". `carry_names` already moves the sidecar (spec 1.3).

**What `./build.sh recomp` regenerates differently under (b).** `build.sh:48` rebuilds `ps2_recomp` on every recomp,
so the change takes effect with no script edit.
- Goal 1 alone: **485** `.cpp` files change name (all 485 proposal rows are csv rows, [H]). The identifier changes
  in those files, in the two headers (104 of the 485 are stubs today, so 104 lines change in
  `ps2_recompiled_stubs.h`, [E]) and in `register_functions.cpp`. It also changes in any file that tail-jumps (`J`)
  to a renamed function or holds it in a jump-table switch. That count needs the real output and cannot be derived
  here.
- Goal 6: **338** more (339 with `entry`).
- Nothing else in any file changes: no body, no extent, no stub, and the table slots are keyed by address.

Under (a), the same renames come with the 237 / 161 extent changes, the 2 dropped functions and the 19 stub flips.

**Two conditions Goal 6 carries under either route** (from [G] and [H]):
- 134 of Goal 6's 338 toml names begin with an underscore, which spec 1.2 rule 3 refuses. Research Q2 must give a
  transform, or Goal 6 applies only 204.
- 6 distinct names sit on 16 of the 338 rows and also at other toml addresses (`__dt__Q23std9exceptionFv` on 8
  rows). A signature match of identical small bodies cannot be right at all of them. The `toml-stub` pass should
  refuse a name that the toml puts at more than one address unless a second signal agrees, rather than score
  it 0.90.

## 5. Hazards for Goal 1's proof half

**Tracked files that depend on an output filename.** No build script, CMake list or test depends on one, under
either route:
- `ps2xRuntime/CMakeLists.txt:490-500` globs `${PS2X_RUNNER_GENERATED_DIR}/*.cpp` with `CONFIGURE_DEPENDS`, and
  `build.sh`/`build_linux.sh` reconfigure before every build.
- `build.sh:49` runs `rm -rf` on the output before the recomp, so no stale file survives a rename.
- `scripts/vm_sync.sh:7` quotes the file count 14,882, which a rename does not change.
- The only `_0x` literal in a test is `ClampFilenameLength`'s (`ps2_recompiler_tests.cpp:1083-1085`).
- The runtime reaches functions by address (`replaceFunction`, `socom2_addresses.h`). `FUN_003b24c0`,
  `FUN_0034afd0` and `FUN_0034b6c0` appear there only in log strings (`game_overrides_socom2.cpp:137`, `:1450`).

Documentation: [I] finds 12 generated-name citations in 8 tracked docs.
- Goal 1 renames one of them: `FUN_001b3648` in research/25.
- Goal 6 renames `FUN_003b24c0` (research/38 and the Sprint 10 Goal 9 plan) and `sub_00194C30` (research/20),
  and `entry_0x180008` (research/44) only if `entry` is renamed.
- A renamed citation breaks nothing: the text goes out of date. These are dated notes, so a correction line in
  each is the project's practice (D4).

**Does ordering or the function table depend on the name?**
- The function list is sorted by start (`elf_parser.cpp:765-767`).
- The table is sorted by address and indexed by `(address − base) >> 2`, and duplicate addresses are resolved by
  address (`function_table_emitter.cpp:48`, `:135-167`).
- Each output file is written on its own. A rename reorders no table.
- The name-dependent rules are the four in §4. Under (a) they turn a rename into a runtime change; under (b) none
  of them sees the new name.
- One order does depend on the filename: `ps2EntryRunner` builds as a unity build with batches of 32 over the
  sorted glob (`CMakeLists.txt:8-9`, `:576-580`). Renamed files move between batches, and the executable's
  function layout changes. That is not a change in meaning, but if a timing-sensitive symptom moves during the
  gate, this is where to look first.

**Name-length limits.**
- The generator has no identifier limit, and clang (llvm-mingw) has none that matters here.
- The filename is clamped to 100 characters, so a name over 87 characters is truncated in the filename (§0.4).
  1 of the 1,141 candidate names exceeds 87, and the longest is 96 ([G]).
- Windows `MAX_PATH` (260): at the owner's root `C:\projects\socom_pc` (the path in
  `recomp/socom2_ghidra.toml`), the longest generated path is 35 + 100 = **135** characters ([G]). A 96-character
  name produces that same 135, because the clamp cuts it to 87 + `_0x` + 6 hex digits + `.cpp`.
- With the unity build on (the default, `CMakeLists.txt:8`), generated sources get no object file of their own.
  With it off, an object named after the full source path under
  `third_party\ps2recomp\build-clang\ps2xRuntime\CMakeFiles\ps2EntryRunner.dir\` would be 236 characters ([G]).
  That is under 260 and under CMake's default Windows object-path limit. **Not verifiable here:** CMake's exact
  object naming for sources outside the source tree, and the value of `CMAKE_OBJECT_PATH_MAX`, come from CMake
  itself, not from this repository's sources. The 236 assumes the full-path form.

## What this means for a task

| task | finding | what it changes |
|---|---|---|
| Goal 6 / S12-R4 (D6) | The toml's names stop at the stub list because `makeName` names a function from `function.name`, never from the stub binding (§2). A name written into the csv is semantic: extent, stub-by-name, correctness-critical, `entry_` (§4, [H]). | Recommend (b), a recompiler change: `general.names` = the sidecar, used only in `makeName`. The applier writes the sidecar, not the csv `Name` column. The audit becomes "sidecar address is a csv row; non-auto csv names have sidecar rows". This needs a ruling that amends S12-R4's letter. |
| Goal 1 (Task 1, the applier) | Under the csv route, 237 of the 485 rows lose their JAL-span body and 19 become HLE stubs, including 17 of the 29 stubs `daa1eda` removed ([H], command E). | Under (b), none of this happens and the 485 renames are pure. If the csv route is kept anyway, the applier must refuse any `PS2_STUB_LIST` or stubs-list name at a non-stub address, any `entry_…`, `main`, and any correctness-critical prefix, and the proof bar must be read as a codegen change on 237 functions. |
| Task 7 / research/44 | `0x001a3448` is `setD4_CHCR` (the toml's name) and not `setD3_CHCR`. Its store goes to D4_CHCR, as in both demo `setD4_CHCR` bodies ([J]). The `hash+callees` pair is false. | Drop or correct that proposal before Goal 1 applies. `hash+callees` has 15 proposals (research/44 command A, spec §1.4), and 1 of the 1 that can be checked against the toml is wrong ([E]). That tie-break chose among bodies that are identical except for a constant, so its 0.95 score is too high. |
| Goal 6 (the `toml-stub` pass) | 380 toml addresses carry names no proposal gives: 338 auto csv rows, `entry`, and 41 non-rows ([E]). 134 of the 338 begin with `_`, and 6 names sit at several addresses ([H], [B]). | The pass applies at most 338. It needs research Q2's underscore rule and should refuse names at more than one address. The agreement test (toml name == sidecar name at the address) is what holds the two files together. |
| research Q1 (consumer map) and the spec's §1.1 | The csv reader is `ElfParser::loadGhidraFunctionMap`, not `importGhidraMap` (dead). The naming sanitiser is `PS2Recompiler::sanitizeFunctionName`. Repeated names are legal (`_0x<start>` suffix). `untracked_stubs` (433) and `[performance].critical` (460) are read by no program. 9 `stubs` selectors bind nothing (§0, §2, §3). | Correct §1.1's first row. Record the 9 inert selectors, which a reader would otherwise take for HLE. |
| research Q2 (readable names) | The filename clamp keeps 87 characters of name at r0001's 6-digit addresses (§0.4). The real sanitiser leaves `_foo` alone and adds `ps2_` in front of `__x`/`_X` (88 toml names, [G]). | Cap 1.2's length at 87, not 96, so the filename carries the whole name. Leading-underscore names still need a rule (134 in Goal 6). |
| Goal 1 proof half (local) | No build script, CMake list, test or runtime path reads an output filename. The table is keyed by address. Unity batches of 32 over the sorted glob change with the names (§5). | Under (b), expect a pure rename: 485 files, two headers, `register_functions.cpp`, and the direct-jump call sites. If the gate moves, suspect exe layout (unity batches), not semantics. |
| Goal 6 beyond naming | The 41 toml addresses that are not csv rows are not functions in the output. None is a JAL target (§3). | Only a function-discovery change (`extra_functions.txt` → a new row that truncates its parent) can name them. That is a boundary change for the gate, and it is out of Goal 6's scope. |
