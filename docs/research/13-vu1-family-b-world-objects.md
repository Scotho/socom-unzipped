# 13 — VU1 dispatcher families B and C (world objects, clipping, multi-pass)

Addendum to `docs/research/12-vu1-entry0-ui-path.md` §(f). Research/12 documents the `0x1b50`
dispatcher and the three family-A handlers (`0x08`/`0xdf8`, `0x10`/`0xf90`, `0x28`/`0x1780`) to a
level an engineer can implement from. This note does the same for every **family-B** and
**family-C** handler, for the `0x3618` clip subroutine and its two inner helpers, and for the
shared packet-flush tail at `0x1980`.

Every claim is marked **[verified]** (read off the disassembly, the pc histogram, an executed
trace, or a differential run) or **[guess]**.

> Scope note. This is a document only — no runtime code was changed. All work was offline
> against `logs/vu1dump{2,3,4}`; no game was run.

---

## 0. Headline results

1. **Family B is the clipped-3D path.** `0x02` walks a per-primitive index list and calls
   `0x3618`, which is a **five-plane Sutherland–Hodgman polygon clipper** working on ping-pong
   buffers at data qwords **40** and **76**. It returns the clipped polygon base in `vi8` and its
   vertex count in `vi10`. **[verified]**
2. **Family B does not have its own per-vertex kernels.** Commands `0x0a`, `0x12`, `0x1a`, `0x56`
   are four-instruction *shims*: they set `vi3 = vi8` (clipped polygon), `vi4 = 150` (the family-B
   staging array), `vi9 = vi10` (clipped vertex count) and then **branch into the middle of the
   family-A handler's loop** (`0xe10`, `0xfa8`, `0x1460`, `0x5e8` respectively). One kernel, two
   bases. **[verified]**
3. **The primitive is emitted as a `TRIANGLE_FAN`.** `0x02` builds a per-primitive GIFtag at
   qword **112** (`NLOOP = vi10`, `EOP = 1`, PRIM/NREG/REGS copied from `TOP+0`); `0x2a`'s flush
   tail converts the 150-based staging quads into GS-format quads at **113…** and does
   `XGKICK 423` (an `NLOOP=0, EOP=1` terminator tag) followed by `XGKICK 112`. **[verified]**
4. **Family C is family A or B plus an inline-GIF-packet command.** `0x30` and `0x32` read an
   **8-qword block embedded in the command list itself**, `XGKICK` its first 7 qwords (a
   texture/render-state packet), rescale the staging array's `S`,`T` by a float taken from the
   block's 8th qword, advance `vi14` past the block, and then **tail-jump back into the draw
   handler** (`0x1780` for `0x30`, `0x1a78` for `0x32`) for a second pass. **This is the handler
   that rewrites `vi14`.** **[verified]**
5. **The clip-plane enable mask at qword `27.x` is dead.** All five stage gates are written
   `IAND` immediately followed by `IBEQ` on the same register, so the VU integer-branch hazard
   makes the branch read the pre-`IAND` value (the bit constant, never zero). All five planes are
   always clipped against. Proved by differential run: forcing `27.x` to `0` or `0xffffffff`
   changes neither the packets nor the cycle count. **[verified]**
   (`logs/vu1entry0/famBC_clipmask_test.txt`)
6. **The `0x3618` prologue's local→view transform is dead code.** It reads the live-in-looking
   `vf13`-`vf16`, produces `vf23`/`vf24`/`vf25` and `CLIPw`s them — but `vf23`/`vf25` are
   overwritten before any read, `vf24` is never read again, and **no `FCAND`/`FCOR`/`FCEQ`/`FCGET`
   exists anywhere in the 16 KB image**, so the clipping-flag register is never consumed. This is
   why research/12's `vf13`-`vf16` perturbation sweep saw no change. **[verified]**
7. **Research/12 §f.3's family-B hand-back rule is incomplete**: `vi12` is not the only register
   that crosses a `B 0x1b60` inside a family-B list. `vi8` and `vi10` do too (every shim reads
   them). See §6.

---

## 1. Corpus and histogram

### 1.1 Selection

Of the 166 dumps whose header `startPc == 0x1b50`, **48 are family B/C** — classified by whether
the decoded command list contains any of `0x02 0x0a 0x12 0x1a 0x2a 0x4c 0x56 0x64 0x30 0x32 0x72
0x74` (37 in `vu1dump4`, 7 in `vu1dump3`, 4 in `vu1dump2`). The remaining 118 are family A.
**[verified]** — `logs/vu1entry0/famBC_dumps.txt`.

> The brief said "the 90 family-B/C dumps". Across all three dump directories there are **48**,
> not 90. Research/12 §f.5 counted 37 family-B/C shapes in `vu1dump4` alone; adding `vu1dump3`
> (7) and `vu1dump2` (4) gives 48. The 90 figure does not correspond to any grouping found here.
> **[verified]**

### 1.2 The seven list shapes

| dumps | command list (static, linear read) | family | example |
|---|---|---|---|
| 12 | `68 06 02 0a 12 56 1a 2a 4c 42` | B, full | `logs/vu1dump4/vu1_prog_134.bin` |
| 11 | `68 02 0a 12 56 1a 2a 4c 42` | B, no cull | `logs/vu1dump4/vu1_prog_141.bin` |
| 8 | `68 06 02 0a 64 12 2a 32 …` | **C over B** | `logs/vu1dump4/vu1_prog_35.bin` |
| 8 | `68 06 64 08 10 28 30 …` | **C over A** | `logs/vu1dump4/vu1_prog_177.bin` |
| 6 | `68 06 02 0a 2a 4c 42` | B, minimal | `logs/vu1dump3/vu1_prog_13.bin` |
| 2 | `68 06 02 0a 12 2a 4c 42` | B, no fill/light | `logs/vu1dump4/vu1_prog_32.bin` |
| 1 | `68 06 64 08 10 28 72 34 …` | C over A, `0x34` variant | `logs/vu1dump3/vu1_prog_27.bin` |

**[verified]**. The `…` marks a list whose linear read runs into an embedded GIF packet — see
§3.2. Research/12 §f.5 printed those as `?0x8006`; they are not commands.

### 1.3 Execution histogram, 48 dumps

`dist/vu1_replay.exe --pchist logs/vu1entry0/famBC_hist.bin <the 48 dumps>`
→ **803 distinct instruction pairs, 1,002,137 pair-executions.** Ranges split at jump-table
targets; jump-table slots themselves (`0x1ba0`+) are omitted. `entered` = count at the range's
first pc. **[verified]** — `logs/vu1entry0/famBC_handlers.txt`.

