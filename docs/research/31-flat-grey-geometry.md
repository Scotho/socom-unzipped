# 31 — Flat grey geometry in Seeding Chaos: the water shards and the ground patch

Read-only research, 2026-09-16. No build, no run, no code change. **[verified]** = read off a file or
computed from one in this pass (command/line given); **[inference]** = follows from verified facts, not
measured. Builds on research/26 (water pass), /27 (depth refuted), /25 §9-§10 (VRAM park).

## 0. Condition sentences [inference]

- **Form 1 (water shards, every stamp since Sprint 2).** The `0x34` env-map pass of the water object
  (vertex RGBA (33,33,33), α 0-51, TEX0 TBP0 0x38a8 PSMT8 32x32, CBP 0x3852 CT16, MODULATE, TCC 1,
  ALPHA 0x44, bilinear) samples a texture whose decoded texels are wrong — bright/opaque where the console's
  are dark — so each sphere-mapped triangle, which reads only a few texels, blends a nearly flat grey
  (~37) over the brown bed instead of a faint reflection; triangles whose texels decode to zero go
  black. Angular shards and black holes are the per-triangle texel values, not geometry or depth.
- **Form 2 (intermittent ground patch, new since a81eb74).** A terrain draw near the stone steps is
  submitted while its texture, or the CLUT it indexes, is served from a stale or not-yet-written region of
  the render-thread shadow VRAM (or with TME=0), so the polygon shows its neutral Gouraud lighting only.
  Which of the two (stale cache vs TME=0) is decided by one field of the trace in §4.

Both forms are "vertex colour with no real texel", which is why they share a tone; they need not share a
cause. §2 shows the tone arithmetic fits a **bright opaque texel**, not an all-zero CLUT and not TME=0
for form 1.

## 1. What the frames say [verified]

- `logs/parity/gate/s6_probe/mission/s28_none.png` (640x448, 2026-09-15 19:50, after a81eb74 19:43):
  grey shards in the stream, 11 flat 16x16 cells (std<1.5, r≈g≈b) at (29,28,26)-(35,34,31), x 184-416,
  y 216-296; the bed between them is (16-21,13-18,10-16). [`python` scan, this pass]
- `scripts/parity/refs/console_spawn_slot8.png`: 0 flat grey cells; water (42,38,33)-(54,48,43).
- Owner's `2.png` (1602x1072): 45 flat cells in x 80-352, y 688-848, r≈g≈b within 1, but **graded**
  along the patch: 34 → 47 → 62 → 43 → 35 down a column, 31 → 46 → 69 → 43 across a row. The same
  spot in `3.png` has 1 flat cell (a window-border pixel). A fully fogged polygon would be flat
  FOGCOL (`gs_gl_backend.cpp:346` `mix(uFogColor, c.rgb, vFog)`; CPU `gs_cpu_backend.cpp:789-797`),
  so form 2 is **not** fog: it is interpolated vertex colour (IIP) with a constant texel factor.

## 2. Tone arithmetic: what produces this grey

Shader (`gs_gl_backend.cpp:296-329`, CPU `gs_cpu_backend.cpp:1134-1206`) [verified]:
`c = vColor`; TME=0 leaves it; MODULATE gives `c.rgb = min(c.rgb*t.rgb*2, 1)`, `c.a = min(c.a*t.a*2,1)`
with TCC=1. Blend 0x44 = `(Cs-Cd)*As + Cd` (research/26 §4).

For the water `0x34` pass (Cs vertex (33,33,33), α ≤ 51, bed Cd ≈ 18) [computed]:

| texel | result over bed 18 | matches shards (29-42)? |
|---|---|---|
| TME=0 (Cs as-is, As=51/255) | 18 + (33-18)*0.2 = **21** | no |
| CLUT all zero (t=0) | c=0 → 18 - 18*As → **darker than bed** | no — but explains the **black holes** |
| t.rgb = 0x80 (grey), t.a = 0x80 | c = 33, a = 0.4 → **24** | no |
| t.rgb ≈ 0xFF, t.a ≥ 0x80 | c = 66, a = 0.4 → 18 + 48*0.4 = **37** | **yes** (29-42 with α 0-51 spread) |

So form 1 needs bright opaque texels for the shards and zero texels for the holes — one wrong 32x32
texture/CLUT, sampled per-triangle through sphere-map ST, gives both [inference]. For the terrain pass
(form 2) TME=0 (`c = vColor`) and a texel of 0x80 (`c*0x80*2/255 = c`) are indistinguishable by tone;
a white texel gives `2c` clamped. The `tme=` field of `[gs-cmd] submit` (line 1221) tells them apart.

## 3. The GL texture cache and where a stale or blank texture can be served [verified, code]

Keying (`gs_gl_backend.h:159-191`, `gs_gl_backend.cpp:2679-2691`): `TextureKey` = TBP0, TBW, PSM,
TW, TH, CBP, CPSM, CSM, CSA, TEXA, TEXCLUT. Entry stores `pageStart = tbp0>>5`,
`pageCount = pageSpan(psm, tbw, 1<<th)` and `generation = m_generation` at decode.

