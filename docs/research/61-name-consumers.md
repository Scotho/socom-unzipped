# 61. The name consumers, exhaustively: who reads a function name or a raw guest offset

Date: 2026-09-24. Sprint 12 research wave, question 1 of the handoff §4
(`docs/superpowers/plans/2026-09-24-sprint-12-cloud-handoff.md`), completing the spec's §1.1 table
(`docs/superpowers/specs/2026-09-24-sprint-12-the-readable-image-design.md`). Read-only: source, the tracked csv and
toml, the two git-ignored proposal files and the r0001 image. Nothing was built or run, no tracked file but this note
and its script was written, and no byte of the game is in either.

**The one-line answer: a csv `Name` reaches the generated code through one reader
(`ElfParser::loadGhidraFunctionMap`; the analyzer's `importGhidraMap`, which the spec first named, has no caller), and
it is not only a label there. Renaming a `FUN_` row (a) changes its identifier and filename, always with an `_0x<start>` suffix, so
two rows can never define one symbol; (b) makes it an *authoritative* range, which for 237 of the 485 proposals moves
the function's decoded END (today they are emitted as the JAL scan's `sub_*` and run to the next call target, one of
them 84,660 bytes past its csv End); and (c) for 19 of the 485 makes the recompiler STUB the function, because the name
is on the runtime's stub list. The runtime, HLE and parity tools address the image by number only; the one struct they
all lean on, the player actor, is `CZSealBody` by its own RTTI, and 31 named displacements plus 24 runtime reads are
the offsets a type would name.**

## The commands

```
# A -- every count in this note that is not B-E (all sections, under a second; --section S for one, --list per row)
python tools_py/research/symbols/name_consumers.py

# B -- the tracked csv is already the fixed csv (fix_ghidra_csv is idempotent on it)
python tools_py/fix_ghidra_csv.py recomp/socom2_ghidra.csv recomp/extra_functions.txt --out /tmp/fixed.csv
#    -> "0 ranges fixed, 0 forced entries added, 0 rows merged, 14879 functions"

# C -- the r0001 image carries no symbol table, so no ELF name ever competes with the csv
python -m tools_py.elf_symbols game/disc/socom2_game.elf
#    -> "0 symbol table entries: 0 STT_FUNC ..."; its PT_LOAD flags are R+X, RW, RWX, RWX

# D -- the analyzer's csv importer has no caller
grep -rn "importGhidraMap(" third_party/ps2recomp        # -> 2 hits: elf_analyzer.cpp:1786 (definition), elf_analyzer.h:42

# E -- the brief's "62 by a rough grep" is 62 LINES
grep -cE "0[xX][0-9a-fA-F]+" tools_py/parity/verdict_core.py   # -> 62
```

A's inputs: `recomp/socom2_ghidra.csv` (14,879 rows), `recomp/socom2.toml`, `recomp/extra_functions.txt`,
`recomp/merge_ranges.txt`, `game/demo_symbol_renames.csv` (479 rows) + `game/demo_symbol_renames_7b.csv` (6) = **485
proposals**, `game/disc/socom2_game.elf`, and the C++ it replicates (`ps2_call_list.h`, `config_manager.cpp`,
`code_generator.cpp`'s keyword list). Every `file:line` below is at `6c1d9ce` (the files cited are unchanged at `f1f42f9`) and re-found by `grep -n '<symbol>' <file>`;
paths under `third_party/ps2recomp/` are written from `ps2xRecomp/`, `ps2xRuntime/`, `ps2xAnalyzer/` down.

**How A's model was checked.** Section `model` replicates `ElfParser` (JAL-scan gap fill, the csv merge, the
authoritative-range filter) in Python. It is a replication, not an observation (no `recomp/output` exists here), but it
reproduces two independent measurements exactly: the symbols README's census of the local `recomp/output`
(**7,958 `FUN_` and 6,750 `sub_`**, `tools_py/research/symbols/README.md`, `toml_overlap.py` row), and the nine toml
stubs that `docs/KNOWN.md` §4 and `docs/research/20-hle-liveness.md` found to have **no generated wrapper**
(`sceCdInitEeCB`, `sceDmaGetEnv`, `fclose`, `sceDeci2ExReqSend`, `sceSifRegisterRpc`, `sceSifLoadElf`,
`sceMpegAddBs`, `sceMpegGetDecodeMode`, `sceVpu0Reset`): A prints the same nine as "absent".

