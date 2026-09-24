# 55. The class inventory as an architecture map, and what the hooks touch

Date: 2026-09-24. Sprint 12 research wave, question 10 of the cloud handoff §4
(`docs/superpowers/plans/2026-09-24-sprint-12-cloud-handoff.md`). This note is read-only. It reads two ELFs,
one Ghidra table, the runtime's address table and overrides, and the parity probe table. No game was run and
no Ghidra process started. `recomp/socom2_ghidra.csv` is **unchanged**, and no name is applied. The one
output is the git-ignored `game/class_inventory.csv`. This note extends `docs/research/44-demo-symbols.md`
and `45-positional-and-bridge-names.md` and the measurements in `tools_py/research/symbols/README.md`. None
of those is edited.

**The one-line answer.** By its class paths, the SOCOM 1 demo has **972 classes** holding 5,967 of its 9,703
functions. Task 7 placed **317** of those methods in our image and proposed **60**. **5,650** are unplaced.
**809 classes have nothing placed.**

The online classes are almost all **non-virtual**: `CZOnlineLobby` (65 methods), `CNetCnf` (38), `CZNetwork`
(24), `CZNetGame`, `CZSealState`, `CZBombState`, `CZNetVoice` and `Headset`. None has an RTTI string in either
build, so Goal 3's vtable route cannot reach them.

The route that does reach the lobby layer is one the project has not used as a name source: **the UI
script-binding table**. Its r0001 copy has 207 command-string→handler rows, all still auto-named. The demo's
copy names its handlers after the same strings: 131 of 147 handlers are `UI<command>`. That gives 124 r0001
handlers a demo name by string alone. The 3 of them that Task 7 also placed agree, and none disagrees.

Of the runtime's **33 function fields** in `socom2_addresses.h`, **27 are named by nothing on disk**. So are
**29 of the 40** addresses its `replaceFunction` wraps reach. Voice cannot be named from the demo at all:
SASE and RTIME's `rt_audio` are absent from it (0 names). Its LPC-10/PTT stack (67 functions) is SOCOM 1's
own codec, and Task 7 placed none of it.

Every number below names the command that produces it. There is one command:

```
# A -- the inventory, the subsystems, the .debug CU walk, the binding table, the hooks, the online
#      classes and the gap map (§1-§5); writes game/class_inventory.csv
python tools_py/research/symbols/class_inventory.py
```

