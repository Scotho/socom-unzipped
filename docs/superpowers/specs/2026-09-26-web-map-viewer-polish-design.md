# Web map viewer — audit and polish pass (design)

**Date:** 2026-09-26. **Scope:** `web/packages/viewer` and the decoders it leans on. **Status:** the
audit is done, the design below is what the pass implements; findings are appended as they land.

## 1. What was asked

Audit the viewer as it stands and improve every aspect of it: accuracy to the original engine, the
mobile controls, presentation and feel. The bar is *as close to native re-rendering as a browser can
get without emulating the game*, smooth and fast, and true to SOCOM. Nothing was excluded, so the
pass is organised by area, and each change is tied to a measured fact or a screenshot.

## 2. Audit: where it stood on 2026-09-26

Baseline: `npm run typecheck` clean, `vitest` 214/214 green, the e2e suite green. Fresh screenshots
(desktop 1280×800, iPhone 13 emulation) of Frostfire, Crossroads, Desert Glory, Night Stalker and
Bitter Jungle, plus a tally of what every texture's bind packet and every drawn packet's GIFtag
actually says (`tools/dump-gsstate.ts`, `tools/dump-fge.ts`, both new).

### 2.1 Accuracy faults, in order of visibility

1. **Every sky is missing.** Frostfire and Night Stalker render black above the horizon; Bitter
   Jungle and Desert Glory show flat fog colour. The dome is decoded and drawn — it is *fogged to
   the fog colour* because the viewer fogs every surface. The disc says otherwise: the per-packet
   GIFtag `PRIM` template carries `FGE`, the GS fog-enable bit, and `tools/dump-fge.ts` over all 22
   maps shows the packets that clear it are exactly the skies (`*sky*`, `skycap`, `clouds`,
   `moon`, `star`, `sunglow`), the self-lit surfaces (`lightrays`, `lightglow*`, `light_bulb`,
   `bomb_glow`, `monitor_*`, `tex_computer*`, `metallight`) and water (`a_water`). SEMANTICS §11.4
   asked whether the bit was deliberate or exporter noise. It is deliberate: a per-surface "no fog".
   The viewer ignores it.
2. **The GS draw state is guessed from pixels when it is on the disc.** Each texture record ends in
   a bind packet whose GIF A+D block writes `ALPHA_1`, `TEX1_1`, `TEX0_1`, `TEST_1` and `CLAMP_1`.
   Tallied over all 22 maps (`tools/dump-gsstate.ts`, 10,000 texture records):
   - `ALPHA`: `(Cs-Cd)*As+Cd` source-alpha blend on most; **`(Cs-0)*As+Cd` additive** on 212
     (glows, flares); `(Cd-0)*As+Cd` on 22 (a "brighten the destination" light map);
     `(Cs-Cs)*As+Cs` = no blend on the 146 cutouts; one `(Cs-0)*FIX[0]+Cd` (`lightglow.tif` on
     MP61, a glow the EE animates and that draws nothing at rest).
   - `TEST`: `ATE=0` on all but the cutouts, which set **`ATE=1, GREATER, AREF=64`** — an alpha
     test at exactly half of the PS2's 128 unity. `ZTE=1, GEQUAL` everywhere.
   - `TEX1`: `MMAG=LINEAR` everywhere; `MMIN=LINEAR` (no mipmaps) on the bulk, and
     **`LINEAR_MIPMAP_LINEAR` with `MXL` 1 or 2** on about 70 ground and detail textures, LOD
     bias `K` around −8.
   - `CLAMP`: `REPEAT`/`CLAMP` per axis, with a few `REGION_*`.
   The viewer instead samples alpha to decide "graded", "transparent" and "opaque", applies one
   blend mode, never uses additive, never mipmaps, and picks wrap from the graded guess.
3. **The lighting is too dark, and the default is a compromise.** The rig is exact (see the
   2026-09-20 spec) but renders ~8× too dark against the PS2 capture; the panel opens at the
   owner's eyeballed trim (ambient +0.10, exposure 1.90×) rather than at the calibrated 8×.
   Crossroads' spawn interior renders near black. *Section 4 records what the research found.*
