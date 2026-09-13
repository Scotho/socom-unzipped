# 23 — Frostfire ground probe: pipeline, data, stubs, candidates, launch-2 reading guide

**Status: zero-run research wave (Sprint 5, 2026-09-13), corrected after an independent review
(§10; the review's scripts are `scratchpad/rv23/grid.py`, `walk.py` and `overlap.py`).** No build and no launch. Every claim is marked
**[verified]** or **[inference]**:
- [verified] means read from the decomp, the ELF bytes, the recompiled output, the runtime source, an
  RDRAM image or a log during this wave.
- [inference] means reasoned from those sources, not observed.

Functions are cited by name. File line numbers are never cited.

Sources:
- `game/analysis/socom2_game.elf.decomp.c` and `game/disc/socom2_game.elf` (bytes);
- `recomp/output/*.cpp`, `recomp/socom2.toml` and `third_party/ps2recomp/ps2xRuntime`;
- the 18 images in `logs/parity/*.rdram`;
- frost1 = `logs/run_[AB]_20260913_004754.log`, launch 1 = `logs/run_[AB]_20260913_073548.log`,
  kill2 = `logs/run_[AB]_20260912_231341.log`;
- `tools/reference/reCOM`.

Background: `KNOWN.md` §2 top row, research/21 §6.4–6.5, research/17, research/20, and `STATUS.md`
2026-09-08 13:30 and 16:15.

Throughout, **A** = `*0x408c58`, the local player actor, and **W** = `*0x45c380`, the world.

---

## 0. Bottom line

1. **The per-frame probe is a vertical line from y = +50000 to −50000.** It asks the collision grid
   for every polygon under the actor's (x, z). The line length cannot be "too short". Height only
   matters when a hit is *selected*. [verified]
2. **Our own build has produced exactly Frostfire's signature before, in single player.**
   `spawn_ours2.rdram` (2026-09-08) shows four things:
   - records 0–10 (the live ones) all have candidate count 0; records 11–36 hold stale non-zero
     counts from earlier frames;
   - A+0x1061 = 0x04 and A+0x420 is stale;
   - the collision grid holds **900 cell nodes and zero registered objects**, and its atom free
     list is **0**, with 7292 atoms orphaned (§2.1);
   - the terrain polygon under the player is still in memory: an offline walk finds it when the
     grid is bypassed.

   Every other in-mission image, ours and the console's, holds 3566–4444 nodes and 3748–4626 free
   atoms. That was the "grid collapse" of `STATUS` 2026-09-08 13:30, which the SQRT.S fix removed.
   The **class** is "the terrain is not registered in the grid cell under the player". [verified]
3. **A latent runtime bug, not a Frostfire candidate:** the `memcpy` stub (and recompiled code)
   aliases VU0 micro memory `0x11000000` onto RDRAM `0x01000000` (§3.4). The only guest code that
   would trigger it, the Nellymoser voice codec's VU0 mode, **cannot run in this game**: its mode word
   is 0 and its only setter is unreferenced (§3.4). [verified by review]
4. **Launch 2 can separate the candidates** if it adds grid peeks, a larger candidate dump and one
   RDRAM image per instance (§6). A data-only walker, with the review's three extra rules, reproduces
   records 0–5 exactly in both `spawn_ours` and `spawn_pcsx2` (§7, tier 0). Run over a Frostfire image, it answers "is
   there a polygon under the spawn in the grid?" without emulating a single instruction.

---

## 1. The probe pipeline

### 1.1 Order of calls in one frame [verified]

The actor vtable is `0x6691a0` (ELF bytes): `+0x20` = `0x005506a0`, `+0x24` = `0x00550570`.

1. **`FUN_005506a0`** (actor `vtbl[0x20]`):
   - runs only when `A+0xf40 != 0`;
   - sets `DAT_0066aab8 = A+0x20` (the actor's y);
   - calls `FUN_005b0840`.
2. **`FUN_005b0840` (ProbeQueue):**
   - sets `A+0x2cc = -999`, then returns early if `A+0x1061 & 0x08`;
   - requires `(A+0xe1 & 1)`, or the mover's `vtbl[0x2c]()`. For the local player's mover
     (`0x6694b0`), `vtbl[0x2c]` = `FUN_005431f0` = `jr ra; li v0,1`, so it is always true;
   - computes the origin (§1.2);
   - takes record `DAT_0044d598` from the array `DAT_0044d588`, growing it by one `0x4c`-byte
     record through `FUN_00180e10(0x4c)` and `FUN_002dc6e0(rec, 0x20)` when full;
   - writes `+4..+0xc` = origin and `+0x44` = the layer mask from `FUN_002dc660(rec, FUN_002dc1b0(A+0x400))`;
   - sets bit 1 of `+2` from `A+0x21c` bit 1, sets `+0x3c` = `FUN_0029ed20(A)` (the self object,
     excluded), stores the index in `A+0x2cc`, and increments `DAT_0044d598`.
3. **`FUN_00550570`** (actor `vtbl[0x24]`): if `DAT_0044d598 > 0`, calls `FUN_005b0800`. It always
   calls `FUN_005b0420`.
4. **`FUN_005b0800` (ProbeBatch):**
   - calls `FUN_0031de90(a0 = W, a1 = DAT_0044d588, a2 = DAT_0044d598)` and zeroes `DAT_0044d598`
     (a2 read from the instruction bytes);
   - `FUN_0031de90` **ignores a0**: it loads W from `0x45c380` itself, sets `a0 = W+0x684` and
     **tail-jumps** (`j`) to `FUN_002d3cf0`.
5. **`FUN_002d3cf0` (grid batch walk, §2.1):** for each cell that holds a probe, it walks the
   cell's atom list and calls `FUN_002d3030(grid, model, array, count)` per model. It returns 1, or 0
   when `DAT_0044f078 != 0` or the count is 0.
6. **`FUN_002d3030` (per-model test):**
   - gates the model on `+0x5c` bit 0, `+0x5d` bit 4, the cell bit for this probe, and the layer
     mask test `FUN_002dc620(rec, 1 << model+0x5c[13..17])`; a model equal to the record's `+0x3c`
     node (the self object) is marked done and skipped;
   - pushes the model matrix when it is not the identity (`FUN_003084f0` / `FUN_00307fa0`) and
     inverts the top of the stack with `FUN_00308160`;
   - for a type-1 record, builds the two line ends (x, ±50000, z), transforms them to model space
     with `FUN_003085c0` into `+0x1c` / `+0x28`, and rejects by bounding box with `FUN_003124f0`;
   - sets `DAT_003df270` = `0x30` if model `+0x80` bit 1, else `0x20`, and loads VU0 with `FUN_002dd210`:
     vf1 = (`+0x28`, w = 1.0), vf2 = (`+0x1c`, w = `DAT_003df270`);
   - walks surfaces `+0x7c[0..+0x78)`: when a surface has vertices it calls `FUN_002dd130`
     (`vcallms 0x70` on the first three vertices); with `DAT_0044d758 == 0` it skips surfaces whose
     `+8` bit 18 is set; for type 1 it requires `surf+8` bit 0, then calls `vtbl[0x14](surf, rec)`;
   - on a hit it runs `vcallms 0x80` to move the hit back to world space, stores `+0x1c` = model and
     `+0xc` = surface, and increments `+0x34`. **The surface loop stops at the first hit per
     model** [verified by review];
   - recurses into `+0x70[0..+0x6c)`.
7. **Surface `vtbl[0x14]`:**
   - `zdb::CDIPoly` (vtable `0x406690`) = `FUN_002dd150`. It runs `vcallms 0x10` on the edge
     (last vertex, first vertex), then `vcallms 0x20` on each further edge, writing vf29 to the hit
     slot and vf3 to `slot+0x10`. **`w == 0.0` after any edge means a miss**, tested with `c.eq.s`;
     passing every edge returns 1.
   - `zdb::CDIBBox` (vtable `0x406670`) = `FUN_002dcda0`.
   - The class names are the strings after the vtables' type words (`0x3f3650` / `0x3f3680`).
8. **`FUN_005b0420` (ProbeTake):**
   - runs only when `!(A+0x1061 & 0x08)` and `A+0x2cc >= 0`;
   - calls `v0 = FUN_005b5d40(f12 = 1.0, a0 = A, a1 = rec, a2 = rec+4)`, as the call bytes at
     `0x5b0460–0x5b0474` show;
   - **on a hit:** `FUN_0059ad30`, then copies to `A+0x400..+0x41c`, sets `A+0x420 = DAT_004365c0`
     and calls `vtbl[0x10]`;
   - **on a miss with `DAT_003df1c8 != 0`:** calls `FUN_005582c0(1/30, …)` when the mover's
     `vtbl[0x38]()` returns non-zero; clears `0x1061` bit 0x02 and **sets bit 0x04**; zeroes
     `+0x1340` and `+0x111c`; **sets the position back to `A+0x400..+0x408`** (`FUN_003157d0`) and
     calls `vtbl[0x10]`;
   - `A+0x2cc = -1` afterwards.
9. **`FUN_005b5d40` (ProbeEval, selection only):**
   - loops `rec+0x34` candidates of 0x20 bytes each, starting at `*(rec+0x48)`;
   - the material is `m = FUN_002dc1d0(cand)`: surface `+8` bits 10..17, where 0 means
     `DAT_0044f310` and an out-of-range index means 0;
   - a candidate with **`0x44f358[m]+0x3c` bit 0 (VOLUMETRIC)** goes to `FUN_005b7350` +
     `FUN_005b5050`, and one with **bit 1 (LIQUID)** goes to `FUN_005b52b0`. Neither becomes ground;
   - a candidate whose owner is an actor (`FUN_0059acd0(cand+0x1c)`) is skipped for the local
     player, because the mover's `vtbl[0x2c]` returns 1;
   - it keeps the **highest candidate with y ≤ origin_y + 1.0**, or failing that the **lowest**
     candidate;
   - it **rejects the pick if `*(A+0x28)+0x34 + 20.0 < pick.y`**, the actor matrix translation y;
   - it returns the pick, or 0.

The flag bits come from `FUN_002dde40`, the SOILS parser: VOLUMETRIC → bit 0, LIQUID → 1,
UNDERWATER → 2, PICKUP → 4. [verified]

The miss branch pins the actor to its last ground point every frame. That explains why A and B hold
**exactly** their spawn x/y/z on all ~1150 actor rows of frost1 and of launch 1. [inference, strong]

### 1.2 Probe origin [verified]

The origin starts from `(A+0xf54, max(A+0xf58, DAT_0066aab8 = A+0x20), A+0xf5c)`. It adds the
bone translation `*(A->vtbl[0x88]() + 0xc) + 0x30`, rotated by the actor matrix `*(A+0x28)`, using
COP2 `vmula/vmadd`. In actor state 3 only the y component is added (`FUN_00309240`).

In the images, origin y − actor y is:

| image | origin y − actor y |
|---|---|
| `spawn_ours`, `spawn_pcsx2` | +4.7 / +5.5 |
| `postload_ours` / `_pcsx2` | +11.2 (the skeleton root node, cf. research/17) |
| `spawn_ours2` | +0.0 (the root had decayed) |

Only x and z reach the query; y only feeds the selection window.

### 1.3 Record and candidate layout [verified in 6 images]

The record is `zdb::DiIntersect` in reCOM terms (§8).

| off | field |
|---|---|
| +0x00 | `u16` type (1 = vertical probe; 2 = vertical column `FUN_0031dea0`/`FUN_002d49c0`; 4 = sphere) |
| +0x02 | flags (bit 0 set at construction; bit 1 from `A+0x21c`) |
| +0x04..+0x0c | origin x, y, z |
| +0x10..+0x18 | second point (types 2/4) |
| +0x1c..+0x24 | model-space top (written per model) |
| +0x28..+0x30 | model-space bottom |
| +0x34 | candidate count |
| +0x38 | capacity (32) |
| +0x3c | excluded object (self) |
| +0x40 | "tree done" model |
| +0x44 | layer mask: last-hit surface word 0, OR 1; `0xffffffff` when `A+0x40c == 0` |
| +0x48 | **pointer** to the candidate buffer (32 × 0x20) |

Record size is 0x4c = 19 words.

A candidate (0x20 bytes) is laid out as:
- `+0..+8` hit point;
- `+0xc` surface (`CDIPoly*`);
- `+0x10..+0x18` normal;
- `+0x1c` owning model.

Surface: word 0 = region/layer bits (`0x400` for the M51 terrain), `+8` bitfield
(`ditype:2 | ptcount:8 | material:8 | …`, reCOM `DI_PARAMS`), `+0xc` vtable, `+0x10` vertex array
(16-byte xyzw).

**So the planned dumps are right:**
- `ProbeEval:a1:19` is the whole record;
- `ProbeEval:a1+0x48*:16` is the first **two** candidates; `:32` covers four and `:64` eight.

The dump prints after return, from the entry value of a1, and `FUN_005b5d40` does not write the
record. [verified from the tracer source and the decomp]

---

## 2. The data the probe walks

### 2.1 The collision grid, `W+0x684` (`zdb::CGrid`) [verified]

| off (grid) | = W+ | field | M51 value (ours / console) |
|---|---|---|---|
| +0x00 | 0x684 | atom pool size | `0x2000` |
| +0x08 | 0x68c | cell dimension | 180.0 |
| +0x0c / +0x10 | 0x690 / 0x694 | cells wide / high | 36 / 25 |
| +0x30 | 0x6b4 | cell array (one atom-list head per cell) | |
| +0x34 | 0x6b8 | atom pool | |
| +0x38 | 0x6bc | **free-atom list head** (0 = pool exhausted) | non-zero; **0 in `spawn_ours2`** |
| +0x3c | 0x6c0 | inverse cell dimension | 1/180 |
| +0x48 | 0x6cc | traversal tick (+1 per query, `FUN_002d6800`) | 2137…37049 |
| +0xf4 / +0xfc | 0x778 / 0x780 | origin x / z | 0 / 0 |

- **Atoms** are `{object, next, prev}`. A cell's list starts with its `zdb::CCell` (`+0x58 == 10`,
  children at `+0xec`/`+0xf0`, each child's model at `+0x64`). After it come models (`+0x58 == 1`)
  and actors (`+0x58 == 2`).
- **Inserts** go through `FUN_002d7580`, which spends one atom per cell covered by the object's
  bounds. Callers: `FUN_0031f240` (thunk `0x2d61a0`) and `FUN_002d6000` (from `FUN_00315860` /
  `FUN_0031d6f0`). Removal is `FUN_002d60e0`. The pool is allocated once. [verified by review]
- **Exhaustion and chain cut are one event.** In `FUN_002d7580`, when the popped free atom's `next`
  is 0, the insert links a NULL atom and zeroes the `CCell`'s `next`. Everything after the cell node
  drops out of that list. **The healthy invariant is nodes + free = 8192.** [verified by review]
- **The M51 terrain hangs under a type-1 atom model** (`0x12d5b40`, children at `+0x70`), not under
  a `CCell` child, so a chain cut removes it from the query. This supports candidate (1).
  [verified by review]
- **What can still drain the pool after the SQRT.S fix** [inference]:
  - a node whose bounds become ±FLT_MAX spends 900 atoms per update on M51, so about five such nodes
    exhaust the ~4600 spare;
  - online-only sources: remote avatar poses, slot actors on uninitialised heap, a saturating VU0 path;
  - `STATUS` 2026-09-08 13:30 records that the FPU trap fired zero times;
  - NaN bounds are safe: `cvt_w` gives `0x7fffffff`, which clamps to one cell.
- **A type-1 probe marks only the cell that contains its (x, z)** (`FUN_002d6c40`/`FUN_002d6800`
  with one point). Terrain that is not linked into *that* cell is invisible to it.
- The cell-bit scratch buffer `DAT_0044d770` runs up to the next referenced global,
  `DAT_0044f070`: 0x1900 bytes, or 1600 words. That matches reCOM's `MAX_NUM_CELL_ATOMS 1600`.
  [inference: the size is taken from the symbol gap]
- The per-probe cell bit is `1 << (index & 0x1f)`.

**Grid census over the images** (walk every cell list):

| image | nodes (CCell/model/actor) | free | free head | nodes + free |
|---|---|---|---|---|
| `postload_ours`, `rest_ours`, `rest_ours_gq` | 3566 | 4626 | non-zero | 8192 |
| `spawn_ours` | 4444 (900/2075/1469) | 3748 | non-zero | 8192 |
| **`spawn_ours2`** | **900 (900/0/0)** | **0** | **0** | 900; 7292 atoms orphaned (6313 still chained) |
| `spawn_pcsx2` | 3577 | 4615 | non-zero | 8192 |
| title/menu images | 1–2 (1×1 grid, dimension 640) | | | |

The `spawn_ours2` orphan counts come from the review (`rv23/grid.py`).

`spawn_ours`'s surplus of models is a separate divergence. It was not investigated.

### 2.2 Other globals the probe reads [verified]

| global | role | value in every mission image |
|---|---|---|
| `DAT_0044d588` / `…590` / `…598` | probe-record array / records allocated / queued this frame | array, 37, 0 |
| `DAT_0044f354` / `DAT_0044f358` | SOILS material count / table (`0x40`-byte objects; `+0x38` foot-step offset, `+0x3c` flags) | 46 |
| `DAT_0044f310` | default material index | 8 |
| `DAT_003df1c8` | miss policy: 0 = re-derive ground from the material table; ≠0 = pin to the last hit and set `0x1061` bit 4. ELF value 1; one reader (`0x5b05f4`); no static writer found | 1 |
| `DAT_0044f078` | batch kill switch: `FUN_002d3cf0` returns 0 when set. One reader (`0x2d3d3c`); no static writer (instruction scan including `$at`-relative stores) | 0 |
| `DAT_0044d758` | surface filter mode in `FUN_002d3030` | 0 |
| `DAT_003df270` | VU0 line w (0x20 / 0x30), set per model | 0x20 |
| `DAT_003df330` / `PTR_DAT_003df338` | matrix-stack depth / top (base `0x450080`, 0x40 per level) | depth 0–10, pointer consistent |
| `DAT_0044d738` | current model | |
| `DAT_004365c0` | the clock that is stamped into A+0x420 | |

### 2.3 How Frostfire's collision reaches memory [verified / inference]

- `MP2.ZDB` is FROSTFIRE. Its TOC holds `RUN\MP\MP2\*_GEO.ZED`, `*_MDL.ZED` (`MP2_MDL`,
  `WORL_MDL`, `CLIB_MDL`, `FLIB_MDL`), `CLUTTER.ZAR`, `READERM.ZAR` and `AIMAPS.MPS`. [verified, TOC read]
- The grid is created from the reader key `grid_params` (`FUN_002d5420`, default dimension 640
  and 8×8). Cells are named `cell%06d` (`FUN_002d5c80`). Clutter from `clutter.zar` is inserted by
  `FUN_002d5060` → `FUN_002d55c0`. [verified strings and calls]
- All of this is recompiled game code. The disc is read by LBN through `sceCdRead`/`sceCdStRead`
  (research/05; research/20 rows 114/119 "faithful"). [inference for the exact call chain]
- The map renders in the frost1 screenshots. Collision polygons live in the same model objects
  (`+0x78`/`+0x7c`), so "Frostfire's collision was never loaded" is less likely than "it was
  loaded and is not linked into the grid". [inference]

---

## 3. Math, recompiled coverage, and every stub on the path

### 3.1 Recompiled coverage [verified]

Every function on the per-frame path has a generated body:
- `FUN_005b0840`, `005b0800`, `005b0420`, `005b5d40`;
- `0031de90`, `002d3cf0`, `002d3030`, `002d2890`, `002d6c40`, `002d6800`, `002d6430`, `002d66b0`,
  `002d78a0`, `002d93a0`;
- `002dd130`, `002dd210`, `002dd150`, `002dcda0`, `003124f0`, `003085c0`, `00308160`;
- `001bfc30`, `001bff28`, `00309180/200/240`, `00307640`.

No body contains an interpreter fallback or an unhandled-instruction marker. Indirect calls are only
the vtable `jalr`s, which go through `dispatchGuestBranch`. `0x2dd150` and `0x2dcda0` are
`extra_functions` entries registered in the dense table. The M51 images hit through exactly this code.

### 3.2 Arithmetic on the path [verified]

- **COP1:** `c.eq.s`, `c.lt.s` and `c.le.s` through `FPU_C_*_S` (both operands pass
  `ps2_fpu_sat`, so denormals compare as ±0), and `cvt.w.s` through `ps2_fpu_cvt_w` (grid
  indices).
- **COP2 macro:**
  - `lqc2`/`sqc2`/`qmtc2.i` and `vmula/vmadd(bc)` in `FUN_005b0840`, `FUN_003085c0` and
    `FUN_001bfc30`;
  - `vmul/vaddbc/vdiv/vwaitq/vmulq/vsub` in `FUN_00308160` (the scaled-orthogonal inverse through
    the Q register).
- **VU0 microprograms:** `vcallms 0x10, 0x20, 0x70, 0x80` through `PS2Runtime::executeVU0Microprogram`:
  - the `VU1Interpreter` runs in VU0 mode;
  - the interpreter is `reset()` per call and state is copied to and from `ctx`;
  - rounding is toward zero (a scope object restored explicitly);
  - the fast path is the default (`PS2X_VU0_FAST`);
  - the step budget is 4096.
- `sqrt` appears only in `FUN_002d6800` for multi-point probes (not type 1) and in `FUN_00307270`
  (quaternion normalise, only for nodes with `+0x4c` bit 1).
- **No `__ieee754_*`, `sin`/`cos`, `fabs`, `floor` or soft-double stub is on the per-frame path.**

**Open [verified negative]:** where the collision microprograms at slots 2/4/14/16 come from. The
only static VU0 upload in the ELF is `FUN_00252150`: `memcpy(0x11000000, 0x3d5980, 0xdd0)`. That
image is Nellymoser's FFT (`SaseEncVad/…/VoicLD.c`, `shared/fftIf.c`). Its slot 2 reads
`LQ vf1, 15(vi0)` and it has only two programs, ending at `0x768` and `0xcd8`, so it is not the edge
test. An RDRAM image does not contain VU0 memory.

[inference] Recompiled accesses to `0x11000000–0x11003fff` alias to RDRAM just as the stub does
(§3.4), so no guest memory copy can place the collision microcode. **It must arrive through a VIF0
MPG packet** (`processVIF0Data` in the runtime). The uploader itself is still unlocated.

### 3.3 Stubs and library routines reachable from the path

The toml bindings were intersected with the static call closure of each stage (`jal` targets
followed through the generated code). [verified]

| stage (depth) | bound stubs reached | research/20 row | note |
|---|---|---|---|
| `FUN_002d3cf0` walk (d≤2) | **none** | | pure recompiled code + COP2 + VU0 |
| `FUN_002d3cf0` (d3) | `memcpy`, `rand`, `strstr` | 29 / 16 / 18: faithful | only through `sub_00262550`, whose generated body is wider than Ghidra's `FUN_00262550` (the model-parent chain); not per-frame [inference] |
| `FUN_005b5d40` (d≤3) | `memset`, `strstr` | 30 / 18: faithful | via the camera-target footstep branch (`FUN_00290bd0`, `FUN_005a2f90`) |
| `FUN_005b5d40` | `__dynamic_cast` (untracked, recompiled) | – | `FUN_0059acd0` |
| `FUN_005b0840` growth | `FUN_00180e10`, `FUN_0034eb50`, `FUN_0034ec30` (game allocators, recompiled) → `malloc` family | 19: faithful, block **content** is research/20's blind spot | first frames only |
| loading SOILS / reader keys [inference: the reader's key match was not traced to this stub] | `strcasecmp` | 9: **wrong shape** (prefix returns the length difference) | 265 sites, all zero-tests, so equality is unaffected |

**No wrong-shape math stub is on this path.** `__ieee754_rem_pio2f` (research/20 §4.5) is not
reachable from any probe stage.

### 3.4 A latent runtime bug: VU0 micro memory and VU1 data alias to RDRAM [verified code; cannot fire in this game]

**The alias.**
- `ps2_stubs::memcpy` resolves its destination with `getMemPtr`. `ps2ResolveGuestPointer` keeps
  `phys = 0x11000000`; since that is ≥ `PS2_RAM_SIZE`, it applies `phys &= PS2_RAM_MASK` and gets
  **`0x01000000`**. `guestContiguousBytes` allows the copy.
- **Recompiled code is correct only for VU0 data, `[0x11004000, 0x1100c000)`.**
  `Ps2IsPhysicalSpecialAddress` leaves out VU0 micro (`0x11000000–0x11003fff`) and VU1 data
  (`0x1100c000–0x1100ffff`). Recompiled accesses there also land on `rdram[addr & 0x1ffffff]`.
  [verified by review]

**The only guest sites, and why they are dead** [verified by review]:
- `FUN_00252150` calls `memcpy(0x11000000, 0x3d5980, 0xdd0)`, the Nellymoser FFT microcode. Its
  follow-up loop writes VU0 data at `0x11004800`, which is inside the correct range.
- `FUN_00252098` (the VU0 FFT) calls `memcpy` at `0x11004000` and `0x11004400`.
- Both sit behind the codec's mode word at `gp−0x7d50`. gp is `0x1dd2f0` from `_start`, so the word
  is at **`0x1d55a0`**. It is **0 in the ELF and in all 18 images**.
- Its only writer is `FUN_00251a98`. That function's only caller, `FUN_0024fac0`, has **no
  references** in `socom2_game.elf`, `SCUSNGUI.ELF`, `game/overlays/*` or any image.
- With mode 0 the upload never runs and the FFT runs in software (`FUN_00251c80`).

So the alias cannot corrupt the Frostfire heap through this codec. It stays a runtime bug worth
fixing. None of the 18 images holds the blob at `0x01000000`, which fits. [verified]

---

## 4. Cheap zero-run discriminators (done)

- **Positions** [verified]:
  - A = (795.73, 101.0, 613.571) on 1154/1154 actor rows and B = (535.73, 142.933, 1253.57) on
    1153/1153, identical in **frost1 and launch 1**. No coordinate ever changes; the pin in §1.1
    is the likely reason.
  - In kill2 both actors move within the first rows: A y 159.53 → 158.50 settles; B y 65.05 → 62.68.
    Spawns sit about 1–2.4 units above ground there.
  - Frostfire's A spawn y is the round 101.0. Both Frostfire x values end in .73 and both z values
    in .57, which suggests one generator plus offsets. [inference]
- **Layer mask** [verified]:
  - launch 1 `A+0x400:12` reads position, `+0x40c = 0`, normal (0, 1, 0) and `+0x41c = 0` on every
    row. B is the same, with `+0x420 = 0x102`.
  - So `FUN_002dc1b0(A+0x400)` = −1 and the record mask is `0xffffffff`. **The stale-layer-mask
    variant of (d) is excluded for launch 1.**
- **Saturation scan** [verified]: no `7f7fffff` / `ff7fffff` / `5f800000` / NaN words in any peeked
  field of frost1, launch 1 or kill2. Coverage is only the actor head, the mover head and the camera.
- **Images** [verified]: there is **no Frostfire image and no online image at all**. The 18 images
  are menu/title, M51 single-player spawn/rest, and three PCSX2.
- **The precedent** [verified]: `spawn_ours2` is the §0 item-2 signature. Records 0–10 are the live
  ones and all read count 0; records 11–36 hold stale non-zero counts. The data-only walker of §7
  validated the grid/cell/model/polygon interpretation:
  - this wave's first version reproduced `spawn_ours` records 0, 1, 2 and 4 to surface, model and y
    (−145.879 vs −145.87, −147.024, −135.551, −153.468), and `spawn_pcsx2` record 0 (−145.873);
  - with the three rules the review added (§7), records 0–5 match exactly, 6/6, in both images
    (`rv23/walk.py`).

  It returns nothing on `spawn_ours2` because the cell list is empty. A direct polygon test on the
  unlinked model still finds y = −145.612.

---

## 5. Candidates, ranked

Each candidate gives its mechanism, why Frostfire and not kill2's map, and the launch-2 row that
shows it. "Rows" refer to the §6 instrument names.

### (1) The terrain is not linked into the grid cell under the spawn — grid collapse or missed insert — **most likely** [inference]

- **Mechanism:** the atom pool runs out, and the same insert cuts the cell chain (§2.1; one event in
  `FUN_002d7580`). Collision is present in
  memory but invisible to the query, so every probe in that region gets 0 candidates and the pin
  keeps the actor there.
- **Roots, sub-ranked:**
  - one or more objects inserted with huge or garbage bounds (the 2026-09-08 class). Online-only
    objects are the new suspects: remote avatar poses, slot actors on uninitialised `0xAF` heap,
    and a saturating VU0 path;
  - map-dependent atom pressure: grid size and object extents;
  - an insert that never happened for that map's static terrain.
- **Why Frostfire:** the grid dimensions, object count, spawn cells and heap layout are all per map.
  Heap addresses are deterministic per script, which fits 2/2 reproduction on both sides. kill2's map
  simply has headroom, or different victims. [inference]
- **Launch-2 row:**
  - `ProbeEval` dump word 13 (`+0x34`) = 0 **for every actor's record**, local and remote (a0
    differs per call);
  - with `W+0x6cc` (tick) still incrementing;
  - and `W+0x6bc` (free head) = 0 on some row. Free = 0 is sufficient but not necessary: removals
    refill the list while the chain stays cut. A healthy grid keeps nodes + free = 8192;
    orphaned atoms break that sum;
  - **decisive:** the RDRAM image gives a grid census near w×h nodes, or the walker empty at
    (795.73, 613.57) / (535.73, 1253.57) while a direct scan of models finds polygons there.

### ~~(2) Online heap corruption by the `memcpy` stub alias~~ — withdrawn [verified by review]

The voice codec's VU0 mode is 0 and its setter is unreferenced (§3.4), so the upload never runs.
This survives only as a latent runtime bug. Launch 2 confirms it cheaply: `VoiceVu0Upload`,
`VoiceVu0Mode` and `VoiceFftSel` should show **0 calls**, and peek `0x1d55a0` should read **0**.

### (2) The query runs over registered terrain but the polygon test fails on data only Frostfire exercises [inference]

- **Mechanism:** the COP2/VU0 path diverges from the console on:
  - non-identity model transforms (`FUN_002d93a0` quaternion/scale nodes → `FUN_00308160`
    VDIV/VWAITQ/VMULQ inverse);
  - model `+0x80` bit 1 (vf2.w = 0x30 instead of 0x20);
  - polygons with more vertices, or sub-model recursion;
  - or a VU0 micro image the edge test does not expect (§3.2 open).

  Each polygon edge then returns w = 0 and there are 0 candidates.
- **Why Frostfire:** M51 and kill2's terrain may use only identity-transform, single-sided
  triangles. A snow map's terrain may be a transformed or double-sided group. Not checked.
- **Launch-2 row:** `+0x34 = 0` **while** the grid census is healthy and the walker lists at least
  one `CDIPoly` at the spawn (x, z). If that polygon's model is flagged `XFORM` or has `+0x80` bit 1
  set, this candidate leads. `ProbeBatch`/`GridQuery` `[ret] v0 = 1` rules out the `0x44f078` gate.

### (3) Candidates exist but selection rejects them: material flags or table [inference]

- **Mechanism:** every candidate's material has VOLUMETRIC (bit 0) or LIQUID (bit 1) set
  (§1.1 step 9), or the material table is shifted or appended so the indices point at the wrong rows.
- **Why Frostfire:** it is the snow map. A "deep snow" soil flagged VOLUMETRIC over solid ground is
  plausible data. For *ours only* to differ, the SOILS table must differ (count, order or flags).
- **Launch-2 row:**
  - `+0x34 ≥ 1` with `[ret] ProbeEval v0 = 0`;
  - material index = `(cand.surface+8 >> 10) & 0xff` from the new dump
    `ProbeEval:a1+0x48*+0xc*:4`, word 2;
  - `0x44f354:2` count differs from the Medley control launch, or `0x44f358[m]+0x3c` in the image
    has bit 0 or bit 1 set.

### (4) Candidates exist but the spawn sits more than 20 units under all of them [inference]

- **Mechanism:** no candidate lies at or below origin_y + 1. The lowest one is above
  `*(A+0x28)+0x34 + 20`, so it is rejected.
- **Why Frostfire:** only if our spawn y differs from the console's. A = 101.0 flat is suggestive but
  unproven.
- **Launch-2 row:** `+0x34 ≥ 1`, `[ret] v0 = 0`; every candidate y (slot word 1) is greater than
  record word 2 + 1 **and** greater than `*0x408c58+0x28*+0x30` word 1 + 20.

### (e) Smaller items, each cheap to exclude

- **Probe never queued or taken:**
  - `+0xf40 = 0`, or `0x1061` bit 0x08 set;
  - shows as `ProbeQueue` or `ProbeTake` counts far below `PlayerUpd`, and `+0x2cc = −999` on rows;
  - bit 0x04 being set proves the take ran at least once. [verified logic]
- **`DAT_0044f078` set:** no static writer; peek `0x44f070:3`, word 2, low byte.
- **Stale layer mask:** excluded for launch 1 (§4). Re-check `+0x40c` stays 0.
- **HLE math stub:** none on the path (§3.3).

---

## 6. Launch-2 instruments: review of the plan, and additions

### 6.1 Planned rows, checked [verified]

| planned | verdict |
|---|---|
| traces `0x5b0840:ProbeQueue`, `0x5b0800:ProbeBatch`, `0x5b0420:ProbeTake` | right: each is reached by `jal` (actor vtable → `jal`), so the table hook fires |
| `0x5b5d40:ProbeEval` `[ret] v0` | right: v0 = the picked candidate or 0 |
| dump `ProbeEval:a1:19` | right: the whole record (§1.3) |
| dump `ProbeEval:a1+0x48*:16` | right, but covers only candidates 0–1; widen to `:32` (four) |
| peek `*0x408c58+0x2c0:4` | word 3 = `+0x2cc` (−999 = reset or not queued, −1 = taken, ≥0 = queued) |
| peek `*0x408c58+0xf40:1` | low byte = the physics gate |
| peek `0x3df1c8:1` | low byte = miss policy (expect 1) |
| peek `0x44d588:5` | array, 0, **records allocated** (`…590`), 0, **queued now** (`…598`, usually 0 after the batch) |
| peek `0x44f354:2` | material count, table pointer |

**Three reading traps** [verified in the tracer source]:
1. `PS2X_CALL_TRACE` logs the first 300 calls, then every k-th. **Keep `PS2X_CALL_TRACE_EVERY=10`**,
   as in launch 1: Task 3's MovePathWatch needs ≤ 20. The first 300 ProbeEval calls (~6 s) are
   logged in full, and the new traces cost about 20 MB per instance. [review]
2. A call that ends in a dispatch unwind prints `[ret-unwound]` and **no `[ret]` and no dump**.
   Count those before reading a missing dump as a miss.
3. **A hook on `0x2d3cf0` will not see this caller.** `FUN_0031de90` reaches it by a tail `j` that
   the generator emits as a direct C call. Hook **`0x31de90`** instead: its `[ret] v0` is
   `FUN_002d3cf0`'s.
4. **Other callers share these hooks** [verified by review]:
   - ProbeEval is also called by `FUN_005b4f30` (ra `0x5b5024`) with a1 = `W+0x14c`, a type-2
     column record. **Read ProbeEval rows with ra = `0x5b0478` only.**
   - GridQuery is also called from ra `0x29c7d8` (`FUN_0029bf70`) and ra `0x5ab6b0`
     (`FUN_005ab590`). **Read GridQuery rows with ra = `0x5b0828` only.**

### 6.2 Recommended launch-2 spec (reviewed set)

Additions to launch 1's full spec:

- **`PS2X_CALL_TRACE`:**
  `0x5b0840:ProbeQueue,0x5b0800:ProbeBatch,0x5b0420:ProbeTake,0x5b5d40:ProbeEval,0x31de90:GridQuery,0x252150:VoiceVu0Upload,0x251a98:VoiceVu0Mode,0x24fac0:VoiceFftSel`
- **`PS2X_CALL_TRACE_EVERY=10`**.
- **`PS2X_CALL_TRACE_DUMP`:**
  `ProbeEval:a1:19,ProbeEval:a1+0x48*:32,ProbeEval:a1+0x48*+0xc*:4,ProbeEval:a0+0x28*+0x30:3`
- **`PS2X_PEEK`:**
  `*0x45c380+0x684:4,*0x45c380+0x694:1,*0x45c380+0x6b4:3,*0x45c380+0x6c0:1,*0x45c380+0x6cc:1,*0x45c380+0x778:3,0x44f070:3,0x44d588:5,0x44f354:2,0x3df1c8:1,*0x408c58+0x2c0:4,*0x408c58+0xf40:1,*0x44d588*:19,0x1d55a0:1`
- **`PS2X_RDRAM_DUMP_AT`:** one per instance, at `ProbeEval#600`, with distinct paths. The runtime
  takes one spec per process. The trigger fires **before** the call, so the record holds the batch
  result; check the ra (`0x5b0478`) and a0 of call #600.
- **Budget:** about 20 MB of log plus 32 MB of image per instance.

What each addition reads:

| item | why |
|---|---|
| `GridQuery` `[ret] v0` (ra `0x5b0828`) | 0 = the `0x44f078` gate or an empty batch; 1 = walked |
| `ProbeEval:a1+0x48*:32` | four candidates: y, surface, normal, model |
| `ProbeEval:a1+0x48*+0xc*:4` | first candidate's surface: region, refcount, bitfield (material = bits 10..17), vtable |
| `ProbeEval:a0+0x28*+0x30:3` | actor matrix translation; the +20 reject uses its y |
| `*0x45c380+0x684:4` / `+0x694:1` | pool size, –, cell dimension, width / height |
| `*0x45c380+0x6b4:3` | cells, pool, **free-atom head** |
| `*0x45c380+0x6c0:1` / `+0x6cc:1` | inverse dimension / **tick** (must advance) |
| `*0x45c380+0x778:3` | grid origin x (word 0) and z (word 2) |
| `0x44f070:3` | cell-bit word, –, `0x44f078` gate |
| `*0x44d588*:19` | **record 0 = the first actor queued this frame**, not necessarily the local player; a host-timed sample independent of trace sampling |
| `0x1d55a0:1` and the three `Voice*` traces | expected 0 and 0 calls (§3.4) |

**Key discriminator:** read the grid peeks over time. A healthy grid keeps nodes + free = 8192; a
collapsed one shows free head = 0. The node count itself comes from the image census.

### 6.3 Reading order for launch 2

1. **`GridQuery` `[ret]`:** 0 → (e) gate; 1 → go on.
2. **`ProbeEval` word 13 for the local a0:**
   - 0 → (1) or (2). Read `W+0x6bc` and the other actor's records, then the image: grid census
     → (1); walker finds a polygon in a healthy grid → (2);
   - ≥1 → go to step 3.
3. **Candidates present:**
   - material bits → (3);
   - y versus origin + 1 and matrix y + 20 → (4);
   - neither → selection defect. Replay tier 1.
4. **Medley control launch with the same set:** the same rows must read "hit". Compare `0x44f354`,
   the grid dimensions and the free head.

---

## 7. Offline replay: can an RDRAM image separate "defect" from "data"?

**Feasible in tiers. Tiers 0 and 1 need only an RDRAM image of the running game.** [verified: the
code bytes of `FUN_005b5d40`, `FUN_002d3030` and `FUN_002dd150` and the vtables in `spawn_ours`,
`s4rand_ours` and `spawn_pcsx2` are identical to the ELF, so the image carries its own code.]

### Tier 0 — data-only walker (no emulation; validated today)

**Inputs:** one image; the spawn (x, z) from the peek rows.

**Algorithm** (reference scripts: this wave's `rw23/oracle.py`, `gridcensus.py` and `img.py`, and
the review's corrected `rv23/walk.py` and `grid.py`, all in session scratchpads that will not survive;
rebuild from this list):
1. Take G = `*(0x45c380)+0x684`. Compute `cx = clamp(int(G.inv·(x − G.orgx + 1e-4)))` and the same
   for z. Take `head = *(G+0x30 + 4·(cx + cz·w))`.
2. Walk the atoms (`obj = *atom`, `next = *(atom+4)`). For a `CCell` (`obj+0x58 == 10`), visit
   `*(child+0x64)` for each child in `obj+0xf0[0..obj+0xec)`, and visit `obj` itself.
3. Per model:
   - require `+0x5c` bit 0 and `+0x5d` bit 4, and the layer bit `1 << (+0x5c >> 13 & 0x1f)`
     against the record mask;
   - skip the model if it is the record's `+0x3c` node;
   - for each surface in `+0x7c[0..+0x78)` with vtable `0x406690`, `+8` bit 0 set and `+8` bit 18
     clear (`DAT_0044d758 == 0`), read
     `n = (+8 >> 2) & 0xff` vertices from `*(+0x10)` (16 bytes each);
   - test (x, z) inside the polygon in xz (same side of every edge) and compute y on the
     three-point plane; **stop at the first hit in this model**;
   - recurse into `+0x70[0..+0x6c)`;
   - flag the model as XFORM when the child's matrix is not the identity or `child+0x4c` bit 1 is
     set. Those models need the transform; the reference script only flags them.
4. **Grid census:** walk all w×h lists, count nodes by `+0x58` type, and walk the free list at
   `G+0x38`. Check nodes + free = 8192; any shortfall is orphaned atoms.

**Reads:**

| walker | grid | means |
|---|---|---|
| empty | near w×h nodes, nodes + free < 8192 | (1) |
| empty | nodes + free < 8192, but a direct model scan finds a polygon | (1), partial chain cut |
| polygon found | healthy (8192), game count 0 | (2) |
| polygon found | game count ≥1 but `v0 = 0` | (3) / (4) |

### Tier 1 — replay the selection in Unicorn

**Inputs:** the image dumped at `ProbeEval#n` (entry), the a0/a1 values from that trace line, and
`tools_py/ee_unicorn.py`.

**Sketch** [inference; untested]:

```python
import re, glob
from tools_py.ee_unicorn import EE
from unicorn.mips_const import UC_MIPS_REG_F12
ee = EE()
ee.write(0, open('frostA_probe600.rdram', 'rb').read())      # the image carries code and data
def rng(addr):                                                # function range from the generated header
    f = glob.glob(f'recomp/output/*_0x{addr:x}.cpp')[0]
    lo, hi = re.search(r'Address: 0x([0-9a-f]+) - 0x([0-9a-f]+)', open(f).read()).groups()
    return int(lo, 16), int(hi, 16) - int(lo, 16)
for a in (0x5b5d40, 0x5b5050, 0x5b52b0, 0x5b7350, 0x59acd0, 0x1821d0, 0x555280, 0x29ed20):
    ee.patch_range(*rng(a))                                   # R5900-only encodings -> emulated
for a in (0x290bd0, 0x5a2f90, 0x270e40, 0x2707c0):            # camera-target / footstep side effects
    ee.hook_function(a, lambda e: 0)                           # handler(ee) -> v0
ee.uc.reg_write(UC_MIPS_REG_F12, 0x3f800000)                  # single-precision 1.0 in f12's low word
v0 = ee.call(0x5b5d40, (A, REC, REC + 4), sp=0x01fe0000)      # A, REC from the ProbeEval #600 [call] line
print(hex(v0 & 0xffffffff), 'vs the trace [ret] v0')
```

- `FUN_005b5d40` and the ten callees checked contain **no COP2**, and the four query/eval
  functions checked contain no `$gp` loads [verified by instruction census].
- Whether Unicorn's MIPS64 FPU accepts `0x3f800000` written straight into F12 is untested.
  Verify it against a `c.lt.s` before trusting a result.
- **Reading:** the replay returns a pick where our run returned 0 → the recompiled selection or
  float compare is suspect. Both return 0 → the data really rejects.

### Tier 2 — replay the batch query (`FUN_002d3cf0` over the dumped array)

**Not feasible without new work.**
- `ee_unicorn` raises `NotImplementedError` on any COP2 instruction. The path uses about 25 COP2
  encodings: `lqc2`/`sqc2`/`qmtc2.i`, `vcallms`, the `vmula`/`vmadd`/`vmaddbc` family,
  `vmul`/`vadd`/`vsub`, `vdiv`/`vwaitq`/`vmulq`.
- It needs the **VU0 micro and data memory**, which no RDRAM image contains. Its source is still
  unlocated (§3.2).

**Cost:**
- a COP2 macro emulator in `ee_unicorn` (Python, SSE-free, with PS2 saturation);
- a small runtime addition that writes the 4 KB VU0 code and data next to `PS2X_RDRAM_DUMP_AT`;
- or a Python HLE of the four programs after decoding them from that capture.

Tier 0 already answers the data question. Tier 2 is only needed if the reading is (3).

---

## 8. External leads — reCOM (SOCOM 1) [believed, not proven]

`tools/reference/reCOM/src/gamez` names the same system:
- **`zdb::CGrid`** (`zGrid/zgrid.h`, `grid_main.cpp`):
  - `m_Atoms` (cell heads), `m_AtomBuf`, `m_FreeAtoms`, `m_InvCellDim`, `m_TickNum` initialised to −1,
    `m_origin` (grid bbox min), an `m_AtomCnt` pool (16384 in S1, `0x2000` measured in S2);
  - `Insert`/`Update`/`gridAddNodeToGrids`/`gridRemoveNodeFromGrids`, and `SetTraversalBoundary`
    / `StartTraversal` / `GetNextAtom`;
  - **`CGridAtom {Ent, Next, Prev}`** and **`zdb::CCell : CNode`**;
  - `MAX_NUM_CELL_ATOMS 1600`.

  This maps onto §2.1 offset for offset from `+0x30` to `+0x48`.
- **`zdb::DiIntersect`** (`zIntersect/zintersect.h`) is the probe record:
  - `m_Type:16` with the flags `m_IntersectCharacters/m_AltitudeCharacters/m_ProximityCharacters`;
  - `m_Tail`, `m_Tip`, `m_MTail`, `m_MTip` (+4, +0x10, +0x1c, +0x28);
  - `m_Cnt` (+0x34), `m_BufCnt` (+0x38), `m_Node` (+0x3c), `m_TreeDoneNode` (+0x40), then
    `m_Intersects`;
  - SOCOM II inserts the layer mask at +0x44 before the buffer pointer at +0x48.
- The S1 hit (`IntersectStruct {pos, norm, node}`) is 28 bytes; S2's 32-byte slot adds the surface
  at +0xc.
- **`DI_PARAMS`**: `m_region`, `m_refcount`, then `ditype:2 | ptcount:8 | material:8 | cameratype:2 | …`.
  This is exactly S2's surface `+8` bitfield (ptcount at bits 2–9, material at bits 10–17). The
  class is **`CDIPoly : CDI`**.
- `zCharacter/zchar.h` has `m_groundTouchDistance = 3.0f`, and `zSeal/zseal.h` has
  `m_ground_normal`. Neither has been matched to an S2 offset.

---

## 9. What this wave did not do

- It did not find the VU0 collision microcode's upload path or decode programs 0x10/0x20/0x70/0x80 (§3.2).
- It did not locate the VIF0 MPG packet that uploads the collision microcode (§3.2).
- It did not explain `spawn_ours`'s surplus of 839 grid models (§2.1).
- It could not know kill2's map name or its grid dimensions. The Medley control launch gives both
  through the §6.2 grid peeks.

---

## 10. Corrections after independent review (2026-09-13)

1. **§0.3, §3.4, §5(2):** the `memcpy`-alias candidate is withdrawn. The codec mode at `0x1d55a0`
   is 0 everywhere, and its setter chain `FUN_00251a98` ← `FUN_0024fac0` is unreferenced. It is now
   a latent runtime bug. `FUN_00252098`'s VU0 FFT sites are added.
2. **§3.4:** recompiled writes are correct only in `[0x11004000, 0x1100c000)`. VU0 micro and VU1 data
   alias to RDRAM. **§3.2:** the collision microcode must come in by VIF0 MPG [inference].
3. **§1.3, §6:** a `:64` candidate dump is eight candidates; the spec uses `:32` for four.
4. **§6.1:** keep `PS2X_CALL_TRACE_EVERY=10` (MovePathWatch needs ≤ 20).
5. **§6.2:** `PS2X_RDRAM_DUMP_AT` takes one spec per process; the second dump is dropped.
6. **§6.1:** added the second callers and ra filters (ProbeEval ra `0x5b0478`, GridQuery ra `0x5b0828`).
7. **§0.2, §4:** `spawn_ours2` has 11 live records at count 0, not six.
8. **§2.1, §5(1):** exhaustion and chain cut are one event in `FUN_002d7580`. Added the
   nodes + free = 8192 invariant, the orphan counts, the drain arithmetic, and the fill and remove paths.
9. **§1.1, §7:** the walker gains three rules: first hit per model, the surface `+8` bit-18 skip, and
   the `+0x3c` self skip. With them it matches 6/6 records in both images.
10. **§1.1:** `FUN_0031de90` ignores a0.
11. **§6.2:** `*0x44d588*:19` is labelled record 0 = first queued.
12. **§2.1:** the terrain hangs under a type-1 atom model, so a chain cut removes it.
13. **§6.2:** replaced by the reviewed spec. Candidates renumbered: (2) query-stage, (3) material,
    (4) placement.
