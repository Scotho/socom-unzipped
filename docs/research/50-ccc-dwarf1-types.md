# 50. The SOCOM 1 demo's DWARF1 types through ccc, and which field offsets can be named

Date: 2026-09-24. Sprint 12 research wave, question 5 of the cloud handoff §4
(`docs/superpowers/plans/2026-09-24-sprint-12-cloud-handoff.md`); the spec's Goal 5
(`docs/superpowers/specs/2026-09-24-sprint-12-the-readable-image-design.md`). This is a read-only note. It reads
three ELFs, two Ghidra tables and research/44's match file. No game was run and no tracked file changed apart from
this note and its script. The tool was cloned and built outside the repository, under `/home/user/tools/`. Only
names, addresses, offsets, counts, type names and field names appear here. A struct layout (field, offset, type)
is a fact about the source; no bytes and no instruction words are quoted.

**The one-line answer.** ccc reads the whole `.debug`: 116,691 DIEs, the same count as an independent DWARF1 walk.
What the section holds is the FTS application layer, the camera library, the C++ runtime and the LPC-10 codec. That
is 80 translation units, 879 functions (9.1 % of the demo's 9,703), and **536 class layouts**, `CZSealBody`'s
0x1140 bytes among them. The engine libraries, where the matched functions live, are not described: only **52 of
research/44's 987** matched functions have a compile unit. Against SOCOM II's own code, **a SOCOM 1 offset is
almost never the SOCOM II offset** for the big engine classes: the actor's constructor moves all 133 of the demo
fields it stores. The SOCOM 1 *names*, however, carry across once the shift has been measured. **Twelve offsets the
tools use can be named safely**: `root_node` 0x2E8 = `CZSealBody::m_root` (SOCOM 1 0x26C), angular velocity 0x48 =
`CEntity::m_velR.y` (0x3C), and `NG_FINGERPRINT` 0x118 = `CZNetGame::m_pos_smooth` (0xE0). Next, the six CZNetGame
valve slots the tools read, each `+4` from its SOCOM 1 name. The last three are unchanged: the scene node's flags
word 0x5C, its byte 0x5D and its visual count 0x88. A thirteenth, health 0x1044 = `CZSealBody::m_health`, rests on
one twin plus research/19's semantics. `actor_pos` 0x1C, `move_scale` 0x1368, the alive byte 0xF7A and the R6 stamp
0x420 have **no SOCOM 1 name**: either the field is new in SOCOM II, or the naive same-offset name is contradicted.
Every offset the ladder reads on r0001 only (all below 0x1334) keeps its value in r0004's twins. The one exception
is five uses of the team word 0xc8 (§4a).

The commands. `ccc` is at `/home/user/tools/ccc` (main, `c025ca9`, `git -C /home/user/tools/ccc log -1`), built
with `cmake -B build -DCMAKE_BUILD_TYPE=Release && cmake --build build`. The script finds it through `$CCC_BIN`,
which defaults to `/home/user/tools/ccc/build/stdump`.

```
# T -- ccc itself on the demo (T0, T1 main; T2 the dwarf_types branch at 8207424, a worktree built the same
#      way in /home/user/tools/ccc_dwarf_types -- `git log main ^origin/dwarf_types` 42 commits, the reverse 1;
#      T3 the raw DIE dump every section below reads)
T0: /home/user/tools/ccc/build/stdump identify game/demo_scus_972_05/SCUS_972.05
T1: /home/user/tools/ccc/build/stdump types --section .debug dwarf game/demo_scus_972_05/SCUS_972.05 \
      | grep -o 'CCC_ERROR("[^"]*")' | sort | uniq -c
T2: /home/user/tools/ccc_dwarf_types/build/stdump types --section .debug dwarf game/demo_scus_972_05/SCUS_972.05 \
      | grep -o 'CCC_ERROR("[^"]*")' | sort | uniq -c        (and grep -c '^struct ', grep -c '// 0x0$' on it)
T3: /home/user/tools/ccc/build/stdump symbols --section .debug dwarf game/demo_scus_972_05/SCUS_972.05

# A-F -- tools_py/research/symbols/dwarf_types.py, one section each (all six with no argument)
A: python tools_py/research/symbols/dwarf_types.py census --selfcheck
B: python tools_py/research/symbols/dwarf_types.py types --write-types
C: python tools_py/research/symbols/dwarf_types.py units
D: python tools_py/research/symbols/dwarf_types.py offsets
E: python tools_py/research/symbols/dwarf_types.py age
F: python tools_py/research/symbols/dwarf_types.py missing
```

A, B, C and F take a few seconds each. D takes about four minutes and E under one, because both twin every
member function of the classes they study; all six together (no argument) take about three minutes, the
twin finder's index being shared. The only output file is `game/demo_types.txt` (B), which is git-ignored.

## 1. The tool, and what the `.debug` holds

**ccc's type commands cannot read this file, but its raw dump can.** ccc main's `identify` (T0) names two symbol
tables in the demo, `.debug` and `.symtab`. T1, `stdump types`, prints **no** type definition. It prints 16,652
`TAG_class_type support not yet implemented.`, 2,812 `Fundamental type support not yet implemented.`, 1,227 enum,
474 structure and 449 subroutine-type errors. The `dwarf_types` branch (T2; one commit ahead of its merge base with
main, which is 42 commits further on, "Add support for importing DWARF classes and fundamental types") prints all
14,939 classes. Every one of them has size `0x0` and no member offsets, and the output carries 27,742 `TODO: Type
name.` and 424 `TODO: Circular reference.`. Neither command gives a layout. T3, `stdump symbols --section .debug
dwarf`, is ccc's own DIE printer. It is **complete**: one line per DIE with its tag, nesting and attributes,
including `byte_size`, every member's `location={const(N),add}`, `bit_offset`/`bit_size` and type references. The
script reads that dump and builds the layouts itself (§2). A's `--selfcheck` walks the section a second time with
the script's own minimal DWARF 1.1 reader. That reader follows the 4-byte length, the 2-byte tag and the
attributes, using the form in each attribute code's low nibble. It gets **116,691 DIEs, with no difference from ccc
by tag**. The first compile unit is `C:\usr\local\sce_2.5.1\EE\lib\crt0.s` (A).

Three ccc caveats:

* Metrowerks' vendor attributes, codes 0x201, 0x204-0x217 and 0x230, are printed as `unknown(...)` (A
  counts them by code). They sit on 654 subprogram DIEs, 629 global and 25 static (T3 piped through
  `grep 'unknown('`). No layout depends on them.