Invalidation (`resolveTexture`, 2693-2707): a hit is served unless `m_shadowPageGeneration[p]` for
any texture page, **or for the single page `cbp>>5`**, exceeds the entry's generation. Pages are marked
(`markShadowPages`, 1430-1435) only by: host->local upload chunks (`executeUpload`, 1460-1468),
local->local copies (`executeTransfer`, 1439-1444), render-thread `WriteVram` (1269-1272), and
`resolveTexture` itself after downloading a GPU render target whose pages overlap the **texture**
pages (2668-2676). Decode reads the render-thread `m_shadowMemory` (2474; `PS2X_GS_TEX_FROM_CPU=1`
switches to the authoritative game-thread VRAM, 2469-2474).

Cases where the served texels can be stale or blank:

1. **CLUT in GPU-drawn pages.** The shadow-refresh loop at 2668-2676 tests only
   `[pageStart, pageStart+pageCount)`, never `cbp>>5`. A CLUT that lives in (or was copied into) a
   render-target page reads the stale shadow. And 2699-2700 checks only one CLUT page.
2. **Readback path does not bump generations.** `downloadRenderTargetToCpu` (2047-2091) writes the
   shadow and clears `shadowStale` (2090) but never calls `markShadowPages`; `downloadRenderTargetToShadow`
   (1980-2041) likewise (its caller marks at 2675, the readback path at 2095-2100 does not). A texture
   decoded from RT pages, then redrawn by the GPU, then read back via the game thread's
   `syncDirtyPagesForRead` (746-757) is served from the old entry: `shadowStale` is false (RT loop skips)
   and no generation moved.
3. **Local->local copy from a GPU-drawn source.** `executeTransfer` (1437-1449) runs
   `m_shadow->BeginTransfer` (the shadow copies at once) without downloading the **source** RT into the
   shadow first; the game-thread `BeginTransfer` (783-819) synced only `m_cpu`. The destination is marked,
   so the next decode is fresh — but of stale bytes.
4. **Rows above 512 / beyond `usedHeight`.** The RT loop's span uses `min(usedHeight, 512)` (2673);
   texture pages under a taller target are not refreshed.
5. **Dirty-row race, documented.** 1580-1608 and 3128-3136: `resolveTexture` between `setupDrawState`
   and the draw can clear `dirtySinceResolve` (research/14 §9.1) — affects RT-as-texture reads, not
   decoded textures.
6. **Blank by construction.** Unsupported PSM decodes magenta 0xFFFF00FF (2549, 2532) — not grey;
   the CPU oracle returns the same (`gs_cpu_backend.cpp:1037`). Not this defect.

The water texture pages are **0x1c5 (TBP0) and 0x1c2 (CLUT)**; a `PS2X_GS_TRACE_PAGES=0x1c2:4`
trace (72-90) prints every upload, copy, download and decode touching 0x1c2-0x1c5 (`[gs-pages]` lines at
1445, 1467, 1695, 1767, 2016, 2069, 2624).

## 4. The VRAM park (a81eb74) and the 0x240000-0x400000 region [verified unless marked]

- Park pages: `0x2400>>5 = 0x120` to `0x200` (seven 0x40000 pieces, `vram_addr` 0x2400 step 0x400;
  research/25 §9). The water texture (byte 0x38a800, page 0x1c5) and its CLUT (0x385200, page 0x1c2)
  are **inside piece 5 (DBP 0x3800, 0x380000-0x3bffff)**.
- Direction (research/25 §10): the load parks the motion pack **into** VRAM; the store reads it back.
  The park is a plain host->local upload through the GIF DMA path (`GS.cpp:645-675`,
  `processPendingTransfers` at 675), so it reaches `executeUpload` and marks pages 0x120-0x1ff: any
  cached texture there is invalidated, correctly. Before a81eb74 the seven pieces aliased to pages 0x100
  and 0x000 (the front buffer) and never touched 0x1c2-0x1c5 — the shards predate the fix
  (research/26 §1: every stamp since Sprint 2), so **the park is not form 1's cause**.
- The console runs the same writes, so the game must upload the mission textures after the restore
  [inference]; our stubs are synchronous, so the order is preserved. The park can only matter if the
  game's texture upload were re-ordered before the store, which the trace in §5 would show as
  `upload dbp=038xx` preceding `transfer dir=1 sbp=03800`.
- Form 2 is new and post-fix; the fix changed which pages the park overwrites (now 0x120-0x1ff,
  including pages terrain textures may stream into) [inference]. Whether a terrain texture sits there
  is answered by the same trace: the `[gs-cmd] submit` covering the patch rect gives its `tbp0`.
- The open packet-offset-0x14 defect (decomp 45100) is the **loading-screen fade** path
  (`REG_GS_PMODE` alpha loop, 64-row strips of a 640-wide CT32 image read from file, DBP += 0x280 per
  strip; `decomp.c:45086-45115`). All strips land on the first DBP in our stub. It writes the display
  buffer, not texture pages: excluded for both forms [inference from the strip geometry].

