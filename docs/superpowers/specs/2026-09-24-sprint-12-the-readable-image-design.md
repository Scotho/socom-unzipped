# Sprint 12 design — "the readable image": every known name in the generated code, with its reason beside it

Date: 2026-09-24 (evening). Written by the Sprint 12 cloud controller from the handoff
(`docs/superpowers/plans/2026-09-24-sprint-12-cloud-handoff.md`, ratified by the local controller the same evening),
R257–R263 (`docs/superpowers/plans/2026-09-23-sprint-11.md`, "Rulings made on the owner's behalf"), research/44 and
/45, and the peer session's measurement scripts (`tools_py/research/symbols/README.md`). Every number here is one of
those documents' and names its command there; the sprint's own research wave (the plan's Phase 2) re-derives the ones
a task rests on before the task builds on them.

**The one-line answer: the recompiled image today reads as 14,882 generated functions of which about 120 carry a
name; the project already holds 485 proven names (479 from research/44, 6 from /45), 656 names in `recomp/socom2.toml`
that never reach the output, a route through RTTI to some 1,500 vtable slots, and a demo `.debug` with types for 95
source files. Sprint 12 puts every name the project can prove into the generated code in a readable form, with its
provenance recorded beside it, and proves the renamed tree still builds and passes the gate.**

## Why this is a sprint and not a task

R263 says why: the rename pass changes the filenames of the generated code, so it carries a recomp, a runtime rebuild
and the r0001 gate; each further lever (vtable slots, BinDiff, ccc types, the toml's stubs) is a proposals file under
its own acceptance rule and then the same rebuild-and-gate; and the value of a name is realised only by the things
that read it — hooks, HLE, the address table, the parity probes, voice chat — which today address the image by raw
number. That is a programme with its own goal, tooling and review loops, and it competes for the machine's lock with
Sprint 11's close. So it runs in the cloud, lock-free, on `sprint-12`, and every item is split into a **code half**
(here) and a **proof half** (the local controller's, at the owner's build windows, batched — handoff §1 ratification
item 4).

## 1. What is established (2026-09-24)

### 1.1 Who consumes a name — **[verified in the tree; the exhaustive map is research Q1]**

| consumer | how it reads the name | what a wrong or unreadable name costs |
|---|---|---|
| **the recompiler** | `recomp/socom2.toml` names `recomp/socom2_ghidra.csv`; `importGhidraMap` (`third_party/ps2recomp/ps2xAnalyzer/src/elf_analyzer.cpp:1786`) copies the `Name` column onto the function at that `Start`; `sanitizeIdentifierBody` (`ps2xRecomp/src/lib/code_generator.cpp:53`) maps every character outside `[A-Za-z0-9_]` to `_`, prefixes `_` to a leading digit, and `sanitizeIdentifier` then prefixes `ps2` to a leading underscore and `ps2_` to a C++ keyword or reserved identifier; the name is the generated function's C identifier and its output filename (`recomp/output/<name>_0x<addr>.cpp`) | two rows with one sanitised spelling are two definitions of one symbol; a name that the sanitiser rewrites is a name a reader cannot grep for |
| | > *Superseded in part (2026-09-24, research/48): the recompiler's own import is `ElfParser::loadGhidraFunctionMap` (`ps2xRecomp/src/lib/elf_parser.cpp:959`, called from `ps2_recompiler.cpp:807`), not the analyzer's `importGhidraMap`; and `makeName` (`ps2_recompiler.cpp:1085`) appends `_0x<start>` to every identifier, so two rows with one `Name` are two distinct C symbols — the csv already carries `AddDmacHandler` ×2, `RFU091` ×3, `RFU116_SetSyscall` ×5 and builds. Uniqueness is still required of every APPLIED name, for grep and for the filename, but the premise is readability, not the linker. A non-auto `Name` also makes its row's range authoritative over the recompiler's jal-scan `sub_` at the same address (`elf_parser.cpp:603-606`), so a rename can change a function's extent: the proof half diffs extents.* | |
| **the runtime hooks** | `game_overrides_socom2.cpp` installs 28 `replaceFunction` wraps on addresses taken from `socom2_addresses.h`, a struct of 41 named fields with one column per revision (r0001 literal, r0004 from `match.json` through `addresses_from_match.py`); function names appear only in comments | a name here is documentation; the table's field names (`node`, `packTrace`, `dnasCheck`) are the project's own and predate the demo's |
| **HLE** | the same table's fields and the syscall/stub selectors in the toml's stub list (`name@addr`, 656 entries) | the stub name selects a runtime handler by string; it must agree with the csv name at that address or a reader sees two names for one routine |
| **the parity tools** | `tools_py/parity/guest_addresses.py` holds the gate's guest probes' addresses **and displacements** per revision (`PROBE_OFFSETS`: `move_scale` is `actor+0x1368` on r0001, `+0x136C` on r0004 — KNOWN §4); `verdict_core.py` carries 62 small hex literals of which the field offsets are the ones a type would name | a raw offset is a per-revision fact with no name; KNOWN §4 records the day one moved and answered with a confident wrong number |
| **the address table across revisions** | `tools_py/carry_names.py` moves the `Name` column from r0001's map onto r0004's addresses through `match.json`; it refuses an address-embedding name (`FUN_…`, `LAB_…`, `thunk_FUN_…`, `caseD_…`) and a collision | a readable name carries; the sidecar (1.3) must carry with it or r0004's map holds names without reasons |
| **voice chat (Q5)** | SOCOM II's codec is **SASE** (`SaseEncVad`/`SaseDec` source paths in all three SOCOM II builds; research/44 addendum, verified against four images); the demo's LPC-10 names and types do not describe it | the names Q5 needs are in retail and unnamed by the demo; the class inventory (research Q10) and the vtable route (Goal 3) are where they would come from |

### 1.2 What "readable" means — **[decided here; proven by research Q2 before Task 1 applies it]**

A readable name is the demo's mangled name rendered as `Class_Method`, with these rules, each of which a test pins:

1. **Form.** `Method__<len>Class…` → `Class_Method`; a `Q<n>` nested path joins with `_` (`Q23zdb5CNode` → `zdb_CNode`);
   the operator table maps `__ct`/`__dt`/`__as`/… to `ctor`/`dtor`/`op_assign`/…; template arguments are dropped from
   the class path and the function name; a free function keeps its name (`sceCdRead`, `hudInit`); a static initialiser
   `__sinit_<file>.cpp` becomes `sinit_<file>`; an anonymous-namespace marker `@` becomes `anon_`.
2. **Overloads.** An argument suffix is added **only where the readable name is not unique** among all names that will
   be applied (today 2 collisions inside the 479 — `C2DBitmapPoly_SetUV`, `CAiMapLoc_ctor` — and 255 colliding names
   over 607 functions across the demo's 9,703). The suffix is the mangled argument list after the `F`, sanitised and cut
   to 24 characters (research Q2 decides between this and a short hash; the default is the argument list because it
   reads). A name that still collides after the suffix is refused, both rows.
3. > *Superseded (2026-09-24, research/47): the rule set a test pins is research/47's R1–R12, with R6 amended by S12-R14; the length limit is 87 characters (the recompiler's 100-character filename budget minus `_0x<addr>`); the overload suffix is the argument list where it splits the whole collision group and a six-hex hash otherwise; a name the demo itself defines at several addresses is kept unsuffixed when the demo holds it that many times; `@n@` is a this-adjusting thunk (`_thunk<n>`), not an anonymous namespace.*
   > *Superseded in part (2026-09-24, research/46 §1.5): the sanitiser that runs is `PS2Recompiler::sanitizeFunctionName` (`ps2_recompiler.cpp:2190`): characters outside `[A-Za-z0-9_]` → `_`, `_` before a leading digit, `ps2_` before a keyword or a reserved spelling (`__x`, `_X`); a leading `_` + lower-case letter is kept. "Returned unchanged" is measured against that function (31 of the 485 readable names fail it today, mostly `__ieee754_*`, `__sinit_*`; research/47 decides their rendering). Filenames are cut at 100 characters of `<name>_0x<addr>`.*
   **Legality.** Every applied name is a legal C identifier that `sanitizeIdentifier` returns **unchanged** (no leading
   underscore or digit, no keyword, no reserved spelling), a legal Windows filename, at most 96 characters (over that,
   the cut plus eight hex digits of SHA-1 of the original, as `ghidra_symbol_match.c_identifier` does today), and unique
   across the whole csv — including the 113 hand-named rows, which neither proposals file checks today (research/45 §9's
   inherited gap; the applier is where it closes).
   > *Superseded in part (2026-09-24, research/48): the csv has no hand-named rows (see 1.3) and already repeats three Ghidra names over ten rows; the rule is: every applied name is unique among applied names and equal to no existing non-placeholder name; the ten pre-existing repeats stay as they are.*
4. **The mangled original is kept** in the provenance sidecar's `Mangled` column, so a demangler can run later and no
   information is lost by the readable form.
5. **A name without a recorded reason is a defect** (R261). See 1.3.

### 1.3 Provenance — **[decided here; the reader and the audit are Task 1's]**

> **Superseded in substance (2026-09-24, research/57, S12-R13): the sidecar is not beside the name, it IS the name.**
> The recompiler reads `recomp/socom2_names.csv` (`[general] names`) and uses its `Name` only for the generated
> identifier, the filename and the `// Function:` header; `recomp/socom2_ghidra.csv`'s `Name` column stays Ghidra's
> export and is never rewritten, because in this recompiler a csv name is function identity (it fixes the extent,
> stubs by name, and flips the correctness-critical prefixes). Every sentence below that says "the csv's `Name`"
> for an applied name reads "the sidecar's `Name`"; the audit rule is restated in S12-R13.

One tracked file beside the csv, `recomp/socom2_names.csv`, with the columns
`Address, Name, Mangled, Pass, Score, Evidence, Source, Date`:

- `Pass` is the proposals file's pass name (`exact`, `hash+callees`, `relinked-body`, `positional`, `vtable-slot`,
  `toml-stub`, `hand`); `Score` the method score research/44 §2 defines (or `1.00` for `hand`); `Evidence` the one-line
  reason in the pass's own vocabulary (`fingerprint unique both sides, 184 B`; `tier B image-wide, ratio 0.63, gap 4`;
  `CZSealBody vtable slot 7 of 26, fixed points 3`); `Source` the note and command that produced the row
  (`research/44 command A`); `Date` the day it was applied.
