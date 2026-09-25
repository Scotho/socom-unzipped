# 54. Member-offset multisets as a looser body key

Date: 2026-09-24. Sprint 12 research wave, question 9 of the cloud handoff §4
(`docs/superpowers/plans/2026-09-24-sprint-12-cloud-handoff.md`). Read-only: two ELFs, one Ghidra table.
No game was run, no Ghidra process started, `recomp/socom2_ghidra.csv` is **unchanged**, and no name is
applied: the pairs this note measures are a git-ignored file. `docs/research/44-demo-symbols.md` and
`45-positional-and-bridge-names.md` are the notes this one extends; neither is edited.

**The one-line answer: the member-offset multiset is a real body key, and it adds names the fingerprint
cannot reach. Keyed on (opcode, displacement), unique on both sides, it pairs 590 functions: 219 agree
with Task 7's 987 and none contradicts them, and 366 are beyond the 987 at size ratio ≥ 0.50. The
holdout the brief asks for is structurally blind to this key (0 wrong at every setting, for a reason §3
gives), so the false-pair rate was measured against link order instead. Link order says the loose rule
carries about 3–11 false pairs in 366, nearly all of them in keys of 3–5 accesses. The recommended rule
(R7 below) keeps 193 pairs, 54 of them engine-shaped, with an estimated 0 false (2σ bound about 5).** The
key also backs **research/45's tightest lead**: `ToQuat__7CMatrixCFP5CQuat` at 0x00308210 wears a unique
29-access key that is identical on both sides. And it catches the positional walk misaligned across one
49-function gap, which is the failure research/45 §2 described in theory.

Every number below names the command that produces it. There is one command:

```
# A -- the census, the pairs, the link-order check, the holdout, the rules, the regions, the leads (§1-§6)
python tools_py/research/symbols/offset_multiset.py --csv game/offset_multiset_new.csv
```

About 25–30 seconds. It re-derives Task 7's 987 pairs in-process with
`ghidra_symbol_match.match(prefix=True)` (research/44 command A's match: the json does not carry the
demo address), checks the count against `game/demo_symbol_matches.json` (`Task 7 re-derived: 987 pairs
(... says 987), 828 PROVED, 159 prologue-only`), and imports `address_matcher`, `symbol_levers` and
`ghidra_symbol_match` rather than re-spelling them. `--csv` writes the 193 pairs from R7 (names,
addresses, sizes and access counts, **no bytes**) to `game/offset_multiset_new.csv` (git-ignored, 194
lines with the header). Section tags `[1]`–`[5]` in the output match the sections of this note, with
`[2b]` for §2a and `[3b]` for §3a.

## 1. The key, and what it drops

For every function with bytes (demo 9,703; ours 14,828: our 14,879 rows less the 51 with no bytes) the
tool walks the body and takes each load or store (`lb lbu lh lhu lw lwu lwl lwr ld ldl ldr lq sb sh sw sd
swl swr sdl sdr sq lwc1 ldc1 swc1 sdc1 lqc2 sqc2`, a hand decoder of the primary opcode, R5900 forms
included) with its signed 16-bit displacement. It then drops four kinds of access, each counted.
(Command A, `[1]`.)

| side | accesses | `$sp` | `$gp` | `$zero` | lui-formed (a global) | kept |
|---|---|---|---|---|---|---|
| demo | 233,363 | 87,117 | 7,224 | 1 | 10,768 | 128,253 |
| ours | 352,074 | 108,362 | 805 | 8,035 | 27,419 | 207,453 |

* The brief asked for `$sp` and `$gp` to be dropped, and they are (the table gives both counts). The tool
  also drops **lui-formed** accesses, meaning any access based on a register that a `lui` (or a
  `lui`+`addiu`/`ori` pair) loaded with an address. This is `address_matcher.mask_address_operands`'
  rule. Such a displacement is the low half of a global's address and moves with every relink, so
  keeping it would give a relinked routine a different key in each image.
* The `$zero` column is almost all ours: 112 rows carry one, and the heaviest are very large rows
  (1,265 accesses in a 39,532-byte row at 0x003d6750; about 550 each in four rows of 7.5–10.8 KB at
  0x001d20c8–0x001d2d98). They read like data inside rows the Ghidra table calls functions. They are
  dropped either way, and this note does not trace them further.