## 5. The one run that separates the candidates

Mission stage only, environment inherited by the game (`tools_py/parity/gate.py:438-451`,
`env = dict(os.environ)`). `t<seconds>` is host time since process start (`traceSkip`, 1118-1123);
s28 is at ~249 s (research/26 §5), so arm at 240.

```
PS2X_GS_TRACE_PAGES=0x1c2:4 PS2X_GS_TRACE_CMDS=t240 PS2X_GS_TRACE_CMDS_MAX=400000 \
PS2X_GS_DUMP_TEX=<scratch dir> PS2X_GS_GL_DEBUG_AFTER=<frame at 240 s, from the first [gs-cmd] line> \
python -m tools_py.parity.gate --only mission
```

What it yields, and the reading:
- `[gs-cmd] submit ... tbp0=038a8 psm=13 cbp=03852 cpsm=02 ... rgba=212121xx` (1221): the water pass,
  with `tme=` — **tme=0 here would already settle form 1 as a frontend/PRIM defect**, not texture.
- `[gs-pages]` on 0x1c2-0x1c5: the last `upload`/`local-copy` into the texture and CLUT pages before
  that submit, and any `gpu-dirty=1` on the `texture` line (2624-2626) → §3 cases 1-3.
- `PS2X_GS_DUMP_TEX` writes the first 6 decodes after the frame as PPM/PGM (2545-2580) and, for indexed
  textures, prints `clut mismatches shadow vs cpu` with `clut[0..3]` (2506-2524). A mismatch count > 0
  is §3 (shadow stale); 0 with a bright/zero CLUT is game-side VRAM content.
- For the ground patch, run the same command and let the owner walk to the steps; find the
  `submit` whose `sc=`/`v0=` covers the patch rect and read its `tme`, `tbp0`, `cbp`.

**Twin run (zero code): `PS2X_GS_TEX_FROM_CPU=1`** (2469-2474). Shards/patch gone → the render-thread
shadow is stale (§3); unchanged → the VRAM bytes themselves are wrong (upload path or game side).

**Oracle**: `PS2X_GS_BACKEND=cpu` (`gs_frontend.cpp:9-12`) samples VRAM directly with the same CLUT
maths (`gs_cpu_backend.cpp:951-973, 1000-1033`); research/26 §5 doubts it reaches 249 s. If it does,
grey there = VRAM content; textured there = GL cache.

**Console reference**: `python -m tools_py.parity.gsdump_capture --slot 8`, then
`python tools_py/gsdump_timeline.py <dump> --all`; compare the console's last upload into 0x38a8/0x3852
(bytes and dbw) and its TEX0/CLUT with our `[gs-pages]` uploads and the PPM/PGM dumps.

Knobs to add if the above is not enough (uncommitted diagnostics):
- `resolveTexture` 2703-2705 (eviction) and 2596-2610 (`decodeTexture` end): log tbp0/cbp/frame,
  generation delta, and a decode summary — % texels index 0, % texels with rgb ≥ 0xF0, CLUT[0].
- `[gs-cmd] submit` at 1221: append `fge=` and `v[1].fog` so a fogged-flat draw is visible.
- Trace only stale serves: at 2695-2702, print when `newest > generation` for a page in a user-given
  range (reuse `tracePagesHit`).

## 6. Excluded or downgraded [verified]

- Depth test (research/27 §3, `PS2X_GS_NO_ZTEST=1`).
- Fog for form 2 (§1 gradient). Form 1 not excluded by pixels; the trace field settles it.
- TME=0 for form 1 by tone (§2, 21 vs 29-42) — unless the vertex α is larger than the dump's ≤ 51.
- The loading-screen strip defect (§4).
- `Missing`-PSM decode (magenta, §3.6).

## 6. The trace run (`s6_water_trace`, 2026-09-16) [verified]

`PS2X_GS_TRACE_PAGES=0x1c2:4 PS2X_GS_TRACE_CMDS=t240` on a mission gate (PASS, shards present: `water flat=0.504
dark=0.268`); 859k log lines, 447k `[gs-pages]`, 400k `[gs-cmd]`.

