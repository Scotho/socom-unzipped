# 44. The SOCOM 1 demo's debug symbols, carried onto our anonymous functions

Date: 2026-09-24. Sprint 11, Task 7 (U3). Read-only: two ELFs, one Ghidra table, one fingerprint. No
game was run, no server contacted, no Ghidra process started, and `recomp/socom2_ghidra.csv` is
**unchanged** — the renames this note measures are proposals in a git-ignored file, to be applied in a
separate reviewed step.

**The one-line answer: 987 of the demo's 9,703 named functions (10.2 %) place onto one of our 14,879
anonymous rows, 619 of them at a score high enough to rename on unreviewed. The names that land are the
whole Sony SDK and C runtime, and about 236 real engine routines — `CZSealBody`, `CMission`, `CZAnimMain`,
`CZNetwork`, `CHUD`, `CAiMap`, `CPnt3D`, `CQuat`, `CMatrix`, `CPacket`.** The ceiling is not the
matcher: 7,595 of the demo's functions (78 %) have no byte-identical counterpart anywhere in our image
at all, because SOCOM II is a year of edits later.

## 1. The inputs

| what | value |
|---|---|
| demo ELF | `game/demo_scus_972_05/SCUS_972.05`, 10,765,300 B, sha256 `00c9cee7f75b921fda1e848d04f64881b5a0b7841300591cac91371bb23d4f8a` (git-ignored; never committed) |
| its build | Metrowerks MIPS C 2.4.1 — debug format is Metrowerks/DWARF1-ish in `.debug` (5.1 MB) and `.line`, **not** STABS |
| its `.symtab` | 350,304 B: 21,894 symbols — 9,703 `STT_FUNC`, 10,182 `STT_OBJECT`. Every FUNC has a non-zero size; every one is in section `main` |
| its shape | `ET_EXEC`, EM_MIPS, one `PT_LOAD` at 0x00100000 (3,626,496 B) + a 4-byte `heap`. Symbol values are **absolute guest addresses**; no section bias is needed |
| its `.relmain` | `SHT_REL`, 115,142 entries — a Metrowerks link leaves its relocations in place |
| our image | `game/disc/socom2_game.elf` (r0001), four `PT_LOAD`s: 0x100000, 0x1D5000, 0x1E7000, 0x4C5380 |
| our table | `recomp/socom2_ghidra.csv`, 14,879 rows, 113 already named by hand, 51 with no bytes in any segment |

A second disc sits beside it, `game/demo_scus_973_68/SCUS_973.68` (the SOCOM II demo of 2003-08-18). It
is **stripped** — no symbol table — and is not used here.

### Why there is no Ghidra step

The brief's Step 2 (install `ghidra-emotionengine-reloaded` + `ccc` into `tools/ghidra`, headless-import
the demo, run `ExportPS2Functions.java`) was **skipped, deliberately**: everything Step 3 consumes is a
name, a start and a size, and the ELF's own `.symtab` already carries all three for all 9,703 functions.
A Ghidra import would have produced the same three columns after a CPU-heavy headless analysis pass, and
`ccc`'s value is the `.debug` section — types, locals, line numbers — which this task does not read.
`tools_py/elf_symbols.py` (94 lines, 8 tests) replaces it. When a later task wants the demo's *types* or
its *struct layouts*, the ccc route becomes the right one and this decision should be revisited.

## 2. The method

`tools_py/ghidra_symbol_match.py`. The passes are **Task 10's**, not a second implementation of them:
`tools_py/address_matcher.match` already answers "is this the same routine, relinked", and a second
answer that disagreed would be worse than no answer. The fingerprint is `tools_py/fingerprint.py` —
FNV-1a 64 over the instruction stream with every address-forming immediate zeroed (`lui`/`addiu`/`ori`
halves, the `j`/`jal` target, branch displacements) and every load/store displacement kept.

| pass | what it proves | score |
|---|---|---|
| `exact` | the fingerprint occurs exactly once in each image | 1.00 |
| `hash+callees` | it occurs more than once, but only one candidate calls the functions this one calls (through pairs already placed) | 0.95 |
| `relinked-body` | the same stream with the global-access displacements masked away too, unique on both sides at the same length, ties broken by callees then by a string anchor | 0.85 |
| `prefix` / `prefix+size` | **optional (`--prefix`)**: the first 16 instructions hash equal and are unique on both sides. Evidence about a *prologue*, not a body | 0.60 / 0.70 |

Two notes on the brief's wording:

* **"hash-plus-callee-count" is vacuous as written.** Inside a group that shares a fingerprint the
  callee *count* is necessarily identical — the hash zeroes the `jal` target but keeps the instruction —
  so counting callees can never split such a group. The matcher's pass 2 uses the callee *set*, mapped
  through the pairs pass 1 already proved. That is the same evidence in the only form that carries any.
