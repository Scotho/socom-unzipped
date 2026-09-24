# 53. Strings as first-class evidence: a shared-string correlator between the SOCOM 1 demo and r0001

Date: 2026-09-24. Sprint 12 research wave, question 8 of the cloud handoff §4
(`docs/superpowers/plans/2026-09-24-sprint-12-cloud-handoff.md`). Read-only: two ELFs, one Ghidra table,
the toml's stub list. No game was run, no Ghidra process started, and `recomp/socom2_ghidra.csv` is
**unchanged**. The note reports names, addresses, counts and pass labels only: it quotes **no string
literal**, and the script never prints a string's bytes.

**The one-line answer: strings are the strongest lever since Task 7.** A function's *set of shared
strings*, when exactly one demo function and exactly one of our unplaced rows carry it, pairs **259**
functions beyond the 987, all ≥ 64 B with a size ratio ≥ 0.50. Checked by two signals that never look at
a string, **214** of them clear a rule that also rejects every pair a second signal speaks against. Of
those 214, 129 are engine routines and 163 lie in FTSCore. Research/45's hold-out gives **zero wrong** apart
from one pair, and on that pair the evidence says **Task 7 is the one that is wrong**. Task 7's proposal
`NetGetBuildTimeStamp` at **0x006473f0** is very probably `MediusGetBuildTimeStamp`, and it should be held
back from the rename commit.

Every number below names the command that produces it. There is one new command:

```
# S -- the whole note: census, keys, holdout, second signals, rules, classes, positional comparison
python tools_py/research/symbols/string_correlator.py
```

About ten seconds; it writes nothing. It works out Task 7's 987 pairs again in-process with the same call
research/44 command A makes (`ghidra_symbol_match.match(..., prefix=True)`). It has to, because
`game/demo_symbol_matches.json` does not carry a pair's demo address. Its first two lines check the
result against that file (`987 pairs, 828 PROVED`; `... says matched 987`). Its sections are labelled
S1–S6 and are quoted verbatim below. Numbers taken from research/44 and research/45 name those notes'
commands.

## 0. The method, and what it reuses

* **A string** is a NUL-terminated run of ≥ 4 printable bytes (`address_matcher.Image.cstring`'s
  definition: 32–126, tab, LF, CR).
* **A string reference** is `address_matcher.Side.anchors()`'s mechanism, reused rather than written again:
  `formed_addresses` finds every `lui` + `addiu`/`addi`/`ori` (or `lui` + a load/store displacement) that
  forms an address, and `Image.cstring` reads the string there. The script keeps the references in order
  with their repeats (`refs_of`). It then checks, for every function on both sides, that the distinct
  sorted set is exactly what `Side.anchors()` returns. S1 prints
  `refs_of() agrees with Side.anchors() on every function: yes (0 disagree)`.
