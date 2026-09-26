# 49. BinDiff on demo1 → r0001, joined to Task 7's 987 pairs

Date: 2026-09-24. Sprint 12 research wave, question 4 of the cloud handoff's §4
(`docs/superpowers/plans/2026-09-24-sprint-12-cloud-handoff.md`); the spec's Goal 4, §1.4 and owner decision D5
(`docs/superpowers/specs/2026-09-24-sprint-12-the-readable-image-design.md`); R262 (BinDiff rather than Ghidra
Version Tracking). Read-only: `recomp/socom2_ghidra.csv` is unchanged, no game was run, and every Ghidra project,
export and diff is under `game/bindiff/` (git-ignored). This note holds names, addresses, counts and similarity
scores. It holds no game bytes.

**The one-line answer: BinDiff installs and runs here (Ghidra 11.0.3 + the EE extension + BinExport 12 + BinDiff 8,
about 8 minutes of wall time end to end), but raw BinDiff cannot be a proposer. It contradicts 155 of the 828 proved pairs, 41 of them
at similarity 1.00. One rule holds: a flow-graph matcher, both bodies ≥ 64 B, size ratio ≥ 0.50, similarity ≥ 0.95.
Under it BinDiff agrees with 332 proved pairs and contradicts none, and it has no other-name pair against the toml's
hand names or against any of the ten proposal files. At that rule it confirms 21 of the 159 prefix pairs (5 engine,
the largest 236 B) and adds 92 new pairs. It does not confirm a single one of R257's big engine routines
(`CMission::Init`, `CSealCtrl::ThrottlesPreTick`, `CZSealBody::GetNodePos`). Its flow-graph similarity does not
reach edited bodies: the 78.3 % ceiling moves to 77.4 %.**

