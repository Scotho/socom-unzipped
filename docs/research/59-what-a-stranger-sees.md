# 59. What a stranger sees: the renamed output, the sidecar and the documents, read cold

Date: 2026-09-25. Sprint 12 research wave, question 14 of the cloud handoff §4
(`docs/superpowers/plans/2026-09-24-sprint-12-cloud-handoff.md`): "with names applied, what `recomp/output` reads
like, what `docs/HOW_IT_WAS_BUILT.md` and `DEVELOPING.md` must say about names, provenance and the two proposal-file
rules". Written by Task 9's sub-agent, which also wrote the documents it judges in §5 — read that section with that
in mind. Read-only: no game was run, nothing was recompiled for this note, and no tracked file other than the four
Task 9 files was touched. Names, addresses and counts only.

**The state read.** The sidecar at commit `cd2fbfc` (Task 3's commit, the first applied names) and the cloud's
recomp of that tree, made by Task 3 under Task 3a's recipe. Later passes (Task 6's BinDiff lever, Task 8's
toml-stub lever) add rows after this; the plan's task table owns the current count, and nothing below is a live
number.

**The one-line answer: 1,560 of the 14,879 generated functions now carry a readable name (the plan's Task 3 row:
1,491 applied plus the 69 Ghidra rows), and each one can be traced to its reason in one grep — once the reader
knows to pad the address. The remaining 13,220 `FUN_`/`sub_` sit mostly in the two overlays, and about a quarter
of them are under the 64-byte floor that every lever keeps. The header's word `identity` is the recompiler's
jargon and misleads; the 125 named stubs carry no header at all; and a build whose names file does not resolve
emits the old names without an error.**

The commands (from the repository root; `T` is the directory Task 3's cloud recomp wrote, holding
`recomp/output/` and `recomp/recomp_run.log`):

