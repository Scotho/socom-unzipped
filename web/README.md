# SOCOM Unzipped map viewer — SOCOM II's multiplayer maps, decoded from the disc and drawn in a browser

Goal: every SOCOM II: U.S. Navy SEALs multiplayer map, read byte for byte out of the game's own
`RUN/MP*.ZDB` archives — container, scene graph, DMA/VIF geometry, GS textures and palettes, lighting,
fog, collision — and drawn again with three.js as close to the console's own picture as a browser
allows, without emulating the game. Nothing is pre-baked and no asset is committed; **you supply your
own disc**. It runs at [s2u.scotho.com/map-viewer](https://s2u.scotho.com/map-viewer/).

It is a spin-off of [**SOCOM Unzipped**](https://github.com/Scotho/socom-unzipped), the static
recompilation of the game for PC. This repository is the `web/` tree of that project on its own: the
viewer stands alone, builds alone, and deploys as a static site, and the research it stands on lives
in the parent project (see [What you need from SOCOM Unzipped](#what-you-need-from-socom-unzipped)).

**Start here if you are a new agent or contributor:** the design and the findings recorded as the
viewer was built are in the parent project's
[`docs/superpowers/specs/2026-09-20-web-map-viewer-design.md`](https://github.com/Scotho/socom-unzipped/blob/main/docs/superpowers/specs/2026-09-20-web-map-viewer-design.md)
and
[`2026-09-26-web-map-viewer-polish-design.md`](https://github.com/Scotho/socom-unzipped/blob/main/docs/superpowers/specs/2026-09-26-web-map-viewer-polish-design.md);
the byte-level format authority is
[`docs/research/36-mp-map-archive-anatomy.md`](https://github.com/Scotho/socom-unzipped/blob/main/docs/research/36-mp-map-archive-anatomy.md),
and the meaning of every vertex lane is [`packages/mesh/SEMANTICS.md`](packages/mesh/SEMANTICS.md), here.
Comments in the code cite `docs/research/NN` and `FUN_00xxxxxx` decompilation addresses: those are the
parent project's research notes and its Ghidra function names.

## How it works (one paragraph)

`@s2u/archive` reads the ZDB table of contents and the ZAR/ZED containers inside it. `@s2u/scene`
reads the map's scene graph (`MP*_GEO.ZED`) into nodes with matrices, walks it the way the engine did,
and places every model, plus the clutter from `CLUTTER.ZAR` and the collision hull. `@s2u/mesh` walks
each model's DMA chain, decodes the VIF1 unpacks into vertices exactly as VU1 would have, and reads the
GIFtag templates for what the packet was (a mesh, a line strip) and how it was to be drawn.
`@s2u/gs` decodes the textures and palettes (PSMT8 with CT16/CT32 CLUTs, PSMCT16 and PSMCT32) and the
GS state block each texture's bind packet sets. `viewer` builds three.js objects from all of that in a
worker, draws them with a shading graph that does the GS's own arithmetic (modulate, clamp, fog,
brighten, blend) in the order the engine drew them, and puts a fly camera in front of it.

## Build

### Prerequisites

- **Node 24** or newer (the tools use `import.meta.dirname` and top-level `await`).
- **A disc tree**: a directory with `RUN/MP*.ZDB` in it, from your own SOCOM II disc (US retail,
  SCUS-97275). The viewer needs only those 22 archives, about 224 MB. See the next section for where
  to get them.

### What you need from SOCOM Unzipped

The viewer needs **no recompiled game, no toolchain and no emulator** — nothing from the parent
project's build. What it takes from SOCOM Unzipped is:

1. **The disc tree.** SOCOM Unzipped's launcher and tooling read the game out of your own ISO into a
   `game/disc/` directory ([its README](https://github.com/Scotho/socom-unzipped#readme), "The user
   supplies their own disc image"); `tools/extract-maps.ts` defaults to that location. You do not have
   to go through the recompilation to get one: mounting the ISO (double-click on Windows, `hdiutil`
   on a Mac, `mount -o loop` on Linux) gives you the same `RUN/` directory, and that is all the
   extractor reads.
2. **The research.** The format is documented in the parent project's `docs/research/` — `36` for
   the archives, `13` for the VU1 world-object program the vertex decode mirrors, `31` for the
   brighten and the blend equations, `26` for the GS state — and the design specs above. The code
   here cites them by number; they are not copied into this repository.
3. **reCOM**, the open-source re-implementation of the engine SOCOM Unzipped vendors under `recom/`,
   which is where the engine's draw order (`zRender/zrndr_pipe.cpp`) and the scene-graph hookup
   (`zVisual/vis_main.cpp`) were read.

### Commands

Run from the repository root:

| command | what it does |
|---|---|
| `npm install` | workspace install (five packages plus `tools`) |
| `SOCOM_DISC=/path/to/disc npm run extract-maps` | disc tree → `public/maps/RUN/*.ZDB` + `index.json`, and three test fixtures. **Run this first.** (`SOCOM_DISC` defaults to `C:/projects/socom_pc/game/disc`.) |
| `npm test` | vitest over every package; the fixture-backed tests skip when the extractor has not run |
| `npm run typecheck` | `tsc` over the five packages, the viewer and `tools` |
| `npm run dev` | Vite at `http://localhost:5173` |
| `npm run build` | the viewer as a self-contained static site in `dist/viewer/` (~830 kB, 220 kB gzipped) |
| `VIEWER_BASE=/map-viewer/ npm run build` | the same, to be served under a path prefix |
| `npm run e2e` | Playwright: loads all three fixture maps, asserts the stats, toggles the overlays, writes screenshots |
| `npm run dump-textures -- RUN/MP2.ZDB` | every texture to PNG, both pixel orders and both CLUT orders, plus contact sheets |
| `npm run export-gltf -- RUN/MP2.ZDB` | one map's world mesh to a `.glb`, for Blender or a glTF validator |

### Deploying

`dist/viewer/` needs nothing but a web server and a `maps/` directory beside it holding the output of
`extract-maps` (`maps/index.json` and `maps/RUN/*.ZDB`). The archives are the game's; serve them only
where you are entitled to.

## Layout

| Path | What |
|---|---|
| `packages/archive` | ZDB table of contents, ZAR/ZED v2, compiled `.rdr`, and the `AssetSource` the rest read through (`/node` for the file system, `http` for the browser) |
| `packages/gs` | GS texture and palette decode, and the GS state block (`ALPHA`, `TEX1`, `TEST`, `CLAMP`) per texture |
| `packages/mesh` | the DMA-chain walk, the VIF1 unpack, and the vertex-lane interpretation that yields `MeshData` and `LineStrip`; `SEMANTICS.md` is the authority |
| `packages/scene` | world root, scene graph and node matrices, the engine's walk order, clutter, collision, the measured spawn table |
| `packages/viewer` | the Vite app: renderer, shading graph, fly camera, map picker, overlays, diagnostics panel, the Playwright e2e |
| `tools/` | the extractor and the dump/export tools |
| `public/maps/`, `test-fixtures/` (ignored) | your extracted game data; never committed |

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
momentum outright, which is what keeps the Playwright poses exact. `test/camera.test.ts` pins the motion
model — ramp, glide, frame-rate independence, which axis each key moves along — rather than the tuning
constants, which are meant to be tuned.

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
panel's title bar beneath it. The panel opens folded on a coarse pointer (a remembered choice still
wins), its body scrolls inside itself, and the status line drops the draw and collision counts and
abbreviates the rest so it fits on one row at 360px. The lift buttons clear the browser's own bottom
bar with `env(safe-area-inset-bottom)`.

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

Settled on 2026-09-26 (the polish spec linked at the top):

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
  A packet whose GIFtag clears `FGE` — every sky, moon, star, water plane and self-lit surface on every
  map (`tools/dump-fge.ts`) — takes no fog, which is what puts the horizon back.
- **The camera is the map's**: a 49° vertical field (`m_vfov`, a half-angle of 24.5°), 46° on Rat's Nest.
- **The PS2 picture** (`options`): the 640×448 frame the console drew, projected with the map's own
  half-angles and stretched onto a 4:3 box the way the television did.
- **The draw order is the engine's** (`options`, "draw in the disc's order", on by default). reCOM's
  `CPipe::RenderNode` walks the scene graph depth first and draws each visual as it reaches it, blended
  or not, deferring only a node whose opacity is under 1 — it sorts nothing — and the live GS state is
  `ZMSK = 0` on every draw (research 26 §2). So every draw carries its place in that walk
  (`LoadedMesh.order`), goes out in it with depth written, and the merge that turns hundreds of world
  packets into a few dozen draws is cut at every blended chunk so an opaque draw never straddles one
  (`loadMap.ts`, pinned by `test/loadMap.test.ts`). A glow drawn before the wall behind it keeps the
  wall out, as it did on the console. Off is three's order: blended draws sorted back to front by
  object centre, no depth under them, which never punches a hole and is never quite where the game
  drew it.
- **The shading is the GS's modulate, in the GS's order** (`world.ts`): `(texel * vertex) >> 7`, the
  product clamped by `COLCLAMP` *before* the fog is mixed in, then the post-process's `1 + FIX/128` as a
  uniform on every material rather than a factor baked into the vertex — so an overbright vertex under
  fog comes out as the hardware had it, and moving the brighten slider rewrites nothing. The
  `(Cd - 0) * As + Cd` light maps are drawn with their own equation: the shader emits `As` and the blend
  is `Cs * Cd + Cd`, the fix the game's own GL backend made (research 31 §12).
- **The line strips are drawn** (`options`, on by default): one pixel wide, textured along the strip
  with the uvs the packet carries (they run well past 0..1, so the texture repeats along a rope),
  gouraud, fogged and blended — `PRIM = IIP|TME|FGE|ABE` on all 194 packets — as one `LineSegments`
  per (texture, fog) with the same shading graph the meshes use. Desert Glory's power lines and lamp
  brackets, Crossroads' tent ropes and light filaments.

## Known gaps

- **Backface culling is inferred from the texture, not read.** The PS2 culls on VU1, and whether a
  given object is culled is chosen by a command list the EE builds per draw — it is not on the disc.
  The viewer culls where the texture is fully solid and keeps both faces where it is not, because a
  solid two-sided surface is modelled as two coincident sheets (Crossroads' awning) while a cutout
  sheet is modelled once (a leaf card). It is the right call on every map swept, but it is a rule
  about textures standing in for a fact about draws. The cull command is emitted per visual from a
  flag byte the decomp reads (`FUN_003b5f20`, `flags & 8`), most likely `vparams` word 0, which the
  scene package does not yet parse.
- **The engine's region culling is not modelled.** `CanSeeRegion` skips whole nodes per frame by the
  camera's region mask; the viewer draws every node. That changes nothing about what is in front of
  what, only what is drawn at all, and the region masks are parsed but not yet used.
- **The one EE-animated `FIX` glow** (`lightglow.tif` on MP61, `(Cs - 0) * FIX + Cd`) is drawn additive:
  its factor is game logic, and at rest it draws nothing.
- **The auto-exposure is a slider.** `FIX` is computed per frame from a column of frame pixels; the
  viewer opens at the one value measured (93) and leaves the readback unmodelled.
- **The detail texture pass is not drawn** (SEMANTICS §11.6).
- **Spawns are not on the disc.** `AIMAPS.MPS` is the file that would hold them and no reader for it exists;
  `scene/spawns.ts` carries the measured table instead, so a map that was never measured opens on its own
  extent rather than at a spawn.
- **The ISO source is M5.** Only the served `public/maps/` tree loads today. The seam is `sourceFor` in
  `packages/viewer/src/worker.ts`, which builds an `HttpAssetSource` per base URL; an ISO source needs a
  `File` from the page, so `ViewerRequest` will have to carry one rather than a `baseUrl` string.

## No game data in the repository

`public/maps/` and `test-fixtures/` are git-ignored, and so is everything the tools write into them —
archives, PNGs, `.glb` files and Playwright screenshots. They are regenerated from the disc by
`npm run extract-maps`, never committed. SOCOM II: U.S. Navy SEALs and all of its assets — models,
textures, maps, audio — are the property of Sony Interactive Entertainment, developed by Zipper
Interactive. This project is not affiliated with, endorsed by, or connected to Sony Interactive
Entertainment.

## Licence

GPL-3.0, as the parent project ([`LICENSE`](LICENSE)).

## This repository and the parent project

This tree is developed as `web/` inside
[SOCOM Unzipped](https://github.com/Scotho/socom-unzipped) and published here with `git subtree`:

```
# from the socom-unzipped checkout, on the branch that carries web/
git subtree push --prefix=web git@github.com:Scotho/socom-unzipped-map-viewer.git main
```

Pull requests here are welcome and are carried back the same way (`git subtree pull`).