Every number below names the command that produces it. The commands are as follows (the paths under
`/home/user/tools/` are §1's installs):

```
# A -- the demo's function table, from its own .symtab (the rows Task 7 reads; 9,703 rows + header)
python -c "
from tools_py.elf_symbols import read_elf
fs = sorted(read_elf('game/demo_scus_972_05/SCUS_972.05').functions)
with open('game/bindiff/demo_functions.csv', 'w') as f:
    f.write('Name,Start,End,Size\n')
    for s, e, n in fs: f.write('%s,0x%08X,0x%08X,%d\n' % (n, s, e, e - s))"

# B -- import, impose the table, analyse, save (one per image; the two ran in parallel)
H=/home/user/tools/ghidra_11.0.3_PUBLIC/support/analyzeHeadless
$H game/bindiff/proj demo1 -import game/demo_scus_972_05/SCUS_972.05 -overwrite \
   -processor r5900:LE:32:default -cspec default -scriptPath ghidra_scripts \
   -preScript BinExportBoth.java game/bindiff/demo_functions.csv none keep > game/bindiff/demo1.ghidra.log 2>&1
$H game/bindiff/proj r0001 -import game/disc/socom2_game.elf -overwrite \
   -processor r5900:LE:32:default -cspec default -scriptPath ghidra_scripts \
   -preScript BinExportBoth.java recomp/socom2_ghidra.csv none auto > game/bindiff/r0001.ghidra.log 2>&1

# C -- impose the table again over what analysis added, and write the .BinExport
$H game/bindiff/proj demo1 -process SCUS_972.05 -noanalysis -scriptPath ghidra_scripts \
   -postScript BinExportBoth.java game/bindiff/demo_functions.csv game/bindiff/demo1.BinExport keep \
   > game/bindiff/demo1.ghidra.log.export 2>&1
$H game/bindiff/proj r0001 -process socom2_game.elf -noanalysis -scriptPath ghidra_scripts \
   -postScript BinExportBoth.java recomp/socom2_ghidra.csv game/bindiff/r0001.BinExport auto \
   > game/bindiff/r0001.ghidra.log.export 2>&1

# D -- the diff (demo primary, r0001 secondary; the stock matchers minus name hashing, §1.3)
/home/user/tools/bindiff8/opt/bindiff/bin/bindiff --config /home/user/tools/bindiff8/bindiff_noname.json \
   --output_dir game/bindiff --output_format bin,log game/bindiff/demo1.BinExport game/bindiff/r0001.BinExport

# E -- the join (§2-§7), 7 s
python tools_py/research/symbols/bindiff_join.py game/bindiff/demo1_vs_r0001.BinDiff \
   --prefix-csv game/bindiff/prefix_verdicts.csv --compare game/demo_symbol_renames.csv \
   game/demo_symbol_renames_7b.csv game/demo_symbol_renames_7c.csv game/demo_symbol_renames_callgraph.csv \
   game/demo_symbol_renames_callgraph_loose.csv game/demo_symbol_renames_offsets.csv \
   game/demo_symbol_renames_prefix_offsets.csv game/demo_symbol_renames_strings.csv \
   game/demo_symbol_renames_strings_loose.csv game/demo_symbol_renames_ui.csv > game/bindiff/join.txt

# F -- the control: D with BinDiff's stock config into a scratch directory, then E on that result (§3.4)
/home/user/tools/bindiff8/opt/bindiff/bin/bindiff --config /home/user/tools/bindiff8/etc/opt/bindiff/bindiff.json \
   --output_dir <scratch> game/bindiff/demo1.BinExport game/bindiff/r0001.BinExport
```

Two scripts are new and tracked: `ghidra_scripts/BinExportBoth.java` (B and C) and
`tools_py/research/symbols/bindiff_join.py` (E); the BinExport patch B and C need is
`ghidra_scripts/binexport-r5900-blocks.patch` (§1.2). The join reads `recomp/socom2.toml`, and the toml's 656
`name@addr` entries were identical to HEAD's when this ran (another task has the toml open for other lines).

## 1. The install

### 1.1 What was installed, and from where

| piece | version | fetched from | installed at |
|---|---|---|---|
| Ghidra | **11.0.3** (`ghidra_11.0.3_PUBLIC_20240410.zip`, 412,949,687 B) | the NSA GitHub release download (tag `Ghidra_11.0.3_build`) | `/home/user/tools/ghidra_11.0.3_PUBLIC` (1.1 GB) |
| EE extension | **ghidra-emotionengine-reloaded v2.1.16**, the release built for Ghidra 11.0.3 (asset `ghidra_11.0.3_PUBLIC_20240504_ghidra-emotionengine-reloaded.zip`, 857,650 B) | chaoticgd's GitHub release download; the tag was found from the clone's CI matrix (`git show v2.1.16:.github/workflows/publish.yml`) | `…/Ghidra/Extensions/ghidra-emotionengine-reloaded`; SLEIGH compiled by `support/sleigh -a …/data/languages` |
| BinExport | **12**, release `v12-20240417-ghidra_11.0.3` (`BinExport_Ghidra-Java.zip`, 3,822,887 B), **patched**, §1.2 | google/binexport's GitHub release download; the source is a `--depth 1` clone of the same tag | `…/Ghidra/Extensions/BinExport` |
| BinDiff | **8** (`@568181968, Sep 25 2023`; `bindiff_8_amd64.deb`, 62,663,460 B) | google/bindiff's GitHub release download (tag `v8`) | unpacked with `dpkg-deb -x` into `/home/user/tools/bindiff8` (106 MB). The system is untouched, and the native `bindiff` binary needs nothing else |

**Why 11.0.3 and not the project's 12.1** (`docs/DEVELOPING.md`): BinExport's newest Ghidra release targets 11.0.3
and none targets 12.x. Building it for 12.1 needs Gradle, which is not reachable here. The EE extension's CI builds
one zip per Ghidra version, and v2.1.16 is the last tag whose matrix includes 11.0.3. **Language:
`r5900:LE:32:default`, compiler spec `default`, on both images.** The DEVELOPING recipe uses the same id. The
default MIPS language does not decode the 128-bit MMI ops.

### 1.2 What had to be fixed locally (outside the repository)

1. **Heap.** `support/analyzeHeadless` line 9, `MAXMEM=2G` → `5G`.
2. **A protobuf clash.** BinExport ships `protobuf-java-3.25.1.jar`. Ghidra's own
   `Ghidra/Debug/Framework-AsyncComm/lib/protobuf-java-3.21.8.jar` loads first, and the first export died with
   `IllegalAccessError: … LazyStringArrayList.emptyList()` (`game/bindiff/demo1.ghidra.log` of the first run). The
   3.21.8 jar was moved to `/home/user/tools/dl/displaced/`. Headless does not use the debugger.
3. **Two BinExport defects on this program. Patched in `BinExport2Builder.java`**, and nothing else changed. The
   source is kept at `/home/user/tools/binexport-patch/BinExport2Builder.java`, the original jar at
   `/home/user/tools/dl/BinExport.jar.orig`, and the patched jar's sha256 is `777716c8…90ae1`.
   - `BasicBlockModel.getCodeBlocks()` stops at the first R5900 `sync` instruction (0x0015dd10 in the demo): it
     returned 4,818 blocks where the functions hold 119,015. `buildFlowGraphs` then looked up blocks it had never
     indexed, and the export ended in `NullPointerException at BinExport2Builder.buildFlowGraphs(…:318)`.
   - Some of our functions are entered by fall-through, with no reference to the entry, so the entry sits inside a
     model block that starts in the previous row. That function's flow graph got no entry block (index 0 by default),
     and BinDiff refused the export: `AttachFlowGraph: flow graph already attached 00180008`.
   - The patch builds blocks **per function**: each model block is intersected with the function's body and split
     at its entry. An edge whose target is not a block of the same function is dropped. Both images' export logs
     (C) print the result. Demo: `blocks 119015, flow graphs 9713, … no entry block 0, … clipped 0, edges dropped 0`.
     r0001: `blocks 159294, flow graphs 14143, … no entry block 0, block tails clipped at a function end 61, edges
     dropped (target outside the function) 68`. So on the demo the patch changes nothing but the crash, and on r0001
     it touches 61 block tails and 68 cross-row edges out of 159,294 blocks.

**Reproducing the patch from the tree.** The rewrite is tracked as a unified diff against the tag's
source: `ghidra_scripts/binexport-r5900-blocks.patch` (BinExport is Apache-2.0; the header names the tag, the
Ghidra version, both defects and the build). It applies to a fresh `git clone --depth 1 --branch
v12-20240417-ghidra_11.0.3 https://github.com/google/binexport` with `git apply`, and the result is byte-identical
to the source the installed jar was compiled from (checked with `cmp`). The rebuild, with `G` the Ghidra 11.0.3
install and the release extension unpacked in it:

```
E=$G/Ghidra/Extensions/BinExport/lib; cp $E/BinExport.jar BinExport.jar.orig; mkdir -p classes
javac -nowarn -d classes -cp "$(find $G/Ghidra -name '*.jar' | grep -v '/Debug/\|BinExport.jar' | tr '\n' ':')BinExport.jar.orig" \
    java/src/main/java/com/google/security/binexport/BinExport2Builder.java
cp BinExport.jar.orig BinExport-patched.jar && (cd classes && jar uf ../BinExport-patched.jar com/google/security/binexport/*.class)
cp BinExport-patched.jar $E/BinExport.jar
```

### 1.3 The function boundaries both sides carry, and the diff's configuration

`BinExportBoth.java` removes every function Ghidra made that the table does not have, then disassembles each row
inside its own body and creates it with the body `[Start, End)`, cut at the next row's `Start`. Ghidra functions
cannot overlap. It runs before analysis, so analysis works from the project's entries, and again after analysis,
where it re-imposes the table and exports. Its log line (B and C):

| | rows | bodies cut at the next start | created | no bytes | exported functions (E `[inputs]`) |
|---|---|---|---|---|---|
| demo | 9,703 | 0 | 9,703 | 0 | 9,713: the 9,703 plus 10 `sub_…` call-graph stubs BinExport adds for call targets that are not a row |
| r0001 | 14,879 | **1,097** (the csv's nested and labelled rows, `caseD_` and multi-entry bodies) | 14,877 | 2 | 14,879 in the call graph, **14,143 with a flow graph** |

- **Names.** The demo keeps its `.symtab` names (`keep`). r0001 gets `auto`: no csv name reaches Ghidra, so its rows
  are `FUN_…` except where the EE extension's own analysis names a syscall wrapper (`SetGsCrt`, `RFU003`, …).
  BinDiff's "name hash matching" is removed from the config (`bindiff_noname.json` is the stock
  `/home/user/tools/bindiff8/etc/opt/bindiff/bindiff.json` minus that one entry), so no name drives a match. The
  control F shows that it would otherwise fire on those syscall names.
- **Rows with no flow graph.** 736 of r0001's rows have no flow graph. Their first word does not decode under
  v2.1.16's SLEIGH: 726 are `Unable to resolve constructor` and 10 are `Nested delay slotted instruction`
  (FTSCore 508, ZSealEtc 207, loader 21). BinDiff counts them as its 736 "library" functions (E `[inputs]`). **None
  of them is one of the 987.** This was measured by a one-off read-only diagnostic over the project, which was not
  kept because the brief allows two scripts. The project's own Ghidra 12.1 and a newer extension may decode them.
  That is a cost of 11.0.3, stated rather than assumed away.
- **On a fresh project, C re-creates 281 r0001 rows** only after clearing data that analysis laid over their
  entries (its log: `created 14877 (after clearing analysis data 281)`). A second C prints 0, because the first one
  saved the cleared state.

### 1.4 Runtime and output sizes

| step | wall time (4 CPUs, shared with other agents) | output (`game/bindiff/`) |
|---|---|---|
| B, both images in parallel | demo 307 s, r0001 314 s (`IMPORT EXIT … SECONDS` in the logs) | project `proj/` 166 MB |
| C, both in parallel | demo 95 s, r0001 113 s (`EXPORT EXIT … SECONDS`) | `demo1.BinExport` 17,582,655 B; `r0001.BinExport` 21,450,146 B |
| D | 22.1 s (setup 1.6 s, matching 20.6 s, its own log) | `demo1_vs_r0001.BinDiff` (SQLite) 6,914,048 B; `.results` 9,387,772 B |
| E | 7 s | `prefix_verdicts.csv` (159 rows), `join.txt` |

D is deterministic. A second run on the same two exports gives the same 8,835 pairs, with the same similarity and
matcher for each.

## 2. The join: agree / disagree / new, by pass

D prints `matched: 8835 of 9713/14879 (primary/secondary, 9713/14143 non-library)`, a whole-image similarity of
3.9 % and a confidence of 8.1 %. BinDiff pairs almost every demo function with *something*. Its matchers, by count
(E `[inputs]`): address sequence 3,072, call sequence (sequence) 1,281, edges flowgraph MD index 986, edges
callgraph MD index 930, flowgraph MD index top-down 662, call reference 626, prime signature 512, call sequence
(exact) 373, and the rest under 100 each. Hash matching has 85.

Each of the 987 is checked by demo address (from `ghidra_symbol_match.match`'s `details`; E checks the re-derived
987 identical to `game/demo_symbol_matches.json`) and by our address (E `[§2 join]`):

| Task 7 pass | pairs | agree | disagree | absent | agree similarity (median, min) | disagree similarity (median) |
|---|---|---|---|---|---|---|
| `exact` | 632 | 519 | 113 | 0 | 1.000, 0.868 | 0.420 |
| `hash+callees` | 20 | 17 | 3 | 0 | 1.000, 1.000 | 0.610 |
| `relinked-body` | 176 | 137 | 39 | 0 | 1.000, 1.000 | 1.000 |
| `prefix` | 119 | 34 | 79 | 6 | 0.854, 0.039 | 0.038 |
| `prefix+size` | 40 | 19 | 21 | 0 | 1.000, 0.112 | 0.033 |
| **all** | **987** | **726** | **255** | **6** | | |

- Of the 255 disagreements, 246 are "BinDiff pairs the demo function elsewhere" and 9 are "BinDiff pairs our
  function with another demo function". 361 BinDiff pairs have exactly one side inside the 987. Those are the same
  disagreements seen from BinDiff's side.
- **NEW** (both sides outside the 987): **7,726 pairs, median similarity 0.143** (p25 0.011, p75 0.433). 2,911 come
  from "address sequence" and 1,232 from "call sequence". Most of BinDiff's output is placement by neighbours, not
  evidence about bodies.

## 3. The false-pair rate against the 828 proved pairs

### 3.1 The method

research/45 §3 holds Task 7's proved pairs out of a lever that uses the rest as anchors, and counts what the lever
gets wrong. BinDiff never sees the 987 at all, so **every one of the 828 is held out by construction**. It is one
block, and the count is direct.

### 3.2 Raw BinDiff: no threshold reaches zero

E `[§3 rate]`: **agree 673, contradict 155, absent 0**. By pass: `exact` 519/113, `relinked-body` 137/39,
`hash+callees` 17/3. The raw sweep (every matcher; `t` = similarity):

| sim ≥ | 0.00 | 0.50 | 0.70 | 0.90 | 0.95 | 1.00 |
|---|---|---|---|---|---|---|
| contradictions on the 828 | 155 | 64 | 45 | 44 | 41 | **41** |
| NEW pairs | 7,726 | 1,750 | 1,270 | 1,081 | 1,008 | 946 |

**Similarity alone never reaches zero.** At similarity 1.00 BinDiff still contradicts 41 proved pairs. They are
overwhelmingly 8–20-byte getters placed by "address sequence" (`CSealStats::NumTimesSeen`, the fifteen
`GetType__…Spec` one-liners, the `_langGet…` run shifted by one), where a flow graph of one block is "identical" to a
thousand others. That is the same small-body problem research/44 §6 found for the fingerprint. For tiny bodies,
flow-graph similarity is no evidence.

### 3.3 The rule that reaches zero

**The rule:** a structural matcher (BinDiff's hash matching, edges flowgraph MD index, flowgraph MD index top-down
or bottom-up, prime signature, relaxed MD index; not the address-sequence, call-sequence, call-reference,
call-graph-MD or instruction-count matchers, which place a function by its neighbours or by one scalar), **both
bodies ≥ 64 B** (research/44 hurdle 2), **size ratio ≥ 0.50** (research/45 tier B), and **similarity ≥ t**. E
`THE RULE`:

- 224 distinct BinDiff pairs contradict a proved pair; 16 of them clear the rule at t = 0. **The largest similarity
  among those 16 is 0.9213**: `rt_msg_client_udp_get_buffer_status` (demo 0x0040ca30, 192 B) → our 0x00632fa8
  (204 B), edges flowgraph MD index. Task 7's `relinked-body` pairs our 0x00632fa8 with its sibling
  `rt_msg_client_get_buffer_status` (demo 0x0040c960, **204 B**, equal length and an equal masked stream unique on
  both sides), so here BinDiff took the wrong sibling.
- **t\* = 0.95**, the first 0.05 step above 0.9213:

| t | 0.00 | 0.30 | 0.60 | 0.70 | 0.90 | **0.95** | 1.00 |
|---|---|---|---|---|---|---|---|
| contradictions under the rule | 16 | 3 | 3 | 1 | 1 | **0** | 0 |
| agreements on the 828 under the rule | 333 | 333 | 333 | 333 | 332 | **332** | 332 |
| NEW pairs under the rule | 1,042 | 348 | 247 | 165 | 111 | **92** | 58 |

- **At t\*, 0 contradictions against 332 agreements**, so the false-pair rate is ≤ 0.9 % at 95 % confidence (rule of
  three, 3/332). By matcher: prime signature 189, edges flowgraph MD index 85, hash matching 49, flowgraph MD index
  top-down 9. By pass: `exact` 231, `relinked-body` 90, `hash+callees` 11. **The limit, stated:** all 332
  agreements are at similarity 1.00, because the proved pairs are byte- or relink-identical bodies. So the 828 test
  the rule where BinDiff sees identical structure. They say nothing about 0.95 ≤ sim < 1.00, where 34 of the 92 NEW
  pairs sit. §3.5 has the only independent evidence for that band.

### 3.4 A second truth set outside the 987: the toml's hand names

`recomp/socom2.toml`'s 656 `name@addr` stub entries are the project's own names, mostly the SDK and libc. E
`[§3 toml]`:

| BinDiff pairs on a toml-named address of ours | total | same name | other name |
|---|---|---|---|
| all, any matcher, any similarity | 552 | 414 | 138 |
| all, under the rule at t = 0.70 | 216 | 216 (17 below sim 1.00) | **0** |
| all, under the rule at t\* = 0.95 | 205 | 205 (6 below 1.00) | **0** |
| NEW only, under the rule at t = 0.70 | 17 | 17 (10 below 1.00) | **0** |
| NEW only, under the rule at t\* = 0.95 | 11 | 11 (4 below 1.00) | **0** |

The largest other-name pair that still clears the rule's matcher and body cuts is at 0.6407 (toml `rand` @0x00197740,
BinDiff demo `SetViewFOV__9CSealCtrlFf`). So on this truth set the rule is clean from 0.70 up.