| rank | pc range | pairs | pair-execs | entered | cmd | what it is | marking |
|---|---|---|---|---|---|---|---|
| 1 | `0x3618-0x3d20` | 226 | 603,937 | 904 | — (`BAL vi15` from `0x2070`) | **five-plane Sutherland–Hodgman clipper**, with `0x3a90` (close polygon) and `0x3ad0` (clip one edge) inside. 60 % of all VU1 work in this corpus. | **[verified]** |
| 2 | `0x0f90-0x1100` | 47 | 59,271 | 9 | `0x10` | family-A distance fade; **entered 765×** at its loop head `0xfa8` (9 from `0x10`, 756 from `0x12`) | **[verified]** |
| 3 | `0x1980-0x1a70` | 31 | 49,261 | 961 | — (`B 0x1980` from `0x1ab8`) | **shared packet-flush tail**: staging → GS format → `XGKICK 423` + `XGKICK 112` | **[verified]** |
| 4 | `0x0df8-0x0f00` | 34 | 45,800 | 9 | `0x08` | family-A transform+divide; loop head `0xe10` entered 791× (9 + 782 from `0x0a`) | **[verified]** |
| 5 | `0x1b60-0x1b98` | 8 | 40,736 | 5092 | `0x4a` | the dispatcher body — 5092 commands over 48 programs = 106 per program | **[verified]** |
| 6 | `0x1f70-0x20c0` | 43 | 36,893 | 39 | **`0x02`** | world-object setup; per-primitive loop head `0x1f98` ran 1224× | **[verified]** |
| 7 | `0x1460-0x15a8` | 42 | 36,652 | 539 | — (`B 0x1460` from `0x15c8`) | the lighting loop, entered only by `0x1a` in this corpus (`0x18` never dispatched) | **[verified]** |
| 8 | `0x0b20-0x0c58` | 40 | 22,858 | 48 | **`0x68`** | int→float unpack, **in place**; first command of every list | **[verified]** |
| 9 | `0x1638-0x1768` | 39 | 22,535 | 37 | **`0x06`** | backface cull: sets bit 0 of each index record's `w` | **[verified]** |
| 10 | `0x1780-0x1960` | 61 | 17,010 | 18 | `0x28` | family-A triangle→GIF→`XGKICK`; 9 dispatched + 8 from `0x30`'s `JR` + 1 from `0x34`'s | **[verified]** |
| 11 | `0x22a0-0x23a8` | 34 | 13,598 | 8 | **`0x30`** | inline state packet + `ST` rescale, then `JR 0x1780` | **[verified]** |
| 12 | `0x1a78-0x1ac0` | 10 | 9,610 | 961 | **`0x2a`** | flush gate (782 dispatched + 179 from `0x32`'s `JR`) | **[verified]** |
| 13 | `0x20c8-0x2108` | 9 | 8,529 | 1224 | **`0x4c`** | primitive loop back-edge (782 dispatched + 442 skip-branches from `0x1f70`) | **[verified]** |
| 14 | `0x05e8-0x0638` | 11 | 5,929 | 539 | — (`B 0x5e8` from `0x648`) | the template-fill loop, entered only by `0x56` here | **[verified]** |
| 15 | `0x0f08-0x0f38` | 7 | 5,474 | 782 | **`0x0a`** | `XGKICK 423`, then shim into `0xe10` | **[verified]** |
| 16 | `0x1108-0x1120` | 4 | 3,024 | 756 | **`0x12`** | shim into `0xfa8` | **[verified]** |
| 17 | `0x2690-0x2950` | 89 | 2,993 | 1 | **`0x34`** | 11-qword inline block variant of `0x30`; ran once in the whole corpus | **[verified]** range; body **[partial]** |
| 18 | `0x15b0-0x15d0` | 5 | 2,695 | 539 | **`0x1a`** | shim into `0x1460` | **[verified]** |
| 19 | `0x0640-0x0650` | 3 | 1,617 | 539 | **`0x56`** | shim into `0x5e8` with base 150 | **[verified]** |
| 20 | `0x04a8-0x04d0` | 6 | 1,128 | 188 | **`0x64`** | `XGKICK 330` (the render-state packet) | **[verified]** |
| 21 | `0x23b0-0x23d0` | 5 | 895 | 179 | **`0x32`** | `0x30` on the 150 base, then `JR 0x1a78` | **[verified]** |
| 22 | `0x2280-0x2298` | 4 | 752 | 188 | **`0x74`** | `qword 39.w := 2` (draw gate on) | **[verified]** |
| 23 | `0x2268-0x2278` | 3 | 564 | 188 | **`0x72`** | `qword 39.w := 0` (draw gate off) | **[verified]** |
| 24 | `0x1b40-0x1b48` | 2 | 96 | 48 | `0x42` | E bit; 9 of 48 arrive via command `0x42`, the other 39 via `0x4c`'s `B 0x1b40` | **[verified]** |
| 25 | `0x1b50-0x1b58` | 2 | 96 | 48 | — | the `XTOP` half, once per program from the EE's `MSCAL` | **[verified]** |

Per-command dispatch counts (read from the jump-table slot pcs), 48 dumps, 5092 dispatches:

```
0x4c 782  0x2a 782  0x0a 782  0x12 756  0x56 539  0x1a 539
0x74 188  0x72 188  0x64 188  0x32 179  0x68  48  0x02  39
0x06  37  0x42   9  0x28   9  0x10   9  0x08   9  0x30   8  0x34 1
```
**[verified]**

Active `XGKICK` sites (pair-execution counts, 3428 kicks total):

| pc | register | value | who | count | marking |
|---|---|---|---|---|---|
| `0x04b8` | `vi2` | 330 | `0x64` | 188 | **[verified]** |
| `0x0f10` | `vi4` | 423 | `0x0a` | 782 | **[verified]** |
| `0x1920` | `vi2` | 300/290 | `0x28` (per triangle) | 348 | **[verified]** |
| `0x1a48` | `vi6` | 423 | flush tail | 961 | **[verified]** |
| `0x1a58` | `vi5` | 112 | flush tail | 961 | **[verified]** |
| `0x2310` | `vi5` | `340 + vi14` | `0x30`/`0x32` (inline block) | 187 | **[verified]** |
| `0x26f8` | `vi5` | `340 + vi14` | `0x34` | 1 | **[verified]** |

---

## 2. VU data-memory map as families B and C use it

`vi1 = XTOP` (424 or 724 in this corpus). Qword numbers without `TOP+` are absolute.

| qword(s) | role | written by | read by | marking |
|---|---|---|---|---|
| `26` | a GIFtag (`NLOOP=0, EOP=1, PRIM …`) | entry 0 | `0x1968` (cmd `0x40`) — not used by B/C | **[verified]** |
| `27.x` | **dead** clip-plane enable mask (§4.4) | entry 0 | `0x3618` (result discarded) | **[verified]** |
| `27.y`,`27.z` | lighting scale factors | entry 0 | `0x1440`/`0x15b0` (`vf31`) | **[verified]** |
| `28` | distance-fade reference point (`.w` = fog base offset) | entry 0 flag-bit-3 path | `0xfa8` (`vf17`) | **[verified]** |
| `29` | distance-fade per-axis scale (`.w` = fog base scale) | entry 0 | `0xfa8` (`vf18`) | **[verified]** |
| `30` | **eye position**, `w = 1.0` — also the plane point for clip planes 2-5 | entry 0 (`0x330`) | `0x1638` (`vf26`), `0x3618` stages 2-5 (`vf28`) | **[verified]** |
| `31` | second plane point (near plane), `w = 1.0` | entry 0 | `0x3618` stage 1 (`vf28`) | **[verified]** |
| `32` | clip-plane 1 normal, `w = 0` | entry 0 | `0x3618` stage 1 (`vf30`) | **[verified]** |
| `33`-`36` | clip-plane 2-5 normals, `w = 0` | entry 0 | `0x3618` stages 2-5 (`vf30`) | **[verified]** |
| `38` | `(1,1,1,0.5)` — the fixed-point rounding bias | entry 0 | `0x1780`, flush tail `0x1980` | **[verified]** |
| `39.w` | **global draw gate**, `0` or `2` | commands `0x72`/`0x74` | `0x1780`, `0x1a78` | **[verified]** |
| `40 … 40+3N-1` | family-A staging array (3 qwords/vertex: ST, RGBAQ, XYZF2) | `0x08`,`0x54`,`0x18`,`0x10` | `0x28` | **[verified]** (research/12 f.4) |
| `40 … 75` | **clipper ping-pong buffer A** (12 vertex slots × 3 qwords) | `0x3618` | `0x3618` | **[verified]** |
| `76 … 111` | **clipper ping-pong buffer B** | `0x3618` | `0x3618` | **[verified]** |
| `112` | **the per-primitive GIFtag** (`x` = `NLOOP|0x8000`, `y`/`z` copied from `TOP+0`, `w` = a software flag) | `0x1f70` | `0x1a78` (reads `w`), `XGKICK 0x1a58` | **[verified]** |
| `113 …` | the family-B GIF packet body, 3 qwords/vertex in `REGS` order | flush tail `0x1980` | GS via `XGKICK 112` | **[verified]** |
| `150 … 150+3V-1` | **the family-B staging array** (`V` = clipped vertex count) | `0x0a`,`0x12`,`0x56`,`0x1a`,`0x32` | `0x2a` flush tail, `0x32` | **[verified]** |
| `290-299`, `300-309` | family-A ping-pong GIF packet buffers | `0x28` | GS | **[verified]** (research/12 f.4) |
| `327` | template colour quad; **`.w` is the alpha scale used by the flush tail** | entry 0 (`SQ vf5`) | `0x5e8`, `0x17d8`, `0x1990` | **[verified]** |
| `328` | unknown (`10000000 11111111 0 0` in the corpus) | entry 0 (`SQ vf6`) | `0x04f8` (cmd `0x5c`, never dispatched) | **[guess]** |
| `329.x`,`329.y` | family-A packet-buffer bases (300, 290) | `0x1950`/`0x1960` | `0x17e0`/`0x17e8` | **[verified]** |
| `329.z` | **saved index-list pointer** across the `BAL` that clobbers `vi15` | `0x1fe0` | `0x20d0` | **[verified]** |
| `330 … 335` | the render-state packet kicked by `0x64`: GIFtag `NLOOP=5, EOP=1, NREG=1, REGS=A+D`, then 5 A+D register writes (observed: `ALPHA_1 0x42`, `TEX1_1 0x14`, `TEX0_1 0x06`, `TEST_1 0x47`, `CLAMP_1 0x08`) | EE via VIF | GS via `XGKICK 330` | **[verified]** tag + count; the register set is per-object data, so the list above is **[guess]** as a general rule |
| `423` | a GIFtag with `NLOOP = 0, EOP = 1` — a **1-qword terminator/flush tag** | EE via VIF | `XGKICK` at `0x0f10` and `0x1a48` | **[verified]** |
| `340 …` | the command list (see §3) | entry 0 | the dispatcher, `0x30`/`0x32`/`0x34` | **[verified]** |
| `TOP+0` | the **per-primitive** GIFtag template: `EOP=1, PRE=1, PRIM = TRIANGLE_FAN\|IIP\|TME\|FGE\|ABE, FLG=PACKED, NREG=3, REGS = ST, RGBAQ, XYZF2` | EE via VIF | `0x1f70` (`LQ 0(vi1)` → `SQ.yz 112`) | **[verified]** |
| `TOP+1` | the **whole-object** GIFtag template: same but `PRIM = TRIANGLE`, `NLOOP` = vertex count | EE via VIF | `0x1780` | **[verified]** |
| `TOP+2.x` | qword offset (added to `vi1`) of the **index list** | EE | `0x1638`, `0x1780`, `0x1f70` | **[verified]** |
| `TOP+2.z` | **vertex count** | EE | `0x0b20`, `0x0df8`, `0x0f90`, `0x05d8`, `0x1440`, `0x22a0`, `0x2690` | **[verified]** |
| `TOP+2.w` | **primitive count** | EE | `0x1638`, `0x1780`, `0x1f70` | **[verified]** |
| `TOP+3` | position bias added by `0x0b20`; `(0,0,0,1)` in the corpus | EE | `0x0b20` | **[verified]** |
| `TOP+4 …` | the **vertex block**, 3 qwords per vertex (§4.1) | EE; rewritten in place by `0x68` | everything | **[verified]** |
| `vi1 + TOP+2.x …` | the **index list**, 2 qwords per primitive (§4.2) | EE; `w` flags rewritten by `0x06` | `0x06`, `0x28`, `0x02` | **[verified]** |

> `40-75`/`76-111` (clipper) and `40 … 40+3N-1` (family-A staging) are the **same memory**. No
> list in the corpus uses both: `0x02` never appears with `0x08`/`0x10`/`0x28` except in the
> C-over-B shape, where `0x08`/`0x10`/`0x28` are absent. The one C-over-A shape that does use the
> 40-base staging (`68 06 64 08 10 28 30`) has no `0x02`, hence no clipper. **[verified]**

**Buffer bound.** `76 - 40 = 36` qwords = 12 vertex slots, and `112 - 76 = 36`. A triangle
clipped against 5 planes can reach 8 vertices, plus the 1-vertex wrap copy the clipper appends =
9 slots. The layout therefore has 3 slots of headroom. **[verified]** (spacing); the ≤ 8 bound
is the standard convex-polygon Sutherland–Hodgman argument, **[guess]** as a hard guarantee.

---

## 3. The command list, revisited

Research/12 §f.2 has the base format (one command per qword at 340, `x` low-16 = command word =
2 × jump slot, `y` = branch target for `0x4c`, `z`/`w` unread). Two corrections:

### 3.1 The `z` field is read — by `0x30`, `0x32` and `0x34`

`0x22d8`/`0x26d0`: `ILW.z vi7, 339(vi14)`. At handler entry `vi14` is already the index of the
*next* command (the dispatcher increments at `0x1b70`), so `339 + vi14` addresses the handler's
**own** list qword. `vi7` is the **number of inline blocks** that follow. It is `1` in every one
of the 187 dispatches in the corpus (`0x22e0`, the outer loop head, ran exactly 187 times for 187
entries). **[verified]** that the field is read and that it is 1 here; **[guess]** that values > 1
occur in other scenes.

Research/12 §f.2 marks `z`/`w` "no handler in the corpus was observed reading them" — that is now
falsified for `z`. `w` is still never read. **[verified]**

### 3.2 A list can contain embedded GIF packets

`0x30`/`0x32` consume **8 qwords** of the list per block, `0x34` consumes **11**. The first qword
is a real GIFtag, `NLOOP` of which says how many of the following qwords are kicked; the
remainder are VU-only parameters. `vi14` is advanced past the whole block, so the list resumes
after it.

Decoded, `logs/vu1dump4/vu1_prog_177.bin` (C over A). `0x30` sits at index 6, so at entry
`vi14 = 7` and the block is `q347…q354`:

```
 [0] q340 cmd=0x68                        int->float unpack
 [1] q341 cmd=0x06                        backface cull
 [2] q342 cmd=0x64                        XGKICK qword 330 (render state)
 [3] q343 cmd=0x08                        transform + perspective divide (base 40)
 [4] q344 cmd=0x10   y=3                  distance fade
 [5] q345 cmd=0x28   y=3                  triangles -> GIF -> XGKICK
 [6] q346 cmd=0x30   y=3  z=1             INLINE BLOCK x1 follows; then JR 0x1780
 [7] q347   GIFtag  NLOOP=6 EOP=1 NREG=1 REGS=A+D     <- XGKICK'd (7 qwords)
 [8] q348     A+D  ALPHA_1   (0x42)
 [9] q349     A+D  TEX1_1    (0x14)
[10] q350     A+D  TEX0_1    (0x06)
[11] q351     A+D  TEST_1    (0x47)
[12] q352     A+D  CLAMP_1   (0x08)
[13] q353     A+D  MIPTBP1_1 (0x34)
[14] q354   .x = 0x40800000 = 4.0f        <- the S/T rescale factor, VU-only
[15] q355 cmd=0x72                        draw gate := 0
[16] q356 cmd=0x74                        draw gate := 2
[17] q357 cmd=0x42                        END (E bit)
```
**[verified]** — `logs/vu1entry0/famBC_cmdlists.txt`.

`logs/vu1dump4/vu1_prog_35.bin` (C over B) is the same idea with `0x32` at index 7, block
`q348…q355` (`q355.x = 4.0f`), list resuming at `q356` with `72 74 4c`, and `0x4c`'s `y = 3`
looping back to index 3 (`0x0a`).

`logs/vu1dump3/vu1_prog_27.bin` has `0x34` at index 7, `vi14 = 8`, block `q348…q358`: GIFtag
`NLOOP=5`, five A+D writes at `q349…q353`, then **five** VU-only parameter qwords `q354…q358`
(read at `6(vi5)`…`10(vi5)`), list resuming at `q359` with `74 42`. **[verified]**

### 3.3 So a linear parse of the list is wrong twice over

`0x4c`/`0x32`/`0x30`/`0x34` all rewrite `vi14`. A parser must either follow the handlers or stop
at the first command word it cannot explain. Research/12 §f.5's `?0x8006` entries are the first
qword of an inline block, not a command. **[verified]**

---

## 4. The handlers

### 4.1 `0x68` → `0x0b20` — int→float vertex unpack (converts **in place**)

This closes one of research/12 §f.4's three open family-A gaps as well.

```
vi3 = vi1 + 4                     ; the vertex block
vi9 = ILW.z 2(vi1)                ; vertex count
vf27 = LQ 3(vi1)                  ; TOP+3, the position bias
loop, TWO vertices per iteration, vi9 -= 2, vi3 += 6:
    ; vertex k occupies qwords vi3+0..vi3+2, vertex k+1 qwords vi3+3..vi3+5
    q+0 : vf21 = ITOF4.xyz(q+0)   ; position, 4 fraction bits  (value / 16)
          vf21.w = ITOF15.w(q+0)  ;                            (value / 32768)
          vf21.xyz += vf27        ; TOP+3 bias
    q+1 : vf31.xy = ITOF12.xy(q+1)   ; U,V  (value / 4096)
          vf31.zw = ITOF15.zw(q+1)   ;      (value / 32768)
    q+2 : vf22    = ITOF0.xyzw(q+2)  ; straight int->float (the colour quad)
    SQ vf21 -> -6(vi3) ; SQ vf31 -> -5(vi3) ; SQ vf22 -> -4(vi3)   ; == q+0,q+1,q+2
    (same three stores for vertex k+1 at -3,-2,-1)
B 0x1b60
```
`IBLTZ vi9, 0x1b60` at `0x0be8` exits early on an odd count after storing only the first of the
pair. The loop is software-pipelined two vertices deep and reads one vertex past the end.
**[verified]** — the store offsets `-6..-1` after `vi3 += 6` are exactly the qwords just read, so
the conversion is **in place**; there is no separate destination array.

Consequence for family B: the source vertex record is **3 qwords**, and after `0x68` it holds
float position (`+0`), float `U,V,?,?` (`+1`) and float colour (`+2`) — the same three-qword shape
the clipper interpolates and the staging array uses. **[verified]**

### 4.2 `0x06` → `0x1638` — backface cull (writes bit 0 of each index record)

```
vi4 = vi1 + ILW.x 2(vi1)          ; index list
vi9 = ILW.w 2(vi1)                ; primitive count
vf26 = LQ 30(vi0)                 ; the eye
vi3 = vi1 + 4                     ; vertex block
vi5 = 16                          ; FMAND mask = MAC bit 4 = Sw
per primitive (vi4 += 2):
    vi8  = ILW.x 0(vi4)                     ; first vertex's qword offset
    vf29 = ITOF15(LQ 1(vi4))                ; the FACE NORMAL, 15-bit fixed point
    vf28 = LQ 0(vi3 + vi8)                  ; that vertex's (float) position
    vf27 = vf26 - vf28                      ; eye - vertex
    vf30 = vf27 * vf29 ; vf30.w = x + y + z ; the dot product
    vi12 = ILW.w 0(vi4) & 32766             ; clear bits 0 and 15
    FMAND vi13, vi5                         ; vi13 = Sw(vf30) -> sign of the dot
    if (vi13 == 0) vi12 |= 1                ; dot >= 0  => front-facing
    ISW.w vi12 -> 0(vi4)
B 0x1b60
```
**[verified]**. So the **index record is 2 qwords**: `[0].x/.y/.z` = the three vertices' qword
offsets relative to `vi1+4` (stride 3), `[0].w` = flags (**bit 0 = front-facing**, written here;
**bit 1** = a second software flag the EE sets), `[1]` = the face normal in 15-bit fixed point.
**[verified]**

### 4.3 `0x02` → `0x1f70` — world-object setup, one primitive per dispatcher round trip

```
0x1f70  vi15 = ILW.x 2(vi1)              ; index-list qword offset
0x1f78  vi12 = ILW.w 2(vi1)              ; PRIMITIVE COUNTER  (survives the hand-back)
0x1f90  vi15 = vi15 + vi1                ; index-list pointer
------- per-primitive re-entry point (0x4c branches back here) -------
0x1f98  vi3  = vi1 + 4                   ; vertex block
0x1fa0  vi11 = 1
0x1fa8  vi13 = ILW.w 0(vi15)             ; flags
0x1fb0  vi5  = ILW.x 0(vi15)             ; vertex 0 qword offset
0x1fb8  vi6  = ILW.y 0(vi15)             ; vertex 1
0x1fc0  vi7  = ILW.z 0(vi15)             ; vertex 2
0x1fc8  vi11 = vi13 & 1                  ; the front-facing bit from 0x06
0x1fd0  vi15 += 2                        ; next index record
0x1fd8  if (vi11 == 0) goto 0x20c8       ; culled -> straight to the loop back-edge
0x1fe0  ISW.z vi15 -> 329(vi0)           ; save it: the BAL below clobbers vi15
0x1fe8  vi11 = 2
0x1ff0  vi13 = vi13 & 2                  ; the second flag bit
0x1ff8  ISW.w vi13 -> 112(vi0)           ; stash it in the GIFtag's REGS[8..15] word
0x2000  vf17,vf18,vf19 = LQ 0,1,2 (vi3 + vi5)     ; vertex 0's three qwords
0x2020  vf26,vf27,vf28 = LQ 0,1,2 (vi3 + vi6)     ; vertex 1
0x2040  vf29,vf30,vf31 = LQ 0,1,2 (vi3 + vi7)     ; vertex 2
0x2060  vi10 = 3 ; vi11 = 3
0x2070  BAL vi15, 0x3618                 ; CLIP. returns vi8 = polygon base, vi10 = vertex count
0x2080  if (vi10 == 0) goto 0x20c8       ; clipped away entirely
0x2090  vf22 = LQ 0(vi1)                 ; TOP+0, the TRIANGLE_FAN GIFtag template
0x2098  vi11 = vi10 + 32767
0x20a0  vi11 = vi11 + 1                  ; == vi10 | 0x8000  (NLOOP = vi10, EOP = 1)
0x20a8  ISW.x vi11 -> 112(vi0)
0x20b0  SQ.yz  vf22 -> 112(vi0)          ; PRE/PRIM/FLG/NREG (y) and REGS (z)
0x20b8  B 0x1b60                         ; hand back
```
**[verified]** from the disassembly and confirmed by counts: `0x1f98` ran 1224 times (total
primitives), `0x2060` 904 (passed the front-facing gate; 320 culled), `0x2090` 782 (survived
clipping; 122 clipped away), `0x20b8` 782.

Notes an implementer must not miss:

* `vi15` is **both** the index-list cursor **and** the `BAL` link register. `0x1fe0` saves the
  cursor to `329.z` before the call; `0x20c8` restores it. **[verified]**
* `vi11 = vi10 + 32767 + 1` is 16-bit wraparound, i.e. `NLOOP = vi10, EOP = 1`. The observed
  qword-112 `x` value is `0x00008003` for a 3-vertex primitive. **[verified]**
* `ISW.w vi13, 112(vi0)` writes a **software flag into the GIFtag's `REGS[8..15]` word**. With
  `NREG = 3` the GS ignores it; `0x1a78` reads it back as `ILW.w -1(vi4)`. **[verified]**
* The `IBEQ vi11, vi0` at `0x1fd8` has an intervening instruction after the `IAND`, so it reads
  the fresh value — unlike the clipper's gates (§4.4). **[verified]**

### 4.4 `0x3618` — the five-plane Sutherland–Hodgman clipper

Called only from `0x2070`. Live-in: `vf17`/`vf18`/`vf19`, `vf26`/`vf27`/`vf28`,
`vf29`/`vf30`/`vf31` (the three vertices, 3 qwords each), `vi15` (return address),
`vf13`-`vf16` (read, but the result is dead). Live-out: **`vi8`** = base qword of the final
polygon, **`vi10`** = its vertex count. **[verified]**

Clobbered: `vi2` (the inner link register), `vi4`-`vi11`, `vi13`, `vf17`-`vf19`, `vf21`-`vf28`,
`vf30`, `ACC`, `Q`, the MAC and clipping flag registers. `vf20`, `vf29` and `vf31` are **not**
written; `vi3`, `vi12` and `vi14` are not written. Nothing else in a family-B list depends on any
of the clobbered registers across the call. **[verified]** (register scan of `0x3618`-`0x3d20`). The caller's `vi10 = 3 ; vi11 = 3` at `0x2060` is redundant — `0x3618`
sets both itself at `0x36d0`/`0x36d8`. **[verified]**

#### Prologue (`0x3618`-`0x3690`)

```
vi4 = ILW.x 27(vi0)               ; the plane mask -- DEAD, see below
vi5 = 40 ; vi6 = 76               ; the two ping-pong buffers
vi8 = vi5
vf23 = vf13*vf17.x + vf14*vf17.y + vf15*vf17.z + vf16    ; local->view transform
vf24 = same for vf26 ; vf25 = same for vf29
SQ vf17,vf18,vf19 -> 0,1,2(vi8)   ; vertex 0
SQ vf26,vf27,vf28 -> 3,4,5(vi8)   ; vertex 1
SQ vf29,vf30,vf31 -> 6,7,8(vi8)   ; vertex 2
SQ vf17,vf18,vf19 -> 9,10,11(vi8) ; VERTEX 0 AGAIN -- the wrap copy
CLIPw.xyz vf23, vf23w ; CLIPw vf24 ; CLIPw vf25
```
**The transform and the three `CLIPw`s are dead.** `vf23` is overwritten at `0x36f0` (`LQI`),
`vf25` inside `0x3ad0`, `vf24` is never read again, and no `FCAND`/`FCOR`/`FCEQ`/`FCGET` exists
anywhere in the image, so the clipping-flag register is never consumed. **[verified]** (grep over
`logs/vu1entry0/full_dis.txt`; the only `CLIP` matches are these three.) This explains
research/12 §f.3's finding that perturbing `vf13`-`vf16` changes nothing — and corrects its
stated reason ("`0x3618` writes `vf13..vf16` before use"): `0x3618` **reads** them, the result is
simply discarded.

The **wrap copy** is what makes the edge loop work: with `N` input vertices laid out at
`base + 3k` and vertex 0 repeated at `base + 3N`, `N` calls to `0x3ad0` cover edges
`v0→v1, v1→v2, …, v(N-1)→v0`. **[verified]**

#### The five stages (`0x3698`, `0x3758`, `0x3818`, `0x38e0`, `0x39a8`)

Five textually identical blocks, differing only in the mask bit and the two plane qwords:

| stage | mask bit tested | plane point (`vf28`) | plane normal (`vf30`) | marking |
|---|---|---|---|---|
| 1 | `0x20` | qword **31** | qword **32** | **[verified]** |
| 2 | `0x02` | qword **30** (the eye) | qword **33** | **[verified]** |
| 3 | `0x01` | qword **30** | qword **34** | **[verified]** |
| 4 | `0x08` | qword **30** | qword **35** | **[verified]** |
| 5 | `0x04` | qword **30** | qword **36** | **[verified]** |

Each block is:

```
vi8 = <bit> ; vi8 = vi4 & vi8 ; if (vi8 == 0) goto <next stage>     ; *** NEVER TAKEN ***
vf28 = LQ <point>(vi0) ; vf30 = LQ <normal>(vi0)
vi8  = vi5            ; input buffer
vi9  = vi6            ; output write pointer
vi10 = <3 for stage 1, else vi11>    ; input vertex count
vi11 = 0                             ; output vertex count
LQI vf21,vf22,vf23 <- (vi8++)        ; load vertex 0 as the first "previous"
repeat vi10 times:  BAL vi2, 0x3ad0  ; clip one edge, appends 0..2 vertices at vi9
vi8 = vi6 ; BAL vi2, 0x3a90          ; close the polygon: copy output[0] to the tail
if (vi11 == 0) goto 0x3a80           ; nothing left -> return with vi10 == 0
swap vi5 <-> vi6                     ; the output becomes the next stage's input
------- after stage 5 -------
0x3a70  vi8  = vi5                   ; final polygon base
0x3a78  vi10 = vi11                  ; final vertex count
0x3a80  JR vi15
```

**The `if (vi8 == 0)` gate is never taken.** `IAND vi8, vi4, vi8` sits in the instruction slot
immediately before `IBEQ vi8, vi0, …`, and on the VU a branch reading an integer register written
by the immediately preceding instruction sees the **stale** value — here the bit constant, which
is never zero. The interpreter models this (`delaysNextBranchRead` /
`recordViWriteForBranch` in `third_party/ps2recomp/ps2xRuntime/src/lib/vu/ps2_vu1_core.cpp`).
Confirmed two ways: the histogram shows every stage's body entered exactly as often as its gate
(904 / 838 / 820 / 798 / 782), and forcing qword `27.x` to `0` or `0xffffffff` changes neither the
packets nor the cycle count. **[verified]**
**A native implementation must therefore run all five planes unconditionally and must not read
qword 27.x.**

**Early-out asymmetry.** In stages 1 and 2 the `IBEQ vi11, vi0, 0x3a80` sits *in the `BAL`'s
delay slot* (`0x3738`, `0x37f8`); in stages 3-5 the delay slot is a `NOP` and the `IBEQ` follows
the return (`0x38c0`, `0x3988`, `0x3a50`). Net behaviour is identical because a taken delay-slot
branch cancels the `BAL` — the polygon-close is skipped, but the polygon is empty anyway. Counts:
`0x3a90` ran 4058 times against 4142 `BAL`s; the 84 missing are exactly stage 1's 66 and stage 2's
18 early-outs. **[verified]**
On the early-out path `vi10` is 0 (the edge loop just ended) and `0x3a70`/`0x3a78` are skipped, so
the caller's `IBEQ vi10, vi0, 0x20c8` fires. 122 of 904 calls took this path. **[verified]**

#### `0x3a90` — close the polygon (3 qwords, `vi8` → `vi9++`)

```
vf21,vf22,vf23 = LQ 0,1,2(vi8) ; SQI each to (vi9++) ; JR vi2
```
Called with `vi8 = vi6` (the output buffer base) and `vi9` pointing just past the last emitted
vertex: it appends a copy of output vertex 0 so the next stage's edge loop wraps. 4058 calls.
**[verified]**

#### `0x3ad0` — clip one edge (the hot loop: 12,492 calls, ~46 % of all pair-executions)

On entry `vf21`/`vf22`/`vf23` hold the **current** vertex `P`; `vi8` points at the **next**
vertex; `vi9` is the output cursor; `vi11` the output count; `vf28`/`vf30` the plane.

```
vf17,vf18,vf19 = vf21,vf22,vf23        ; P  (saved)   -- ADDx against vf0.x (== 0)
vf21,vf22,vf23 = LQI (vi8++) x3        ; C  (the next vertex)
vf25 = C.q0 - vf28 ; vf26 = P.q0 - vf28
vf25.xyz *= vf30   ; vf26.xyz *= vf30
vf25.w = vf25.x+vf25.y+vf25.z          ; dC  (signed distance of C)
vf25.z = vf25.w                        ; stash dC in .z too
vf26.w = vf26.x+vf26.y+vf26.z          ; dP
vi7  = FMAND(32)  -> 32 iff dC < 0     ; MAC bit 5 = Sz, from the ADDw.z that wrote vf25.z
vi13 = FMAND(16)  -> 16 iff dP < 0     ; MAC bit 4 = Sw, from the MADDz.w that wrote vf26.w
vf25.w = dP - dC ; vf26.z = dC - dP
vi13 |= vi7                            ; 0 | 16 | 32 | 48
DIV Q, vf26.w, vf25.w                  ; Q = dP / (dP - dC)     (issued in a delay slot)

vi13 == 0   both inside  -> SQI P (3 qwords); vi11 += 1
vi13 == 48  both outside -> emit nothing
vi13 == 16  P out, C in  -> Q := dC / (dC - dP);  I = C + (P - C) * Q
                            SQI I; vi11 += 1
vi13 == 32  P in,  C out -> I = P + (C - P) * Q  (Q = dP/(dP-dC), from the delay slot)
                            SQI P; SQI I; vi11 += 2
JR vi2
```
All three qwords (position, UV, colour) are interpolated with the same `Q`. **[verified]**

Observed branch mix over the 12,492 calls: both-inside 11,919; both-outside 423; entering 75;
leaving 75. **[verified]**

> `FMAND vi7, vi7` / `FMAND vi13, vi13` read the MAC flags of the FMAC op that wrote the lane in
> question (`Sz` for `vf25.z`, `Sw` for `vf26.w`). A native implementation can just compare the
> two floats against 0 — **but must match the VU's sign convention for `-0.0`**, where the MAC
> sign bit is set and a `< 0` comparison is false. Not exercised by this corpus. **[guess]**

### 4.5 The four shims: `0x0a`, `0x12`, `0x1a`, `0x56`

All four are the same four-instruction idiom — *set the family-B bases and jump into the
family-A kernel's loop*:

| cmd | pc | extra work first | `vi3` | `vi4` | `vi9` | branches to | what that loop is | marking |
|---|---|---|---|---|---|---|---|---|
| `0x0a` | `0x0f08` | `vi4 = 423; XGKICK vi4` | `vi8` | `150` | `vi10` | `0xe10` | `0x08`'s transform + perspective divide | **[verified]** |
| `0x12` | `0x1108` | — | `vi8` | `150` | `vi10` | `0xfa8` | `0x10`'s distance fade | **[verified]** |
| `0x1a` | `0x15b0` | `vf31 = LQ 27(vi0)` | `vi8` | `150` | `vi10` | `0x1460` | `0x18`'s lighting | **[verified]** |
| `0x56` | `0x0640` | — | — | `150` | `vi10` | `0x5e8` | `0x54`'s template fill | **[verified]** |

Literally (`0x0f08`):
```
0f08  vi4 = 423
0f10  XGKICK vi4          ; the NLOOP=0/EOP=1 terminator tag
0f20  vi3 = vi8           ; the clipped polygon, from 0x3618
0f28  vi4 = 150           ; the family-B staging array
0f30  B 0xe10
0f38  vi9 = vi10          ; (delay slot) the clipped vertex count
```
The family-A entries set the same three registers to `vi1+4`, `40`, `ILW.z 2(vi1)` and fall into
the identical loop. So **one kernel implementation serves both families**; only the three
pointers differ. **[verified]**

`0x56`'s target `0x5e8` is the fill loop proper; `0x54`'s prologue (`0x5d8`-`0x5e0`) sets
`vi4 = 40` and `vi9 = ILW.z 2(vi1)`. The loop is:
```
05e8  vf28 = LQ 327(vi0)
0600  vi9 -= 3
0608  SQ vf28 -> 1(vi4) ; 4(vi4) ; 7(vi4)      ; slot +1 (RGBAQ) of three vertices
0620  if (vi9 > 0) goto 0x600
0628  vi4 += 9                                  ; (delay slot)
0630  B 0x1b60
```
It overshoots to the next multiple of 3 — for `vi10 = 4` it writes slots for 6 vertices. That
overshoot lands inside the 150-base array's headroom (`150 + 3*12 = 186`), so it is harmless here;
research/12 §f.4 records the same overshoot reaching qword 245 on the 40 base. **[verified]**

#### Corrections to research/12 §f.4's `0xf90` write-up

The brief lists two known gaps; both are closed here.

*The `vf24`/`vf25` loads are dead.* `LQ vf24, 2(vi4)` (`0xfc8`, `0x1040`) and
`LQ vf25, 5(vi4)` (`0xfd0`, `0x1048`) load the two `XYZF2` staging quads, and `vf24`/`vf25` are
never read anywhere in `0xf90`-`0x1100`. A native version may skip them. **[verified]**

*The full pipelined pair.* Both halves, per iteration (two vertices, `vi3 += 6`, `vi4 += 6`):

```
vf20 = LQ 0(vi3)        vf21 = LQ 3(vi3)        ; the two source positions (float, after 0x68)
vf30 = LQ 0(vi4)        vf31 = LQ 3(vi4)        ; the two staging ST quads
                                                ;   (.w of the ST quad is the clip-space w that
                                                ;    0x08/0x0a stored there)
vf22 = vf20 - vf17      vf23 = vf21 - vf17      ; vf17 = qword 28, the reference point
vf26 = vf22 * vf18      vf27 = vf23 * vf18      ; vf18 = qword 29, the per-axis scale
vf26.w = vf26.x+vf26.y+vf26.z                   ; squared-ish distance term
vf27.w = vf27.x+vf27.y+vf27.z
vf14.w = vf30.w * vf18.w + vf17.w               ; base fog from the clip w
vf15.w = vf31.w * vf18.w + vf17.w
vf14.w = max(min(vf14.w, 255.0), 0)             ; LOI 255, then MAXx.w against vf0.x
vf15.w = max(min(vf15.w, 255.0), 0)
vf28.w = max(min(vf26.w, 1.0), 0)               ; LOI 1.0
vf29.w = max(min(vf27.w, 1.0), 0)
vf14.w *= vf28.w        vf15.w *= vf29.w
SQ.w vf14 -> -4(vi4)    SQ.w vf15 -> -1(vi4)    ; == slot +2 (XYZF2) of each vertex: the F field
```
`IBLTZ vi9, 0x10f8` at `0x10d0` exits after storing only `vf14` when the count is odd; the loop
back-edge is `IBGTZ vi9, 0x1008` at `0x10e8`. **[verified]**

### 4.6 `0x2a` → `0x1a78`, and the shared flush tail `0x1980`

```
0x1a78  vi4 = 113                      ; packet body base
0x1a80  vi5 = ILW.w -1(vi4)            ; == qword 112 .w, the flag 0x1f70 stashed there
0x1a88  vi6 = ILW.w 39(vi0)            ; the global draw gate (0x72 / 0x74)
0x1a90  vi3 = 150                      ; the family-B staging array
0x1a98  vi9 = vi10                     ; the clipped vertex count
0x1aa8  vi6 = vi6 | vi5
0x1ab8  if (vi6 != 0) goto 0x1980      ; else fall through to 0x1ac8: B 0x1b60 (draw nothing)
```
The gate passed on all 961 entries in the corpus (`0x1ac8` count = 0), so the "skip" path is
**[verified]** to exist but never exercised here. **[verified]**

Command `0x2c` (`0x1ad8`, never dispatched in any corpus) is the same flush with `vi3 = 150`,
`vi4 = 113`, `vi9 = 2` and no gate — a fixed two-vertex flush. **[verified]** from the
disassembly.

The tail (`0x1980`-`0x1a70`), with the pipeline unrolled into plain per-vertex form:

```
vf28   = LQ 38(vi0)                     ; (1,1,1,0.5)
ACC    = (0.5, 0.5, 0.5, 0.0)           ; ADDAw.xyz vf28w ; SUBAw.w vf0.w - vf0.w
vf28.w = LQ.w 327(vi0)                  ; the alpha scale (1.0f in the corpus)
vi5    = vi4 - 1                        ; == 112, the GIFtag to kick
for k in 0 .. vi9-1:
    dst = vi4 + 3k ;  src = vi3 + 3k
    SQ (src+0)                       -> dst+0     ; ST     : copied verbatim (still float)
    SQ FTOI0(ACC + (src+1) * vf28)   -> dst+1     ; RGBAQ  : *(1,1,1,aScale) +(0.5,0.5,0.5,0)
    SQ FTOI4(src+2)                  -> dst+2     ; XYZF2  : float -> 12.4 fixed
vi6 = 423 ; XGKICK vi6                  ; the NLOOP=0/EOP=1 terminator tag
XGKICK vi5                              ; the real packet: tag@112 + 3 x vi9 qwords
B 0x1b60
```
The `+0.5` bias applies to R,G,B only (`ACC.w = 0`), then `FTOI0` truncates — i.e. round-to-nearest
on colour, truncate on alpha. `ST` is left as float because the PACKED `ST` descriptor takes
floats (`S`=x, `T`=y, `Q`=z). The real loop is pipelined and over-reads one vertex past the end;
`vi3` ends 3 qwords past where a naive loop would leave it. **[verified]** — `0x19f0` ran 2908
times over 961 entries (mean 3.03 vertices per primitive).

### 4.7 `0x4c` → `0x20c8` — the primitive loop back-edge

```
0x20c8  vi12 -= 1                       ; the primitive counter set by 0x1f78
0x20d0  vi15 = ILW.z 329(vi0)           ; restore the index-list cursor (WRITE, not read)
0x20d8  if (vi12 == 0) goto 0x2100      ; -> B 0x1b40, the E bit: PROGRAM ENDS
0x20e8  vi14 = ILW.y 340(vi14)          ; the loop target from this command's own y field
0x20f0  B 0x1f98                        ; back into 0x02's per-primitive body
```
Reached 1224 times: 782 by dispatch and 442 by `0x1f70`'s two skip branches (320 culled + 122
clipped away). 1185 loops, 39 ends — 39 being exactly the number of dumps whose list contains
`0x02`. **[verified]**

