# 11 — reCOM applicability assessment (2026-09-07)

Subject: `tools/reference/reCOM` (git-ignored clone of https://github.com/NotEnoughPhotons/reCOM,
HEAD `5b05af1d`, single squashed commit dated 2026-06-29 "gamez: Remove all PC dependent stuff").
A Ghidra-driven C++ source reconstruction of the GameZ engine and the SOCOM application layer,
written against **SOCOM 1 (SCUS_972.05, May 2002 build)** with symbol names taken from a demo disc,
targeting the Metrowerks MIPS compiler. This note says what in it maps onto *our* binary
(SOCOM II r0001, `game/overlays/socom2_game.elf`, decomp `game/analysis/socom2_game.elf.decomp.c`),
what it is good for, what it is not, and what to read next.

Method (all read-only, reproducible): every string literal in reCOM's `src/**/*.{cpp,h}` (540 with
4..60 chars, no `%`) was looked up in `game/analysis/socom2_game.elf.strings.txt`; **422 of 540 are
present in our ELF**. Each hit was then attributed to the `FUN_xxxxxxxx` whose body references the
string's address in the decomp (scratch script, `// ---- FUN_ @` markers). Pairs below marked
**[verified]** were additionally checked by reading the decomp body against the reCOM .cpp; pairs
marked **[string-match]** rest on the literal set alone; **[guess]** is a guess.

Conventions: addresses are ELF virtual addresses of the game overlay (the strings file also lists
the 0x20xxxxxx / 0x30xxxxxx mirrors — ignore those). Sizes are from `recomp/socom2_ghidra.csv`.

---------------------------------------------------------------------------------------------

## 1. What reCOM contains, module by module, and what it labels in our binary

Overall size: ~28.4k lines across `src/` (headers included), 72 `TODO`s, many `.cpp` files empty
(0 bytes). Headers are the most valuable part: class layouts and enums were transcribed from the
demo disc's debug symbols, and those match SOCOM II far more often than the function bodies do.
The 461 plain-text `.rdr` files under `data/s1/` (SOCOM 1 dialogs, ui, mission folders) are the
second most valuable part: they are the *uncompiled* form of what our `READERC.ZAR` holds.

### zNetwork (6 files, 501 lines; `znet.h` is the substance, the .cpp are skeletons)
Covers: `CZNetwork` (session/medius state block: server IP/port strings, `m_bMediusEnabled`,
`m_bNetCnfRequired`, RSA pubkey, session/access keys), `CZNetGame` (round/bomb/team valves,
`BSEALLISTVAR`/`BTERRLISTVAR`/`BCHATLISTVAR` UI vars), `CZNetVoice` (PTT), `CZOnlineLobby`,
and the enums `LOBBY_STATE`, `MP_MAJOR_GAME_STATE`, `MP_GAME_TYPE`, `CZNetwork::EVENT`.
No Medius/DME/libnet code at all (`zNetDme.cpp` is empty).
Labels in our binary:

| ours | reCOM name | evidence |
|---|---|---|
| `FUN_002a76d0` (0x2a76d0, 1636 B) | `CZNetGame::Initialize` | **[verified]** creates the same UI vars and valves in the same order: `BSEALLISTVAR`, `BTERRLISTVAR`, `BNONELISTVAR`, `BCHATLISTVAR`, `mp_major_game_state`, `mp_join_game`, `player_team`, `late_joiner`, `mp_45_sec_clock`, `mp_penalty`, `player_join_count`, `player_ready_count`, `mp_persistent`, `mp_bomb`, `mp_game_over`, `bomb_owner` |
| `FUN_002e0450` (0x2e0450) | `CZOnlineLobby::Init` | **[verified]** `MEDIUS_LOBBY_NAME`, `GAMENAMEVAR`, `CLANNAMEVAR`, `Clan_Description`, valve `socom_online_state` — exactly the commented-out lines in `zNetMedius.cpp` |
| `FUN_001f3bf0` (0x1f3bf0, 2128 B) | menu-state `PostEvent(name)` → `CZNetwork::EVENT` id | **[verified]** string ladder `ONSTART`=0, `ONEXIT`=1, `ONACTIVATE`=2, `ONMPEGEND`=3, `MP_JOIN_ROOM`=4, `MP_PLAYER_NOT_FOUND`=5 … `ON_STATE_POP`=0xd, `ON_SKB_APPLY`=0xe, **`ON_SKB_APPLY2`=0xf (SOCOM II addition)**, `ON_SKB_CLOSE`=0x10 … i.e. reCOM's enum order with one insertion after ON_SKB_APPLY. Callers: shell state update (`FUN_001f45e0`, `FUN_001f4d20` with `MP_SYSTEM_MESSAGE`), `InitNetwork`/`NetCnfOpen` handlers, DNAS/net-config code (`FUN_002ca840`, `FUN_002ca9a0`) |
| `FUN_001f4860` (0x1f4860) | `CMenuState::Init` (SOCOM II variant) | **[verified]** `readerc.zar`+`run/ui` → `CRdrArchive::AddArchive` (`FUN_0032c1e0`) → `CZAR::ReOpen` (`FUN_00258b40`); `LoadWorld("ui")` = `FUN_001e91c0` (0x1e91c0, 4204 B, reads `worldmodel`); `common/assetlib/font` and `ui/assetlib/uisk` via `CAssetMgr::GetLoadedLibRef` = `FUN_00320d70`; `ZuiInit` = `FUN_0038d6a0` (reads `UiParams.rdr`); `uisounds.rdr` in `data/common/dialog` → tags `SOUNDS`/`TELETYPE`/`SELECTION`(S2: was `BACK`); `CSnd::LoadSounds("sounds.rdr","HUDUI"/"UIVOICE"/…)` = `FUN_00344090`; `run/uizanim.zar`; and the **`NETCNF_REQUIRED` UI variable** is written here from `DAT_0045a1c9` through `FUN_00351ff0(name,2)` (the UI-variable reader already in HANDOFF) — this is `CZNetwork::m_bNetCnfRequired` surfacing to the shell. `FUN_001f53d0` is a second, shorter copy of the same routine (probably the re-Init after `POP_TO_MENU_STATE` — **[guess]**) |
| `FUN_00245ad8` | libnet `CallRpc` | **[verified]** (already in `docs/research/10`); reCOM has no equivalent — libnet is Sony SDK code, not GameZ |
| `FUN_0027e610` | `SwitchMenu` binding → `PostEvent` | **[string-match]** |

