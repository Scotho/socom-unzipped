# 44. The SOCOM 1 demo's debug symbols, carried onto our anonymous functions

Date: 2026-09-24 (revised after review). Sprint 11, Task 7 (U3). Read-only: two ELFs, one Ghidra table,
one fingerprint. No game was run, no server contacted, no Ghidra process started, and
`recomp/socom2_ghidra.csv` is **unchanged** — the renames this note measures are proposals in a
git-ignored file, to be applied in a separate reviewed step.

**The one-line answer: 987 of the demo's 9,703 named functions (10.2 %) place onto one of our 14,879
anonymous rows, and 479 of those are safe enough to propose as renames. The names that land are the
whole Sony SDK and C runtime, and about 236 real engine routines — `CZSealBody`, `CMission`,
`CZAnimMain`, `CZNetwork`, `CHUD`, `CAiMap`, `CPnt3D`, `CQuat`, `CMatrix`, `CPacket`.** The ceiling is
not the matcher: 7,595 of the demo's functions (78 %) have no byte-identical counterpart anywhere in
our image at all, because SOCOM II is a year of edits later.

Every number below names the command that produces it. The two commands are:

```
# A -- the match, the proposals and the engine table (§3, §4, §7)
python -m tools_py.ghidra_symbol_match \
    game/demo_scus_972_05/SCUS_972.05 game/disc/socom2_game.elf recomp/socom2_ghidra.csv \
    --prefix --engine --top 50 --out game/demo_symbol_matches.json \
    --renames game/demo_symbol_renames.csv

# B -- the checks and the buckets (§5, §6): the same run with --verify
python -m tools_py.ghidra_symbol_match \
    game/demo_scus_972_05/SCUS_972.05 game/disc/socom2_game.elf recomp/socom2_ghidra.csv \
    --prefix --verify --top 0
```

Seven seconds with `--verify`, three and a half without. Both outputs are under `game/`, which
`.gitignore` excludes, and neither is committed.

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

(`python -m tools_py.elf_symbols game/demo_scus_972_05/SCUS_972.05` prints the first five rows.)

A second disc sits beside it, `game/demo_scus_973_68/SCUS_973.68` (the SOCOM II demo of 2003-08-18). It
is **stripped** — no symbol table — and is not used here.

### Why there is no Ghidra step

The brief's Step 2 (install `ghidra-emotionengine-reloaded` + `ccc` into `tools/ghidra`, headless-import
the demo, run `ExportPS2Functions.java`) was **skipped, deliberately**: everything Step 3 consumes is a
name, a start and a size, and the ELF's own `.symtab` already carries all three for all 9,703 functions.
A Ghidra import would have produced the same three columns after a CPU-heavy headless analysis pass, and
`ccc`'s value is the `.debug` section — types, locals, line numbers — which this task does not read.
`tools_py/elf_symbols.py` (205 lines, 13 tests) replaces it.

**Reopen this when a later task wants the demo's types, its struct layouts, or its translation units.**
The last of those is the sharpest: `ccc` recovers which source file each function came from, and a
translation unit is what the linker actually grouped, where §5's class-name clustering is only a guess
at it.

## 2. The method

`tools_py/ghidra_symbol_match.py`. The passes are **Task 10's**, not a second implementation of them:
`tools_py/address_matcher.match` already answers "is this the same routine, relinked", and a second
answer that disagreed would be worse than no answer. The fingerprint is `tools_py/fingerprint.py` —
FNV-1a 64 over the instruction stream with every address-forming immediate zeroed (`lui`/`addiu`/`ori`
halves, the `j`/`jal` target, branch displacements) and every load/store displacement kept.

| pass | what it proves | method score |
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
  by a length weight: 1.0 at ≥64 B, 0.8 at ≥32 B, 0.5 at ≥16 B, 0.25 below.

### What a proposal has to clear, and what a wrong one costs

The `Name` column of `recomp/socom2_ghidra.csv` is not a comment. `recomp/socom2.toml` feeds that table
to the recompiler, which makes the name **the generated function's C identifier and its output
filename** (`recomp/output/AddDmacHandler_0x1a3830.cpp`, `void entry_0x180008(…)`). A wrong name is then
inherited by every future reader and every address-table comment, with no record that it was a guess.

So a pair reaches `game/demo_symbol_renames.csv` only if **all six** of these hold — each is a separate
way for a rename to be wrong:

1. **score ≥ 0.80**, and
2. **body ≥ 64 bytes.** These are not the same rule, and the first alone is not enough: `exact` × the
   32-byte weight is `1.0 × 0.8 = 0.80` *exactly*, so the score line on its own admits eight-instruction
   bodies. At 64 bytes and up the weight is 1.0 and the score **is** the method's face value; below it
   the 0.80 is manufactured by the weighting. With both rules in force the lowest score in the file is
   in fact **0.85**. The pairs between the two rules are not thrown away — see §7.