- **The water texture is uploaded from EE memory, not copied from the frame buffer**: `transfer dir=0 sbp=00000 spsm=13
  -> dbp=038a8 dpsm=13 dbw=1 at (0,0) 32x32` followed by `upload 1024 bytes` (line 287010, frame 13393), then two more
  uploads of 64x64 (4096 bytes) to the same address later (lines 294575, 303234). `dir=0` is host→local; the `sbp=0` is
  unset. (§0's "copy" reading of an earlier draft is withdrawn.)
- **The CLUT block 0x3852 is a shared scratch slot rewritten every frame in two formats**: a PSMCT32 16x16 (1 KiB)
  upload and a PSMCT16 16x16 (512 B) upload alternate (21 and 16 of each over the trace); the water draws
  (`tbp0=038a8 psm=13 cbp=03852 cpsm=02`) follow the CT16 upload (line 286953 → first water submit 287568), and the
  CT32 upload comes ~130 lines later. 31,567 textured submits use `psm=13 cpsm=02` against 77,485 with a CT32 CLUT, so
  16-bit CLUTs are common, not a water-only path.
- **Uploads and draws are replayed in order on the GL thread** (`executeCommands` cases BeginTransfer/Upload at
  gs_gl_backend.cpp:1261-1268 call `executeTransfer`/`executeUpload`, which write `m_shadow` and `markShadowPages`),
  so the CT16→draw→CT32 alternation is not a record/replay race.
- No `[gs-gl tex]` mismatch lines: the decode diagnostic needs `PS2X_GS_GL_DEBUG_AFTER`; not set in this run.

**Next (queued):** the zero-code twin `PS2X_GS_TEX_FROM_CPU=1` on a mission gate (`s6_water_texcpu2`; the first attempt
never reached the HUD because a plugged-in controller changed the boot flow — `PS2X_HOST_GAMEPAD=0` now pins it). Shards
gone → the GL shadow/cache serves stale or mis-laid texels for this texture/CLUT pair; unchanged → the VRAM bytes the
game uploads are read the same way by both backends and the comparison moves to the PCSX2 slot-8 GS dump.

## 7. The CPU-VRAM twin is not a diagnostic (`s6_water_texcpu2`, 2026-09-16) [verified]

`PS2X_GS_TEX_FROM_CPU=1` on a full mission gate (controller pinned off, pristine card): **every screen from the boot on
renders as noise** -- the armory, the briefing text, the fonts are half-legible over a field of random texels
(`logs/parity/gate/s6_water_texcpu2/mission/s44_holdS.png`) -- and the frame file went stale by 138-174 s per hold
(`SnapshotVram` copies the whole 4 MB per `resolveTexture`; the exe fell to a frame every few seconds). The HUD search
ran its 40 presses on that noise (dist 133, never matched) and the holds landed in the armory. So the game-thread
VRAM read from the render thread is not the authoritative picture it was assumed to be: either the snapshot races
the game thread's uploads, or the decode addresses the two memories differently. Either way the twin cannot say
whether the water's texels are wrong in VRAM or wrong in the cache, and it goes off the list.

**What is left, in order:** (a) the PCSX2 slot-8 GS dump (`gsdump_capture --slot 8`, `gsdump_timeline.py --all`):
the console's last upload into 0x38a8/0x3852 and its TEX0/CLUT against our `[gs-pages]` uploads -- byte-level and
lock-free once the dump exists; (b) the `resolveTexture` eviction/decode log knobs (§5) on a normal run, to see
which cache entry serves the water draw on a shard frame; (c) the `PS2X_GS_BACKEND=cpu` oracle only if (a) and (b)
disagree.

Also noted on the same day's `s6_gamepad5` gate: its spawn capture (`s28_none.png`) is a **letterboxed, HUD-less frame**
(the location cinematic caught after the HUD match) and the console comparison scored it `flat=0.071 dark=0.212`
-- the first 'PASS'-side flat figure ever printed, and meaningless: every HUD spawn frame before it reads
0.503-0.509. The comparison must refuse a frame that is not a HUD frame (gate hardening, done the same day).

## 8. The trace window was the cinematic; the console's water pass, byte for byte (2026-09-16) [verified]

- **Section 6's trace covered no gameplay.** `s6_water_trace` armed at t240; its `[gs-cmd]` window is frames 13198-13408
  and the drive's wait captures at that time (`mission/w27_036..038.png`) show the mission intro cinematic (the car on the
  road, `06:47 HOURS`, letterboxed). The spawn capture s28 lands between 248 s (`s6_blockptr`) and 361 s (`s6_water_trace`)
  across runs, so a host-time arm cannot be aimed at it. The A/B "layouts" in that window (the texture set packed one CLUT
  lower every few frames, binds moving with it) are the cinematic's two camera set-ups, self-consistent, and not a defect.
- **The console at spawn (`tools/pcsx2/snaps/..._20260916033728_(2).gs`, slot 8, 8 frames)** uploads the same set every
  frame -- CT32 16x16 palettes at 0x384e, 0x3852 (CT16 on the first pass, CT32 on the second), 0x3854..0x3894, then T8
  textures 0x3898 64x64, **0x38a8 32x32**, 0x38ac 64x64, 0x38bc 64x64 -- and draws the water with `tbp0=038a8 psm=13
  cbp=03852 cpsm=02 csm=0 tfx=0 tcc=1`, 378 kicks per frame, vertex colour **(0x21,0x21,0x21) with alpha 0x00..0x33**,
  `ALPHA_1=0x44` (`(Cs-Cd)*As+Cd`), `TEST_1=0x5000c`, `TEXA` ta0=0 ta1=0x80 aem=0, `TEX1_1=0x60` (bilinear, no mips),
  `CLAMP_1=0`, `FOGCOL=0x484a4a`. Our cinematic-window submits carry the identical `rgba=2121213x`, cbp/cpsm and test
  word -- the grey vertex colour is the game's, not ours.