reCOM's `LOBBY_STATE` / `CZNetwork::EVENT` / `MP_*` enums are the direct key to the `socom_online_state`
valve values and the event ids that `dlgNet*.rdr` scripts test. The struct field names of `CZNetwork`
(`m_ServerIP[32]`, `m_MediusIP[64]`, `m_SessionKey[17]`, `m_AccessKey[17]`, `m_PubKey`) are what the
1.50 Medius client fills; use them when naming the globals around 0x6561b0/0x686f14 noted in STATUS.

### zMPEG (2 files, 49 lines) and zVideo (4 files, 189 lines)
zMPEG is only `CMPEG::Uninit` with five allocation flags (`mpegBuffAlloc`, `rgb32Alloc`,
`path3tagAlloc`, `demuxBuffAlloc`, `audioBuffAlloc`). zVideo is the `_zvid_public` struct (frame
counters, `doMpeg224`, `pcrtcDo`, `renderBuf`, `textureBaseAddr`) and stubs. Thin, but the struct
names the fields of our video-state block, and the five-buffer list names what `FUN_00309a10` frees.
Labels (movie path — see §2a for the mechanism):

| ours | name | evidence |
|---|---|---|
| `FUN_003098e0` (0x3098e0, 292 B) | `MpegStart(path, loop, flag, arg)` — the movie player entry | **[verified]** referenced with `socom.pss` (intro) by `FUN_001ed560`; called by the menu background path and by `FUN_00366a00`/`FUN_00367950`; allocs a 0x48 ctx (`DAT_00451cf8`), calls `FUN_0030b4d0(ctx, cb=0x30b9d0, 0x451cc0, …)` and `FUN_003b17d0(0x1e)` |
| `FUN_003096f0` (132 B) | `MpegStop` | **[verified]** the stop half of the same pair |
| `FUN_00309a10` (300 B) | `CMPEG::Uninit`-like buffer free (`DAT_00451cc0`, `DAT_00451cc8` …) | **[guess]** mirrors reCOM's five-flag Uninit |
| `FUN_00309b40` (1044 B) | MPEG buffer alloc / init | **[guess]** called once when `DAT_00451cc0 == 0` |
| `FUN_001bc3e0` | sceMpeg error print (`[MPEG ERROR]%s`) | **[string-match]**; the sceMpeg/sceIpu SDK functions themselves are already named in `recomp/socom2.toml` (0x1BAB08..0x1BC480, 0x1A31A8..0x1A34B0) |
| `FUN_003b1200` (0x3b1200, 420 B) | `zVid_Init` | **[verified]** creates valve `lodLevel` (the only string in reCOM's `zVid_Init`) |

### zArchive (3 files, 1621 lines) — the most complete module
Covers the ZAR container: `HEAD`/`TAIL` structs, `ZAR_VERSION_1 0x20001` (tail at EOF-96) and
`ZAR_VERSION_2 0x20002` (head at offset 0), key records, string table, "securify" (byte-wise
`~x`), `Open/ReOpen/ReadDirectory/ReadDirectory_V2/Fetch*/Insert/WriteDirectory`. The header
comment says V2 "only works on release S1 and demos of S2" — **that is wrong for us in the good
direction**: retail SOCOM II files are plain (unsecured) V2 archives and parse exactly as reCOM's
`ReadDirectory_V2` describes. **[verified]** on disc:

```
RUN/UI/READERC.ZAR : flags=0 keys=111 stable=2190 stable_ofs=0x11755140 pad=16 datasize=0x1320b0 crc=0 appver=1  version=0x20002
RUN/UI/UI_MDL.ZED  : flags=0 keys=198 stable=826  stable_ofs=0x113bb458 pad=16 datasize=0xc1730  crc=0 appver=-1 version=0x20002
```
Layout (from reCOM `zar.h`/`zar_main.cpp`, confirmed by parsing the two files above): HEAD is
**25 words / 100 bytes** (`flags, key_count, stable_size, stable_ofs, padding, reserved[16],
offset(=data size), crc, appversion, version`); then the string table (`stable_size` bytes); then
`key_count` × 16-byte keys `{s32 name_ofs, u32 offset, u32 size, s32 child_count}` in pre-order
(root first, `name_ofs` is relative to `stable_ofs`, the address the table was packed at); then
align to `padding`; then the data blob. `READERC.ZAR` lists 111 keys = the 111 `.rdr` dialogs in
HANDOFF; `UI_MDL.ZED` keys are model names each with a `N000_000` child (node data), i.e. a ZED is a
ZAR with the node tree as keys. With `flags != 0` the header/stable/keys/data are securified (XOR
0xFF); retail files are not.
Labels:

| ours | name | evidence |
|---|---|---|
| `FUN_00258000` (0x258000, 1288 B) | `CZAR::ReadDirectory_V2` | **[verified]** reads 100 bytes, tests `== 0x20002`, copies `reserved[16]` with an 8-iteration 8-byte loop, allocs `stable_size` (+0x40), key bytes `key_count<<4`, `(pos + key_size + 100) % padding` alignment, honours `mode & 0x20` to keep the file open instead of slurping the data (`m_rootOffset` at +0x30) |
| `FUN_00257590` (856 B) | `CZAR::WriteDirectory` (V2) | **[verified]** sets +0x98 = 0x20002, packs the string table, pads with 100 + key bytes |
| `FUN_002590a0` (400 B) | `CZAR::CZAR(name, io)` | **[verified]** used as `FUN_002590a0(&zar,0,0)` before every Open |
| `FUN_00258920` (540 B) | `CZAR::Open(name, version, mode, padded_size)` | **[verified]** `CSnd::Init` calls it as `Open(path, 0, 0x21, 0x10, 0)` — reCOM's `m_vagArchive.Open("RUN\\SOUNDS\\VAGSTORE.ZAR", 0, 0x21, 16)` verbatim |
| `FUN_00258b40` (144 B) | `CZAR::ReOpen(appver, mode)` | **[verified]** `AddArchive` result → `ReOpen(x, 1)` in `CMenuState::Init` |
| `FUN_00258ce0` / `FUN_00258f20` | `CloseKeepDir` / `Close(bool)` | **[guess]** by call order after Open in `CSnd::Init` |
| `FUN_002578f0`, `FUN_0025b030`, `FUN_0025af10`, `FUN_002597b0`, `FUN_002599b0` | key-count / `CKey::Read` / `fixupKey` / key-buffer helpers | **[guess]** callees of the two directory functions |
| `FUN_0024a5a8` | *not* ZAR (0x20001 is a stack offset there) | — |

### zReader (9 files, 2084 lines)
Covers the LISP-like `.rdr` reader: `_zrdr` node (`type:8, isclone:1, packed:1, unused:6,
length:16` + union `{real, integer, string, array}`; array element 0 holds the count), the
tokenizer (`;` comments, `"` strings, `( )`), the `#ifdef/#else/#endif/#include` preprocessor,
`zrdr_find{tag,string,int,real,bool,PNT2D,PNT3D}`, `CRdrFile::Load` from a ZAR key with the
`_resolveA/_resolveB` pointer relocation (compiled rdr = node array + string table with relative
pointers), `CRdrArchive` (list of open `readerc.zar`/`readerm.zar`), `_OutputASCII` writer.
Labels:

| ours | name | evidence |
|---|---|---|
| `FUN_0032f630` (0x32f630, 1240 B) | `zrdr_read(name, path, flags)` | **[verified]** every rdr open in the menu/mission init goes through it |
| `FUN_0032f0d0` → `FUN_0032f0e0` | `zrdr_findtag` (8-byte thunk) → `zrdr_findtag_startidx` | **[verified]** |
| `FUN_0032ee10` (264 B) | `zrdr_findstring` | **[verified]** |
| `FUN_0032d6e0` (144 B) | `zrdr_free` | **[verified]** |
| `FUN_0032c1e0` (200 B) | `CRdrArchive::AddArchive(name, path)` | **[verified]** |
| `FUN_0032e250` (420 B) | `zrdr_tobool` (compares `"false"`; `"true"/"on"/"off"` nearby) | **[string-match]** |
| `FUN_005e3ff0` | `_get_pptoken` (`#include`) — the ASCII preprocessor survives in retail | **[string-match]** |
| `FUN_00351ff0` / `FUN_00351a90` | `CUIVarManager::Get(name,type)` / `CValve::Parse` (`valves`,`value`,`PERSIST`) | **[string-match]**; `FUN_00351ff0` was already identified in HANDOFF |

The compiled-rdr byte format on disc (extracted `dlgMenu.rdr` from `READERC.ZAR`, 10880 B):
`01 00 00 00 | a1 11 00 00 | b0 11 00 00 | "SCREENS\0LIBRARIES\0ui/assetlib/ui2d\0…"` — a 12-byte
header {1, string-table size 0x11a1, node-array offset 0x11b0}, then the string table, then the
node array **[guess on the header meaning; the string-table/array split is certain]**. reCOM's
`CRdrFile::Resolve` (`zrdr_file.cpp`) is the relocation to read against `tools_py/rdr_tree.py`.

### zRender (5 files, 800 lines) / zVisual / zNode / zTexture
`zrender.h` has the `_RenderPhase` enum (WORLD, HUD_OBSOLETE, CHARSET, COMMON, CHARSET1..8, ALPHA,
HUDSET1/2/SMALL, SHADOW, CHARSETCUSTOM), `CPipe` (the render pipeline object: camera, 128-entry
`m_texLoadChain`, per-phase `CGSTexBuffer`s, opacity stack, `m_simpletrans`/`m_doUI` flags),
`CStack` (64-entry matrix stack), LOD/material/prelight band structs. `zrndr_pipe.cpp` has
`RenderNode`/`RenderWorld`/`RenderVisual`/`RenderUiNode` bodies with the VU/GS parts stubbed.
`node_saveload.cpp` documents the `.ZED` naming (`run/<lib>/<4-char root>_txr.zed`, `_pal.zed`,
`_mdl.zed`, keys `textures`/`palettes`/`models`/`renderphase`), `ztex.h` the `TEXTURE_PARAMS`
bitfield (`texelBitSize`, `selectQwc`, `pal_offset`, `transparent`, `palettized`, `bilinear`…).
Labels:

| ours | name | evidence |
|---|---|---|
| `FUN_00318da0` (0x318da0, 2000 B) | `CSaveLoad::Load` / world root read (`worldmodel`, `GlobalLighting`, `NightMission`, `LensFX_NVG`, `LensFX_StarlightScope`, `MetersPerUnit`, `ShadowVector`, `assetlibs`, `cameras`, `light_list`, `GriddedTerrain`, `DefaultMaterial`) | **[string-match]** |
| `FUN_003197e0` (468 B) | `CSaveLoad::LoadTextures_PS2` (`renderphase`, `textures`) | **[string-match]** |
| `FUN_003196a0` (316 B) / `FUN_003195a0` | `LoadPalettes_PS2` (`palettes`) / models loop (`models`) | **[string-match]** |
| `FUN_00310f20` (760 B), `FUN_00311220`, `FUN_00311330`, `FUN_00311520`, `FUN_00310da0` | `CNode::ReadDataBegin` and siblings (`visuals`, `children`, `matrix`, `NodeType`, `model_name`, `regionmask`, `nparams`) | **[string-match]** |
| `FUN_003c3570`, `FUN_003c4190` | visual detail/LOD readers (`vparams`, `detail_cnt`, `detail_buff`, `vtype`) | **[string-match]** |
| `FUN_00322470`/`FUN_003c38c0` | texture fallback (`null_xmas.bmp`) | **[string-match]** |

Not labelled by reCOM: the VU1 packet builders (`FUN_0033b110`, `FUN_003389c0`, `FUN_00339de0`,
`FUN_0033bf30`…) — reCOM stubs everything below `CVisual::Render`.

### zUI (6 files, 402 lines) and zTwoD (9 files, 1566 lines)
zUI: `CGameDlgDesign` (`BACKGROUND TYPE IMAGE|MPEG`, `FILENAME`, `ANIMATIONS`, models), the
object-spec classes (`CTextSpec`, `CImageSpec`, `CTtySpec`, `CWrapSpec`, `CTickerSpec`,
`CHProgressBarSpec`, `CCounterSpec`, `CClockSpec`), `CUIVariable`/`CUIVarManager`, `UIVAR_LONGEVITY`.
zTwoD: `C2D` base (vtable order: Parse, GetAssetLibs, Draw×2, Reset, Tick, TickZAnimCmd,
ParseZAnimCmd, HandlePad, SetActive, SetNormal, SetTrans, SetUseFrameBufferAlpha, SetMapOffset),
`C2DBitmap` (two RGBA rows, two UV rows, tex handle), `C2DString`, `C2DFont`/`C2DFontEntry`
(`offset, width, displaywidth, xspacing, top, bottom, baseline, lKerning, rKerning`), `C2DMessage_Q`,
`C2DButton` with four `ButtonState`s. Labels:

| ours | name | evidence |
|---|---|---|
| `FUN_00381550` (0x381550, 1660 B) | `CGameDlgDesign::LoadFromRdr` (SOCOM II) | **[verified]** `BACKGROUND`→`TYPE`: `IMAGE`→+0x30=0, `MPEG`→1, **`MPEG_LOOPING`→2**; `FILENAME`→+0x18; `USES_MEMCARD`→+0x71; `NOFONTLIB`→+0x70; `LIBRARY`/`LIBRARIES`, `SCRIPT_LIBRARY`, `OBJECTS`, `ANIMATIONS` loop |
| `FUN_00382070` (1512 B) | `GetObjectSpec` (`TEXT`, `IMAGE`, `TELETYPE`, `WRAPPEDTEXT`, `PROGRESSBAR`, `COUNTER`, `CLOCK`, `CAPTION`, `HCENTERED`, `SCALE`, `COLOR`) | **[verified]** same dispatch as `zui_spec.cpp` |
| `FUN_0037da50` (712 B), `FUN_00383360` | `LoadDlgObjects` (`CHILDOF`) | **[string-match]** |
| `FUN_00380620` (3184 B), `FUN_0037eab0` (5808 B), `FUN_0036e880` (4928 B) | per-object-type Parse (XSIZE/YSIZE/UIVAR/CAPTION…) — the `C2D::Parse` overrides | **[string-match]** |
| `FUN_00359c40` (1260 B), `FUN_0035b7f0`, `FUN_0035bef0` | `C2DFont::Load` (`charoffsets`, `glowtexture`, `xspacing`, `lKerning`, `rKerning`, `baseline`, `faces`) | **[string-match]** |
| `FUN_002b6fc0` | `C2DMessage_Q::Init` (`TtySpeed`, `XMargin`, `YMargin`, `maxlength`, `maxsize`, `spacing`, `descends`, `centered`, `fadetime`) | **[string-match]** |
| `FUN_00367950` (0x367950, 3028 B) | `CGameMenu::Init/LoadFromDesign` | **[verified]** — see §2a |
| `FUN_00366a00` (256 B) / `FUN_00366b10` | `CGameMenu::StartBackgroundMovie(name)` / `StopBackgroundMovie` | **[verified]** `FUN_001f3bd0` = `j 0x366a00; lw a0,8(a0)` and `FUN_001f3be0` = `j 0x366b10; lw a0,8(a0)` (ELF words checked): 8-byte trampolines that pass `shellState->menu` (+8) — the gotcha-1 shape; both already recompile. `FUN_00366940` (184 B) is a sibling that also writes the running flag (restart/toggle, **[guess]**) |
| `FUN_00367810` | `CGameMenu::FireEvent(eventId, arg)` | **[verified]** walks the design's `ANIMATIONS` records (count at menu+0x8d8, 16-byte entries, event id at +0x705) and starts each matching `ANIMATION` through the script runner (`FUN_0026a250(0x414bb0, anim, 0)` → `FUN_00272bb0`/`FUN_002734b0`) — i.e. `EVENT ( ONMPEGEND ) ANIMATION ( x )` handlers |
| `FUN_0038d6a0` (196 B), `FUN_003943e0` | `ZuiInit` (`UiParams.rdr`, `data/common`) | **[verified]** |

### zSave (4 files, 76 lines), zSound (6 files, 490 lines), zSystem (11 files, 594 lines)
zSave: only the `CSaveManager`/`CSaveModule` shape (module name, priority, flags, ZAR key; the
save is a ZAR of per-module `.rdr`). zSound: `CSnd`/`CSndInstance`/`CSndJukebox` layouts,
`VAGSTORE.ZAR` open, `sounds.rdr`, `snd_InitVAGStreamingEx(6, 0xf000, 1, 1)` comments (989snd
calls are commented out). zSystem: `_zsys_public` (DMA handles, SPR double-buffer packets,
`isT10K`, `timerTicksPerSecond`), `CSched_Manager` (the named-task scheduler: `AddTask(name, fn,
priority, registrar)` — this is what registers `UnitTick`, `ai_pre_tick`, `diTick`, `ParticleTick`
seen in our mission logs), `CTTY`. Labels:

| ours | name | evidence |
|---|---|---|
| `FUN_0034d190` (0x34d190, 712 B; `FUN_0034d180` = 8-byte thunk) | `CSnd::Init` | **[verified]** opens `RUN\SOUNDS\VAGS_ENG.ZAR` then `RUN\SOUNDS\VAGSTORE.ZAR` (S2 adds the language VAG archive), `Open(…,0,0x21,0x10)`, `CloseKeepDir` |
| `FUN_00345040`, `FUN_003450f0`, `FUN_00345170`, `FUN_00345230` | `CSnd::Open` / `NetOpen` / `UIOpen` / … (each reads `sounds.rdr`) | **[string-match]** |
| `FUN_00344090` (804 B) | `CSnd::LoadSounds(rdr, bankname)` | **[verified]** `("sounds.rdr","HUDUI")` etc. |
| `FUN_00344f30` | `CSnd::GetSoundByName` | **[guess]** by use in `CMenuState::Init` |
| `FUN_001eb8c0` (720 B), `FUN_001ec480` (1208 B) | `CCoreState::Init` (SP / MP variants: `UnitTick`, `ai_pre_tick`, `readerm.zar` remove) | **[string-match]** |
| `FUN_001eca50` (184 B) / `FUN_001e7530` (364 B) | `CCoreState::CCoreState` (`"CoreState"`) / `CMenuState::CMenuState` (`"MenuState"`, `dlgIntroScreen.rdr`) | **[verified]** |
| `FUN_002adbc0` (844 B) | `CMission::CMission` (`CSaveModule("CMission")`) | **[string-match]** |

### zFTS (23 files, 1105 lines; `fts_mission.cpp` is real, the rest empty) and zGame (10 files, 389 lines)
`CMission::Init/PreOpen/Read/OnMissionStart/OnMissionComplete/Tick`, `CGame`/`COurGame`
(state stack of 16, `Switch`, `StartEngine` order), `CGameState` vtable (PreInit, Init, PreUnInit,
UnInit, Tick, OnPop, OnPush), `CMenuState`/`CCoreState`/`CLoadState`/`CCinematicState`/`CExitState`.
Labels:

| ours | name | evidence |
|---|---|---|
| `FUN_002ad290` (0x2ad290) | `CMission::Init` | **[verified]** `HUD_ON/HUD_OFF/HUD_LETTERBOX_ON/OFF` AddCmd, `readerc.zar` in `run` and `run/ui`, `global_valves.rdr`, valves `mission_complete/failure/abort/timeout/nofade`, `orders/materials/decals/fonts/messages/subtitles/small_messages.rdr`, `character.rdr`, `ai_turrets.rdr`, `hud.rdr` (`static_radio`, `dynamic_radio`); S2 adds `mpeg_subtitles.rdr` |
| `FUN_002acc10` (1652 B) | `CMission::PreOpen(db)` | **[verified]** `mission.rdr`, `LoadingScreenAssets`, `UiVars`, `Valves`(`PERSIST`,`VALUE`), `WEAPON_MODEL_POSTFIX` |
| `FUN_002aab20` | `CMission::Read` (`ai_params`, `weather_factor`, `respawn_time`, `respawn_fade`; S2 adds `init_aim_pitch`) | **[verified]** |
| `FUN_002abd40`, `FUN_002ac410` | `CMission::OnMissionStart` / `OnMissionComplete` (touch the five mission valves + `readerm.zar`) | **[string-match]** |
| `FUN_002af8c0`, `FUN_002afa10` | `CreateCustomCharTypes` ×2 (`UiVehicles`) | **[string-match]** |
| `FUN_002b3470` (44 B) | `CVehicleRdr::Open` (`vehicles.rdr`) | **[string-match]** |
| `FUN_001fdee0` (564 B) | `hudInit` (`hud.rdr`, `data/common`, `TacMap`, `Polygons`, `Lines`) | **[verified]** |
| `FUN_001c4cc0` (3316 B) | the **loader's** `main()` (research/05), which shows `LOADING.RAW` before the overlays boot — the S2 home of reCOM's `CVideo::RestoreImage("RUN\\LOADING.RAW", raw)` | **[verified]** string at 0x1d4458 is in the SCUS_972.75 segment (0x100000..0x1d5000) |
| `FUN_001e7040` | `CGame::Tick` loop (already in HANDOFF as the top loop) | — |

### zAnim (9 files, 1786 lines), zValve (3 files, 497 lines), zAI
`zanim.h` lists every animation-script command name and the `DATATYPE_*` ids of SOCOM 1;
`anim_main.cpp` has the (commented) `AddCmd` registration order. `zvalve.h` has `CValve`
(16-bit value, `VTYPE_PERM/TEMP/PERSIST`, callback list) and the `OP_*` comparison ops used by
`VALVE ( name == 0 )` expressions. Labels:

| ours | name | evidence |
|---|---|---|
| `FUN_0025bc20` (0x25bc20) | `CZAnimMain::InitCommands` | **[verified]** registers, in order, every name in reCOM's list (`QUAD_ALIGN`, `IF`, `ELSEIF`, `ENDIF`, `NODE_ACTIVE`, `NODE_RENDERED`, `RANGE_TEST`, `RANDOM_WEIGHT`, `FAIL`, `ANIM_HEALTH`, `ANIM_LOD`, `LOOP`, `WAIT`, `OBJECT_*`, `PARTICLE_SOURCE`, `CAMERA`, `DESTRUCTION_SOURCE`, `SOUND`, `LIGHT`, `WHILE`, `END_WHILE`, `EXPRESSION`, `BREAK`, `CALL_ANIMATION` … `TIMER`, `FIRE_WEAPON`, `ui::UI_COMMAND`, `ui::UI_APP_COMMAND`) plus the S2 additions (`VALVE`/`VBIT`/`VWATCH` etc. — HANDOFF's ids) via `FUN_0026a8e0(0x414bb0, name, parse, create, exec, post)` |
| `FUN_00293890` (288 B), `FUN_0029bc20` | `zdb::CCamera::RegisterAnimCommands` / `CAppCamera::RegisterAnimCommands` (`CAMERA_INDOORS`, `CAMERA_PARAMS`, `DYNAMICS_*_CAMERA`, `SET/GET_CAMERA_REGION_TEST` / `CAMERA_3RD_PERSON`) | **[string-match]** |
| `FUN_005de320` (2028 B) | `CSealCtrlAi::RegisterCommands` (all `ai::*`) | **[verified]** by the complete `ai::` name set |
| `FUN_0027ad60`, `FUN_00372f10`, `FUN_003769c0` | UI-side VALVE/UIVAR command parsers | **[string-match]** |