- **The rule, in code:** every row of `recomp/socom2_ghidra.csv` whose `Name` is not an auto name (`FUN_`, `LAB_`,
  `thunk_FUN_`, `caseD_`, `sub_`, `entry`) has exactly one sidecar row with the same `Address` and `Name`; a sidecar row
  whose address is not in the csv, or whose name disagrees, fails the test. The 113 pre-Sprint-12 hand names are
  backfilled with `Pass=hand, Evidence=named before Sprint 12` in Task 1's first commit so the rule has no exception.
  > *Superseded (2026-09-24, research/48 §1, §3, §7): the csv holds NO hand names. Its 113 non-`FUN_`/`thunk_FUN_` rows are 69 Ghidra syscall stubs (52 EE kernel, 8 SIF, 9 `RFUnnn` reserved slots; all from the csv's first commit `f69790b`, 2026-09-04), 42 `caseD_` labels, `entry`, and one `thunk_EXT_FUN_09481d98`. So: the placeholder predicate is anchored — `FUN_`/`LAB_`/`DAT_`/`SUB_`/`sub_` + 8 hex, `thunk_(EXT_)FUN_` + 8 hex, `caseD_<hex>`, `switchD_` + 8 hex, `entry` — and the backfill is 69 rows with `Pass=ghidra, Score=1.00, Date=2026-09-04` and one of three `Evidence` texts (kernel / SIF / reserved-slot stub). The audit keys on `Address`, one row per address. The file is CSV with the column line first and no `#` header. The leak check refuses a `Mangled` value carrying `@unnamed@` as an opaque token (one of the 485 today, 156 demo names in general): the sidecar's commit carries one reviewed `leak_allow.txt` line for `recomp/socom2_names*.csv`.*
- > *Amended (2026-09-24, research/48 §4–§5): `carry_names`' 8-hex-run rule is replaced by the anchored placeholder predicate above — it silently dropped `C2DBitmapPoly_SetUV_ffffffff` and let `caseD_<n>` travel (6 of 42 land on a different r0004 address); a dropped name is counted as refused. Of the 485 proposals' addresses 469 are placed in `match.json` (424 `exact`, 14 `hash+callees`, 31 `relinked-body`) and 16 are `unresolved` (the three mic routines, four static initialisers, seven SDK, two `rt_`): those stay r0001-only.*
- **`carry_names`** reads the sidecar and writes `recomp/socom2_names_r0004.csv` beside `socom2_ghidra_r0004.csv`
  with `Pass=carried:<original pass>` and `Evidence=match.json <how> from 0x<r0001 addr>; <original evidence>`, so a
  carried name says both why it exists and how it travelled. The r0004 csv is regenerated **from the tracked r0004 csv
  itself** (its own `Start/End/Size` never move; only `Name` does, and only where the row is still auto-named or holds
  the r0001 name being replaced) because the raw r0004 export is not tracked.
- **The recompiler's own `sub_*` gap-fill names get no row**: they are placeholders, not names (research Q3 confirms
  or overturns with the count).

