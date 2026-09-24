# 51. Vtable coverage after 7c: the classes the RTTI walk cannot open, and what opens them

Date: 2026-09-24. Sprint 12 research wave, question 6 of the handoff §4
(`docs/superpowers/plans/2026-09-24-sprint-12-cloud-handoff.md`), the follow-up to the spec's Goal 3
(`docs/superpowers/specs/2026-09-24-sprint-12-the-readable-image-design.md`) and the groundwork in
`tools_py/research/symbols/README.md` ("7c: vtable anchors, the RTTI walk"). Read-only: two ELFs, two Ghidra tables,
Task 7's match file. No game was run, nothing under `recomp/` or `game/` was written.

**The one-line answer: the bare-name walk's three failure buckets are mostly an artefact of the lookup key, not of
the image. Keyed on the demo's own RTTI string (which is qualified: `zdb::CNode`, `std::ctype<char>`) and filtered by
the vtable layout, 211 of the 248 demo classes resolve to exactly one retail primary vtable, not 111. But the rule 2
of Goal 3, as written, names 2 slots over the 111 and 11 over all 211, because 71 of the 111 have no body-matched
fixed point at all and the runs it allows are mostly inherited (shared) bodies. Reading the vtable start as a fixed
point, which the plan's own Task 4 test already assumes, names 39 / 67; naming equal-count vtables whole names
83 / 169; the leave-one-out holdout is 37 right, 0 wrong. Rule 4 (constructors) as written never picks the class's constructor on the demo:
of the 21 classes where it fires, 19 get a destructor and 2 another function.**

Every number below names the command that produces it:

```
# A -- everything in this note (sections 1-7 and the table); about 6 s
python tools_py/research/symbols/vtable_coverage.py --r0004

# B -- A plus the per-class lists behind the counts, all 268 retail vtable class names, and each
#      constructor miss by demo name
python tools_py/research/symbols/vtable_coverage.py --list

# C, D -- the groundwork's numbers, reproduced unchanged before extending them
python tools_py/research/symbols/vtable_rtti.py
python tools_py/research/symbols/vtable_anchors.py
```

C reproduces the README's buckets (248 demo classes: one retail vtable 111, several 54, string but no RTTI
pointer 3, absent 66, template 14), 1,154 demo slots against 1,496 retail and 41 of 111 equal; D reproduces 248
objects, 221 with ≥ 2 function slots, 2,611 slots, 19 anchored, 7 located, 7 ambiguous, 49 retail slots. A's section 0 recomputes C's five buckets the same way and
gets the same counts, so every bucket below is the README's bucket. "The 111", "the 54", "the 66", "the 14", "the 3"
are those buckets throughout.

Inputs: `game/demo_scus_972_05/SCUS_972.05` (demo), `game/disc/socom2_game.elf` + `recomp/socom2_ghidra.csv`
(ours, r0001), `game/demo_symbol_matches.json` (the 987 pairs; "fixed point" uses the 828 non-prefix ones, as
`vtable_anchors.py` does), `game/demo_symbol_renames.csv` and `…_7b.csv` (for "already named"),
`game/overlays_r0004/socom2_game_r0004.elf` + `recomp/socom2_ghidra_r0004.csv` (the r0004 check).

## 0. Two layout facts the buckets hide

**The RTTI name string is the qualified C++ name.** The demo's `__RTTI__Q23zdb5CNode` points at `"zdb::CNode"`,
`__RTTI__Q23std8ctype<c>` at `"std::ctype<char>"`, `__RTTI__Q221@unnamed@zui_skb_cpp@12CBmpWithNode` at
`"@unnamed@zui_skb_cpp@::CBmpWithNode"`. `vtable_rtti.py` searches `"\0CNode\0"`, which a qualified string can never
match (a `:` precedes the bare name). 8 of the 248 demo vtables have a zero RTTI word (A §0; `CTurret`,
`CSaveModule` and six game-state classes: `PersistentGame`, `BriefingRoom`, their two `…Clone`s, `TransientGame`,
`RoomGame`), so for those the name comes from the mangling.