### zSeal / zCharacter / zWeapon / zCamera / zGrid / zEntity / zMath / zInput
Mission-side. `FUN_0059ba80` (5260 B) is the character-dynamics parameter reader (all `cam_*`,
`max_*`, `*_accel`, `FALLING_DAMAGE_*`, `THROW_PARAMS` keys = reCOM `char_dyn.cpp`); `FUN_00553ea0`
the skeleton reader (`skel_root`, `lbicep` … `rthigh`, `aimnodes`, `rifle_out`); `FUN_00575490` the
AI state-name table (`animate`, `avoid`, `breach`, `deploy`, `follow`, `hostage`, `lasing`, `pursue`,
`rescued`, `stunned`, `surrender` …); `FUN_00533370` the character flag parser (`debug`, `disabled`,
`display`, `nofade`, `noshoot`, `nosnooze`, `recycle`, `setup`); `FUN_002d5420` `grid_params`;
`FUN_005550d0` `dynamics.rdr`; `FUN_00288b80` `run/motion.zar`. All **[string-match]**.
`zinput.h` gives the `PAD_BUTTON` order (START, SELECT, RIGHT, LEFT, UP, DOWN, TRIANGLE, CIRCLE,
SQUARE, CROSS, R1, R2, L1, L2, RSTICK, LSTICK) and `KEY_STATE` (UP, FALLING, DOWN, RISING) — the same
0/1/2/3 per-button states HANDOFF found at `DAT_0044f108+1+idx`.