4. **The camera is not the game's.** The viewer opens at 65° vertical FOV. Every map's
   `cameras/camera` authors `fov (0.6109 0.4276)` — half-angles of 35° and 24.5°, a **49° vertical
   field** (46° on Rat's Nest), and a tan ratio of 1.536 that is 4:3 stretched by 512/448, i.e.
   the projection is built in framebuffer pixels and the CRT widens it.
5. **Altitude fog** is parsed and not applied (six maps).
6. **Blended world draws are one mesh per texture.** three sorts transparent objects by centre, and a
   map-wide mesh has one centre, so blended world surfaces can sort wrongly against each other.

### 2.2 Presentation and feel

- No PS2 presentation option: the game drew a 512×448 field-rendered frame onto a 4:3 CRT. A
  viewer that only ever draws at native resolution and 16:9 never looks like the game.
- `THREE.Clock` is deprecated (a console warning on every load).
- A page with no WebGL at all shows "booting" forever: `boot()` rejects unhandled.
- No deep link: the map cannot be shared by URL and the last map is not remembered.
- Pointer lock is requested without `unadjustedMovement`, so mouse acceleration reaches the look.
- No keyboard look (arrows), no fullscreen control.

### 2.3 Mobile

- The canvas is `100vh`, which on iOS is taller than the visible viewport: the frame's centre is
  off and the bottom of the world is under the browser bar. `100dvh` and a `visualViewport` resize
  fix it.
- Drag-look on a phone is the mouse rate (0.0028 rad/px): a full-width drag on a 390 px screen is
  62°, half what a thumb expects.
- No fullscreen, no boost, no landscape hint. The pixel ratio is capped at 2 with no adaptation, so
  a weak phone renders Crossroads' 44k triangles at 2× and drops frames.
- `overscroll-behavior` is not set on the page, so a stray vertical drag can rubber-band.

## 3. Design

### 3.1 Honour the disc's GS state (accuracy)

**`gs`**: `parseTextureRecord` decodes the bind packet's `ALPHA_1`, `TEX1_1`, `TEST_1` and `CLAMP_1`
into a typed `GsState` on the record (`blend: 'source' | 'additive' | 'destination' | 'none' |
'fixed'`, `alphaTest: number | null` as a 0..1 threshold, `mipmaps: boolean`, `wrapS/wrapT`). The
existing `tex0` recovery is untouched; the four new registers are read by id from the same block.

**`mesh`**: `MeshData` gains `fog: boolean`, from `TOP+0`'s `FGE` (the family-B template; `TOP+1`
keeps the bit set on every packet of every map, and a dome or a water plane is always partially
visible, so family B is the path those surfaces actually take). `mergeMeshes` keeps it when every
part agrees and defaults to `true`. `LineStrip` gains the same.

**`viewer`**: `loadMap` groups the world by `(texture, fog)`; `textureFlags` carries the `GsState`.
`world.ts` builds materials from it:

| disc | three material |
|---|---|
| `ATE=1 GREATER 64` | `alphaTest = 0.5`, opaque, depth write |
| `ATE=0`, source blend, texture has non-solid texels | `transparent`, `NormalBlending`, no depth write |
| `ATE=0`, additive | `transparent`, `AdditiveBlending`, no depth write |
| `ATE=0`, destination | drawn as additive (the closest a fixed-function blend can get; noted) |
| `ATE=0`, any blend, every texel solid | opaque |
| `TEX1.MMIN` mipmapped | `generateMipmaps`, `LinearMipmapLinearFilter` |
| `CLAMP.WMS/WMT` | `RepeatWrapping` / `ClampToEdgeWrapping` (region modes as their base) |
| `FGE = 0` | `material.fog = false` |

The "blend graded alpha" toggle stays as an escape hatch and now means "honour the disc's blend
modes" (off = the old cutout-at-half for everything with alpha). `isGraded`/`isOpaque` remain only
as the "has non-solid texels" test that keeps an opaque wall out of the transparent queue. Backface
culling keeps the texture-solid rule from the 2026-09-20 spec, which the state block does not
settle (the cull is a VU1 command, not a GS register).

Blended world surfaces are no longer merged map-wide: parts that blend keep their chunk identity
(one mesh per chunk per texture), so three's back-to-front sort has real centres to sort.

### 3.2 The game's camera

Default vertical FOV = `2 * vfov` from `cameras/camera` (49°, 46° on MP8), applied per map;
the wheel and the boost keep their behaviour relative to it. The near plane stays the map's 4.

### 3.3 Fog

Linear fog as before, with the sky and self-lit surfaces exempt by `FGE`. Altitude fog: *see
section 4 for whether the research settled the band.*

### 3.4 Lighting

*See section 4.* Whatever the exposure's mechanical explanation, the panel's default should be the
calibrated pair, not an eyeballed one, unless the calibrated pair is shown wrong on a second map.

### 3.5 PS2 presentation

A "PS2 look" toggle: render at 512×448 into the canvas backing store, present it at 4:3 inside the
viewport (letterboxed, bilinear upscale), with the vertical FOV from the map. Off by default on a
desktop, because a 1:1 image is what a diagnosing eye wants; the toggle is remembered.

### 3.6 Feel and hardening

- `Timer` instead of `Clock`; `boot()` failures land in the status line.
- `?map=MP7` deep links, the last map remembered, and the picker writes the URL.
- `unadjustedMovement` pointer lock where supported; arrow keys look; `F` toggles fullscreen.
- Adaptive pixel ratio: the smoothed frame time above 24 ms steps the ratio down (to a floor of
  0.75), below 12 ms steps it back up to the cap. Cap 2 on a fine pointer, 1.5 on a coarse one.

### 3.7 Mobile