* An enum's constant is right only in the enum's own `byte_size`, and the rest of each 4-byte slot is junk.
  T3 prints the four constants of the 1-byte `_zvid_mode` (`D_MODE_NTSC` … `D_MODE_NUM`) as four consecutive
  ten-digit numbers: the low byte counts 0..3 and is the enumerator, and the upper three bytes are the same junk.
* Metrowerks emits **no `typedef`**: 0 DIEs (A).

**The census (A):**

| what | count |
|---|---|
| `.debug` / `.line` | 5,093,034 / 194,940 bytes |
| DIEs | 116,691: member 77,784, class_type 14,939, inheritance 9,028, array_type 4,623, local_variable 2,656, formal_parameter 2,203, enumeration_type 1,189, compile_unit 959, lexical_block 879, global_subroutine 853, global_variable 689, structure_type 474, subroutine_type 389, subroutine 26 |
| compile-unit DIEs | **959 = 80 translation units + 879 per-function CUs.** A unit opens with one CU that has no pc range and holds the unit's types and globals (79 of them), then has one CU per function. The assembler's `crt0.s` is the 80th |
| distinct CU names | **114, of which 95 with a source extension**: the same 114 path strings and 95 source files `debug_paths.py` counts by string search. The other 19 are MSL's extension-less C++ headers (`vector`, `fstream`, `streambuf`, …) |
| per-function CUs named after their own unit / after a header | 573 / 306. The 306 are inlines emitted into the unit that used them: MSL headers (`fstream` 34, `vector` 31 + 10, `streambuf` 28, …) and engine headers (`zseal.h` 17, `ztwod.h` 14, `FTS\hud.h` 12, `zgame.h` 9, `zfts.h` 4, `zmath_matrix.h` 3, `zentity.h` 2, `znode.h` 2, …) |
| units by directory | `Z:\dev\Apps\FTS` 35, `C:\dev\libpttclient` 35 (34 LPC-10 `.c` + `libpttclient.cpp`), `Z:\dev\gamez\zcamera` 4, MSL `Src` 3, `crt0.s`, `gcc_wrapper.c`, `libpttserver.cpp` |
| subprograms | 879 (853 global + 26 static), all with a pc range, one per per-function CU; **879 of the demo's 9,703 `.symtab` functions (9.1 %)** start a subprogram DIE |
| locals / parameters / lexical blocks / globals | 2,656 / 2,203 / 879 / 689 |
| class_type DIEs | 14,939. Every unit repeats the classes it includes, so this is not a count of classes (§2) |
| structure_type | 474, all anonymous (`@anonN`) records with no members: the RTTI and vtable objects' types |

The brief expected about 95 compile units, from `debug_paths.py`'s 95 source files. The 95 is the count of
source-file *names*. The units are 80, and the
compile-unit DIEs are 959. The **`gamez` engine directories (zseal, zentity, znode, zmath…) have no unit of
their own**. They appear only as the headers of inlines. So the `.debug` describes the FTS game layer, the
camera, the C++ runtime and the voice codec, and says nothing about the engine libraries' own functions. Their
*classes*, though, are fully described wherever an FTS unit includes their header (§2).

## 2. The types

**B:** 14,939 class DIEs reduce to **514 names and 566 distinct layouts, of which 536 are complete** (byte size
above zero) under 507 names. Seven names are only ever declared. Eighteen names have more than one complete layout.
Thirteen of them are MSL templates, because the DWARF names an instance by its bare name, so `vector`,
`compressed_pair`, `node`, `pair`, … each cover several instances; one more is the anonymous `@class`. The other
four are `AI_PARAMS` (three layouts: 0xc, 0x24, 0x3c), `SequenceEntry`, `entry` and newlib's `_reent` (0x2f0 and
0x2ec). A consumer has to pick the layout by unit or by size (B). **The whole list, with every field flattened
through the bases, is in `game/demo_types.txt`: 536 layouts, 6,354 lines** (B, `--write-types`; git-ignored).

The 40 largest by own member count (B; size in bytes; "flat" counts through the base classes):

| class | size | own | flat | bases |
|---|---|---|---|---|
| **CZSealBody** | 0x1140 | 255 | 301 | CEntity, CBody |
| CharacterDynamics | 0x1bc | 99 | 99 | - |
| CSealCtrl | 0x240 | 82 | 84 | CEntityCtrl |
| CSealCtrlAi | 0x5d0 | 77 | 161 | CSealCtrl |
| CZKit | 0x87c | 76 | 76 | - |
| **CZNetGame** | 0xf8 | 64 | 64 | - |
| CHUD | 0x14960 | 60 | 60 | - |
| Source | 0x134 | 55 | 55 | - |
| **CMission** | 0x670 | 52 | 57 | CSaveModule |
| CAppCamera | 0xd4 | 47 | 47 | - |
| BitmapReticule | 0x34c0 | 46 | 57 | C2D |
| OrdersMenu | 0x350 | 45 | 45 | - |
| CInGameWeaponSel | 0x1160 | 45 | 56 | C2D |
| lpc10_encoder_state | 0x2544 | 44 | 44 | - |
| CWeaponSel | 0xd00 | 42 | 53 | C2D |
| CZProjectile | 0xa8 | 38 | 38 | - |
| CZWeapon | 0xb0 | 38 | 38 | - |
| **CZNetwork** | 0x1264 | 37 | 37 | - |
| CPad | 0x194 | 37 | 37 | - |
| **CCamera** | 0x520 | 35 | 113 | CNode, tag_CAMERA_PARAMS |
| lpc10_decoder_state | 0xc00 | 35 | 35 | - |
| **CEntity** | 0x110 | 34 | 34 | - |
| CPipe | 0x694 | 34 | 34 | - |
| CWorld | 0x6be0 | 33 | 86 | CNode |
| CGrid | 0x651c | 32 | 36 | tag_GRID_PARAMS |
| CZNewHudMap | 0xeb0 | 31 | 42 | C2D |
| tag_NODE_PARAMS | 0x60 | 30 | 30 | - |
| CZAnimMain | 0x1c4 | 30 | 35 | _zanim_main_params |
| C2DMessage_Q | 0x180 | 27 | 38 | C2D |
| _options | 0x1b | 27 | 27 | - |
| _zvid_public | 0x80 | 26 | 26 | - |
| CWind | 0x68 | 26 | 26 | - |
| CZAnim | 0x60 | 25 | 46 | _zanim_anim_params |
| tag_CAMERA_PARAMS | 0x90 | 25 | 25 | - |
| sceGifTag | 0x10 | 24 | 24 | - |
| C2DString | 0x88 | 24 | 35 | C2D |
| **CNode** | 0xc0 | 23 | 53 | tag_NODE_PARAMS |
| CAiPath | 0x9c | 23 | 23 | - |
| CSealUnit | 0xa4 | 23 | 23 | - |
| CZNetVoice | 0x48 | 23 | 23 | - |