* Our image has 9 times fewer `$gp` accesses than the demo (805 against 7,224). SOCOM II reaches small
  globals by `lui` far more often. That is a fact about the build, and it is why the lui mask matters.

Three keys are built over what is kept:

| key | what it is | functions ≥ 64 B with ≥ 3 accesses (demo / ours) | of those, key unique on its own side |
|---|---|---|---|
| **K1 opdisp** | the multiset of (opcode, displacement) | 5,103 / 7,793 | 4,187 / 5,930 |
| **K2 disp** | the multiset of displacements alone | 5,103 / 7,793 | 3,838 / 5,489 |
| **K3 objptr** | K1 over accesses based on `$a0`, `$v0`, `$s0`–`$s7` only | 4,694 / 6,925 | 3,775 / 5,067 |

The fingerprint (`tools_py/fingerprint.py`) keeps every displacement in its exact place in the stream.
These keys keep the displacements and throw away the stream: the order, the registers, every
non-memory instruction. That is the point of them. An edited routine that still touches the same
fields keeps its key when an inserted instruction has already changed its fingerprint.

## 2. The pairs

Rule: the key is worn by **exactly one** function on each side across the whole image (functions under
64 B count as peers), it has **≥ 3 accesses**, and **both bodies are ≥ 64 B**. (Command A, `[2]`.)

```
K1 opdisp: pairs 590; overlap the 987: agree 219 (exact 155, prefix 31, prefix+size 13, relinked-body 20), contradict 0; beyond the 987 371, of which ratio >= 0.50 366 (our row still FUN_ 366)
K2 disp:   pairs 499; overlap the 987: agree 162 (exact 119, prefix 25, prefix+size 8, relinked-body 10), contradict 0; beyond the 987 337, of which ratio >= 0.50 331 (our row still FUN_ 331)
K3 objptr: pairs 477; overlap the 987: agree 181 (exact 125, prefix 31, prefix+size 8, relinked-body 17), contradict 0; beyond the 987 296, of which ratio >= 0.50 295 (our row still FUN_ 295)
```

| key | pairs | agree with the 987 | contradict the 987 | beyond the 987 | … and ratio ≥ 0.50 |
|---|---|---|---|---|---|
| K1 opdisp | 590 | 219 | **0** | 371 | **366** |
| K2 disp | 499 | 162 | **0** | 337 | 331 |
| K3 objptr | 477 | 181 | **0** | 296 | 295 |

* **No contradiction, with any key.** None of the three ever pairs a function of the 987 with anything
  other than its Task 7 partner. For the 828 proved pairs that is nearly guaranteed (§3 explains why).
  For the **159 prologue-only pairs** it is not guaranteed, because those bodies were edited and their
  keys need not agree. K1 lands on 44 of them and agrees with all 44 (31 `prefix`, 13 `prefix+size`;
  12 engine-shaped). Among them are `Read__7CFileCDFPci` (0x0039d960, 768/820 B, 53 accesses),
  `ToEuler__7CMatrixCFP6CPnt3D` (0x00308020), `Read__Q23zdb7CVisualFRQ23zar4CZAR` (0x003c3570),
  `FindChild__Q23zdb5CNodeFPCcb` (0x00315d00), `sceIoctl` and `sceMpegCreate`. Each is now a pair with
  two independent keys, a prologue hash and an offset multiset, each unique on both sides.
* Every one of the 366 lands on a row that is still `FUN_`.
* K1 is the widest key and the one the rest of this note leads with. K2 (displacements alone) is looser
  in content yet pairs *fewer* functions. Dropping the opcode merges more keys, so fewer stay unique,
  and §2a shows that what it does pair is less reliable. K3 is narrower and pairs fewer still.
* `game/demo_symbol_renames_7b.csv`'s six rows against K1: `agree 1, silent 5`, no contradiction.

### 2a. The false-pair rate, measured by link order