### 1.4 The passes and what each has proved — **[verified: research/44 §3, /45 §5, the symbols README]**

| pass | rule (in code) | proposals today | scored |
|---|---|---|---|
| `exact`, `hash+callees`, `relinked-body` (Task 7, research/44 command A) | six hurdles: score ≥ 0.80, body ≥ 64 B, not a prefix pass, no colliding demo name, our row still `FUN_`, a unique legal identifier | **479** (338 / 15 / 126) | 1.00 / 0.95 / 0.85 × the length weight |
| `positional` (Task 7b, research/45 command A) | tier A or B, body ≥ 64 B, key unique image-wide, identifier hurdles; holdout 148 + 115 re-derived, 0 wrong | **6** | tier B `image-wide`; scored 0.80 |
| `bridge` (7b) | both hops strong, no contradiction | 704 confirmations, **0** new names | corroboration only |
| `prefix`, `prefix+size` (Task 7, `--prefix`) | a 16-instruction prologue hash unique both sides; **never proposed** (hurdle 3) | 159 pairs, 0 proposals; R257 says the big engine routines are "reviewed by hand" | 0.60 / 0.70 |
| `vtable-slot` (Task 7c, Goal 3, not written) | string → RTTI object → vtable; slots aligned on body-matched fixed points; equal-count runs by position; constructors from the vtable-pointer store | 111 classes resolve to one retail vtable, 1,154 demo slots against 1,496 retail, 41 classes with equal slot counts; 54 several, 66 absent, 14 templates | below `exact`: **0.75** proposed, the plan fixes it |
| `toml-stub` (Goal 6, not written) | the toml's 656 `name@addr` (272 agree with Task 7's proposals name for name, 1 differs) | ~384 addresses the toml names and nothing else does | 0.90: the project's own hand names, checked against the csv by a test |
| BinDiff (Goal 4, not run) | flow-graph similarity; an independent cross-check, never a proposer on its own | agree / disagree / new over the 987 | not a pass; a second signal |