* **A shared string** (the key's alphabet) is a string that code references in **both** images, byte for
  byte. A string only one side references can never make two keys equal, so it is dropped from both.
* **The keys** (S2/S3): `set` is the set of shared strings a body references. `multiset` adds how many
  times each is referenced, ignoring order. `sequence` is the references in instruction order.
  `unique-string` pairs two functions when one shared string is referenced by exactly one function on each
  side, and refuses a function whose unique strings point at two partners. `set+callees` pairs on the set
  together with the set of *placed* callees: demo `jal` targets carried through Task 7's pairs, against
  our `jal` targets that are Task 7 rows. That is Q7's kind of callee.
* **Unique both ways**: exactly one demo function and exactly one of our rows carry the key. This is
  measured at two **scopes**. `image-wide` counts over every function with bytes (9,703 demo, 14,828 ours,
  which is our 14,879 rows less the 51 with no bytes; research/44 §1). `unplaced` counts only over the
  functions Task 7 left unplaced.
* **Size floors**: research/44's hurdle 2 (both bodies ≥ 64 B) and research/45's size ratio ≥ 0.50.

## 1. The string census

Command S, section S1, verbatim:

```
NUL-terminated printable strings >= 4 B in the PT_LOADs: demo 7715 occurrences / 5092 distinct; ours 8771 / 6250; shared byte-for-byte (distinct) 3096
  of which >= 128 B (Image.cstring's reach is 127): demo 0 distinct, ours 0 distinct, shared 0
refs_of() agrees with Side.anchors() on every function: yes (0 disagree)
strings the code forms the address of (distinct): demo 3212, ours 4121; referenced on BOTH sides (the key alphabet) 2132; of those also in the census-shared set 2128
functions referencing >= 1 string: demo 1399 of 9703, ours 1600 of 14828; >= 1 SHARED string: demo 916, ours 1126
distinct strings per function, demo: 0:8304 1:730 2:297 3:84 4-7:170 8-15:65 16-31:34 32+:19
distinct strings per function, ours: 0:13228 1:643 2:430 3:149 4-7:217 8-15:86 16-31:50 32+:25
distinct SHARED strings per function, demo: 0:8787 1:409 2:237 3:78 4-7:106 8-15:55 16-31:21 32+:10
distinct SHARED strings per function, ours: 0:13702 1:547 2:289 3:82 4-7:117 8-15:59 16-31:22 32+:10
shared strings referenced by exactly one function on each side: 1537 of 2132
of the 987 Task 7 pairs: both sides reference a string 110; shared-string sets equal and non-empty 104
```

How to read it:

* **Census.** Demo 5,092 distinct strings, ours 6,250, and 3,096 shared byte for byte. The census covers
  the PT_LOADs only, so the demo's 5 MB `.debug` (not loaded) is not in it. No string anywhere is 128 B or
  longer, so `Image.cstring`'s 127-byte reach loses nothing.
* **Referenced.** The code forms the address of 3,212 distinct strings in the demo and 4,121 in ours, and
  **2,132** are referenced on both sides. Only 4 of those 2,132 are outside the census-shared set: a
  reference that lands inside a longer run reads a suffix.
* **Who references strings.** 1,399 of the demo's 9,703 functions (14.4 %) and 1,600 of our 14,828
  (10.8 %) reference at least one string; 916 and 1,126 reference at least one *shared* one. Strings are
  a minority signal: 8,787 demo functions have an empty key. **This is research/45 §4's "anchors()
  rescues zero of the 21", seen from the other side.** The small thunks and constructors reach no
  strings; the bodies that do are larger, and they are mostly *not* among the 987.
* **Discrimination.** 1,537 of the 2,132 shared strings (72 %) are referenced by exactly one function on
  each side. A string, once referenced, is nearly always a private one.
* **Why the relinked-body tie-break almost never fired.** Only 110 of Task 7's 987 pairs reference a
  string on both sides, and 104 carry equal non-empty sets. Task 7 matched the string-free code, and the
  string-bearing code is what it left behind.

## 2. The set key, unique both ways

Command S, section S2/S3. Columns: pairs | pairs touching a Task 7 pair: agree / contradict | beyond the
987 | of those ≥ 64 B on both sides | and ratio ≥ 0.50 | of those, our row still `FUN_`:

```
  set           image-wide   372 |   85 /   1 |  286 |  281 |  257 |  257
  set           unplaced     289 |    0 /   0 |  289 |  284 |  259 |  259
```

* **image-wide** (the brief's strict reading, where the set is carried by one function in each whole
  image): **372 pairs**. 86 of them touch a Task 7 pair: 85 agree and 1 contradicts (§4.3). **286 are
  beyond the 987, 281 of those are ≥ 64 B, and 257 also clear ratio ≥ 0.50**; all 257 are still `FUN_`.
* **unplaced** (unique among the functions Task 7 did not place, which is what a pass after Task 7 would
  run on): 289 / 284 / **259**. S2/S3's last line, `set/image-wide within set/unplaced: 257 of 257`, shows
  the strict set is contained in this one. The two extra pairs are keys that a Task 7 function also
  carries.
* For scale: 916 demo and 1,126 of our functions have a non-empty set; 629 and 713 distinct sets (S2/S3).

## 3. The other keys

Same command, same columns:

```
  multiset      image-wide   356 |   84 /   1 |  271 |  266 |  245 |  245
  sequence      image-wide   353 |   84 /   0 |  269 |  264 |  243 |  243
  unique-string image-wide   327 |   68 /   1 |  258 |  254 |  227 |  227  (conflicts refused 39)
  set+callees   image-wide   332 |   85 /   2 |  245 |  240 |  221 |  221
  multiset      unplaced     274 |    0 /   0 |  274 |  269 |  247 |  247
  sequence      unplaced     272 |    0 /   0 |  272 |  267 |  245 |  245
  unique-string unplaced     261 |    0 /   0 |  261 |  257 |  230 |  230  (conflicts refused 36)
  set+callees   unplaced     247 |    0 /   0 |  247 |  242 |  222 |  222
  union over every kind and scope, beyond the 987, >=64+ratio: 330 pairs
  of which a demo function paired two ways 0, our row paired two ways 0
```

| key (scope `unplaced`) | ≥ 64 B + ratio, beyond the 987 | holdout ≥ 64 + ratio, blocks of 8 / of 1 (re-derived / wrong) | link order outside, of the pairs order can judge (S4b) |
|---|---|---|---|
| `set` | **259** | 44 / 1 · 46 / 1 | 10 of 204 |
| `multiset` | 247 | 44 / 1 · 46 / 1 | not printed |
| `sequence` | 245 | 43 / 0 · 45 / 0 | 11 of 198 |
| `unique-string` | 230 | 43 / 1 · 46 / 1 | 10 of 188 |
| `set+callees` | 222 | 45 / 2 · 48 / 2 | 8 of 177 |

The holdout columns come from S4, the last column from S4b.

* **The multiset and the sequence are not weaker than the set; they are stricter.** A repeated or
  reordered reference only splits keys. They cost 12 and 14 pairs, and they buy one thing: the sequence
  happens to separate the disputed pair in §4.3, which is why its holdout column reads 0.
* **The unique-string key is the weakest in the sense the brief means** (one private string is enough),
  but it yields *fewer* pairs. It refuses 36 functions whose private strings point at two partners, and it
  cannot pair a function whose strings are all shared with other functions.
* **Adding the placed callees adds nothing.** It is the set key cut by 37 pairs. It still makes the
  disputed pairing (both halves of it: 2 wrong in the holdout instead of 1), and the 8 link-order
  outsiders it keeps are the same kind as the set key's. Q7's callee evidence is better used as a check
  than as part of the key; see the rules in §4.4.
* **The kinds agree with one another.** Across every kind and scope, 330 distinct pairs clear
  ≥ 64 B + ratio, and no demo function and no row of ours is paired two different ways.

## 4. The false-pair rate

### 4.1 Research/45 §3's holdout, reused

The folds are exactly `symbol_levers.holdout`'s. The 987 pairs are sorted by our address. Only the **828
PROVED** pairs may be held out; the 159 prologue pairs always stay as anchors. Runs of 8 (or 1)
consecutive eligible pairs go to fold `(j // block) % 3`. The kept pairs feed the callee map and, at scope
`unplaced`, leave the pool. A pair the key makes is judged when either side is held out, and it is wrong
when it does not reproduce Task 7's answer. Command S, section S4. The cells are re-derived / wrong for
any size | ≥ 64 B on both sides | ≥ 64 B and ratio ≥ 0.50:

```
 blocks of 8:
  set           image-wide   72 /  1 |   43 /  1 |   43 /  1
  multiset      image-wide   72 /  1 |   43 /  1 |   43 /  1
  sequence      image-wide   71 /  0 |   42 /  0 |   42 /  0
  unique-string image-wide   56 /  1 |   42 /  1 |   42 /  1
  set+callees   image-wide   73 /  2 |   44 /  2 |   44 /  2
  set           unplaced     73 /  1 |   44 /  1 |   44 /  1
  multiset      unplaced     73 /  1 |   44 /  1 |   44 /  1
  sequence      unplaced     72 /  0 |   43 /  0 |   43 /  0
  unique-string unplaced     57 /  1 |   43 /  1 |   43 /  1
  set+callees   unplaced     74 /  2 |   45 /  2 |   45 /  2
 blocks of 1:
  set           image-wide   72 /  1 |   43 /  1 |   43 /  1
  multiset      image-wide   72 /  1 |   43 /  1 |   43 /  1
  sequence      image-wide   71 /  0 |   42 /  0 |   42 /  0
  unique-string image-wide   56 /  1 |   42 /  1 |   42 /  1
  set+callees   image-wide   74 /  2 |   45 /  2 |   45 /  2
  set           unplaced     75 /  1 |   46 /  1 |   46 /  1
  multiset      unplaced     75 /  1 |   46 /  1 |   46 /  1
  sequence      unplaced     74 /  0 |   45 /  0 |   45 /  0
  unique-string unplaced     60 /  1 |   46 /  1 |   46 /  1
  set+callees   unplaced     77 /  2 |   48 /  2 |   48 /  2
```

**Every "wrong" in this table is the same pair, and it is disputed (§4.3).** At scope `image-wide`, the
string-only keys do not depend on the anchors, so the folds only split one fixed set of pairs; that is why
blocks of 8 and blocks of 1 print the same rows there.

**Three limits, stated so the table is not over-read:**

* **The holdout is thin.** Only 104 of the 987 carry equal non-empty sets (S1), so at most about 46 held-out
  pairs can be re-derived at the size floors. Zero wrong out of 44 bounds the true rate below about 7 % at
  95 % (the rule of three, 3/44); on its own it proves little more.
* **The bias runs the other way from research/45's.** A held-out pair is a routine that survived nearly
  intact. A string key does not care whether a body was edited, so that bias does not favour it. Its own
  risk is **sibling routines that share strings**, and the disputed pair is exactly that kind.
* So the error rate is measured a second time, directly on the 259 real candidates, with two signals that
  never look at a string (§4.2).

### 4.2 Two signals that never look at a string, measured on the real candidates

Command S, section S4b. **Link order** is research/45 §1's: in o's PT_LOAD, take the nearest Task 7
anchors below and above o, and ask whether d lies between their demo addresses. **Placed callees** is
Q7's kind.

```
baseline, the 987 Task 7 pairs leave-one-out: link order {'anchors-out-of-order': 78, 'between': 879, 'edge': 6, 'outside': 24}
set/unplaced: 259 pairs; link order {'anchors-out-of-order': 54, 'between': 194, 'edge': 1, 'outside': 10}; placed callees {'disjoint': 5, 'none': 101, 'one side': 25, 'overlap': 128}
  the same 259 demo and our functions paired at random (20 shuffles, mean): {'anchors-out-of-order': 54.0, 'between': 11.3, 'edge': 1.0, 'outside': 192.7}
recomp/socom2.toml's name@addr (656 entries) on the set/unplaced pairs: 6 named there, 6 the same name
  (the same check on the 987: 361 named there, 360 the same name)
```

* **Link order.** Of the 204 string pairs that order can judge, 194 fall between their anchors and 10 do
  not (4.9 % outside). Task 7's own pairs, each tested with itself left out, are 24 outside of 903
  (2.7 %). The same 259 functions paired at random are 192.7 outside of 204 (94.5 %). Solving
  0.049 = (1 − w)·0.027 + w·0.945 gives **w ≈ 2.4 %**, about **5 wrong pairs among the 204**. That is an
  estimate from S4b's counts, not a measurement of any one pair.
* **Callees.** Where both sides have placed callees (133 pairs), 128 overlap and 5 are disjoint; 101 have
  none on either side and 25 on one side only.
* **The toml's hand names**, an independent truth set: 6 of the 259 land on a `name@addr` entry of
  `recomp/socom2.toml`, and **all 6 carry the same name**. That is small, but it is the project's own
  names, and nothing in this method saw them.

### 4.3 The one disagreement with Task 7

Command S, section S4b, verbatim:

```
pairs where a string key (any kind, image-wide) contradicts Task 7: 2
  string key: demo MediusGetBuildTimeStamp 0x003b29dc -> our 0x006473f0 (292/292 B); Task 7: our row held by NetGetBuildTimeStamp (exact)
  string key: demo NetGetBuildTimeStamp 0x00419580 -> our 0x00620518 (292/300 B); Task 7: -> our 0x006473f0 by exact
    demo NetGetBuildTimeStamp     0x00419580: demo callers 0; nearest anchor below it in the demo: NetIpBinaryToString
    demo MediusGetBuildTimeStamp  0x003b29dc: demo callers 1; nearest anchor below it in the demo: MediusGetClientAddrList
    our  0x006473f0 (292 B): our callers 1; nearest anchor below it in ours: 0x00646bb0 = MediusGetClientAddrList
    our  0x00620518 (300 B): our callers 0; nearest anchor below it in ours: 0x00616e60 = NetFreeAllObjects
    Task 7 says 0x006473f0 = NetGetBuildTimeStamp; the string keys say 0x00620518 = NetGetBuildTimeStamp and 0x006473f0 = MediusGetBuildTimeStamp
```

These are two sibling build-stamp routines from two network libraries, both 292 B in the demo. Task 7's
`exact` fingerprint pairs the demo's Net routine with our 0x006473f0. The fingerprint zeroes every
address-forming immediate, so it cannot see *which* strings a body names; it saw one unique instruction
shape on each side. Everything that is not that shape points the other way:

* **Strings.** 0x006473f0 references the same shared strings as the demo's Medius routine, and 0x00620518
  those of the demo's Net routine. The two differ by a format string with a text prefix and one without.
* **Neighbourhood.** 0x006473f0 sits directly after our `MediusGetClientAddrList` anchor, as the demo's
  Medius routine sits after the demo's. 0x00620518 sits in the Net library's run, after `NetFreeAllObjects`.
* **Callers.** 0x006473f0 has one caller in ours and the demo's Medius routine has one; the Net routine
  and 0x00620518 have none on either side.

**Reading:** the SOCOM II Medius routine was very probably rebuilt into the shape SOCOM 1's Net routine
had, and Task 7's `exact` pair is wrong. It is proposal **row 478** of `game/demo_symbol_renames.csv`
(`0x006473f0, FUN_006473f0, NetGetBuildTimeStamp, …, exact, 292`, read with `grep` from research/44
command A's output). Command S cannot settle this without reading the two bodies: that takes a human's
ten minutes, or BinDiff (Q4). Until then the holdout scores both readings, as "wrong" and as
"wrong but the disputed".

### 4.4 The rules, and the one that reaches zero

Command S, section S4b. The key is at scope `unplaced`, and in the holdout the second signals are
computed from the **kept** anchors only. The cells are the real-run pairs beyond the 987 | the holdout
with blocks of 8: re-derived / wrong / wrong other than the disputed pair | the same for blocks of 1:

```
  set           R0 key, >=64 B, ratio >= 0.50           259 |  44 / 1 / 0 |  46 / 1 / 0
  set           R1 R0 + placed callees not disjoint     254 |  44 / 1 / 0 |  46 / 1 / 0
  set           R2 R1 + link order not outside          245 |  41 / 1 / 0 |  46 / 1 / 0
  set           R3 R2 + a positive second signal        214 |  39 / 1 / 0 |  44 / 0 / 0
  sequence      R0 key, >=64 B, ratio >= 0.50           245 |  43 / 0 / 0 |  45 / 0 / 0
  sequence      R3 R2 + a positive second signal        205 |  38 / 0 / 0 |  44 / 0 / 0
  unique-string R3 R2 + a positive second signal        186 |  39 / 1 / 0 |  44 / 0 / 0
  set+callees   R3 R2 + a positive second signal        186 |  42 / 2 / 0 |  45 / 0 / 0
```

This is an excerpt; command S prints all four rules for every key. R3's "positive second signal" is link
order `between` **or** placed callees that `overlap`.

* **With Task 7 as truth, only `sequence` reaches zero wrong at every rule level, with a yield of 245.**
  It gets there by accident: the one pair it separates is the disputed one, and an instruction-order key is
  what an edit disturbs first.
* **With the disputed pair set aside, every key and every rule reaches zero** in both holdouts.
* **R3 on the set key: 214 pairs; 0 wrong in blocks of 1 (44 re-derived), and 1 wrong in blocks of 8,
  which is the disputed pair.** By construction R3 takes no pair that a non-string signal speaks against,
  and every pair it takes has one non-string signal speaking for it. It removes all 10 link-order
  outsiders and all 5 callee-disjoint pairs from R0. By §4.2's arithmetic, a wrong pair lands `between`
  about 5.5 % of the time (11.3 / 204), so about 0.3 of R0's estimated 5 wrong pairs survive the order
  test. Order cannot judge the pairs whose own anchors are out of order; R3 admits one of those only on
  callee overlap, and what they hold is not measured. So R3's expected residual is **of the order of one
  wrong pair in 214**, an estimate and not a count.

## 5. What the string-named pairs are

Command S, section S5. "Engine" is `ghidra_symbol_match.is_engine` (research/44 §4). The class is the class
part of a copy of `readable()` from `tools_py/research/symbols/readable_names.py`; `(free)` is a name with no
class marker.

```
set/unplaced R0: 259 pairs, is_engine 160, not 99; readable classes 116; largest [('(free)', 71), ('CZSealBody', 14), ('CMission', 8), ('zdb_CNode', 6), ('CZOnlineLobby', 6), ('CZAnimMain', 6), ('CZMarkList', 4), ('zdb_CWorld', 4), ('CConsole', 3), ('CSnd', 3), ('Particle', 3), ('CZBombState', 3)]
set/unplaced R3: 214 pairs, is_engine 129, not 85; readable classes 99; largest [('(free)', 58), ('CZSealBody', 14), ('CMission', 8), ('zdb_CNode', 6), ('CZOnlineLobby', 5), ('CZAnimMain', 5), ('zdb_CWorld', 4), ('CConsole', 3), ('CSnd', 3), ('Particle', 3), ('CZBombState', 3), ('CSaveManager', 3)]
R3 pairs per our PT_LOAD: {'0x100000-0x1d5000': 9, '0x1e7000-0x408480': 163, '0x4c5380-0x66a000': 42}
R3 demo names also on a Task 7 pair: 0; names on two R3 pairs: 0; identifiers colliding after c_identifier with the 987 or within R3: 0
```

The mix is the reverse of Task 7's. Nearly half of Task 7's matches are the boot loader's SDK and C
runtime (474 of 987; research/44 command B), while **only 9 of the 214 are**. **163 are in FTSCore and
42 in ZSealEtc.** The FTS application layer (menus, HUD, UI command handlers, the lobby) is where the
string-bearing code lives, and it is exactly the code a year of edits changed too much for a fingerprint.
`is_engine`'s "not" count is an upper bound on the SDK: it counts every free function that does not start
with `z` or `hud`, so FTS routines such as `ftsFixupAiMap` and the `UI*` command handlers fall on the SDK
side.

The twelve largest R3 bodies (command S, S5; the address is **ours**):

| our address | demo / our size | readable name | is_engine | link order | callees |
|---|---|---|---|---|---|
| 0x0055ac20 | 6428 / 5904 | `CAiSGrenade_Tick` | engine | anchors out of order | overlap |
| 0x0019c148 | 5400 / 5744 | `_vfprintf_r` | not | anchors out of order | overlap |
| 0x0059ba80 | 4948 / 5260 | `CharacterDynamics_Load` | engine | between | overlap |
| 0x00191970 | 4556 / 4708 | `_dtoa_r` | not | between | overlap |
| 0x0021ded0 | 4184 / 4680 | `CZActionBitmap_Init` | engine | between | overlap |
| 0x001fa360 | 4000 / 3992 | `CHUD_Init` | engine | between | overlap |
| 0x00380620 | 3828 / 3212 | `CButtonSpec_ctor` | engine | between | one side |
| 0x002a8140 | 3680 / 2596 | `ftsFixupAiMap__FP6CAiMap` | not | between | overlap |
| 0x002178c0 | 3508 / 5256 | `BitmapReticule_Init` | engine | between | overlap |
| 0x0019b360 | 3020 / 3184 | `_vfiprintf_r` | not | anchors out of order | overlap |
| 0x00367950 | 2980 / 3048 | `CGameMenu_LoadFromDesign` | engine | between | overlap |
| 0x0053ce00 | 2876 / 2028 | `CCharacterType_Parse` | engine | anchors out of order | overlap |

Compare research/44 §4's top 50, where the big engine routines were nearly all `prefix` (0.60, never
proposed). Here they are **whole routines of 3–6 KB with a matching set of private strings and matching
callees**. `CHUD_Init` (4000 / 3992 B) and `CGameMenu_LoadFromDesign` (2980 / 3048 B) are the kind of name
the rename pass has so far been unable to reach.

## 6. Research/45's 501 "no body evidence" positional candidates

Command S, section S6:

```
gaps 156, candidates 528, no body evidence 501 (research/45 sec 5: 156 / 528 / 501)
shared-string sets at the positional pairing: equal 13, differ 2, one side only 17, neither 469
  equal and >=64 B and ratio >= 0.50: 13
  of those: paired the same way by the set key (unplaced) 9, and by R3 9; equal but the set is not unique (position alone picks the partner) 4
  set           unplaced   confirms   9, contradicts   6
     positional 0x0027a2e0 <- UIAdvanceMPMission__FP13C2DAnimCmdHdrPf (228/36 B); string key (not in R3): demo side -> our 0x00279490 (308 B, link order outside)
     positional 0x0027a3c0 <- UISendClanMessage__FP13C2DAnimCmdHdrPf (228/36 B); string key (not in R3): demo side -> our 0x002797f0 (232 B, link order outside)
     positional 0x0027a740 <- UIInvitePlayerToClanWithArg__FP13C2DAnimCmdHdrPf (132/232 B); string key (in R3): our side <- UIInvitePlayerToClan__FP13C2DAnimCmdHdrPf (228 B, link order between)
     positional 0x0027a830 <- UIInvitePlayerToClan__FP13C2DAnimCmdHdrPf (228/12 B); string key (in R3): demo side -> our 0x0027a740 (232 B, link order between)
     positional 0x0063d460 <- rt_time_get_time_string (20/104 B); string key (in R3): our side <- rt_time_get_time_string_ptr (76 B, link order between)
     positional 0x0063d4c8 <- rt_time_get_time_string_ptr (76/20 B); string key (in R3): demo side -> our 0x0063d460 (104 B, link order between)
  unique-string unplaced   confirms  10, contradicts   2
  set+callees   unplaced   confirms   9, contradicts   5
```

* **The two levers reach different populations.** 469 of the 501 carry no shared string on either side.
  The string pass finds its 259 mostly *outside* research/45's equal-count gaps: it needs no gap and no
  count.
* **Confirms 9 (set key) to 10 (`unique-string`, `multiset`, `sequence`). Contradicts 6 (set key) or 2
  (`unique-string`).** In all six contradictions **the positional pairing is the less size-consistent
  one**: 228 / 36, 228 / 36, 132 / 232, 228 / 12, 20 / 104 and 76 / 20 B (ratios 0.16, 0.16, 0.57, 0.05,
  0.19, 0.26). The string key's alternatives are 228 / 308, 228 / 232, 228 / 232 and 76 / 104 B (ratios
  0.74, 0.98, 0.98, 0.73). Four of the six are two sibling pairs
  that position reads one step out of line, the shape research/45 §2 warns of when a split and a merge
  cancel inside a gap. R3 takes the string reading for those four. It refuses the other two, whose string
  partner lies outside the link order, so those two stay open.