* **A score, because a hash is worth what the stream under it is long.** A `jr $ra; nop` thunk
  fingerprints the same in every program ever compiled; it reaches the output only when it happens to be
  unique on both sides, and the score then says how little that is worth. The method score is multiplied
  by a length weight: 1.0 at ≥64 B, 0.8 at ≥32 B, 0.5 at ≥16 B, 0.25 below. A rename is only proposed at
  ≥0.80, which no prefix pair and no body under 64 bytes can reach.

The relocatable-image worry in the brief turned out not to bite: the demo is `ET_EXEC` with absolute
symbol values, so nothing needed rebasing. `.relmain` was still used, as a **check on the mask** — see §5.

## 3. The result

```
demo functions 9703, ours 14879, matched 987 (10.2%)
  by pass: exact 632, hash+callees 20, relinked-body 176, prefix 119, prefix+size 40
  score >= 0.80: 619
  collisions: 1 name on several addresses, 0 addresses under several names
```

* **Match count 987. Rate 10.2 % of the demo's functions; 6.6 % of our 14,879 rows.**
* All 987 land on a row that is still `FUN_xxxxxxxx` — not one collides with a name we set by hand.
* 619 proposals clear the rename line (478 `exact`, 126 `relinked-body`, 15 `hash+callees`), at 619
  distinct addresses.
* Where they land: 429 in the boot loader (0x100000–0x1D5000 — the Sony SDK and C runtime, which is
  byte-identical between the two games), 230 in FTSCore (0x1E7000–0x407000), 169 in ZSealEtc
  (0x4C5380–0x66A040), the rest spread by the prefix pass.

### Reproducing it

```
python -m tools_py.ghidra_symbol_match \
    game/demo_scus_972_05/SCUS_972.05 game/disc/socom2_game.elf recomp/socom2_ghidra.csv \
    --prefix --out game/demo_symbol_matches.json --renames game/demo_symbol_renames.csv
```

Three and a half seconds. Both outputs are under `game/`, which `.gitignore` excludes — 619 rows is well
past the ~200 that would belong in an appendix here, and neither file is committed.

## 4. The top 50 named engine functions, by size

"Engine" here means a Metrowerks-mangled C++ member or a `z…`/`hud…` free function — i.e. not `sce*`,
not `__ieee754*`, not the MPEG/IPU decoder, not libc. 236 of the 987 qualify. The address is **ours**.

