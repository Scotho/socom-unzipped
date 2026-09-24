# 45. Two more levers on the demo's names: position between anchors, and a bridge through demo2

Date: 2026-09-24 (revised after review). Sprint 11, Task 7b. Read-only: three ELFs, one Ghidra table.
No game was run, no server contacted, no Ghidra process started, and `recomp/socom2_ghidra.csv` is
**unchanged** — the renames this note measures are proposals in a git-ignored file, to be applied in a
separate reviewed step. `docs/research/44-demo-symbols.md` (Task 7) is the note this one extends; it is
not edited here.

**The one-line answer: lever 1 (position) adds 6 names, lever 2 (the bridge) adds 0.** Position between
proved anchors is real — link order survives 92–98 % per overlay, and 528 of our anonymous functions sit
in anchor gaps whose two builds hold the same count — but a correspondence is not evidence, and when
every candidate is made to buy its name with a body key that is unique **across the whole image**, 522
of the 528 cannot. The bridge fails for a reason worth writing down: it still has to cross the SOCOM 1 →
SOCOM II edit, which is the same hop Task 7 already could not cross, and the Aug 2003 demo is on the
wrong side of it. 130 of its 131 fresh candidates die on the second hop.

The peer review that specified both levers measured the first one first: the link-order and anchor-gap
figures below are **socom-pc-6c's measurement** (`tools_py/research/symbols/link_order.py`, committed in
41a6a16), reproduced here by the tool rather than taken on trust.

Every number names the command that produces it. There is one command:

```
# A -- both levers, the calibration, the holdout, and the proposals file (§1-§7)
python -m tools_py.ghidra_symbol_match \
    game/demo_scus_972_05/SCUS_972.05 game/disc/socom2_game.elf recomp/socom2_ghidra.csv \
    --prefix --top 0 --positional --bridge game/demo_scus_973_68/SCUS_973.68 \
    --holdout 3 --holdout-block 8 --size-ratio-calibration \
    --renames-7b game/demo_symbol_renames_7b.csv
```

Twenty-two seconds. Its output is quoted verbatim throughout. Two variants are quoted too:
`--holdout-block 1` for §3, and `--positional-min-evidence gap-only|any` for §4.

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
(`_request_end` twice, `kCopy`) are kept with their real addresses instead of dropped.

**The walk must run per region.** The whole-image longest increasing subsequence is 492 of 984, which
would read as "link order does not survive" — it is an artefact: the demo has one `PT_LOAD` and we have
four, so the demo's single run of addresses interleaves what we split into three overlays. Inside a
region the agreement is 92–98 %. `symbol_levers.anchor_gaps` takes the regions from our own `PT_LOAD`
table and never compares across two of them.

## 2. Lever 1: the anchors, the gaps, and the rule

### The anchor set is part of the answer, so the tool fixes it

`--positional` **implies `--prefix`**, and prints that it did. This is a rule about evidence, not a
convenience. Whether a prologue-only pair is an *anchor* or a *candidate* decides the file:

```
--prefix (always, now):  987 anchors, 156 gaps, 528 candidates ->  6 rows
the other way:           828 anchors, 137 gaps, 459 candidates -> 28 rows
```

Those 28 are mostly the 159 prologue pairs themselves, falling into the gaps and clearing tier B on the
strength of the prologue that made them prefix pairs in the first place — which is note 44's hurdle 3
("a prologue agreeing is not a body agreeing, at any length or any `--good`") re-admitted by the back
door. A prologue unique on both sides is a fine **position marker** and is not proof of identity, so its
place is on the anchor side. The anchor composition is printed and written into the proposals file's
header:

```
Task 7b: Anchors: 987 Task 7 pairs (exact 632, hash+callees 20, prefix 119, prefix+size 40,
relinked-body 176); 828 of them PROVED, the rest prologue-only
```

### The gaps

Between two consecutive anchors that ascend on **both** sides, when both builds hold the same number of
still-unplaced functions, the i-th on one side corresponds to the i-th on the other. 156 usable gaps
holding 528 functions. Gap sizes run 1 (72 gaps), 2 (25), 3 (16), 4 (11), 5 (9), … up to a single gap of
49.