## 1. How a csv Name becomes code (the corrections to the spec's §1.1)

1. **The reader.** `ps2_recompiler.cpp:805-808` calls `ElfParser::loadGhidraFunctionMap` (`elf_parser.cpp:959`). The
   analyzer's `importGhidraMap` (`elf_analyzer.cpp:1786`) has no caller (D) and `build.sh:47-50` runs only
   `fix_ghidra_csv.py` and `ps2_recomp`. research/48 reached the same reader the same day and superseded the spec's
   row in place; this note adds the rest of the path. For the record, `importGhidraMap` *would* create a new function
   named with the csv `Name` for a `Start` it had not found; it is dead code. The live reader: every row whose `Start` lies
   in an executable PT_LOAD becomes a function carrying the csv `Name` (`:1024-1032`); a row outside one is skipped
   and counted ("Ignored N"); A: all 14,879 are inside one.
2. **The name the analyzer/recompiler gives a function it finds itself** is `sub_%08X` (`MakeAutoFunctionName`,
   `elf_parser.cpp:213`): the JAL scan (`ScanJalTargetsFallback`, `:456`, run because the image has no DWARF,
   `:1421`) proposes 9,514 starts (A). Each one that is not a csv `Start` is deleted (`:1065-1071`). Each one that
   *is* ties with the csv row at the same start; the sort (`:1073-1094`) puts a non-auto name first, else **the
   larger End**, else the name. So a `FUN_` row whose next JAL target lies beyond its csv End is emitted as `sub_`
   and decoded to that target. A: **6,750 rows emitted as `sub_`, 7,958 as `FUN_`, 171 named** (59 `thunk_*`, 42
   `caseD_*`, 70 other); 1,130 of the 6,750 run more than 16 bytes past their csv End. This is why
   `ps2_recompiled_stubs.h` says `sub_0018DBB8` for `sceCdDelayThread` (spec Goal 6).
3. **Auto vs authoritative.** `IsAutoGeneratedName` (`elf_parser.cpp:28`) is `sub_`, `FUN_`, `LAB_`, `DAT_`. Any other
   name is authoritative: its csv End is final (`:604-627`) and an auto-named start inside its range is dropped
   (`addOrMerge`, `:663`). **So a rename is not only a label: it changes the function's range whenever the row is a
   `sub_` today.** A: of the 485, 237 are `sub_` today; renaming moves each one's End in by 4 bytes (124), 8 (16),
   12 (22), 16 (2) or more than 16 (73), the largest `KM_GetSoftwareKeyPair` at 0x64f604 by 84,660; none drops
   another function.
4. **The identifier.** `generateOutput` (`ps2_recompiler.cpp:1085-1115`) names every function
   `sanitizeFunctionName(Name) + "_0x" + <start hex>` (an `entry_<start>` name gets `_0x<end>`). **The suffix makes
   every identifier unique by address**: the csv today already has 17 sanitised spellings shared by 48 rows (A:
   thirteen `caseD_*`, `RFU116_SetSyscall` ×5, `RFU091` ×3, `AddDmacHandler` ×2, one `thunk_FUN_` ×2) and builds. The spec's "two rows with one sanitised spelling are two definitions
   of one symbol" (and research/44's hurdle 4 reason) does not hold for this recompiler; uniqueness is still worth
   keeping for grep, not for the link.
5. **The sanitiser that runs** is `PS2Recompiler::sanitizeFunctionName` (`ps2_recompiler.cpp:2190`, helpers
   `:36-79`): characters outside `[A-Za-z0-9_]` → `_`, `_` before a leading digit, `main` → `ps2_main`, and **`ps2_`
   before a keyword or a reserved spelling (`__x`, `_X`)**. A leading `_` followed by a lower-case letter is kept. The
   spec's description (`ps2` before any leading underscore, "`sanitizeIdentifier`") is the *other* copy,
   `CodeGenerator::sanitizeFunctionName` (`code_generator.cpp:181`; `sanitizeIdentifierBody` `:53`,
   `isReservedCxxIdentifier` `:83`, `isReservedCxxKeyword` `:92`, 92 keywords): it is reached only through
   `getFunctionName` (`:164`) for an address with no rename entry *and* an ELF symbol, and this image has no symbols
   (C), so it never runs here. There is no function called `sanitizeIdentifier`.