Two things an implementer must get right: `B 0x1f98` re-enters `0x02` **after** its prologue, so
`vi12` and `vi15` are *not* recomputed; and the branch target `vi14` comes from `y` of the `0x4c`
command's qword, not from a fixed offset. **[verified]**

### 4.8 Family C

#### `0x64` → `0x04a8` — kick the render-state packet

```
vi2 = 330 ; XGKICK vi2 ; B 0x1b60
```
Qword 330 is a GIFtag `NLOOP=5, EOP=1, NREG=1, REGS = A+D`, so 6 qwords go to the GS: five GS
register writes uploaded by the EE. In the sampled dumps those are `ALPHA_1`, `TEX1_1`, `TEX0_1`,
`TEST_1`, `CLAMP_1`. **[verified]** for the tag and the count; the specific register set is
per-object data, **[guess]** as a general rule.

#### `0x72` → `0x2268` and `0x74` → `0x2280` — the draw gate

```
0x72:  ISW.w vi0 -> 39(vi0)             ; qword 39.w := 0
0x74:  vi3 = 2 ; ISW.w vi3 -> 39(vi0)   ; qword 39.w := 2
```
Qword `39.w` is OR'd into the visibility test in both `0x1780` (per triangle) and `0x1a78` (per
primitive), so `0x74` forces everything to draw and `0x72` restores per-primitive gating.
**[verified]**

