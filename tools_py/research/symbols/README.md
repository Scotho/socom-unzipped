# Symbol-work measurement scripts (socom-pc-6c, 2026-09-24; read-only, run from the repo root)

Kept for Sprint 12 (R263). Each reproduces the figures cited in research/44's addenda; none touches a tracked file or emits game bytes.

## The Sprint 12 research wave: one script per note (added 2026-09-25, Task 9)

Twelve more read-only scripts, one behind each note of the wave (`docs/superpowers/plans/2026-09-24-sprint-12.md`,
Task 0b). Each is run from the repo root on the git-ignored inputs under `game/` plus tracked files, prints names,
addresses and counts only, and writes nothing tracked; the note it serves names its exact command and owns every
figure it prints, so this table gives none. The runtime is the note's own statement unless marked *(Task 9)*,
measured on the cloud container on 2026-09-25.

| note | script | what it measures | runtime |
|---|---|---|---|
| 61 | `name_consumers.py` | every reader of a function name or a raw guest offset: the toml's keys and which the recompiler reads, the live and the unused identifier sanitiser over each name set, the names that change what the recompiler *does* (stub by name, correctness-critical prefixes), the recompiler's function list replayed, the parity tools' hex literals | about 1 s *(Task 9)* |
| 47 | `readable_proof.py` | the readable-name rule set R1–R12 over four name sets (the proposals, the demo's 9,703, the toml's 656, the coexisting set): collisions before and after the overload suffix, lengths against the filename budget, what either sanitiser would alter | about 3 s |
| 48 | `sidecar_census.py` | the csv's name census by class, where `sub_` comes from, the history of every non-auto name (`git log`), the syscall-stub check, the carry to r0004 and the audit prototype; `--rows` prints the 69 backfill rows | about 10 s (`--no-git` less) |
| 49 | `bindiff_join.py` | BinDiff's demo→r0001 result joined to Task 7's 987 pairs: agree / disagree / absent / new, the contradiction rate against the proved pairs, the zero-contradiction rule, the 159 prologue pairs' verdicts, each proposals file against BinDiff | 7 s for the join; the Ghidra imports, BinExport and BinDiff before it about 8 minutes (research/49 §1) |
| 50 | `dwarf_types.py` | the demo's DWARF1 `.debug` through ccc's raw DIE dump: the tag census, the class layouts, the compile units, each raw offset the tools use against SOCOM II's own access pattern, the layout-age caveat | about three minutes for all six sections (needs ccc under `/home/user/tools/`) |
| 51 | `vtable_coverage.py` | the classes the bare-name RTTI walk cannot open and what opens them: the retail vtable census by layout, the qualified RTTI string, fixed points and the positional rule in four readings, the constructor rule | about 6 s |
| 52 | `callgraph_propagation.py` | callee / caller / (caller, callee) keys unique both ways from the placed pairs, their holdout error, iteration to a fixed point, the ORDERED rule, research/45's positional candidates against them | about 90 s |
| 53 | `string_correlator.py` | the set of shared strings a body references as a key: the census, the key variants at two scopes, the holdout, rule R3 and its confirming signals | about 10 s |
| 54 | `offset_multiset.py` | (opcode, displacement) multisets as a looser body key (K1–K3), link order as the key-independent check, the prologue pairs it confirms | about 25–30 s |
| 55 | `class_inventory.py` | the demo's classes as an architecture map, the subsystems, the UI script-binding table in both images, what the runtime's hooks touch, the online and voice classes, the gap map; writes the git-ignored `game/class_inventory.csv` | about 30–35 s |
| 56 | `sase_probe.py` | SASE, SOCOM II's voice codec: source paths, code range and entry points, parameters, the tables it reads (addresses and lengths only), the three SOCOM II builds compared; `--dis` prints one span's mnemonics | under 10 s |
| 57 | `toml_names.py` | the recompiler's naming pipeline replayed: the toml's keys and selectors, where `FUN_` / `sub_` / real names in `recomp/output` come from, the rename hazards, filename lengths, the what-if of writing names into the csv | about 2 s *(Task 9)* |

The levers these notes led to are not here: each is a tracked module, `tools_py/*_lever.py`, with its own CLI,
tests and proposals file, and `tools_py/apply_names.py` is the one thing that turns their files into sidecar rows.

## 7b: link order, readable names, toml overlap, debug paths

# Task 7 review measurements (from socom-pc-6c, 2026-09-24)

Four read-only scripts, each run from the repo root with the tree at f1efa5b. All inputs are
git-ignored files under `game/` plus `recomp/socom2_ghidra.csv` and `recomp/socom2.toml`.
None of them writes anything. Numbers quoted in the review came from exactly these.

