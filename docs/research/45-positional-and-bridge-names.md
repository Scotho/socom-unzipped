# 45. Two more levers on the demo's names: position between anchors, and a bridge through demo2

Date: 2026-09-24. Sprint 11, Task 7b. Read-only: three ELFs, one Ghidra table. No game was run, no
server contacted, no Ghidra process started, and `recomp/socom2_ghidra.csv` is **unchanged** — the
renames this note measures are proposals in a git-ignored file, to be applied in a separate reviewed
step. `docs/research/44-demo-symbols.md` (Task 7) is the note this one extends; it is not edited here.

**The one-line answer: lever 1 (position) adds 16 names, lever 2 (the bridge) adds 0.** Position
between proved anchors is real — link order survives 92–98 % per overlay, and 528 of our anonymous
functions sit in anchor gaps whose two builds hold the same count — but 491 of those 528 have no body
evidence of any kind, and 19 more have body evidence that cannot tell them from a sibling in their own
gap. The bridge fails for a reason worth writing down: it still has to cross the SOCOM 1 → SOCOM II
edit, which is the same hop Task 7 already could not cross, and the Aug 2003 demo is on the wrong side
of it. 130 of its 131 fresh candidates die on the second hop.

The peer review that specified both levers measured the first one first: the link-order and anchor-gap
figures below are **socom-pc-6c's measurement** (`peer_7b/link_order.py`), reproduced here by the tool
rather than taken on trust. Where the two disagree slightly, §1 says why.

Every number names the command that produces it. There is one command:

```
# A -- both levers, the holdout, and the proposals file (§1-§6)
python -m tools_py.ghidra_symbol_match \
    game/demo_scus_972_05/SCUS_972.05 game/disc/socom2_game.elf recomp/socom2_ghidra.csv \
    --prefix --top 0 --positional --bridge game/demo_scus_973_68/SCUS_973.68 \
    --holdout 3 --holdout-block 8 --renames-7b game/demo_symbol_renames_7b.csv
```

Thirteen seconds. Its output is quoted verbatim throughout. Two variants are quoted too:
`--holdout-block 1` for §3's single-pair holdout, and `--positional-blurred` for §4's 19.

## 1. Lever 1: does link order survive?

Sorted by our address, consecutive Task 7 pairs keep the demo's address order:

```
region 0x100000-0x1d5000:  474 pairs, consecutive in demo order 463/473 (97.9%)
region 0x1e7000-0x408480:  322 pairs, consecutive in demo order 294/321 (91.6%)
region 0x4c5380-0x66a000:  191 pairs, consecutive in demo order 175/190 (92.1%)
```

Boot loader, FTSCore, ZSealEtc. The peer's figures were 97.2 %, 90.7 %, 92.1 %; the small differences
are one methodological choice, stated rather than smoothed over. The peer keyed each pair by looking
its demo address up from the demo NAME and skipping names that occur twice; this tool keys by the demo
address `ghidra_symbol_match`'s `details` already carries, so the three pairs under a duplicated name
(`_request_end` twice, `kCopy`) are kept with their real addresses instead of dropped. Same measurement,
three more pairs, one more anchor in each of two regions.

**The walk must run per region.** The whole-image longest increasing subsequence is 492 of 984, which
would read as "link order does not survive" — it is an artefact: the demo has one `PT_LOAD` and we have
four, so the demo's single run of addresses interleaves what we split into three overlays. Inside a
region the agreement is 92–98 %. `symbol_levers.anchor_gaps` takes the regions from our own `PT_LOAD`
table and never compares across two of them.

## 2. Lever 1: the gaps, and what a candidate has to buy its name with

Between two consecutive anchors that ascend on **both** sides, when both builds hold the same number of
still-unplaced functions, the i-th on one side corresponds to the i-th on the other:

```
lever 1 (positional): anchors 987, gaps 156, candidates 528, no body evidence 491,
  body evidence not gap-discriminating 19, our row already named 0, tier A 11, tier B 7
```

156 usable gaps holding 528 functions (the peer counted 151 and 510 over the whole image without the
per-region split; the three extra anchors and the split account for the difference). Gap sizes run
1 (72 gaps), 2 (25), 3 (16), 4 (11), 5 (9), … up to a single gap of 49.

A correspondence is not evidence, so every candidate then has to clear a body rule. **The rule, and
where each threshold comes from:**

