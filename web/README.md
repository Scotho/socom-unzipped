# `web/` — the browser map viewer

A TypeScript recreation of SOCOM II's multiplayer maps that runs in a browser: it reads the game's own
`RUN/MP*.ZDB` archives byte for byte — container, scene graph, DMA/VIF geometry, GS textures and palettes,
collision — and draws them with three.js. Nothing is pre-baked and no asset is committed; the viewer decodes
the disc. The design and the findings recorded as it was built are in
[`docs/superpowers/specs/2026-09-20-web-map-viewer-design.md`](../docs/superpowers/specs/2026-09-20-web-map-viewer-design.md);
the byte-level format authority is
[`docs/research/36-mp-map-archive-anatomy.md`](../docs/research/36-mp-map-archive-anatomy.md), and the meaning
of every vertex lane is [`packages/mesh/SEMANTICS.md`](packages/mesh/SEMANTICS.md).

## Prerequisites

- **Node 24** or newer (the tools use `import.meta.dirname` and top-level `await`).
- **The owner's disc tree**: a directory with `RUN/MP*.ZDB` in it. `tools/extract-maps.ts` reads
  `$SOCOM_DISC`, defaulting to `C:/projects/socom_pc/game/disc`.

## Commands

Run from `web/`:

| command | what it does |
|---|---|
| `npm install` | workspace install (five packages plus `tools`) |
| `npm run extract-maps` | disc tree → `public/maps/RUN/*.ZDB` + `index.json`, and three fixtures. **Run this first.** |
| `npm test` | vitest over every package; the fixture-backed tests skip when the extractor has not run |
| `npm run typecheck` | `tsc` over the five packages, the viewer and `tools` |
| `npm run dev` | Vite at `http://localhost:5173` |
| `npm run build` | the viewer as a self-contained static site in `dist/viewer/` (~830 kB, 220 kB gzipped) |
| `npm run e2e` | Playwright: loads all three fixture maps, asserts the stats, writes screenshots |

## The viewer stands on its own

The viewer is a **standalone project** and is meant to stay one. `npm run build` emits a static
`dist/viewer/` that needs nothing but a web server and a `maps/` directory beside it — no recompiled game,
no WebAssembly, no server code. It is useful by itself, to anyone who wants to look at the maps, and it is
the only part of this repository that a browser can already run end to end. Whatever the full-game route
does, the viewer keeps its own entry point, its own build and its own deployable output rather than being
absorbed into it.

## Controls

The camera flies like a creative-mode build camera: momentum, not teleporting.

| input | what it does |
|---|---|
| click the canvas | captures the mouse; look is then free. **Esc** gives it back |
| drag | looks, for touch screens and anywhere pointer lock is refused |
| `W`/`S` | fly along the look direction — nose down and `W` descends |
| `A`/`D` | strafe, always level with the horizon whatever the pitch |
| `Space` / `Shift` | up and down in world space |
| `Ctrl` | boost, with the field of view widening to match |
| wheel | trims the fly speed between 0.1x and 16x; the panel shows the trim |
| `Q`/`E` | down and up, kept from the earlier bindings |

Starts ramp and stops glide rather than snapping. The velocity is integrated in closed form, so the camera
covers the same ground per second at 30 fps as at 240 — and `setCamera` from the debug hook clears the
momentum outright, which is what keeps the Playwright poses exact.
| `npm run dump-textures -- RUN/MP2.ZDB` | every texture to PNG, both pixel orders and both CLUT orders, plus contact sheets |
| `npm run export-gltf -- RUN/MP2.ZDB` | one map's world mesh to a `.glb`, for Blender or a glTF validator |

## No game data in the repository

`public/maps/` and `test-fixtures/` are git-ignored, and so is everything the tools write into them —
archives, PNGs, `.glb` files and Playwright screenshots. They are regenerated from the disc by
`npm run extract-maps`, never committed.

## The packages

- **`archive`** — ZDB table of contents, ZAR/ZED v2, compiled `.rdr`, and the `AssetSource` the rest read through.
- **`gs`** — GS texture and palette decode: PSMT8 with CT16/CT32 CLUTs, PSMCT16 and PSMCT32 direct.
- **`mesh`** — the DMA-chain walk, the VIF1 unpack, and the vertex-lane interpretation that yields `MeshData`.
- **`scene`** — world root, scene graph and node matrices, clutter, collision, the measured spawn table.
- **`viewer`** — the Vite app: three.js renderer, the build-camera fly controls above, map picker, overlays,
  diagnostics panel. `test/camera.test.ts` pins the motion model — ramp, glide, frame-rate independence,
  which axis each key moves along — rather than the tuning constants, which are meant to be tuned.

## Known gaps

- **MP6 and MP72 prop chains.** Eleven model-nodes across Desert Glory and Crossroads fail in the `mesh`
  packet decoder: their chains carry relocation-type-1 tags (36 §3) the walker enters at the wrong offset,
  so the header it then reads is nonsense. The maps draw without those props and say so in the diagnostics
  panel. First work item of M6.
- **Spawns are not on the disc.** `AIMAPS.MPS` is the file that would hold them and no reader for it exists;
  `scene/spawns.ts` carries the measured table instead, so a map that was never measured opens on its own
  extent rather than at a spawn.
- **The ISO source is M5.** Only the served `public/maps/` tree loads today. The seam is `sourceFor` in
  `packages/viewer/src/worker.ts`, which builds an `HttpAssetSource` per base URL; an ISO source needs a
  `File` from the page, so `ViewerRequest` will have to carry one rather than a `baseUrl` string.