| script | what it measures | figures it printed |
|---|---|---|
| `link_order.py` | whether the 987 pairs keep the demo's link order inside each of our PT_LOAD regions, and how many unnamed functions sit in anchor gaps where both builds hold the same count (lever 1) | in-order 457/470 (97.2 %) boot loader, 291/321 (90.7 %) FTSCore, 175/190 (92.1 %) ZSealEtc; whole-image LIS 492/984 (the demo's one PT_LOAD interleaves our three overlays, so run per region); 930 ordered gaps, 151 with equal counts, 510 functions nameable by position |
| `readable_names.py` | the GNU-v2 / Metrowerks mangled name to `Class_Method`, with the overload-collision census over the 479 proposals and over all 9,703 demo names | 479 proposals: 2 colliding readable names over 4 rows (`C2DBitmapPoly_SetUV`, `CAiMapLoc_ctor`); 9,703 demo names: 9,351 distinct, 255 colliding names covering 607 functions; 1,212 classes, CZSealBody 351 methods, CSealCtrlAi 140, CZKit 110 |
| `toml_overlap.py` | how many of the 479 proposals repeat a name `recomp/socom2.toml` already carries, plus the `recomp/output` name census | 273 proposals sit on toml-named addresses; 272 identical, 1 differs (`setD3_CHCR` vs `setD4_CHCR`); output: 14,882 files, 7,958 `FUN_`, 6,750 `sub_`, ~120 real names |
| `debug_paths.py` | the source paths in the demo's `.debug`, grouped by directory, and how often engine class names occur there | 114 path strings, 95 source files; `Z:\dev\Apps\FTS` 37, `C:\dev\libpttclient` 35 = libpttclient.c plus **all 34 units of the LPC-10 reference vocoder** (analys.c bsynz.c chanwr.c dcbias.c decode.c deemp.c difmag.c dyptrk.c encode.c energy.c f2clib.c ham84.c hp100.c invert.c irc2pc.c ivfilt.c lpcdec.c lpcenc.c lpcini.c lpfilt.c median.c mload.c onset.c pitsyn.c placea.c placev.c preemp.c prepro.c random.c rcchk.c synths.c tbdm.c voicin.c vparms.c; f2clib.c is the Fortran-to-C runtime that implementation carries). **CORRECTION: the review first called this GSM 06.10 from the first five names; it is LPC-10 (2400 bit/s), not GSM.** Gamez dirs a handful; CZSealBody 109, CMission 116, CEntity 96, CPnt3D 69 occurrences in `.debug` |

## Voice codec: the corrected record (2026-09-24, socom-pc-6c)

Measured by string search over the four ELFs (`python - <<EOF` with `re.finditer` over the raw
file; the LPC-10 unit list is the 34 files of the public reference implementation):

| build | voice codec evidence |
|---|---|
| SOCOM 1 demo, May 2002 (`SCUS_972.05`) | `C:\dev\libpttclient`: all 34 LPC-10 reference units + `libpttclient.c`; 48 named functions `PTT_Init`, `PTT_JoinGame`, `PTT_PushToTalk`, `lpc10_encode`, `lpc10_decode`, `voicin_`, `pitsyn_` ... **None of the 48 is placed in our image by Task 7's matcher**, and retail carries no `PTT_` or `lpc10` string |
| SOCOM II Aug 18 demo (`SCUS_973.68`), r0001 retail, r0004 | 25 to 26 source paths `../../SaseEncVad/source/*.c` and `../../SaseDec/source/*.c`: `Coder.c LDPDA.c PtchCand.c QP0SC3.c RefineC0.c Voicing.c PostFilt.c PreProc.c BitPackC.c PackSC.c DecSC.c SWSynth.c SetAmps.c libspeech.c libquan.c libsigproc.c libsnd.c libmath.c` (r0004 adds `CalcCost.c`, `EncSC.c`) *(> Correction, 2026-09-24, research/56: `EncSC.c` is in all three; r0004 adds only `CalcCost.c`.)*. A codec called **SASE**, encoder with VAD plus decoder; the file names (sine-wave synthesis, pitch candidates, set amplitudes) say a sinusoidal low-rate speech coder. Vendor not identified from strings. The Aug 18 demo alone also carries `rt_lpc10 version: 1.00.0002`; retail and r0004 do not |

So: SOCOM 1 = LPC-10; SOCOM II = SASE. The review's first message said GSM 06.10 and its second
draft said LPC-10 for SOCOM II; both are wrong for SOCOM II and the GSM claim was wrong outright.
The `.debug` types for libpttclient in the SOCOM 1 demo describe LPC-10, which SOCOM II does not
ship, so they do not help the voice-chat row.

Caveats for the 7b agent:

- `readable()` is a naming helper, not a demangler: it takes the function name, the operator table,
  and the class path (`Q<n>` nested or a single `<len><Name>`), drops template arguments, and
  sanitises to `[A-Za-z0-9_]`. Argument types are ignored on purpose, which is why overloads
  collide; resolve those with an argument suffix only where the readable name is not unique.