The holdout in §3 cannot see this key's errors, so the rate is measured with evidence the key does not
use: **link order**. Link order survives 92–98 % inside each of our overlays (research/45 §1). For each
pair the tool takes the two nearest reference pairs by our address inside our PT_LOAD and asks two
questions:

* **bracket:** does the demo address lie strictly between the two references' demo addresses?
* **near:** does it lie within 64 KB of either reference's demo address, on that reference's side?

`bracket` also fails a true pair that sits at a translation-unit boundary, where the far reference is in
another unit. `near` tolerates that.

Each test has a **truth rate** (the 987, leave-one-out) and a **null rate** (the same pairs with the demo
side rotated by 20–80 % of the list, so every row meets a demo function from elsewhere). The estimate
solves `p_obs = (1 − f)·p_true + f·p_null` for f. It takes p_true from the **159 prologue pairs**,
because those are edited routines, the population the new pairs come from. (Command A, `[2b]`.)

```
truth, ref = the other 986, 828 PROVED    bracket  740/ 823 (89.9%, null 1.2%)  near  794/ 823 (96.5%, null 10.2%)
truth, ref = the other 986, 159 prologue  bracket  139/ 158 (88.0%, null 1.1%)  near  153/ 158 (96.8%, null 0.9%)
```

| K1, new pairs (ratio ≥ 0.50) | n | near, ref = the 987 | est. false | near, ref = 987 + the new pairs | est. false |
|---|---|---|---|---|---|
| all | 366 | 342/364 (94.0 %) | 11 | 350/364 (96.2 %) | 3 |
| 3–5 accesses | 104 | 93/103 (90.3 %) | 7 | 96/103 (93.2 %) | 4 |
| 6–10 accesses | 106 | 99/106 (93.4 %) | 4 | 102/106 (96.2 %) | 1 |
| 11–20 accesses | 87 | 83/86 (96.5 %) | 0 | 84/86 (97.7 %) | 0 |
| ≥ 21 accesses | 69 | 67/69 (97.1 %) | 0 | 68/69 (98.6 %) | 0 |

K2, all new pairs: near 298/329 (90.6 %), est. false 22 (ref = the 987); K2 is the weakest of the three.
K3: 276/293 (94.2 %), est. false 8. The `bracket` test puts every figure higher (K1, all: 287/364, est.
false 39). The pairs it fails are real, as can be checked by eye. `qsort` (2,596/2,540 B, 88 accesses)
sits between `_Bfree` and `copysign`, which are two libc units. `SlerpFaster__5CQuat` sits just before
the `CQuat` cluster, and the anchor below it is in another unit. So `near` is the test that measures
false pairs, and `bracket` measures unit boundaries as well.

Reading it: **the error lives in small keys.** At 3–5 accesses the key is a handful of field offsets, and
edited code produces coincidental unique matches. `SetModelname__Q23zdb5CNodeFPCc` and
`SetMovie__15CCinematicStateFPCc` (3 accesses each) both land in our `CZWeapon` setters at
0x003d24c0/0x003d2ac0, far from their own classes. At ≥ 11 accesses the estimate is 0.

## 3. The holdout (research/45 §3), and why it cannot see this key

Research/45 §3's method is reused unchanged: the truth is the 828 PROVED pairs, the 159 prologue pairs
always stay anchors, the folds are 3, and blocks of 8 and of 1 are run. A pair is re-derived if it
touches a held-out function, and wrong if it is not Task 7's pair. Two uniqueness scopes are run:
**image-wide**, and **pool** (unique among the functions the kept anchors leave, which is the setting a
pass run after Task 7 would see). (Command A, `[3]`.)

| block, scope | K1 alone / +prologue / +callees | K2 | K3 |
|---|---|---|---|
| 8, image-wide | 175 / 175 / 82, **0 wrong** | 129 / 129 / 62, 0 wrong | 142 / 142 / 76, 0 wrong |
| 8, pool | 193 / 193 / 97, 0 wrong | 136 / 136 / 68, 0 wrong | 156 / 156 / 87, 0 wrong |
| 1, image-wide | 175 / 175 / 91, 0 wrong | 129 / 129 / 68, 0 wrong | 142 / 142 / 84, 0 wrong |
| 1, pool | 187 / 187 / 100, 0 wrong | 140 / 140 / 73, 0 wrong | 154 / 154 / 90, 0 wrong |