The one place where Task 7 and the toml disagree is also where BinDiff sides with the toml. **At 0x001a3448, Task 7's
`hash+callees` says `setD3_CHCR`; the toml says `setD4_CHCR`; and BinDiff pairs demo `setD4_CHCR` (0x0015ada8)
there, at similarity 1.00** (call reference matching, so outside the rule). This is the error research/52 §4 and
research/57 found by other routes (S12-R13). It is also the one "contradiction" at similarity 1.00 in §3.2 where
BinDiff is right and the proved pair is wrong.

**Stability (F).** BinDiff's matching is a greedy cascade. With the stock config its name matcher fires on the
syscall names of §1.3, and that shifts the cascade: 8,865 pairs, of which only 7,277 are shared with D's 8,835. **The
rule's pairs barely move**: 445 in D, 446 under F, 441 shared (a scratch script over both SQLite files). F's join also
lands on t\* = 0.95 (largest contradicting 0.9213 again), 0 contradictions, 331 agreements and 94 NEW. The rule
measures structure, and the cascade's order does not change it.

### 3.5 The other levers

E `[§7 levers]` checks each proposals file's rows against BinDiff's pair at the same address of ours, under the rule
at t\*. Across 2,055 rows in ten files, BinDiff names a different demo function **0 times**:

| file | rows | BinDiff under the rule: same | other | no rule pair |
|---|---|---|---|---|
| `game/demo_symbol_renames.csv` (Task 7's 479) | 479 | 330 | 0 | 149 |
| `…_7b.csv` | 6 | 2 | 0 | 4 |
| `…_7c.csv` (vtable slots) | 199 | 3 | 0 | 196 |
| `…_callgraph.csv` / `…_callgraph_loose.csv` | 235 / 522 | 9 / 8 | 0 / 0 | 226 / 514 |
| `…_offsets.csv` / `…_prefix_offsets.csv` | 188 / 43 | 7 / 4 | 0 / 0 | 181 / 39 |
| `…_strings.csv` / `…_strings_loose.csv` | 214 / 45 | 3 / 0 | 0 / 0 | 211 / 45 |
| `…_ui.csv` | 124 | 1 | 0 | 123 |

Of the rule's 92 NEW pairs, 31 are already some other file's proposal, always with the same name, and **61 are
BinDiff's alone**.

## 4. The 159 prefix pairs, and owner decision D5

E `[§4 prefix]`. All 159 rows are in `game/bindiff/prefix_verdicts.csv`: demo and our address, both sizes, the
pass, the engine flag, the raw verdict, the rule verdict, the similarity, the confidence, the matcher, and BinDiff's
competing pair.

| | pairs | raw: agree / disagree / absent | under the rule at t\* = 0.95: confirmed / contradicted / unconfirmed |
|---|---|---|---|
| `prefix` | 119 | 34 / 79 / 6 | |
| `prefix+size` | 40 | 19 / 21 / 0 | |
| **all** | **159** | **53 / 100 / 6** | **21 / 0 / 138** |
| engine (`is_engine`) | 64 | 10 / 48 / 6 | **5 / 0 / 59** |

**The 21 confirmed** are `__ieee754_pow`, `__divdi3`, `__moddi3`, `__ieee754_rem_pio2`, `__udivdi3`, `__umoddi3`,
`__ieee754_exp`, `libnetb_udp_create_space`, `sceSifMBindRpcParam`, `FindMostRecentException`, `lgAudARead`,
`memcpy`, `sceSifWriteBackDCache`, `sceVu0ClipAll`, `SaveFireMessage`, `rt_comm_get_remote_ip`, and the five engine
routines **`CHUD::Flash` (0x001f7e80, 236 B), `zAnimGetDirectionFromAzimuthZenith` (0x0025cb00, 208 B),
`CZAnimMain::SeqSetState` (0x0026a040, 172 B), `CZNetwork::zNetRegisterRemoteObjectCallback` (0x0030ce80, 108 B),
`CCharacterWeap::SetupCharacterWeapon` (0x0053eee0, 104 B)**. 4 of the 21 are already in research/54's
`prefix+offsets` file (§3.5), so BinDiff adds 17.

The 20 largest by demo size (research/44 §4's order):

| # | demo name | ours | demo / our B | pass | raw verdict | rule | sim | BinDiff's matcher (competing pair) |
|---|---|---|---|---|---|---|---|---|
| 1 | `__ieee754_pow` | 0x001ad528 | 3916 / 3916 | prefix+size | agree | confirmed | 1.000 | edges flowgraph MD index |
| 2 | `__divdi3` | 0x0019eb90 | 1684 / 1684 | prefix+size | agree | confirmed | 1.000 | flowgraph MD index top-down |
| 3 | `__moddi3` | 0x0019f228 | 1680 / 1680 | prefix+size | agree | confirmed | 1.000 | edges flowgraph MD index |
| 4 | `ThrottlesPreTick__9CSealCtrlFP4CPadf` | 0x005966a0 | 1560 / 1728 | prefix | disagree | unconfirmed | 0.006 | edges flowgraph MD (demo 0x00333f90 → 0x005966a0) |
| 5 | `__ieee754_rem_pio2` | 0x001ae478 | 1464 / 1464 | prefix+size | agree | confirmed | 1.000 | edges flowgraph MD index |
| 6 | `Open__18CActionTxtrMachineFUi` | 0x0021f850 | 1452 / 2160 | prefix | disagree | unconfirmed | 0.002 | call sequence (demo 0x00174b30 → 0x0021f850) |
| 7 | `__udivdi3` | 0x0019f8b8 | 1404 / 1404 | prefix+size | agree | confirmed | 1.000 | edges flowgraph MD index |
| 8 | `__umoddi3` | 0x0019fe38 | 1384 / 1384 | prefix+size | agree | confirmed | 1.000 | edges flowgraph MD index |
| 9 | `Init__8CMissionFv` | 0x002ad290 | 1328 / 1700 | prefix | disagree | unconfirmed | 0.200 | flowgraph MD top-down (demo 0x001f8e30 → 0x00321d30) |
| 10 | `__ieee754_exp` | 0x001ad088 | 1180 / 1180 | prefix+size | agree | confirmed | 1.000 | edges flowgraph MD index |
| 11 | `Open__11CNodeActionFPQ23zdb6CWorldPCc` | 0x002b4f40 | 1132 / 1484 | prefix | disagree | unconfirmed | 0.008 | edges flowgraph MD (demo 0x001ff140 → 0x003a9a80) |
| 12 | `apply_script_frame__FP27_zanim_…` | 0x0025f3c0 | 1072 / 1212 | prefix | disagree | unconfirmed | 0.033 | call sequence (demo 0x001dd870 → 0x0025f3c0) |
| 13 | `overflow__Q23std39basic_filebuf<…>Fi` | 0x00186f70 | 1044 / 1140 | prefix | disagree | unconfirmed | 0.015 | call sequence (demo 0x001471d0 → 0x00188040) |
| 14 | `RunEventAnim__10CMenuStateFPCcPCc` | 0x001f3bf0 | 1036 / 2128 | prefix | disagree | unconfirmed | 0.018 | edges flowgraph MD (demo 0x003788c0 → 0x003127f0) |
| 15 | `__ieee754_rem_pio2f` | 0x001b04f8 | 944 / 944 | prefix+size | agree | unconfirmed | 1.000 | edges **callgraph** MD index (not structural) |
| 16 | `ClutterTick__Q23zdb19CClutterAnimManager…` | 0x002d8330 | 940 / 1088 | prefix | disagree | unconfirmed | 0.008 | flowgraph MD top-down (demo 0x00217ba0 → 0x00583030) |
| 17 | `sceIoctl` | 0x001a8820 | 844 / 884 | prefix | agree | unconfirmed | 0.925 | edges **callgraph** MD index |
| 18 | `FindExceptionHandler__FP12ThrowContext…` | 0x00182c80 | 804 / 828 | prefix | disagree | unconfirmed | 0.003 | call sequence (demo 0x00144550 → 0x00182c80) |
| 19 | `LoadAssetLib_PS2__Q23zdb9CSaveLoad…` | 0x003199c0 | 804 / 708 | prefix | disagree | unconfirmed | 0.013 | edges flowgraph MD (demo 0x0022ac50 → 0x002ac410) |
| 20 | `DrawFunc<11CDynGrenade>__2ai…` | 0x00598860 | 784 / 812 | prefix | disagree | unconfirmed | 0.018 | flowgraph MD top-down (demo 0x002889a0 → 0x00592260) |

`GetNodePos__10CZSealBodyFPCQ23zdb5CNodeR6CPnt3Db` (our 0x005df930, 460 / 408 B): disagree, unconfirmed, 0.040, call
sequence (demo 0x0031e5d0 → 0x005df930). The 6 absent are all engine: `__dt__16CInGameWeaponSelFv`,
`__dt__15CZPlayerMapItemFv`, `__ct__8CMemCardFv`, `zNetRemoteObjectUpdateCallback__9CZNetworkFiii`,
`__dt__16C2DMessageStringFv`, `SetItem__5CZKitFUi10EQUIP_ITEM`.

**Read the "disagree" rows correctly.** None of the 100 raw disagreements is a contradiction under the rule. Each one
is BinDiff's cascade parking the function next to a stranger at similarity 0.002–0.2, because its structural matchers
need an equal MD index (an equal flow graph), and an edited routine has a different one. **For D5, BinDiff is not
the mechanical substitute for R257's hand review of the big engine routines.** It confirms none of `CMission::Init`,
`CSealCtrl::ThrottlesPreTick`, `CActionTxtrMachine::Open`, `CNodeAction::Open`, `CMenuState::RunEventAnim` or
`CZSealBody::GetNodePos`. The five engine routines it does confirm are all ≤ 236 B, and SOCOM II left their flow
graphs intact.

## 5. New pairs beyond the 987

E `[§5 new]`. **All 7,726 NEW pairs**, by our PT_LOAD (research/44 §3's split) and by the class path of a copy of
`readable()`:

| our region | NEW | engine member | engine free (`z…`/`hud…`) | SDK / runtime |
|---|---|---|---|---|
| 0x100000–0x1d5000 (loader) | 538 | 166 | 8 | 364 |
| 0x1d5000–0x1d5600 | 0 | 0 | 0 | 0 |
| 0x1e7000–0x408480 (FTSCore) | 3,819 | 2,837 | 88 | 894 |
| 0x4c5380–0x66a000 (ZSealEtc) | 3,369 | 1,977 | 62 | 1,330 |
| all | 7,726 | 4,980 | 158 | 2,588 |

**3,595 clear body ≥ 64 B on both sides and size ratio ≥ 0.50** (3,594 of them on a `FUN_` row). The twelve largest
by demo size are all noise: `DefineFPAnims__7AnimSetFv` (29,668 B) → a 76-byte row of ours at similarity 0.000,
`RegisterPackets` (20,188 B) → 368 B at 0.027, `InitializeAnimNames__Fv`, `CZSealBody::ComputeNextPosition`,
`zAnimLoadObjectMotion`, `CZSealBody::Recoil`, `CSealCtrlAi::FollowTick`, `CHUD::StatusLine`,
`CSealCtrlAi::HandleEvent`, `DynProgAccNBestOptSil` (the best of them at 0.118), `CAiSGrenade::Tick`,
`zAnimLoadParticleSource`. These are call-sequence placements, and none is a claim about a body.

**Under the rule at t\* = 0.95: 92 NEW pairs.** All 92 are on `FUN_` rows, all have a demo name unique in the demo,
and 34 are below similarity 1.00. By region: loader 12 (SDK 12), FTSCore 46 (engine member 35, SDK 11), ZSealEtc 34
(engine member 12, SDK 22), so 47 are engine and 45 SDK. By matcher: prime signature 57, flowgraph MD index top-down
18, edges flowgraph MD index 14, bottom-up 3. The twelve largest:

| demo name | demo → ours | demo / our B | sim | matcher |
|---|---|---|---|---|
| `__kernel_rem_pio2` | 0x00168290 → 0x001b0c50 | 2892 / 2892 | 1.000 | edges flowgraph MD index |
| `sceSifStopModule` | 0x00162c90 → 0x001ab398 | 520 / 520 | 1.000 | prime signature |
| `sceFsInit` | 0x0015f338 → 0x001a79f0 | 464 / 516 | 0.957 | edges flowgraph MD index |
| `lgAudEnumerate` | 0x003b5c78 → 0x00243c68 | 464 / 472 | 0.975 | flowgraph MD top-down |
| `KM_SetLocalKeyPair` | 0x0040ae04 → 0x0062f640 | 448 / 472 | 0.952 | edges flowgraph MD index |
| `rt_msg_client_ishutdown` | 0x0040d3d0 → 0x00633790 | 392 / 392 | 0.982 | edges flowgraph MD index |
| `init<PC9CAiMapLoc>__Q23std56__vector_imp<…>` | 0x0018e710 → 0x0051e620 | 380 / 380 | 1.000 | prime signature |
| `KM_SetPublicKey` | 0x0040abb4 → 0x0062f3e0 | 340 / 344 | 0.954 | edges flowgraph MD index |
| `_kDebugException` | 0x00164040 → 0x001ac740 | 284 / 288 | 1.000 | prime signature |
| `GetNextAtom__Q23zdb5CGridFv` | 0x00215910 → 0x002d6260 | 284 / 280 | 0.964 | flowgraph MD top-down |
| `init<PCQ28Particle34SequenceEntry<…>>__Q…` | 0x002384c0 → 0x00328fc0 | 268 / 268 | 1.000 | prime signature |
| `init<PCQ28Particle16SequenceEntry<f>>__Q…` | 0x00238720 → 0x00329220 | 268 / 268 | 1.000 | prime signature |

## 6. What flow-graph similarity adds beyond the byte fingerprint

E `[§6 ceiling]`. research/44 §6 puts 7,595 demo functions (78.3 %) in the "absent" bucket: no byte-identical
counterpart in our image. E recomputes the same 7,595.

- BinDiff pairs **6,733** of them with something. **716** of those pairs are at similarity ≥ 0.70, and **533** of
  those are NEW (neither side in the 987) on a `FUN_` row of ours. That is the raw number the brief asks for.
  §3.2's raw sweep says 45 of the 828 proved pairs are contradicted at 0.70, so at that level a raw pair is a
  hypothesis, not a name.
- **Under the rule at t\* = 0.95: 88** NEW on `FUN_` rows (44 engine; 34 below similarity 1.00). That is 1.16 % of
  the 7,595. **The ceiling moves from 78.3 % to 77.4 %** of the demo's 9,703 ((7,595 − 88) / 9,703).

So R262's premise that "flowgraph similarity survives edits where byte hashes do not" holds only for one narrow kind
of edit, in this form. BinDiff's structural matchers find a body whose *instructions* moved but whose *flow graph*
did not: a changed constant, a changed call target, a register allocation. That is what the prime-signature and
MD-index matchers catch (e.g. `__kernel_rem_pio2`, 2,892 B, similarity 1.00, which the fingerprint missed). A body
with an added branch, a removed block or an inlined call has a different MD index. BinDiff's cascade then hands it
to address-sequence and call-sequence matching, and the similarity it reports for the result (median 0.143 over
the NEW pairs) is a measurement of that difference, not a match. The 78 % stays the vtable route's to attack
(spec Goal 3).

## 7. Recommendation for Goal 4

- **The threshold: similarity ≥ 0.95**, under the rule of §3.3 and never on similarity alone. It takes a structural
  matcher (hash, edges flowgraph MD index, flowgraph MD index top-down or bottom-up, prime signature, relaxed MD
  index), both bodies ≥ 64 B, and size ratio ≥ 0.50. The 0.95 is data-derived: the first 0.05 step above the one
  contradiction at 0.9213.
- **`prefix+bindiff` at 0.80 (the spec's S12-R3 default), as Task 6 plans:** a Task 7 prefix pair that BinDiff pairs
  identically under the rule at 0.95. **Yield: 21 pairs, 5 of them engine; 17 not already in `prefix+offsets`.**
  Evidence: 0 contradictions on the 828 (332 agreements), 0 other-name pairs on the toml (205), 0 disagreements with
  any lever file (2,055 rows), stable under a different cascade (441 of 445 pairs). The sidecar's `Evidence` would read, e.g.,
  `prologue unique both sides + BinDiff edges flowgraph MD index 0.97, 236/248 B` (`CHUD::Flash`).
- **A standalone `bindiff` pass: not as a proposer.** Keep the spec's "never a proposer on its own" for the 61 NEW
  pairs no other lever has. The rule's zero is measured on pairs of similarity 1.00, and the band where a real edit
  would sit (34 pairs between 0.95 and 1.00) has only the toml's 4 as independent evidence. Write them to a loose
  file (`game/demo_symbol_renames_bindiff_loose.csv`, score 0.75, not applied). **BinDiff under the rule does
  qualify as a confirming key for S12-R18's cross-lever promotion.** It agrees with 31 NEW pairs other levers
  already propose (and with 8 rows of `…_callgraph_loose.csv`) and never disagrees. Expected yield of promotion: the
  loose-file rows BinDiff confirms (8 in the call-graph loose file today). Expected error: ≤ 0.9 % at 95 % from 0/332.
- **What it costs to keep:** the installs in §1 (1.2 GB under `/home/user/tools/`, plus 0.5 GB of downloaded
  archives in `/home/user/tools/dl/`, all outside the repository) and the
  patched BinExport, whose source and original are kept beside it. A re-run is B + C + D + E, about 8 minutes of wall time (314 + 113 + 22 + 7 s, §1.4).

## What this means for a task

| task | finding | what it changes |
|---|---|---|
| Task 6 (BinDiff as the second signal) / Goal 4 | Installed and run: Ghidra 11.0.3, EE extension v2.1.16, BinExport 12 (patched, §1.2), BinDiff 8; the join is `tools_py/research/symbols/bindiff_join.py`. The zero-contradiction rule is structural matcher + both bodies ≥ 64 B + ratio ≥ 0.50 + similarity ≥ **0.95** (§3.3) | Task 6 proceeds; S12-R2's "could not install" branch does not apply. The `prefix+bindiff` pass takes the rule verbatim, not a similarity cut alone (41 contradictions remain at 1.00 without it) |
| Task 6's `prefix+bindiff` yield | 21 of the 159 prefix pairs confirmed, 5 engine (all ≤ 236 B), 17 not in `prefix+offsets`; 0 contradicted (§4) | ~17 new names at 0.80, not the big engine routines |
| D5 / S12-R3 (R257's hand review) | BinDiff confirms none of the big engine routines: `CMission::Init` 0.200, `CSealCtrl::ThrottlesPreTick` 0.006, `CZSealBody::GetNodePos` 0.040, `CActionTxtrMachine::Open` 0.002, `CNodeAction::Open` 0.008 (§4) | For routines > 236 B the mechanical substitute is not BinDiff. It stays the vtable slot (Goal 3) or the owner's hand review (a HUMAN_TASKS line; row O11 since 2026-09-25); "admit nothing on a prologue alone" stands |
| Goal 1 / the applier (`setD3_CHCR` at 0x001a3448) | BinDiff pairs demo `setD4_CHCR` there at 1.00 and agrees with the toml; a third independent signal after research/52 and /57 (§3.4) | No change to S12-R13's hold; it gains a third witness |
| S12-R18 (cross-lever promotion) | Under the rule BinDiff disagrees with 0 of 2,055 lever rows and agrees with 31 NEW pairs other levers propose (§3.5) | BinDiff under the rule is admissible as the second independent key that promotes a loose row |
| A standalone `bindiff` pass | 92 NEW pairs under the rule (47 engine), 61 BinDiff-only; evidence at similarity < 1.00 is thin (§3.3, §5) | Loose file only, score 0.75, not applied, until a second key agrees |
| The 78 % ceiling (spec §1.4) | Flow-graph similarity adds 88 NEW pairs among the 7,595 absent: 78.3 % → 77.4 % (§6) | R262's "survives edits" is true only for flow-graph-preserving edits; the ceiling remains Goal 3's |
| Tooling (`docs/DEVELOPING.md`'s Ghidra 12.1) | BinExport supports Ghidra ≤ 11.0.3; the cloud copy is 11.0.3 with an older EE extension; 736 r0001 rows do not decode under it (none of the 987) (§1.3) | A later BinDiff run on 12.1 needs a BinExport build for 12.x (Gradle); until then the cloud's 11.0.3 is the BinDiff Ghidra, and the project's own `socom2_ghidra.csv` stays the 12.1 one |