6. **The filename.** `getOutputPath` (`ps2_recompiler.cpp:2110`) uses the identifier, maps `/\:*?"<>|$` to `_`, and
   `clampFilenameLength` (`:2155`) cuts the name part so the whole file name is at most **100** characters, keeping
   the `_0x<start>` suffix: with a six-digit address a name longer than 87 characters gets a cut filename and a full
   identifier. A: 1 of the 485 `Proposed` names (96 characters) would be cut; 0 of the readable names.
7. **What else prints the name.** `function_emitter.cpp:76-85` writes `// Function: <raw csv Name>` (unsanitised) and
   `PS_LOG_ENTRY("<identifier>")`; `generateFunctionHeader` (`:1743`, `ps2_recompiled_functions.h`),
   `generateStubHeader` (`:1688`, `ps2_recompiled_stubs.h`), the registration table
   (`function_table_emitter.cpp:60-86`), direct jumps (`control_flow_emitter.cpp:217`) and jump-table switches
   (`jump_table_switch_emitter.cpp:24-31`, falling back to `func_<hex>`) all use the identifier by address. The
   runtime CMake globs `*.cpp` (`ps2xRuntime/CMakeLists.txt:490-495`); no build file names a generated file.

## 2. The consumer map

"Name?", "addr?", "offset?" say whether the consumer reads that kind of thing; the last column is what renaming one
csv `FUN_` row changes there. Counts are A's.