A lone split or a lone merge in our Ghidra table changes a gap's count on one side and the gap is
refused whole. Two of them inside one gap **cancel**: the count still agrees and every pairing in the
gap is shifted by one. Nothing but the body rule stands between that and a wrong name, which is what
`AlignmentTest` is for — it builds exactly that case and asserts the default rule refuses all three
pairings while `--positional-min-evidence any` takes a demonstrably wrong one.

### The rule

| hurdle | the cut | why that number |
|---|---|---|
| **tier A** | equal body length **and** equal address-masked fingerprint | This is `address_matcher`'s own relinked-body test, unchanged. The matcher refused these pairs for exactly one reason: the masked hash was not unique. |
| **tier B** | equal address-**masked** 16-instruction prologue hash, size ratio ≥ **0.50** | 16 instructions is `ghidra_symbol_match.PREFIX_WORDS` — "the prologue" means one thing in both modules. The hash is **masked** where Task 7's prefix pass hashes the raw stream, because a prologue that touches a global carries half an address in a load displacement and between two *games* that half always moves. |
| **body ≥ 64 bytes**, both tiers | note 44's hurdle 2, unchanged | The reason note 44 gives for it — the `Name` column becomes a C identifier *and* an output filename, inherited by every later reader with no record that it was a guess — does not care which rule proposed the row. An earlier draft gave tier A a 32-byte floor; that was wrong, and §5 says what it cost. |
| **the key must be unique IMAGE-WIDE** | one demo function and one of our rows wear it, in the whole image | §4. This is the hurdle the first draft of this module did not have, and it is what decides the file. |
| the identifier hurdles | Task 7's, verbatim | Both files are applied to one CSV, so a name the recompiler would see twice is two definitions of one C symbol whichever file proposed it. `proposals_7b` is handed Task 7's 479 spellings and refuses any that collides. |

A candidate may never take a row Task 7 already paired (those rows are the anchors) nor a row we named
by hand. On this data the second never fired: `our row already named 0`.

**The size ratio is measured, and its arithmetic is now stated correctly.** `--size-ratio-calibration`:

```
159 pairs; six lowest ratios [0.0902, 0.2992, 0.3944, 0.4091, 0.4783, 0.4868];
cut 0.50 keeps 153 (96.2%); lowest kept 0.5063
```

Task 7's 159 prefix-pass pairs are the sample of "the same routine after a year of edits". Exactly six
of them fall under 0.50; 153 (96.2 %) clear it; the lowest ratio the cut actually keeps is 0.506. An
earlier draft called 0.478 "the 5th percentile" — it is the fifth lowest *observation*; the 5th
percentile by nearest rank is 0.557. Read correctly the statistic argues for a slightly **tighter** cut,
not a looser one (0.55 would keep 152 instead of 153). 0.50 is kept, and the loosest row in the file
(`RemoteRespawn`, ratio 0.63) is comfortably inside either.

## 3. Lever 1: the error rate, measured on known answers

Hold out Task 7's own pairs, run the walk with the rest as anchors, and check the held-out rows against
the answer Task 7 already proved. **The held-out truth is the 828 PROVED pairs**, not all 987: note 44
hurdle 3 refuses to treat a prologue agreement as proof of identity, and tier B's own evidence is a
prologue, so re-deriving a prefix pair at tier B is a prologue confirming a prologue. The prologue pairs
stay as anchors throughout; only the proved ones are ever held out. Both figures are printed.

```
--holdout 3 --holdout-block 8           --holdout 3 --holdout-block 1
  truth = the 828 proved pairs            truth = the 828 proved pairs
    image-wide  148   0 wrong               image-wide  274   0 wrong
    gap-only      2   0 wrong               gap-only     11   1 wrong (90.9%)
    no            5   0 wrong               no            0        --
    untiered     57   2 wrong (96.5%)       untiered    155   4 wrong (97.4%)
```