* **Positional plus strings as a rule of its own adds 4 at most.** Of the 13 candidates whose sets are
  equal at the positional pairing (all 13 ≥ 64 B, ratio ≥ 0.50), the string pass already makes 9. The
  other 4 have a set that other functions also carry, so position alone picks the partner there. That is
  research/45's `gap-only` situation, which its §3 caught being wrong once in eleven. Research/45's
  positional holdout, re-run with the string sets as a bucket, never catches "strings equal" wrong: 2 / 0
  with blocks of 8 and 13 / 0 with blocks of 1 among the untiered, against 55 / 2 and 142 / 4 for
  "no strings" (S6, last block). The sample is too small to justify a rule for 4 names.

## 7. What cannot be answered from what is on disk

* **Which of the disputed build-stamp readings is true** (§4.3). The evidence is printed, and settling it
  takes a read of the two bodies or BinDiff (Q4). No tool on disk decides it.
* **Strings reached other than through a `lui` pair**, such as a `$gp`-relative small-data address or a
  pointer stored in a data table and loaded at run time, are invisible to `formed_addresses`, and how many
  there are was not measured. Keys are therefore under-populated, never wrong: a missed reference can
  only split a pair's keys or make a key look unique when it is not. The second case is the risk, and
  §4.2's link-order check is what bounds it on the real data.