- **The console's water texture decodes to blue-grey noise** (`assets/31-console-water-texture-ct16.png`: the 1 KiB T8
  payload through the 512 B CT16 palette, 156 distinct indices, palette colours (74..115, 82..123, 98..123), every alpha
  bit set). With TEXA ta1=0x80 and tcc=1 that is a 40 % blend of `texel * 0x21 * 2 / 255 ≈ 26` over the bed -- the subtle
  dark tint the console shows. So form 1's flat 29-42 grey needs one of: **bright texels** (section 2's table), or **no
  blend at all** (an opaque draw of the modulated texel, 26-33, e.g. PABE set with As < 0x80, or a wrong ALPHA/FBA word
  reaching the GL state), or **fog at full weight** (FOGCOL 72-74 grey, blended at 40 %: ~40).
- **The GL-thread ordering is right at the code level:** `executeCommands` calls `flushBatch()` before every transfer,
  upload, WriteVram, clear and present (gs_gl_backend.cpp), so a batched water draw cannot resolve its texture after the
  second-pass CT32 palette lands on 0x3852. The refresh-from-render-target path never fired either: no
  `download gpu->shadow` line in the whole trace (the 63 `gpu-dirty=1` texture lines at frame 10908 are the boot's
  frame-0 full-VRAM clear note, never acted on).
- **Instrumentation added for the gameplay-window run (`s6_water_state`)**: `[gs-cmd] submit` now prints
  `alpha= pabe= fba= fge= fog= texa=ta0/ta1/aem tex1= tod=HH:MM:SS.mmm`; `PS2X_GS_TRACE_CMDS_TBP0=<blocks>` (comma list)
  and `PS2X_GS_TRACE_CMDS_PER_FRAME=<n>` keep a trace armed for a whole mission; `PS2X_GS_DUMP_TEX_TBP0/_EVERY/_MAX/_FROM`
  sample the decoded water texture across the run (file names carry the frame). The run arms at t250 with
  blocks 0x38a4,0x38a8,0x38a0,0x38ac.

## 9. The gameplay-window trace, and the semantic we did not implement: the GS on-chip CLUT (2026-09-16) [verified]

`s6_water_state` (the section 8 instrumentation, armed at t250; the spawn capture at 318.6 s = frames 14172-14176,
`tod=03:57:07`, shards present: `flat=0.516`):

- **Every water draw in the gameplay window matches the console's state word for word**: `tbp0=038a8 psm=13 cbp=03852
  cpsm=02`, `rgba=212121`, alpha 0x00..0x33, `alpha=44 pabe=0 fba=0 fge=1 fog=ff` (unfogged -- the fogged water submits
  of section 8's table are the cinematic's), `texa=00/80/0`, `tex1=60`, `test=5000c`, 63 submits per frame, 40 fps.
- **The decoded water texture is right at every sampled decode** (`PS2X_GS_DUMP_TEX_TBP0=0x38a8`, frames 14160/14183:
  rgb (72..112, 80..120, 96..120), alpha 128 everywhere -- the console palette's range, section 8).
- **The in-frame order is right**: CT32 upload to 0x3852, CT16 upload to 0x3852, the 1 KiB texture upload to 0x38a8,
  the 63 water resolves, then the second CT32 upload to 0x3852 -- the slot holds the water's CT16 palette during every
  water resolve, and `flushBatch()` precedes every upload on the GL thread.

So the water pass itself is decoded and drawn correctly, and the flat cells are **other draws sharing the palette
slots**. The console dump shows how the game uses them: the water's TEX0 is written **once per pass with CLD=1** and
378 kicks follow; a second texture (`tbp0=03908`, CT32) writes TEX0 with `cbp=03852 cpsm=00 cld=1` sixteen times over
the eight frames -- the same block, the other format. On the GS, **CLD=1 copies the palette from VRAM into the on-chip
CLUT buffer at the TEX0 write**, and every later draw samples that copy; CLD=0 keeps it, CLD=2/3 record CBP0/CBP1, CLD=4/5
reload only when CBP moved off them. Our frontend parsed `cld` and both backends ignored it (the CPU rasteriser's
`// TODO: clut cache`): they decoded through the slot's bytes **at decode time**. Any texture whose slot was re-purposed
between its TEX0 write and its decode -- the 0x3852 CT16/CT32 pair, and the second-pass CT32 write that overlaps the
0x3854 palette by two blocks -- read the other texture's bytes as its palette: flat cells (a run of identical entries),
black holes (entry 0), and the frame-to-frame flicker of a slot rewritten every frame. This is the mechanism of
section 3's 'stale-serve holes' with the palette, not the texels, as the stale part.

**Fix (test-first, `ps2_gs_tests` 'TEX0 CLD=1 loads the CLUT at the write ...' and 'TEX0 CLD=2/4 track CBP0 ...')**:
the frontend snapshots the 2 KiB from block `cbp` at every TEX0/TEX2 write that asks for a load (`GSClutLoad`, an
unchanged palette re-uses its serial), tags the context with the serial (`GSContext::clutId`), and both backends decode
indexed textures from the snapshot (the GL texture-cache key carries the serial; the CLUT page's generation no longer
evicts such an entry). CSM2 palettes keep the live-VRAM path. Measured on the gate after the fix: see STATUS.