3. **not a prefix pass**, at any length or any `--good`. The cut is clamped in code, not promised in
   help text: `--good 0.60` cannot put a prologue match in the file.
4. **not a colliding demo name.** One demo name on two of our addresses cannot be applied to both: one C
   `static` is not two functions, and two CSV rows sharing a `Name` give the recompiler two definitions
   of one symbol.
5. **our row is still `FUN_…`.** A function we named by hand keeps its name.
6. **a unique, legal C identifier.** Metrowerks mangling is not identifier-safe — templates carry `<`,
   `>` and `,`, an anonymous namespace carries `@`, a static initialiser is named after its source file
   (`__sinit_ent_main.cpp`) — and `<`/`>` are illegal in a Windows filename too. `c_identifier` maps
   every character outside `[A-Za-z0-9_]` to `_`, prefixes a leading digit, and cuts a name past 96
   characters with eight hex digits of SHA-1 of the original. The **mangled original is kept in its own
   `Mangled` column**, so nothing is lost. If two proposals sanitise to the same spelling, neither is
   written.

The relocatable-image worry in the brief turned out not to bite: the demo is `ET_EXEC` with absolute
symbol values, so nothing needed rebasing. `.relmain` was still used, as a **check on the mask** — §5.

## 3. The result

Command A, first six lines:

```
demo functions 9703, ours 14879, matched 987 (10.2%)
  by pass: exact 632, hash+callees 20, prefix 119, prefix+size 40, relinked-body 176
  collisions: 1 names on several addresses, 0 addresses under several names
  proposals: 479 (score >= 0.80 AND body >= 64 bytes)
    held back: body under 64 bytes                138
    held back: colliding demo name                2
    held back: prefix pass                        159
    held back: score below 0.80                   209
```

* **Match count 987. Rate 10.2 % of the demo's functions; 6.6 % of our 14,879 rows.**
* All 987 land on a row that is still `FUN_xxxxxxxx` — not one collides with a name we set by hand.
* **479 proposals** (338 `exact`, 126 `relinked-body`, 15 `hash+callees`), at 479 distinct addresses
  under 479 distinct identifiers, 9 of them sanitised from a template, an anonymous namespace or a
  `__sinit_*.cpp`.
* Where the 987 land: 429 in the boot loader (0x100000–0x1D5000 — the Sony SDK and C runtime, which is
  byte-identical between the two games), 230 in FTSCore (0x1E7000–0x407000), 169 in ZSealEtc
  (0x4C5380–0x66A040), the rest spread by the prefix pass.

## 4. The top 50 named engine functions, by size

Command A's table, verbatim (`--engine --top 50`). "Engine" is `ghidra_symbol_match.is_engine`: a
Metrowerks-mangled C++ member (`name__<len><Class>F<args>`) or a `z…`/`hud…` free function — so not
`sce*`, not `__ieee754*`, not the IPU/MPEG decoder, not libc. 236 of the 987 qualify. The address is
**ours**.

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
**none of them is a proposal**, and none can become one.

The largest matches overall are library, not engine, and they are what says the pipeline is sound
(drop `--engine` to see them): `_getAllRefs` (1796 B, exact), `sceGsExecStoreImage` (1676 B, exact),
`_printf` (1516 B, relinked-body), `_PES_packet` (1456 B, exact), `__kernel_tan`, `__ieee754_acosf`,
`sceGsSetDefDispEnv`, `sceCdRead`, `sceSifCallRpc`, `sceMpegDemuxPssRing`, `strncmp`.

## 5. Collisions, and what says the pairings are real

**Collisions: 1.** One demo name, `_request_end`, lands on two of our addresses (0x1A67E8 and 0x1BD0A0)
— a `static` compiled into two translation units of the IOP-RPC glue, which is the benign kind. **Both
rows are held out of the proposals file** (`held back: colliding demo name 2`), because one of the two
is wrong by construction and which one is not knowable here. **Zero** of our addresses sit under two
demo names: the matcher takes each of our functions at most once, and that is checked rather than
assumed (`ghidra_symbol_match.collisions`, exercised by the tests).

Two independent checks that the fingerprint is doing what it claims, both from command B:

1. **`.relmain` agrees with the mask.**

   ```
   relocated words inside a demo function body: 106763; blanked by the mask: 106581 (99.83%)
   ```

   The heuristic mask and the linker's own record of what carries an address are the same set to within
   182 words — which is why a relinked body fingerprints equal at all. (The mask is used rather than
   `.relmain` itself because our side has no relocation table, and a mask only one side applies proves
   nothing.)