### Apps/FTS (38 files, 1301 lines)
`main.cpp` (`process_arguments`, `zSysInit`, `theGame.StartEngine/StartPlay`, `Tick` forever),
`st_menu.cpp`/`st_core.cpp` (the two state Inits above), `game/database.cpp` (`LoadWorld`: node
universe, `run/<lib>/models.zar`, `hookupVisuals`, `DismemberWorldModel`, `GenerateLandmarkList`),
`hud/*` (23 files, only letterbox/pausemenu/newhudmap/main non-empty; `hud.h` has the HUD class
layouts). `getopt.cpp`/`options.cpp` are empty — the `_options gopt` struct in `zgame.h` is the
list of debug switches (`doHud`, `noDie`, `infiniteAmmo`, `doRenderReport` …) that the retail
binary still parses from `SetDatabase`-style arguments **[guess]**.

### Coverage summary
Of the 540 reCOM literals, 422 exist in our ELF and 419 of those resolve to a function; the
remaining 118 are mostly PC-only strings (`fprintf_s`, SDL comments) and a handful of renamed tags
(`BACK`→`SELECTION`, `MPEG` gains `MPEG_LOOPING`). The named-function yield from this pass is
~70 distinct `FUN_` addresses with a defensible reCOM name (table above), none of which were in
`recomp/socom2_ghidra.csv` (which names 114 SDK/thunk symbols only).