## 10. Three bisects: the shards are not the water pass (2026-09-16) [verified]

| run | change | spawn `flat` | reading |
|---|---|---|---|
| `s6_clut` | GS on-chip CLUT modelled (section 9) | 0.504 | unchanged |
| `s6_vu1interp` | `PS2X_VU1_NATIVE=0` (VU1 interpreter) | 0.507 | unchanged: not the vertex data (research/15's residual lists cleared for this) |
| `s6_skipwater` | `PS2X_GS_SKIP_TBP0=0x38a8,0x38a4` (every draw binding the water texture dropped) | 0.488 | **the flat polygons stay** -- they are drawn under the water |

The same polygon outlines appear in every run, so they are geometry with a per-draw defect, not a flicker of the
water. The console's water vertices (dump, 756 kicks) are Gouraud (`GIFtag PRIM 0x07b`: tri-strip, IIP=1, TME, FGE, ABE,
STQ) with per-vertex alpha 0x00..0x33 and s/q, t/q inside 0..2; ours print the same PRIM bits. What remains is the
**bed**: whatever textured draw fills the stream floor, decoded flat. Next: `PS2X_GS_TRACE_CMDS_BOX=x0,y0,x1,y1` (added
with `iip=` and the `[gs-vtx]` per-vertex line) lists every submit whose bounding box touches a shard pixel at the spawn
frame -- its `tbp0/cbp/cpsm`, texel factor (`tme`), and vertex colours name the culprit draw and its texture, and
`PS2X_GS_DUMP_TEX_TBP0` on that block shows what it decodes to.

## 11. The oracle: the console's draw list through our CPU rasteriser has no slabs (2026-09-16) [verified]