```
# A -- the census of the renamed output and its diff against the baseline (the plan's Task 3a recipe)
python -m tools_py.recomp_census $T/recomp/output $T/recomp/recomp_run.log --json a.json
python -m tools_py.recomp_census --diff game/recomp_baseline/census.json a.json

# B -- A's extents split by PT_LOAD (research/44 §3's ranges) and by identifier class
python - a.json <<'EOF'
import json, sys, collections, re
ext = json.load(open(sys.argv[1]))["extents"]
R = [(0x100000, 0x1d5000, "boot loader"), (0x1e7000, 0x408480, "FTSCore"), (0x4c5380, 0x66a000, "ZSealEtc")]
c = collections.Counter()
for start, v in ext.items():
    s = int(start, 16); r = next(n for lo, hi, n in R if lo <= s < hi)
    k = re.match(r"(FUN_|sub_|thunk_|caseD_|entry)?", v["identifier"]).group(1) or "readable"
    c[r, "all"] += 1; c[r, k] += 1
    if k in ("FUN_", "sub_"):
        if v["end"] is None: c[r, "stub"] += 1
        else: c[r, "<64"] += v["end"] - s < 64; c[r, ">=1K"] += v["end"] - s >= 1024
for r in ("boot loader", "FTSCore", "ZSealEtc"):
    print(r, {k: c[r, k] for k in ("all", "readable", "FUN_", "sub_", "stub", "<64", ">=1K")})
EOF

# C -- the header forms
cd $T/recomp/output && grep -l '^// Function:' *.cpp | wc -l && grep -h '^// Function:' *.cpp | grep -c '(identity sub_' \
  && grep -h '^// Function:' *.cpp | grep -c '(identity FUN_' && grep -h '^// Function:' *.cpp | grep -c '(identity thunk_'

# D -- the sidecar as committed at cd2fbfc: passes, scores, multi-pass rows, repeated names
git show cd2fbfc:recomp/socom2_names.csv > names.csv && python - <<'EOF'
import csv, collections
r = list(csv.DictReader(open("names.csv")))
print(len(r), sum("&" in x["Pass"] for x in r), collections.Counter(x["Score"] for x in r).most_common(),
      sum(len(x["Evidence"]) > 120 for x in r), len(r) - len({x["Name"] for x in r}))
EOF

# E -- the named stubs: A's extents of kind "stub" whose address has a sidecar row, the handler name
#      (stub_target) against the sidecar Name; and the anonymous stubs (kind "stub", identifier FUN_/sub_)
# F -- the runtime's r0001 address table against the sidecar: every `0x........u,   // <field>` literal in
#      kR0001 of third_party/ps2recomp/ps2xRuntime/include/runtime/socom2_addresses.h that is a start in
#      recomp/socom2_ghidra.csv, and the sidecar Name at it
```

A and C take seconds; B, D, E and F under a second each. E and F are ten-line loops over A's JSON and the two
tracked csvs, written out in the text where their numbers are used.

## 1. How many generated files carry a readable name

| class of identifier | baseline (the plan's Task 3a row) | after `cd2fbfc` (command A) |
|---|---|---|
| readable (a sidecar name) | 69 | **1,560** |
| `FUN_…` (Ghidra's placeholder) | 7,958 | 7,043 |
| `sub_…` (the recompiler's JAL-scan placeholder) | 6,750 | 6,177 |
| `thunk_…`, `caseD_…`, `entry` (Ghidra labels) | 59, 42, 1 | 56, 42, 1 |
| functions / files | 14,879 / 14,882 | 14,879 / 14,882 |

The 14,882 files are the 14,879 functions plus `ps2_recompiled_functions.h`, `ps2_recompiled_stubs.h` and
`register_functions.cpp` (research/57 §1). The diff (command A, second line) prints 1,491 renamed, 0 extents
changed, 0 functions only on one side, `unhandled` and `unmapped` unchanged — the plan's Task 3 row, which is where
the count is owned. So **1,560 of 14,879 functions (10.5 %) read as names**; `ps2_recompiled_functions.h`
declares every one under its new identifier (`void CZOnlineLobby_JoinRoom_0x2e3790(…)`), and no file name is cut
(the longest is 60 characters, command A's `extents`; the longest sidecar name is 47, command D).

## 2. What is still `FUN_`/`sub_`, and where

Command B, split by `PT_LOAD`:

| region | functions | readable | `FUN_` + `sub_` | of those, stubs | under 64 B | 1 KB and over |
|---|---|---|---|---|---|---|
| boot loader (the Sony SDK and C runtime) | 1,357 | 507 | 844 | 87 | 273 | 97 |
| FTSCore (the FTS engine and application layer) | 8,287 | 760 | 7,477 | 1 | 1,868 | 797 |
| ZSealEtc (the game) | 5,235 | 293 | 4,899 | 1 | 1,436 | 582 |

(The "readable" column counts the 69 Ghidra syscall-stub rows in the boot loader.) Four classes account for what
remains; they overlap (a small body can sit in an overlay), and each has its note:

- **Edited bodies in the two overlays** — 12,376 of the 13,220. research/44 §6: most of the demo's functions have
  no byte-identical counterpart because SOCOM II is a year of edits later; research/49 §6 moves that ceiling by
  under a point. research/55 §5's gap map names the largest demo classes with nothing placed then; against the
  sidecar at `cd2fbfc` (command D's file, `grep -c '^0x[0-9a-f]*,<Class>_'`) they are still almost empty:
  `CSealCtrlAi` 2 names, `CNetCnf` 0, `CZNetGame` 0, `CZNetVoice` 0, `CSealCtrlSquirm` 0, `CAiPath` 1, where
  `CZSealBody` has 31 and `zdb_CNode` 15. The online classes are non-virtual (research/55 §4.1), so the vtable
  route cannot reach them.
- **Small bodies** — 3,577 (273 + 1,868 + 1,436) are under 64 bytes, the floor every lever keeps (research/44 §2
  hurdle 2; D3 keeps the 138 sub-64-byte `exact` pairs out). No pass as written will name these.
- **The large engine routines** — 1,476 are 1 KB or more. The five R257 named are left to the owner's hand review
  (S12-R22): BinDiff scores them 0.002–0.200 and no vtable slot reaches them (the plan's Log, 2026-09-25 early).
- **The toml-bound stubs** — 89 stub files (87 in the boot loader) still carry a placeholder identifier although
  their body names the runtime handler it calls (`sub_0018EF70_0x18ef70` calls `ps2_stubs::sceCdDiskReady`; command
  E). These are Task 8's `toml-stub` pass's to name, and a stranger reading one sees the handler's name in the body
  and a number in the identifier.

`sub_` versus `FUN_` is itself a trap for a reader: both are placeholders, from two different programs (research/57
§1: `sub_` is the recompiler's JAL scan winning the extent tie against a csv `FUN_` row), in two hex cases
(`sub_002E3790`, `FUN_0038a6a0`).

## 3. The header: what `// Function: X (identity Y)` tells, and the word `identity`

A renamed code file opens (command C; line 14 after the includes):

```
// Function: CZOnlineLobby_JoinRoom (identity sub_002E3790)
// Address: 0x2e3790 - 0x2e3a30
void CZOnlineLobby_JoinRoom_0x2e3790(uint8_t* rdram, R5900Context* ctx, PS2Runtime *runtime) {
```