#### `0x30` → `0x22a0` and `0x32` → `0x23b0` — inline state packet + `S/T` rescale + second pass

```
0x22a0  vi3 = 40 ; vi4 = 40 ; vi6 = 752 (= pc 0x1780) ; vi9 = ILW.z 2(vi1)   ; cmd 0x30
0x23b0  vi3 = 150; vi4 = 150; vi6 = 847 (= pc 0x1a78) ; vi9 = vi10           ; cmd 0x32
------- shared body at 0x22c0 -------
        ISW.x vi3 / ISW.y vi4 / ISW.z vi9  -> 339(vi0)     ; save the three pointers
        vi7 = ILW.z 339(vi14)              ; N = the z field of this command's own list qword
outer (0x22e0), N times:
        vi5  = vi14 + 340                  ; the inline block
        vi14 = vi14 + 8                    ; <-- THE vi14 REWRITE
        restore vi3 / vi4 / vi9 from 339
        vi7 -= 1
        XGKICK vi5                         ; the block's GIFtag says how much (NLOOP=6 -> 7 qwords)
        vf30.x = LQ.x 7(vi5)               ; the 8th qword's x: the S/T scale (4.0f observed)
        inner, vi9 times (vi3 += 3, vi4 += 3, in place):
            vf25    = LQ 0(vi3)            ; the staging ST quad
            vf25.xy = vf25.xy * vf30.x     ; scale S and T only; Q and w untouched
            SQ.xy vf25 -> 0(vi4)
0x23a0  JR vi6                             ; 0x1780 for 0x30, 0x1a78 for 0x32
```
**[verified]**. `N` was 1 in all 187 dispatches (`0x22e0` entered 187 for 187 entries), so the
outer loop is **[verified]** to exist but only ever ran once. Because `vi6` is a pc, both
handlers re-run a *draw* handler, giving a second textured pass over the same geometry with
rescaled UVs and new GS state — a detail/lightmap pass. The interpretation is **[guess]**; the
mechanism is **[verified]**.