The bed pass under the water is a second pass over the water's own 63 triangles: `tbp0=03898` (64x64 T8) through the
palette at 0x384e (its SECOND upload of the frame: alpha 0x7b, bright), vertex colour (13,9,6) with Gouraud alpha
0x64/0x00, blend 0x44, unfogged -- identical on the console (dump packet 1193: [TEX0 03898][189 kicks][TEX0 038a8][189
kicks]) and in our trace (`s6_box`), and our decode of that texture is byte-for-byte the console's
(`PS2X_GS_DUMP_TEX_TBP0=0x3898` on `s6_bed`: mean 196/202/195, alpha 123; the dump's payload through its palette: the same).

So the draw list is right and the decode is right. `ps2_gs_tests` 'console GS dump replays through the CPU rasteriser'
(`PS2X_CONSOLE_REPLAY_DIR`: the dump's initial VRAM -- found in the state blob by its swizzled palettes at file offset
0x12c1df -- and its 5386 packets of frames 0-1, fed to `GS::processGIFPacket`) renders the console's own frame through
our frontend + CPU rasteriser: **a smooth textured stream bed, no slabs** (`assets/31-console-dump-cpu-replay.png`;
`water flat=0.136 dark=0.128` -> PASS against the bar; the PCSX2 reference reads 0.188/0.084, our GL frame 0.503/0.266).

**Therefore the shards are a GL-backend rasterisation defect of this pass** -- frontend, state, CLUT, texture decode and
vertex data are all cleared. Candidates inside `gs_gl_backend.cpp` for a textured Gouraud-alpha tri-strip with STQ
coordinates: the per-fragment s/q,t/q against the bound texture's size, the texture wrap for coordinates outside 0..1
(the bed's s/q spans -0.54..0.89, t/q -0.78..1.12 -- CLAMP=0 means repeat), the alpha source in the blend, and the
texture cache handing a 64x64 entry to a draw expecting another size. Next: replay the same packets through the GL
backend (a headless raylib window in the test or vu1_replay) and diff against the CPU frame per pass.

## 12. The cause: the GL backend dropped the game's full-frame brighten (`Cd*C + Cd`) (2026-09-16) [verified, fixed]

The replay test now renders the dump through BOTH backends (`PS2X_CONSOLE_REPLAY_GL=1`: a hidden raylib window, this
thread as the render thread, the readback inline; the GL shadow VRAM is seeded from the dump's initial VRAM at
`Initialize`), and `PS2X_CONSOLE_REPLAY_STOP=<n>` truncates the stream, so a binary search over 5386 packets finds where
the two frames part (16 s per step, no game launch):

- packet 1194 (the water + bed passes): +0.4 mean difference, the bed pass itself renders alike in both;
- **packet 1389: the whole frame.** The game's post-process: a sprite copies the frame at half size into the depth-buffer
  pages (FRAME 0x118, ZMSK), then a full-screen sprite draws it back with `ALPHA_1 = 0x5d00000069` -- A=Cd, B=0, C=FIX,
  D=Cd, FIX=93: **out = Cd x (1 + 93/128) = 1.73 x Cd**, a brighten of every pixel. The CPU rasteriser applies it (lit
  pixels x1.717 measured); the GL blend table mapped `Cd*C + Cd` to `src=GL_ZERO, dst=GL_ONE` -- identity -- because GL has
  no destination factor above one. So every gameplay frame we drew was 1.73x too dark, and the water's bed pass (a dark
  polygon pass the brighten was supposed to lift) stayed as dark slabs: form 1. (Form 2, the flat hill patch, is
  the same missing lift over a dark terrain pass -- to be confirmed on the gate's captures.)

**Fix** (`gs_gl_backend.cpp`): for `Cd*C + Cd` the SOURCE term carries `Cd*C`: the fragment shader emits C
(`uSrcMode` 1 = the FIX constant, 2 = the fragment's As broadcast) and the blend is `src=GL_DST_COLOR, dst=GL_ONE`;
C = Ad keeps the identity (it would need the destination alpha in the shader). Offline result on the console dump:
GL water `flat 0.616 -> 0.130` (CPU 0.136, PCSX2 0.188), frame mean 20.9 -> 65.0 (CPU 57.9) --
`assets/31-console-dump-gl-replay-before.png` vs `assets/31-console-dump-gl-replay-fixed.png`. The 7.6 mean residual
between GL and CPU after the fix is the next comparison to make with the same harness.

## 13. Why the game never asked for the brighten: the stubbed exposure readback (2026-09-16) [verified, fixed]

The blend fix alone did not move the live gate (`s6_blend`: 3/3, water flat 0.507): the in-game trace shows every
post-process sprite with `alpha=69` -- **FIX = 0** -- where the console dump writes `0x5d00000069` (FIX 93). The factor is
computed by the guest. The console dump has, right before the post-process, two local->host transfers of a 1x4 column
of frame pixels at (317, 430) with a FINISH after each (packets 1387/1388); our traces have none: `FUN_003b24c0`, the
auto-exposure thread's pixel readback (a VIF1 packet, FINISH wait, BUSDIR and a reverse-FIFO DMA of one quadword into
the caller's buffer, whose first R/G/B bytes feed the exposure), is **bound to `socom2_LumReadPixel`, which answered a
constant 0x80 grey pixel** since the reverse-FIFO path was missing (research/20 section 4: 'constant by omission, the
effect is visual only'). A mid-grey scene needs no brighten, so FIX stayed 0 and every gameplay frame drew 1.73x too
dark; the water's dark bed pass, meant to be lifted by that pass, stayed as the slabs.

**Fix**: `runtime/socom2_lum_readback.h` parses the packet's A+D BITBLTBUF/TRXPOS/TRXREG/TRXDIR and reads the pixels
out of GS memory through `GS::ReadVram` (the GL backend downloads GPU-drawn pages on read), writing the quadword
where the DMA would have; test-first in `ps2_gs_tests` ('SOCOM II exposure readback ...'). Measured on the gate: see
STATUS (`s6_lum`).

## 14. Measured on the gate, and what is left (2026-09-16) [verified]

- `s6_lum3` (libgraph packets + readback, one blocking GPU sync per pixel): the readback returns pixels, every frame is
  lit, but the HUD reference no longer matched (re-captured; threshold 30 -> 40) and the guest's pad polling starved.
- `s6_lum5/6` (one blocking sync per 100 ms): still starved -- each wait holds the single EE host thread for the GL
  backlog (~3 frames); eighteen pop-up presses went unanswered and the holds drew static frames.
- `s6_lum7` (**asynchronous** readback: `GS::requestVramReadback` posts the download in stream order, `PeekVram` reads
  the copy the last one left, one request per 100 ms): **mission PASS, and the gate's water bar passes for the first
  time** -- `flat=0.197 dark=0.080` against the console reference's 0.188 / 0.084 (every earlier run: 0.50 / 0.26).

**Still visible, not measured by the bar:** the bed pass's polygons remain as flat LIGHT slabs in the stream
(`logs/parity/gate/s6_lum7/mission/s28_none.png`). Every vertex of that pass carries alpha 0x64 in our trace (585 of 585,
`s6_box`) where the console fades its shore vertices to 0 (the water pass: 46 of 189 vertices at 0; ours never). The
same in both VU1 paths, so it is EE-side vertex data or an op both paths compute alike -- the next lead. The pop-up
detector (`sp_death_probe.screen_state`) also false-positives on the lit look (prompt distance 0.000 with no pop-up).

## 15. The slabs are holes in the under-water terrain: fans our VU1 truncates (2026-09-16) [verified]

With the brighten and the readback in place the slabs stayed, now light. Two more instruments settled where they
come from:

- **`PS2X_GIF_DUMP=<file>:t<seconds>[:<MB>]`** records OUR GIF stream (every packet the frontend processes, in order,
  plus the VRAM at arming after a GPU readback) in the shape the replay test reads. Replaying our own spawn-view stream
  (`s6_gifdump2`, armed 7 s after s28) through the CPU rasteriser AND the GL backend draws the same slabs -- and the
  console's stream draws none on either. The rasterisers are cleared; the difference is in the packets.
- **Per-packet pixel history** (`PS2X_CONSOLE_REPLAY_PIXEL=x,y`) at a slab pixel (196,280): the console paints it black
  with the under-water terrain (texture 0x36b1, one 21 KB PATH1 packet), then blends the bed and water passes over the
  black; ours never touches it before the bed pass, which blends over the fog clear (0x484a4a) -- the light slab.
- **The terrain itself**: for texture 0x36b1 the console kicks 96 fan triangles + 30 list triangles per frame, ours 70 +
  30; the console fan that covers the slab pixel reaches a near vertex at screen (180,367) that our fan does not have
  (ours has the same base edge (187,262)-(456,262) and stops). The vertex data our VU1 receives is fine (the
  `PS2X_VU1_DUMP` replays reproduce the console's per-vertex alphas for the water and bed passes exactly: the earlier
  'no zero alphas' reading was the box filter sampling only the stream's middle), the eye position (data qword 30)
  does not change the count (+-60 units), and neither do PS2X_VU1_FAST / FMAC_CHECK; the interpreter and the native
  program agree. The five-plane Sutherland-Hodgman clipper (0x3618) or the backface cull (0x1638) -- both driven by
  MAC-flag tests on VU arithmetic -- drops near-camera terrain triangles the console keeps. That is the open item.

What the owner sees now (`s6_lum7`/`s6_lum8`): a lit scene matching the console's tone, the water bar passing, and
light flat patches on the stream where our terrain has holes -- the same defect class as the flat hill patch (form 2).

## 16. The holes are draw-list omissions on the EE: the VU1 is cleared (2026-09-16) [verified]

`s6_gifdump3` (gate PASS 1/1, water flat 0.185 dark 0.058) recorded OUR GIF stream and 8000 VU1 program dumps
(`PS2X_VU1_DUMP`, `PS2X_VU1_DUMP_AFTER=330`) from the same spawn-view frames, so the console's draw list, ours, and our
VU1 inputs can be laid side by side. Tools: `tools_py/research/terrain/` (README there).

- **Fan alignment.** Per frame the console kicks 82 terrain fans (texture 0x36b1) and we kick 57; the first 43 match one
  to one (order, polygon size histogram 3/4/5 vertices, first vertex within 2 px). The 25 missing are a block from the
  console's second path-1 packet onward, interleaved with fans we do draw.
- **The backface cull keeps everything.** `vu1_replay --pchist` on the terrain dumps: 0x2060 (front-facing) == 0x1f98
  (primitives) in every family-B program. The clipper is where primitives go (16 -> 10 -> 10 -> 8 -> 8 -> 5 in one dump),
  and Python plane maths on the dump's own data qwords 30-36 reproduces those drops exactly, with margins of 12..190 units
  -- data, not MAC-flag timing. Replayed with the plane normals zeroed, those primitives project behind the camera
  (wrapped FTOI4 coordinates): the console would drop them too.
- **Classification.** Every terrain program of the frame (both the clipped 0x02 family and the unclipped 0x08/0x28 one)
  replayed as-is and with the clip planes AND the cull normals zeroed, then each console fan matched by three shared
  vertices (`classify2.py`): **63 KICKED, 18 ABSENT, 1 SENT-BUT-DROPPED**. The 18 never reach VU1 memory in any
  program. They share vertices with fans we draw and unproject (camera fitted from dump 237, 0.9 px residual) into
  the same world region (x 890..1035, z 853..1080, one flat strip at y = -153) -- the EE leaves out parts of the
  same area, not a distant tile. (The one sent-but-dropped fan is program 242's unclipped list path dropping a
  triangle the console draws: a second, smaller defect.)
- **What builds the list.** `FUN_003b5f20` writes the family-B/C command lists (clipped path when `DAT_004b4eb0 == 0`);
  `FUN_00336cb0` walks a render list of objects; per-object visibility is `FUN_00290c30` -> `FUN_00294ac0` (VU0
  macro-mode: 8 box corners through a 4x4, `VCLIPw`, `CFC2 $vi18`, AND-mask culls, OR-mask marks 'partial') and
  `FUN_00294a30` (`CTC2 $zero,$vi16` / two `VSUB.xyw` / `CFC2 $vi16 & 0xC0`: the sticky zero/sign STATUS bits decide
  clipped vs unclipped VU1 path). The recompiler's `VCLIPw` (magnitude compare against |w|, six bits shifted in) and
  `ps2_vu0_fmac_flags` (MAC + sticky status, cleared by CTC2) read correctly against the VU manual. The 177 per-frame
  1x4 frame-buffer readbacks in the console dump are all the exposure thread's grid samples (`FUN_003b1dd0`), not a
  visibility mechanism; our 100 ms snapshot answers them adequately.
- **Next step** (a runtime hook, one build + one run): wrap `FUN_00290c30` through `registerFunction` to log the eight
  corners, the guest result and a clean IEEE recomputation for the spawn frame; find the box holding world
  (947, -139, 969) (console fan c46's triangle). Culled with a wrong mask -> the CLIP path; never visited -> the
  render-list build upstream (streaming, PVS or LOD selection), which is where the flat hill patch (form 2) would
  also come from.