| hurdle | the cut | why that number |
|---|---|---|
| **tier A** | equal body length **and** equal address-masked fingerprint, body ≥ **32 bytes** | This is `address_matcher`'s own relinked-body test, unchanged. The matcher refused these pairs for exactly one reason: the masked hash was not unique on both sides. Position supplies the uniqueness the matcher lacked; nothing else is loosened. The 32-byte floor is because a `jr $ra; nop` thunk hashes the same in every program ever compiled — under eight instructions the hash adds nothing to the position. |
| **tier B** | equal address-masked **16-instruction prologue** hash, both bodies ≥ **64 bytes**, size ratio ≥ **0.50** | 16 instructions is `ghidra_symbol_match.PREFIX_WORDS` — "the prologue" means one thing in both modules. The hash is **masked** where Task 7's prefix pass hashes the raw stream, because a prologue that touches a global carries half an address in a load displacement and between two *games* that half always moves. 64 bytes because a prologue that is the whole function is not a prologue. |
| **the size ratio** | neither body more than twice the other | **Measured, not chosen.** Task 7's 159 prefix-pass pairs are the sample of "the same routine after a year of edits": their min/max size ratio has a 5th percentile of **0.478**, and 153 of the 159 (96.2 %) clear 0.50. Tighter starts refusing routines we have independent reason to believe are the same one; looser stops refusing anything. |
| **gap-discriminating** | the body key must not equal a sibling's in the same gap | §4. This is the hurdle the first cut of the module did not have. |
| the identifier hurdles | Task 7's, verbatim | Both files are applied to one CSV, so a name the recompiler would see twice is two definitions of one C symbol whichever file proposed it. `proposals_7b` is handed Task 7's 479 spellings and refuses any that collides. |

A candidate may never take a row Task 7 already paired (those rows are the anchors) nor a row we named
by hand. On this data the second never fired: `our row already named 0`.

## 3. Lever 1: the error rate, measured on known answers

The lever asserts "position implies identity", which is the kind of claim that has to be tested rather
than argued. Hold out every k-th Task 7 pair, run the walk with the rest as anchors, and check the
held-out rows against the answer Task 7 already proved.

```
--holdout 3 --holdout-block 1        --holdout 3 --holdout-block 8
  tier A   360  1 wrong (99.72%)       tier A   127  0 wrong (100.00%)
  tier B    32  0 wrong (100.00%)      tier B     8  0 wrong (100.00%)
  blurred    0  0 wrong                blurred    6  0 wrong (100.00%)
  untiered  80  5 wrong (93.75%)       untiered  19  2 wrong (89.47%)
```

Read the `untiered` line: **the body rule is doing the work.** Position alone is right about 90–94 % of
the time, which over 528 candidates would be thirty-odd wrong names with nothing to mark them. With
tier A or B the walk re-derived 527 held-out pairs across the two settings and got one wrong.

`--holdout-block` exists because the obvious holdout is misleading. Holding out single pairs leaves
gaps that contain one held-out function each, and a gap of one is gap-discriminating by definition — so
`block 1` never exercises the §4 hurdle at all and says nothing about the multi-function gaps the real
run actually scores. `block 8` holds out runs of eight consecutive pairs and does.

**The bias, stated with the result.** A held-out pair is by construction a function Task 7 *could*
match — one that survived into SOCOM II nearly intact. The 528 candidates the real run scores are the
ones Task 7 could not match. So this measures the walk, not the population, and it is an **upper bound**
on the real accuracy. That is precisely why the tiers are a hurdle in the code and not a note in a
report.

## 4. The 19 the body evidence cannot separate

Of the 37 candidates that cleared tier A or B, **19 shared their body key with a sibling in the same
gap**, leaving 18. They are not a random 19:

```
sceDmaSendN / sceDmaSendI                  stat / unlink
sceSifQueryMemSize / MaxFreeMemSize / TotalFreeMemSize / BlockTopAddress / BlockSize
_sceSifLoadModuleBuffer / sceSifStopModule Copy__12CZAnimArgCmdFv / Copy__14CZAnimArgValveFv
rt_mutex_platform_destroy / _lock          rt_msg_client_get_local_ip / _iget_local_ip
rt_msg_client_is_valid_outgoing_msg        PlaySelectionSound__Fv
```

Wrapper families. Each pair is the same instruction stream differing only in an immediate — a syscall
number, a query selector — and `fingerprint` zeroes `addiu`/`ori` immediates **on purpose**, because
that is how it sees through a relink. So their masked hashes are equal by construction, and for such a
pair the body check confirms nothing that position did not already assert. The evidence exists to
*check* the positional guess; where it cannot separate the candidate from its own neighbours it has not
checked it, and a silently swapped `sceSifQueryMemSize` / `sceSifQueryBlockSize` is the kind of wrong
name nobody ever catches.