#### `0x34` → `0x2690` — the 11-qword-block variant

Same skeleton as `0x30` (`vi3 = vi1+4`, `vi4 = 40`, `vi6 = 752`, `vi9 = ILW.z 2(vi1)`,
`ILW.z vi7, 339(vi14)`, `XGKICK vi5`) but `vi14 += 11` and the per-vertex body is much larger: it
reads five VU-only parameter qwords at `6(vi5)`…`10(vi5)`, uses `ERLENG`/`WAITP`/`MFP` (a
reciprocal square root — a normalize), and writes `SQ.xy -> -3(vi4)` (ST) and
`SQ -> -2(vi4)` (RGBAQ). Executed **once** in the entire 48-dump corpus. Enough is known to
recognise it and to skip the right number of list qwords; the maths is **not** documented to
implementation level here. **[partial]**

One latent difference worth recording: `0x2690`'s `vi5 = vi14 + 340` is computed **outside** the
outer loop (whose head is `0x26d8`), so with `N > 1` it would re-kick the same block. `0x30`/
`0x32` recompute `vi5` each iteration. Untested — `N` was 1. **[verified]** from the
disassembly; consequence **[guess]**.

---

## 5. Executed command order

From `dist/vu1_replay.exe --trace` with `PS2X_TRACE_VU_STEPS=4000000`, taking the pc two steps
after every `0x1b90` (`JR vi3`). Full output: `logs/vu1entry0/famBC_order.txt`. **[verified]**