- `100dvh`, `visualViewport` resize, `overscroll-behavior: none`.
- Touch look rate 2× the mouse rate (`pointerType === 'touch'`).
- A fullscreen button beside the frame counter on a coarse pointer; a boost by holding the stick at
  its rim for 400 ms (the stick's own gesture, no new control).

## 4. Findings recorded during the pass

### The factor of eight is two factors, and neither is in the VU (2026-09-26)

The VU1 lighting path applies no shift: normals `ITOF15`, the material colour `ITOF0`, the lights raw
floats, the result `FTOI0` straight into the GIF packet (`socom2_dispatch_0x1b50.cpp` 930-1004,
1604-1770; research/13 §4.1). What the earlier spec missed is *when the path runs*. The EE builds
each object's command list per frame (`FUN_003b5f20`, decomp 307800-308038) and emits the light
command only when `DAT_003e1470` is set, which `FUN_003b6d10` (decomp 308333-308357) takes from the
node's `nparams` flag word: `m_dynamic_motion` (bit 1) or `m_dynamic_light` (bit 2), on the node or on
the model it instances. Surveyed over all 22 maps (`scene.test.ts`, "which placements the engine
lights"): Frostfire, Desert Glory and Crossroads have none; the others flag a handful of ferns, palms,
flares and a few named props. Everything else takes command `0x08`, which copies `record2` into `RGBAQ`
untouched. The world is prelit (bit 5, `prelight`, on 245 of Frostfire's 459 nodes) and drawn as such.

Then the frame is brightened. `docs/research/31` §12-13 (2026-09-16) verified on the console dump
that the post-process redraws the frame with `ALPHA = (Cd - 0) * FIX + Cd`, `out = Cd * (1 + FIX/128)`,
with `FIX = 93` read off the dump, and that the game's auto-exposure thread computes `FIX` from a
column of frame pixels (`FUN_003b24c0`); the defaults cap it at 100.

Arithmetic: the rig at Frostfire's ground normal is about 0.21, so lighting every vertex with it was
five times too dark; the missing brighten is 1.73 more; the product is the "eight". The viewer now
draws `record2 * (1 + FIX/128)` on unflagged parts and `record2 * lit * (1 + FIX/128)` on flagged ones,
lifts the fog and clear colours by the same factor, and opens at `FIX = 93`. The panel keeps a "rig on
every node" toggle so the old reading can be compared.

### The GS draw state is on the disc, per texture (2026-09-26)

`tools/dump-gsstate.ts` over all 22 maps: every texture record's bind packet is the `0x64` packet VU1
sends, a GIFtag `0x1000000000008005` and five A+D writes -- `ALPHA_1`, `TEX1_1`, `TEX0_1`, `TEST_1`,
`CLAMP_1`. Section 2.1 item 2 has the tally. `@s2u/gs` decodes it as `GsState`;
`viewer/src/materialSpec.ts` maps it to a material and is pinned by ten tests. The earlier claim that
"every texture sets 0x44 with the test off" was a five-map sample read one quadword early.

### `FGE` is a per-surface "no fog", and the skies were never missing (2026-09-26)

`tools/dump-fge.ts` -- SEMANTICS §11.4 is answered, and the answer is in the mesh package as
`MeshData.fog`. The sky dome is ordinary `worldmodel` geometry (reCOM has no sky pass); it was being
drawn, fogged to the fog colour.

### Altitude fog is read off the EE, not inferred (2026-09-26)

`sub_00294070` from `0x2947D0`: `m_fog_alt[0].y = fog_bottom`, `m_fog_alt[1].y = 1 / (fog_top -
fog_bottom)`; `sub_00293F90` copies them to qwords 28/29 beside `offset`/`scale`, parking them at
`-10000` / `0.001` when the flag is off. The VU multiplies the distance term by `clamp(dot(P - ref,
scl), 0, 1)` (research/13 lines 570-585). No dump from an altitude map exists, so the band is applied in
world space; the dumps show `ref`/`scl` rewritten per object into model space, which is the same test
on an unscaled object.

### three's range fog is a smoothstep (2026-09-26)

`rangeFogFactor` is `smoothstep(near, far, viewZ)`, not the GS's linear ramp. The viewer's fog is
therefore a TSL node of its own on `scene.fogNode` (`viewer/src/fog.ts`), which is also where the
altitude band lives.

### The console's frame (2026-09-26)

`zVid_Init` sets 640×448; `zvid_SetVideoMode`'s NTSC branch is interlaced field mode; the static GS
packet at `0x3E0880` has `DTHE = 0` (no dither), `COLCLAMP = 1`, a Z16S depth buffer; the DISPLAY
register shows 640 pixels on a 4:3 set. Every map authors `fov (0.6109 0.4276)` -- half-angles, and
the engine forces the horizontal one (`node_saveload.cpp:309`) -- so the projection is 70° by 49° in
framebuffer pixels, anamorphic by 448/640 against 4:3. The PS2 picture mode reproduces exactly that.

## 5. Verification

- Unit: the new decoders (`GsState`, `fog` on `MeshData`) pinned on synthetic packets and on the
  Frostfire fixtures; material mapping pinned in `viewer/test`.
- e2e: the existing three-map run stays green; a phone-viewport pass is added; screenshots before
  and after in `test-fixtures/screens/audit-2026-09-26/`.
- Typecheck and vitest clean; a build under `VIEWER_BASE=/map-viewer/` for the s2u deploy.