The classes the project names by hand, and every type name matching `Chat|Lobby|GameList|Net|Medius|Msg|Packet`
(B):

| class | SOCOM 1 layout |
|---|---|
| CZSealBody (the actor, research/61 §3) | 0x1140; CEntity at 0, CBody at 0x110 |
| CEntity / CBody | 0x110 / 0x48 |
| CMission | 0x670 |
| CPnt3D / CQuat / CMatrix | 0xc / 0x10 / 0x40 |
| CZNetwork / CZNetGame / CZNetVoice / CNetClock | 0x1264 / 0xf8 / 0x48 / 0x20 |
| CZOnlineLobby | **0x98** (10 members) |
| CZAnimMain, CHUD, CAiMap, CSealCtrl, CSealCtrlAi, CZKit, CGame, COurGame, CCamera, CAppCamera | 0x1c4, 0x14960, 0x12c, 0x240, 0x5d0, 0x87c, 0x7c, 0x210, 0x520, 0xd4 |
| MultiplayerMsg / CMultiplayerMsgVec / NetBandwidthInfo / NetClientMetric / ZAnimNetworkPacket | 0x14 / 0xc / 0x20 / 0x8 / 0x8 |
| **CPacket, CNetCnf** | **no layout**: neither name has a class DIE |

No type is named for chat, a game list or Medius. `CZNetGame` carries `m_uiv_ChatList` (a `CUIVariable*`),
and that is the demo's whole chat surface in `.debug`.

## 3. Functions to units: what the linker grouped

**C:** of the 987 pairs, **52 fall inside a per-function CU's pc range, from 21 units**. The top 15 (matched,
of which body-matched):

| unit | matched | body |
|---|---|---|
| MSL `Src\iostream.cpp` | 9 | 3 |
| MSL `Src\locale.cpp` | 5 | 4 |
| `gamez\zcamera\zcam_main.cpp` | 5 | 4 |
| `FTS\st_exit.cpp` | 4 | 4 |
| `FTS\hud_main.cpp` | 4 | 2 |
| `FTS\hud_fader.cpp` | 4 | 4 |
| `FTS\hud_playermapitem.cpp` | 3 | 3 |
| `cw301\PS2 Support\gcc_wrapper.c` | 2 | 2 |
| MSL `Src\ios.cpp` | 2 | 1 |
| `FTS\hud_letterbox.cpp` | 2 | 2 |
| `FTS\hud_linemap.cpp` | 2 | 1 |
| `FTS\main.cpp`, `orders.cpp`, `st_core.cpp`, `st_menu.cpp` | 1 each | 1, 1, 1, 0 |

Thirteen of the 52 are header inlines (their own CU names a header).

The other 935 have no unit, and they are not at the edges of the image. The pc ranges span
0x140460-0x422268, and 908 of the 935 sit inside that span, between units. Only 3 sit between two functions of
the same unit, and 24 sit outside the span (C). **The engine objects were linked without debug information
and interleaved with the FTS objects that have it.** So the "what the linker actually grouped" fact research/44
§1 asked for exists for 52 functions. For those 52, research/44 §5's class clustering and the units agree. Each
class's matched members sit in one unit (`CCamera` → `zcam_main.cpp` 5, `CZPlayerMapItem` →
`hud_playermapitem.cpp` 3, `CFlashFX`/`CFader` → `hud_fader.cpp`, `CHUD` → `hud_main.cpp`). The one exception
is `ios_base`, split `ios.cpp` 2 / `iostream.cpp` 1 (C). For the engine classes behind research/44's headline
matches (`CZSealBody`, `CMission`, `CZAnimMain`, `CZNetwork`), **the `.debug` has no unit to offer**: none of
their matched members has a compile unit. The class-name clustering remains the only grouping there is.

## 4. The offsets the tools use, against SOCOM II's own access pattern (the table Goal 5 consumes)

**The method (D).** The candidate for an offset is the demo field at that offset in the class research/61 §3
names. The field is looked up through the base classes and resolved into nested members (`deep_name`). The
evidence about SOCOM II comes from four sources:

1. **Forward twins.** Every demo member function of the class is paired with an r0001 function: research/44's
   pair when there is one, else a **twin finder**. The finder does an opcode-histogram prefilter, then scores
   the instruction streams with every immediate and displacement removed (difflib ratio). It accepts at ratio
   ≥ 0.60 and a margin ≥ 0.10 over the runner-up. The two bodies are aligned instruction for instruction.
   Wherever an aligned load or store is based on the `this` register on both sides, it gives a SOCOM 1 → SOCOM II
   displacement pair. `this` is followed from `$a0` through register copies and through its spill to the stack.
   The demo's zseal code keeps `this` on the stack and reloads it for each access; r0001 keeps it in `$s0`.