So they are refused by default and counted. This is the one **judgement** in the rule rather than a
measurement, so it is a knob: `--positional-blurred` admits them, the rows carry `Discriminating=no`,
and the file's header says the flag was given. The argument for admitting them is real — the only thing
separating a name from its sibling is the order the linker emitted them in, that order is source order,
and the holdout saw six such pairs and got all six right. Six is not a measurement. The default file
leaves them out; with the flag it holds **35** rows instead of 16.

## 5. Lever 1: what it adds

```
7b proposals: 16
    held back: identifier already spent or collides 2
```

The two refused are both `_sceRpcGetPacket`, one demo name landing positionally on two of our rows —
the same `static`-in-two-translation-units shape as Task 7's `_request_end` collision, and refused for
the same reason: one of the two is wrong by construction and which one is not knowable here.

All 16, from `game/demo_symbol_renames_7b.csv` (tier, our address, demo size / our size):

| tier | our address | sizes | name |
|---|---|---|---|
| B | 0x00598b90 | 1456/2320 | `RemoteRespawn__10CZSealBodyFb` |
| B | 0x00187dc0 | 604/632 | `seekoff__Q23std39basic_filebuf<w,…>FlQ33std8ios_base7seekdir…` |
| B | 0x001af6f8 | 596/596 | `__ieee754_expf` |
| B | 0x002c1f10 | 364/376 | `HandleBombStateRequest__11CZBombStateFiUcP6CPnt3D` |
| B | 0x00634098 | 208/216 | `rt_msg_client_iupdate_all` |
| B | 0x001a52b8 | 176/176 | `deci2Putchar` |
| A | 0x001ab6d0 | 144/144 | `sceSifSearchModuleByAddress` |
| A | 0x001ab5a0 | 144/144 | `sceSifUnloadModule` |
| A | 0x001a7bf8 | 140/140 | `_fs_version` |
| A | 0x001ab0c8 | 140/140 | `_lf_version` |
| B | 0x001b4470 | 84/88 | `mceGetInfoApdx` |
| A | 0x002222b0 | 44/44 | `MissionEndCleanup__15CZPlayerMapItemFv` |
| A | 0x00639500 | 44/44 | `rt_mutex_platform_unlock` |
| A | 0x001a41e0 | 40/40 | `open` |
| A | 0x003087d0 | 40/40 | `__ct__7CMatrixFv` |
| A | 0x006148b8 | 40/40 | `NetRegisterMallocFreeCallbacks` |

Six are engine or game-network routines rather than SDK: `CZSealBody::RemoteRespawn`,
`CZBombState::HandleBombStateRequest`, `CZPlayerMapItem::MissionEndCleanup`, `CMatrix::CMatrix`, and the
two `rt_msg_client_*` / `rt_mutex_platform_*` entries from the RTIME messaging layer. The most
interesting of them is `RemoteRespawn__10CZSealBodyFb` at **0x00598b90**: 1,456 bytes in the demo
against 2,320 in ours, the same prologue, sitting in a four-function gap — the remote-respawn path grew
by 60 % between the two games, which is the shape you would expect of the online respawn rules changing.
`HandleBombStateRequest` (0x002c1f10) is the demolition objective's network handler, and
`MissionEndCleanup` (0x002222b0) names a map-item teardown.

## 6. The other 491: what the lever sees and refuses

491 of the 528 candidates produced no body evidence at all. **124 of them carry an engine-shaped name**,
and those are the most valuable output of this task that is not a proposal — they are leads with an
address, not names. The largest twenty-five, by demo body size, with our size beside it:

```
0x00272c30 1936/1676 gap  8  ActivateArgV__6CZAnimFPc
0x002227b0 1408/1224 gap  4  TickSealCone__15CZPlayerMapItemFP11CZNewHudMap
0x00369210 1308/1212 gap 11  Clear__9CGameMenuFv
0x002222e0 1188/1232 gap  4  SetViewCone__15CZPlayerMapItemFP11CZNewHudMapPC6CPnt3DPC6CPnt3DUiff
0x00369eb0 1156/ 192 gap 11  __ct__9CGameMenuFv
0x00228ee0  988/1356 gap  4  PlayCamera__16CZHudMissionCamsFP11CMissionCamb
0x00308b00  952/1000 gap  8  DistToVector__6CPnt3DCFPC6CPnt3DPC6CPnt3DP6CPnt3DPf
0x00599690  920/ 376 gap  4  CreateRemoteSeal__10CZSealBodyFiiPCciPcUcPUc
0x002734b0  916/ 712 gap  8  Activate__6CZAnimFP6CZAnim
0x0050df90  892/  92 gap  6  AddNoise__2aiFPC6CPnt3DP6CPnt3DRC5PNT2D
0x0050df30  880/  92 gap  6  AddNoise__2aiFP6CPnt3DRC5PNT2D
0x0050dff0  864/ 416 gap  6  MakeNoise__2aiFP6CPnt3DRC5PNT2D
0x00268c00  760/ 724 gap 20  Load__15CZAnimNameTableFRQ23zar4CZAR
0x00308800  700/ 768 gap  8  DistToVector__6CPnt3DCFPC6CPnt3DPC6CPnt3DPf
0x00351a90  644/ 400 gap  8  Parse__6CValveFP8CRdrFile10VALVE_TYPE
0x00222c80  580/ 548 gap  4  GetBlipID__15CZPlayerMapItemFP10CZSealBody
0x002c1c30  552/ 736 gap  2  ChangeBombState__11CZBombStateFv
0x005994a0  532/ 492 gap  4  DoRespawn__10CZSealBodyFv
0x00308210  524/ 432 gap  1  ToQuat__7CMatrixCFP5CQuat
0x00369b60  500/ 840 gap 11  __dt__9CGameMenuFv
0x002c1a80  496/ 360 gap  6  InitBomb__11CZBombStateFv
0x00360380  472/ 280 gap  5  MakePacket__7C2DLineFPQ23zdb7CCamera
0x00269230  468/ 492 gap 20  GetDatabaseNode__10CZAnimMainFPCci
0x002732c0  468/  92 gap  8  ActivateEx__6CZAnimFie
0x00269930  420/ 464 gap 20  StopSequence__10CZAnimMainFPCc
```

Read the size columns. `ai::AddNoise` is 892 bytes in SOCOM 1 and 92 in ours; `CZAnim::ActivateEx` is
468 against 92. Those are not edits, they are rewrites — or the positional guess is simply wrong there,
and nothing in this task can tell which. `ToQuat__7CMatrixCFP5CQuat` at 0x00308210 is the tightest of
the lot: a gap of **one**, 524 bytes against 432, in the middle of a `CMatrix` cluster Task 7 already
placed. If any one of these is worth a human's half hour, it is that one.

## 7. Lever 2: the bridge, and why it adds nothing

`game/demo_scus_973_68/SCUS_973.68` — build id `SOCOM 2 v0001 17:30:02 Aug 18 2003`, 4.56 MB, one
`PT_LOAD` at 0x100000, **zero symbols** — sits between SOCOM 1 and retail r0001 in time. Being
stripped, it can never contribute a name; its only possible contribution is **body evidence**, as a
stepping stone: demo1 → demo2 → retail, each hop by `address_matcher.match`.

### The function table, and its measured limits

demo2 has no symbols, and `tools_py` had no Ghidra-free boundary tool that was not a script wanting a
Ghidra CSV, so `symbol_levers.scan_functions` derives one from the bytes: **what follows a `jr $ra` and
its delay slot (past any zero padding) is a function start** — on MIPS you cannot fall through a return,
and this rule does nearly all the work — plus **every `jal` target inside the image**, which catches the
first function of a run and keeps a leading data block out of it. A range then runs to the next start,
with trailing zero padding trimmed but **never past the delay slot of the last `jr $ra`** (a `nop` delay
slot *is* a zero word; trimming it cut every such function one instruction short, and fixing that took
the scan from 85.3 % to 94.6 %). A range with no `jr $ra` in it is dropped as data or a jump table.

The limits are measured, not asserted, by running the same scan on **demo1**, whose `.symtab` is the
ground truth:

```
the boundary scan, checked on demo1's own .symtab: 9532 ranges for 9703 real functions,
9353 starts right, 9177 with both boundaries right (94.6%)
```

Recall 96.4 %, precision 98.1 %, and 94.6 % of real functions get **both** boundaries right and so
fingerprint like the real thing. A third seed — every 32-bit word in the image pointing at an aligned
address inside it, i.e. vtable and constructor-table entries — is implemented and **off by default**,
because it was measured to make the table worse: a vtable slot pointing into the middle of a function
splits it, and both-boundaries-right falls from 94.6 % to 92.2 %. What the scan cannot see at all is a
function that is never a `jal` target and never follows a return; its bytes are absorbed by its
predecessor, which spoils that one too. On demo2 the scan yields **12,250 ranges** — between demo1's
9,703 and retail's 14,879, which is where a build five months before release should sit.

### The result

```
hop1 resolved 859, hop2 resolved 5206, composed (any pass) 723,
composed (both hops strong) 704, agrees with Task 7 704, contradicts Task 7 0, new 0
```

