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

The tree below is the built one (corrected 2026-09-21; the plan's `packages/mesh/src/packet.ts` was never
written -- its work is `vif.ts` and `interpret.ts` -- and `meshData.ts`, `paletteTable.ts`, `node.ts` and
`world.ts` were added as the packages landed).

```
web/
  package.json            workspace root: vite, vitest, typescript, playwright, three
  README.md               how to run it: prerequisites, the commands, the known gaps
  packages/
    archive/              ZDB, ZAR/ZED, compiled .rdr readers; ISO9660 reader; AssetSource interface
      src/{bytes,zdb,zar,rdr,assetSource,fsAssetSource,httpAssetSource,mapIndex,node,index}.ts
    gs/                   GS texture and palette decode (PSMT8, PSMCT16, PSMCT32); CLUT handling
      src/{tex0,texture,palette,paletteTable,decode,index}.ts
    mesh/                 DMA-chain walker, VIF1 unpack, vertex-lane interpretation -> MeshData
      src/{dma,vif,interpret,meshData,index}.ts, SEMANTICS.md
    scene/                world root, scene graph, clutter, collision -> a SceneDescription
      src/{worldRoot,sceneGraph,modelLibrary,clutter,collision,spawns,buildScene,index}.ts
    viewer/               the Vite app: three.js renderer, camera, UI, overlays, diagnostics
      src/{main,renderer,camera,ui,worker,loadMap,overlays,world,hook}.ts, e2e/viewer.spec.ts
  tools/
    extract-maps.ts       disc tree -> web/public/maps/RUN/*.ZDB + index.json (testing source)
    dump-textures.ts      every texture of one map to PNG, both orders, plus contact sheets
    export-gltf.ts        map -> glTF (debugging aid and golden generator); gltf.ts, png.ts are its writers
  test-fixtures/          git-ignored: copies of MP2/MP6/MP72 archives, reference PNGs, screenshots
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
- 2026-09-20, M2 texture bytes: Frostfire's pixels are **raster**, and its 8-bit palettes **are** in the GS
  `csm1` CLUT order. Evidence: `tools/dump-textures.ts` decoded all 65 MP2 textures four ways into
  `web/test-fixtures/textures/MP2/` and I looked at the contact sheets. `sheet-raster.png` is diamond plate,
  concrete, shipping containers and readable signage; `sheet-swizzled.png` is the same bytes as 16x16 block
  hash. The decisive texture is `sign04.tif`: raster it reads "DANGER / FLAMMABLE LIQUID", swizzled it is
  red-and-white noise. For the CLUT, `sheet-raster.png` against `sheet-raster-linear-clut.png`:
  `cuba1a_sky01.tif` is a smooth cloud sky with the 32-entry swap undone and a hard-banded contour map
  without it. `decodeTexture` defaults to `'raster'` and `'csm1'`, keeps both other readings reachable as
  arguments, and its 65 decodes are frozen as sha256-16 goldens in
  `packages/gs/test/goldens/frostfire-textures.json`. Two asides the dump settled for free: all 65 records
  carry a usable TEX0 and every CBP names a loaded palette (no diagnostic fired on Frostfire), and the rows
  are stored bottom-up, so the viewer flips V rather than the decoder flipping rows (superseded by
  the M3 entry: bottom-up rows with `flipY = false` need no extra flip, because that is already
  what GL calls V = 0).
- 2026-09-20, M2 shape: `decodeTexture` returns `{ rgba, diagnostics: string[] }`, not a bare `Rgba`. A record
  with no TEX0 in its bind packet, or a CBP no loaded palette answers, still decodes -- by `m_texelBitSize`
  and by the first palette -- and says so in a string, so the viewer reports a bad texture instead of the
  decoder throwing mid-map.
- 2026-09-20, M3 viewer: Frostfire renders in the browser from the served archive alone, and the two
  screenshots say it is the right map. `frostfire-spawnA.png` (camera at spawn A raised 20 units, looking
  at spawn B) is the industrial compound: corrugated warehouse walls with their ribs vertical, yellow
  handrails on the walkway, rusted elbow pipes, a wet concrete yard, an overcast sky. `frostfire-top.png`
  (straight down from y = 1400 over the spawn midpoint) is a level-shaped footprint -- roofs, two round
  tanks, a container yard, a stair tower -- inside the dark disc of the sky chunk's underside, with the
  distant skirt beyond it. 8,764 triangles in 37 draws (one per cited texture), 53-69 ms to decode the
  8 MB archive, zero diagnostics, zero console errors.
  - **Texture orientation, settled by looking:** the decoder's bottom-up rows are exactly GL's V = 0, so
    the viewer uses `DataTexture` with `flipY = false` and the UVs `interpret.ts` produces, unflipped.
    Nothing is mirrored or rotated in either screenshot -- signage, ribbing and railings all read the
    right way up on the first try, so neither the V flip nor a UV-axis fix was needed.
  - **Vertex colour:** the PS2 writes 128 as full brightness, which a normalised three.js byte attribute
    reads as 0.5; the viewer doubles the three colour bytes (clamped) when it builds the attribute, and
    the map is lit as the reference is rather than at half light. `mesh` had already rescaled alpha.
  - **Placement:** the whole world takes the modal `nparams` translation, read from
    `MP*_GEO.ZED/models/worldmodel/children` at load time rather than typed in -- (960, 0, 800) on
    Frostfire (section 8 of `mesh/SEMANTICS.md`). Standing at spawn A the camera is on the floor, not in
    it, which is the same check the mesh tests make, now made by eye.
  - **Backend:** the renderer is three's `WebGPURenderer` from `three/webgpu`, which bundles under Vite
    without special handling; headless chromium has no adapter, so both screenshots were drawn by its
    **WebGL2 fallback** over ANGLE/SwiftShader (`--enable-unsafe-swiftshader`). The status line reports
    whichever backend `renderer.backend.isWebGPUBackend` names, so a desktop browser saying `webgpu` is
    the same build.
  - **Decode thread:** the archive read, VIF walk and texture decode run in a module Web Worker and come
    back in the transfer list, so nothing is copied and the frame loop never stalls.
- 2026-09-20, M3 review round 1: three findings fixed on top of M4's scene-graph landing. A bad DMA
  chain now costs one chunk, not the map -- the walk happens inside `decoder`'s per-chunk `try` (M4 had
  already moved it there; the same guard was extended to the model archives and to the texture archive,
  so an unreadable `MP*_TXR.ZED` leaves a map drawn in vertex colour rather than no map at all). The
  viewer package joined `npm run typecheck`, appended as `tsc --noEmit -p packages/viewer` because its
  config is `noEmit` and `tsc -b` will not take it. And every worker request now carries a monotonic id
  its answer repeats, so the boot auto-load and the map the player picks a moment later cannot land out
  of order -- the page drops any answer that is not the one it is still waiting for.
- 2026-09-20, M4 close: **all three extracted maps render**, with the collision hull, the measured
  spawns and a diagnostics panel over them. Playwright drove one pass over the three, selecting each by
  the name `mission.rdr` shows, and photographed each from its own spawn A and from 800 units above the
  midpoint of its two spawns:

  | map | triangles | draws | collision polys | diagnostics | load |
  |---|---|---|---|---|---|
  | FROSTFIRE (MP2) | 16,931 | 152 | 3,338 | **0** | 59-78 ms |
  | DESERT GLORY (MP6) | 27,311 | 439 | 5,951 | 6 | 88-113 ms |
  | CROSSROADS (MP72) | 44,279 | 392 | 9,820 | 11 | 104-136 ms |

  What the pictures show. `desert-glory-spawnA.png`: a rock-walled wadi in low sun, the eroded rock
  faces textured and lit, a walled compound and a telegraph pole in the middle distance, an overcast
  sky dome over it. `desert-glory-top.png`: hillside terrain with flat-roofed buildings, a wooden
  walkway, a parked truck and stair flights standing on the ground, not floating over it.
  `crossroads-spawnA.png`: spawn A is **indoors** -- a dark plastered room with a doorway on the right
  opening onto a cobbled street, which is a dull picture but the correct position. `crossroads-top.png`
  is the map that picture belongs to: a north-African town of red-tiled roofs around a square with a
  red-tiled rotunda at its centre, market stalls under awnings, and palms, all placed. `frostfire-overlays.png` is the same
  camera as `frostfire-top.png` with collision and spawns switched on: the hull traces every deck,
  crate, tank and railing of the rig in green (`ditype` 2) and pink (`ditype` 3), and the two spawns
  stand where the sweep measured them: A's blue sphere among the shipping containers under its letter,
  and B's letter over the enclosed deck at the far end, its sphere hidden by the roof above it -- the
  markers are depth-tested, so they sit in the world rather than floating over it, while the letters are
  not, so a spawn is never lost. Nothing is at the origin and nothing floats.

  **The MP6/MP72 chain gap (M6's first work item).** Every diagnostic on the two new maps is one of two
  causes. Five prop chains on Desert Glory and six on Crossroads fail in the `mesh` packet decoder --
  the counted totals are 15 and 29 chains, which the viewer collapses to one line per model-node
  because it decodes a prop group's geometry once. The messages, verbatim:

  ```
  chunk mp6_pole_lines/N000_I000_V00: chunk N000_I000_V00 packet 1: the header claims 2760716326
    triangles from TOP+0 reaching TOP+5521432652, past the 1024 quadwords of VU data memory
  chunk mp6_light_hangout/N000_I000_V00: chunk N000_I000_V00 packet 1: the header claims 1085931520
    vertices reaching TOP+3257794564, past the 1024 quadwords of VU data memory
  chunk tent_beige/N000_I000_V01: chunk N000_I000_V01 packet 2: the header claims 3210739712
    vertices reaching TOP+9632219140, past the 1024 quadwords of VU data memory
  chunk light_bright/N000_I000_V03: chunk N000_I000_V03 packet 1: the header claims 3222274048
    vertices reaching TOP+9666822148, past the 1024 quadwords of VU data memory
  ```

  **[SUPERSEDED 2026-09-20 -- see "Relocation type 1 is LINE_STRIP" below. The walker was never
  wrong; these packets are not meshes.]**

  The counts are the tell: 1040187392 is `0x3E000000`, 3212836864 is `0xBF800000`, 3222274048 is
  `0xC0080000` -- IEEE floats 0.125, -1.0 and -2.125. The decoder is reading vertex floats where it
  expects a packet header, so it entered the packet at the wrong offset rather than misreading a
  header: the chain walk is landing in the middle of the data, which is what 36 section 3's
  relocation-type-1 tags on these two maps predict. The scene package's naming test already rules out
  a placement cause -- every one of the 203 models of the three maps has exactly the key set the N-I-V
  rule predicts. It is a `mesh` gap, and it is not touched here.

  The second cause is textures a map's own `TXR` does not hold: `null_xmas.bmp` on both maps, and
  `afghan2r_rug1..3.tif` and `afghan2r_rug_trim.tif` on Crossroads. The `afghan2r_` prefix is Desert
  Glory's texture family, so these are `FLIB_MDL.ZED` models carrying another mission's texture names;
  where those pixels live is the other M6 question. Those meshes draw in vertex colour, and the
  **highlight untextured** toggle paints them magenta so they can be found: 0 such draws on Frostfire,
  2 on Desert Glory, 6 on Crossroads.

  Three decisions worth keeping. **Spawns are code, not archive** -- `@s2u/scene`'s `spawns.ts` holds
  all 22 maps' measured A/B positions keyed by shown name, with a header saying they are actor readings
  pending `AIMAPS.MPS`; the viewer looks a map up by `mission.rdr`'s name, so the camera stands at spawn
  A on every map, not just Frostfire. **Collision is realised, not stored** -- Frostfire's 2,756 stored
  polygons become 3,338 world-space ones, because an instanced prototype's hull is realised once per
  context, exactly as its chunks are. **`CLUTTER.ZAR` is a second placement root** -- its six Desert
  Glory models are in the scene graph as prototypes that nothing instances from `worldmodel`, so
  `placeInstances` never reaches them; reading the archive adds 110 instances and 1,601 triangles of
  rock and grass that were missing from the ground before.

- 2026-09-21, the code-diet spike's verdict (docs/research/35 §1.7): the whole recompiled game is 180.27 MB of
  wasm, 13.7 MB brotli on the wire, and Chromium compiles it in 0.2 s lazily; the size gate on the full-game route
  is open. The viewer route's archive, texture, mesh and scene layers stand as the asset side of that route and of
  the replay viewer. The next design decision is the runtime port (Emscripten: scheduler, GS, VU1, disc delivery),
  which is its own spec.

### Relocation type 1 is `LINE_STRIP`, not a broken walk (2026-09-20)

**Supersedes** the M4-close finding above, which read the absurd vertex counts as the chain walk
entering a packet at the wrong offset. It was not. `dma.ts` needed no change and the offsets were
always right.

A type-1 tag is written byte for byte like a type-2 tag, and `CVisual::SetBuffer`
(`research/recom/src/gamez/zVisual/vis_main.cpp:320-366`) patches types 1, 2, 4 and 7 through the
identical arm. What differs is the **packet**: relocation type 1 marks a GS `LINE_STRIP`. All 194 of
them across the three maps carry `PRIM` type 2 in *both* GIFtag templates (bits 47-57 of the tag), and
no other packet in any map has prim type 2. Tag counts: 31 in MP6, 163 in MP72, 0 in MP2.

The layout is `SEMANTICS` section 4's vertex triple lane for lane, already in floats, with no index
list, no face normal and no `TOP+3` bias: `TOP+0`/`TOP+1` are the templates, then per point a
`V4-32` float `(x, y, z, normal.x)`, a `V4-32` float `(u, v, normal.y, normal.z)` and a `V4-8 USN`
rgba. Point counts run 2 to 9; segment *k* joins point *k* to *k+1*. The mesh decoder was reading
point 0's float position as the counts quadword, which is where `1124466688` came from: `0x43070000`,
the float 135.0.

What they are: Desert Glory's power lines, lamp brackets and handcuff chains; Crossroads' tent guy
ropes and light filaments. 877 segments over 1,071 points in total. **No triangles were ever lost** --
the failing chunks hold only strips, which is why fixing this moved no triangle count. They are decoded
as `LineStrip` and drawn as one `LineSegments` pass; the GS draws them one pixel wide at any distance,
so no width had to be invented.

Diagnostics after: Frostfire 0, Desert Glory 6 -> 1, Crossroads 11 -> 5. Every remaining one is the
second cause already recorded above -- five textures a map cites but its own `_TXR.ZED` does not hold:
`null_xmas.bmp` (MP6) and `afghan2r_rug1..3.tif` plus `afghan2r_rug_trim.tif` (MP72).

### 128 is unity on RGB, not 255 (2026-09-20)

An intermediate change divided RGB by 255 and alpha by 128, on a reading of section 4's "`rgb/255` and
`a/128` are the browser values". That was wrong and made the pipeline 1.992x dark. Every texture in the
three maps binds `TEX0.TFX = MODULATE` -- 241 of 241, measured with `web/tools/dump-bindpacket.ts` --
and MODULATE is `C = (Ct x Cf) >> 7`, so **128 is unity on every lane**. RGB is now `c/128`, unclamped
(the GS clamps the product, not the vertex); alpha is `min(c/128, 1)`. `SEMANTICS` sections 4 and 11
carry the correction.

The vertex colour is a **material** colour, not a lit one: the VU multiplies it by a computed light
before the GS sees it (`staging+1 = record2 * lit`, NAT:1615). Measured over the three maps it averages
0.29 of unity and never exceeds it. The viewer emulates the VU's own model in
`viewer/src/lighting.ts` -- `lit = light[0]*n.x + light[1]*n.y + light[2]*n.z + light[3]` with the
normal clamped componentwise to zero, from dispatcher command `0x18` -> `0x1440` -- using the vertex
normals, which were decoded and then discarded until now. The *values* it needs (the normal/light
matrix in vf5-vf7, the colour block in vf9-vf12) are uploaded by the EE at VU1 entry 0 and are not on
the disc, so the matrix is taken as identity and the four colours are sliders.

### Fog is per map, in `cameras/camera` (2026-09-20)

Not in `mission.rdr`. `MP<N>.ZDB` -> member `MP<N>.ZED` -> ZAR key `cameras/camera`, a 144-byte
`zdb::tag_CAMERA_PARAMS` (`research/recom/src/gamez/zCamera/zcam.h:67-101`): fog RGBA at `0x10` (floats
0..1, always exact n/255), `fog_near`/`fog_far` at `0x64`/`0x68`, `fog_top`/`fog_bottom` at
`0x7C`/`0x80`, flags u32 at `0x8C` with bit 29 fog-enabled, bit 30 directional, bit 31 altitude. The
authored source is readable beside it as text in `READERM.ZAR -> mp<N>.rdr`.

The coefficient is `F = clamp(w * scale + offset, 0, 255)` with `scale = -255/(far-near)` and
`offset = 255 - near*scale`, where `w` is **view depth**, not radial distance -- the radial form in
`sub_002948D0` is the EE's own mirror for CPU-side object fades. The GS blends
`C = (F*C)>>8 + ((255-F)*FOGCOL)>>8`. The framebuffer clears to the fog colour
(`reCOM zrndr_pipe.cpp:157`), so the horizon comes free and there is no separate sky colour.

Two of the 22 multiplayer maps ship fog disabled (MP51, MP81) and six enable altitude fog (MP1, MP7,
MP10, MP62, MP64, MP82). The altitude band is parsed and **not applied** -- no VU1 dump exists from a
map that enables it, so its encoding is the one inferred part of the model -- and a map that enables it
says so in the diagnostics panel.