2. **The actor's constructor.** Demo `__ct__10CZSealBodyFPQ23zdb5CNodeP14CCharacterType` against r0001
   `FUN_00553ea0` (the constructor KNOWN §4 names). The instruction streams do not align (unoptimised against
   optimised code). So the two ordered sequences of `this`-relative stores and member-address computations are
   aligned instead: **271 pairs, ratio 0.747** (D). This source also fixes r0001's `CBody` base at **0x170**
   (SOCOM 1: 0x110), from the secondary-vtable store.
3. **Reverse twins.** Each r0001 function that uses the displacement on a `this` register is twinned back into
   the demo, and the demo displacement at the aligned instruction is read off. It counts only when the demo twin
   is a member of the class.
4. **The neighbourhood.** Two checks here. First, the demo fields within 0x20 of the candidate: do they share
   its shift? Second, which demo fields the map places within 0x10 of the r0001 offset.

The r0004 column follows every r0001 use of the displacement on a `this` register into r0004. It uses
`game/r0004/match.json` first, and an accepted twin where match.json leaves a function unresolved, as it does
for the `move_scale` functions. This is the `guest_addresses.py` method. For a small displacement (0x1c, 0x48,
0x70, …) the count includes other classes' uses of the same number; for 0x2e8 and above it is effectively the
actor's.

