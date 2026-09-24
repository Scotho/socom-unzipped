# 60. Vtable slots through RTTI: the `vtable-slot` lever as shipped (Task 7c)

Date: 2026-09-24. Sprint 12 Task 4 (`docs/superpowers/plans/2026-09-24-sprint-12.md`), the spec's Goal 3 as
amended by S12-R16, built on the measurement in `docs/research/51-vtable-coverage.md`. The lever is
`tools_py/vtable_lever.py`, its own module with its own CLI. Its tests are `tools_py/tests/test_vtable_lever.py`
and its output is `game/demo_symbol_renames_7c.csv` (git-ignored). The lever only reads: it writes that one
proposals file, nothing under `recomp/` changed, no game was run, and no image bytes are in this note (names,
addresses and counts only).

**The short answer.** The demo's own qualified RTTI string, plus the layout filter, resolves **211** of the
demo's 248 `__vt__` classes to **228** retail vtables (211 primaries and 17 paired secondaries). These are
research/51's numbers, reproduced by the shipped code. Under the shipped reading ("whole + shared") the rule
proposes **363** rows before the hurdles and writes **199**. **15** of those confirm a Task 7 `prefix` pair
under the same name (S12-R3's second signal). The leave-one-out holdout over the **88** fixed points
re-derives **37** of them, **37 right and 0 wrong**. **0** proposals disagree with any Task 7 pair or with any
row of Task 7's or 7b's file. The one caveat to carry: **148** of the 236 slot namings behind the 199 rows sit
in equal-count vtables that have no body-matched fixed point, and the holdout cannot test those.

Every number below names the command that produces it:

```
# A -- the lever: resolution census, the four readings, the shipped census, the holdout by fixed point,
#      the top classes, the csv rows inside vtable data; writes the proposals file.  About 4 s.
python -m tools_py.vtable_lever game/demo_scus_972_05/SCUS_972.05 game/disc/socom2_game.elf \
    recomp/socom2_ghidra.csv game/demo_symbol_matches.json \
    --out game/demo_symbol_renames_7c.csv --holdout --data-rows

# B -- A with every secondary vtable refused (what pairing secondaries adds)
python -m tools_py.vtable_lever game/demo_scus_972_05/SCUS_972.05 game/disc/socom2_game.elf \
    recomp/socom2_ghidra.csv game/demo_symbol_matches.json --primary-only

# C -- research/51's measurement script, for the comparison figures
python tools_py/research/symbols/vtable_coverage.py

# T -- the synthetic-image suite (26 tests; no disc, no demo)
python -m unittest tools_py.tests.test_vtable_lever
```

Inputs are the ones research/51 used. The demo is `SCUS_972.05`; ours is r0001's `socom2_game.elf` with
`recomp/socom2_ghidra.csv`. Task 7's pairs come from `game/demo_symbol_matches.json`, and Task 7's and 7b's
proposals files (`game/demo_symbol_renames.csv`, 479 rows, and `…_7b.csv`, 6 rows) supply the "already
named" rows and the spent identifiers.

## 1. The rule as shipped

`VTABLE_RULE` in `tools_py/vtable_lever.py`, written verbatim into the file's `#` header by
`write_proposals_7c` (the function writes it itself, so no file of this shape can leave it out):

1. **Resolve** (`resolve_classes`). The key is the demo class's own RTTI string: the demo's `__RTTI__` object
   → its name string, which is the qualified name (`zdb::CNode`, `std::ctype<char>`). When the demo's RTTI
   word is 0 (8 classes), the key is read from the mangling. The lookup runs `"\0name\0"` in retail → the
   aligned words pointing at the string (RTTI objects) → the aligned words pointing at those. A word is kept
   only if it is a **vtable head by the layout**: word 1 is zero (a primary) or a negative this-offset (a
   secondary), and the words after it are csv function starts. A head needs ≥ 2 such slots, or 1 when it
   lies inside the span the ≥ 2-slot vtables occupy (±0x100, research/51 §1). A base-list word also points
   at an RTTI object; the layout drops it.
   - One retail primary is required; several are refused.
   - The demo's secondary (the second header inside its `__vt__` object) pairs with retail's secondary by
     the header word, and only when each side holds exactly one.
2. **Align** (`align_slots`). A vtable's slots are the consecutive function-start words after the header,
   stopping at the first word that is not a csv function start (a 0 word is a pure virtual). The fixed
   points are the **vtable start** plus every slot whose demo target and our target are a **proved**
   (non-prefix) Task 7 pair, kept as a strictly increasing chain. A run between two fixed points, or after
   the last one, is named by position only when it has equal length on both sides. So an equal-count
   vtable with no body-matched fixed point is named whole.
3. **Hurdles** (`propose`). Each refusal is counted:
   - one name per row, and one row per name;
   - our csv row is still a placeholder (`name_provenance.is_placeholder`);
   - a row already in Task 7's or 7b's file is skipped, and its agreement is counted;
   - a Task 7 pair under a **different** name is refused and printed as a finding;
   - a shared body (one of our rows in ≥ 2 retail vtables) is admitted only when ≥ 2 vtables name it, and
     name it alike;
   - body ≥ 64 B and size ratio ≥ 0.50 (`symbol_levers.MIN_BODY` / `SIZE_RATIO`, unchanged);
   - a unique legal identifier (`c_identifier` on the mangled name), checked against this file, Task 7's
     and 7b's `Proposed` columns and the csv's own non-placeholder names (A: 547 identifiers already spent).
4. **Constructors are not proposed.** S12-R16 withdrew rule 4. research/51's variant C is ~150 lines of MIPS
   scanning and its recall question is still open, so it is not repeated here; C §7 prints it (ours 87
   exactly-one, demo 22 of 23).

Three choices were made where research/51 or the brief left one:

- **The reading is "whole + shared"** (research/51 §6, its fourth row), as S12-R16 (2) and (3) rule.
- **Secondaries are paired**, as research/51's 169 / 184 assume. B shows what refusing them costs: 17
  vtables and 5 rows (**194** instead of 199).
- **A Task 7 pair that is not in Task 7's file and carries the same name is admitted.** research/51 refused
  every Task 7 row as "already named" (its 16). S12-R3 names a vtable slot as the second signal that lets a
  `prefix` pair reach a proposals file, and all 16 of those rows are `prefix`/`prefix+size` pairs that the
  slot names identically (§5). This is the whole difference between research/51's 184 and this file's 199:
  184 + 16 − 1 (the one that then fails the ratio) = 199.

## 2. Resolution (A, first two lines)

| bucket, per demo `__vt__` class | classes |
|---|---|
| one retail primary, no secondary | 191 |
| one primary + secondary(ies) | 20; secondary paired 17, refused 3 (the demo has the primary only: research/51's `CRadioStrip`, `CHandlerButton`, `C2DButton`) |
| several primaries: refused (`zdb::CNodeEx`) | 1 |
| secondary only: refused (`CUIVarManager`, its primary has no slot) | 1 |
| string present, no vtable by the layout: refused (`CIO` all pure virtual, `CSaveModule`) | 2 |
| absent: no string (research/51's 32 dropped classes + `CBmpWithNode`, whose qualified string retail lacks) | 33 |
| **total / resolved** | **248 / 211** (228 vtables) |

Retail holds 292 vtables by the layout, over 268 class names; research/51 §1 has the same figures. The fixed
points use 821 proved Task 7 pairs out of the JSON's 987 (exact 629, hash+callees 20, relinked-body 176;
prefix 119 and prefix+size 40 are not fixed points). 3 pairs were dropped because their demo name sits on
several demo addresses, which research/51's script also does. 4 more were dropped because their address is
held in `recomp/socom2_name_holds.csv` (`--holds`, S12-R20): none of the 4 was a fixed point, and the file's
199 rows are identical with and without the holds.

## 3. The four readings (A, "the readings"; research/51 §6 for comparison, C)

| reading | proposed | named here | research/51 named (C) | holdout: fixed points / reached / right / wrong |
|---|---|---|---|---|
| strict (rule 2 as written) | 50 | 13 | 11 | 88 / 12 / 12 / 0 |
| start (the start is a fixed point) | 122 | 73 | 67 | 88 / 37 / 37 / 0 |
| whole (+ equal-count vtables named whole) | 363 | 180 | 169 | 88 / 37 / 37 / 0 |
| **whole + shared (shipped)** | **363** | **199** | 184 | 88 / 37 / 37 / 0 |

"Proposed" is identical to research/51's in every row. "Named" differs only by the admitted Task 7 prefix
pairs (§1, third choice).

## 4. The shipped file (A, "shipped reading")

| stage | count |
|---|---|
| vtables / with a fixed point / named whole (no fixed point) | 228 / 70 / 82 |
| demo slots / retail slots | 2,324 / 2,858 |
| slots in equal runs | 505 (the demo slots in unequal runs, counted over every vtable including those with no fixed point: 1,731; research/51 counts only runs a fixed point bounds, 705) |
| fixed points / conflicting | 88 / 0 |
| **distinct rows proposed** | **363** |
| refused: body under 64 bytes | 130 |
| refused: size ratio under 0.50 | 21 |
| refused: a shared body that one vtable names | 12 |
| refused: a shared body named differently | 1 (0x001f3b20: `CExitMenu` slot 1 → `MyTick__9CGameMenuFf`, `CLoadMenu` slot 1 → `MyTick__9CLoadMenuFf`) |
| refused: our row not a placeholder / already in Task 7's or 7b's file / contradicts a Task 7 pair / identifier | 0 / 0 / 0 / 0 |
| **written** | **199** rows at `Score` 0.75, `How` `vtable-slot` |
| of them, a shared body that ≥ 2 vtables name alike | 19 |
| of them, confirming a Task 7 prefix pair | 15 |

What the 199 rows rest on, counted per naming vtable (236 namings: a shared row is named by each of its
vtables): **148** are a whole vtable with no fixed point, **60** come before the first fixed point, and **28**
come after a fixed point.

Top 20 classes by slots named (A):

| slots | class | slots | class |
|---|---|---|---|
| 11 | `std::basic_filebuf<char, …>` | 4 | `CDIDummy` |
| 11 | `std::basic_filebuf<wchar_t, …>` | 4 | `CGame` |
| 8 | `std::ctype<wchar_t>` | 4 | `CHudBrightText` |
| 8 | `zdb::CLight` | 4 | `CZLineMap` |
| 7 | `zdb::CLightMap` | 4 | `std::basic_streambuf<char, …>` |
| 7 | `zdb::CRenderMap` | 4 | `std::basic_streambuf<wchar_t, …>` |
| 6 | `zdb::CDIPoly` | 3 | `CClockSpec` |
| 5 | `C2DMessageString` | 3 | `CCounterSpec` |
| 5 | `zdb::CDIBBox` | 3 | `CHandlerButtonSpec` |
| 4 | `C2DString` | 3 | `COurGame` |

## 5. Against Task 7: agreements, disagreements

- **Rows of Task 7's or 7b's file that the rule reaches: 0.** No slot run covers any of the 485 rows already
  proposed. research/51's "already named 16" were all Task 7 pairs outside the files.
- **Task 7 pairs the rule reaches: 16, all prefix pairs, and 16 of 16 carry the same name. There are 0
  disagreements.** These are out of sample: a prefix pair is never a fixed point. 15 are written (A,
  `CONFIRMS`): `__dt__Q23std8ios_baseFv`, `xsputn`/`xsgetn` of `std::basic_streambuf<char>`, `overflow`/`uflow`
  of `std::basic_filebuf<char>`, `__dt__Q23std11logic_errorFv`, `__dt__15CZPlayerMapItemFv`,
  `Read__Q23zdb3CDIFRQ23zdb9CSaveLoad`, `__dt__Q23zdb9CLightMapFv`, `_Copy__Q23zdb6CLightCFPQ23zdb5CNode`,
  `FindChild__Q23zdb5CNodeFPCcb`, `__dt__10CImageSpecFv`, `__dt__18CHandlerButtonSpecFv`,
  `__dt__11SystemTunerFv`, `__dt__Q23zdb7CVisualFv`.
- The 16th, `Serialize__8CMissionFi` at 0x002a6340 (A, `NOTE`), agrees by name but is refused on the size
  ratio: the demo body is 140 B and ours is 1,552 B (ratio 0.09). It is the 0.090 at the bottom of
  `symbol_levers`' size-ratio calibration. The slot confirms the identity that the ratio doubts. The row is
  held back, and it is the obvious case for a reviewer.
- Row 478 (S12-R9) and `setD3_CHCR` (S12-R13) are not virtual functions and are not reached.

## 6. The holdout (A, `--holdout`)

The method is leave-one-out over the fixed points (research/45 §3's shape, research/51's method): drop one,
re-derive it by position from the rest, compare. **88 fixed points: 37 re-derived, 37 right, 0 wrong, 51 not
reached.** A fixed point is not reached when dropping it leaves an unequal run. The 37 are listed one per line
by A: 30 at the same index on both sides (e.g. the `*Spec` classes' slot 3) and 7 shifted by +3 or +5 where
the base gained virtuals (e.g. `C2DMessageString` demo 27 → ours 32, `CZSealBody` 14 → 17, `CFlashFX` 19 → 24).

Two limits, each one-directional and to be read with the result:
- **It is an upper bound.** A fixed point is a body Task 7 could match, one that survived nearly intact.
- **It cannot speak for the 148 whole-vtable namings**, which rest on the equal slot count alone. The
  evidence for those is research/51's: in the equal-count vtables that do have fixed points, 29 of 29 sit at
  the same index on both sides (C, "all opened"). The 16 of 16 name agreements in §5 are a second,
  out-of-sample check that does reach them. Of the 15 written confirmations, 9 include a whole-vtable naming
  (`start..end` in `FixedPoints`), 4 come before a fixed point (`start..3:3`) and 2 after one (`6:6..end`).
  (A, the `fixed points` field of each `CONFIRMS` line.)

The stop rule (a non-zero wrong count means the file is not applied) is not triggered.

## 7. The 64 csv rows that start inside vtable data (A, `--data-rows`)

`recomp/socom2_ghidra.csv` exports these as functions, but they are data: they start inside the spans the
vtables occupy. 60 start on a vtable's own header or slot words; the other 4 (0x001d4f90, 0x00406740,
0x00408000, 0x006690c0) start on other words in those spans, not on a vtable head. research/51 §1 notes
RTTI objects and base lists in these areas; which of those these four are was not checked.
Several are enormous: the 0x404f60–0x4083d0 rows each run ~0.78 MB, to the next csv row past the whole data
area, and the 0x1d4fxx rows ~73 KB. The rule is unaffected, because no retail slot word points at any of
them (research/51 §1), but "a csv start" is not proof that a word is code.

| start | csv name | vtable at that word |
|---|---|---|
| 0x001d4f90 | FUN_001d4f90 | – |
| 0x001d4fc0 | FUN_001d4fc0 | std::bad_exception |
| 0x001d4ff0 | FUN_001d4ff0 | std::locale::facet |
| 0x00404f60 | FUN_00404f60 | CCoreState |
| 0x00405060 | FUN_00405060 | CLoadState |
| 0x004051c0 | FUN_004051c0 | CZActionBitmap |
| 0x00405400 | FUN_00405400 | CZClaymoreMapItem |
| 0x004054b0 | FUN_004054b0 | @unnamed@hud_newhudmap_cpp@::COverlayLine |
| 0x00405990 | FUN_00405990 | @unnamed@hud_scorepopup_cpp@::CScorePopup |
| 0x00405a00 | FUN_00405a00 | @unnamed@hud_scorepopup_cpp@::CHudPopups |
| 0x00405fd0 | FUN_00405fd0 | zar::CZAR |
| 0x00406000 | FUN_00406000 | zdb::CNodeEx |
| 0x00406030 | FUN_00406030 | CZAnimArgInt |
| 0x00406060 | FUN_00406060 | CZAnimArgValve |
| 0x004060e0 | FUN_004060e0 | CZBodyAnim |
| 0x004062d0 | FUN_004062d0 | CSealCtrlCopy |
| 0x00406600 | FUN_00406600 | zdb::CCell |
| 0x00406650 | FUN_00406650 | zdb::CDI |
| 0x004066d0 | FUN_004066d0 | TransientGame |
| 0x00406730 | FUN_00406730 | CSMGetServerList |
| 0x00406740 | FUN_00406740 | – |
| 0x00406800 | FUN_00406800 | zdb::CLightMap |
| 0x00406850 | FUN_00406850 | zdb::CLight |
| 0x00406bb0 | FUN_00406bb0 | CSndQueueEntry |
| 0x00406c10 | FUN_00406c10 | zdb::CBatchRelocator |
| 0x00406e80 | FUN_00406e80 | C2DBitmap |
| 0x00407050 | FUN_00407050 | @unnamed@zui_2d_cpp@::CListItemImageTypeImpl |
| 0x00407140 | FUN_00407140 | @unnamed@zui_2d_cpp@::CListItemWrappedTextTypeImpl |
| 0x00407550 | FUN_00407550 | CHProgressBar |
| 0x004075c0 | FUN_004075c0 | CHProgressBar (secondary) |
| 0x00407700 | FUN_00407700 | CHandlerButton |
| 0x0040777c | FUN_0040777c | CHandlerButton (secondary) |
| 0x00407820 | FUN_00407820 | C3StateButton |
| 0x004079e0 | FUN_004079e0 | CWrappedText |
| 0x00407a70 | FUN_00407a70 | CWrappedText (secondary) |
| 0x00407b40 | FUN_00407b40 | @unnamed@zui_2d_cpp@::CListItemStringTypeImpl |
| 0x00407d40 | FUN_00407d40 | CUIMapCtrlSpec |
| 0x00407dd0 | FUN_00407dd0 | CHProgressBarSpec |
| 0x00407ef0 | FUN_00407ef0 | CSecureTextSpec |
| 0x00408000 | FUN_00408000 | – |
| 0x00408010 | FUN_00408010 | CHeadsetTuner |
| 0x004080a0 | FUN_004080a0 | CBmpWithNode |
| 0x00408110 | FUN_00408110 | CBmpWithNode (secondary) |
| 0x00408180 | FUN_00408180 | CFileIO |
| 0x004081f0 | FUN_004081f0 | CMemCardIO |
| 0x00408250 | FUN_00408250 | CTurret |
| 0x004082c0 | FUN_004082c0 | CVehicle |
| 0x00408330 | FUN_00408330 | zdb::CSubMesh |
| 0x00408350 | FUN_00408350 | zdb::CMesh |
| 0x004083d0 | FUN_004083d0 | CZProjectile |
| 0x006690c0 | FUN_006690c0 | – |
| 0x00669180 | FUN_00669180 | CBasicPlanner |
| 0x006691a0 | FUN_006691a0 | CZSealBody |
| 0x00669210 | FUN_00669210 | CZSealBody (secondary) |
| 0x00669590 | FUN_00669590 | CRemoteCtrl |
| 0x006697c0 | FUN_006697c0 | CAiSSuspended |
| 0x006698b0 | FUN_006698b0 | CAiSGoto |
| 0x006699a0 | FUN_006699a0 | CAiSFollow |
| 0x00669ab0 | FUN_00669ab0 | CAiSHostage |
| 0x00669b00 | FUN_00669b00 | CAiSAvoid |
| 0x00669c90 | FUN_00669c90 | CAiSEvent |
| 0x00669d80 | FUN_00669d80 | CAiSSurrender |
| 0x00669e70 | FUN_00669e70 | CAiSShotAt |
| 0x00669f40 | FUN_00669f40 | CAiGroup::act_sound |

## 8. What was delivered, and what was not

- `tools_py/vtable_lever.py`, containing:
  - `Image`, `layout_census`, `vtable_regions`, `demo_classes`;
  - `resolve_classes`, `fixed_points`, `align_slots`, `predict`, `holdout`;
  - `propose`, `write_proposals_7c`, `load_pairs`, `data_rows`, `main`;
  - `VTABLE_RULE`, `PROPOSAL_COLUMNS_7C`, `HOW`, `SCORE`.
- `tools_py/tests/test_vtable_lever.py`: 26 tests on synthetic images, covering
  - resolution: one class to one vtable; a base-list word dropped; a positive word 1 dropped; a pure-virtual
    zero stopping the count; two primaries refused; a secondary pairing by the header; an absent class;
  - alignment: the fixed point at slot 1 naming slots 0 and 2; an unequal run refused; a whole vtable; the
    strict reading;
  - hurdles: a shared body admitted and refused both ways; a row already in a Task 7 file; a Task 7
    disagreement; a prefix pair confirmed; a non-placeholder row; < 64 B; ratio < 0.50; a spent identifier;
    a template identifier;
  - holdout: right, and wrong;
  - file: the header and columns; the NO-DATA path.
- `game/demo_symbol_renames_7c.csv`, git-ignored: 199 rows, the rule, the reading, the anchors, the holdout
  and the census in its `#` lines.
- Not delivered: no rename applied (Task 3's applier), no constructor pass, no change to `symbol_levers.py`
  or `ghidra_symbol_match.py`.

## What this means for a task

| task | finding | what it changes |
|---|---|---|
| Task 3 (applier) | `game/demo_symbol_renames_7c.csv` holds 199 rows in Task 7's first seven columns plus seven of its own; 0 overlap with Task 7's and 7b's files; 0 identifier collisions against them or the csv | the applier reads it as a third file under pass `vtable-slot` at 0.75; `Class`/`Slot`/`FixedPoints` belong in the sidecar's `Evidence` |
| Task 4 step 3 (apply, PROOF) | holdout 37 / 37 right, 0 wrong: the stop rule is not triggered | the file may be applied; the PROOF row is batched with Task 3's |
| S12-R3 (prefix pairs) | the slot names 16 Task 7 prefix pairs identically, 0 differently; 15 are written here | 15 of the 159 prologue pairs reach the sidecar through this pass. `Serialize__8CMissionFi` (ratio 0.09) agrees by slot and is held on size: a reviewer's case |
| S12-R16 / the spec's expected yield | 199 at whole + shared (184 in research/51 + 16 prefix confirmations − 1); 194 with secondaries refused | the plan's "~169" is research/51's "whole" before admitting the confirmations; quote 199 |
| a reviewer | 148 of the 236 slot namings rest on an equal slot count with no body-matched fixed point, which the holdout cannot test | the `FixedPoints` column says `start..end` on exactly those rows, so they are one filter away if the owner wants them held |
| Task 3a / the csv | 64 csv rows are vtable data exported as functions, some ~0.78 MB long (§7) | a csv fix-up candidate (they are not code); nothing names them today |
| constructors | not proposed; variant C's recall is still unmeasured on retail | a `vtable-ctor` pass needs its own holdout first (research/51 §7) |
