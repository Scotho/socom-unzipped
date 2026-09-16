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