---------------------------------------------------------------------------------------------

## 2. Ranked uses for us

### (a) Naming functions on the online path and the movie path — highest value
**Movie path (M3 item 7 / HANDOFF priority 2)** — now fully traced with reCOM's help **[verified]**:
1. `READERC.ZAR/dlgMenu.rdr` (extracted with the V2 layout above) carries
   `BACKGROUND ( TYPE ( MPEG_LOOPING ) FILENAME ( …/menuloop.pss ) )` and a script command
   `ui::UI_COMMAND ( TYPE ( BackgroundMPEG ) … )`. SOCOM 1's `data/s1/common/dialog/dlgMenu.rdr`
   shows the same pair in plain text, and shows the convention `BackgroundMPEG ( OFF )` before
   `SWITCHMENU ( LOAD_SCREEN )`.
2. `FUN_00381550` (`CGameDlgDesign::LoadFromRdr`) stores the mode at design+0x30 (2 = looping).
3. `FUN_00367950` (`CGameMenu::Init`) — when mode is 1 or 2: copies the filename to menu+0x27c,
   sets menu+0x279 = 1 (has movie), +0x27a = looping, calls `FUN_00350cd0(); FUN_00350fb0();`
   (VAG/CD-priority prep, **[guess]**), then `FUN_003098e0(filename, 1, 0, 0)` and stores the
   result in +0x278 (running). **If the start fails (returns 0) it immediately fires event 3 =
   `ONMPEGEND` via `FUN_00367810(menu, 3, 0)`, i.e. runs the dialog's `EVENT ( ONMPEGEND )`
   animations at once.**