| # | demo name | our address | size | pass | score |
|---|---|---|---|---|---|
| 1 | `ThrottlesPreTick__9CSealCtrlFP4CPadf` | 0x005966a0 | 1560 | prefix | 0.60 |
| 2 | `Open__18CActionTxtrMachineFUi` | 0x0021f850 | 1452 | prefix | 0.60 |
| 3 | `Init__8CMissionFv` | 0x002ad290 | 1328 | prefix | 0.60 |
| 4 | `Open__11CNodeActionFPQ23zdb6CWorldPCc` | 0x002b4f40 | 1132 | prefix | 0.60 |
| 5 | `RunEventAnim__10CMenuStateFPCcPCc` | 0x001f3bf0 | 1036 | prefix | 0.60 |
| 6 | `DrawFunc<11CDynGrenade>__2aiFQ22ai9LINE_TYPEffUi11CDynGrenade` | 0x00598860 | 784 | prefix | 0.60 |
| 7 | `Read__7CFileCDFPci` | 0x0039d960 | 768 | prefix | 0.60 |
| 8 | `SeqTick__10CZAnimMainFf` | 0x00269da0 | 636 | prefix | 0.60 |
| 9 | `CalcAlternateZoomedPos__10CUIMapCtrlCFP6CPnt3DRC8CCornersRC6CPnt3Df` | 0x0036d510 | 500 | prefix | 0.60 |
| 10 | `AddCallback__22CZBodyAnimCallbackListFPCcf` | 0x0028b270 | 472 | prefix+size | 0.70 |
| 11 | `GetCmd__10CZAnimMainFiPcb` | 0x0026aa30 | 460 | prefix | 0.60 |
| 12 | `GetNodePos__10CZSealBodyFPCQ23zdb5CNodeR6CPnt3Db` | 0x005df930 | 460 | prefix | 0.60 |
| 13 | `Format__11CUIVariableFP5_zrdrPci` | 0x003860f0 | 456 | prefix | 0.60 |
| 14 | `GetDirQuat__6CAiMapFQ26CAiMap3DIRR5CQuatb` | 0x00518ea0 | 444 | prefix | 0.60 |
| 15 | `_validate_cell__6CAiMapFRC18MAP_FOREACH_STRUCTPv` | 0x00517eb0 | 440 | prefix | 0.60 |
| 16 | `hudInit__Fv` | 0x001fdee0 | 428 | prefix | 0.60 |
| 17 | `ReadDeathAndFlinchAnims__7AnimSetFv` | 0x005a4840 | 424 | exact | 1.00 |
| 18 | `CreateSequence__12CSndSequenceFP5_zrdr` | 0x00349e90 | 424 | prefix | 0.60 |
| 19 | `__dt__18CHandlerButtonSpecFv` | 0x003880f0 | 356 | prefix | 0.60 |
| 20 | `ToEuler__7CMatrixCFP6CPnt3D` | 0x00308020 | 328 | prefix | 0.60 |
| 21 | `__dt__16CInGameWeaponSelFv` | 0x001fd8c0 | 324 | prefix | 0.60 |
| 22 | `__dt__8CMissionFv` | 0x00609810 | 316 | prefix | 0.60 |
| 23 | `__dt__15CZPlayerMapItemFv` | 0x00222190 | 284 | prefix | 0.60 |
| 24 | `RemoteSealDeletionCallback__11CZSealStateFii` | 0x002bef60 | 276 | prefix | 0.60 |
| 25 | `CreateCompassNavPoints__8CMissionFv` | 0x002acad0 | 272 | prefix | 0.60 |
| 26 | `SetRotate__7CMatrixFPC6CPnt3D` | 0x003083c0 | 272 | prefix | 0.60 |
| 27 | `__dt__10MapCompassFv` | 0x00212380 | 272 | prefix+size | 0.70 |
| 28 | `zNetSendApplicationMessage__9CZNetworkFciiiiPUcb` | 0x0030cef0 | 264 | prefix | 0.60 |
| 29 | `Destroy__10CZSealBodyFP10CZSealBody` | 0x005998b0 | 260 | prefix | 0.60 |
| 30 | `__dt__7CAiMapsFv` | 0x0052ea10 | 256 | prefix | 0.60 |
| 31 | `Draw__9CPlainBmpFRC7CMatrixPQ23zdb16CTextureRelocMgr` | 0x00379160 | 256 | prefix | 0.60 |
| 32 | `Flash__4CHUDFfRC6CPnt3Dfff` | 0x001f7e80 | 236 | prefix | 0.60 |
| 33 | `Init__14CFlyoutMachineFUi` | 0x003d5600 | 228 | prefix+size | 0.70 |
| 34 | `GetAction__11CNodeActionFPQ23zdb5CNodeb` | 0x005aa470 | 216 | prefix | 0.60 |
| 35 | `zAnimGetDirectionFromAzimuthZenith__FffP6CPnt3D` | 0x0025cb00 | 208 | prefix+size | 0.70 |
| 36 | `WriteGsMemory__6CVideoFUiP1Ui` | 0x003b18d0 | 192 | relinked-body | 0.85 |
| 37 | `IsInRange__12CZProjectileFPC6CPnt3Df` | 0x003c71d0 | 188 | prefix | 0.60 |
| 38 | `__ct__7CPacketFP7CPacketUiUi` | 0x0029dc30 | 180 | exact | 1.00 |
| 39 | `SeqSetState__10CZAnimMainFi` | 0x0026a040 | 172 | prefix | 0.60 |
| 40 | `Tick__7CTPaintFP14_zanim_cmd_hdrPf` | 0x005d5700 | 172 | prefix | 0.60 |
| 41 | `Mul__5CQuatCFPC5CQuatP5CQuat` | 0x003070c0 | 168 | exact | 1.00 |
| 42 | `Load__13C2DBitmapPolyFffffffffPQ23zdb8CTexture` | 0x00359590 | 164 | exact | 1.00 |
| 43 | `__dt__13CUIVarManagerFv` | 0x00385ce0 | 164 | prefix | 0.60 |
| 44 | `__dt__9CPlainBmpFv` | 0x001fdbe0 | 160 | prefix+size | 0.70 |
| 45 | `Cross__6CPnt3DCFPC6CPnt3DP6CPnt3Db` | 0x00592400 | 160 | prefix | 0.60 |
| 46 | `__as__13CDesignDlgObjFRC13CDesignDlgObj` | 0x0037d910 | 156 | prefix | 0.60 |
| 47 | `RegisterAnimCommands__10CftsPlayerFv` | 0x002b3930 | 152 | relinked-body | 0.85 |
| 48 | `SetUV__13C2DBitmapPolyFffffffff` | 0x00359140 | 144 | hash+callees | 0.95 |
| 49 | `SetPos__13C2DBitmapPolyFffffffff` | 0x00359490 | 144 | hash+callees | 0.95 |
| 50 | `__dt__13CDesignDlgObjFv` | 0x0037d9b0 | 144 | prefix | 0.60 |

