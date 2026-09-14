# 26 — The grey shards at the Seeding Chaos stream: GL depth quantisation (draft)

Draft, uncommitted, 2026-09-14. Research only; no code changed. Markings: **[verified]** = read off an
artefact or computed from one in this pass; **[inference]** = follows from verified facts but not measured.

## 0. Condition sentence

**The stream's water mesh is drawn as grey shards with holes because the GL backend maps GS z to
depth as `z / 2^32 * 2 - 1` in float32, which rounds every z below ~2^30 to a multiple of 128.
The game's Z16S depth for this water is z ≈ 1000–9000, so the water, the stream bed and the banks
tie or invert in the ZTST=GEQUAL test. Where water ties with the bank it overdraws it ("pokes
above the terrain"); where the bed rounds above the water, the water is rejected (black holes). The
straight shard edges are iso-depth-error lines, not mesh edges.** [inference, built on the
verified facts below; settled by the §5 run]

## 1. The defect, from the frames

- Every gate stamp whose `mission/s28_none.png` is gameplay shows the same shards. That is 27
  frames from `famb` (Sprint 2) through `s5_head_1x_b`, including `native_default`,
  `hostdraw_on`/`hostdraw_fix` (host-draw path), `s3d_2x_host` (GS_SCALE=2), `fam4`, `famc` and
  every s3/s4/s5 stamp. It never looks right. [verified: contact sheet over `logs/parity/gate/*`
  and `D:/socom_archive/gate/*`; the other stamps' s28 is the car cinematic, a dialog or black]
- Shard colour is flat (31,29,27)–(44,43,41), with 7×7 std ≤ 1.2. The rest of the stream bed
  inside the water footprint is near-black (5–9). [verified, pixel samples of `s5_head_1x_b` s28]
- s28 is the **spawn view**, before any hold (t = 249.4 s; holds start at s30). [verified,
  `mission.drive.log`]

## 2. Console reference: it exists

- PCSX2 savestate **slot 8 = spawn** (`tools/pcsx2/sstates/SCUS-97275 (0F6FC6CF).08.p2s`). Its
  embedded Screenshot.png is the same camera as our s28. [verified: trees, rock and HUD line up
  after resizing 480→448]
- On the console the water is one continuous dark-brown translucent surface filling the stream bed
  and bounded by the banks: (42,38,33), (47,45,38), (54,48,43). There are no shards and no black
  holes. [verified]
- No console **GS dump** of this spot exists. The four `tools/pcsx2/snaps/*.gs` are SELECT RANK
  and the title. [verified] To get one: `python -m tools_py.parity.gsdump_capture --slot 8` (dump
  lands in `tools/pcsx2/snaps/*.gs`), then `python tools_py/gsdump_timeline.py <dump> --all`. Look
  for the TEX0 bind `tbp0 0x38a8` (page 0x1c5) and the `TEST 0x5000c` / `ALPHA 0x44` A+D writes
  (§3.2).

## 3. The draw path

### 3.1 List builder [verified, decomp]

`FUN_003b5b90` (`game/analysis/socom2_game.elf.decomp.c`) appends the per-object VU1 command list.
When `DAT_004b4dc0 != 0` it adds an env-map block, using `0x34` if `DAT_004b4eb0 != 0` (the no-clip
branch, after `0x30`) and `0x36` otherwise (after `0x32`). It brackets the block with `0x72` (draw
gate off) and `0x74` (gate on). The material table `FUN_005187e0` names surface class 2 "water"
(collision/sound material). Its link to `DAT_004b4dc0` is [inference].

### 3.2 The water object is VU1 dump `logs/vu1dump3/vu1_prog_27.bin` [verified]

- The list is `68 06 64 08 10 28 72 34 74 42`: family C over A. The first pass is `0x28` (TOP+1
  tag: PRIM 0x7b = TRIANGLE, IIP, TEX, FOG, ABE). The second pass is `0x34`, sphere-map ST plus
  rim alpha (research/15 §6), which re-enters `0x28`'s body.
- The `0x34` block's eye (938.75, −125.03, 832.17) is the spawn camera (console player
  (939.4, −126.3, 832.2), STATUS 2026-09-08 17:30).
- The `0x34` block's A+D writes:
  - `ALPHA_1 0x44`: (Cs−Cd)·As+Cd.
  - `TEX1_1 0x60`: bilinear.
  - `TEX0_1 0x20170a45553078a8`: TBP0 0x38a8, PSMT8 32×32, TCC 1, MODULATE, CBP 0x3852, CT16 CLUT.
  - `TEST_1 0x5000c`: **ZTE 1, ZTST GEQUAL**, ATE 0.
  - `CLAMP_1 0`: REPEAT.
- Base colour (33,33,33,65).
- Kicked output (`vu1_prog_27.bin.pk`, 126 triangles):
  - Pass 1 RGBA is (13,9,6,100): the console's dark brown.
  - Pass 2 RGB is (33,33,33) with α 0–51: a faint grey reflection.
  - **q < 0 on 0 vertices, ADC 0 on all.**
  - **z 1032–8693** (36 distinct values; the triangles nearest the spawn are 1105–1328).
- Rasterised at XYOFFSET (1728,1824), the pass-1 triangles **cover exactly the console's water
  footprint** at this camera. Our shards lie inside that outline, with edges that are not mesh
  edges. [verified: `scratchpad/water/overlay.png` method; reproducible with
  `tools_py/gif_packets.parse_packet`]
- The live GS state agrees. An earlier GS trace logs `zbp=118 zpsm=3a zmsk=0 test=5000c abe=1` on
  1748 of 1755 submits (`logs/run_20260905_*.log`). The guest's DBuff asks for zpsm **0x3a (Z16S)**
  with ztest GEQUAL (research/20 §4.1). [verified]
- Native coverage: the list runs natively (`0x34` landed Sprint 3 Task 8) and is bit-exact to the
  interpreter on this very dump, register file included (research/15 §0.9). [verified in research/15]

### 3.3 The GL depth path [verified, code]

In `gs_gl_backend.cpp`:
- `appendVertex`: `out.z = min(z, 2^32−1) / 2^32` (float).
- Vertex shader: `gl_Position.z = aPos.z * 2.0 − 1.0`.
- Depth attachment: `GL_DEPTH_COMPONENT32F`.
- `setupDrawState`: GEQUAL → `GL_GEQUAL`, with `glDepthMask(!zmsk)`.

The CPU backend compares **integer** z (`z >= storedZ`, `gs_cpu_backend.cpp`). The shader line has
been unchanged since the GL backend landed (`409d0c3`).

The float32 round trip (numpy, same operations), in z units, is [verified]:

| GS z | GL depth |
|---|---|
| 64 | 0 |
| 100–191 | 128 |
| 192 | 256 |
| 1105, 1111, 1190, 1202 | **1152** |
| 1280, 1287, 1296, 1328 | **1280** |
| 4000 | 3968 |

The window depth near ndc −1 has a float32 spacing of 2^−24, i.e. **128 z units for every z below
~2^30**. A Z16S scene therefore has **~512 depth levels in total**. The 36 distinct water z values
collapse to 20 levels, and the four nearest triangles' twelve vertices collapse to two.

## 4. Candidates, ranked

1. **GL depth quantisation (condition sentence).**
   - For: it explains shape (straight iso-error edges inside the correct footprint), both errors
     (overdraw of the banks and holes in the bed), and persistence across every stamp and knob
     (native, host-draw and GS_SCALE all share `appendVertex` and the shader).
   - Against: none found. Why it does not show elsewhere is [inference]: most layered surfaces are
     > 128 z apart or rely on draw order, where GEQUAL ties pass.
   - *Check:* a GL run with depth normalised to the Z format (e.g. `z / 65536` for Z16/Z16S,
     `z / 2^24` for Z24, before `*2−1`, or `glClipControl`/`glDepthRange` equivalent) behind an
     uncommitted diagnostic knob. Shards gone and brown water bounded by the banks → settled.
2. **Env-map texture/CLUT for the `0x34` pass** (TBP0 0x38a8 PSMT8, CBP 0x3852 CT16).
   - This affects colour only. It can make the reflection flat grey, but it cannot cut shapes or
     make holes.
   - *Check:* `PS2X_GS_TRACE_CMDS=t249` on the mission, find the `tbp0=038a8` submits, and compare
     the decoded texture and CLUT against the slot-8 console GS dump (§2).
3. **Native VU1 `0x34` / family C over A wrong** (the brief's (a)).
   - Against: the dump's vertices are sane (q > 0, ADC 0, footprint = console), and native is
     bit-exact to the interpreter on this dump.
   - *Check:* `PS2X_VU1_NATIVE=0` mission-only gate; s28 unchanged → excluded.

Excluded or downgraded:
- **(d) clip/cull.** q<0 = 0 and ADC 0 at this camera [verified on the 2026-09-09 dump; that the
  current exe emits the same is inference].
- **(c) blend.** ALPHA 0x44 maps to SRC1-alpha / ONE_MINUS_SRC1 correctly; no ATE, FBA or DATE on
  this draw [verified in code].
- **(e) as briefed.** TEST_1 *is* sent here, ZTE 1 GEQUAL, so the DBuff "never sent" note does not
  apply to this draw [verified]. The fault is the precision of the test, not its mode.

## 5. Proposed runs (controller schedules; not launched)

Reach the spot with the gate's mission stage alone: `python -m tools_py.parity.gate --only mission`
(`scripts/parity/gameplay_probe.txt`; s28 lands at ~249 s, before any hold). Env vars are inherited
by the game process [inference; confirm in `gate.py`].

- **Run 1 (settles it).** Two mission-only gates on one build carrying an uncommitted diagnostic
  knob, e.g. `PS2X_GS_DEPTH_NORM=1`, that rescales `out.z` by the ZBUF psm's range. Compare s28/s29
  knob-off vs knob-on against slot-8's screenshot. Prediction: knob-on, no shards, no black holes,
  continuous brownish translucent water bounded by the banks. The title/transition captures and
  `--vram-diff` should be unchanged or better.
- **Run 2 (only if Run 1 leaves the colour grey).** Mission-only gate with `PS2X_GS_TRACE_CMDS=t249`,
  plus `python -m tools_py.parity.gsdump_capture --slot 8` on PCSX2. Diff the `tbp0 0x38a8` binds,
  TEX0/CLUT and alpha of the `0x34` pass.
- **Zero-code fallback for Run 1.** `PS2X_GS_BACKEND=cpu` (exact integer z) at s28. It is likely too
  slow to reach 249 s, and the CPU backend's window capture is untested for this, so treat it as
  a fallback only.

## 6. Open

- s30/s32 "dark flat plane" once in the water: unexplained. It is consistent with the brown base
  pass at α 100 over a dark bed plus a faint reflection, but no console frame exists inside the
  water.
- Our whole scene is darker than the console's at the same camera (terrain (5–9) vs (33,30,27)
  in places). That is a separate issue [inference]. The display env and PMODE differ (research/20
  §4.3).
- The 640×448 vs 640×480 frame height is the known display-env difference, not this defect.