* **The toml check is small** (6 pairs). It says the method agrees with the project's hand names where
  they overlap. It is not a rate.
* **Whether the 214 are right one by one.** §4's numbers are rates. The note ships no per-pair file; the
  pass that proposes them writes that file.

## Recommendation

**A pass named `string-set`**, run after Task 7 (anchors = the 987) and independent of 7b. It writes its
own proposals file in the manner of 7b and never touches the csv directly.

* **Rule (R3):** among the functions Task 7 left unplaced, the set of shared strings a body references is
  non-empty and carried by exactly one demo function and exactly one of our rows. Both bodies are ≥ 64 B,
  with size ratio ≥ 0.50. The placed callees are not disjoint. Link order against the flanking Task 7
  anchors is not `outside`. At least one of link order `between` or callee `overlap` holds. Then Task 7's
  identifier hurdles apply: not a colliding name, our row still `FUN_`, a unique legal identifier. On
  this data none of those fires (S5: 0 / 0 / 0).
* **Score: 0.80**, the same as positional tier B. It stands on one key plus one independent confirming
  signal, below `relinked-body` (0.85) and above `vtable-slot` (0.75).
* **Measured:** holdout 44 re-derived and 0 wrong with blocks of 1; 39 re-derived with blocks of 8, and
  the one "wrong" is the disputed pair, where the evidence favours this pass over Task 7. The estimated
  residual is of the order of one wrong pair in 214 (§4.4).