It takes about 30 to 35 seconds. It re-derives Task 7's 987 pairs in-process with
`ghidra_symbol_match.match(prefix=True)`, because the json does not carry the demo address, and checks them
against `game/demo_symbol_matches.json` (`Task 7 pairs 987 (re-run == json: yes)`). It rebuilds research/45's
positional gaps with `symbol_levers.anchor_gaps` (`gaps 156, candidates 528`, research/45's own figures). It
imports `readable_names.readable` rather than copying it, and copies `vtable_rtti.py`'s
string→RTTI→vtable chain. A second command is quoted once:
`python tools_py/research/symbols/readable_names.py` (the README's census).

In what follows, "placed" means one of Task 7's 987 pairs lands on the method: `exact`, `hash+callees`,
`relinked-body`, `prefix` or `prefix+size`. "Proposed" means that pair is also one of the 479 rows of
`game/demo_symbol_renames.csv`. "7b" means one of research/45's 6. A "lead" is a research/45 lever-1
candidate: the i-th unplaced function in an equal-count anchor gap, before any body rule. A lead is a
position, not a name.

## 1. The inventory

Command A, block `[1]`:

```
members 5967, free 3736; classes by class path 972 (README rsplit method: 1210)
README's three, by class path vs rsplit: CZSealBody 369/351, CSealCtrlAi 142/140, CZKit 114/110, CZOnlineLobby 65/65, CNetCnf 38/38
wrote game/class_inventory.csv: 972 rows (one per class path), 22 columns
totals over classes: methods 5967, placed 317, proposed_479 60, proposed_7b 2, unplaced 5650, positional_leads 227
classes with >=1 placed: 163; with >=1 proposed: 44; with 0 placed: 809
classes by method count: 1 240, 2-4 441, 5-9 159, 10-49 120, >=50 12
```

**The class count is 972, not 1,212.** A class here is the mangled name's own class path: the `Q<n>` nested
list or the single `<len><Name>` after the first `__`, joined with `::`. The README's 1,212 is
`readable(n).rsplit("_", 1)[0]`. That splits a method whose name has an underscore
(`_validate_cell__6CAiMap` becomes `CAiMap__validate`), so one class becomes several keys. That undercounts
the class it came from: CZSealBody has **369** methods, not 351, and CZKit **114**, not 110. The README's own
script prints **1,210** today (`readable_names.py`: `classes 1210`), so its 1,212 does not reproduce either.
The spec's §1 and the handoff quote 1,212 and 351. The class-path figures are 972 and 369.

The 972 include namespaces used as classes (`std` 88, `ai` 36, `zdb`/`zar` paths), 395 `std`/`Metrowerks`
classes, and anonymous-namespace classes (`@unnamed@zanim_menu_cpp@`, `@unnamed@zui_skb_cpp@::CSoft…`).
`game/class_inventory.csv` has one row per class (**972 rows**) with these columns:

- `methods`, `placed` and `placed_<pass>` for each of the five passes;
- `proposed_479`, `proposed_7b`, `unplaced` and `positional_leads`;
- `demo_vtable_slots`, from the `__vt__` symbol's size;
- `name_in_demo` and `name_in_r0001` (the `\0Name\0` test `vtable_rtti.py` uses, with the qualified name);
- `r0001_vtables` and `r0001_vtable_slots`;
- `debug_dirs_by_pc` and `debug_dirs_by_name` (§2);
- the largest unplaced method's name and size.

The top 40 by method count (command A, block `[1]`). In the `placed` column the split is
exact/hash+callees/relinked-body/prefix/prefix+size. In `vt demo→r0001`, the demo count comes from the
symbol's size and the r0001 count from the RTTI chain. `—` means there is no vtable.

| class | methods | placed (split) | prop. | 7b | unplaced | leads | vt demo→r0001 |
|---|---|---|---|---|---|---|---|
| CZSealBody | 369 | 11 (6/0/2/3/0) | 2 | 1 | 358 | 8 | 25→26 (+7 secondary) |
| CSealCtrlAi | 142 | 0 | 0 | 0 | 142 | 0 | 40→44 |
| CZKit | 114 | 2 (1/0/0/1/0) | 0 | 0 | 112 | 0 | — |
| CSealCtrl | 94 | 3 (2/0/0/1/0) | 0 | 0 | 91 | 0 | 39→44 |
| CZWeapon | 91 | 5 (5/0/0/0/0) | 1 | 0 | 86 | 0 | 2→2 |
| std | 88 | 1 | 0 | 0 | 87 | 0 | — |
| zdb::CNode | 80 | 10 (7/0/0/2/1) | 0 | 0 | 70 | 31 | 14→15 |
| CZAnimMain | 66 | 11 (7/0/0/4/0) | 0 | 0 | 55 | 14 | — |
| CZOnlineLobby | 65 | 1 (0/0/0/1/0) | 0 | 0 | 64 | 0 | — |
| CZAnim | 61 | 0 | 0 | 0 | 61 | 4 | — |
| CAiMap | 60 | 4 (1/0/0/2/1) | 0 | 0 | 56 | 2 | — |
| zdb::CWorld | 54 | 4 (3/0/0/0/1) | 1 | 0 | 50 | 0 | 17→18 |
| CEntity | 45 | 0 | 0 | 0 | 45 | 0 | 18→26 |
| zdb::CCamera | 42 | 5 (4/0/0/1/0) | 1 | 0 | 37 | 2 | 14→15 |
| CMission | 41 | 4 (0/0/0/4/0) | 0 | 0 | 37 | 0 | 5→5 |
| CSnd | 41 | 0 | 0 | 0 | 41 | 0 | 9→12 |
| CAiMaps | 39 | 2 (1/0/0/1/0) | 0 | 0 | 37 | 0 | — |
| CNetCnf | 38 | 0 | 0 | 0 | 38 | 0 | — |
| CSealUnit | 38 | 0 | 0 | 0 | 38 | 0 | 2→2 |
| zar::CZAR | 38 | 3 (1/0/0/2/0) | 0 | 0 | 35 | 0 | 1→1 |
| zdb::CVisual | 38 | 8 (3/0/0/4/1) | 1 | 0 | 30 | 1 | 7→6 |
| CTargetMods | 37 | 7 (7/0/0/0/0) | 0 | 0 | 30 | 7 | — |
| ai (namespace) | 36 | 7 (5/0/1/1/0) | 0 | 0 | 29 | 4 | — |
| zdb::CGrid | 36 | 1 (1/0/0/0/0) | 1 | 0 | 35 | 0 | — |
| CZProjectile | 33 | 3 (2/0/0/1/0) | 0 | 0 | 30 | 0 | 2→2 |
| CInGameWeaponSel | 31 | 1 (0/0/0/1/0) | 0 | 0 | 30 | 0 | 21→26 |
| std::__vector_pod<Ui,…> | 30 | 0 | 0 | 0 | 30 | 0 | — |
| CAiPath | 29 | 0 | 0 | 0 | 29 | 0 | — |
| CSealStats | 28 | 2 (2/0/0/0/0) | 0 | 0 | 26 | 0 | — |
| CSndInstance | 28 | 1 (1/0/0/0/0) | 0 | 0 | 27 | 0 | — |
| CHUD | 27 | 2 (1/0/0/1/0) | 0 | 0 | 25 | 0 | — |
| C2D | 25 | 1 (1/0/0/0/0) | 0 | 0 | 24 | 0 | 21→26 |
| CZFTSWeapon | 25 | 1 (1/0/0/0/0) | 0 | 0 | 24 | 0 | 3→3 |
| C2DString | 24 | 1 (1/0/0/0/0) | 0 | 0 | 23 | 0 | 29→34 |
| CZNetwork | 24 | 3 (0/0/0/2/1) | 0 | 0 | 21 | 0 | — |
| CZNewHudMap | 24 | 0 | 0 | 0 | 24 | 0 | 21→26 |
| CZPersonaState | 24 | 0 | 0 | 0 | 24 | 0 | — |
| OrdersMenu | 24 | 0 | 0 | 0 | 24 | 0 | — |
| std::basic_string<c,…> | 24 | 0 | 0 | 0 | 24 | 0 | — |
| CBody | 23 | 0 | 0 | 0 | 23 | 0 | 3→(1/2/1) |

What the table shows:

- **The big classes are almost entirely unplaced.** 11 of CZSealBody's 369 methods are placed and 2 are
  proposed.
- **Proposals and classes barely overlap.** 60 of the 479 proposals are class methods. The other 419 are free
  functions: the SDK, libc and RTIME (§2).

## 2. Subsystems

### 2.1 By name prefix

Command A, block `[2]`. Classes are grouped by the first class-path component. The first match wins, in this
order: `CZOnline*`, `CZNet*`, `CZ*`, `CSeal*`, `CAi*`, `C2D*`, `CUI*`, `CNet*`/`CHNet*`, `std`/`Metrowerks`,
other `C*`, lowercase `z*` namespaces, then everything else.

| subsystem | classes | methods | placed | prop. | unplaced | leads | what the project already knows |
|---|---|---|---|---|---|---|---|
| C* (other) | 249 | 1,507 | 118 | 23 | 1,389 | 53 | reCOM's zFTS/zGame: `CMission::Init` = FUN_002ad290 and siblings, `CGameState` vtable order (research/11 §1, [verified]) |
| std/Metrowerks (MSL) | 395 | 1,239 | 28 | 3 | 1,211 | 48 | nothing; the CodeWarrior runtime |
| CZ* (other) | 59 | 1,137 | 49 | 8 | 1,088 | 59 | CZSealBody health `+0x1044` and life `+0xF7A` (research/19 F1). reCOM's `zseal.h` names in SOCOM 1 order (research/19 F6). The actor vtable 0x6691a0 is CZSealBody's (§3) |
| z* namespaces (zdb, zar, …) | 70 | 559 | 49 | 7 | 510 | 48 | the render path: `CSaveLoad::Load` FUN_00318da0, `CNode::ReadDataBegin` family; the VU1 packet builders (FUN_003389c0 = the `node2` hook) are **not** labelled by reCOM (research/11 zRender). zArchive fully described (research/11) |
| other classes/namespaces | 98 | 461 | 24 | 5 | 437 | 6 | `ai::` command set: `CSealCtrlAi::RegisterCommands` = FUN_005de320 (research/11 zAnim, [verified]) |
| CAi* | 59 | 349 | 15 | 5 | 334 | 5 | the AI state-name table FUN_00575490 (research/11, [string-match]) |
| CSeal* | 9 | 326 | 6 | 0 | 320 | 0 | `CSealStats` names (research/19 F6) |
| C2D* | 18 | 169 | 19 | 9 | 150 | 7 | reCOM's `C2D` vtable order and `C2DMessage_Q` (research/11 zTwoD) |
| CZOnline* | 1 | 65 | 1 | 0 | 64 | 0 | `CZOnlineLobby::Init` = FUN_002e0450, `LOBBY_STATE` (research/11 zNetwork, [verified]) |
| CUI* | 8 | 59 | 5 | 0 | 54 | 1 | `CUIVariable`/`CUIVarManager` (research/11 zUI) |
| CZNet* | 3 | 51 | 3 | 0 | 48 | 0 | `CZNetGame::Initialize` = FUN_002a76d0 (research/11). `CZNetGame` at `*0x437ce8` and its valves (research/19 F2). The uninitialised ghost flag `+0xd2` (research/19 F3, research/20 §1) |
| CNet* | 3 | 45 | 0 | 0 | 45 | 0 | `m_bNetCnfRequired` → `NETCNF_REQUIRED`; NetCnf* bindings at 0x277ab0–0x278040 (research/11 §2a) |

Free functions, by family (same block):

| family | functions | placed | prop. | leads | what the project already knows |
|---|---|---|---|---|---|
| other free (libc, MSL, SDK, statics) | 2,316 | 369 | 211 | 192 | the toml's 656 stub names (research/44 addendum) |
| sce* | 428 | 201 | 140 | 41 | every bound stub and its consumers: the HLE liveness census, 223 stubs (research/20 §2) |
| Medius* client API + cb* callbacks | 383 | 11 | 3 | 20 | none from reCOM ("Medius 1.50 … absent from reCOM", research/11 §2d) |
| rt_* (RTIME) | 250 | 76 | 60 | 34 | libnetb/libnet only (research/10, cited by research/11) |
| z* | 142 | 5 | 3 | 0 | `zAnim*` command names (research/11 zAnim) |
| UI* script bindings | 129 | 4 | 1 | 13 | the r0001 binding table at 0x3dd4d4 and about 20 online rows with addresses (research/11 §2a). §4.2 turns this into names |
| libpttclient (LPC-10 + PTT) | 67 | 0 | 0 | 0 | SOCOM 1's codec. Not SOCOM II's (README voice record) |
| DME* | 13 | 3 | 1 | 1 | none |
| hud* | 8 | 1 | 0 | 0 | `hudInit` = FUN_001fdee0 (research/11, [verified]) |

`rt_*` by second token: rt_msg 108, rt_comm 55, rt_time 27, rt_rel 24, rt_circ 17, rt_mutex 11, rt_memory 8.
The per-class and per-family totals reconcile with Task 7:

- placed: 317 + 670 = **987**;
- proposed: 60 + 419 = **479**;
- leads: 227 + 301 = **528**.

### 2.2 By `.debug` source directory

`debug_paths.py` extracts strings. Command A goes one step further **at the compile-unit level only**. It walks
the DWARF1 DIE chain: a u32 length, a u16 tag, then attributes. It keeps each `TAG_compile_unit`'s `AT_name`
and `AT_low_pc`/`AT_high_pc`. Types, members and locals are Goal 5's (ccc) and are not read.

Command A, block `[2]`:

```
.debug CU walk: 959 compile-unit DIEs (walk ends exactly at the section end: yes), 880 with a pc range;
demo functions inside a CU range: 879 of 9703
```

| directory | source files | functions in its pc ranges | placed | prop. | classes with a member there |
|---|---|---|---|---|---|
| `Z:\dev\Apps\FTS` | 37 | 428 | 25 | 8 | 59 |
| MSL / CodeWarrior | 24 | 254 | 19 | 2 | 64 |
| `Z:\dev\gamez\zcamera` | 5 | 70 | 5 | 1 | 2 |
| `C:\dev\libpttclient` | 35 | 59 | 0 | 0 | 0 |
| `Z:\dev\gamez\zseal` | 1 | 17 | 2 | 0 | 3 |
| `Z:\dev\gamez\ztwod` | 1 | 14 | 1 | 0 | 3 |
| `Z:\dev\gamez\zgame` | 1 | 9 | 0 | 0 | 1 |
| `C:\dev\libpttserver` | 1 | 9 | 0 | 0 | 0 |
| `Z:\dev\gamez\zfts` | 2 | 7 | 0 | 0 | 4 |
| zmath, zui, zentity, znode, zutil, sce SDK | 1–2 each | 1–3 each | 0 | 0 | 1–2 each |

**The `.debug` describes the FTS application layer and almost nothing else.** Only 879 of the 9,703
functions (9.1 %) sit inside a compile unit's pc range. The GameZ engine is present only as inline
instances from its headers: one or two units per `gamez` directory, and zcamera's five.

The FTS files by function count:

- `orders.cpp` 32, `hud_ingame_weaponsel.cpp` 30, `hud_main.cpp` 27, `hud_newhudmap.cpp` 25, `reco.cpp` 22;
- `hud_weaponsel.cpp` 22, `hud_objectives.cpp` 21, `hud_linemap.cpp` 18, `main.cpp` 17, `st_core.cpp` 16;
- then the rest of `hud_*.cpp` and `st_*.cpp`, `thezoom.cpp`, `database.cpp`, `getopt.cpp`, `options.cpp`
  and `aidemo.cpp`.

That is reCOM's Apps/FTS file list (research/11 §Apps/FTS: `main.cpp`, `st_menu`/`st_core`,
`game/database.cpp`, `hud/*`). The FTS classes it describes are the HUD and the menu states:

- CInGameWeaponSel 30, CHUD 27, OrdersMenu 24, CZNewHudMap 24, CWeaponSel 22, CZObjectiveList 21;
- BitmapReticule 15, CZPauseTest 12, CZLineMap 12, CZPlayerMapItem 12, MapCompass 11, CCoreState 10;
- CZHudMissionCams 10, CMenuState 9, and smaller ones.

**No online class has a compile unit.** The `debug_dirs_by_pc` column is empty for CZOnlineLobby, CNetCnf,
CZNetwork and CZNetGame. debug_paths.py's name-occurrence method reaches them only as a type named inside
someone else's unit: CZOnlineLobby's name appears in 3 FTS units, CZNetwork's in 14. Command A attributes
each occurrence to the enclosing compile unit and finds 350 of the 972 class names anywhere in `.debug`. A
class named in 30 FTS units is declared in a header that FTS includes. That is not where it is implemented,
so the CSV's `debug_dirs_by_name` column is coverage, not location.

## 3. What the hooks touch

Command A, block `[3]`.

**`socom2_addresses.h`: 41 fields, 8 DATA, 33 function fields.** The r0001 column is parsed from the
initialiser. The three symbolic entries resolve through `socom2_osk_prefill.h` and `socom2_chat.h`.

Two columns of the table below need a definition:

- **task 7**: the pair on the address, or `unnamed`.
- **context**: the Task 7 anchors either side of the address in its PT_LOAD, how many of our functions lie
  between them, and how many demo functions lie between their demo twins when the twins are in order.

| field | r0001 | task 7 | context and other evidence |
|---|---|---|---|
| rtNetConfigInit | 0x00620648 | unnamed | between `NetFreeAllObjects` and `IsEven` (the Medius/RTIME region); 281 of ours, demo twins out of order |
| packTrace | 0x0025a5d0 | unnamed | between `zar::CZAR::CloseKeepDir` and `zAnimGetDirectionFromAzimuthZenith`; twins out of order |
| cull | 0x00290c30 | `TestFOV__Q23zdb7CCamera…` [prefix] | named, not proposable (hurdle 3) |
| node, node2, defer, flush | 0x00338480, 0x003389c0, 0x003371b0, 0x00336cb0 | unnamed | one gap, `_zrdr::IsArray` … `CSaveModule::SaveRdr`: 255 of ours against 7,082 demo functions between the twins, so position gives no handle. research/11: the VU1 packet builders, not labelled by reCOM |
| lod, detail | 0x003b7b90, 0x003b6e10 | unnamed | the `zdb::CVisual` neighbourhood (`ApplyDecalRender` … `tag_GlobalLight` ctor): 44 of ours, 48 in the demo |
| camCfg | 0x002918b0 | unnamed | the `zdb::CCamera` neighbourhood (`TestFOV` … `RegisterAnimCommands`): 23 of ours, 20 in the demo |
| musicManager, cuePush | 0x0034afd0, 0x0034b6c0 | unnamed | the `CSndSequence` neighbourhood (`CreateSequence` … `zsys_FullAllocAndFree`): 93 of ours, 45 in the demo |
| oskOpen | 0x0038d770 | unnamed | the `@unnamed@zui_skb_cpp@` soft-keyboard unit: 48 of ours, 55 in the demo |
| oskOpenThunk | 0x002808d0 | unnamed | **binding command `GetTextInput`** → the demo's `OnGetTextFromUser__24@unnamed@zanim_menu_cpp@F…` (§4.2) |
| chatFanoutRecv, chatListRender | 0x002f4ef0, 0x002f5020 | unnamed | between `_roomplayer_sort_aux` (MediusLobbyWorldPlayerListResponse) and a `Metrowerks::cdeque` swap, i.e. the lobby unit; 26 of ours; twins out of order |
| dnasCheck | 0x002cc670 | unnamed | **binding command `DNASAuthenticate`**, an r0001-only command (research/11 already had it) |
| netbExOpen, netbExTcpRecv, netbExAvailable | 0x002472c8, 0x002474f8, 0x002479b8 | unnamed | **1-for-1 gaps**: leads `sceBInetOpen` (demo 288 B / ours 408 B), `sceBInetRecv` (280/324), `sceBInetGetAvailBytesToRead` (168/232) |
| netbExTcpSend | 0x00247738 | unnamed | gap of 2 ours / 1 demo (`sceBInetSend`) |
| netbExConnected | 0x00247bd8 | unnamed | gap of 1 ours / 0 demo: no SOCOM 1 counterpart |
| netbExUdpRecv, netbExUdpSend | 0x00247d30, 0x00247fe8 | `libnetb_recv_from`, `libnetb_send_to` [prefix+size] | named, not proposable |
| netbExStartAsync, …2 | 0x00248350, 0x002483f8 | unnamed | twins out of order |
| netbExDescriptorDma | 0x00247c98 | `libnetb_trans_data` [exact, proposed] | named |
| dnasSha1Hash | 0x0062eec0 | unnamed | gap `AppendKeyChain` … `KM_SetLocalClientID`: 8 of ours, 7 in the demo: `GetKeyChain, RemoveKeyChain, InitializePRNG, SHA, KM_GetVersionStringPtr, KM_Initialize, KM_Create` |
| dnasRsaBlock, dnasRc4SetKeyHash, dnasRc4SetKey, dnasRc4Encrypt, dnasRc4Decrypt | 0x0062b948, 0x0062a638, 0x0062a5a8, 0x0062a720, 0x0062a7c8 | unnamed | one gap `IsEven` … `rt_circ_buf_create`: 107 of ours, 40 in the demo |

```
function fields named by no Task 7 pair or proposal: 29 of 33; by nothing on disk (no pair, proposal,
toml name, binding-table command or hand name): 27
```

**`game_overrides_socom2.cpp`: 28 `replaceFunction` call sites reach 40 fixed addresses, plus 1 dynamic
(`PS2X_CALL_TRACE`).** The 40 are 32 table fields and 8 boot-loader literals. Of the loader literals, five
are Task 7 pairs: `sceSifSendCmd` [exact], `sceSifMInitRpc` [relinked-body, proposed], `sceSifMBindRpcParam`
[prefix], `sceSifMUnBindRpc` and `sceSifMCallRpc` [exact, proposed]. `0x00181c90` carries the toml's
`mwLoadOverlay`. `0x001c59c0` and `0x001c5b30`, the disc and memory-card game-code loaders (research/43), are
named by nothing.

```
wrap addresses (loader literals 8, table fields 32): named by no Task 7 pair or proposal 32 of 40; by nothing on disk 29
```

The two `bindAddressHandler` targets (ret0) are both named: `netbExDescriptorDma` = `libnetb_trans_data`
[exact, proposed], and `0x001ac9d8` = `InitSystemCallTableAddress` [relinked-body, proposed; toml].

**The parity probes (`tools_py/parity/guest_addresses.py`, r0001).**

- `camera_record` 0x416054, `player_actor` 0x408c58 and `guest_clock` 0x4365c0 are data. Nothing names them:
  Task 7 matches functions only, and the demo's 10,179 sized OBJECTs (research/44 §1) are matched by nothing
  yet.
- `actor_vtable` 0x6691a0 **is CZSealBody's primary vtable**. The chain is string 0x65c240 → RTTI 0x65c288 →
  vtables 0x6691a0 and 0x669210 (`actor_vtable is CZSealBody's vtable: yes`). That is a name for the probe no
  name file carries.
- **The csv holds a function row on it:** `FUN_006691a0` of 256 B, and `FUN_00669210` of 256 B on the
  secondary vtable. Command A's census counts **70 of the 240 r0001 vtables located by RTTI** sitting on a
  csv `FUN_` row, which is data exported as code.

The three functions the `move_scale` comment names:

- `0x00551ec0` (MoveScale) is **CZSealBody vtable slot 3 of 26**. The demo has 25 slots, so the alignment is
  unproven. The demo's slot 3 is `Tick__10CZSealBodyFf`.
- `0x00553dc0` is unnamed: a 45-of-ours / 22-demo gap inside CZSealBody (`ResetToInitialState` …
  `OnRecycleEntity`).
- `0x00553ea0` is **one of the two functions that build CZSealBody's vtable pointer**. The other is
  0x5533e0. It also sits in a 4-of-ours / 3-demo gap whose demo span holds
  `__ct__10CZSealBodyFPQ23zdb5CNodeP14CCharacterType`. research/11 called it the skeleton reader
  ([string-match]). The three agree: it is **the CZSealBody constructor**, a lead for Goal 3's
  constructor by-product.

## 4. Online play and voice

### 4.1 The classes

Command A, block `[4]`. Every class here except the three C2D rows has **no vtable in the demo** and **no
class-name string in either image**. The raw substring count in r0001 is 0 for CZOnlineLobby, CNetCnf,
CZNetwork, CZNetGame, CZSealState, CZBombState, CZPersonaState and CZNetVoice (the command in §4.3's note).
So Goal 3 cannot reach them.

| class / family | methods | placed | prop. | unplaced | leads | what is placed |
|---|---|---|---|---|---|---|
| CZOnlineLobby | 65 | 1 | 0 | 64 | 0 | `PasswordSecurity` @0x2faf50 [prefix] |
| CNetCnf (+ CHNetCnf 3) | 38 | 0 | 0 | 38 | 0 | — |
| CZNetwork | 24 | 3 | 0 | 21 | 0 | `zNetRemoteObjectUpdateCallback` @0x30cdf0 [prefix], `zNetRegisterRemoteObjectCallback` @0x30ce80 [prefix+size], `zNetSendApplicationMessage` @0x30cef0 [prefix] |
| CZNetGame | 16 | 0 | 0 | 16 | 0 | — |
| CZSealState | 14 | 1 | 0 | 13 | 0 | `RemoteSealDeletionCallback` @0x2bef60 [prefix] |
| CZBombState | 13 | 2 (+1 7b) | 0 | 11 | 4 | `CreateBombHere` @0x2c1bf0, `RequestNewBombState` @0x2c2090 [relinked-body]. Leads: `UninitBomb`→0x2c1970, `InitBomb`→0x2c1a80, `ChangeBombState`→0x2c1c30 (and `HandleBombStateRequest`→0x2c1f10, already 7b) |
| CZPersonaState | 24 | 0 | 0 | 24 | 0 | — |
| CZGameState, CZGrenadeState | 7, 7 | 0, 1 | 0 | 7, 6 | 0, 4 | — |
| CSealStats | 28 | 2 | 0 | 26 | 0 | — |
| C2DMessage_Q / C2DMessageString / CZMPBombMapItem | 11 / 3 / 4 | 1 / 1 / 0 | 1 / 0 / 0 | 10 / 2 / 4 | 0 | **vtables:** 21→26, 29→34, 5→5 |
| rt_msg_client_* | 95 | 22 | 18 | 73 | 19 | 15 relinked-body, 5 exact, 2 prefix, e.g. `rt_msg_client_startup` @0x632778 … `rt_msg_client_set_scratch_buf_min_size` @0x638208 |
| UINet*/UILobby*/UI*Clan* bindings | 44 | 2 | 1 | 42 | 6 | `UINotOnCorrectClanTeam` @0x2775e0 [exact], `UIRemovePlayerFromClan` @0x27a840 [relinked-body] |
| CZNetVoice | 11 | 0 | 0 | 11 | 0 | — (`Init`, `WorkerThread`, `HandleNewIPBuf`, `Permit`, `Channel` …) |
| Headset | 13 | 0 | 0 | 13 | 0 | — (`Queue`, `DeQueue`, `ConnectedTick`, `SoundSysCallback` …) |
| libpttclient (LPC-10 + PTT) | 59 in CU range; PTT_/PTTServer_ 23 | 0 | 0 | all | 0 | — |
| **Sase*** | **0 in the demo** | — | — | — | — | r0001: 25 `Sase` strings (21 `SaseEncVad`, 4 `SaseDec`) |
| **rt_audio** | **0 in the demo** | — | — | — | — | r0001 only: RTIME `rt_audio version: 1.08.0009`; CVS paths `rt_audio/include/rt_audio.h`, `rt_audio/src/{audio.c, audio.h, codec.c, codec.h, grid.c, grid.h, rt_audio.c, rt_audio_internal.h}` |

The RTIME set differs between the builds (block `[4]`):

- **demo:** `rt_comm 1.02.0005`, `rt_crypt 1.01.0002`, `rt_msg_client 1.06`;
- **r0001:** `rt_audio 1.08.0009`, `rt_comm 1.03.0029`, `rt_crypt 1.01.0023`, `rt_msg_client 1.08.0204`,
  `rt_udp 01.02.0048`, `rt_upnp 1.01.0007`, plus `dme_client` CVS paths.

So `rt_audio`, `rt_udp` and `rt_upnp` are SOCOM II additions **the demo cannot name**. `rt_audio`, with a
`codec.c`, is the likely home of the voice transport around SASE. That is **[inference]**: nothing here
traces a call from it into the SASE units.

**The chat and game-list readers Sprint 11 bounded.** Task 2 wraps `chatFanoutRecv` 0x002f4ef0 and Task 2b
wraps `chatListRender` 0x002f5020. Both are unnamed, have no lead and fill no vtable slot. They sit in the
lobby unit's neighbourhood (§3). By semantics alone, the demo candidates are the Medius callbacks
`cbChatMessage__FiiiP20MediusChatFwdMessage` (480 B) and `cbGameList__FiiiP22MediusGameListResponse` (908 B),
with `UpdateGameListDisplay__Fv`, all free functions. That is a lead for a reader. It is not evidence, and
nothing on disk tests it.

### 4.2 The lever this question found: the UI script-binding table

Command A, block `[2b]`:

```
UI script-binding table: demo 147 rows at 0x439540 (function named UI<command>__...: 131; the rest
anonymous-namespace On*/Execute* handlers); r0001 207 rows at 0x3dd4d0, 207 distinct functions, 207 still auto-named
r0001 command strings also in the demo table: 124 (-> a demo name for that r0001 function); of those,
Task 7 pairs on the r0001 target: agree 3, disagree 0; r0001-only commands: 83
network/lobby commands in the r0001 table: 67, of which the demo table names 38
```

Research/11 §2a read the r0001 table (`InitNetwork` 0x276dc0, `LobbyConnect` 0x276780,
`NetCnfOpen` 0x277dd0 …) as addresses for a reader. The demo holds the same table: rows of
`[id, command string, handler]`, stride 12 in the demo and 16 in r0001. Its handlers carry symbols, so the
command string joins the two builds.

- **124 r0001 handlers get their demo name by string.** 131 of the demo's 147 handlers are
  `UI<command>__FP13C2DAnimCmdHdrPf`. The rest are anonymous-namespace `On*`/`Execute*` handlers in
  `zanim_menu.cpp`: `GetTextInput` → `OnGetTextFromUser`.
- **83 r0001-only commands** are named by their own command string and nothing else. They include
  `LobbyConnect`, `MediusInit`, the friends/ignore/clan-message family, the MUIS persona commands,
  `DNASAuthenticate` and `InitializeOnlineArmory`.
- The check available today is Task 7's pairs on the same addresses: **3 agree, 0 disagree**.

The 38 network commands the demo also names include every wrapper around `CNetCnf`: `NetCnfInit`,
`NetCnfUninit`, `NetCnfOpen`, `NetCnfClose`, `NetCnfCurrCombo`, `NetCnfSelectCombo` and
`NetGetInterfaceList`. They also include the lobby wrappers `LobbyLogin`, `LobbyRegister`, `LobbyLogout`,
`LobbyBailout`, `RefreshGameList`, `SendChatText`, `SendMediusChat` and `InitNetwork`. Each wrapper's callees
are then the lead into `CZOnlineLobby` and `CNetCnf`: one call-graph hop (question 7's propagation). That hop
is **not measured here**.

### 4.3 Ranked: whose naming pays first

A class's naming pays when it names code that the hooks, the online bugs or voice chat already reach.

| rank | class | why first | likely route to the unplaced |
|---|---|---|---|
| 1 | the chat/game-list readers (0x2f4ef0, 0x2f5020) and the lobby unit around them | installed hooks on the network trust boundary (Sprint 11 S), unnamed, no lead | call graph from the Medius callback registrations (`MediusUniqueCallbackChatFwdMessageHandler` and similar, question 7), shared strings (`"%s: %s"`, `"%s %s: %s"` anchor them in r0004; question 8), BinDiff (question 4). Not vtables: free callbacks |
| 2 | CZOnlineLobby (65, 1 placed) | the lobby state machine every online bug runs through; research/11 has `Init` | **binding table** (§4.2) → callees; strings; BinDiff. No RTTI, no leads |
| 3 | CNetCnf (38, 0) | the network-config path behind "No Network Adaptor detected" (research/11 §2a) | **binding table**: 7 `NetCnf*` wrappers named, then their callees. No RTTI |
| 4 | rt_msg_client_* (95; 22 placed, 18 proposed) | the transport under every packet; library code keeps link order | **positional**: 19 leads (research/45 lever 1); relinked-body and exact already carry 20 |
| 5 | CZNetwork (24, 3 prefix) | session and remote-object layer (`zNet*`); research/11 has its fields | the 3 prefix pairs are R257 hand-review candidates and anchors for a call-graph hop. No RTTI, no leads |
| 6 | CZBombState / CZGrenadeState / CZSealState | demolition and respawn replication (7b's `HandleBombStateRequest`, `RemoteRespawn`) | **positional**: 3 new CZBombState leads and 4 CZGrenadeState leads; CZSealState has only a call-graph route from `zNetRegisterRemoteObjectCallback` |
| 7 | CZNetGame (16, 0) | the round state at `*0x437ce8` (research/19 F2/F3) | research/11's `Initialize` FUN_002a76d0 and the valve strings; no RTTI |
| 8 | voice: SASE, rt_audio | Q5 | **not from the demo** (0 names). Strings, CVS paths and call structure (question 11). CZNetVoice (11), Headset (13) and libpttclient (0 placed) are SOCOM 1's voice stack; Headset's USB-queue methods are the only ones likely to survive, and they have no route but BinDiff and call graph |

The zero substring counts behind "no class-name string in either image" come from this one-off check, which
is not in command A:
`python -c "d=open('game/disc/socom2_game.elf','rb').read(); print([d.count(s) for s in (b'CZNetVoice',b'CZOnlineLobby',b'CNetCnf',b'CZNetwork',b'CZNetGame',b'CZSealState',b'CZBombState',b'CZPersonaState')])"`
prints eight zeros. Command A's `name_in_r0001` column (NUL-bounded) says `no` for the same eight.

## 5. The gap map

Command A, block `[5]`:

```
Goal 3's reach: classes with >= 1 r0001 vtable (qualified RTTI): 203, methods 2466, unplaced 2302;
one vtable with demo slots == r0001 slots: 68 (methods 544)
gap map: classes with >= 10 methods and 0 placed: 62 (methods 1249)
  name in neither image (no RTTI string: non-virtual class) -- uninformative 27
  name in r0001 (class survives: edited bodies)                            26
  template (name check n/a)                                                8
  name in demo, absent in r0001 (dropped, renamed, or RTTI discarded)      1
```

The 62 zero-placed classes with ten or more methods fall into four kinds.

**Present in r0001, so Goal 3 can open them (26).** The class survives; its bodies were edited past the
fingerprint's reach, or are too small to be unique. Research/44 §6's 78 % ceiling in its plainest form. In
the list below, methods are given first and demo→r0001 vtable slots in brackets:

- `CSealCtrlAi` 142 (40→44) and `CSealCtrlSquirm` 13 (40→44);
- `CEntity` 45 (18→26) and `CSnd` 41 (9→12);
- `CSealUnit` 38 (2→2) and `CBody` 23;
- the FTS HUD classes (where r0001 has two vtables, the first is given): `CZNewHudMap` 24 (21→26), `CWeaponSel` 23 (21→26), `CZObjectiveList` 22 (21→27),
  `BitmapReticule` 16 (21→26), `CZPauseTest` 13 (21→26), `CZLineMap` 12 (5→5);
- `CAppCamera` 22 (2→2);
- the C2D/UI widgets: `CBufferIO` 16 (14→17), `C2DButton` 14 (24→29), `CUIListBox` 14 (27→26),
  `CRenderableString` 13 (35→34), `CSliderBar` 10 (29→29), `CTeleType` 10 (35→34);
- `CTurret` 16 (18→26), `zdb::CMesh` 16 (8→7), `CConsole` 14 (4→4), `CAiState` 13 (10→18);
- `CZBodyAnim` 13 (5→3), `CZSIScript` 13 (4→3) and `CSTable` 10.

**In neither image, so non-virtual (27).** The test cannot tell dropped from alive, because a class without
virtuals has no RTTI string in either build:

- `CZAnim` 61, `CNetCnf` 38, `CAiPath` 29, `CZPersonaState` 24, `OrdersMenu` 24, `CCharacterType` 21,
  `CPickup` 21, `CZAnimSet` 21;
- `CPipe` 19 (research/11's render pipeline object), `Particle::Source` 18, `CZAmmo` 17, `CZBodyAnimBlend` 17;
- the two anonymous-namespace menu and soft-keyboard classes, 16 each;
- `CZNetGame` 16, `CGraph` 15, `Headset` 13, `CRdrFile` 12, `CSndJukebox` 12, `CZNetVoice` 11;
- `zdb::CGSTexBuffer` 11, `CAiTarget`, `CAiVisMap`, `CCtrlrConfigs`, `CMPEG`, `CRdrEditor` and `CZSIObject`,
  10 each.

The matcher's limit is the same for these (edited bodies), but Goal 3 cannot help. Their routes are position,
call graph, strings and BinDiff.

**Templates (8).** All MSL containers, `std::deque<CCnfStateMachine…>` among them. Not worth naming first.

**Present in the demo only (1).** `CSMOpen` 10: its name string is in the demo and absent from r0001, the
only candidate for a class SOCOM II dropped.

**The qualified-name fix for Goal 3.** Command A resolves each demo `__vt__` class in r0001 twice, by bare
name as `vtable_rtti.py` does and by qualified name:

```
demo __vt__ classes 248: nested 38, nested resolved only when qualified 37, resolved, bare name 164,
resolved, qualified name 200, template 14, top-level 196, r0001 vtables located (qualified) 240,
r0001 vtables located (qualified) that sit on a csv FUN_ row (data exported as code) 70
```

Metrowerks writes a nested class's RTTI string qualified: `"zdb::CNode"`, not `"CNode"`. So 37 of the 38
nested classes resolve only by the qualified name, among them `zdb::CNode` (80 methods, 14→15),
`zdb::CWorld` (54, 17→18), `zdb::CCamera` (42, 14→15), `zdb::CVisual` (38, 7→6), `zdb::CMesh` and
`zar::CZAR`. The qualified lookup resolves 200 classes where the bare one resolves 164. Command A also
refines the resolve in one way. It counts a "vtable" only where a function start follows the two-word header.
Word 1 may be non-zero, because a secondary-base vtable carries the this-adjustment there (CZSealBody's
0x669210). This drops the derived classes' RTTI objects that `vtable_rtti.py`'s "several" bucket counted.

## What this means for a task

| task | finding | what it changes |
|---|---|---|
| Goal 3 (Task 7c, vtables) | Resolving by the qualified RTTI name opens 200 demo vtable classes against 164 by bare name. 37 nested `zdb::`/`zar::` classes resolve only when qualified (§5) | `vtable_rtti.resolve` and 7c's pass must look up `'::'.join(path)`; question 6's "the qualified Q2 name" is confirmed with a count. Test on `zdb::CNode`: string present, 1 vtable, 14→15 slots |
| Goal 3: which classes first | 203 classes have an r0001 vtable (2,302 unplaced methods), and 68 have one vtable with equal slot counts (544 methods, command A `[5]`). By unplaced methods and payoff: **CSealCtrlAi** 142 (40→44) with CSealCtrl 94 / CSealCtrlSquirm 13 / CRemoteCtrl (39/40→44, the +4 family, README); **CZSealBody** 358 unplaced (25→26 + 7), where slot 3 is the MoveScale probe site 0x551ec0 and 0x553ea0 / 0x5533e0 build its vtable; **zdb::CNode** 70 (14→15); **CEntity** 45 (18→26); **CSnd** 41 (9→12, the music hooks' neighbourhood); **zdb::CCamera** 37 (14→15, `camCfg`'s neighbourhood); the FTS HUD set (CZNewHudMap, CWeaponSel, CZObjectiveList, BitmapReticule, CZPauseTest; 21→26/27) | The 7c plan's first targets, and its first fixed points: 0x553ea0 as the CZSealBody constructor (vtable store + positional gap containing `__ct__10CZSealBodyFPQ23zdb5CNodeP14CCharacterType` + research/11), and `actor_vtable` 0x6691a0 named as CZSealBody's vtable in `guest_addresses.py`'s comment |
| Goal 3's limit for online play | CZOnlineLobby, CNetCnf, CZNetwork, CZNetGame, CZSealState, CZBombState, CZPersonaState, CZNetVoice and Headset have no RTTI string in either build (§4.1) | Do not plan online naming on vtables. Their routes are §4.2's binding table, question 7's call graph, question 8's strings, positional leads and BinDiff |
| a new pass: `ui-binding` (research wave → plan) | The r0001 binding table's 207 handlers are all auto-named; 124 get a demo name by command string; 83 more are named only by their command string; 3 agree with Task 7, 0 disagree (§4.2) | A task: a proposals file whose rule is "the r0001 row's command string equals a demo row's string → the demo handler's name". Its evidence is the table, not the body. Checks: agree/disagree with the 987 and with any BinDiff pair. Score below `exact`; the ruling is the controller's. The 83 r0001-only rows could take `UI<command>`, the demo's own convention in 131 of 147 rows, marked as convention |
| Goal 1 / the spec §1 and the README's numbers | The class count by class path is 972 (1,210 by the README's rsplit key; the README's 1,212 does not reproduce); CZSealBody is 369, CZKit 114, CSealCtrlAi 142 (§1) | Quote 972 / 369 in the plan; the rsplit key is not a class |
| Question 1 / Task 1 (the csv) | 70 of the 240 r0001 vtables located by RTTI sit on a csv `FUN_` row, CZSealBody's two among them (`FUN_006691a0`, `FUN_00669210`, 256 B each, overlapping) (§3, §5) | Data exported as code. Rows the rename pass must not name as functions. Question 1 / Goal 3 should list them. The vtable pass should refuse to "name" a row that is itself a vtable |
| the hooks (`socom2_addresses.h`, the overrides) | 27 of 33 function fields and 29 of 40 wrap addresses are named by nothing on disk (§3). Leads with an address, no name: netbExOpen/TcpRecv/Available ↔ `sceBInetOpen`/`sceBInetRecv`/`sceBInetGetAvailBytesToRead` (1-for-1 gaps research/45 refused for want of a body key); dnasSha1Hash ↔ `SHA` (an 8/7 gap); oskOpenThunk = `GetTextInput` → `OnGetTextFromUser`; dnasCheck = `DNASAuthenticate`; 0x553ea0 = the CZSealBody constructor | A hand-review queue of six leads for Goal 1's `hand` pass, each with its evidence line; question 9's offset multiset (research/54) is the body check to run on the three `sceBInet` leads first |
| the render hooks (node, node2, defer, flush) | They sit in a gap whose demo twins are 7,082 functions apart: no positional handle, no vtable, not in reCOM (§3) | Named last. BinDiff (question 4) is their only lever on disk |
| Q5 / question 11 (voice) | The demo names nothing in SOCOM II's voice path: 0 `Sase`, 0 `rt_audio`; its LPC-10/PTT stack (67 functions) and CZNetVoice (11) / Headset (13) are SOCOM 1's and 0 are placed. r0001 carries RTIME `rt_audio 1.08.0009` with `codec.c`, `grid.c`, `audio.c`, absent from the demo (§4.1) | Question 11's note starts from the strings and `rt_audio`'s CVS paths, not the demo; that `rt_audio` wraps SASE is an inference to test by call structure |
| research/45's positional leads | The online classes with leads: rt_msg_client_* 19, CZBombState 3 new (`UninitBomb`, `InitBomb`, `ChangeBombState`), CZGrenadeState 4; CZOnlineLobby, CNetCnf, CZNetwork, CZSealState 0 (§4.1) | Sort question 9's hand-review queue so these come first after `ToQuat` |
| Goal 5 (ccc / DWARF1) | The `.debug` holds 959 compile units; 880 have pc ranges covering 879 functions, 428 of them FTS (37 files, the HUD and menu states) and none online (§2.2) | The types walk starts from the CU ranges command A already parses; its prize is the FTS HUD classes, not the network layer |

The stop rule applies to three things, which are not on disk:

- which demo function each chat reader is (the Medius callback names are semantics, not evidence);
- whether the binding wrappers' callees are CZOnlineLobby and CNetCnf methods (question 7's hop);
- whether `rt_audio` calls the SASE units.