Of the 14,657 files with a `// Function:` line, 1,366 carry `(identity …)`: 507 over a `sub_`, 856 over a
`FUN_`, 3 over a `thunk_` (command C). The 61 Ghidra-named code rows print their name alone (display and map name
are equal). The 133 named stubs (125 applied, 8 Ghidra) print **no header**: a stub file is the identifier and a
call to its handler.

**What it tells.** The display name, the map's name for the same start, and the extent. It does not say where the
name came from, and nothing in the file points at `recomp/socom2_names.csv`.

**Is `identity` the right word? No.** It is the recompiler's term (S12-R13: a map name is function identity, in
that it decides the extent and stubbing), and inside that ruling it is exact. A stranger reads
`X (identity Y)` as "X is the same function as Y" — an alias, perhaps defined elsewhere — or as a type-theory word;
there is no file called `sub_002E3790` any more, and the reader cannot tell that Y is a placeholder that still
governs the code. What I would change (Task 3b's `function_emitter.cpp:77`, a one-line wording change and its
`ps2xTest` assertion):

```
// Function: CZOnlineLobby_JoinRoom
// Name source: recomp/socom2_names.csv row 0x002e3790 (map name sub_002E3790)
// Address: 0x2e3790 - 0x2e3a30
```

That tells a stranger where the reason lives and gives the sidecar's own padded spelling of the address to grep,
without the loader reading more than the first two columns (it cannot read `Pass` safely: `Mangled` may hold a
quoted comma). "Map name" says what `Y` is. The same two lines on a stub file (`// Function: sceCdRead — stub,
calls ps2_stubs::sceCdRead`) would give the 133 named stubs a pointer too.

**The address has three spellings** in one file and its sidecar row: `0x2e3790` in the identifier, `002E3790` in
the `sub_` name, `0x002e3790` in the sidecar. A reader who greps the identifier's form in the sidecar finds
nothing. `docs/DEVELOPING.md` ("Names in the generated code") now says to pad; the header change above would make it
unnecessary.

**The stubs cross-check the names.** Of the 125 applied names on stub files, 111 equal the runtime handler's name
exactly and the other 14 differ only by leading underscores (`_printf` / `printf`, `kernel_cosf` / `__kernel_cosf`
— S12-R14's stripping; command E). Nothing reports this agreement; it is free evidence.

## 4. Does the sidecar answer "why is this called that?" in one line

Command D's file, one row:

```
0x002e3790,CZOnlineLobby_JoinRoom,JoinRoom__13CZOnlineLobbyFPCc,string-set,0.80,"string-set: strings=2;order=anchors-out-of-order;callees=overlap",demo_symbol_renames_strings.csv; research/53,2026-09-24
```

**Mostly yes.** One line gives the demo's own mangled name (so the readable form is checkable against research/47's
rules), the method, a score, the evidence and the note whose rule admitted it. Where it falls short:

- **The evidence is in each pass's private vocabulary.** `order=anchors-out-of-order`, `key=caller+pair; |K|=5+5`,
  `fixed points start..end` need the note to decode; the pass name is also repeated inside `Evidence`
  (`exact: fingerprint exact, 164 B`). 165 of the 1,560 rows have more than 120 characters of evidence (command D),
  128 of them multi-pass rows.
- **`Pass` joins agreeing passes with `&` and uses `+` inside a name** (`vtable-slot&prefix+offsets`); 163 rows
  are multi-pass (command D). Documented now; not guessable.
- **`Score` is on each pass's own scale** (the six values 0.75–1.00, command D): `exact`'s 1.00 is research/44's
  method score, `vtable-slot`'s 0.75 a fixed pass score set by ruling. It is not a probability and not comparable
  across passes. Documented now in DEVELOPING.
- **`Source` names a git-ignored file** (`demo_symbol_renames_strings.csv` lives under `game/`). The note beside it
  is the durable pointer; the file is regenerated by the lever.
- **The demo's address is absent.** To re-check a pair, a reader needs the SOCOM 1 function; `Mangled` finds it in
  the demo's `.symtab` except where one name has several addresses (research/47 R10).
- **Names repeat in 7 rows** (the Ghidra stubs `AddDmacHandler` ×2, `RFU091` ×3, `RFU116_SetSyscall` ×5; command D),
  so a grep by name can return several rows; the address is the key.

## 5. Do the documents answer a newcomer's first three questions