2. **Class members cluster.** `classes with >=3 matched members: 23; all members within 256 KB: 14` —
   `CQuat` within 1 KB, `C2DBitmapPoly` within 1 KB, `CPacket` within 0, `CMatrix` within 35 KB,
   `CZAnimMain` within 44 KB. Random pairings do not do that. The classes that *do* spread
   (`CZSealBody` over 2.1 MB, `CMission` over 3.5 MB) spread among their **`exact`** matches too, so the
   cause is the compiler emitting an inline member into several translation units, not a bad match.
   Note the limit of this check: a class name is a guess at a translation unit, not the unit itself —
   which is the strongest argument for the ccc route in §1.

## 6. Why the other 89.8 % did not match

Command B's buckets. Every demo function is in exactly one, by what its plain fingerprint can see:

```
exact-fingerprint buckets (demo functions, of those placed):
  absent      7595  placed 304
  ambiguous   1476  placed 51
  unique       632  placed 632
ambiguous by body size: {'total': 1476, '<=16': 1108, '>=64': 60, '>=128': 11}
```

| its exact fingerprint in our image | demo functions | of those, placed |
|---|---|---|
| **absent** — the routine was edited between SOCOM 1 and SOCOM II, or is demo-only | 7,595 (78.3 %) | 304, all by the relinked-body or prefix pass |
| **present but ambiguous** — several of our rows wear it | 1,476 (15.2 %) | 51 |
| **present and unique on both sides** | 632 (6.5 %) | 632 |
| | 9,703 | **987 (10.2 %)** |

The ambiguity is overwhelmingly a *small-function* problem — **1,108 of the 1,476 are bodies of 16 bytes
or less**, the getters and the `jr $ra` thunks that every C++ program has a thousand of. Only 60
ambiguous bodies are 64 bytes or more, and only 11 are 128 or more. **There is no big win left in
smarter disambiguation.** The ceiling is that SOCOM II is a different build of the game.

The prefix pass is where the remaining headroom is: it added 159 pairs (119 + 40) for a 64-byte
prologue hash, and 40 of those are at the same total length. Widening or narrowing that window, or
pairing on the prologue *and* a string anchor, is the obvious next lever — and it is worth it only
because the names it reaches are the engine ones.

## 7. The 138 on the line, and what they expose

138 pairs clear the score (0.80) but not the 64-byte body rule, so they are **counted, kept in
`game/demo_symbol_matches.json`, and not proposed**. They deserve their own paragraph because the
argument for holding them back is the same argument that says the whole method has a limit.

* **Why they clear the score.** All 138 are `exact` — one fingerprint, one occurrence in each image —
  on a body of 32 to 63 bytes, 25 of them at exactly 32 (eight instructions).
* **Why that is thinner than it looks.** Uniqueness here is measured *within each table*, and the two
  tables are different sizes (9,703 against 14,879). Pass 1 cannot be fooled by a duplicate — it takes
  a pair only when the hash occurs exactly once on *each* side — but it has no way to see a routine
  SOCOM II **deleted**. If such a routine's hash is unique in the demo, and some unrelated eight-
  instruction body of ours is unique in ours, and the two masked streams coincide, the pair is taken and
  nothing in the pass can tell that from a real survival. The body-length rule is the whole defence, and
  at 32 bytes there is not much stream for a coincidence to have to survive.
* **What they actually are, in this run.** Read by hand: overwhelmingly boot-loader SDK and runtime —
  `_dpfgt`, `_dpflt`, `mwInit`, `memclr`, `sceDmaSync`, `sceDmaGetChan`, `__ptmf_scall` — code that is
  byte-identical between the two games because Sony shipped it, not because the matcher guessed well.
  The realised risk is low. But that is a fact about *this run*, not a property of the tool, which is
  precisely why it is written here and not assumed by the code.

To propose them anyway, someone has to lower `PROPOSE_MIN_SIZE` in the source and say so in a commit
message. `--min-size` on the command line is clamped upward only.

## 8. What was delivered, and what was deliberately not

Delivered: `tools_py/elf_symbols.py` (+13 tests), `tools_py/ghidra_symbol_match.py` (+44 tests), this
note, and two git-ignored outputs under `game/`.

Not delivered, on purpose:

* **No rename was applied.** `recomp/socom2_ghidra.csv` is byte-for-byte unchanged. The 479 proposals
  are in `game/demo_symbol_renames.csv` (`Address, Current, Proposed, Mangled, Score, How, Size`),
  git-ignored. Applying them is the brief's separate, reviewed step. `Proposed` is guaranteed to be a
  legal C identifier and a legal filename, and unique within the file; `Mangled` keeps the demo's own
  spelling so a demangler can be run later. What still needs a human decision is *style*, not validity:
  `Mul__5CQuatCFPC5CQuatP5CQuat` is a perfectly good identifier and an ugly one, and `CQuat_Mul` would
  read better in the recompiler's output.
* **No `ghidra_scripts/ImportDemoSymbols.java`.** See §1.
* **No demo bytes are in the repository**, here or anywhere else: names and addresses only.