4. The script binding `BackgroundMPEG` (table row 135, fn `0x0027a420`) → `FUN_00366a00`
   (start, via the 8-byte trampoline `FUN_001f3bd0` with the shell object `0x408538`, whose +8 is
   the menu) or `FUN_00366b10` (stop, via `FUN_001f3be0`); argument `OFF` stops, `INPUT_STRING`
   takes the name from the UI input var. `PlayMPEG` (0x27ab30) / `PlayMPEGNoFade` (0x27aa70) are the full-screen
   cinematic path (dlg*Cinematic.rdr post `ONMPEGEND` when done — exactly as in S1).
5. Player core: `FUN_003098e0` start, `FUN_003096f0` stop, `FUN_00309b40` alloc, `FUN_00309a10`
   free, decoder/thread `FUN_0030b4d0` with per-frame callback `0x30b9d0`; below that the SDK
   (`sceMpegCreate` 0x1BB738, `sceMpegGetPicture` 0x1BB990, `sceMpegDemuxPssRing` 0x1BAB08,
   `_sendDataToIPU` 0x1BC480, already in `socom2.toml`).
   First diagnostic for the black menu: `PS2X_CALL_TRACE="0x367950:MenuInit,0x3098e0:MpegStart,0x3096f0:MpegStop,0x27a420:BackgroundMPEG,0x367810:MenuPostEvent"` and read whether `MpegStart` returns 0 (then the menu sees `ONMPEGEND` at once and never retries) or 1 with no frames (then the IPU stub is the whole story). Where the decoded frame goes: follow `0x30b9d0`'s output buffer to the GS upload — reCOM's `_zvid_public::doMpeg224` and `renderBuf` say the frame is composited by the video layer, not by a UI texture (**[guess]** for S2).

**Online path**: reCOM adds no libnet/Medius code, but it names the *game-side* layer above it:
`CZNetwork` fields and `EVENT` ids (`FUN_001f3bf0`), `CZOnlineLobby::Init` (`FUN_002e0450`),
`CZNetGame::Initialize` (`FUN_002a76d0`), `m_bNetCnfRequired` → `NETCNF_REQUIRED` UI var
(`FUN_001f4860`), and the `LOBBY_STATE` enum for `socom_online_state`. The script bindings in the
0x3dd4d4 table complete it: `InitNetwork` 0x276dc0, `UnInitNetwork` 0x27e5c0, `MediusInit`
0x276c60, `MediusEnabled` 0x27aff0, `LobbyConnect` 0x276780, `LobbyDisconnect` 0x274d60,
`LobbyLogin` 0x27dd20, `LobbyRegister` 0x27dde0, `LobbyLogout` 0x27dcc0, `NetCnfInit/Uninit/Open/
Close/CurrCombo/SelectCombo` 0x278040/0x278020/0x277dd0/0x277d50/0x277bf0/0x277ab0,
`NetGetInterfaceList` 0x277970, `IsNetwork` 0x27e6d0, `ForceMediusStatusReport` 0x2776b0,
`DNASAuthenticate` 0x2cc670 (the one bound to ret0), `IsControllerConnected` 0x277150.
`NetGetInterfaceList`/`NetCnfOpen` are the callers of libnetb fno 8/9 that currently return -1 —
they are the next functions to read for the "No Network Adaptor detected" screen.