Two lines to read. **`untiered` says the body rule is doing the work**: position alone is right about
96–97 % of the time, which over 528 candidates would be sixteen-odd wrong names with nothing to mark
them. And **at block 1 `gap-only` gets one wrong out of eleven**, where `image-wide` gets none out of
274 — which is §4's whole argument arriving from the other direction. Across the two runs above that is
13 `gap-only` with one wrong against 422 `image-wide` with none; both readings say the same thing, and
neither number is printed by a single command, so the per-run figures are the ones to quote. The level
that decides the file is the level that has never been caught being wrong here; the one immediately
below it has.

`--holdout-block` exists because the obvious holdout is misleading. Holding out single pairs leaves gaps
that contain one held-out function each, and a gap of one is gap-unique by definition — so `block 1`
never exercises the `no` level at all. `block 8` holds out runs of eight consecutive pairs and does.

**Three things this measurement is not.** It is a **one-off run**, not a suite test: the suite pins the
mechanism (`HoldoutTest` proves the walk re-derives, and `test_the_wrong_counter_counts` builds a
relinked-out-of-order fixture and proves the error counter actually counts), and the numbers above come
from the documented command. It is an **upper bound**: a held-out pair is by construction a function
Task 7 *could* match, one that survived into SOCOM II nearly intact, while the 528 candidates are the
ones it could not. And it can **barely speak for the image-wide rule at all** — a held-out pair's key is
usually image-wide unique by construction, which is often *why* Task 7 matched it. All three sentences
travel with the proposals file, in its header.

## 4. What the body evidence is actually worth: three levels

The first draft of this module asked only whether a candidate's body key could be told from its own
**gap siblings**. The review's finding F1 is that the *justification* for that hurdle — a silently
swapped `sceSifQueryMemSize`/`BlockSize` is a wrong name nobody ever catches — is an argument about the
key having peers *anywhere*, not about the twins happening to land in the same gap. Measured on the
first draft's file: **9 of its 16 rows had a key with peers elsewhere in the image**, all written
`Discriminating=yes`. `__ct__7CMatrixFv` was a 40-byte body whose (length, masked fingerprint) key 22 of
our 14,879 rows wear; its name rested on position alone exactly as the rows the draft refused did.

So the check is now image-wide and the column says which level a row cleared:

| level | meaning | of the 27 that clear a tier |
|---|---|---|
| `image-wide` | one demo function and one of our rows in the whole image wear this key | **6** |
| `gap-only` | unique among its gap siblings; its twins live in other gaps | 7 |
| `no` | not unique even inside its gap — the wrapper families | 14 |

Only `image-wide` reaches the file. The other two are counted, named here, and reachable with
`--positional-min-evidence gap-only` (11 rows — the 6 plus 5, two `_sceRpcGetPacket` candidates being
lost to the identifier rule) or `any` (25 rows), and those runs write to
`game/demo_symbol_renames_7b_loose.csv` — the strict path refuses a below-`image-wide` row outright, so
the flag is a boundary and not a convention. §3's holdout is the independent check on the choice:
`--holdout-block 1` re-derived 274 `image-wide` pairs with none wrong and 11 `gap-only` pairs with **one
wrong** (`--holdout-block 8`: 148 and 2, both clean).

**Tier A cannot reach `image-wide`, and that is structural rather than a fact about this data.** A
tier-A key that is unique on both sides at the same length is precisely `address_matcher`'s
relinked-body acceptance condition — Task 7 would already have placed that pair, and it would be an
anchor, not a candidate. Tier A exists only where the key is ambiguous. The census prints the breakdown
rather than leaving it to be asserted:

```
by tier: tier A x image-wide 0, tier A x gap-only 6, tier A x no 13,
         tier B x image-wide 6, tier B x gap-only 1, tier B x no 1
```

All 19 tier-A candidates are `gap-only` or `no`; none is `image-wide`. All 6 accepted rows are tier B.
Tier A is kept all the same: it is live at the two looser levels, where it is the *stronger* of the two
rules, and the `Tier` column is what tells a reader of a loose file which rule a row rests on. The
"never" is also contingent on `address_matcher`'s pass-3 shape, and a lever that deletes its own hurdle
because a sibling module currently subsumes it becomes coupled to that module's internals.