**A base class's RTTI object is pointed at by every derived class's RTTI object.** A Metrowerks RTTI object is two
words, `[name string, base list]`; the base list is `[base RTTI, offset]` pairs ending in zero. So "aligned words
pointing at the RTTI object" counts one real vtable plus one word per derived class. This is what fills the 54
(section 2). A secondary-base vtable is `[RTTI, negative this-offset, slots…]` (CZSealBody's offset differs between the two
builds; the demo keeps the secondary inside the same `__vt__` OBJECT, after the primary's slots).

## 1. The whole space: every retail vtable, counted by the layout

The census: an aligned word pointing at an RTTI object whose first word points at a NUL-preceded name string, then a
zero word (primary) or a small negative offset (secondary), then consecutive csv function starts (A §1).

| figure | value |
|---|---|
| retail vtables with ≥ 2 function slots | **266** (244 primary, 22 secondary), 246 class names, 247 RTTI objects, 3,558 slots |
| … plus 1-slot vtables inside the address spans the ≥ 2 set occupies (±0x100): 0x1d4ea0–0x1d5390, 0x404e10–0x4084f0, 0x669020–0x66a060 | 26 → **292 retail vtables** (266 primary, 26 secondary), 268 class names |
| 1-slot matches outside those spans (5 names, all in the code segment: `std::list<C2D *, …>`, `C2Dlist`, `zdb::tag_VIS_PARAMS`, `CEntityCtrl`, `CFileIO`) | 123 — not vtables (one function word, inside the code segment; what they are is not identified here); they are what made `CEntityCtrl` and `CFileIO` look ambiguous |
| the same pattern on the demo (≥ 1 slot) | 259 (238 primary, 21 secondary); 238 primaries sit on a `__vt__` symbol, the 10 missed have a zero RTTI word (8) or no function in the first slot (`CIO`: every slot a pure-virtual zero; `CUIVarManager`: the primary is empty and its secondary header follows at once) |
| retail vtables whose RTTI string **is** a demo `__vt__` class's own RTTI string | **234** (213 primary) over **213** demo classes (210 of the ≥ 2 set) — the most the demo's 248 could ever map to |
| retail class names with **no** demo counterpart (neither a demo `__vt__` nor a demo `__RTTI__` string) | **55 classes, 58 vtables, 703 slots** — Goal 3's ceiling on the retail side |
| r0004, the same ≥ 2 census | 269 vtables (246 primary), 248 names; every r0001 name is in r0004; r0004 adds `CZArchive` and `MCPopMessage` |

The largest of the 55 by slot count (A §1): `CSecureText` 38 (2 vtables), `SelectedSlot` 29, `CategorySlot` 29,
`CBmpWithNode` 29 (2), `CWeaponSlot` 28, `CVehicle` 27, then at 26 each `CLensFlareEntry`, `CMPTeammateNames`,
`@unnamed@hud_scorepopup_cpp@::CHudPopups`, `CMPInfoBox`, `CWhosTalking`, `CRadioIcon_Dynamic`, `CRadioIcon_Static`,
`SlotList`, `CHealthBar`, `CSpectatorInfo`, `CMsgEditor`; then `CRdrIO` 18,
`@unnamed@zui_2d_cpp@::CListItemWrappedTextTypeImpl` 18, `CAiSPlan` 18, `CAiSUseVehicle` 18, `CSoundBufferIO` 17,
`CLobbyFileIO` 15, `CZUniversInformationServer::CAcctDB` 14 (2), `CShutdownState` 10. These are SOCOM II's own
classes (the vehicle, the HUD's online widgets, the lobby's file I/O, the account database). One of the 55 is not new:
`CBmpWithNode` is the demo's `@unnamed@zui_skb_cpp@::CBmpWithNode` with the anonymous namespace dropped (section 2).

Two table facts a Task 4 implementer needs (A §1): 64 csv rows start inside the vtable spans (data taken for code —
`FUN_004062d0` is `CSealCtrlCopy`'s vtable, `FUN_00669210` is `CZSealBody`'s secondary vtable), and several more
start on RTTI objects and base lists in 0x3e1xxx–0x3fcxxx (section 2). No retail slot word points into a vtable span
(A §1: `retail slot words pointing into a vtable region: 0`), so "the slot is a csv function start" did not admit
data here — but it is a test on a table that contains data rows.

## 2. The 54 "several retail vtables"

What the 338 words pointing at the 54 classes' RTTI objects are (A §2):

| word | count |
|---|---|
| a word inside a derived class's RTTI base list | **261** |
| a primary vtable (≥ 2 slots) | 45 |
| a secondary vtable | 18 |
| a 1-slot primary vtable inside the spans | 6 |
| a 1-slot match outside the spans (section 1) | 3 |
| other (`CIO`'s all-pure-virtual vtable at 0x406520, `CUIVarManager`'s empty primary, three words in the RTTI area of `CBody`, `CEntity`, `CZWeapon`, which have two RTTI objects each) | 5 |

**The qualified name splits none of them.** Only 1 of the 54 is qualified in the demo (`CBmpWithNode`, above), and
there the qualified string is the one retail does *not* carry. Bare-name collisions across namespaces are not what
fills the bucket; base lists are.

How the 54 split once the lookup is the demo's RTTI string and the layout filter (A §2):

| split | classes |
|---|---|
| the layout filter alone leaves one primary vtable | **34** |
| one primary + one secondary, the demo has the same pair → primary to primary, secondary to secondary by the header word | **13** |
| one primary + one secondary, the demo has the primary only (`CRadioStrip`, `CHandlerButton`, `C2DButton`: SOCOM II added a second base) → primary to primary | **3** |
| `CBmpWithNode`: the qualified string is absent; the bare string resolves to a primary + secondary pair | 1 (opens by the bare name, not the qualified one) |
| no retail vtable the layout accepts: `CIO` (every slot a pure-virtual zero), `CSaveModule` (only base-list words point at its RTTI) | 2 |
| `CUIVarManager`: the primary has no slot of its own, so only its 8-slot secondary counts (the demo's is also 8) | 1 |

So **split by qualified name 0 / by the layout filter 34 / by pair shape 16 (+1 via the bare name) / still unopenable
3** (`CIO`, `CSaveModule`, `CUIVarManager`, the last openable by its secondary alone). The pair needs no body
evidence: the header word (0 or a negative offset) says which is which. Where body-matched slots exist they agree:
of the 29 demo parts (primary or secondary) of the 16, 5 have their body-matched slots in the same-shape retail
vtable, 0 in the other one, 4 have a body-matched slot whose retail partner sits in neither of the class's vtables
(an override in SOCOM II: `CZSealBody` secondary, `C2DClock`, `CRenderableString`, `C2DCounter`), 20 have none (A §2).

## 3. The 14 templates

All 14 are MSL's `std::` streams and facets (`basic_istream`, `basic_ios`, `basic_ostream`, `basic_streambuf`,
`basic_filebuf`, `codecvt`, `ctype`, each for `char` and `wchar_t`) (A §3).

- **The bare template name is not a string in retail**: `"\0basic_istream\0"` and the other six occur 0 times. The RTTI
  string is the full demangled instantiation (`"std::basic_istream<wchar_t, std::char_traits<wchar_t>>"`).
- Each bare name (`std::basic_istream<` as a prefix) names exactly 2 retail classes (the two instantiations), 2 primary
  vtables.
- **Body-matched slots tell the instantiation for 2 of 14** (`basic_filebuf<char>` 2 anchors, `ctype<char>` 4); the
  other 12 have no body-matched slot.
- **The full RTTI string opens 14 of 14**: 10 to one primary, 4 (the two `istream`/`ostream` pairs) to a primary +
  secondary. The "template" bucket was the script skipping them, not a property of the image.

## 4. The 66 absent

| of the 66 | count (A §4) |
|---|---|
| resolved by the demo's qualified RTTI string to one primary vtable (all 33 are `Q`-qualified: 6 `std::`, `zar::CZAR`, 16 `zdb::`, 2 `Particle::`, 8 anonymous-namespace) | **33** |
| resolved to two primaries: `zdb::CNodeEx` — two RTTI objects (0x3e1e40, 0x65c220), two 3-slot vtables (0x406000, 0x669240) with different slots, 0 body-matched slots | 1 (refused) |
| **still absent** | **32** |

The 32: `C2DOrderItem`, `CRestrainedTravel`, `CStealthTravel`, `CBasicTravel`, `CAiSRestrained`, `CAiSCorpse`,
`C2DFont`, `PersistentGameClone`, `BriefingRoomClone`, `BriefingRoom`, `PersistentGame`, `CTickerTapeText`,
`CCycleButton`, `CycleItem`, `CCycleButtonSpec`, `CTickerSpec`, `CStickAccelerationTuner`, `CZStaticRadioBitmap`,
`CZDynamicRadioBitmap`, `CLensFlareSaturate`, `CTeamMateNames`, and eleven `CSM*`/`CCnfStateMachine` (the demo's
network-configuration state machine) (B §4). For them (A §4):

- **The anchor route** (`vtable_anchors.py`'s: ≥ 2 non-prefix body-matched slots, one base at the same spacing):
  1 has ≥ 2 anchors (`CycleItem`, ambiguous), **0 located**. (An earlier draft of the script read past the end of
  each `__vt__` OBJECT and "located" 12 `CSM*` vtables that were their neighbours; the count is from the fixed read.)
- **r0004**: the name string is present in r0004 for **0 of 32**; r0004's vtable names are a superset of r0001's
  (section 1). Nothing r0001 dropped comes back in r0004.
- **Task 7 pairs**: 28 have demo methods (by the `__<len><Name>` mangling) and **not one of them paired**; 1 has a
  paired method (`BriefingRoomClone`, 1 of 4); 3 have no demo method under their own name (`CSMSetInit`,
  `CSMAddCombo`, `CSMAddIFC`, whose slots are all inherited). By the brief's criterion **28 are classes SOCOM II
  dropped**, and the remaining 4 are not evidence against that.
- Some of the 32 have name-similar classes among section 1's 55 (`CZStaticRadioBitmap` / `CRadioIcon_Static`,
  `CZDynamicRadioBitmap` / `CRadioIcon_Dynamic`, `CTeamMateNames` / `CMPTeammateNames`). Nothing measured here connects
  them (none of the 32 has a located vtable), so a rename is a guess this note does not make.

## 5. The 3 "string but no RTTI pointer"

The bare strings exist because each class's `what()` returns its own name; the RTTI object points at the qualified
string instead (A §5):

- `"bad_cast"` at 0x1cf928: no data word points at it; formed by lui+addiu in one function, 0x1824c0, Task 7's
  `what__Q23std8bad_castCFv`. `"std::bad_cast"` resolves to one primary vtable.
- `"exception"` at 0x1cf938: no data word; formed in 0x1824d0, `what__Q23std9exceptionCFv`. `"std::exception"` → one.
- `"bad_exception"` at 0x1cfad0: no data word; formed in 0x184110, `what__Q23std13bad_exceptionCFv`.
  `"std::bad_exception"` → one.

## 6. Fixed points, and what Goal 3's rule 2 actually names

**Where the fixed points are, over the 111** (A §6):

| figure | value |
|---|---|
| classes with 0 body-matched fixed points | **71** |
| with ≥ 1 | **40** |
| with ≥ 2 | **5** |
| fixed points in all, conflicting (non-monotonic) | 45, 0 |
| demo slot words paired by Task 7 (non-prefix / with prefix) | 48 / 58 of 1,154 |
| retail slot words that are a shared body (the target is in ≥ 2 retail vtables) | 991 of 1,496 (661 distinct targets) |
| retail slot words already named (hand-named csv row, a Task 7 pair, a 7b proposal) | 56 of 1,496 |
| equal-count classes (the 41): with ≥ 1 fixed point / with none | 13 / 28; their 14 fixed points all at the same index both sides |

**The rule in four readings** (A §6; "proposed" = distinct retail rows a run would name; "named" = after rule 3's
refusals: a collision, an already-named row, a shared body, a body under 64 bytes, a size ratio under 0.50):

| reading, the 111 | slots in equal runs | proposed | shared body | < 64 B | ratio < 0.50 | already named | collision | **named** | holdout (reached / right / wrong) |
|---|---|---|---|---|---|---|---|---|---|
| strict — rule 2 as written: between fixed points and after the last | 75 | 29 | 20 | 7 | 0 | 0 | 0 | **2** | 4 / 4 / 0 |
| start — the vtable start is a fixed point (the run before the first counts when equal) | 123 | 76 | 22 | 7 | 5 | 2 | 1 | **39** | 17 / 17 / 0 |
| whole — start, plus the 28 equal-count vtables with no fixed point named whole | 205 | 153 | 30 | 25 | 10 | 4 | 1 | **83** | 17 / 17 / 0 |
| whole + a shared body kept when ≥ 2 vtables propose it, all with one name | 205 | 153 | 16 | 35 | 10 | 4 | 1 | **87** | 17 / 17 / 0 |

The holdout drops each fixed point in turn, re-derives it by position from the others, and compares (the Goal 3
code bar's shape). A second, independent check: every proposal that lands on a row Task 7 already paired carries
the same demo name as that pair — 4 of 4 in "whole" over the 111, 16 of 16 over everything opened, 0 disagree (A §6,
`check: Task 7 row, same name`). A fixed point is never itself proposed, so these agreements are out of sample.

**So the number the plan's Task 4 should quote as the 111's expected yield is 2 under the rule as written, 39 under
the reading its own Step 1 test uses** ("a body-matched fixed point at slot 1 … → slots 0 and 2 proposed" names
slot 0, before the first fixed point). The reason is structural: 71 of 111 vtables have no fixed point, and after
the first fixed point most equal runs are inherited slots, which rule 3 refuses as shared bodies (20 of 29).

## 7. Constructors

Pattern: lui + addiu/ori forming a located vtable address (the pair at most 8 instructions apart), then a sw of the
formed register (A §7). The demo is the truth: its `__ct__`/`__dt__` symbols name every function the pattern finds.

**Rule 4 as written** (sw to offset 0 within 8 instructions; propose when exactly one function):

| over | ours: exactly one / several / none | the demo, same classes, its own vtable: exactly one / several / none | the demo's "exactly one" is |
|---|---|---|---|
| the 111 | 4 / 78 / 29 | 12 / 72 / 27 | **10 a destructor, 2 something else, 0 the class's constructor** |
| all 211 resolved (sections 2–5) | 12 / 122 / 77 | 21 / 114 / 76 | **19 destructors, 2 other, 0 constructors**; on ours the one "exactly one" that is a Task 7 row is a `__dt__` |

Why (A §7): Metrowerks destructors re-store the vtable (every class with a non-trivial destructor has ≥ 2 storing
functions, so "exactly one" selects classes whose constructor was inlined away — and leaves the destructor); the
vptr is often not at offset 0 (the demo's stores by offset: 0 → 612, 12 → 214, 96 → 25, 28 → 20, 128 → 13, of
1,152); and constructors form the address early. Of the 111's 46 demo `__ct__` symbols, 23 contain rule 4's pattern
for their own vtable, 44 contain some store of it (within 32, any offset); over the 211: 50 and 102 of 107.

**Two refinements, scored the same way** (A §7). Destructors are recognisable: in the demo the most frequent callee
of the 470 vtable-storing functions is `__dl__FPv` (238 of them); in ours the most frequent callee of the 540 is
0x180ad0 (279) — operator delete by that analogy only, it has no pair.

| variant, all 211 | ours: exactly one | demo: exactly one → own `__ct__` / other | ours: exactly one that is a Task 7 row → own `__ct__` / other |
|---|---|---|---|
| A — rule 4 as written | 12 | **0** / 21 | 0 / 1 |
| B — within 32, any offset, operator-delete callers dropped, the last vtable stored is the owner | 101 | 53 / 51 (inlined constructors in factories, `Copy`, `__sinit_*`, `CreateDisplayObj`) | 4 / 1 |
| C — B, counting only stores through `this` (a0 or a register a0 was moved into) | 87 | **22 / 1** (`CMemCardIO` → `__ct__8CMemCardFv`) | **6 / 0** |

Variant C is the only one with a usable precision (demo 22 of 23, ours 6 of 6), but its demo recall is low (23 of
211) and ours returns 87 — 3.8 times the demo's count — so the demo's precision does not transfer on this evidence
alone. For the 111 alone: C gives ours 45 exactly-one, demo 8 own constructors of 9. What would settle it: a holdout of
C against more retail truth than 6 rows (the Task 7c file's own pairs, or BinDiff's).

## The table: what opens what

Cumulative, lever by lever, marginal slots named under each reading of rule 2 (A §6 `cumulative` and A §T). "Classes"
is demo classes; the pair lever adds 29 vtables for 16 classes, templates 18 for 14.

| lever | classes opened | slots named: strict / start / whole / whole+shared | cost |
|---|---|---|---|
| bare-name RTTI walk (today's 111) | 111 | 2 / 39 / 83 / 87 | exists (`vtable_rtti.py`) |
| layout filter on the "several" (header word 0 or negative, slots are function starts; base-list words dropped) | 34 | 2 / 12 / 21 / 22 | one predicate in `resolve_vtables` |
| primary/secondary pair by the header word | 16 | 1 / 1 / 5 / 6 | read the demo's secondary header inside its `__vt__` OBJECT |
| the demo's own RTTI string as the key (qualified names; replaces the bare name) | 33 | 1 / 4 / 18 / 25 | read the demo's `__RTTI__` object instead of parsing the mangling; also fixes the next two |
| … the same key for the 3 "no RTTI pointer" | 3 | 0 / 3 / 3 / 3 | none beyond the above |
| … the same key for the 14 templates (full instantiation string) | 14 | 5 / 8 / 39 / 41 | none beyond the above |
| **all levers together** | **211** | **11 / 67 / 169 / 184** | holdout 12/12, 37/37, 37/37, 37/37 right; Task 7 name checks 16 of 16 agree |
| body-matched slots alone for templates | 2 of 14 | (inside the row above) | — |
| anchors for the 32 still absent | 0 | 0 | — |
| r0004's strings for the 32 | 0 | 0 | — |
| constructors, rule 4 as written | 12 exactly-one on ours | — | demo precision 0 of 21: do not ship |
| constructors, variant C | 87 exactly-one on ours | — | demo 22 of 23, ours 6 of 6; recall unmeasured on retail |

Not openable by anything measured here: the 32 absent (28 with no Task 7 pair at all), `CIO`, `CSaveModule`,
`zdb::CNodeEx` (two vtables, no body evidence), and on the retail side the 55 new classes / 703 slots, which no
demo name describes.

## What this means for a task

| task | finding | what it changes |
|---|---|---|
| Task 4 (7c), rule 1 | The lookup key must be the demo's own RTTI string (qualified, with template arguments), and a candidate must pass the layout (word 1 zero or a small negative offset, then function starts); 261 of the 54's 338 "vtables" are base-list words. With both, 211 classes resolve to one primary, not 111; the qualified `Q2` name splits 0 of the 54 and opens 33 of the 66 | `resolve_vtables` reads `__RTTI__` → string in the demo and filters by layout; the "several" bucket is split by the header word, not by the `Q2` name; templates are not refused |
| Task 4 (7c), rule 2 | As written it names 2 slots on the 111 and 11 on all 211; the plan's own Step 1 test (slot 0 before a fixed point at slot 1) assumes the vtable start is a fixed point, which names 39 / 67; holdout 0 wrong in every reading | a ruling on which reading ships; the spec's "expected yield" line becomes 39 (111) / 67 (211) for the start reading, or 83 / 169 if equal-count vtables with no fixed point are named whole (evidence: 29 of 29 fixed points in equal-count vtables sit at the same index; no in-vtable check possible for the 82 with none) |
| Task 4 (7c), rule 3 | Shared bodies are the largest refusal (20 of 29 strict proposals; 991 of the 111's 1,496 slot words); keeping a shared body when ≥ 2 vtables name it alike adds 15 over all 211 (whole reading) | optional amendment; small |
| Task 4 (7c), rule 4 | Constructors as written: the unique storing function is a destructor 19 times, never the constructor (demo, 0 of 21); ours' one checkable case is a `__dt__` | rule 4 is not shipped as written; variant C (drop operator-delete callers, `this` stores, last vtable wins) is the candidate, with its own holdout before it names anything |
| Task 4 (7c), `slot_count` | Pure-virtual slots are zero words and stop the count (`CIO`; the demo's `CSaveModule` after its first slot), and an empty primary is followed at once by its secondary header (`CUIVarManager`); 64 csv rows start inside vtable spans (data) | the synthetic tests add a pure-virtual zero slot; the "function start" test is not proof a word is code |
| research Q10 (class inventory) | 55 retail classes / 58 vtables / 703 slots have no demo counterpart (CVehicle, CSecureText, the online HUD widgets, `CZUniversInformationServer::CAcctDB`, …) | these are the named-by-nothing classes; their class names are free (RTTI) even where their methods are not |
| research Q5 / Q11 (voice, SASE) | None of the 268 retail vtable class names mentions SASE (B §1 prints them all) | the vtable route will not name the codec: no SASE class has a vtable with RTTI |
| r0004 carry | The census generalises (269 vtables, a strict superset of r0001's names) | a 7c file for r0004 can be derived by the same code rather than carried |