- `link_order.py` counts gaps by function *starts* in `recomp/socom2_ghidra.csv` against the demo's
  `.symtab` FUNC starts. A gap with equal counts is a candidate, not a match: check size ratio and
  the 16-instruction prologue hash per pair before writing a proposal.
- The `.debug` parse in `debug_paths.py` is string extraction only. A real DWARF1 walk is the ccc
  route, deferred.

## 7c: vtable anchors, the RTTI walk

# Task 7c groundwork: vtable-slot matching through RTTI (socom-pc-6c, 2026-09-24)

Two read-only scripts, run from the repo root with the tree at f1efa5b (Task 7's outputs under
`game/` as of that commit). Neither writes anything. Inputs: the SOCOM 1 demo ELF, our r0001
`game/disc/socom2_game.elf`, `recomp/socom2_ghidra.csv`, `game/demo_symbol_matches.json`.

## The layout fact everything rests on

Metrowerks 2.4.1.01 lays a vtable out as `[pointer to the class's __RTTI__ object, 0, slot0, slot1,
...]`. Checked on the demo's `__vt__10CZSealBody` (OBJECT at 0x472110, 108 bytes: word 0 =
0x450d88 = `__RTTI__10CZSealBody`, word 1 = 0, words 2.. are function starts). The RTTI object holds
a pointer to the class-name string. Both pointers survive in retail, and the name strings survive
(research/05), so the chain **string -> RTTI object -> vtable** locates a retail vtable with no
function anchor. Confirmed on retail: `"CZSealBody"` at 0x65c240, RTTI object at 0x65c288, vtables
at 0x6691a0 (26 slots, the primary) and 0x669210 (7 slots, a secondary base), the first being the
vtable that the body-matched slots had located independently.

## `vtable_anchors.py`: what today's 987 pairs reach on their own

| figure | value |
|---|---|
| demo `__vt__` objects | 248 |
| with two or more function slots | 221 |
| slots in those | 2,611 |
| vtables with two or more body-matched (non-prefix) slots | 19 |
| located uniquely in our image from those anchors | 7 (7 more ambiguous) |
| retail slots in the located seven | 49 |

Anchors alone are the bottleneck: 19 of 221. The examples it prints include CZSealBody (23 demo
slots, 25 counted from the anchored base, 4 anchors) and CFlashFX (21 vs 23, 2 anchors). The base it
prints is the first anchored word's slot-0 position and can sit one word off the true start;
`vtable_rtti.py` gives the true start.

## `vtable_rtti.py`: what the RTTI route reaches

Walks every demo `__vt__` class, takes the bare class name from the mangled symbol, and resolves it
in retail through the chain above.

| bucket (of 248 demo classes) | count |
|---|---|
| exactly one retail vtable | 111 |
| several retail vtables (multiple inheritance, or a bare name shared by a nested class or another namespace) | 54 |
| class-name string absent in retail | 66 |
| template instantiation (skipped: the bare name is not recoverable this way) | 14 |
| string present but no RTTI pointer | 3 |

For the 111 unambiguous classes: **1,154 demo slots against 1,496 retail slots**, and **41 of the
111 have the same slot count in both builds** (nameable slot for slot once a body-matched fixed
point confirms the alignment). The largest: CSealCtrlCopy 39 -> 44, CSealCtrlAi 40 -> 44,
CRemoteCtrl 39 -> 44, CSealCtrlSquirm 40 -> 44, C2DMessageString 29 -> 34, the C2D* family 21 -> 26.
The consistent +4/+5 across a family says the common base gained virtuals, so a run of equal-count
slots after the insertion point will still align; treat it as the positional pass does (anchors as
fixed points, equal-count runs by position).

With class names as arguments (`python vtable_rtti.py CZSealBody CMission CFlashFX`) it prints the
chain for each. CZNetwork's name string is absent in retail (so is its vtable, or the class lost its
virtuals); CMission's retail vtable at 0x406290 has 5 slots.

## Caveats for the 7c implementer

- `slot_count` counts consecutive words that are function starts in our CSV. A vtable packed
  directly after another stops at the next vtable's RTTI-pointer header, so the count does not run
  over; but a function the CSV does not know (the 51 unreadable bodies, gap functions) ends the
  count early.
- The 'several' bucket is not a failure: a class with two retail vtables (CZSealBody) is the
  primary plus a secondary-base vtable, and the demo has the same pair; match by slot count and by
  which one the body-matched slots fall in. Bare-name collisions across namespaces are the other
  cause and need the demo's qualified name (`Q2` components) to split.
- The 66 absent names include classes SOCOM II dropped and classes whose RTTI the linker
  discarded; do not read the bucket as 'deleted class'.
- Constructors: the `lui/addiu` pair forming a located vtable address followed by `sw` to
  `0($a0)` (or the `this` register) marks a constructor of that class; the same for destructors
  that reset the vtable. That is the free by-product R260 names; nothing here measures it yet.