### Family B — `logs/vu1dump4/vu1_prog_141.bin` (32 primitives, 194 dispatches)

```
68  02  then 32 x [ 0a  12  56  1a  2a  4c ]
```
`0x02` runs **once**; `0x4c` loops back to `0x1f98` *inside* `0x02`, so the per-primitive work
re-enters the dispatcher six times per primitive without re-dispatching `0x02`. The static list's
trailing `42` is never dispatched — `0x4c` ends the program itself. **[verified]**

### Family B — `logs/vu1dump4/vu1_prog_134.bin` (35 primitives, 213 dispatches)

```
68  06  02  then 35 x [ 0a  12  56  1a  2a  4c ]
```
**[verified]**. The two smaller B shapes behave the same with a shorter body:
`vu1_prog_32` → `68 06 02` + 21 × `[0a 12 2a 4c]`; `vu1dump3/vu1_prog_13` → `68 06 02` + 5 ×
`[0a 2a 4c]`. **[verified]**

### Family C over B — `logs/vu1dump4/vu1_prog_35.bin` (3 primitives, 27 dispatches)

```
68  06  02  then 3 x [ 0a  64  12  2a  32  72  74  4c ]
```
**`0x32` is the handler that rewrites `vi14`**: entered with `vi14 = 8` (index 8 of the list) it
sets `vi14 = 16`, kicks the inline block at `q348…q354`, rescales `S`/`T` at qwords 150…, and
`JR`s to `0x1a78`, which re-runs the flush (a second `XGKICK 423` + `XGKICK 112`) and hands back.
The dispatcher then reads **q356 = `0x72`**, q357 = `0x74`, q358 = `0x4c` (`y = 3` → back to
index 3, `0x0a`). **[verified]**