### (b) File / format documentation
- **ZAR / ZED** — done above; the two on-disc headers parse with reCOM's V2 description. A
  `tools_py/zar.py` (list keys, extract a key, optional un-securify) is a 60-line port of the
  scratch parser used here and would make every `READERC.ZAR`/`UI_*.ZED`/`VAGSTORE.ZAR` inspectable
  offline (VAGSTORE.ZAR is 576 MB: keep `mode & 0x20` semantics, i.e. do not slurp).
- **.rdr (compiled and text)** — `zrdr.h` + `zrdr_parse.cpp` + `zrdr_file.cpp` are the spec;
  `data/s1/**/*.rdr` are 461 worked examples of the text form (dialog `SCREENS/OBJECTS/SPEC/
  ANIMATIONS`, `ui/zrdr`, mission `zrdr`) — the S2 `READERC.ZAR` dialogs use the same tags plus
  `MPEG_LOOPING`, `NOFONTLIB`, `CHILDOF`, `SELECTION`.
- **UI_GEO/UI_MDL/UI_TXR/UI_PAL .ZED** — `node_saveload.cpp` (`_txr/_pal/_mdl` split, `renderphase`
  key, `textures`/`palettes`/`models` key lists), `ztex.h` (`TEXTURE_PARAMS`, `PALETTE_PARAMS`),
  `node_model.h`, `zvis.h` (mesh/visual structs). The model key tree of `UI_MDL.ZED` (198 keys,
  one `N000_000` child per model) matches.
- **Save data** — only the container shape (`CSaveManager` = ZAR of per-module rdr/blobs,
  `CSaveModule(name, priority, flags)`, `"CMission"` module). Our `zSave` functions are unlabelled
  beyond `FUN_002adbc0`.
- **VAG / 989snd banks** — `zsnd.h` names the `CSnd` fields (`m_bank`, `m_ID`, `m_isStreamed`,
  `m_stream1name/2name`, `m_offset1/2`) and `vagReadOffset(name)` = key offset/size inside
  `VAGSTORE.ZAR`, which is what the stream-safe CD reads in `docs/research/06` serve. The bank
  binary format itself is not in reCOM (06 already has it from the IRX).

### (c) Engine behaviours behind tracked parity gaps (`docs/parity/REPORT.md`)
- **Main menu (81) — movie background**: mechanism in (a). Also: `CMenuState::Tick` does
  `zVid_ClearColor(0,0,0)` + `zVid_Swap(false)` each frame, so with no movie frame the background is
  legitimately black, not a rendering bug.
- **Controller-configuration screens skipped after Select Rank (golden s09/s10)**: reCOM only
  has the placeholder `CCtrlrConfigs::Init()` comment in `CMission::Init`, but the string pass gives
  the S2 functions: `FUN_002c5e70` (368 B) reads `controller.rdr` / `ControllerConfigs` in
  `data/common`; `FUN_0027b960` (1420 B, binding `SetControllerConfig` 0x27fb40 is nearby) reads
  `SelectedControllerConfig`, `stick_preset`, `INVERT_PITCH_CONTROLLER`; `FUN_0027b790` =
  `SetStickPreset`; `IsControllerConnected` = 0x277150. The rank-confirm script's condition is
  almost certainly one of the `*_CONTROLLER` UI vars (`STEREO_/INVERT_PITCH_/VIBRATION_/SUBTITLE_/
  DIALOG_/ORDER_RESPONSE_/FIREMODESWAP_/STICK_SWAP_CONTROLLER`, 0x3eef40..0x3ef090) or
  `IsControllerConnected` — trace those with `PS2X_CALL_TRACE` at the rank confirm before reading
  further (**[guess]**; this is the HANDOFF "pad/DBCMAN-derived UI variable" lead made concrete).
- **Loading screen black (s00)**: in S1 `COurGame::StartEngine` shows `RUN\LOADING.RAW` by
  `CVideo::RestoreImage(raw=true)` = a raw framebuffer blit. In S2 the string (0x1d4458) and the
  code that uses it are in the **loader** (`SCUS_972.75`, `main()` = `FUN_001c4cc0`), so the blit
  happens before FTSCore is even decrypted — it bypasses everything the game overlay draws; check
  whether our loader path performs that raw-frame upload at all.
- **Text-only title cards black**: these are `TEXT` objects of `dlgIntroScreen.rdr` (`CMenuState`
  default menu) drawn through `C2DString::Draw` → `C2DFont` glyph sprites; reCOM's `C2DFont` entry
  fields explain the per-glyph `top/bottom/baseline/kerning` maths if the capture-timing hypothesis
  in REPORT does not hold.
- **Glyphs heavier than golden (shadow pass alpha)**: `C2DFont` has `m_pGlowTexHandle` and
  `C2DString::m_Type = STRING_PLAIN|STRING_GLOWY`; `C2DBitmap` defaults RGBA rows to
  `128,128,128,128` (i.e. GS "1.0" is 0x80) — a place to compare our alpha/colour clamp.
- **Mission camera/HUD (M4)**: `zcam.h`/`camera.cpp` and `hud.h` name the objects; the
  `_RenderPhase` enum explains why UI/HUD geometry is grouped into phase-specific `CGSTexBuffer`s.

### (d) SOCOM II vs SOCOM 1 — differences visible from this pass
- Command sets grew: zanim ids differ (S1 `OBJECT_ACTIVE_STATE`=0x10, `SOUND`=0x1A,
  `CALL_ANIMATION`=0x20, `VALVE`=0x2D; S2 per HANDOFF: 0x11, 0x1e, 0x2d, 0x3d plus `VBIT`/`VWATCH`);
  `CZNetwork::EVENT` gains `ON_SKB_APPLY2` (id 0xf, shifting `ON_SKB_CLOSE` to 0x10); the UI
  binding table has 207 rows (S1 count unknown) with S2-only entries such as `InitializeOnlineArmory`,
  `NetCensorText`, `SwitchProgressiveVideo`, `CheckVideoMode`, `DNASAuthenticate`.