**Every setting is zero-wrong, and the zero carries no information.** A proved pair is the same stream
on both sides up to masked addresses, so its two bodies wear the *same* key by construction. The rule
can then either pair them (the key is unique) or refuse them (it is not). It can never pair them
wrongly. Research/45 §3 warned that its holdout "can barely speak for the image-wide rule at all". For
this key it cannot speak at all. The 175 is simply how many of the 828 have a unique K1 key of ≥ 3
accesses; with the 44 prologue pairs from §2 it makes up the 219 overlap. The two findings that do
carry information are §2's zero contradictions over the **44 edited prologue pairs**, and §2a's link
order.

So the brief's instruction ("if the multiset alone is never zero-wrong, measure it combined with…") is
answered from §2a rather than from here. The two tightenings were measured anyway, on the pairs beyond
the 987 (Command A, `[3]` last block and `[3b]`):

* **+ prologue** (equal masked 16-instruction prologue, 7b's tier B key): keeps **17** of the 366. Edited
  routines rarely keep 64 bytes of prologue *and* have a unique offset multiset, so almost everything
  this key can add has a different prologue.
* **+ callees** (every demo callee that is one of the 987 maps into our body's call set, and at least one
  does): keeps **73**.

The pass as it would run, with all 987 as anchors and pool uniqueness, gives about the same count:
K1 alone 372 (367 at ratio ≥ 0.50), +prologue 17, +callees 73.

### 3a. The candidate rules

Command A, `[3b]`. These are the K1 pairs beyond the 987 at ratio ≥ 0.50, scored by §2a's `near` test.

| rule | pairs | engine-shaped | near, ref = the 987 | est. false |
|---|---|---|---|---|
| R1 K1, ≥ 3 accesses | 366 | 116 | 342/364 (94.0 %) | 10.9 |
| R2 K1, ≥ 6 accesses | 262 | 72 | 249/261 (95.4 %) | 3.9 |
| R3 K1, ≥ 11 accesses | 156 | 39 | 150/155 (96.8 %) | 0.1 |
| R4 K1 + callees | 73 | 22 | 72/73 (98.6 %) | 0.0 |
| R5 K1 + prologue | 17 | 4 | 16/17 (94.1 %) | 0.5 |
| R6 K1 + (callees or prologue) | 85 | 24 | 83/85 (97.6 %) | 0.0 |
| **R7 K1, ≥ 11 accesses, or callees/prologue** | **193** | **54** | **186/192 (96.9 %)** | **0.0** |

R7 matches the truth rate of the 159 edited pairs (96.8 %) with 192 decided pairs. The binomial error
on 192 at 97 % is about 1.2 points, so the 2σ bound is about 5 false (arithmetic on command A's two
rates, not a line it prints). The six R7 pairs that are not
near a reference are all listed by command A: `Merge__9AI_PARAMS` (69 accesses), `AuxInitNetwork`
(18), `fastallo_Terminate` (26), `SetConnectionInfo__13CZOnlineLobby` (18, prologue equal),
`JoinGameStateHandler` (3, prologue and callees equal), `Build__6CBBox8` (48, 196/196 B). By key
strength each reads as a moved unit, not a false pair. That is a judgement; the note does not claim it
as a measurement.

## 4. Where the new pairs are

Command A, `[4]`. "Engine-shaped" is `ghidra_symbol_match.is_engine` (a Metrowerks member or a
`z…`/`hud…` free function). Classes use `readable()`, copied from
`tools_py/research/symbols/readable_names.py`.

| PT_LOAD of ours | R1 (366) | … engine-shaped | R7 (193) | … engine-shaped |
|---|---|---|---|---|
| 0x100000–0x1d5000 boot loader | 45 | 0 | 24 | 0 |
| 0x1d5000–0x1d5600 | 0 | 0 | 0 | 0 |
| 0x1e7000–0x408480 FTSCore | 156 | 91 | 77 | 40 |
| 0x4c5380–0x66a000 ZSealEtc | 165 | 25 | 92 | 14 |
| **total** | **366** | **116** | **193** | **54** |

K2 splits its 331 as 33 / 0 / 138 / 160 and K3 its 295 as 40 / 0 / 133 / 122 (the same command,
`[4] K2`/`K3` lines).

* **The engine names come mostly from FTSCore**: 91 of R1's 116 engine-shaped names are there, over 76
  distinct readable classes (R7: 54 over 41), and no single class dominates. The top R1 classes are
  `CAiEvent`, `CZAnimMain`, `CZAnimNameIndexTable`, `CSndSequence` and `CZWeapon` (3 each); the rest have
  2 or fewer.
* **ZSealEtc's new pairs are mostly not engine-shaped** (140 of 165 in R1): the networking and support
  libraries (`GCD`, `QUO`, `ConstructQueue`, `fastallo_Terminate`) and a speech recogniser's user-word
  trainer (`TrainFree`, `ProcessDelayBlock`, `userwordStartUserWordTraining`, §5). The boot loader's 45
  are libc and SDK (`qsort`, `fseek`, `__kernel_rem_pio2` under K3).

The twelve largest R7 pairs (demo/our size), all shown by command A:

| our address | demo/our B | accesses | name |
|---|---|---|---|
| 0x0059ba80 | 4948/5260 | 160 | `Load__17CharacterDynamicsFRC8CRdrFile` |
| 0x00196d38 | 2596/2540 | 88 | `qsort` |
| 0x00365d50 | 1396/2520 | 9 (callees agree) | `ParseButtonAnim__FP5_zrdrP10ActionItem` |
| 0x00193a90 | 1164/1196 | 79 | `fseek` |
| 0x00307b40 | 1096/1116 | 61 | `Resize__5CBitsFUi` |
| 0x002df160 | 1056/1012 | 45 | `CircleSegmentClip__Q23zdb11CCircleClipFP6CPnt4D…` |
| 0x00286e50 | 916/960 | 47 | `ClipToBox__FRC6CPnt3DRC6CPnt3DR6CPnt3Dffff` |
| 0x0033f8b0 | 912/996 | 40 | `snd_SendIOPCommandNoWait__FiiPcPFUiUl_vUl` |
| 0x0050b5c0 | 864/872 | 55 | `ConstructQueue` |
| 0x0034f3c0 | 848/884 | 40 | `zSysReset__Fv` |
| 0x006277e8 | 784/776 | 96 | `GCD` |
| 0x00627270 | 764/784 | 72 | `QUO` |

The twelve largest engine-shaped R7 pairs add `ProcExpr__16CZAnimExpressionFPf` (0x0025e960, 760/752),
`LimitUVs__3zdbFPsPsPs` (0x003bfb60), `Merge__9AI_PARAMS…` (0x00533db0), `Parse__6CTMoveFP5_zrdr`
(0x005d64b0), `PlaceLaterally__10CZSealBody…` (0x005b3a60), `ZAnimLoad__8CMissionFv` (0x002abad0),
`SlerpFaster__5CQuat…` (0x00306890) and `Play__11CSndJukebox…` (0x00348dc0). `CharacterDynamics::Load`
(4,948 B against 5,260 B, 160 accesses, callees agree) is larger than anything research/44 or /45
placed: research/44 §4's largest engine match was 1,560 B and prologue-only, and its largest match of
any kind was `_getAllRefs` at 1,796 B.

## 5. Against research/45 §6's positional leads

Command A, `[5]`, recomputes the leads the way research/45 made them: untiered positional candidates with
an engine-shaped name. It gets **156 gaps and 126 leads**, research/45's figures. Two tests are run on
them.

**The unique pairing (the §2 rule).**

* **K1 agrees with 19 leads and contradicts none.** K3 agrees with 13 and contradicts none.
* K2 agrees with 12 and contradicts **1**: `GetDirVec__6CAiMapFQ26CAiMap3DIRR6CPnt3D`. Position puts it at
  0x00519080 (168 B, **0** accesses). The key puts it at 0x00519130 (280 B, 28 accesses; the demo body
  is 256 B with 28 accesses). The next demo function is `dummy_cell__6CAiMapFv`, an 8-byte body, so the
  two-function gap is a swap. **The key is right and the positional lead is wrong.**
* **`ToQuat__7CMatrixCFP5CQuat` at 0x00308210 is confirmed.** Its K1 and K2 keys are identical on both
  sides (29 accesses each), unique image-wide, with Jaccard 1.00. The pair is in R7 and in
  `game/offset_multiset_new.csv`, so research/45's "worth a human's half hour" lead now has body
  evidence.

**The multiset similarity (Jaccard of the K1 multisets) of each positional partner.** A random partner
would rank first with probability about 1 in 14,828.

| figure | count |
|---|---|
| leads | 126 |
| partner ranks 1st in its gap (gaps of more than one: 112) | 94 |
| partner ranks 1st image-wide among our 14,828 (ties allowed) | 86 |
| … strictly 1st, no tie | 53 |
| mutual strict best (our row's best demo match is the lead's demo function too) | 50 (43 with J ≥ 0.5) |
| partner has Jaccard 0 | 27 |
| median Jaccard | 0.60 |

Research/45's twelve largest leads:

| our address | demo/our B | gap | accesses demo/ours | Jaccard | rank in gap | rank image-wide | name |
|---|---|---|---|---|---|---|---|
| 0x00272c30 | 1936/1676 | 8 | 85/104 | 0.52 | 1 | 1 | `ActivateArgV__6CZAnimFPc` |
| 0x002227b0 | 1408/1224 | 4 | 107/101 | 0.42 | 1 | 1 | `TickSealCone__15CZPlayerMapItem…` |
| 0x00369210 | 1308/1212 | 11 | 74/78 | 0.43 | 1 | 1 | `Clear__9CGameMenuFv` |
| 0x002222e0 | 1188/1232 | 4 | 73/61 | 0.49 | 1 | 1 | `SetViewCone__15CZPlayerMapItem…` |
| 0x00369eb0 | 1156/192 | 11 | 63/2 | 0.02 | 6 | 2930 | `__ct__9CGameMenuFv` |
| 0x00228ee0 | 988/1356 | 4 | 52/64 | 0.18 | 1 | 1 | `PlayCamera__16CZHudMissionCams…` |
| 0x00308b00 | 952/1000 | 8 | 54/53 | 0.88 | 1 | 1 | `DistToVector__6CPnt3D…` |
| 0x00599690 | 920/376 | 4 | 27/11 | 0.09 | 1 | 1011 | `CreateRemoteSeal__10CZSealBody…` |
| 0x002734b0 | 916/712 | 8 | 40/28 | 0.31 | 1 | 1 | `Activate__6CZAnimFP6CZAnim` |
| 0x0050df90 | 892/92 | 6 | 20/0 | 0.00 | 5 | 4161 | `AddNoise__2aiFPC6CPnt3DP6CPnt3DRC5PNT2D` |
| 0x0050df30 | 880/92 | 6 | 17/0 | 0.00 | 4 | 3935 | `AddNoise__2aiFP6CPnt3DRC5PNT2D` |
| 0x0050dff0 | 864/416 | 6 | 20/5 | 0.19 | 2 | 319 | `MakeNoise__2aiFP6CPnt3DRC5PNT2D` |
| 0x00308210 | 524/432 | 1 | 29/29 | **1.00** | 1 | 1 | `ToQuat__7CMatrixCFP5CQuat` |

**The two levers confirm each other on the edited engine routines.** For seven of the twelve largest
leads, the positional partner is the single most similar body in our whole image by field offsets, not
merely the best in its gap. That is the tightest test of both: position chose the row without looking
at the body, and the offsets chose it without looking at the position. The five that fail are exactly
the five whose size ratio is under research/45's own 0.50 cut: `__ct__9CGameMenu` 1156→192,
`CreateRemoteSeal` 920→376, `MakeNoise` 864→416, and the two `ai::AddNoise` 892/880→92 with **no** kept
accesses on our side. For those five the key agrees with research/45's doubt: either rewritten beyond
recognition, or not the partner at all. Of the thirteen rows above, only `ToQuat` is a unique-key pair.
The other seven rank-1 partners are similar but not identical, which is what an edited routine looks
like. Jaccard rank is **evidence, not a proposal rule**. This note
measured no false-pair rate for it.

**All 528 positional candidates (any tier, any name).** K1 agrees with 46 and contradicts 15; K2 is at
35/17, K3 at 35/11. All 15 of K1's contradictions come from 8 key pairs in two places:

* **One 49-function gap is misaligned (13 of the 15).** This is our 0x004df288–0x004e5948 against the
  demo's 0x0034e610–0x003539d8 (command A prints each gap that holds a contradiction), a speech
  recogniser's user-word trainer (`TrainFree`, `InitUserWordTraining`,
  `ProcessDelayBlock`…). The counts on the two sides agree, but the order does not. Every key pairing
  there has the better size: `TrainFree` (132 B, 13 accesses) goes by position to a 3,248-byte body, by
  key to a 132-byte body with 13 accesses. `ProcessDelayBlock` (352 B, 46 accesses) goes by position to
  60 B with 0 accesses, by key to 364 B with 46. `cbScoreUserWordResultAvailable` (80 B, 18 accesses)
  goes by position to 80 B with 0 accesses, by key to 80 B with 18. By size the key's partner is
  closer in 5 of the 7 key pairs and tied in 1. In the other one position is closer:
  `SendPartOfLabelsToEngine`, 212 B in the demo, 256 B by key, 204 B by position. Every key partner
  sits one to several rows away from the positional one, which is the shift pattern of research/45
  §2's "a split and a merge cancel", seen in real data. The body rule kept it out of research/45's file
  (every candidate in that gap is untiered). Three of the 7 key pairs clear R7: `TrainFree`,
  `cbScoreUserWordResultAvailable` and `ProcessDelayBlock`, all in `game/offset_multiset_new.csv`.