Judged against the text Task 9 wrote (`docs/HOW_IT_WAS_BUILT.md` "How the generated code got its names",
`docs/DEVELOPING.md` "Names in the generated code", the symbols README's wave table):

1. **"Where did this function's name come from?"** Answered: DEVELOPING gives the sidecar, the grep with the
   padded address, each column, and the warning that the csv's `Name` column is not the place.
   HOW_IT_WAS_BUILT gives the method in prose and points at research/44 §2 and research/45 §2.
2. **"How far can I trust it?"** Partly. The documents point at the pass's note and say what `Score` is not; they
   do not say, per pass, what error its note measured. That is correct for a class-N page (the notes own the
   numbers), but the stranger has to open a note per pass. A single table — pass, note, rule, measured error, the
   command — belongs in the plan's close (Task 11) or in a note, not in either document.
3. **"How do I add or fix one?"** Adding: answered (a proposals file, the applier, `--report-only` first, a hand
   name as `Pass=hand`). Fixing: answered only as "a finding for the controller, settled by a ruling and a holds
   line" — there is no documented mechanical route to retire an applied name, because the applier refuses to
   overwrite its own row.

## 6. Other things a stranger would trip on

- **A names file that does not resolve is silent.** `loadDisplayNames` logs `no names file …; output names come
  from the function map` at info level and the recomp succeeds with the old names (`ps2_recompiler.cpp:2037`).
  `names` is opened relative to the recompiler's working directory, not the toml's; Task 3b's open item (a
  `build_revision.sh --out <dir>` run does not find the relative path) is this trap. DEVELOPING now says to look
  for the `Loaded … display names` line; `build.sh recomp` does not check it.
- **The hooks name the same routines differently.** Of the 37 literal addresses in the runtime table's r0001
  column, 30 are function starts in the map, and 5 of those now carry a sidecar name the table's field does not
  mention (command F): `packTrace` is `zar_CZAR_Fetch`, `lod` is `zdb_CVisual_DrawLOD`, `dnasCheck` is
  `UIDNASAuthenticate`, `netbExDescriptorDma` is `libnetb_trans_data`, `dnasRsaBlock` is `RSADecryptBlock`. A reader
  of `game_overrides_socom2.cpp` who searches the generated code for `packTrace` finds nothing. D4 allows the
  comment to follow the name.
- **Readable names keep the demo's spellings**, so styles mix: `UIDNASAuthenticate` (a derived binding name),
  `zdb_CNode_…`, `anon_zanim_menu_OnGetTextFromUser`, `_printf` beside `kernel_cosf`. research/47 and S12-R14 are
  the rules; nothing in the output says so.
- **The sidecar's `Date` is the day of application**, not of the evidence; a row carried to r0004 keeps its
  r0001 evidence behind `Pass=carried:<pass>`.

## What this means for a task

| task | finding | what it changes |
|---|---|---|
| Task 3b (header wording) | `(identity Y)` reads as an alias; nothing in a generated file points at the sidecar; the address has three spellings | Emit `// Name source: recomp/socom2_names.csv row 0x%08x (map name Y)` instead of `(identity Y)`, the padded spelling included; update the `ps2xTest` assertion. A comment-only change: no identifier, extent or body moves, and the census's extents hash does not read the line |
| Task 3b (stubs) | The 133 named stub files carry no header at all | Emit the same name-source line on a stub file |
| Task 3b open item / `build.sh` | A names file that does not resolve is an info line and the build succeeds with the old names | Have `build.sh recomp` (and `build_revision.sh`) fail, or print loudly, when `recomp_run.log` lacks `Loaded … display names` while the toml sets `names`; and close the `--out <dir>` path |
| Task 8 (`toml-stub`) | 89 stub files still wear `FUN_`/`sub_` while their body names the handler; 111 of 125 named stubs equal the handler name, 14 differ by underscores | The pass names the 89; the underscore rule (S12-R14) is the one difference to expect |
| Task 11 (close) | A newcomer cannot see, per pass, what error was measured without opening each note | One table (pass, note, rule, measured error, command) in the Outcome or a note — not in HOW_IT_WAS_BUILT (class N) or DEVELOPING |
| A later sprint (D4) | `packTrace`, `lod`, `dnasCheck`, `netbExDescriptorDma`, `dnasRsaBlock` have sidecar names the runtime table does not mention | Add the sidecar name to each field's comment in `socom2_addresses.h` (a comment change, D4) |
| The applier | No route retires an applied name; a correction is a ruling plus a holds line plus a hand-removed row | Consider a `--retire <addr>` that removes a row only together with its holds line, so the one-writer rule survives corrections |
| Documents (done here) | DEVELOPING lacked the grep's padding, `&`/`+` in `Pass`, what `Score` is, and the silent-names-file trap | Written into "Names in the generated code" (Task 9) |