- Assets: S2 adds `VAGS_ENG.ZAR` (localised VAG archive) before `VAGSTORE.ZAR`,
  `mpeg_subtitles.rdr`, `run/uizanim.zar`, `ui/assetlib/uisk`, `MPEG_LOOPING`, `NOFONTLIB`,
  `SELECTION` (was `BACK`) in `uisounds.rdr`, `UIVOICE` bank, locale ZARs (`UIMNLOC.ZAR`).
- ZAR: retail S2 is plain V2 — reCOM's "V2 only for S1/S2-demo" remark is a reCOM limitation,
  not a format difference; our reader also honours the keep-open mode (`mode & 0x20`).
- Build/compiler: S2 r0001 (Oct 2003) vs S1 May 2002; both Metrowerks — reCOM's `premake5.lua`
  PS2 target is aspirational only.
- Everything network-specific (Medius 1.50 message layouts, libnetb 1.10, DNAS) is absent from
  reCOM; `docs/research/10` and the Horizon logs remain the only source.

---------------------------------------------------------------------------------------------

## 3. What does not transfer, and licensing / ethics

- **No runtime**: reCOM is a PS2 source reconstruction targeting the original toolchain. There is
  no GS/VU/IPU/SPU emulation, no DMA/VIF packet code, no libnet/Medius, no 989snd; every hardware
  touch point is a `// TODO` or a commented-out SDK call. Nothing in it replaces or competes with
  `ps2xRuntime`/`ps2xIOP` — it is documentation for the *game* side of the HLE boundary only.
- **SOCOM 1, not II**: bodies were reconstructed from SCUS_972.05; where S2 changed a routine
  (every "S2 adds …" above) the reCOM text is a starting sketch, not ground truth. Verify against
  the decomp before trusting a field offset (`CZNetwork`'s layout in particular is unverified here).
- **Incomplete and sometimes wrong**: many files are empty; several functions are known-bad
  transcriptions (`_eval_defined` has a stray `;` after `while`, `C2DBitmap::SetPos` writes
  `m_iWidth` twice, `zrdr_findint` reads the wrong node). Treat it as annotated notes.
- **Licence/ethics**: the repository ships **no licence file**; its README reserves all rights to
  Zipper/SCEA and forbids shipping copyrighted assets. reCOM's own code is a reconstruction of
  copyrighted game code. **Do not copy code from it into `socom_pc/`** (neither the runtime nor the
  recompiled output); use it the way this note does — as a symbol dictionary and format reference —
  and cite it by file path. Our binary's names should be derived by verifying against *our*
  decomp (as the [verified] rows are), so they stand on their own. The clone stays git-ignored
  under `tools/reference/`.

---------------------------------------------------------------------------------------------

## 4. Action list for the next sessions (file paths are what to open)

1. **Menu movie (priority 2)** — trace `MpegStart` as in §2a; then read
   `tools/reference/reCOM/src/gamez/zVideo/zvid.h` (`doMpeg224`, `renderBuf`, `pcrtcDo`) and
   `src/gamez/zMPEG/zmpeg.cpp` next to `FUN_003098e0`/`FUN_0030b4d0`/`FUN_0030b9d0` in
   `game/analysis/socom2_game.elf.decomp.c` to name the decoded-frame buffer and where it is
   uploaded to the GS; implement `Kernel/Stubs/IPU.cpp`/`MPEG.cpp` against that contract
   (FFmpeg → the buffer `0x30b9d0` expects). Cross-check `data/s1/common/dialog/dlgMenu.rdr`
   for the `BackgroundMPEG ON/OFF` protocol around `SWITCHMENU`.
2. **Online (priority 1)** — read `src/gamez/zNetwork/znet.h` while naming `FUN_00276dc0`
   (`InitNetwork`), `FUN_00277970` (`NetGetInterfaceList`), `FUN_00277dd0` (`NetCnfOpen`) and the
   `CZNetwork` globals they touch; use `LOBBY_STATE` to decode `socom_online_state` values seen
   over PINE; use `CZNetwork::EVENT` ids with `PS2X_CALL_TRACE=0x1f3bf0:PostEvent` to see which
   net events the shell posts on our exe vs PCSX2.
3. **Controller-config screens** — `PS2X_CALL_TRACE="0x2c5e70:CtrlrConfigsInit,0x27b960:CtrlrCfg,0x277150:IsControllerConnected,0x27fb40:SetControllerConfig"`
   at the rank confirm on ours; compare the `*_CONTROLLER` UI vars over PINE
   (`tools_py/parity/pine.py`). Reference: `src/gamez/zInput/zinput.h`, `zin_pad.cpp`.
4. **ZAR/rdr tooling** — port the scratch V2 parser to `tools_py/zar.py` (list/extract; header
   100 B; `flags != 0` ⇒ XOR 0xFF) and extend `tools_py/rdr_tree.py` to read compiled `.rdr` from
   disc using `src/gamez/zReader/zrdr_file.cpp` (`Resolve`/`_resolveB`). Then dump all 111
   `READERC.ZAR` dialogs to text once (`_OutputASCII` in `zrdr_local.cpp` is the printer) — this
   removes the RAM-dump step from every shell investigation.
5. **Parity: text/glyphs** — `src/gamez/zTwoD/ztwod.h` + `ztwod_font.cpp` beside
   `FUN_00359c40` (font load) and the glyph sprite builder to settle the shadow/glow pass.
6. **Mission (priority 3)** — `src/gamez/zFTS/fts_mission.cpp` (`CMission::Tick`, the
   `mission_*` valves) with `FUN_002abd40`/`FUN_002ac410`; `src/gamez/zRender/zrndr_pipe.cpp`
   and `zrender.h` for `_RenderPhase`/`CPipe` when naming `FUN_00339de0`/`FUN_0033b110`;
   `src/Apps/FTS/hud/hud.h` for the HUD objects.
7. **Symbol hygiene** — record the [verified] rows of this note as `name@0x…` comments in
   `recomp/socom2.toml` (or a `recomp/names.csv`) so `PS2X_CALL_TRACE` output and future notes use
   the reCOM names consistently; re-run the literal cross-reference (scratch method above) whenever
   reCOM gains files — its upstream is active (commit 2026-06-29).
