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
| double-tap `W`, held | boost, with the field of view widening to match. Nothing is bound to `Ctrl`: `Ctrl+W` closes the tab and no page can prevent it |
| wheel | trims the fly speed between 0.1x and 16x; the panel shows the trim |
| `Q`/`E` | down and up, kept from the earlier bindings |
| arrow keys | look, at a steady rate, for a keyboard with no mouse to hand |
| `F` | fullscreen, and back (also the button under the frame counter) |
| `` ` `` | hides and shows the panel and the frame counter, for a clean look at the map |

The mouse is captured with `unadjustedMovement` where the browser offers it, so the OS's pointer
acceleration stays out of the look. `?map=MP7` opens a map by its archive, the picker writes the URL,
and the last map picked is remembered for the next visit.

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

## On a touch screen

A one-finger drag looks around, which the canvas gives for free. Moving is the part a phone had no way
to do, so the left half of the screen is a virtual stick — a circle that appears wherever the thumb
lands and follows it — and two buttons in the bottom-right corner do what Q and E do. The right half
is left alone so looking still works while the stick is held. The stick feeds an axis pair into the
same velocity model the keys drive, so the ramp, the glide and the frame-rate independence come out of
that for free; `stickVector` in `viewer/src/touch.ts` is the only arithmetic, and it is unit-tested.

They appear on a coarse pointer, or at the first touch event for a hybrid a media query gets wrong,
and not at all on a mouse. A touch drag turns twice as far per pixel as a mouse drag, because a thumb
has a phone's width to work with; the stick held at its rim for 400 ms is the boost, the one gesture a
thumb can make without leaving the stick; and a round fullscreen button sits above the lift buttons,
which on a phone also asks for a landscape lock. The canvas is `100dvh`, so the picture's centre is the
screen's whether or not the browser bar is showing, and the pixel ratio starts at 1.5 on a coarse
pointer and adapts (`main.ts`, `adapt`): frames over 24 ms step it down to 0.75, frames under 12 ms
step it back up.

Everything the viewer draws over the map goes in one strip along the top: the back link, then the
panel's title bar beneath it. Beneath and not beside — the link is 147px and the header wants 244px,
which with the chevron and the padding needs 442px, and none of 360, 390 or 430 has it. The panel
opens folded on a coarse pointer (a remembered choice still wins), its body is capped at
`55vh - 96px` and scrolls inside itself so it can never reach the stick's zone, and the status line
drops the draw and collision counts and abbreviates the rest so it fits on one row at 360px. The
lift buttons clear the browser's own bottom bar with `env(safe-area-inset-bottom)`.

Deliberately minimal: one gesture, and no tuning pass beyond the look rate.

## Loading a map without freezing the page

Switching maps used to take one 690–1,703 ms frame, and the whole of it was the *first frame that drew
the new map*: `buildWorld` costs 14–20 ms, and then three uploads every texture and geometry and
compiles every program at once. So the build still happens in one go and what is spread out is the
showing — `buildWorld` returns its objects in two queues and `viewer/src/scheduler.ts` hands them to
the scene a few per frame. The world's own meshes go first and the previous map stays up until they
start landing; the props follow behind a map that is already drawn and flyable.

The budget that does the work is a **count**, not a clock: adding a mesh to a group costs about a
hundredth of a millisecond, and the 400 ms is spent in the render that follows, where a time budget
cannot see it. The collision hull — tens of thousands of segments on the larger maps, and off by
default — is likewise held as arrays and only made into an object the first time it is switched on.

Meanwhile the overlay says what is happening: bytes fetched (the archive is read a chunk at a time so
the bar has a real denominator), then the worker's own stages, then the scene build. The map picker is
the only control taken away while a load runs.

## What the picture is made of

Settled on 2026-09-26 (`docs/superpowers/specs/2026-09-26-web-map-viewer-polish-design.md`):

- **The world is drawn unlit, then the frame is brightened.** The EE emits the VU1 light command only
  for a node flagged `m_dynamic_motion` or `m_dynamic_light`; on most maps that is nobody, and the
  vertex colours the exporter baked go to the GS untouched (`viewer/src/lighting.ts`). The game's
  post-process then multiplies every pixel, fog included, by `1 + FIX/128`, `FIX` being its
  auto-exposure's reading (93 on the console dump). That is the "factor of eight" the earlier notes
  could not place. The rig from `GlobalLighting` is exact and is applied to the flagged nodes only.
- **The GS state is read off each texture's bind packet** (`gs/src/gsState.ts`, `viewer/src/materialSpec.ts`):
  the blend equation (source alpha, additive on 212 glows, none on the cutouts), the alpha test and its
  reference (`GREATER 64`, exactly half), the filtering and mipmap request, and the wrap mode per axis.
  Nothing about a texture's alpha is guessed from its pixels any more, except whether it has any.
- **Fog is the GS's linear ramp with the altitude band**, as a fog node of its own (`viewer/src/fog.ts`):
  `F = clamp(w*scale + offset) * clamp((y - bottom)/(top - bottom))`, the second term read off the EE's
  own setup and parked at the engine's off values (`-10000`, `0.001`) on the sixteen maps without it.
  A packet whose GIFtag clears `FGE` -- every sky, moon, star, water plane and self-lit surface on every
  map (`tools/dump-fge.ts`) -- takes no fog, which is what puts the horizon back.
- **The camera is the map's**: a 49° vertical field (`m_vfov`, a half-angle of 24.5°), 46° on Rat's Nest.
- **The PS2 picture** (`options`): the 640×448 frame the console drew, projected with the map's own
  half-angles and stretched onto a 4:3 box the way the television did.

## Known gaps

- **Backface culling is inferred from the texture, not read.** The PS2 culls on VU1, and whether a
  given object is culled is chosen by a command list the EE builds per draw -- it is not on the disc.
  The viewer culls where the texture is fully solid and keeps both faces where it is not, because a
  solid two-sided surface is modelled as two coincident sheets (Crossroads' awning) while a cutout
  sheet is modelled once (a leaf card). It is the right call on every map swept, but it is a rule
  about textures standing in for a fact about draws. The cull command is emitted per visual from a
  flag byte the decomp reads (`FUN_003b5f20`, `flags & 8`), most likely `vparams` word 0, which the
  scene package does not yet parse.

- **The blend order is three's.** The hardware sorted nothing: it walked the grid and deferred only
  fading objects. three draws blended surfaces back to front by object, so the graded textures keep one
  mesh per chunk and never write depth; a `(Cd - 0) * As + Cd` brighten and the one EE-animated `FIX`
  glow are drawn additive, the nearest fixed-function blend.
- **The auto-exposure is a slider.** `FIX` is computed per frame from a column of frame pixels; the
  viewer opens at the one value measured (93) and leaves the readback unmodelled.
- **The detail texture pass is not drawn** (SEMANTICS §11.6).

- **Spawns are not on the disc.** `AIMAPS.MPS` is the file that would hold them and no reader for it exists;
  `scene/spawns.ts` carries the measured table instead, so a map that was never measured opens on its own
  extent rather than at a spawn.
- **The ISO source is M5.** Only the served `public/maps/` tree loads today. The seam is `sourceFor` in
  `packages/viewer/src/worker.ts`, which builds an `HttpAssetSource` per base URL; an ISO source needs a
  `File` from the page, so `ViewerRequest` will have to carry one rather than a `baseUrl` string.
