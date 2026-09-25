# 52. Call-graph propagation from anchors: callers and callees of the 987 as evidence for the bodies between

Date: 2026-09-24. Sprint 12 research wave, question 7 of the cloud handoff §4
(`docs/superpowers/plans/2026-09-24-sprint-12-cloud-handoff.md`). Read-only: two ELFs, one Ghidra table,
the toml's stub list. No game was run, no Ghidra process started, and `recomp/socom2_ghidra.csv` is
**unchanged**. The note reports names, addresses, counts and mnemonics only; the script prints no byte of
either image.

**The one-line answer: the caller side adds little on its own and a great deal as fuel.** A function's set
of placed callees, when exactly one unplaced demo function and exactly one unplaced row of ours carry it,
pairs **218** functions beyond the 987 at proposal grade (≥ 64 B, size ratio ≥ 0.50). The caller side
adds **45** in the first round. Iterated to a fixed point it takes the total from **313** (callees only)
to **870**. Research/45's holdout finds **no wrong pair** at the rules below. Its only "errors" are one
Task 7 pair the call graph shows to be wrong: the proposal **`setD3_CHCR` → 0x001a3448** is really
`setD4_CHCR`. But the holdout **cannot see** the failure that does happen in the real run. Research/53's
string key contradicts **4** of the 870. In all 4 the key is only common library callees (`memcpy`,
`sprintf`, `atoi`, `_malloc`) and link order says "outside". Adding "link order not outside" removes all
4 and costs 108. **Recommendation: a `callgraph` pass, 762 pairs in 10 rounds: 238 in round 1 at 0.80,
524 in later rounds at 0.75.** It has 0 wrong in the iterated holdout (159 + 191 re-derived), 0 clashes
with the string key (67 agree), and 0 wrong against the toml (54 same, 1 alias).

Every number below names the command that produces it. There is one new command:

```
# Q7 -- the whole note, sections [1]-[9]
python tools_py/research/symbols/callgraph_propagation.py
```