### Family C over A — `logs/vu1dump4/vu1_prog_177.bin` (single pass, 10 dispatches)

```
68  06  64  08  10  28  30  72  74  42
```
**`0x30` rewrites `vi14` from 7 to 15**, kicks `q347…q353`, rescales `S`/`T` at qwords 40…, and
`JR`s to `0x1780`, which rebuilds and re-kicks every triangle (a second `XGKICK` per triangle at
`0x1920`). The dispatcher then reads **q355 = `0x72`**, q356 = `0x74`, q357 = `0x42` (END).
**[verified]**

`logs/vu1dump3/vu1_prog_27.bin` is the same shape with `0x34` in place of `0x30`:
`68 06 64 08 10 28 72 34 74 42`, with `0x34` moving `vi14` from 8 to 19. **[verified]**

---

## 6. Live-in / live-out and the hand-back contract

### 6.1 Live-in at `pc 0x1b50` for a family-B/C program

Identical to research/12 §f.3: `vf1`-`vf4` (clip matrix, read by `0x0a`'s kernel at `0xe10`),
`vf5`-`vf7` and `vf9`-`vf12` (light/colour, read by `0x1a`'s kernel at `0x1460`). `vf13`-`vf16`
are read by `0x3618` but the result is dead (§4.4), so they are **not** live. No `vi` register is
live-in. **[verified]** — research/12's perturbation sweep covered all seven list shapes; the
static register scan here agrees.

Lists without `0x0a` do not need `vf1`-`vf4`, and lists without `0x1a` do not need `vf5`-`vf12`;
the minimal B shape `68 06 02 0a 2a 4c 42` needs only `vf1`-`vf4`. **[verified]**

### 6.2 What crosses a `B 0x1b60` inside a family-B list

| register | set by | read by | marking |
|---|---|---|---|
| `vi1` | `XTOP` at `0x1b50`, never rewritten | every handler | **[verified]** |
| `vi14` | the dispatcher (`0x1b70`), rewritten by `0x4c`/`0x30`/`0x32`/`0x34` | the dispatcher | **[verified]** |
| **`vi8`** | `0x3a70` inside `0x3618` — the clipped polygon's base qword | `0x0a` (`0x0f20`), `0x12` (`0x1108`), `0x1a` (`0x15b8`) | **[verified]** |
| **`vi10`** | `0x3a78` inside `0x3618` — the clipped vertex count | `0x0a`, `0x12`, `0x1a`, `0x56`, `0x2a`, `0x32` | **[verified]** |
| **`vi12`** | `0x1f78` — the primitive counter | `0x20c8` | **[verified]** |
| `vi15` | `0x1f70`/`0x1fd0` — the index cursor; mirrored to `329.z` | `0x1f98` body, restored by `0x20c8` | **[verified]** |

Plus VU data memory: qword **112** (the GIFtag, written by `0x02`, kicked by the flush), qwords
**40**/**76** (the clipped polygon, `0x3618` → `0x0a`/`0x12`/`0x1a`), qwords **150…** (the staging
array, `0x0a`/`0x12`/`0x56`/`0x1a` → `0x2a`/`0x32`), qword **39.w** (the draw gate,
`0x72`/`0x74` → `0x1780`/`0x1a78`), qword **329.z** (the saved index cursor).

> **This corrects research/12 §f.3**, which states that `vi12` is "exactly one register" crossing
> the family-B boundary. That is true only for the `0x02` → `0x4c` edge it was analysing;
> `vi8` and `vi10` cross every `0x02` → `0x0a` → `0x12` → `0x56` → `0x1a` → `0x2a` edge, and they
> are set inside `0x3618`, not by `0x02`'s own code. **[verified]** from the disassembly
> (`0x0f20`/`0x0f38`, `0x1108`/`0x1120`, `0x15b8`/`0x15d0`, `0x0650`, `0x1a98`, `0x23d0`).

### 6.3 The hand-back rule for family B and C

A native program may stop only immediately before an `ILW.x vi5, 340(vi14)` read
(`vu.m_state.pc = 0x1b60`) or at program end (`pc = 0x1b50`, ended). For **family A** research/12
allows any command boundary because every handler recomputes its pointers. For **family B/C that
is false**: handing back mid-list requires reproducing `vi8`, `vi10`, `vi12` and `vi15` as well as
`vi1`/`vi14`, plus the whole of qwords 40-111, 112, 150…, 329 and 39.

The safe boundaries remain:

* **the start of the list** (`vi14 = 0`, no `vi` live), and
* **program end**.

A third boundary is safe and useful: **immediately before `0x02` is dispatched** (i.e. after
`0x68` and, where present, `0x06`), because at that point only `vi1`/`vi14` and the `vf` live-in
set matter — `0x1f70` recomputes `vi15`, `vi12`, `vi3` from `vi1`. **[verified]** from the
disassembly. Everything after that, up to the program's `B 0x1b40`, is a single indivisible unit
for hand-back purposes.

For **family C over A** (`68 06 64 08 10 28 30 72 74 42`) every handler is pointer-independent
except `0x30`, which reads `vi14` (for the inline block) and writes it. So a hand-back is safe
anywhere in that list as long as `vi14` is right; `vi9`/`vi3`/`vi4` are re-derived. **[verified]**

---

## 7. Corrections and additions to research/12

| research/12 says | correct statement | marking |
|---|---|---|
| §f.1 row 1: `0x3618` is a "per-primitive clip/transform subroutine; uses `vf13..vf16`" (name **[guess]**) | It is a five-plane Sutherland–Hodgman clipper. It reads `vf13`-`vf16` but the result is dead. | **[verified]** |
| §f.2: "`z`, `w` … no handler in the corpus was observed reading them" | `z` **is** read, by `0x30`/`0x32`/`0x34`, as the inline-block count. `w` is still never read. | **[verified]** |
| §f.3: "`0x1440` and `0x3618` both *write* `vf13..vf16` before use" | `0x1440` writes them; `0x3618` **reads** them and discards the result. | **[verified]** |
| §f.3: family B's boundary needs "exactly one register: `vi12`" | `vi8`, `vi10`, `vi12` (and `vi15`, mirrored in memory) all cross. | **[verified]** |
| §f.4: `0xf90`'s `LQ vf24`/`vf25` shown without comment | They are dead loads; `vf24`/`vf25` are never read in `0xf90`-`0x1100`. | **[verified]** |
| §f.4: `0xf90` pseudocode shows only the `vf14` half | Both halves given in §4.5 above, including `vf30 = LQ 0(vi4)` — the base fog input is the **staging ST quad's `.w`** (the clip-space `w`), not a source-vertex field. | **[verified]** |
| §f.4: `0x68`/`0x0b20` listed as a gap ("the full per-vertex field layout … is still needed") | Closed in §4.1: 3 qwords per vertex, converted **in place**, `ITOF4.xyz`+`ITOF15.w` / `ITOF12.xy`+`ITOF15.zw` / `ITOF0.xyzw`. | **[verified]** |
| §f.4: `0x54`/`0x05d8` listed as a gap | Closed in §4.5 (the loop is transcribed; `0x56` shares it with base 150). | **[verified]** |
| §f.5: the C shapes' last token printed as `?0x8006` | That qword is the GIFtag of an inline GIF packet embedded in the list, not a command. | **[verified]** |
| §f.5: "the ending is **[guess]** (a handler rewrites `vi14`, so the static tail is not the executed tail)" | The handler is `0x32` (C over B) / `0x30` (C over A) / `0x34`; it advances `vi14` by 8 (11 for `0x34`) per inline block. Executed tails in §5. | **[verified]** |
| §f.1: research/12's family-A corpus never dispatched `0x18`'s handler from `0x1a` | In the B/C corpus `0x1440`'s prologue never runs; `0x1460` is entered 539 times, all from `0x1a`. | **[verified]** |

Still open from research/12: `0x18`/`0x1440`'s loop body is transcribed here only as far as
"which registers and which stores" (§4.5 does not expand the four-matrix light combine). That
gap is unchanged.

---

## 8. Open questions

1. **`N > 1` inline blocks.** `0x30`/`0x32`/`0x34` read a block count from their own list qword's
   `z`; it was 1 in all 187 dispatches. A scene with `N > 1` would exercise `0x30`'s outer loop —
   and would hit `0x34`'s stale-`vi5` difference (§4.8). Needs a dump with `z > 1`.
2. **The `0x1a78` gate's false path** (`0x1ac8`) never ran: qword `39.w | 112.w` was always
   non-zero. Needs a scene where `0x72` runs without a later `0x74`, or an index record with
   bit 1 clear while the gate is 0.
3. **`0x34`'s per-vertex maths** (`ERLENG` normalize, five parameter qwords) is not documented to
   implementation level. One sample.
4. **`-0.0` in the clipper's sign tests.** `FMAND` reads the MAC sign bit, which is set for
   `-0.0`; a naive `x < 0.0f` is not equivalent. Not exercised here but a real divergence risk.
5. **Qword 328** is written by entry 0 and read only by command `0x5c` (`0x04f8`), never
   dispatched. Role unknown.
6. **`TOP+2.y`** (`= 1` in every sampled dump) is read by nothing in the executed ranges.
7. **The `0x3618` prologue's dead transform** may not be dead on hardware if the GS or a later
   microprogram revision reads the clip flags; nothing in this image does. Worth re-checking if a
   second VU1 microcode image turns up.

---

## 9. Commands used

```bash
# selection + list grouping (48 of 166 dispatcher dumps are family B/C)
python <select startPc==0x1b50, decode the list at qword 340, classify>   # famBC_dumps.txt

# histogram over the 48
dist/vu1_replay.exe --pchist logs/vu1entry0/famBC_hist.bin <the 48 dumps> \
  > logs/vu1entry0/famBC_replay.txt
python <hist -> ranges split at jump-table targets>                       # famBC_handlers.txt
python <hist -> per-command dispatch counts from the slot pcs>

# disassembly (full_dis.txt is the whole 16 KB image, from research/12 f.7)
python tools_py/vu1dis.py --start 0x3618 --count 8 logs/vu1dump4/vu1_prog_141.bin
python <slice full_dis.txt by pc range>                                   # famBC_dis.txt
#   NOTE: `--raw` makes vu1dis skip the 16-byte dump header, shifting every label by -0x10.
#   Do not mix --raw with a dump file.

# executed order (the default step cap is 1200, far too low)
PS2X_TRACE_VU_STEPS=4000000 dist/vu1_replay.exe --trace logs/vu1dump4/vu1_prog_35.bin
python <pc two steps after each 0x1b90 -> dispatch sequence>              # famBC_order.txt

# list + inline-block decode
python <print qwords 340..363 of the data section>                        # famBC_cmdlists.txt

# is qword 27.x live?  (patch one word of the data section, re-run, compare --state)
dist/vu1_replay.exe --state <orig> <27.x=0> <27.x=0xffffffff>             # famBC_clipmask_test.txt
```

Artifacts: `logs/vu1entry0/famBC_dumps.txt`, `famBC_hist.bin`, `famBC_handlers.txt`,
`famBC_replay.txt`, `famBC_dis.txt`, `famBC_order.txt`, `famBC_cmdlists.txt`,
`famBC_clipmask_test.txt`.