The ceiling stands as research/44 §6 states it: 7,595 of the demo's 9,703 functions (78 %) have no byte-identical
counterpart in our image because SOCOM II is a year of edits later. The vtable route is the first lever aimed at that
ceiling rather than at the disambiguation under it: an edited virtual keeps its slot.

### 1.5 What the machine must prove, and what the cloud can — **[the handoff's §1]**

The cloud session runs static analysis for hours without lagging anyone and cannot build the Windows runtime, run the
game or take the lock. Every goal below therefore states a **code bar** (a test, a proposals file, a note) the cloud
meets and a **proof bar** (recomp, runtime, gate) the local controller meets at a window. The sprint's acceptance bar
(§4) is the proof bar of Goal 1 plus the code bars of everything else.

## 2. Goals

### Goal 1 — the rename pass, applied and proven **[A]** — first, because everything else runs on the renamed tree

The 479 (research/44 command A, regenerated) plus 7b's 6 (research/45 command A, regenerated) applied to
`recomp/socom2_ghidra.csv` in readable form (1.2), with the provenance sidecar (1.3), the `carry_names` change, and
the r0004 map regenerated from it. One reviewed commit; the applier is a tool (`tools_py/apply_names.py`) whose
acceptance rule is code: it refuses any name that fails 1.2's hurdles and prints why, and it refuses to write a csv
row without writing the sidecar row in the same run.

- **Code bar:** the applier's tests on synthetic csv/proposal fixtures (a collision, a hand-named row, a keyword, a
  leading digit, a 97-character name, a row with no sidecar); the sidecar audit test green over the real csv; the
  readable-name uniqueness proof over the demo's 9,703 and over all proposal files (research Q2's command, re-run by the
  task); the Python suite `OK`.