**The twin finder's false-pair rate** is measured against research/44's pairs as truth (E). On bodies of 16
instructions or more, **417 of 418 accepted are right on the body-matched pairs**, and **116 of 117 on the
prefix pairs**, which are the edited bodies this method is for. The finder does not enforce one-to-one, so two
demo functions can take the same r0001 twin. `SetHalfVerticalFOVRadians` (ratio 0.69) and
`SetHalfHorizontalFOVRadians` (0.80) both take 0x2913f0 (D's CCamera listing), and the weaker of the two
supplies the camera's −4 readings. Within one function, an ordered run of identical zero-stores can also pair
the wrong members, as it does in CZNetGame's `Initialize`. That is why one function alone never confirms an
offset. **The verdict rule (D):**

* *Confirmed* or *shifted by N*: two twin functions agree, or at least half of the ≥ 2 demo neighbours share
  the shift.
* *Single-twin candidate*: one function only, with its neighbours not agreeing.
* *Contradicted*: the demo field at the same offset is seen at a different r0001 offset.
* *Unknown*: no aligned use.

### 4a. The actor, `CZSealBody` (r0001 vtable 0x6691a0)

| r0001 offset (tool) | the demo field at the same offset | SOCOM 1 field that aligns with it (offset) | r0001 evidence (D) | r0004 (D) | verdict |
|---|---|---|---|---|---|
| **0x1c** / 0x20 / 0x24 `actor_pos` (`guest_addresses`, `verdict_core`) | `CEntity::m_node` (a `CNode*`) | none | `m_node` itself is at **0x28** in r0001 (8 uses), and the constructor's run of 9 stores moves `m_velM`/`m_velW` +0xc (demo 0x20-0x34 → 0x2c-0x40). r0001's 0x1c-0x27 is 12 bytes SOCOM 1 does not have, between `m_id` (0x4 → 0x4, 2 uses) and `m_node` | 738 uses unchanged (393 fns) | **contradicted**: no SOCOM 1 name. The position triple is new in SOCOM II (SOCOM 1 read position through `m_node`) |
| **0x48** `ANGVEL_OFFSET` (`sp_death_probe`) | none (a 12-byte gap in the demo's CEntity) | **`CEntity::m_velR.y`** (float, 0x3c) | 5 uses in 3 twin functions: `TeleportTo__7CEntityFPC6CPnt3DPC5CQuat`, `TeleportTo__7CEntityFPC7CMatrix` and the constructor. 9 of 13 neighbours share +0xc: `m_velM`, `m_velW` and `m_velR` all moved +0xc | 396 unchanged (241 fns) | **shifted by +0xc, named.** Rotational velocity about y = yaw rate, which fits "2.0 × turn axis" |
| 0x70 `QUAT_OFFSET` (`sp_death_probe`) | `CEntity::m_next_quat.x` | (a demo offset 0x44, no field) | `m_next_quat` is at **0x78** in r0001 (3 uses). One reverse twin gives demo 0x44; 0 of 14 neighbours agree | 331 unchanged | **contradicted** (the same-offset field moved to 0x78); unknown |
| 0x80, 0xa0, 0xa8 matrix (`sp_death_probe`, `online_match_ours`) | `CEntity::m_next_matrix` (+0, +0x20, +0x28) | none aligned | Interior words 0x94 and 0xb0 and `m_control` 0xc0 map to themselves (1, 1 and 6 uses). One use maps 0xb4 → 0xb8 | 262 / 212 / 116 unchanged | **unknown; consistent** with `m_next_matrix` unchanged, not confirmed |
| 0xc8 team word (`verdict_replay`) | `CEntity::m_max_target_range_sq` (a float) | none aligned | The demo's `m_team` is at 0xc4 and `m_control` 0xc0 is unchanged. The same-offset field is a float, not a team word | 166 unchanged, 5 moved to 0xcc | **unknown**. If it is the team, the hypothesis is `m_team` +4, unconfirmed |
| 0x23c (+0x240, +0x244) turn axis / throttle triple (`sp_death_probe`) | `CZSealBody::pi_diIntersect.m_BufCnt` | `m_prev_thr_x` (0x194), from the constructor only | The map puts the demo's throttle floats here: 0x23c `m_prev_thr_x`, 0x240 `pre_thr_lr`, 0x244 `pre_thr_fb` (demo 0x188-0x198, shifts +0xa8/+0xb8). One function; 0 of 8 neighbours agree | 57 unchanged | **single-twin candidate**: the throttle block (`pre_thr_lr/fb/strafe`, `m_prev_thr_x/z`); which word is which is not established |
| **0x2e8** `root_node` (`guest_addresses`) | `CZSealBody::m_reyelid` | **`CZSealBody::m_root`** (`CZBodyPart*`, 0x26c) | The constructor's **run of 25 stores at +0x7c**: demo 0x26c `m_root` … 0x2cc `m_rtoe`, every body-part pointer, → r0001 0x2e8 … 0x348. 8 of 11 neighbours share the shift. One reverse twin (`Recoil__10CZSealBodyFv`) disagrees (demo 0x280). The eye parts that follow moved +0x78, so `m_reyelid` is at 0x360 | 26 unchanged (18 fns) | **shifted by +0x7c, named `m_root`** |
| 0x400 R6 peek base, "last ground hit" (`verdict_core`) | `CZSealBody::m_snakePath.m_length` | none aligned | The constructor places the demo's three `IntersectStruct`s (`m_last_altitude`, `m_last_reticule`, `m_last_reticule_action`, 32 bytes each: pos, poly, norm, node) at +0xb0: a run of 5 stores, demo 0x32c … 0x36c → r0001 0x3dc … 0x41c; then 0x37c → 0x428. That puts 0x400 mid-struct | 37 unchanged | **unknown**. `m_last_altitude` fits "last ground hit" in meaning, but the constructor's +0xb0 contradicts 0x400 for it |
| 0x420 `ACTOR_STAMP_OFFSET` (`verdict_core`) | `CZSealBody::m_look_dir.x` | none | `m_look_dir` is at 0xf8c in r0001: two constructor runs of 3, `m_look_dir` +0xb6c and `m_formation_dir` +0xb70 | 14 unchanged | **contradicted**; no SOCOM 1 name |
| 0xf78 / **0xf7a** alive (`sp_death_probe`, `verdict_core`, `verdict_replay`) | `CZSealBody::m_weapons` (a vector) | none | `m_weapons` moved (0x1170). The block around it is demo 0xe50-0xe5b at +0x120/+0x121: 0xf70 `m_anim_handled` (1 observation), 0xf74 `m_weapon_state` (11), 0xf79 `m_item` (6). 0xf7a is demo 0xe5a, **padding** after the 1-byte `m_item`. SOCOM 1's alive flag is `CEntity::m_isAlive`, a bit (bit_offset 11) of the bitfield word at 0xdc; that word's byte access 0xdd sits at 0xe1 in r0001 (4 observations) | 6 / 11 unchanged | **no SOCOM 1 counterpart**: the alive byte is new in SOCOM II |
| 0xfb4 `DEATH_TIME_OFFSET` (`sp_death_probe`) | `CZSealBody::m_groundNormal.x` | none | `m_groundNormal` is at 0x1344 (constructor run +0x390). The r0001 neighbourhood holds the demo's death fields, one observation each: 0xfac `m_skel_y_w`, 0xfb8 `m_lastkiller_id`, 0xfc0 `m_movespeedmod`, 0xfc4 `m_killer_index`. The demo's `m_deathType` (0xea4) and `m_time_of_death` (0xea8) are not seen | 3 unchanged | **contradicted; unknown.** The hypothesis `m_time_of_death` (demo 0xea8, +0x10c) is not aligned |
| **0x1044** `HEALTH_OFFSET` (`sp_death_probe`, `verdict_replay`, `online_match_ours`) | `CZSealBody::m_wateranimnode.m_parent` | **`CZSealBody::m_health`** (float, 0xea0) | 2 uses in one twin function, `HandleBloodDrip__10CZSealBodyFf`, found in both directions (demo 0xea0 → 0x1044, 1 observation in the map). 0 of 7 neighbours share +0x1a4: the health field moved relative to its neighbours, and the fields after it sit at +0x104 | 10 unchanged (6 fns) | **single-twin candidate, shifted by +0x1a4**. Research/19 F1's independent semantics (float, 1.0 full, ≤ 0 dead) agree with the name |
| 0x1334 (the word r0004 inserted) | none | none | Neighbourhood: 0x1338 `m_throttleQuadrant`, 0x133c `m_descent` (+0x390/+0x392) | 1 use, moved to 0x1338 | **unknown** |
| **0x1368** `move_scale` (`guest_addresses`) | none (beyond the demo's 0x1140) | none | Its three functions have **no demo twin**. Best ratios: 0.47 for the setter `FUN_00553dc0` → `AdrenalineIncr`, 0.12 for the user `FUN_00551ec0`. The constructor has no aligned store there. Neighbourhood: 0x1360 `m_jumpTimer`, 0x1364 `m_nextJumpTimer`, 0x136c `m_belowwateranim`, 0x1370 `m_inwateranim`. The one demo field of that block the map does not place is `m_jumpImpulse` (0xfd4, "not seen") | all 6 uses → 0x136c (3 fns), as KNOWN §4 | **unknown**. The position alone suggests `m_jumpImpulse`; a clamped multiplier of the throttle triple is not a jump impulse, so it is not named |

The actor's shift map (D, runs of one shift, offsets seen at least twice) is not one shift but a dozen: demo
0x1c-0x40 **+0xc**, 0x50-0x54 +0x8, 0x60-0x68 +0x4, 0x70-0x74 +0x8, 0x7c-0xc0 **+0**, 0x170-0x178 +0xa4,
0x26c-0x28c **+0x7c**, 0x33c-0x35c +0xb0, 0xdd4-0xdd8 +0x114, 0xf50-0xf5c +0x104, 0xfc0-0xfc8 +0x390, 0x10ac-0x112c
**+0x3a0**. The constructor's own runs (D) add +0xa0 (`m_zoomstate`), +0x110 (`m_threatscale`/`m_threatangle`, 16
stores) and +0x3a0 (`m_aim_norm` … `m_prev_reticle_pt`, 12 stores). SOCOM II's `CZSealBody` is at least 0x14cc long
(demo 0x112c + 0x3a0), against the demo's 0x1140. The shift changes a dozen times along the object, and some fields
(`m_health`, `m_look_dir`, `m_weapons`) left their SOCOM 1 neighbourhood altogether.

### 4b. The other classes research/61 §3 names

| r0001 offset (tool) | class | the demo field at the same offset | SOCOM 1 field that aligns (offset) | evidence (D) | r0004 (D) | verdict |
|---|---|---|---|---|---|---|
| 0x0c, 0x10, 0x14, 0x20, 0x24, 0x2c valves `mp_round_count`, `mp_game_over`, `player_team`, `mp_major_game_state`, `mp_minor_game_state`, `late_joiner` (`verdict_core.VALVES`) | CZNetGame | `m_pGameOverValve`, `m_pPlayerTeamValve`, … (the next valve down) | **`m_pRoundCountValve` 0x8, `m_pGameOverValve` 0xc, `m_pPlayerTeamValve` 0x10, `m_pMajorGameStateValve` 0x1c, `m_pMinorGameStateValve` 0x20, `m_pLateJoinerValve` 0x28** | **By name** against SOCOM II's own valve names (research/19 F2, read back out of both images). `mp_max_rounds` 0x0 and `mp_half_rounds` 0x4 sit at their SOCOM 1 offsets, `mp_max_round_time` (new) is at 0x8, and **all 8 valves after it are +4**, including `player_join_count` 0x44 and `player_ready_count` 0x48. Twins (D lists each with its aligned pairs): `SetE3RoundCount` (ratio 0.97) 0x8 → 0xc; `Initialize` (0.71) gives 0x1c-0x4c all +4. Its first few valve stores are misaligned (0x8 → 0x78, 0xc → 0x1c, 0x18 → 0xc …), and those produce the rows' single-twin readings for 0x0c and 0x2c | 662-753 unchanged each | **shifted by +0x4, named** (the name check is the confirmation) |
| 0x58, 0x5c, 0x70 valves `aiteam_00`, `aiteam_08`, `total_mp_kills` | CZNetGame | `m_uiv_NoneList`, `m_uiv_ChatList`, `m_persona_object_index` | none | No demo valve of those names. The demo's valve block ends at 0x4c; its `m_uiv_*` lists moved +0x38 (0x50 → 0x88 …) | unchanged | **new in SOCOM II**; the naive names are contradicted |
| 0xde `NG_LAG_FLAG_OFFSET` | CZNetGame | none | `m_bdown` (0x98), from 1 zero-store in `Initialize` | The byte flags 0x94-0x9f moved +0x38/+0x39 (`m_late_joiner` 0x94 → 0xcc in `Initialize`; `m_ten_second_launch` 0x9f → 0xd8 in `Initialize` and `TenSecondLaunch`); 0 of 11 neighbours share `m_bdown`'s +0x46 | 3 unchanged, 1 moved to 0xe2 | **unknown** (a single ambiguous store) |
| 0x100 (the peek split) | CZNetGame | none | `m_pTimerAnim` (0xc8) | +0x38, with the neighbours | 70 unchanged | shifted by +0x38 (not a field the tools read) |
| **0x118** `NG_FINGERPRINT_WORD` (50.0f) | CZNetGame | none (beyond the demo's 0xf8) | **`m_pos_smooth`** (float, 0xe0) | 2 uses in `Initialize`, neighbours at +0x38 agree, and `m_mpe3_round_count` 0xe4 → 0x11c (`SetE3RoundCount`, 0.97). reCOM names it `m_pos_smooth` independently | 119 unchanged, 1 moved | **shifted by +0x38, named** |
| **0x2c8** camera LOD scale (`game_overrides_socom2.cpp` cull/camcfg trace) | CCamera | `m_mtxSet.mtxWorldToView+0x8` | **`CCamera::m_RangeScale`** (float, 0x2b8) | 2 uses in 1 twin, `GetScaledRangeSquared` (ratio 0.85). The camera's fields to 0x2a8 map to themselves (`m_scrZ` 0x290; the region masks 0x2a0-0x2a8 in three exact pairs); 0x4a0 is +0x10 and 0x3c0 is +0x30 (`TestFOV`, a prefix pair), so 16 bytes were inserted before `m_RangeScale` and more later | 4 unchanged | **single-twin candidate, shifted by +0x10**, consistent with the block |
| 0x2cc camera LOD base scale | CCamera | `m_mtxSet.mtxWorldToView+0xc` | none | Under +0x10 it is demo 0x2bc, the padding after `m_RangeScale` | 20 unchanged | **unknown** (new in SOCOM II if +0x10 holds) |
| 0x330 camera 4×4 | CCamera | `m_mtxSet.mtxWorldToClip+0x30` | none | +0x10 would make it `mtxWorldToClip+0x20`, +0x30 would make it `mtxWorldToClip` itself; the insertion point between is not measured | 18 unchanged | **unknown** (two hypotheses) |
| 0x564 camera plane mask | CCamera | none (beyond the demo's 0x520) | none | The demo's `m_fovMask` is at 0x514; a +0x50 shift would be needed | 6 unchanged | **unknown** |
| **0x5c** / **0x5d** node flags (node trace) | CNode (`zdb::CNode`) | `tag_NODE_PARAMS`' flags word (27 bitfields, `m_active` … `m_apply_clip`, B); 0x5d is its byte 1 | **the same** | 5 uses in 2 twin functions / 4 uses in 1. CNode's aligned uses are +0 in 45 of 59 | 394 / 26 unchanged | **confirmed, unchanged** |
| **0x88** component presence | CNode | `CNode::m_visual` (the `CVisualVector` at 0x84) +4, its count | the same | 3 uses in 2 twin functions | 167 unchanged | **confirmed, unchanged** |
| 0x8c component data | CNode | `m_visual` +8, its data pointer | none aligned | Same member as 0x88 | 166 unchanged | consistent, unconfirmed |
| 0x9c fade/scale float | CNode | **`CNode::m_Opacity`** (float) | none aligned | CNode is +0 almost throughout | 200 unchanged | consistent, unconfirmed: "fade" and opacity agree |
| 0xa8 newlib `_reent` rand state (loader) | _reent | `_reent::_new._reent._rand_next` | none | `rand` (12 instructions) and `srand` (4) are below the finder's floor, and no r0001 body carries their relinked fingerprint: SOCOM II's newlib `rand` is a different build | (not class-specific) | **unknown in SOCOM II**; the name is SOCOM 1's newlib |
| chat packet: name 0x1c/32, type 0x3c, message 0x40/64, 0x80 (`socom2_chat.h`) | not in `.debug` | none | none | No demo layout has that shape (a `char[32]` at 0x1c together with a `char[64]` at 0x40). `chatFanoutRecv` 0x2f4ef0 (best 0.45) and `chatListRender` 0x2f5020 (0.44) have no demo twin | - | **unknown**: no SOCOM 1 layout |
| chat list 0x8c/0x90 and holder 0x04/0x08 | not established | - | - | - | - | **unknown** |
| OSK argument block: Purpose 0x10/64, SkbName 0x58/32, 0x98, 0x9c, 0xac (`socom2_osk_prefill.h`) | not in `.debug` | none | none | No demo layout of that shape (a `char[64]` at 0x10 together with a `char[32]` at 0x58). `oskOpen` 0x38d770 has no twin (0.27). `CSoftKeyboard` has 16 methods and no layout (§6) | - | **unknown** |
| music manager 0x0b/0x1c/0x28/0x34, sound definition 0x1c/0x1d, RtNet config 0x0c, camera holder 0xb4, camera config record 0x04/0x22/0x24/0x26, detail component 0x60/0x64, deferred draw list 0x04-0x14 | not established | - | - | The object's class is not named by any evidence here. Candidates by name alone (for example `CAppCamera` for the holder, whose 0xb4 is `m_next_rumble_time` in SOCOM 1) are not evidence | - | **unknown** |

**The list of offsets that can be named safely**, each with its confirming command D. These are the names
Goal 5's `guest_addresses.py` change can write beside the numbers, with the SOCOM 1 offset recorded as
provenance and never as a value:

| r0001 (= r0004) | name | SOCOM 1 offset | why it is safe |
|---|---|---|---|
| actor 0x2e8 | `CZSealBody::m_root` | 0x26c | a 25-store constructor run at +0x7c (every body-part pointer), 8 of 11 neighbours |
| actor 0x48 | `CEntity::m_velR.y` | 0x3c | 3 twin functions, 9 of 13 neighbours at +0xc |
| actor 0x1044 | `CZSealBody::m_health` | 0xea0 | **one** twin function, plus research/19's semantics. Name it with that caveat, or wait for a second twin |
| CZNetGame 0x118 | `CZNetGame::m_pos_smooth` | 0xe0 | twin + neighbours + reCOM's name |
| CZNetGame 0x0c, 0x10, 0x14, 0x20, 0x24, 0x2c | `m_pRoundCountValve`, `m_pGameOverValve`, `m_pPlayerTeamValve`, `m_pMajorGameStateValve`, `m_pMinorGameStateValve`, `m_pLateJoinerValve` | each −4 | SOCOM II's own valve names |
| CNode 0x5c, 0x5d, 0x88 | `tag_NODE_PARAMS` flags word, its byte 1, `CNode::m_visual` count | same | body-identical twins use them |

Not nameable from SOCOM 1: `actor_pos` 0x1c, `move_scale` 0x1368, the alive byte 0xf7a, the stamp 0x420, the
peek base 0x400, the quaternion 0x70, the death time 0xfb4, the lag flag 0xde, the chat, OSK, music, RtNet and
draw-list records.

## 5. The layout-age caveat, quantified

**E:** 14 classes have a demo layout and ≥ 3 body-matched members: `C2DBitmapPoly C2DLine C2DPoly CCamera CMatrix
CNode CPnt3D CQuat CTargetMods CWorld CZAnimMain CZPlayerMapItem CZSealBody CZWeapon`. Research/44 §5 counted 23
classes with ≥ 3 matched members; E counts body-matched only and needs a layout.

* **The body-matched members** use 33 distinct demo fields (E). These are unchanged *by construction*: an
  exact or relinked-body pair keeps every field displacement, so it says the code survived, not that the
  layout did. A sample built only from these would read "100 % survives", and would be wrong.
* **The edited members**, twinned through the prefix pairs and the twin finder, use 109 distinct demo fields.
  **32 sit at the same offset in r0001 and 77 moved** (E, majority per field).
* **The actor's constructor** stores to 133 demo fields and **moves all 133** (E).
* **The control**: the same alignment, run r0001 → r0004 on the same r0001 functions, reads 315 fields,
  **315 unchanged, 0 moved** (E). The method does not invent moves where there are none. (It is an easy control:
  r0004's bodies are nearly identical to r0001's, so it bounds the noise on clean alignments only.)

Per class (E): edited-twin fields same / moved.

| class | SOCOM 1 size | same / moved | reading |
|---|---|---|---|
| CPnt3D, CQuat, CMatrix | 0xc, 0x10, 0x40 | 3/0, 2/0, 1/0 | leaf math types: unchanged |
| C2DLine, C2DPoly, CTargetMods | | only body-matched fields (3, 4, 6) | unchanged where seen |
| CNode | 0xc0 | 4 / 3 | mostly unchanged |
| CCamera | 0x520 | 10 / 3 | the head unchanged, a 16-byte insertion before `m_RangeScale` |
| CZAnimMain | 0x1c4 | 6 / 2 | mostly unchanged |
| CZPlayerMapItem, C2DBitmapPoly | | 1 / 2, 0 / 1 | too few to say |
| CWorld | 0x6be0 | 0 / 6 | moved (+0xc, +0x10 and others) |
| CZWeapon | 0xb0 | 3 / 33 | moved, in coherent blocks (+4, +0x1c/+0x20, +0x28), mostly from its constructor |
| **CZSealBody** | 0x1140 | **2 / 27** | moved: the dozen runs in §4a |

**So:** the small value and math types carry over unchanged, and so do the scene-graph node and the camera's
head. The gameplay objects (the actor, the weapon, the world, and the net game of §4b) were rebuilt: SOCOM 1's offsets
for them are wrong far more often than right, often by hundreds of bytes. Their SOCOM 1 names, though, still
identify SOCOM II fields once a twin measures the shift. R262's caveat is not a formality. **A SOCOM 1 offset
applied unchecked to `CZSealBody` would be wrong for about 27 of every 29 fields.**

## 6. What is NOT there

* **The LPC-10 codec (F).** Its 34 units hold **23 class DIEs under 3 names** (`lpc10_encoder_state`
  0x2544, `lpc10_decoder_state` 0xc00, and an anonymous `@class`), 0 enums and 42 functions. They are not
  engine, and SOCOM II does not ship LPC-10: research/44 addendum 1 names its codec SASE.
* **Units with no class type of their own (F):** `crt0.s`, `gcc_wrapper.c` and `FTS\aidemo.cpp`.
* **Engine classes without a layout (F).** 934 classes have member functions in `.symtab` (`std`, `ai` and the
  anonymous namespaces are left out). 267 have a complete layout under the same name, and 360 template
  instances match a layout under their bare name, a loose match. **307 have no layout**, 6 of them templates.
  The largest by method count are `CVisual` 38, **`CNetCnf` 38**, `CZPersonaState` 24, `Particle` 22,
  `CBufferIO`, `CMemCard`, `CMesh`, `CTurret` and **`CSoftKeyboard`** 16 each, `CConsole` 14, `CZSealState`
  14, `Headset` 13 and **`CPacket`** 10. Every one of them is named as a string in the demo file. Of the
  handoff's two question marks, **`CZOnlineLobby` has a layout (0x98, 65 methods) and `CNetCnf` has none**.
* **What the `.debug` never describes**: the engine libraries' functions (§3); the chat record, the OSK
  argument block and the network message layouts (§4b); and any SOCOM II-only field.

**What a stranger would need to fill the gap.** One of two things. The first is a SOCOM II build that keeps
its symbols: research/58 says only a copy of the Aug 28 or Nov 25 2003 build that still has its `.symtab` is
worth having, and a `.debug` would be better still. Absent that, the second is SOCOM II's own evidence, offset
by offset. That means a twin that reaches the accessing function. It does not reach `move_scale`'s,
`chatFanoutRecv`'s, `oskOpen`'s or the lag-flag setter's: none of these functions has a demo twin, because
SOCOM II rewrote them. Otherwise it means a runtime observation, the way research/19 read the valve names and
KNOWN §4 found `move_scale`. The demo's types then supply candidate *names* for the fields such evidence
locates, through `game/demo_types.txt`.

## What this means for a task

| task | finding | what it changes |
|---|---|---|
| Goal 5, `guest_addresses.py` names | 12 offsets named safely (§4 list): `m_root` 0x2e8, `m_velR.y` 0x48, `m_pos_smooth` 0x118, six CZNetGame valve slots, and the CNode words 0x5c/0x5d/0x88. A 13th, `m_health` 0x1044, rests on one twin plus semantics | The Goal 5 change writes these names beside the numbers with the D command as evidence and the SOCOM 1 offset as provenance only. It adds `m_health` with its single-twin caveat or leaves it for a second twin. It names nothing in the "not nameable" list |
| Goal 5, r0004 columns for the ladder's r0001-only offsets | Health 0x1044, alive 0xf78/0xf7a, death time 0xfb4, angular velocity 0x48, quaternion 0x70, matrix 0x80/0xa0/0xa8, stamp 0x420, peek 0x400 and throttle 0x23c: every twinned use keeps its value on r0004. The team word 0xc8 keeps 166 uses and moves 5 (to 0xcc). All of them are below r0004's one actor insertion at 0x1334 | These are the measurements the table's own comment waits for ("they join when somebody measures them"). Each can get an r0004 column equal to r0001, with D as the evidence. For the small offsets (0x48 … 0xc8) the counts include other classes' uses of the same number, so the actor-specific argument is the 0x1334 insertion. 0xc8's five moved uses should be read before its column is filled |
| Goal 5, the stop rule | Contradicted naive names: `actor_pos` 0x1c (`m_node`), the quaternion 0x70 (`m_next_quat`), the stamp 0x420 (`m_look_dir`), the death time 0xfb4 (`m_groundNormal`), the alive byte (`m_weapons`), the valves 0x58/0x5c/0x70 (`m_uiv_*`) | These are written as contradictions and never applied. A test that asserts "no SOCOM 1 name at these offsets" would hold the line |
| R262 (the layout-age caveat) | Edited twins: 32 of 109 fields at the same offset. The actor's constructor: 0 of 133. The control r0001 → r0004: 315 of 315 | The caveat stands with a number. A SOCOM 1 offset for a gameplay class is wrong more often than right. Only the leaf math and scene-node types carry over |
| research/44 §1 ("reopen for types / units") | Units cover 52 of the 987 pairs, from 21 units; the engine libraries have none | The translation-unit route adds nothing to the engine names. Research/44 §5's clustering stays the only grouping for `CZSealBody`, `CMission`, `CZNetwork` |
| Tooling | ccc main reads DWARF1 completely but cannot build types (T1); the `dwarf_types` branch prints no offsets (T2). `tools_py/research/symbols/dwarf_types.py` builds all 536 layouts from ccc's raw dump, and an independent walker checks it | Nothing to install beyond ccc main. A ccc upgrade that implements `TAG_class_type` would replace the script's layout code, not its evidence code |
| Voice chat (the SASE row) | `.debug`'s voice types are LPC-10's (3 names), and `CZNetVoice` (0x48) is SOCOM 1's network voice object | Nothing here describes SASE. `CZNetVoice`'s layout is a starting candidate for SOCOM II's voice object only after a twin check |
| OSK / chat hooks | No demo layout for the chat packet or the OSK argument block; `CSoftKeyboard` has no layout; the hook functions have no demo twin | Those constants stay what the hooks measured. The demo cannot confirm them |
