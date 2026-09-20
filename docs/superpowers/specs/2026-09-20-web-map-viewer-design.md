# Web map viewer — the browser recreation's first milestone (design)

Written 2026-09-20 by the browser project's overseer under the owner's overnight mandate ("work autonomously on this
task overnight using your best discretion, progressing through each milestone"). The owner approved the scoping
(`docs/research/35-browser-recreation-scoping.md`) and the code-diet spike, chose the map order Frostfire, Desert
Glory, Crossroads, allowed pre-extracted map files to be served for testing provided reading the player's own ISO
stays possible, and set a 30 s first-load budget. The review gate this process normally puts on a spec before
implementation is waived for tonight by that mandate; the owner reviews this file when convenient.

## 1. What this is

A browser application that loads a SOCOM II multiplayer map from the game's own archives and renders it in 3D with a
free camera, textured world geometry, placed props, and overlays for collision and the known spawn positions. It is
the first milestone of the browser recreation (`docs/research/35`): the replay viewer for live matches builds on it
(it needs a map to draw actors in), and the eventual match client reuses its archive and asset layers.

It is a **viewer**, not the game. It does not emulate VU1 or the GS. Geometry and textures are decoded exactly from
the archives; lighting is the baked vertex colour; blending and fog are approximated. Where the match itself is
concerned, fidelity means running the recompiled game code, which is the full-game route the code-diet spike gates;
this viewer does not pretend to that.

### 1.1 Why viewer-first tonight
The full-game route (recompiled game as wasm, GS as WebGPU compute) is the only route to mechanically identical
gameplay and stays the target. It is gated on the code-size measurement now running, and even a good number makes it
a months-scale port with no shipped precedent. The viewer route is weeks-scale, every one of its formats is now
specified (`docs/research/36-mp-map-archive-anatomy.md`), and its archive, texture and mesh layers are needed by the
replay viewer whichever way the game itself goes. The spike's verdict is recorded in section 9 when it lands.

## 2. Goals and non-goals

**Goals**
1. Frostfire (MP2), then Desert Glory (MP6), then Crossroads (MP72), render with correct geometry and textures from
   the archives alone, verified against in-game reference captures.
2. Every multiplayer map opens; a map that hits an unknown construct degrades (missing prop, untextured chunk) and
   says so in a diagnostics panel instead of failing.
3. Two asset sources behind one interface: pre-extracted archive files served over HTTP (testing), and the player's
   own ISO read in the browser (the shipped stance). The second is designed in now and implemented as its own
   milestone; nothing may assume the first.
4. Collision polygons and the known A/B spawn positions as toggleable overlays.
5. WebGPU rendering with automatic WebGL2 fallback; nothing in the viewer requires WebGPU.
6. Verification that does not need a human: unit tests on the real archives when the disc tree is present (skipped
   otherwise, as the Python suite does), decoded textures and rendered frames checked against reference images.

**Non-goals (this milestone)**
- `AIMAPS.MPS` (AI navigation, spawn regions, minimap). Format unknown; spawns come from the measured table in
  `docs/research/33-online-map-coverage.md` until it is decoded.
- Character models (`CLIB_MDL`, a different chain form), animation, weapons, HUD, audio, replay, networking.
- GS-accurate rendering (alpha test order, dithering, texture-function quirks, fog, depth precision).
- The full-game wasm build. Its findings are recorded, not built, here.

## 3. Architecture

Everything lives under `web/` in the repository, one npm workspace, TypeScript throughout, Vite for the app, vitest
for tests, Playwright for rendered-frame checks. No game data is committed: `web/public/maps/` and
`web/test-fixtures/` are git-ignored and populated by a script from the owner's disc tree.

```
web/
  package.json            workspace root: vite, vitest, typescript, playwright, three
  packages/
    archive/              ZDB, ZAR/ZED, compiled .rdr readers; ISO9660 reader; AssetSource interface
    gs/                   GS texture and palette decode (PSMT8, PSMCT16, PSMCT32); CLUT handling
    mesh/                 DMA-chain walker, VIF1 unpack, vertex-lane interpretation -> MeshData
    scene/                world root, scene graph, clutter, collision -> a SceneDescription
    viewer/               the Vite app: three.js renderer, camera, UI, overlays, diagnostics
  tools/
    extract-maps.ts       disc tree -> web/public/maps/<name>/... (testing source)
    export-gltf.ts        map -> glTF (debugging aid and golden generator)
  test-fixtures/          git-ignored: copies of MP2/MP6/MP72 archives, reference PNGs
```

Dependency direction is strictly downward: `viewer -> scene -> mesh, gs -> archive`. `archive`, `gs`, `mesh` and
`scene` have no DOM or three.js dependency and run under node for tests and tools.

### 3.1 `archive`
- `AssetSource`: `list(): Promise<string[]>` and `read(path): Promise<Uint8Array>` for disc paths like
  `RUN/MP2.ZDB`. Two implementations: `HttpAssetSource` (fetches from `/maps/...`, the testing source) and
  `IsoAssetSource` (a `File`/`Blob` from the File System Access API or drag-and-drop, parsed as ISO9660 from the
  primary volume descriptor at sector 16, path table walked lazily, reads by LBN; `tools_py/iso_lbn.py` is the
  reference). Both return the same bytes for the same path.
- `Zdb`: header at 0xA0, count at 0x98, 92-byte entries, absolute 2048-aligned offsets; `entries`, `get(name)`.
- `Zar`: the v2 layout (100-byte head, string table, 16-byte pre-order keys, aligned data blob); `root`, `find(path)`,
  `data(key)`. Offsets are relative to the data blob. Parsing consumes exactly `key_count` records or throws.
- `Rdr`: the compiled S-expression form (version 1 header, string table, 8-byte nodes) to a nested array/string
  tree; used for `mission.rdr` (name), `mp<N>.rdr` (world params), `mp<N>_lib.rdr` (texture wrap and detail
  bindings).
- `MapIndex`: given an `AssetSource`, lists the 22 MP archives and their display names (from `mission.rdr`).

### 3.2 `gs`
- `TextureRecord` from a `texdat` blob: the 16-byte `TEXTURE_PARAMS`, pixel bytes, and the 9-quadword bind packet;
  the `TEX0` quadword is decoded for `PSM`, `CBP`, `CPSM`, `TW`, `TH`.
- `PaletteRecord` from `par` + `buf`: `gsaddr`, format (CT16 or CT32), 256 entries.
- `decodeTexture(tex, palettes) -> RGBA8 ImageData` for PSMT8 with either palette format, PSMCT16 and PSMCT32
  direct. PS2 alpha (0..0x80) is scaled to 0..255. The two open questions from `docs/research/36` (raster versus
  swizzled pixel order; the 32-entry CLUT interleave for 8-bit palettes) are settled empirically in milestone 2 by
  decoding known textures and looking, with the runtime's `ps2_gs_psmt8.h` and `ps2_gs_psmct32.h` as the reference
  for the swizzle if the raster reading is wrong. The decision and its evidence go into this spec's section 9.
- `PaletteTable`: one id-to-palette map over every `*_PAL.ZED` the map loads (ids are global across archives).

### 3.3 `mesh`
- `walkChains(buffer, nodeOffsets) -> Chain[]`: count quadword then N DMA tags; relocation type from tag bits
  16-23; `ADDR` as a byte offset into the same buffer; type 6 is a texture name.
- `unpackVif(chain) -> VifBlock[]`: only NOP, STCYCL, UNPACK, MSCAL, MSCNT; the five UNPACK formats
  (V4-32, V4-16, V4-8 unsigned, V3-16, all `FLG=1`) with STCYCL skipping-write. Anything else throws with the
  offending code, and the viewer reports it per chunk.
- `interpretPacket(blocks) -> MeshData`: positions, UVs, normals, colours, and the triangle order, from the VU1
  family-B semantics. This is the milestone with a real unknown (the fixed-point scale and lane meaning of the
  V4-16 pairs and the V3-16 block, and the strip or fan order the header quadword implies). The authority is the
  translated microprogram `vu/generated/vu1_d418194495c25213.cpp` and `docs/research/13`, `15`; the check is
  `tools_py/research/terrain/patch_dump.py` against a family-B dump, and the rendered Frostfire world against
  `logs/parity/*/refs/map_frostfire.png` and the mission captures.
- `MeshData` is plain typed arrays with a texture name per sub-mesh, so `viewer` builds `BufferGeometry` from it
  without knowing anything about the PS2.

### 3.4 `scene`
- `WorldRoot` from `MP<N>.ZED`: lighting, `MetersPerUnit`, `ShadowVector`, `grid_params`.
- `SceneGraph` from `MP<N>_GEO.ZED`: prototypes, instances (`model_name` + `nparams` matrix), `children`, and the
  `di` collision polygons (12-byte params, `CPnt4D` points) per model.
- `ModelLibrary` from `WORL_MDL.ZED`, `MP<N>_MDL.ZED`, `FLIB_MDL.ZED`: model name to chain buffer and node
  offsets; `worldmodel` is the world.
- `Clutter` from `CLUTTER.ZAR`: model name, 96-byte matrix, inverse scale per instance.
- `SceneDescription`: world mesh, prop instances with world matrices, collision polygons in world space, spawn
  markers (from the measured table), and a diagnostics list of everything that failed to decode.

### 3.5 `viewer`
- three.js `WebGPURenderer` with its WebGL2 fallback; one `Group` per model prototype instanced by matrix; textures
  as `DataTexture` from `gs`, nearest or linear per the record's `m_bilinear`, wrap from `mp<N>_lib.rdr`.
- Fly camera (WASD + mouse, plus touch), map picker listing the 22 maps, toggles for collision, spawns, wireframe,
  and untextured chunks; a diagnostics panel listing decode failures; a coordinate readout in game units and metres
  (`MetersPerUnit`) so positions can be compared with the research tables.
- Asset source chooser: the served `/maps/` index by default when present; an "Open ISO" button that takes the
  player's disc image and uses `IsoAssetSource`. The ISO never leaves the browser.
- Everything renders at any window size; a phone can open it, but the target is a desktop browser.

## 4. Data flow

```
AssetSource.read("RUN/MP2.ZDB") -> Zdb -> member blobs
  MP2.ZED         -> WorldRoot
  MP2_GEO.ZED     -> SceneGraph (+ collision)
  WORL_MDL.ZED,
  MP2_MDL.ZED,
  FLIB_MDL.ZED    -> ModelLibrary -> walkChains -> unpackVif -> interpretPacket -> MeshData per model
  MP2_TXR.ZED,
  *_PAL.ZED       -> PaletteTable, TextureRecords -> decodeTexture -> RGBA
  CLUTTER.ZAR     -> Clutter
  READERM.ZAR     -> Rdr(mission, mp2, mp2_lib)
                  => SceneDescription => three.js scene
```

Decoding runs in a Web Worker so a 12 MB archive does not freeze the page; the main thread receives transferable
typed arrays. Per-map work is small (Frostfire's world is 485 KB of chains and 651 KB of textures), so the first
paint is expected well under a second after the archive is in memory.

## 5. Verification

- **Unit tests (vitest, node)** for every reader against synthetic buffers, and against the real archives when
  `web/test-fixtures/` is populated: member counts, key counts (MP2_GEO 10,433; MP2_TXR palettes 53; MP2 world 123
  chunks), zero VIF decode errors on all five dumped maps, `m_ptcount == points/16` for every collision polygon. Tests
  skip with a clear message when the fixtures are absent, so a fresh clone is green.
- **Texture goldens**: a decoded PNG per Frostfire texture written by a tool; the first pass is looked at by the
  implementing agent (the Read tool renders images) and the chosen decode is then frozen as a golden hash.
- **Mesh goldens**: Frostfire's world exported to glTF, its bounding box compared with `grid_params` and the known
  spawn positions (both spawns must lie inside the world's box and near its ground), and a Playwright screenshot of
  the viewer compared by eye against the in-game reference; then frozen as an image-diff golden with a tolerance.
- **App smoke**: Playwright opens the viewer, loads each of the three priority maps from the served source, asserts
  zero diagnostics and a non-empty draw call count.
- Nothing here launches the game, takes the loop lock, or exceeds a few cores.

## 6. Milestones

| # | Milestone | Done when |
|---|---|---|
| M0 | Scaffold | `web/` workspace builds and tests green on a clone with no fixtures; `extract-maps` populates fixtures and `public/maps` from the disc tree; CI-style `npm test` documented. |
| M1 | Archive layer | ZDB, ZAR, Rdr, MapIndex pass real-archive tests; the 22-map name table is produced by code, not typed. |
| M2 | Textures | Every Frostfire texture decodes to a PNG that looks right; the swizzle and CLUT questions are answered in section 9; goldens frozen. |
| M3 | World mesh | Frostfire's `worldmodel` renders textured in the viewer and matches the reference by eye; vertex semantics documented in section 9; glTF export works. |
| M4 | Scene | Props placed from the scene graph, collision and spawn overlays, diagnostics panel; Desert Glory (clutter) and Crossroads render. |
| M5 | ISO source | `IsoAssetSource` reads a real ISO in the browser and produces identical bytes to the served source (tested with a hash per member). |
| M6 | All maps | Every one of the 22 MP archives opens; failures are listed, not fatal. |

M0 to M3 are tonight's target; M4 if time allows. Each milestone is a commit or a short series on
`feat/web-map-viewer`, worktree `C:\projects\socom_pc_web`, never touching the tree the sprint-9 agent uses.

## 7. Conventions

- Branch `feat/web-map-viewer` off `main`, per `docs/GIT_STRATEGY.md`; commits with explicit pathspecs and the
  project's subject style; the session's trailer on every commit. No push overnight; the owner sees the branch first.
- No game data committed. `.gitignore` gains `web/node_modules/`, `web/dist/`, `web/public/maps/`,
  `web/test-fixtures/`, `web/**/playwright-report/`.
- TypeScript strict; no `any` in the decoders; every binary layout is a documented `DataView` reader with the byte
  offsets in comments citing `docs/research/36`.
- Third-party: three.js (MIT), Vite, vitest, Playwright. Nothing GPL enters `web/` (the runtime is GPL-3.0 and
  stays a reference, not a dependency, for this milestone).

## 8. Risks

| Risk | Mitigation |
|---|---|
| Vertex-lane semantics wrong (positions scaled, UVs swapped, strip order) | The VU1 translation is the authority; verify against a terrain dump and the reference capture before building on it; keep `interpretPacket` isolated so a fix does not ripple. |
| Texture byte order is GS-swizzled | Decode both ways in M2; the runtime's swizzlers exist for the second reading. |
| A map uses a VIF or DMA construct the five dumps did not show | The unpacker throws per chunk; the viewer degrades and reports; M6 sweeps all 22. |
| three.js WebGPU renderer quirks | The WebGL2 fallback is automatic; the viewer needs nothing WebGPU-specific. |
| Overnight host load disturbs the sprint-9 agent | Node and vitest only; Playwright headless for seconds at a time; no parallel native compiles beyond the spike's idle-priority job. |

## 9. Findings recorded during implementation

Filled in as milestones close. Each entry: date, what was decided, the evidence.

- 2026-09-20, route: viewer-first tonight; full-game route pending the code-diet spike (interim: the
  program-counter-store diet shrank native objects 1.4 percent, so the size lever is elsewhere; wasm-to-native
  ratio and full compile pending).