**704 agreements, 0 contradictions, 0 new names.** The acceptance rule was: both hops `exact` or
`relinked-body`, no contradiction of Task 7, our row still `FUN_*`. Relaxing it to admit `hash+callees`
on either hop yields **one** new name — a rounding error, and a weaker claim, since a `hash+callees` hop
inherits the other pairs as its evidence.

### Why, precisely

The bridge's arithmetic is the whole story:

* hop1 (demo1 → demo2) resolves **859** of the demo's 9,703 functions. Task 7's direct match placed
  **987**. The bridge is *strictly worse at the hard hop*, because the hard hop is the same one: the
  SOCOM 1 → SOCOM II edit is where the year of changes lives, and the Aug 2003 demo is already on the
  far side of it. demo2 helps only where it is closer to demo1 than retail is, and it almost never is.
* **131** demo1 functions are placed by hop1 that Task 7 could not place directly. That is the bridge's
  entire potential contribution. Of those 131, **130 die on hop2 as `unresolved`** and one fails the
  strength rule. A routine byte-identical in SOCOM 1 and the Aug 2003 build but not in retail is a
  routine edited in the last five months — and for that one, demo2 is on the wrong side of the edit too.
* The deeper reason there is no residue: both passes are **transitive on masked hashes**. If demo1 and
  demo2 agree and demo2 and retail agree, then demo1 and retail agree, and Task 7 would already have
  seen it — *unless* the direct comparison was ambiguous and the two hops were each unique. That
  disambiguation is the only mechanism by which a bridge can add a name, and on this data it fires zero
  times.

So the bridge's contribution is **corroboration, not discovery**: 704 of Task 7's 987 pairs are now
independently confirmed by a two-hop path through a third build, with zero contradictions. That is worth
having — a pair confirmed twice by different routes is a pair a reviewer need not re-check — and it is
not a name. `game/demo_symbol_renames_7b.csv` has no `Source=bridge` row and, on this input, never will.

## 8. What was delivered

* `tools_py/symbol_levers.py` (515 lines): `scan_functions`/`scan_accuracy`, `anchor_gaps`,
  `positional`, `holdout`, `bridge`, `proposals_7b`/`write_proposals_7b`, and the two rules as
  constants (`POSITIONAL_RULE`, `BRIDGE_RULE`) so the file header and the code cannot drift apart.
* `tools_py/ghidra_symbol_match.py` gains `--positional`, `--positional-blurred`, `--bridge`,
  `--holdout`, `--holdout-block` and `--renames-7b`. Its Task 7 behaviour is untouched: with none of
  those flags the run prints and writes exactly what §3 of note 44 quotes.
* `tools_py/tests/test_symbol_levers.py`, **31 tests**, on synthetic MIPS fixtures — an anchor gap that
  lines up and one that does not, anchors out of order, a gap in another `PT_LOAD`, a blurred gap
  refused and admitted, a bridge that agrees and one that contradicts, the scan's boundary rules. No
  disc, no demo, no ELF on disk. `test_elf_symbols`, `test_ghidra_symbol_match` and
  `test_address_matcher` still pass: 132 together.
* `game/demo_symbol_renames_7b.csv` — git-ignored, 16 rows, `Address, Current, Proposed, Mangled,
  Source, Tier, Discriminating, DemoAddr, DemoSize, OurSize, Ratio, GapSize`, with both acceptance
  rules written into `#` lines above the column header.

Not delivered, on purpose: **no rename was applied**, `recomp/socom2_ghidra.csv` is byte-for-byte
unchanged, `docs/research/44-demo-symbols.md` is untouched (the controller owns it), and **no demo bytes
are in the repository** — names and addresses only.

## 9. What is left

* **The 124 engine-shaped leads in §6** are the best thing here that is not a proposal. They need
  disassembly, not a hash: a human reading `ToQuat__7CMatrixCFP5CQuat` at 0x00308210 next to the
  `CMatrix` members Task 7 already named would settle it in minutes.
* **The blurred 19 (§4)** need one decision, not more evidence: are we willing to trust link order
  alone for a wrapper family? If yes, `--positional-blurred` writes them today.
* **The bridge is done.** It is not worth revisiting with a better demo2 table — the boundary scan is
  already at 94.6 % and the failure is not the table, it is that 130 of 131 candidates die on a hop no
  table can help with. If a *named* intermediate build ever turns up, the lever's code is ready for it.
* Note 44 §6's conclusion stands unchanged: the ceiling is that SOCOM II is a different build of the
  game, and neither of these levers moves it.