The `gap-only` 7 are `seekoff__…basic_filebuf<w,…>`, `_sceRpcGetPacket` (twice — the same
`static`-in-two-translation-units shape as Task 7's `_request_end`), `sceSifUnloadModule`,
`sceSifSearchModuleByAddress`, `_fs_version`, `_lf_version`. The `no` 14 are wrapper families:
`sceSifQueryMemSize`/`MaxFreeMemSize`/`TotalFreeMemSize`/`BlockTopAddress`/`BlockSize`,
`_sceSifLoadModuleBuffer`/`sceSifStopModule`, `sceDmaSendN`/`sceDmaSendI`,
`Copy__12CZAnimArgCmdFv`/`Copy__14CZAnimArgValveFv`, and three `rt_msg_client_*`
(`get_local_ip`, `iget_local_ip`, `is_valid_outgoing_msg`). Each pair is the same
instruction stream differing only in an immediate — a syscall number, a query selector — and
`fingerprint` zeroes `addiu`/`ori` immediates **on purpose**, because that is how it sees through a
relink. Their masked hashes are equal by construction.

**A cheaper strengthener was tried and measured to fail.** `address_matcher.Side.anchors()` — the
distinct strings a body forms the address of — rescues **zero** of the 21 rows the image-wide rule
refuses: those bodies are SDK thunks and tiny constructors, and they reach no strings at all.

## 5. Lever 1: what it adds

```
lever 1 (positional, min evidence image-wide): anchors 987, gaps 156, candidates 528,
  no body evidence 501, evidence no: refused 14, evidence gap-only: refused 7,
  evidence image-wide: taken 6, our row already named 0

7b proposals: 6
```

The buckets sum to 528 at every evidence level, which they did not in the first draft.

All 6, from `game/demo_symbol_renames_7b.csv` — every one tier B, `image-wide`, `KeyPeers 1/1`:

| our address | sizes | ratio | gap | name |
|---|---|---|---|---|
| 0x00598b90 | 1456/2320 | 0.63 | 4 | `RemoteRespawn__10CZSealBodyFb` |
| 0x001af6f8 | 596/596 | 1.00 | 1 | `__ieee754_expf` |
| 0x002c1f10 | 364/376 | 0.97 | 2 | `HandleBombStateRequest__11CZBombStateFiUcP6CPnt3D` |
| 0x00634098 | 208/216 | 0.96 | 8 | `rt_msg_client_iupdate_all` |
| 0x001a52b8 | 176/176 | 1.00 | 1 | `deci2Putchar` |
| 0x001b4470 | 84/88 | 0.95 | 2 | `mceGetInfoApdx` |

The most interesting is `RemoteRespawn__10CZSealBodyFb` at **0x00598b90**: 1,456 bytes in the demo
against 2,320 in ours, the same prologue, a globally unique prologue hash, sitting in a four-function
gap — the remote-respawn path grew by 60 % between the two games, which is the shape you would expect of
the online respawn rules changing. `HandleBombStateRequest` (0x002c1f10) is the demolition objective's
network handler.

**What the two corrections cost, honestly.** The first draft proposed 16. The image-wide rule takes away
9 of them. Raising tier A's floor from 32 to note 44's 64 bytes takes away the rest of the small ones —
`open`, `__ct__7CMatrixFv`, `NetRegisterMallocFreeCallbacks`, `rt_mutex_platform_unlock`,
`MissionEndCleanup__15CZPlayerMapItemFv` were all under 64 B, and four of the five were image-wide
failures anyway. What survives is the set whose names no other function in either image could have
produced.

## 6. The other 501: what the lever sees and refuses

501 of the 528 candidates produced no body evidence at all. **126 of them carry an engine-shaped name**,
and those are the most valuable output of this task that is not a proposal — they are leads with an
address, not names. The largest twelve, by demo body size, with our size beside it:

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
```

Read the size columns. `ai::AddNoise` is 892 bytes in SOCOM 1 and 92 in ours. That is not an edit, it is
a rewrite — or the positional guess is simply wrong there, and nothing in this task can tell which.
> *Note (2026-09-24, research/53 §6): a shared-string key contradicts 6 of these 501 leads (`UIInvitePlayerToClan*`, `rt_time_get_time_string*` among them); in all six the positional pairing is the less size-consistent reading. The leads stay leads. research/52 §8 adds: the call graph confirms 67 and contradicts 22 of the 501 — in gaps 49, 11 and 8 the positional pairing is one row off, so `__ct__9CGameMenuFv` is at 0x00369b60, not 0x00369eb0.*

`ToQuat__7CMatrixCFP5CQuat` at 0x00308210 is the tightest lead in the set: a gap of **one**, 524 bytes
against 432, in the middle of a `CMatrix` cluster Task 7 already placed. If any one of these is worth a
human's half hour, it is that one.

## 7. Lever 2: the bridge, and why it adds nothing

`game/demo_scus_973_68/SCUS_973.68` — build id `SOCOM 2 v0001 17:30:02 Aug 18 2003`, 4.56 MB, one
`PT_LOAD` at 0x100000, **zero symbols** — sits between SOCOM 1 and retail r0001 in time. Being stripped,
it can never contribute a name; its only possible contribution is **body evidence**, as a stepping
stone: demo1 → demo2 → retail, each hop by `address_matcher.match`.

### The function table, and its measured limits

demo2 has no symbols, and `tools_py` had no reusable Ghidra-free boundary tool (`find_interior_functions
.py` spells the same rules but is a script that wants a Ghidra CSV to compare against), so
`symbol_levers.scan_functions` derives one from the bytes: **what follows a `jr $ra` and its delay slot
(past any zero padding) is a function start** — on MIPS you cannot fall through a return, and this rule
does nearly all the work — plus **every `jal` target inside the image**, which keeps a leading data block
out of the first function. A range then runs to the next start, with trailing zero padding trimmed but
**never past the delay slot of the last `jr $ra`** (a `nop` delay slot *is* a zero word; trimming it cut
every such function one instruction short, and fixing that took the scan from 85.3 % to 94.6 %). A range
with no `jr $ra` in it is dropped as data or a jump table.

The limits are measured, not asserted, by running the same scan on **demo1**, whose `.symtab` is the
ground truth:

```
the boundary scan, checked on demo1's own .symtab: 9532 ranges for 9703 real functions,
9353 starts right, 9177 with both boundaries right (94.6%)
```

Recall 96.4 %, precision 98.1 %, and 94.6 % of real functions get **both** boundaries right and so
fingerprint like the real thing. A third seed — every 32-bit word pointing at an aligned address inside
the image, i.e. vtable and constructor-table entries — is implemented and **off by default**, because it
measures worse: a vtable slot pointing into the middle of a function splits it, and
both-boundaries-right falls from 94.6 % to 92.2 %. `find_interior_functions.py` also seeds on
`lui`+`addiu`-formed addresses, which this does not try; whether that beats 94.6 % is unmeasured.

**A mis-bounded range costs recall, never correctness**, because `am.match` needs equal length *and* an
equal masked hash, so a wrongly cut body fingerprints like nothing on either side and can only suppress
a match. That is no longer only an argument: `BridgeSafetyTest` builds demo2 fixtures with a range
split, a range merged, and both, and asserts the composition count drops while every name that still
lands, lands on the right row. What the scan cannot see at all is a function that is never a `jal`
target and never follows a return; its bytes are absorbed by its predecessor, which spoils that one too.
On demo2 the scan yields **12,250 ranges** — between demo1's 9,703 and retail's 14,879, which is where a
build five months before release should sit.

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

* hop1 (demo1 → demo2) resolves **859** of the demo's 9,703 functions. Task 7's direct match placed
  **987**. The bridge is *strictly worse at the hard hop*, because the hard hop is the same one: the
  SOCOM 1 → SOCOM II edit is where the year of changes lives, and the Aug 2003 demo is already on the
  far side of it.
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

* `tools_py/symbol_levers.py`: `scan_functions`/`scan_accuracy` (a Ghidra-free boundary scan for a
  stripped image), `anchors_from_details`/`anchor_composition`/`proved_anchors`, `anchor_gaps`,
  `_tier`/`key_census`/`_evidence`, `positional`, `size_ratio_calibration`, `holdout`, `bridge`,
  `proposals_7b`/`write_proposals_7b`, and `POSITIONAL_RULE`/`POSITIONAL_CAVEAT`/`BRIDGE_RULE` as
  constants so the CSV header and the code cannot drift apart.
* `tools_py/ghidra_symbol_match.py` gains `--positional`, `--positional-min-evidence`, `--bridge`,
  `--holdout`, `--holdout-block`, `--size-ratio-calibration` and `--renames-7b`. Its Task 7 behaviour is
  untouched: with none of those flags the run prints and writes exactly what §3 of note 44 quotes, and
  `--renames` produces a byte-identical file. Flags that would be silent no-ops are refused rather than
  ignored, and a bad output path is one `NO-DATA:` line, not a traceback.
* `tools_py/tests/test_symbol_levers.py`, **57 tests**, on synthetic MIPS fixtures — an anchor gap that
  lines up and one that does not, anchors out of order, a gap in another `PT_LOAD`, the three evidence
  levels, the tier×evidence census, a split and a merge that cancel inside one gap, tier B straddling
  the size-ratio cut (accepted at 0.629, refused at 0.489 — and each leg asserts the ratio it actually
  produced, because the first version of that test computed the accept tail as `d_size * 0.63` instead
  of `d_size / 0.63` and silently ran at 0.86), the strict path refusing a loose row, a holdout that
  re-derives a pair *wrongly*, a bridge that agrees, one that contradicts, and one whose demo2 table is
  mis-bounded. No disc, no demo, no ELF on disk. `test_elf_symbols`, `test_ghidra_symbol_match`,
  `test_address_matcher` and `test_carry_names` still pass: 167 together.
* `game/demo_symbol_renames_7b.csv` — git-ignored, 6 rows, `Address, Current, Proposed, Mangled, Source,
  Tier, Evidence, KeyPeers, DemoAddr, DemoSize, OurSize, Ratio, GapSize`, with both acceptance rules,
  the holdout's bias, the anchor composition, and every Task 7 threshold the file's contents depend on
  (`--min-score`, `--good`, `--min-size`, and how many Task 7 identifiers are already spent) written
  into `#` lines above the column header. A run below `image-wide` writes
  `game/demo_symbol_renames_7b_loose.csv` instead; `write_proposals_7b` refuses the strict path for
  such a row whoever calls it.

Not delivered, on purpose: **no rename was applied**, `recomp/socom2_ghidra.csv` is byte-for-byte
unchanged, `docs/research/44-demo-symbols.md` is untouched (the controller owns it), and **no demo bytes
are in the repository** — names and addresses only.

## 9. What is left

* **The 126 engine-shaped leads in §6** are the best thing here that is not a proposal. They need
  disassembly, not a hash.
* **The 21 candidates behind `--positional-min-evidence`** (5 more rows at `gap-only`, 19 at `any`) need
  one decision, not more evidence: are we willing to trust link order alone for a wrapper family, or for
  a routine whose twin lives in another gap? Every such row carries `Evidence` and `KeyPeers` saying
  exactly what it rests on, and they land in their own file — and §3's block-1 holdout has already
  caught `gap-only` being wrong once in eleven where `image-wide` was never wrong in 274, so the honest
  recommendation is no.
* **One inherited gap, deliberately not fixed here.** Neither this file's `proposals_7b` nor Task 7's
  `proposals` checks a proposed identifier against the 113 names already in `recomp/socom2_ghidra.csv`'s
  own `Name` column. None of these 6 collides today. Whatever APPLIES either file is the right place for
  that check, and fixing it in one of the two would be worse than in neither.
* **The bridge is done.** The boundary scan is already at 94.6 % and the failure is not the table — 130
  of 131 candidates die on a hop no table can help with. If a *named* intermediate build ever turns up,
  the lever's code is ready for it.
* Note 44 §6's conclusion stands unchanged: the ceiling is that SOCOM II is a different build of the
  game, and neither of these levers moves it.