* **Expected yield: 214 new names**, 129 of them engine routines by `is_engine`, 163 in FTSCore, 42 in
  ZSealEtc and 9 in the boot loader (S5). This compares with Task 7's 479 proposals and 7b's 6.
* **The loose level:** R0 gives 259 and would add 45 more pairs, each with a non-string signal against it
  or none for it. Leave them in a separate loose file, as 7b does.
* **And one correction to carry into the rename commit:** hold Task 7's proposal row 478
  (`NetGetBuildTimeStamp` → 0x006473f0) out, or review it by hand.

## What this means for a task

| task | finding | what it changes |
|---|---|---|
| Goal 1, the rename pass (R257, Task 7's 479) | Task 7's `exact` pair `NetGetBuildTimeStamp` → 0x006473f0 is contradicted by strings, neighbourhood and callers, which all say `MediusGetBuildTimeStamp` (§4.3) | Hold row 478 out of the reviewed rename commit, or read the body first. It is the first measured case of an `exact` pair being wrong: two sibling routines that the address-blind fingerprint cannot tell apart |
| A new pass, `string-set` (a Task 7d, or a lever of Task 7b's module) | The set key (R3) proposes **214** names at 0.80, 0 wrong in the holdout outside the disputed pair, with an estimated residual of the order of 1 (§4.4) | Add the pass and its proposals file; it is the largest lever after Task 7 itself. It goes in `symbol_levers` beside `positional`, reusing `Side.anchors()`, `anchor_gaps`' regions and the holdout's folds; `tools_py/research/symbols/string_correlator.py` is its measurement |
| Goal 2, provenance | Each R3 row has three separable pieces of evidence: the set size, the link-order verdict and the callee verdict | Give the sidecar's evidence column room for all three, e.g. `strings=3;order=between;callees=overlap` |
| Task 7b, positional (research/45 §6) | The string key contradicts 6 of the 501 positional leads; in all 6 the positional pairing is the less size-consistent one (§6) | Correct research/45 §6's lead list for `UIInvitePlayerToClan*` and `rt_time_get_time_string*`. A positional-plus-strings rule would add only 4, resting on position: not worth a rule |
| Q7, call-graph propagation | Putting the placed-callee set into the string key costs 37 pairs and fixes no error; used as a check it removes 5 pairs (§3, §4.4) | Q7's callee evidence is a confirming signal, not a key. Measure the caller side the same way (Q7's own brief) |
| Goal 3 / 7c, vtable slots | The 214 include 99 readable classes, among them `CZSealBody` 14, `CMission` 8, `CZOnlineLobby` 5 (S5) | More body-matched fixed points for slot alignment. Whether they open any of the classes 7c could not is **unmeasured**: re-run 7c's anchor count after the pass |
| Goal 4, BinDiff | One disputed `exact` pair and 214 new ones, both with a clear test | Add both to BinDiff's agree / disagree list; §4.3 is the case a flow graph with string references settles |
| Q10, the class inventory | The string-bearing code Task 7 could not reach is the FTS application layer (163 of 214 in FTSCore) | The architecture map gains its UI, menu and lobby routines with names, which is where online play's code lives |