* **`NetGetAverageDelayToClient` against `NetFindClientByIpAddress` (2 of the 15)** is a two-function
  disagreement: 152 B and 7 accesses in the demo, by key 216 B with 7, by position 284 B with 11.
  Undecided. Both are 7-access keys in a 6–10 bucket whose estimated error is about 1 in 100.

## 6. Recommendation

**Pass `offset-multiset`, score 0.75.** It belongs below `positional` (0.80), whose own holdout is
informative. It sits level with the proposed `vtable-slot` and above `prefix` (0.60/0.70).

**Rule, in code** (every piece is in command A):

1. The key is K1: the multiset of (primary opcode, signed displacement) over every load/store not based
   on `$sp`, `$gp`, `$zero` or a lui-formed address register (`address_matcher`'s mask).
2. The key is worn by exactly one demo function and exactly one of our rows, image-wide.
3. It has ≥ 3 accesses, both bodies are ≥ 64 B, and the size ratio is ≥ 0.50.
4. The pair is neither of the 987 on either side, and our row is still `FUN_`.
5. **Either** the key has ≥ 11 accesses, **or** every demo callee that is one of the 987 maps into our
   body's call set (at least one does), **or** the masked 16-instruction prologues are equal.
6. Task 7's identifier hurdles, unchanged.

**Evidence column**, in the pass's own words: `offset multiset unique both sides, 29 accesses, ratio 0.82`
(`+ callees` or `+ prologue` where one of those, not the access count, carried it).

**Yield: 193 new pairs, 54 engine-shaped** (77 FTSCore, 92 ZSealEtc, 24 boot loader). Estimated false:
0, with a 2σ bound of about 5 (§3a). The identifier hurdles and collisions with other proposal files are
**not** measured here. The applier's hurdles will take some rows (templates, colliding readable names),
so the count that reaches the csv is below 193, by an amount this note cannot give.

**Not recommended:** K2 (displacements alone), the key with the most estimated false pairs (22 in 331);
K3, which only narrows K1 (295 pairs, no better rate than R7's cut); and R1 at ≥ 3 accesses with no
tightening (about 3–11 false in 366).

**A second, smaller use:** the 44 prologue-only pairs K1 confirms (§2) now rest on two independent keys,
each unique on both sides. Research/44's hurdle 3 refuses a pair whose *only* evidence is a prologue.
These pairs have more than that, and the applier could admit them under `offset-multiset` with
`Evidence: prologue + offset multiset unique both sides`. Twelve are engine-shaped, including
`Read__7CFileCDFPci` and `ToEuler__7CMatrixCFP6CPnt3D`.

**What this does not move:** research/44 §6's ceiling. 193 names is 2 % of the demo's 9,703. The key
reaches edited routines only when they kept their field accesses and nothing else in either image has
the same access set. The big rewritten routines (`ai::AddNoise`) have lost their accesses, not moved
them.

## What this means for a task

| task | finding | what it changes |
|---|---|---|
| Goal 1 / the proposals files (Task 7 family) | K1 unique both ways adds 366 pairs beyond the 987 and contradicts none of the 987 (§2). The recommended cut R7 keeps 193 (54 engine-shaped) at an estimated 0 false by link order (§3a) | A new proposals file (or a pass in `ghidra_symbol_match`) named `offset-multiset`, score 0.75, with the rule in §6. Implementing it is a small function over `address_matcher.Side` plus `symbol_levers._prologue`. Command A is the reference implementation, and `game/offset_multiset_new.csv` is its expected output |
| Goal 1 / hurdle 3 (`prefix` never proposed) | 44 of the 159 prologue-only pairs are independently confirmed by a unique offset multiset, 0 contradicted (§2) | These 44 can be proposed under `offset-multiset` with two keys as evidence. Hurdle 3's reason (a prologue alone is not a body) no longer applies to them. The ruling is the controller's |
| research/45's holdout as the standard false-pair test | For any body key that is equal on both sides of a proved pair, the holdout is zero-wrong by construction: 0 wrong at all 36 settings here (§3) | A false-pair rate for such a key must come from independent evidence. Link order, with a truth rate, a null and the `near` test, is the one used here; the questions 4, 7 and 8 notes should not quote a holdout zero for a body key without it |
| 7b (positional) | The offset key catches the positional walk misaligned across a 49-function gap (13 contradictions from 7 key pairs; by size the key's partner is closer in 5, tied in 1) and one swapped pair in the engine leads (`GetDirVec__6CAiMap`, K2) (§5) | Equal counts in a large gap are not an alignment. A future looser positional level should require the multiset key not to disagree; `gap-only`/`any` should stay unused (research/45 §9 already says no) |
| research/45 §6's 126 leads | 19 confirmed by a unique K1 pairing, 0 contradicted by K1. For 86, the positional partner is the single most similar body image-wide by K1 Jaccard (53 strictly), and 7 of the largest 12 pass, the 5 that fail being the 5 under size ratio 0.50 (§5). `ToQuat__7CMatrixCFP5CQuat` 0x00308210 is confirmed exactly and is in R7 | The hand-review queue for the leads should be sorted by Jaccard rank: rank-1 leads first, the five under ratio 0.50 (`__ct__9CGameMenu`, `CreateRemoteSeal`, `MakeNoise`, two `ai::AddNoise`) last. `ToQuat` needs no review beyond R7 |
| Q5 (voice chat) / question 11 | A speech recogniser's user-word trainer lives in our ZSealEtc at 0x004df288–0x004e5948 (a 49-function gap with equal counts on both sides). The demo's names for it include `cbGenderDisable`, `TrainSmoothCounts`, `TrainFree`, `InitUserWordTraining`, `userwordStartUserWordTraining` and `ProcessDelayBlock`; 7 of them place by key where position is misaligned (§5) | A lead for the headset's voice-command path, separate from the SASE codec; not investigated here |
| question 4 (BinDiff) | Offset multisets and flow-graph similarity both survive edits. This note gives an agree/new list (R7, 193 pairs) to diff BinDiff against | Report BinDiff's agreement with R7 as a cross-check of both |
| the Ghidra table | 8,035 `$zero`-based "loads" in 112 of our rows, 1,265 of them in one 39,532-byte row at 0x003d6750 (§1) | They look like data inside function rows. Untraced here (stop rule); worth a look by whoever audits the csv's row extents |