About ninety seconds on this container; it writes nothing. It works out Task 7's 987 pairs again in-process with the
call research/44 command A makes (`ghidra_symbol_match.match(..., prefix=True)`). It has to, because
`game/demo_symbol_matches.json` does not carry a pair's demo address. Its second line checks the result
against that file (`agree with game/demo_symbol_matches.json: 987 of 987`). Section [8] imports
`tools_py/research/symbols/string_correlator.py` (research/53's script) from the same directory to rebuild
the string-set key. Without that file it prints `NO-DATA` and stops there. The sections are labelled
[1]–[9] and quoted below. Research/45's own figures (528, 501, 6) are its command A's. [6] reproduces all
three.

## 1. The two call graphs, and what they cannot see (Q7 [1])

A call edge here is a `jal` whose target is a function start in the table
(`address_matcher.call_targets`, the one Task 10's `hash+callees` pass reads). "Live" means a row with
bytes: 9,703 demo functions, and 14,828 of our 14,879 rows (51 have no bytes, research/44 §1).

| | demo | ours |
|---|---|---|
| `jal` | 50,434 | 58,099 |
| … to a function start | 50,433 | 56,419 |
| … into a body, not its start | 0 | 2 |
| … outside every table row | 1 | 1,678 |
| `jalr` (through a register: **invisible**) | 4,148 | 7,089 |
| live functions with **zero static callers** | 3,056 of 9,703 (31.5 %) | 5,328 of 14,828 (35.9 %) |
| … among the unplaced | 2,775 of 8,716 (31.8 %) | 5,069 of 13,841 (36.6 %) |
| with zero callees | 3,247 | 6,211 |
| isolated (neither), unplaced | 1,016 (11.7 %) | 2,927 (21.1 %) |

**The limit, stated.** A third of each image has no static caller. Those functions are virtual methods,
callbacks, and entries in constructor and jump tables, all reached by `jalr`. Their K_caller is empty
by construction. A fifth of our unplaced rows are isolated and can never wear a key. Our 1,678 `jal`
targets outside every row are calls into code the Ghidra table does not cover. They are dropped, and
this note does not look at them. 7c's vtables would turn many `jalr` sites into edges, but that is not
measured here.

## 2. The keys, and "unique both ways" (Q7 [2])

For every unplaced live function, with the 987 as anchors:

* **K_callee**: the set of its callees that are placed pairs, written as demo addresses.
* **K_caller**: the same for its callers.
* **K_both** = (K_caller, K_callee).

These are sets, as the brief asks. Task 10's pass 2 counts multiplicity inside a fingerprint group,
which is a different use of the same edges. A key is **unique both ways** when it is non-empty and
exactly one demo function and exactly one of our functions wear it. The census counts **every** live
function, anchors included, so an unplaced function that shares its key with an anchor is refused.
That is research/45 §4's image-wide bar. The looser census over the unplaced only is printed beside it
for contrast.

| key | non-empty, demo | non-empty, ours | unique both ways, image-wide | unplaced-only census |
|---|---|---|---|---|
| K_callee | 2,137 of 8,716 | 2,779 of 13,841 | **251** | 256 |
| K_caller | 455 | 446 | **170** | 183 |
| K_both | 2,473 | 3,110 | **426** | 434 |

K_caller is small because the anchors are low in the graph. The 987 are mostly SDK, runtime and math
leaves, so they are callees of many functions and callers of few. The image-wide bar costs 5, 13 and 8
pairs against the looser census.

## 3. The yield beyond the 987 (Q7 [3])

Rules: `raw` is the key alone. `+body64` adds ≥ 64 B on both sides (note 44 hurdle 2). `+ratio` adds a size
ratio ≥ 0.50 (research/45's tier-B cut). `K>=n` requires at least n anchors in the key; for K_both that is
|K_caller| + |K_callee|. **agree** means the callee key and the caller key are each unique and name the
same pair.

| key | raw | +body64 | +body64+ratio | … K ≥ 2 | … K ≥ 3 |
|---|---|---|---|---|---|
| callee | 251 | 242 | **218** | 154 | 83 |
| caller | 170 | 96 | 86 | **33** | 19 |
| both | 426 | 342 | 313 | 227 | **125** |
| agree | 10 | 8 | 8 | 8 | 7 |

Every pair at `+body64` and above lands on a row that is still `FUN_`. At `raw`, 31 caller pairs and 33
both pairs land on hand-named rows; §6.2 covers those.

**What the caller side adds, first round.** The caller key finds 158 raw pairs the callee key does not.
K_both finds 37 that neither component finds alone. The two single keys name one demo function two ways
twice. At proposal grade, the **union** of the three zero-error rules of §4 is callee
`+body64+ratio` ∪ caller `+body64+ratio+K>=2` ∪ both `+body64+ratio+K>=3`. Any function claimed two
ways is dropped. The union gives **263**: 129 only the callee rule finds, 9 only the caller rule, 16 only
K_both. So the caller side adds **45** pairs to the callee key's 218 in round 1, or +21 %.

## 4. The false-pair rate: research/45 §3's holdout (Q7 [4])

This is research/45 §3's method unchanged. The truth is the **828 PROVED pairs**
(`symbol_levers.proved_anchors`). They are held out in 3 folds, in blocks of 8 consecutive pairs by our
address and then in blocks of 1. The 159 prologue pairs stay as anchors throughout. The keys are rebuilt
from the kept anchors, and every rule runs over everything not kept. One rule here is **stricter** than
45's: a derived pair counts when **either** side is held out. A held-out demo function paired to some
never-placed row of ours is scored wrong, not skipped. "Re-derived / wrong":

| key × rule | blocks of 8 | blocks of 1 |
|---|---|---|
| callee raw | 83 / 0 | 118 / 0 |
| callee +body64+ratio | 74 / 0 | 104 / 0 |
| callee … K ≥ 2 | 53 / 0 | 76 / 0 |
| caller raw | 104 / **1** | 137 / **2** |
| caller +body64+ratio | 73 / **1** | 104 / **2** |
| caller … K ≥ 2 | 45 / 0 | 59 / 0 |
| both raw | 197 / **1** | 262 / **2** |
| both +body64+ratio | 152 / **1** | 205 / **2** |
| both … K ≥ 2 | 121 / **1** | 151 / 0 |
| both … K ≥ 3 | 83 / 0 | 99 / 0 |
| agree +body64+ratio | 11 / 0 | 26 / 0 |
| **union** | **126 / 0** | **157 / 0** |

(`+body64` and `+body64+ratio` re-derive the same pairs in the holdout: a held-out pair is an unedited
body, so its ratio is 1.)

**The measured rate is not zero for the caller key and K_both, and the "wrong" pairs are Task 7's error,
not the call graph's.** [4] lists every wrong pair. There are exactly two, and both come from one Task 7
pair:

```
demo setD4_CHCR @0x15ada8 ['0x1000b400', ...] -> ours 0x001a3448 ['0x1000b400', ...];
     Task 7 pairs our 0x001a3448 with setD3_CHCR (hash+callees)
     Task 7's demo partner setD3_CHCR @0x15aa38 forms ['0x1000b000', ...]
demo setD3_CHCR @0x15aa38 -> ours 0x001a30b8 ['0x1000b000', ...]; Task 7 pairs this demo function with 0x001a3448
```

The bracketed values are the hardware-register addresses each body forms. `0x1000B000` is the base of
EE DMA channel 3 (IPU out) and `0x1000B400` of channel 4 (IPU in). The fingerprint zeroes `lui` halves, so
`setD3_CHCR` and `setD4_CHCR` hash equal, and Task 7's `hash+callees` pass took the wrong sibling for
0x001a3448. The caller key pairs each helper through its own callers to the row whose channel matches. [4] prints
them: `setD4_CHCR` through {`sceIpuInit`}, and `setD3_CHCR` through {`sceIpuRestartDMA`, `sceIpuStopDMA`}. **The toml agrees with the call
graph.** [7]: over the 361 Task 7 pairs whose row the toml names, 360 names agree and one differs,
`0x001a3448 Task 7 setD3_CHCR (hash+callees), toml setD4_CHCR`. That is research/44's addendum's
"one sibling-helper difference", now settled. The pair is a proposal:
`grep setD3_CHCR game/demo_symbol_renames.csv` shows it at 0.95. **With that one truth pair corrected,
every rule in the table is 0 wrong.**

Read without the correction, as the brief asks, **what tightening brings the rate to zero, and what it
costs**:

* caller: requiring |K| ≥ 2 costs 86 → 33 at proposal grade.
* both: requiring |K| ≥ 3 costs 313 → 125 (K ≥ 2 is still 1 wrong at blocks of 8).
* callee: already 0, with no tightening.
* agree (the "agreement with the callee pass" tightening): 0 wrong, but it keeps 8 of 218. Two
  independent unique keys rarely exist together.

## 5. Iteration to a fixed point (Q7 [5])

Each round's pairs join the anchors, the keys are rebuilt, and the rule runs again until it adds nothing.
The holdout is run iterated too: re-derived and wrong are summed over all rounds of each fold.

| rule | rounds | per round | total | iterated holdout, blocks of 8 | blocks of 1 |
|---|---|---|---|---|---|
| callee +body64+ratio | 5 | 218, 68, 22, 4, 1 | **313** | 91 / 0 | 116 / 0 |
| callee … K ≥ 2 | 4 | 154, 34, 8, 1 | 197 | 62 / 0 | 84 / 0 |
| caller … K ≥ 2 | 2 | 33, 1 | 34 | 51 / 0 | 61 / 0 |
| both … K ≥ 3 | 8 | 125, 70, 69, 45, 37, 29, 15, 12 | 402 | 121 / 0 | 135 / 0 |
| agree +body64+ratio | 1 | 8 | 8 | 12 / 0 | 27 / 0 |
| **union** | **9** | 263, 187, 175, 104, 75, 36, 21, 7, 2 | **870** | **183 / 0** | **204 / 0** |

**This is where the caller side pays.** Alone, the callee key stops at 313 after five rounds. The union
reaches 870 after nine. A pair placed through its callers becomes an anchor, and that anchor completes
someone else's callee set. Of the 870, 406 names are engine-shaped (`is_engine`). They land 73 in the
boot loader, 463 in FTSCore and 334 in ZSealEtc ([5]). Among the largest are `_vfprintf_r` (0x0019c148),
`RenderWorld__5CPipeFPQ23zdb6CWorld` (0x00339de0), `Load__17CharacterDynamicsFRC8CRdrFile` (0x0059ba80)
and `Tick_0__10CZSealBodyFf` (0x0057a330), with 3.3–5.4 KB bodies that no hash could reach.

## 6. What the holdout cannot see (Q7 [7], [8])

The holdout's bias (research/45 §3) is concrete here. A held-out pair is an **unedited** body, and its
call set is intact on both sides. The real candidates are the 78 % that SOCOM II edited. An edit that
adds or removes one call breaks the true partner's key, and another routine may then happen to wear the
old set uniquely. Three checks the holdout does not use can see that:

### 6.1 The toml's hand names ([7])

| set | our rows the toml names | same name | differ |
|---|---|---|---|
| Task 7's 987 (baseline) | 361 | 360 | 1 (`setD3_CHCR`, §4) |
| union, round 1 | 29 | 29 | 0 |
| union, fixed point | 57 | 56 | 1: 0x0062b168 `RSAGenerateKeyPair` / toml `socom2_RsaGenerateKeyPair` |

The one difference is the project's own spelling of the same routine, not a disagreement.

### 6.2 Our hand-named rows ([7])

The raw caller key lands on 31 rows we named by hand. All are 16-byte syscall stubs, which the
fingerprint cannot tell apart. They differ only in the syscall-number immediate, which the fingerprint
zeroes, and that is why Task 7 left them.
29 names agree. The 2 that differ (`AddDmacHandler`/`AddDmacHandler2` at 0x001a3840,
`RFU086_WaitEvnetFlag`/`_SetTLBEntry` at 0x001ac210) are **raw-byte identical**, which for a syscall
stub means the same syscall number: aliases, not errors. None is a proposal (all are under 64 B).

### 6.3 Research/53's string-set key ([8]), the one check that finds errors

[8] rebuilds research/53's R0 (the placed-string set unique over the unplaced, ≥ 64 B, ratio ≥ 0.50) and
gets **259** pairs, the figure research/53 reports. The string key never reads a `jal`:

| call-graph set | pairs | also a string pair | **clash** | strings silent |
|---|---|---|---|---|
| callee +body64+ratio | 218 | 24 | 1 | 193 |
| caller +body64+ratio | 86 | 5 | 0 | 81 |
| both +body64+ratio | 313 | 30 | 1 | 282 |
| union, round 1 | 263 | 28 | 1 | 234 |
| union, fixed point | 870 | 76 | **4** | 790 |

The 4 clashes, each with the key that made it and its link-order verdict:

| round | demo function → our row (call graph) | K_callee (K_caller empty in all 4) | strings say | link order |
|---|---|---|---|---|
| 1 | `cbGetMyClans__F…` → 0x002f10b0 | {atoi, memcpy} | it is at 0x002e8bd0 | outside |
| 2 | `Create__Q23zdb5CGrid…` → 0x0033dff0 | {_malloc, sprintf} | it is at 0x002d5c80; `Save__12CSaveManager…` is at 0x0033dff0 | outside |
| 2 | `UpdateLadderRating__13CZOnlineLobbyFi` → 0x002e7d70 | {CUIVarManager::Add, memcpy, memset, sprintf} | `UpdateClanStats__13CZOnlineLobbyFv` is at 0x002e7d70 | outside |
| 3 | `Save__12CSaveManagerFPCciiPc` → 0x0034d190 | {CZAR::Close, CZAR::Open, sprintf} | it is at 0x0033dff0 | outside |

In each case two independent signals, strings and link order, stand against one. **These are
call-graph errors**, and they share one shape: a key made only of ubiquitous callees, on a routine the
year of edits touched. The CGrid/CSaveManager pair is the worst kind: a round-2 error that took a
row, which then pushed the real `CSaveManager::Save` elsewhere in round 3. Iteration compounds.

### 6.4 The link-order bracket ([7])

For each pair, [7] checks whether our address lies between the our-images of the demo function's
nearest placed neighbours in demo order, in the same `PT_LOAD`. On the 828 proved pairs, each against the
other anchors, **727 of 796 (91.3 %)** are inside, where chance is 1.85 %. The union is inside 217 of
242 in round 1 (89.7 %) and 727 of 822 at the fixed point (88.4 %). By round, against the 987:
217/242, **145/177**, 144/165, 92/101, 71/74, 32/34, 18/20, 6/7, 2/2. Round 2 dips to 81.9 %, and to
85.6 % (154/180) against the grown anchors. So the excess over the baseline sits in the early
iterations, where the 4 clashes are. The whole set still reads as correct in bulk: bracketing the 828
proved pairs with the 987 **plus** the union's 870 raises them to **745 of 809 (92.1 %)**. Wrong
anchors would have lowered that.

## 7. The tightened rule: ORDERED (Q7 [9])

The rule is the union, iterated, dropping any pair whose bracket (over that round's anchors) says
`outside`. `unknown` means no same-region neighbour on a side, and it is allowed.

```
union callee|caller K>=2|both K>=3 ordered: rounds 10, per round [238, 149, 141, 85, 67, 46, 24, 6, 4, 2],
  total 762; iterated holdout blocks of 8 159/0 wrong; blocks of 1 191/0 wrong; strings agree 67, clash 0;
  toml names 55: same 54, differ 1 (0x0062b168 RSAGenerateKeyPair / toml socom2_RsaGenerateKeyPair)
  link-order verdicts ...: round 1 between 217, round 1 unknown 21, rounds 2+ between 494, rounds 2+ unknown 30
  round 1    238 pairs; strings agree 27; toml same 28 of 28; engine-shaped 101
  rounds 2+  524 pairs; strings agree 40; toml same 26 of 27; engine-shaped 262
  demo names on two pairs 1 (_sceRpcGetPacket); identifiers colliding within the rule 1;
  identifiers colliding with the 987's 0
```

The order requirement costs **108** (870 → 762) and removes all 4 string clashes. The same filter
applied to the single keys: callee 313 → 273 and both-K ≥ 3 402 → 326, each with 0 wrong and 0 clashes.
Applied to the loose `both +body64+ratio` it gives 979, but that one is **2 wrong** at blocks of 1: the
|K| cut is still load-bearing. All 762 land on `FUN_` rows: 71 in the boot loader, 385 in FTSCore and
306 in ZSealEtc. 363 are engine-shaped. 55 sit on rows the toml names.

**What the disk cannot settle.** No check here is wrong about the ORDERED set, but most of it is
checked by nothing. Strings speak for 67 pairs and the toml for 55; the other ~640 rest on the call
graph, the size ratio and link order alone. By the rule of three, 0 clashes in 67 bounds the rate on
the checked subset at about 4.5 % (95 %). It does not prove zero. BinDiff (question 4) is the missing
second signal for the silent majority.

## 8. Against research/45's positional candidates (Q7 [6], [9])

Research/45 command A's walk is reproduced in [6]: 156 gaps, 528 candidates, **501 with no body
evidence**, 27 tiered, 6 proposals.

| call-graph set | 501 no-evidence: confirm / contradict / silent | 27 tiered | 45's 6 |
|---|---|---|---|
| callee raw | 15 / 3 / 483 | 0 / 0 / 27 | 0 / 0 / 6 |
| caller raw | 28 / 1 / 472 | 6 / 0 / 21 | 1 / 0 / 5 |
| both raw | 47 / 3 / 451 | 7 / 0 / 20 | 1 / 0 / 5 |
| agree raw | 5 / 0 / 496 | 0 / 0 / 27 | 0 / 0 / 6 |
| union, fixed point | 70 / 24 / 407 | 6 / 0 / 21 | 1 / 0 / 5 |
| **ORDERED** | **67 / 22 / 412** | 6 / 0 / 21 | 1 / 0 / 5 |

The call graph **never contradicts a tiered candidate or one of 45's six**. Its contradictions all fall
on the no-evidence 501, the ones position alone would have named. [6] lists every one:

* **gap 1, `sceCdMmode`** (0x0016f750): position says 0x0018ef70 (196/516 B), the call graph says
  0x0018f610 (208 B). **The toml settles it for the call graph**: 0x0018ef70 = `sceCdDiskReady`,
  0x0018f610 = `sceCdMmode`. A gap of one is not proof of anything.
* **gap 49**, the largest gap: 17 of the union's 24 contradictions. The routines are `TrainSelectPhenom`,
  `ExitUserWordTraining`, `SendLabelsToEngine`, `FindBestTranscription`, `DoDurationModeling`,
  `ScoreTranscriptions`, `CheckConsistency`, `DoUserWordTraining`, `SendPartOfLabelsToEngine`,
  `cbDoUserWordTraining`, `SendResultUserWords` and their neighbours. The call graph puts every one of
  them **one row earlier** than position does. This is the split-and-merge that cancels inside a gap,
  the case research/45 §2 built `AlignmentTest` for, now seen in real data. The size ratio favours the
  shift (e.g. `ScoreTranscriptions` 2144 B: the call graph's row is 2384 B, position's is 560 B).
* **gap 11** (`CGameMenu`): `__dt__9CGameMenuFv` and `__ct__9CGameMenuFv` are shifted the same way. So
  research/45 §6's lead `__ct__9CGameMenuFv` at 0x00369eb0 (1156/192 B) is wrong; the call graph says
  0x00369b60 (840 B).
* **gap 8** (`CZAnim`): `ActivateEx__6CZAnimFie` shifted by one (the call graph's row is 388 B,
  position's 92 B). **gap 6**: `CalcNrNodes10`.
* Raw-key-only contradictions, which the size cuts remove from every rule: `TrainInit` and
  `UIChangeCharacterType` fail the ratio, and `NetGetObject` (48 B) fails the 64-byte floor.

Where the call graph names a different row for the demo function, [6]'s count is: at rule level the
size ratio favours the call graph 12 times and position 3 times. The 3 are near ties inside the gap-49
shift (0.95 against 0.87–0.94). Among the raw-key-only ones it favours the call graph once and position
twice, and the size cuts remove all three.

## 9. Recommendation

**A pass named `callgraph`**, in `symbol_levers` beside `positional`, with its own proposals file:

* **Rule.** An unplaced demo function and an unplaced `FUN_` row are paired when one of these three
  keys is non-empty and unique both ways **image-wide**:
  * the placed-callee set, or
  * the placed-caller set with |K| ≥ 2, or
  * the (caller set, callee set) pair with |K| ≥ 3.

  Both bodies are ≥ 64 B with a size ratio ≥ 0.50. A function claimed two ways is dropped. Link order
  over that round's anchors is not `outside`. The pass iterates to a fixed point, each round's pairs
  anchoring the next. Then Task 7's identifier hurdles apply.
* **Score.** 0.80 for round 1, the same bar as positional tier B. The evidence is an image-wide-unique
  key plus link order plus size ratio, directly on the 987. Rounds 2 and later get **0.75**: their
  evidence is inherited from call-graph pairs, and §6.3 shows that is where errors compound. At 0.75
  they sit under hurdle 1 and go to a loose file, unless a second signal lifts them (a string pair, or
  BinDiff when it runs). 40 of the 524 already have a string pair.
* **Evidence column.** `callee 3, caller 1, round 2, order between`.
* **Expected yield.** 238 names at 0.80 and 524 at 0.75, **762** in all. The identifier hurdle refuses
  the 2 `_sceRpcGetPacket` rows (one `static`, two translation units), so **760** reach a file. 363 are
  engine routines. Compared with research/53's string key: 67 of the 762 are also string pairs and the
  other 695 are not. The two passes are complementary, and where they agree the pair has two
  independent reasons.

## What this means for a task

| task | finding | what it changes |
|---|---|---|
| Goal 1, the rename pass (Task 7's 479) | Proposal `setD3_CHCR` → 0x001a3448 (`hash+callees`, 0.95) is wrong. The body forms DMA channel 4's register (0x1000B400) where demo `setD3_CHCR` forms channel 3's. The caller key and the toml both say `setD4_CHCR`. The real `setD3_CHCR` is 0x001a30b8 (§4) | Hold the row out of the reviewed commit, or apply `setD4_CHCR` as the toml has it. This is the second measured Task 7 error after research/53's `NetGetBuildTimeStamp`, and both are sibling routines that the address-blind fingerprint cannot separate |
| Task 7 / `address_matcher` pass 2 | `hash+callees` "last pair sharing this hash" chose the wrong sibling between channel helpers | A cheap guard: refuse a `hash+callees` or `relinked-body` pair whose bodies form different hardware-register addresses (0x1000_0000–0x1200_FFFF are not relocated). Unmeasured beyond this pair |
| A new pass, `callgraph` (a Task 7d, or a lever in `symbol_levers`) | The ORDERED union: 762 pairs in 10 rounds. 0 wrong in the iterated holdout (159 + 191), 0 clashes with strings (67 agree), 0 wrong against the toml (54 same, 1 alias) (§7) | Add the pass and its file: 238 at 0.80 and 524 at 0.75 in a loose file. `tools_py/research/symbols/callgraph_propagation.py` is its measurement. Keep the link-order requirement and the \|K\| cuts: without them 4 real errors pass (§6.3) |
| Research/45 holdout method, generally | The holdout re-derives unedited bodies, so it could not see the one failure the call graph actually has: keys of ubiquitous callees on edited routines (§6) | Every new key needs an independent real-run check (strings, toml, hand names, BinDiff) beside the holdout. A 0-wrong holdout is not enough on its own |
| Task 7b, positional (research/45 §6) | The call graph contradicts 22 of the 501 no-evidence candidates. The toml settles `sceCdMmode` against position. Gaps 49, 11 and 8 are shifted by one row. The shift is a split-and-merge in real data (§8) | Mark gaps 8, 11 and 49 misaligned in research/45 §6's lead list. The `__ct__9CGameMenuFv` lead is 0x00369b60, not 0x00369eb0. 45's six are untouched |
| Research/53, `string-set` | The two keys agree on 67 of the ORDERED pairs and never clash. The call graph failed the string key 4 times and the string key never failed the call graph (§6.3) | Use each as the other's second signal. A pair both keys make can carry a higher score than either alone |
| Goal 2, provenance | A `callgraph` row rests on a key size, a round and a link-order verdict | The sidecar's `Evidence` column needs `callee n, caller n, round r, order v` |
| Goal 3 / 7c, vtable slots | 762 more placed bodies to align slots on. A third of each image has no static caller because it is reached by `jalr` (§1) | Re-run 7c's fixed-point count after this pass. The reverse is unmeasured: vtables turned into call edges could give the `jalr` third a K_caller |
| Goal 4, BinDiff | The ORDERED set's silent ~640, the 4 clashes and the 22 positional contradictions | These are BinDiff's test list. It is the signal that can lift rounds 2+ from 0.75 |
| Goal 6, toml-stub | 55 of the 762 sit on toml-named rows: 54 same name, and `RSAGenerateKeyPair` against the toml's `socom2_RsaGenerateKeyPair` | The toml pass and this one overlap on 55 rows. The one spelling difference is the owner's to rule |
| Q5, voice (Sprint 9) | Gap 49 in ZSealEtc (0x004e0050–0x004e4dc0) holds routines the names call user-word training and transcription scoring. 17 of the union's 24 contradictions of position are in this gap, each one row off | A lead for the voice-command side of the headset, not the SASE codec. Addresses from the ORDERED set, names from the demo |