Read the `pass` column: the big engine routines are nearly all `prefix`, which is the pass that says
"the prologue agrees and nothing else does" — exactly what you expect of a routine that SOCOM II
*edited*. They are in the table because the names are the most interesting thing the demo has to say;
they are at 0.60 because none of them should be written into the CSV without a human reading the body.

The largest matches overall are library, not engine, and they are what says the pipeline is sound:
`_getAllRefs` (1796 B, exact), `sceGsExecStoreImage` (1676 B, exact), `_printf` (1516 B, relinked-body),
`_PES_packet` (1456 B, exact), `__kernel_tan`, `__ieee754_acosf`, `sceGsSetDefDispEnv`, `sceCdRead`,
`sceSifCallRpc`, `sceMpegDemuxPssRing`, `strncmp`.

## 5. Collisions, and what says the pairings are real

**Collisions: 1.** One demo name, `_request_end`, lands on two of our addresses (0x1A67E8 and 0x1BD0A0)
— a `static` compiled into two translation units of the IOP-RPC glue, which is the benign kind. **Zero**
of our addresses sit under two demo names: the matcher takes each of our functions at most once, and
that is checked rather than assumed (`ghidra_symbol_match.collisions`, exercised by the tests).

Two independent checks that the fingerprint is doing what it claims:

1. **`.relmain` agrees with the mask.** Of the 106,763 relocated words that fall inside a demo function
   body, **106,581 (99.83 %)** are blanked either by `fingerprint`'s opcode rule or by the
   relinked-body mask. The heuristic mask and the linker's own record of what carries an address are
   the same set to within 182 words — which is why a relinked body fingerprints equal at all. (The mask
   is used rather than `.relmain` itself because our side has no relocation table, and a mask only one
   side applies proves nothing.)
2. **Class members cluster.** Of the 23 demo C++ classes with three or more matched members, 14 have
   every member inside a 256 KB window of our image — `CQuat` within 1 KB, `C2DBitmapPoly` within 1 KB,
   `CPacket` within 0, `CMatrix` within 35 KB, `CZAnimMain` within 44 KB. Random pairings do not do
   that. The classes that *do* spread (`CZSealBody` over 2.1 MB, `CMission` over 3.5 MB) spread among
   their **`exact`** matches too, so the cause is the compiler emitting an inline member into several
   translation units, not a bad match.

## 6. Why the other 89.8 % did not match

Every demo function falls into exactly one of three buckets by its plain fingerprint, and the later
passes then rescue some of each:

| its exact fingerprint in our image | demo functions | of those, placed |
|---|---|---|
| **absent** — the routine was edited between SOCOM 1 and SOCOM II, or is demo-only | 7,595 (78.3 %) | 304, all by the relinked-body or prefix pass |
| **present but ambiguous** — several of our rows wear it | 1,476 (15.2 %) | 51 |
| **present and unique on both sides** | 632 (6.5 %) | 632 |
| | 9,703 | **987 (10.2 %)** |

The ambiguity is overwhelmingly a *small-function* problem — 888 of the 1,476
are bodies of 16 bytes or less, the getters and the `jr $ra` thunks that every C++ program has a
thousand of. Only 60 ambiguous bodies are 64 bytes or more, and only 11 are 128 or more. **There is no
big win left in smarter disambiguation.** The ceiling is that SOCOM II is a different build of the game.

The prefix pass is where the remaining headroom is: it added 159 pairs (119 + 40) for a 64-byte
prologue hash, and 40 of those are at the same total length. Widening or narrowing that window, or
pairing on the prologue *and* a string anchor, is the obvious next lever — and it is worth it only
because the names it reaches are the engine ones.

## 7. What was delivered, and what was deliberately not

Delivered: `tools_py/elf_symbols.py` (+ 8 tests), `tools_py/ghidra_symbol_match.py` (+ 16 tests), this
note, and two git-ignored outputs under `game/`.

Not delivered, on purpose:

* **No rename was applied.** `recomp/socom2_ghidra.csv` is byte-for-byte unchanged. The 619 proposals
  are in `game/demo_symbol_renames.csv` (`Address, Current, Proposed, Score, How, Size`), git-ignored.
  Applying them is the brief's separate, reviewed step — and before it runs, someone should decide what
  to do with Metrowerks mangling: `Mul__5CQuatCFPC5CQuatP5CQuat` is a perfectly good identifier but an
  ugly one, and a demangler (or just `CQuat_Mul`) would read better in the recompiler's output.
* **No `ghidra_scripts/ImportDemoSymbols.java`.** See §1: it would have re-derived the three columns
  `.symtab` already holds. If a later task wants the `.debug` section's types, that script — and the ccc
  extension — become worth installing, and this is the note to reopen.
* **No demo bytes are in the repository**, here or anywhere else: names and addresses only.