- **Proof bar (local, PROOF REQUESTED row):** `./build.sh recomp` writes `recomp/output` with the new filenames and no
  duplicate symbol; `./build.sh runtime` links; the r0001 gate 3/3 with **PINS MATCH** on the rebuilt exe; the C++
  suite green. Until that row carries the local result the task is `DONE (code), PROOF PENDING`.
- **Stop rule:** a proposal that would rename a hand-named row, or that collides with one, is refused, never
  overridden (D2's default). A rename that changes a name `socom2_addresses.h`'s comments or the parity tools' comments
  cite is allowed (D4) and the comment is updated in the same commit.

### Goal 2 — provenance on every name **[A]** — inside Goal 1, stated apart because it is the rule the sprint keeps

- **Code bar:** the sidecar file, its reader in `carry_names`, the audit test (1.3's rule), and the plan's stop rule
  "never a rename applied to the csv without its sidecar rows and its acceptance rule in code". A proposals file that
  cannot say its `Evidence` in one line has no acceptance rule and does not apply.

### Goal 3 — vtable slots through RTTI (Task 7c) **[A]** — the lever aimed at the 78 %

> *Amended (2026-09-24, research/51, S12-R16): rule 1's lookup key is the demo's own qualified RTTI string plus a
> layout filter (211 classes, templates included); rule 2 counts the vtable start as a fixed point and names
> equal-count vtables whole (169 slots, holdout 0 wrong); rule 3 admits a shared body two or more vtables name the same
> way; rule 4 (constructors) is withdrawn as written. The plan's Task 4 carries the amended rule.*

From `tools_py/research/symbols/vtable_rtti.py` and `vtable_anchors.py`: a third proposals file
(`game/demo_symbol_renames_7c.csv`) under its own rule, pass name `vtable-slot`, in `tools_py/ghidra_symbol_match.py`
and `tools_py/symbol_levers.py` (both the cloud's on `sprint-12` from the branch's first commit). The rule:

1. A demo `__vt__` class resolves to **exactly one** retail vtable through `"\0Name\0"` → RTTI object → vtable (the 111);
   the "several" bucket is split by the demo's qualified `Q2` name and by which vtable the body-matched slots fall in,
   else refused; templates refused (research Q6 measures what opens them).
2. Slots align on **body-matched fixed points** (a Task 7 pair in both vtables at the same slot index after alignment);
   a run of slots between two fixed points, or after the last one, names by position **only when the run has equal
   length on both sides**; a class with no fixed point names nothing (its 41 equal-count classes wait for a fixed point
   or for research Q6's evidence).
3. Each named slot's body clears **size ratio ≥ 0.50** and 64 bytes (7b's tier B cuts, unchanged and for the same
   reasons); a slot's target that is already named, or is a shared base body (the same address in two vtables), is
   refused with its reason counted.
4. **Constructors** are proposed from the `lui/addiu` pair forming a located vtable address followed by a store to the
   `this` register's word 0, as `Class_ctor` (`Class_dtor` for the reset), only when exactly one such function exists
   per vtable.
5. The identifier hurdles of 1.2, against the csv and both earlier files.

- **Code bar:** synthetic-image tests (a vtable with an RTTI header, a fixed point, an equal-count run, an unequal run
  refused, a shared base body refused, a constructor store); the file written with its rule in `#` header lines; a
  holdout against the 828 proved pairs in the shape of research/45 §3 (hold out the fixed points that are also slots,
  re-derive, count wrong); a research note with every count and its command.
- **Proof bar:** the same as Goal 1's, batched with it or with the next window.
- **Stop rule:** if the holdout's wrong count is not zero at the rule above, the file is not applied and the note says
  what rule would make it zero and what that costs.

### Goal 4 — BinDiff as the independent cross-check **[A, if the environment can install it]**

R262 replaced Ghidra Version Tracking with BinDiff. Ghidra headless (`tools/ghidra/docker/`) exports both images
through BinExport; BinDiff diffs demo1 → r0001; the result is joined to the 987 pairs by address: **agree / disagree /
new**, by pass, and a false-pair rate against the 828 proved pairs by research/45's holdout method.

- **Code bar:** the join tool and its tests on a synthetic BinDiff result; research note Q4 with the three counts and
  the rate; a ruling on what BinDiff's flow-graph similarity is worth as a second signal (the plan's default: a
  BinDiff-confirmed `prefix` pair on an engine routine is the mechanical form of R257's "reviewed by hand", and may be
  proposed at 0.80 under a `prefix+bindiff` pass — S12-R3).
- **Stop rule:** if BinDiff or Ghidra cannot be installed under the environment's network policy, the goal is retired
  by a ruling that says so and what it cost, and R257's hand review stays a HUMAN_TASKS line.

### Goal 5 — the demo's DWARF1 types through ccc, with the layout-age caveat **[A, same condition]**

`ccc` (chaoticgd) walks the demo's `.debug` (5.1 MB, 95 units, mostly FTS and the LPC-10 codec): compile units, types,
locals. Output: a types note (research Q5) naming which engine structs have layouts, and — for every field offset the
parity tools or the hooks use by raw number — whether SOCOM II's own access pattern agrees (the three twin functions'
displacements, as KNOWN §4's `move_scale` row did by hand). **A field offset from SOCOM 1 is a hypothesis about SOCOM II
until the access pattern confirms it (R262).**

- **Code bar:** the list of offsets that can be named safely, each with its confirming command; a `guest_addresses.py`
  change that names those offsets (a name beside the number, per revision) with a test; no hook or probe changes its
  behaviour.
- **Stop rule:** the same as Goal 4's for the install; and a layout the access pattern contradicts is written as a
  contradiction, never applied.

### Goal 6 — the toml's 656 stub names reach the generated output **[A]**

> *Amended (2026-09-24, research/57, S12-R13): the names reach the output through the sidecar and the recompiler's
> `[general] names` key, not through the csv; 41 of the 656 are not csv rows and no route names them (none is a call
> target; 9 are stub selectors that bind nothing, KNOWN §4's nine); the 338 auto-named toml addresses apply as
> `toml-stub` rows, the 134 names starting with `_` rendered by research/47's R6 and S12-R14, and the six names the
> toml gives to several addresses refused by R10, not scored 0.90.*

Today `ps2_recompiled_stubs.h` declares `sceCdDelayThread` as `sub_0018DBB8`: the toml's `name@addr` selects a runtime
handler and never names the function. Research Q12 finds the smallest change that carries every known name into
`recomp/output`. The default this spec proceeds on (S12-R4): **the csv plus the sidecar are the one home of a name**;
the ~384 toml-only names apply through the same applier as a `toml-stub` pass at 0.90 (the project's own hand names,
their `Evidence` the toml line), and a test asserts every toml stub name agrees with the csv name at its address, so the
two files cannot drift. A recompiler change is made only if Q12 shows the stub header takes its name from somewhere
the csv cannot reach; then it is a synthetic-ELF-tested change in `ps2xRecomp`.

- **Code bar:** the pass applied through the applier with sidecar rows; the agreement test; synthetic-ELF tests if the
  recompiler changes.
- **Proof bar:** the recomp and the gate, batched with Goal 1's window or the next.

### Goal 7 — what a stranger sees **[A]**

With names applied, `recomp/output` reads differently and `docs/HOW_IT_WAS_BUILT.md` and `docs/DEVELOPING.md` must say
what a name is, where its reason lives, and the two proposal-file rules (research/44 §2's six hurdles and research/45
§2's), without repeating a number those notes own.

- **Code bar:** the two documents' new paragraphs, `python -m tools_py.docmaint` exit 0, the doc tests green.

## 3. Decisions for the owner — each with the default the sprint proceeds on

| # | decision | default | ruling |
|---|---|---|---|
| D1 | The naming style | `Class_Method` (1.2) | S12-R1 |
| D2 | May a hand-named row be renamed? | **No** (R257's rule 5): a proposal on a hand-named row is refused and counted | S12-R1 |
| D3 | Are the 138 `exact` pairs between the score line and the 64-byte rule ever proposed? | **No** (research/44 §7): `PROPOSE_MIN_SIZE` stays 64 | S12-R1 |
| D4 | May a rename change a name the parity tools or the address table cite in a comment? | **Yes**: comments are not contracts; the comment is updated in the same commit | S12-R1 |
| D5 | R257's "159 prefix matches reviewed by hand for the big engine routines" | a hand review is the owner's; the sprint substitutes a mechanical second signal (Goal 4's `prefix+bindiff`, or a Goal 3 vtable slot) and admits nothing on a prologue alone | S12-R3 |
| D6 | Where the toml's names live | the csv and the sidecar; the toml's stub list stays as the handler selector and a test holds it to the csv | S12-R4 |
| D7 | Installing Ghidra, BinDiff and ccc in the cloud environment (network policy, disk) | attempted; a refusal retires the goal by a ruling with its cost | S12-R2 |

Say a word to change any of these and the affected task is reworked; nothing is lost, every rename is one csv edit
and one sidecar row away from reversal.

## 4. The acceptance bar of the sprint

1. **The renamed tree builds and passes the r0001 gate 3/3 with PINS MATCH** (the local proof, on the commit the
   PROOF REQUESTED row names), with no duplicate symbol in `recomp/output` and the C++ suite green.
2. **Every proposals file's acceptance rule is stated in code, not in prose** — Task 7's six hurdles are the model; a
   file's `#` header repeats the rule the code enforces, and a test proves the strict path refuses a row the rule
   refuses.
3. **Every name in the csv has a sidecar row** and the test that says so is in the suite.
4. **Every number in every note names its command**, and the numbers a task rests on were re-derived by an agent that
   did not write the note.
5. The Python suite `OK`; CI green on `sprint-12`; nothing of the game in the repository; no push anywhere but
   `sprint-12`; no edit to the files handoff §5 reserves for Sprint 11.

## 5. What this does not do

- It does not touch the game's behaviour: no hook, probe or HLE path changes what it does; only what it is called and
  what stands beside the number.
  > *Qualified (2026-09-24, research/46 §4–§5): a rename CAN change behaviour in two ways the recompiler has — a name on `ps2_call_list.h`'s stub list makes the recompiler stub the function by name (19 of the 485; held, S12-R10), and a non-auto name makes the csv End final where the JAL scan's larger End won before (237 of the 485; accepted only when the cloud's own recomp shows no new `unmapped`/`unhandled` continuation, S12-R11). The promise stands as a bar, enforced by the applier's holds and the recomp census, not as an assumption.*
- It does not propose a name on a prologue alone, on position alone, or on a SOCOM 1 layout alone.
- It does not merge to `main`, open a PR, or write `docs/CURRENT_SPRINT.md`, `HANDOFF.md`, `STATUS.md`,
  `HUMAN_TASKS.md` or Sprint 11's KNOWN rows (handoff §5); its live state is the plan's log and its research notes.
- It does not fetch the Nov 25 2003 prototype or the Aug 28 2003 beta (research Q13 writes what each would add so the
  owner can decide).
- It does not decide voice chat (Q5); it writes the note Q5's owner starts from (research Q11) and names the classes
  whose naming would pay first for online play and voice (research Q10).

## 6. Pointers

- The plan: `docs/superpowers/plans/2026-09-24-sprint-12.md` (tasks in dependency order, the "needs the local tree"
  column, the PROOF REQUESTED rows, the log, the rulings `S12-R1`…).
- The handoff and its ratification: `docs/superpowers/plans/2026-09-24-sprint-12-cloud-handoff.md`.
- The seed rulings: R257–R263 in `docs/superpowers/plans/2026-09-23-sprint-11.md`.
- The notes: `docs/research/44-demo-symbols.md`, `45-positional-and-bridge-names.md`; the measurement scripts and the
  corrected voice-codec record: `tools_py/research/symbols/README.md`.
- The consumers: `recomp/socom2.toml`, `recomp/socom2_ghidra.csv`, `third_party/ps2recomp/ps2xRecomp/src/lib/elf_parser.cpp`
  (`loadGhidraFunctionMap`, the auto-name rule, the End tie-break), `ps2xRecomp/src/lib/ps2_recompiler.cpp`
  (`sanitizeFunctionName`, `makeName`, `isStubFunction`, `clampFilenameLength`) — research/46 §1 is the map,
  `ps2xRuntime/include/runtime/socom2_addresses.h`, `ps2xRuntime/src/lib/game_overrides_socom2.cpp`,
  `tools_py/parity/guest_addresses.py`, `tools_py/carry_names.py`.