| consumer | file:line | Name? | addr? | offset? | what a rename of a csv Name changes there |
|---|---|---|---|---|---|
| csv reader | `elf_parser.cpp:959-1107` | yes | Start/End | no | the row now wins its start against the JAL scan's `sub_` (named sorts first) |
| auto-name rule | `elf_parser.cpp:28-34` | prefix | no | no | the row becomes authoritative: its End becomes the csv End (237 of 485 move), auto starts inside it drop (0) |
| JAL gap fill | `elf_parser.cpp:213, 456-532` | writes `sub_%08X` | yes | no | nothing; it only loses the tie |
| analyzer `importGhidraMap` | `elf_analyzer.cpp:1786-1872` | yes | yes | no | nothing: no caller (D) |
| analyzer names | `elf_analyzer.cpp:150-193` (SDK signature names), `function_classifier.cpp:130` (auto prefixes) | writes | yes | no | nothing: the analyzer wrote the toml once ("Generated by ElfAnalyzer", `recomp/socom2.toml:2`) and `build.sh` does not run it |
| forced entries | `tools_py/fix_ghidra_csv.py:78` (adds `FUN_<addr>`), `:99` (a row inside a `merge_ranges.txt` range is deleted with its name) | writes / deletes | yes | no | a renamed row inside a merge range would vanish: 0 of 485 (A); all 1,619 forced entries are already rows (A, B) |
| identifier | `ps2_recompiler.cpp:1085-1115`, `:2190` | yes | Start | no | identifier `<sanitised>_0x<start>` at the definition, both headers, the table and every call site |
| unused sanitiser copy | `code_generator.cpp:53-202` | yes | no | no | nothing on this image (C) |
| output filename | `ps2_recompiler.cpp:2110-2175` | identifier | Start | no | the file is renamed; cut at 100 characters |
| `// Function:` comment | `function_emitter.cpp:76` | raw | Start | no | the raw csv Name, unsanitised, heads the file |
| stub by name | `ps2_recompiler.cpp:2023-2035` (`m_stubFunctions`, `isStubName`) | **yes** | Start | no | **a name on the runtime stub list, or equal to a toml stub selector's name, stubs the function: 19 of 485 newly** |
| skip by name | `ps2_recompiler.cpp:2013-2021` | yes | Start | no | none: `skip = []` |
| correctness-critical | `ps2_recompiler.cpp:2037-2055`, `:1070` | prefix `__ct__`, `__sinit_` | Start | no | a stub, skip or decode failure on such a row becomes a hard recomp failure: 6 of 485 readable names (`__sinit_*`), 16 of the raw `Proposed` |
| stub dispatch | `ps2_recompiler.cpp:1145-1196`, `:768-792`; `function_table_emitter.cpp:73` | selector name, else csv Name | Start | no | none where a `name@addr` selector binds the address (the selector's name wins); the table bucket uses the csv Name |
| toml loader | `config_manager.cpp:27-260` | via stubs | yes | no | see §2.1 |
| relocation names | `control_flow_emitter.cpp:280-289` | ELF relocs | yes | no | none: the image has none (C) |
| runtime hooks | `game_overrides_socom2.cpp`: 28 `replaceFunction(` at 1364, 1448-49, 1512, 1589, 1738, 1749, 2037, 2097, 2134-68, 2242-50, 2271, 2294, 2303 | no | yes | yes (§3) | none: every wrap binds by address; names are in 124 comments and 3 log strings (A) |
| address table | `socom2_addresses.h`: 41 fields, 33 functions + 8 DATA (A) | no | yes | no | none; 1 proposal sits on a field (`netbExDescriptorDma` → `libnetb_trans_data`) |
| handler by name, run time | `game_overrides.cpp:61-111` (`bindAddressHandler`) ← `game_overrides_socom2.cpp:2280, 2309` (`"ret0"`); `ps2_runtime_calls.h:23-62` (exact or leading-`_` alias) | handler string | yes | no | none: the handler name is a literal, the address a literal/field |
| HLE stats | `Kernel/HleStats.cpp:149-200, 292-303` reads `recomp/socom2.toml`'s `stubs = [` at run time; `:55` picks float returns by name | selector name | yes | no | none from the csv; a toml selector rename relabels the stats |
| call trace | `game_overrides_socom2.cpp:1330-1366` (`PS2X_CALL_TRACE="addr:label"`, default label `FUN_%08x`); `scripts/parity/env.sh:33`, `tools_py/parity/sim_walk_to_b.py:70` (`0x553dc0:MoveScale,0x30cd80:NetIdle`) | hand label | **r0001 literal** | no | none; the two harness addresses are r0001 literals outside every per-revision table |
| parity probes | `tools_py/parity/guest_addresses.py:56-61` (4 addresses), `:125-129` (`PROBE_OFFSETS`, 3 × 2 revisions) | no | yes | yes | none |
| verdict core | `tools_py/parity/verdict_core.py`: 62 lines, 118 literals, 48 values (E, A); 52 address / 53 offset / 13 other occurrences | labels only | yes | yes | none; `MOVE_SCALE_NAME`/`NET_IDLE_NAME` (`:71-72`) are call-trace labels |
| other parity readers | `sp_death_probe.py:65-79`, `verdict_replay.py:140-149`, `online_match_ours.py:47, 1368, 1966-68, 2798`, `music_state_poll.py:146-171`, `scripts/parity/guest_probe_console.json` | no | r0001 literals | yes | none |
| matcher → carry | `tools_py/address_matcher.py:193, 573` puts each csv Name in `match.json`; `tools_py/carry_names.py:32, 45, 60` carries it unless it holds an 8-hex run or collides | yes | yes | no | a rename reaches r0004 only after `match.json` is regenerated; a name with 8 hex characters in a row is silently kept back |
| r0004 column | `tools_py/addresses_from_match.py` (`FIELDS`, by r0001 address) | no (its own field names) | yes | no | none |
| data via twin | `tools_py/data_via_twin.py:115-116, 181-190` | label | yes | no | the vote report's labels |
| toml across revisions | `tools_py/revision_toml.py:97, 605, 681` | label | yes | no | none: it moves the address after `@` and keeps the name |
| symbol matcher | `tools_py/ghidra_symbol_match.py:133` (`FUN_` or `thunk_FUN_` is renameable) | yes | yes | no | a renamed row stops being a candidate (hurdle 5) |
| profiler | `tools_py/hostprof_diff.py:64` counts generated code by a `FUN_`/`_FUN_` symbol prefix | yes | no | no | a renamed function is counted as runtime; the 6,921 `sub_`/named ones already are (A: 6,750 + 171) |
| HLE census | `tools_py/hle_constants.py:91` | label | yes | no | labels |
| Ghidra exporter | `ghidra_scripts/ExportPS2Functions.java:292, 398, 519, 638` | writes | yes | no | producer of the raw names; not in the build |

### 2.1 The toml: every key, and whether ps2xRecomp reads it (A, section `toml`)

| key | entries | carries | read by `config_manager.cpp`? | other readers |
|---|---|---|---|---|
| `[general].stubs` | 223 `name@addr` | name + address | **yes** (`:68-75`): the address stubs that start, **the name stubs every function of that name** (`ps2_recompiler.cpp:771-773`), the name picks the handler (223 of 223 resolve, A) | `HleStats.cpp` at run time; `revision_toml.py`; `hle_constants.py` |
| `[general].untracked_stubs` | 433 `name@addr` | name + address | **no** ("informational only", `recomp/socom2.toml:248-249`) | `revision_toml.py` |
| `[general].skip` | 0 | names or addresses | yes (`:77-84`) | — |
| `[patches].instructions` | 46 | instruction address + word | yes (`:86-126`) | `revision_toml.py` |
| `[mmio]` | 233 | instruction address → hardware register | yes (`:128-144`) | `revision_toml.py`, `resolve_mmio.py` |
| `[[jump_tables.table]]` | 31 tables (30 distinct bases), 1,019 entries | table address + targets | yes (`:146-245`) | `revision_toml.py` |
| `[performance].critical` | 460 names (415 `sub_*`) | names only | **no** | none (`revision_toml.py:33` says so too) |
| `[general]` scalars | `input`, `ghidra_output`, `output`, `single_file_output`, `patch_syscalls`, `patch_cop0`, `patch_cache` | paths / flags | yes | `build_revision.sh` rewrites three paths |
| `recomp/extra_functions.txt` | 1,619 bare addresses | addresses | via `fix_ghidra_csv.py` only | `translate_extras.py`, `find_*` tools |

Of the 656 selectors, 41 name an address that is no csv `Start` (9 `stubs`, 32 `untracked`), and none carries the
csv's own Name at its address (A: all 656 sit on `FUN_` rows or on no row).

## 3. The raw offsets a type would name (the list Goal 5 starts from)

Revision "both" means a per-revision column with a value for each; "r0001" means a literal applied to whatever image
runs, with no r0004 confirmation recorded beside it. The player actor block's word 0 is the vtable at 0x6691a0, whose
RTTI object names the class **`CZSealBody`** (A, section `offsets`), so every "actor" row is a `CZSealBody` field.

| offset | revision | file:line | what it addresses |
|---|---|---|---|
| +0x1c / +0x20 / +0x24 | both (0x1c, 0x1c) | `guest_addresses.py:128`; `verdict_core.py:69` (word indices 7-9); `verdict_replay.py:140`; `online_match_ours.py:296, 2798` | CZSealBody position x, y, z |
| +0x2e8 | both (0x2e8, 0x2e8) | `guest_addresses.py:126`; `guest_probe_console.json` | CZSealBody → skeleton root node pointer |
| +0x1368 / +0x136c | both (**moved**) | `guest_addresses.py:127`; `sp_death_probe.py:71`; `guest_probe_console.json` (r0001 only) | CZSealBody MoveScale (KNOWN §4) |
| +0x48 | r0001 | `sp_death_probe.py:76` | CZSealBody angular velocity |
| +0x70 | r0001 | `sp_death_probe.py:78` | CZSealBody quaternion |
| +0x80 (rows +0x80..+0xb0), +0xa0 / +0xa8 | r0001 | `sp_death_probe.py:79`; `online_match_ours.py:1368` | CZSealBody 4×4 matrix, row 2 x / z |
| +0xc8 | r0001 | `verdict_replay.py:143` | CZSealBody team word (meaning open) |
| +0x23c (+0x240, +0x244) | r0001 | `sp_death_probe.py:77` | CZSealBody scaled turn axis / velocity triple |
| +0x400 (peek base), +0x420 | r0001 | `verdict_core.py:889, 948` | CZSealBody position-apply timestamp |
| +0xf78 / +0xf7a | r0001 | `verdict_core.py:888`; `sp_death_probe.py:69`; `verdict_replay.py:142` | CZSealBody alive byte |
| +0xfb4 | r0001 | `sp_death_probe.py:70` | CZSealBody believed time of death (inference) |
| +0x1044 | r0001 | `sp_death_probe.py:68`; `verdict_replay.py:141`; `online_match_ours.py:1966` | CZSealBody health |
| +0x0c, +0x10, +0x14, +0x20, +0x24, +0x2c, +0x58, +0x5c, +0x70 | r0001 | `verdict_core.py:784-792` | `CZNetGame` (`*0x437ce8`, research/19 F2) valve slots |
| +0xde, +0x118, (+0x100 peek split) | r0001 | `verdict_core.py:75, 77, 976` | CZNetGame lag flag; the 50.0f fingerprint word |
| +0x1c, +0x3c, +0x40, span 0x80 | r0001 | `socom2_chat.h:12-15` | chat packet: originator name, type, message |
| +0x8c, +0x90; +0x04, +0x08 | r0001 | `socom2_chat.h:33, 35` | chat list run; its holder |
| +0x10, +0x58, +0x98, +0x9c, size 0xac | r0001 | `socom2_osk_prefill.h:36-42` | GetTextInput argument block (Purpose, SkbName, MaxBytes, MaxChars) |
| +0x0b, +0x1c, +0x28, +0x34 | r0001 | `game_overrides_socom2.cpp:1401-1430` | music manager (`musicManager` field's object) |
| +0x1c, +0x1d | r0001 | `game_overrides_socom2.cpp:1422` | music sound definition |
| +0x0c | r0001 | `game_overrides_socom2.cpp:1483` | RtNet config object (base port) |
| +0x2c8, +0x2cc, +0x330, +0x564 | r0001 | `game_overrides_socom2.cpp:1778-1788, 1996` | camera: LOD scale, 4×4, plane mask |
| +0xb4 | r0001 | `game_overrides_socom2.cpp:1995` | camera holder (`cameraHolder`) → camera |
| +0x04, +0x22, +0x24, +0x26 | r0001 | `game_overrides_socom2.cpp:1988` | camera configuration record |
| +0x5c, +0x5d, +0x88, +0x8c, +0x9c | r0001 | `game_overrides_socom2.cpp:1855-1858` | scene node flags, component presence, fade float |
| word 0x18 / 0x19 (+0x60 / +0x64) | r0001 | `game_overrides_socom2.cpp:1939-1940` | detail component's table and count |
| +0x04, +0x08, +0x0c, +0x10, +0x14 | r0001 | `game_overrides_socom2.cpp:2070-2079` | deferred draw list (base, bump, sentinel, head) |
| +0xa8 | loader (same in every pressing) | `game_overrides_socom2.cpp:2235` | newlib `_reent._rand_next` |

A's `offsets` section prints the 31 named-constant lines and the 24 distinct `<ptr> + 0x..` reads; the table adds the
comment-only and decimal ones it cannot match (`+ 4`, `+ 8`, `camera & mask) + 0x2c8`). **Data addresses outside the
tables** found on the way, r0001 literals applied to any image: the LOD globals `0x4b4a40`-`0x4b4ed8` in the detail
trace (`game_overrides_socom2.cpp:1926-1971`), the demux budget `0x451da8` in the generic `Kernel/Stubs/MPEG.cpp:1973`,
the music globals in `music_state_poll.py:146-171`, the valve name pointers in `verdict_core.py:784-793`, and the two
call-trace addresses in §2. A's `runtime` section counts the overlay-range literals per runtime file (79 in
`socom2_addresses.h`, 12 in `game_overrides_socom2.cpp` (the ten LOD-global reads above, the boot ELF's sreg table
0x1da6c0 in its bss, the overlay load base 0x1e7000), 3 `socom2_osk_prefill.h`, 1 each in `socom2_chat.h`,
`MPEG.cpp`, and two that are not addresses: `COP0_STATUS_BEV` in `ps2_runtime.cpp` and one word of the RSA modulus).

## 4. The readable-name impact, counted (A, sections `sanitise` and `behaviour`)

| name set | altered by the sanitiser that runs | by the unused variant | shared spelling | `_0x` filename cut | on the stub list | NEWLY stubbed | correctness-critical | 8-hex run |
|---|---|---|---|---|---|---|---|---|
| csv `Name` (14,879) | 9 (`_Exit`, `_LoadExecPS2`, `_EnableIntc` … → `ps2__…`) | 15 | 17 names / 48 rows | 0 | 8 (`sceSif*`, stubbed by name today) | — | 0 | 14,767 |
| 485 `Proposed` | 43 | 132 | 0 | 1 | 117 | 19 | 16 | 5 |
| 485 `Mangled` | 46 (9 also character-mapped) | 135 | 0 | 1 | — | — | — | — |
| 485 `readable(Mangled)` | **31** (`__muldi3`, `__ieee754_*`, `__kernel_*`, `_PES_packet`, `_Error`, six `__sinit_*`, `__TransferControl__F…`) | **121** | 2 names / 4 rows | 0 | 117 | **19** | 6 | 0 |

- The **19 newly stubbed** (A `--list`): `sceCdDiskReady` 0x18ed78, `sceSifFreeSysMemory` 0x1aabf0, `_sceVu0ecossin`
  0x1bff50 and sixteen `sceVu0*` matrix routines 0x1bfc30-0x1c07f8. Each is on `ps2_call_list.h`'s stub list, so the
  recompiler replaces the game's body with the runtime's `ps2_stubs::` function. 104 more proposals already sit on a
  `[general].stubs` address under the same name (no change).
- **A conflict with the toml:** the toml stubs `sceCdDiskReady@0x0018EF70`; Task 7 proposes `sceCdDiskReady` for
  0x18ed78 (`relinked-body`, 0.85). Applied, two addresses carry one handler name, and 0x18ed78 is stubbed by name.
  Goal 6's agreement test must refuse one of them.
- **carry_names' rule meets the overload suffix:** the readable names carry no 8-hex run, but the spec's default
  suffix (the mangled argument list) makes `C2DBitmapPoly_SetUV_ffffffff` from `SetUV__13C2DBitmapPolyFffffffff`, and
  `carry_names.py:32` would silently keep it from r0004. Over the demo's 607 colliding functions, 2 would hit
  (`__ct__7CMatrixF…`, the `SetUV` above; A, section `suffix`). research/48 finds the same `SetUV` loss among the
  469 names `match.json` carries.
- **readable() leaves 11 free functions mangled** (`_delete_vec__FPvPCci`, `QFromRot__FP5CQuatPC6CPnt3D`, …) and
  keeps `__sinit_` (so `__sinit_ent_main_cpp` stays reserved, correctness-critical by prefix, and becomes
  `ps2___sinit_…`): the spec's `sinit_<file>` rule is not in the sketch yet (A, section `suffix`: 11 and 6;
  research Q2's to decide).
- **Five different definitions of "auto name"** are in use: the recompiler's `sub_ FUN_ LAB_ DAT_`
  (`elf_parser.cpp:28`), the analyzer's `sub_ FUN_ func_ entry_ function_ LAB_` (`function_classifier.cpp:130`), the
  symbol matcher's `FUN_ thunk_FUN_` (`ghidra_symbol_match.py:133`), `carry_names`' any 8-hex run, and the spec's
  §1.3 `FUN_ LAB_ thunk_FUN_ caseD_ sub_ entry`. To the recompiler the 59 `thunk_*` and 42 `caseD_*` rows are
  authoritative names; to the spec they are placeholders.

## 5. Where this contradicts the spec or a note

1. Spec §1.1 and §6: the csv importer is `ElfParser::loadGhidraFunctionMap` (`elf_parser.cpp:959`), not
   `importGhidraMap`, which is dead. (Agrees with research/48's in-place supersession of §1.1; §6's pointer line
   still names `importGhidraMap` and `sanitizeIdentifier`.)
2. Spec §1.1 and 1.2 rule 3: the sanitiser that runs is `PS2Recompiler::sanitizeFunctionName`
   (`ps2_recompiler.cpp:2190`). It leaves `_lower…` unchanged and prefixes `ps2_` (not `ps2`) to `__x`, `_X` and
   keywords. "Returned unchanged" under it refuses 31 readable names; "no leading underscore" refuses 121.
3. Spec §1.1 (and research/44 hurdle 4's reason, still unsuperseded in that note): two rows with one sanitised
   spelling do not make two definitions of one symbol; every identifier ends `_0x<start>`, and 48 rows share 17
   spellings today. (research/48 superseded the spec's sentence; research/44 §2 hurdle 4 still gives the linker as
   the reason.)
4. Spec §5 ("no hook, probe or HLE path changes what it does"): applying the 485 as they stand changes the decoded
   range of 237 functions and stubs 19 more. research/48's supersession says "a rename can change a function's
   extent" without a count; the count is 237, and the stubbing is not in the spec at all.
5. Spec §1.1 "the name selects a runtime handler by string; it must agree with the csv name at that address": today
   no csv row agrees with its selector (0 of 656), and after the 485 one disagrees (`sceCdDiskReady`).
6. Spec §1.1 "`sanitizeIdentifier` prefixes `_` to a leading digit": true of `sanitizeIdentifierBody`; the copy that
   runs then keeps `_3…` as it is (neither `__` nor `_` + capital), and only the unused variant turns it into
   `ps2_3…`.
7. The brief's "62 hex literals" in `verdict_core.py` is 62 lines, 118 literals, 48 distinct values (E, A).

## 6. What the disk cannot answer, and what would

- **The effect of the 237 End changes on the generated code** (whether any branch now leaves its function to an
  address no function starts at, a `[guest-branch:missing-target]`): needs a recomp of the renamed tree and a diff of
  `recomp/output` and `recomp_run.log`'s `unmapped=` count against today's (the local proof window).
- **Whether the 19 newly stubbed runtime implementations match the game's bodies**: needs the gate on a build with
  them, or a decision to keep them recompiled (a `skip`-like exemption or the applier refusing stub-list names).
- **Which of the r0001-only offsets in §3 hold on r0004**: needs research Q5's DWARF walk plus the twin-displacement
  check `guest_addresses.py` records for `move_scale`, per field.

## What this means for a task

| task | finding | what it changes |
|---|---|---|
| Task 1 (the applier, Goal 1) | a rename of a `sub_`-emitted row moves its End to the csv End (237 of 485) | the proof bar must diff more than filenames: compare `unmapped=`/`unhandled=` from `build.sh recomp` before and after, and say so in the PROOF REQUESTED row |
| Task 1 | 19 proposals are on the runtime stub list and would be stubbed by name (`isStubFunction`) | the applier refuses a name `ps2_call_list.h` resolves unless a `[general].stubs` selector already binds that address, or the plan decides to accept the HLE with a gate run; a test pins the refusal |
| Task 1 / Q2 | the sanitiser that runs is `ps2_recompiler.cpp:2190`; it alters 31 readable names and leaves 90 more with a leading `_` alone | rule 3 is written against that function (replicated in Python, tested on `__x`, `_X`, `_x`, a keyword, `main`, a leading digit); "no leading underscore" is a style choice, not a legality one, and costs 121 names or a strip rule |
| Task 1 | identifiers are unique by their `_0x<start>` suffix; the filename is cut at 100 characters, keeping the suffix | uniqueness stays for grep, not the link; the 96-character cap can be 87 so no filename is ever cut |
| Task 1 / Goal 2 (sidecar audit) | five auto-name definitions disagree; the recompiler treats `thunk_*` and `caseD_*` as real names | the audit names its exemption list and a test pins it against `IsAutoGeneratedName` |
| Goal 6 (toml stubs) | `sceCdDiskReady` is 0x18ef70 in the toml and 0x18ed78 in Task 7; 9 selectors bind nothing (A = KNOWN §4's nine); `untracked_stubs` and `[performance]` are never read | the agreement test refuses the conflict; the toml-only names apply through the csv (the `sub_` naming is a tie-break on End, `elf_parser.cpp:1073-1094`, which a named csv row wins without any recompiler change, taking the csv End with it as in Task 1's row) |
| Q2 (readable names) | the default overload suffix can create an 8-hex run (`…_ffffffff`), which `carry_names` silently withholds; `readable()` leaves 11 `__F…` free functions and `__sinit_` | the suffix rule avoids 8 hex characters in a row (or `carry_names` tests the sidecar's `Pass`, not the spelling); the sketch gains the free-function and `sinit_` rules |
| Goal 5 (types) | the player actor is `CZSealBody` by RTTI; §3 lists 31 named offsets and 24 runtime reads, of which only 3 have an r0004 column | the ccc walk starts from `CZSealBody`, `CZNetGame`, the camera and the chat packet; each confirmed offset enters `guest_addresses.py` with its revision column |
| r0004 lane | the call-trace addresses (`env.sh:33`, `sim_walk_to_b.py:70`), the LOD globals (`game_overrides_socom2.cpp:1926-1971`) and `MPEG.cpp:1973` are r0001 literals outside every revision table | candidates for `socom2_addresses.h` / `guest_addresses.py` columns (KNOWN §4's defect class); no Sprint 12 task, a `LOCAL:` line for Sprint 11's owner |
| Goal 1 (D4 comments) | 11 citations of a proposal's `FUN_` address, on 9 lines in 6 files (A: `GS.cpp:1007`, `State.h:236`, `System.cpp:435`, `game_overrides_socom2.cpp:145, 171, 172, 256`, `music_state_poll.py:69`, `patch_istat.py:2`) | the rename commit updates those lines and nothing else; no code reads a generated identifier by name |
| profiler | `hostprof_diff.py:64` counts generated code by a `FUN_` prefix; 6,921 generated functions already escape it | switch it to the `_0x<hex>` suffix before the rename lands |
