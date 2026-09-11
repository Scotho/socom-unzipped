# 12 — VU1 entry 0 (the 2D/UI command interpreter) on the title screen

Date: 2026-09-10. Offline analysis only — no game run, no build.

Scope: what VU1 entry point `pc 0` actually does on the title screen, so that it can be
hand-written natively in C++ and verified packet-for-packet against the interpreter.
**Section (f), added as a Task-5 addendum, does the same for the dispatcher at entry
`pc 0x1b50` using the mission dumps — that is the entry the native work is now targeted at,
because entry 0 emits no packets on the title screen (finding 2 below).**
Sources: `logs/vu1dump_title/*.bin` (150 consecutive VU1 program dumps captured on the title
screen), `dist/vu1_replay.exe`, `python tools_py/vu1dis.py`, and the generated translation
`third_party/ps2recomp/ps2xRuntime/src/lib/vu/generated/vu1_d418194495c25213.cpp`.

Row marking follows `docs/research/11-recom-applicability.md`: **[verified]** = checked against a
measurement in this note (histogram, poison sweep, scramble run, or a value that matches the
captured data bit-for-bit); **[guess]** = inference from the disassembly with the verification
step named.

---

## 0. Headline results

1. **Every title-screen VU1 run is entry `pc 0`, executes exactly 82 instruction pairs, produces
   zero GIF packets, and ends on the E bit at `0x1b40` with `pc = 0x1b50`.** All 150 dumps are
   byte-identical in behaviour (75 with `top = 424`, 75 with `top = 724`). **[verified]** —
   `--pchist` shows 82 pairs each executed exactly 150 times, 12300 total.
2. **The title screen does not draw through VU1.** 150 consecutive programs, 0 packets, 0 bytes.
   Whatever puts the title image on screen reaches the GS by another path (PATH2/PATH3 or the
   EE's own GIF writes), not through a VU1 `XGKICK`. **[verified]** (replay output).
3. **The command list is not at qword 340 on the title screen because entry 0 never uploads
   one.** The dispatcher reads command words with `ILW.x vi5, 340(vi14)` at `pc 0x1b60` — so the
   list *is* at absolute data qwords 340, 341, 342 … (`x` word of each), indexed by `vi14` which
   starts at 0 and increments by one per command. Entry 0 is itself the routine that fills that
   area: the loop at `0x458-0x488` copies `header.z` qwords from the VIF input buffer to
   `340++`. On the title screen `header.z == 0`, that loop is skipped, qword 340 stays all
   zeros, and the dispatcher at `0x1b50` is **never entered at all** — the EE `MSCAL`s `pc 0`
   directly and entry 0 always terminates on its own E bit. **[verified]** (disassembly at
   `0x450`, histogram shows no execution at or after `0x1b50`, and `data[340] == 0` in every
   dump).
4. **Entry 0 on the title screen has no live-in registers.** Scrambling `vi1..vi15` and
   `vf1..vf31` in a dump changes nothing about the run: same 82 pairs, same 83 cycles, same end
   pc, same `vf0..vf28` out, same VU-data result hash. Only `top` (via `XTOP`) and VU data
   memory are inputs. **[verified]** — `logs/vu1entry0/state_scramble.txt` vs
   `logs/vu1entry0/state_prog0.txt`.
5. **Entry 0 writes exactly 13 VU data qwords: 0, 1, 2, 3, 30, 31, 32, 33, 34, 35, 36, 327, 328.**
   No others. **[verified]** by a 1024-run poison sweep (poison each qword in turn; a qword whose
   poisoning still yields the baseline post-run data hash is one the program overwrites) — run
   twice, once on the real title dump and once on an all-zero data buffer, both giving the same
   13. See `logs/vu1entry0/poison_state.txt`, `logs/vu1entry0/zpois_state.txt`.
6. **On the title screen those 13 stores are idempotent — VU data memory is unchanged by the
   run.** A "null run" (same dump with the start pc moved to the E-bit pair `0x1b40`, so no store
   executes) reports the same `data=` hash as the full 82-pair run, and consecutive title dumps
   have byte-identical data memory. The title screen is a complete steady state: all 32 `vf`
   registers and all `vi` registers are identical across dumps 0, 12 and 13. **[verified]**

---

## (a) Execution histogram — the ranges entry 0 runs on the title screen

`dist/vu1_replay.exe --pchist logs/vu1entry0/title_hist.bin logs/vu1dump_title/*.bin`
(2048 `uint32`s, one per instruction pair; index = pc/8).

| pc range | pairs | runs each | what it is | command word | XGKICK site |
|---|---|---|---|---|---|
| `0x0000-0x0038` | 8 | 150 | entry-0 prologue: `XTOP`, read the header qword, test flag bit 1 | jump-table entry **0** (`0x1ba0: B 0x0`) — but on the title screen reached by `MSCAL 0` from the EE, not through the table **[verified]** | none |
| `0x0118-0x01d8` | 25 | 150 | flag-bit-0 branch: load the object matrix from `TOP+1..TOP+4`, save `TOP+12/13` to 327/328, start `M_proj × M_obj` | same handler | none |
| `0x0200-0x02a0` | 21 | 150 | finish `M_proj × M_obj` → qwords 0..3; start `M_view × M_obj` | same handler | none |
| `0x02c8-0x0378` | 23 | 150 | finish `M_view × M_obj` (stays in `vf13..vf16`); `M_light × M_obj` → `vf5..vf8`; copy camera/clip-plane block `TOP+5..TOP+11` → qwords 30..36; read `header.y` (= 0) and skip the vertex-copy loop | same handler | none |
| `0x0490-0x04a0` | 3 | 150 | handler epilogue, `B 0x1b40` | same handler | none |
| `0x1b40-0x1b48` | 2 | 150 | the **E bit**: one more pair, then the program ends with `pc = 0x1b50` | — | none |

Not executed on the title screen but part of the same handler (listed so a native version knows
what it must fall back on): `0x40-0x108` (flag bit 1: GIF-template path, **two XGKICKs** — `vi6 =
423` at `0x50` and `vi2 = 330` at `0xf8`), `0x1e0-0x1f8` and `0x2a8-0x2c0` (alternate matrix
source when `header.x != 0`), `0x380-0x3c0` (vertex copy to qword 400++), `0x3c8-0x430` (flag
bit 3: four qwords to 27/38/28/29), `0x438-0x488` (command-list upload to qword 340++).

### The dispatcher (`0x1b50`-`0x1b98`) — not executed on the title screen, but this is what a native handler hands back to

```
1b50: XTOP   vi1                     ; vi1 = TOP & 0x3ff  (VIF double-buffered input base, qwords)
1b58: IADDIU vi14, vi0, 0            ; command index = 0
1b60: ILW.x  vi5, 340(vi14)          ; <-- the command word: data[340 + vi14].x
1b68: IADDIU vi4, vi0, 884           ; 884 pairs * 8 = 0x1ba0 = the jump table
1b70: IADDIU vi14, vi14, 1           ; ++command index
1b80: IADD   vi3, vi5, vi4
1b90: JR     vi3                     ; -> 0x1ba0 + 16*cmd
```

`0x1b60` is the re-entry point that skips `XTOP` (jump-table command 37 and handler `0x4c8`
branch there); `0x1b50` is the full restart (jump-table command 34). **[verified]** from the
disassembly and the generated code (`L_0x1b50`ff.).

Jump table at `0x1ba0`, 61 entries (commands 0..60), each entry two pairs (`B target` + delay).
First entries: 0 → `0x0` (this handler), 1 → `0x1f70`, 2 → `0x2110`, 3 → `0x1638` (backface
cull), 4 → `0xdf8` (transform/divide), 5 → `0xf08`, … 12 → `0x1440` (lighting), 20 → `0x1780`
(build GIF packet + `XGKICK vi2` at `0x1920`), 33 → `0x1b40` (**end program**, E bit), 34 →
`0x1b50` (restart with `XTOP`), 37 → `0x1b60` (next command, no `XTOP`), 44 → `0x4a8`
(`XGKICK 330` then `B 0x1b60`), 52 → `0xb20` (int→float vertices), 60 → `0x2b58`.
The handler names for 3/4/12/20/52 are carried over from
`docs/research/07-render-pipeline-diagnosis.md:123-127` **[string-match to research/07]**; the
table addresses themselves are **[verified]** from the disassembly.

---

## (b) Register roles in entry 0

| register | role | marking |
|---|---|---|
| `vi1` | `XTOP` result — base qword of the VIF double-buffered input block. 424 or 724 on the title screen (`top` alternates every run). Every `*(vi1)` load below is relative to it. | **[verified]** (`L_0x0`: `vi1 = top & 0x3FF`; dumps alternate 0x1a8/0x2d4) |
| `vi5` | **flags**, = `header.w` (`ILW.w 0(vi1)`). Bit 0 → matrix-concat path (`0x140`); bit 1 → GIF-template path (`0x40`, two XGKICKs); bit 3 → the 27/38/28/29 block (`0x3f0`). Title screen: `flags == 1`. Later reused as a store cursor by the two copy loops (`vi5 = 400` at `0x388`, `vi5 = 340` at `0x450`). | **[verified]** (header qword at TOP is `00000000 00000000 00000000 00000001` in all 150 dumps; branch decisions match) |
| `vi3` | `header.x` — selects the alternate matrix source: 0 = use the resident constant matrices at qwords 4..7 / 8..11 / 16..19 / 20..23; non-zero = take them from `vi1+14..vi1+21` instead, and shift the trailing data pointer by `vi3`. Title screen: 0. | **[verified]** (branches at `0x1a0`, `0x268`, `IADD vi7, vi7, vi3` at `0x2c8`; value 0 in every dump) |
| `vi11` | `header.y` — count of qwords to copy from `vi7` to data qword **400++** (loop `0x390-0x3c0`, two qwords per iteration). Title screen: 0, loop skipped. | **[verified]** (`ILW.y vi11, 0(vi1)` at `0x300`; `IADDIU vi5, vi0, 400` at `0x388`) |
| `vi4` | `header.z` — count of qwords to copy from `vi7` to data qword **340++**, i.e. **the command list itself** (loop `0x458-0x488`). Title screen: never read (the path branches out at `0x370`); the header value is 0. | **[verified]** (`ILW.z vi4, 0(vi1)` at `0x3d8`; `IADDIU vi5, vi0, 340` at `0x450`) |
| `vi7` | running source pointer into the input block: `vi1+1`, then `vi1+14`, then `+vi3`, then `+vi11` / `+vi4` as each copy loop consumes its slice. Ends at `vi1+14` on the title screen (`0x1b6` for `top=424`). | **[verified]** (end-state `vi7 = 0x1b6 = 424+14`) |
| `vi8`, `vi9` | scratch for the flag tests (`vi8` = the mask 2/1/8, `vi9` = `vi5 & vi8`); `vi8` is reused as the copy-loop source cursor. `vi8` ends equal to `vi7`. | **[verified]** |
| `vi2` | GIF-packet base **330**, only on the flag-bit-1 path (`IADDIU vi2, vi0, 330` at `0x40`, `XGKICK vi2` at `0xf8`). Untouched on the title path. | **[verified]** (scramble run leaves `vi2` = garbage) |
| `vi6` | GIF-packet base **423**, only on the flag-bit-1 path (`XGKICK vi6` at `0x50`). Untouched on the title path. | **[verified]** (same) |
| `vi10`, `vi12`-`vi15` | never touched by entry 0 on the title screen. `vi14` is the dispatcher's command index; `vi15` is the `BAL` link register used by other handlers. | **[verified]** (scramble run) |
| `vf9`-`vf12` | the projection matrix rows, loaded from data qwords **4..7**; then reloaded at `0x278` with qwords **20..23** (a fourth matrix) and left there. | **[verified]** |
| `vf25`-`vf28` | the view matrix rows, from data qwords **8..11**; then reloaded at `0x308` with `TOP+8..TOP+11` (clip-plane rows) on their way to qwords 33..36. | **[verified]** |
| `vf21`-`vf24` | the light/normal matrix rows, from data qwords **16..19** (or `TOP+14..TOP+17` when `vi3 != 0`). | **[verified]** |
| `vf17`-`vf20` | the object matrix rows, from `TOP+1..TOP+4`. | **[verified]** |
| `vf1`-`vf4` | `M(4..7) × M(TOP+1..TOP+4)` — the composed local→clip matrix. **Stored to data qwords 0..3.** | **[verified]** — recomputing the product in float32 reproduces the captured qwords 0..2 bit-for-bit and qword 3 to within 1 ulp on `z` |
| `vf13`-`vf16` | `M(8..11) × M(TOP+1..TOP+4)` — the composed local→view matrix. **Left in registers, never stored.** | **[verified]** |
| `vf5`-`vf8` | `M(16..19) × M(TOP+1..TOP+4)` — the composed normal/light matrix (`vf8` is just `MOVE vf24`). Left in registers. Note `vf5`/`vf6` are used earlier in the handler for a different purpose (the `TOP+12/13` → 327/328 copy) and then overwritten. | **[verified]** |
| `vf29`-`vf31` | never touched by entry 0. | **[verified]** (scramble run) |
| `ACC`, `MAC`, `status` | left as `bef01fd3,80000000,80000000,00000000` / `mac=087` / `status=0c3` after every title run; deterministic, and dead because the next run's first FMAC is a `MULA` that overwrites `ACC`. | **[verified]** |
| `Q`, `P`, `R`, `I`, `clip` | never written — entry 0 on the title screen contains no `DIV`/`RSQRT`/`EFU`/`RINIT`/clipping op. | **[verified]** (full 82-pair listing in `logs/vu1entry0/entry0_dis.txt`) |

---

## (c) VU data-memory layout as the title screen uses it

All indices are **qwords** (16 bytes) into VU1 data memory; `TOP` is 424 or 724.

**Resident (uploaded once, read by entry 0):**

| qword | contents on the title screen | role | marking |
|---|---|---|---|
| 0..3 | `457,0,0,0 / 0,-457,0,0 / -2048,-2048,280.9,-1 / -1.337e8,-1.336e8,1.858e7,-65214` | **output** of entry 0: composed local→clip matrix | **[verified]** (written; value reproduced by recomputation) |
| 4..7 | `457,0,0,0 / 0,-457,0,0 / -2048,-2048,280.9,-1 / 509111,655360,173396,320` | projection / screen matrix (the `M_proj` source) | **[verified]** as the source; the name is **[guess]** — the `457` / `-2048,-2048` / `320` pattern is a PS2 screen-space projection (half-width 2048, 320-px guard) |
| 8..11 | `1.428,0,0,0 / 0,-1.428,0,0 / 0,0,-1.009,-1 / -457,0,314.8,320` | view/camera matrix (`M_view`) | **[guess]** — same shape, one row of translation; verify by watching it change when the in-game camera moves |
| 12..15 | `320,0,0,0 / 0,448,0,0 / 0,0,-32762.5,0 / 2048,2048,32772.5,1` | the GS viewport scale/offset quad (320 = half of 640, 448 = half of 896 (field-doubled 448-line), 2048/2048 = GS centre, 32762.5/32772.5 = Z range) | **[guess]** — not read by entry 0; verify by matching against the XYOFFSET/Z values in a captured GIF packet |
| 16..19 | `-0.469,-0,-0,0 / 0.7484,-0,-0,0 / -0.469,-0,-0,0 / 0,0,0,1` | light / normal matrix (`M_light`) | **[guess]** — read by entry 0 as a matrix; the values look like three light intensities |
| 20..23 | `0.8,0.8,0.8,0 / 0 / 0 / 0.5569,0.5569,0.5569,0` | ambient/diffuse colour block, loaded into `vf9..vf12` after the projection use | **[guess]** — verify by changing them in a replay and watching the lit colours in a menu dump |
| 24..26 | `0,0,0,255` / `0,0,0,-FLT_MAX` / `00008000 3035c000 00000412 0` | constants: 255 (colour clamp), −max (Z clamp), and a GIF tag | **[guess]** |
| 27, 38, 28, 29 | all zero on the title screen | written only on the flag-bit-3 path from `TOP+1..TOP+4` | **[verified]** as a write target of that path |
| **30** | `320, 0, -65214, 1` | **eye position** — this is the qword research/07 identified as the backface-cull eye (`LQ vf26, 30(vi0)`), and the bug fixed there was this qword holding a guest RAM address | **[verified]** as a write target; the *name* is **[string-match to research/07]** |
| **31** | `320, 0, -65214.2, 1` | second eye position, 1 ulp apart from 30 — probably the previous frame's or the clip-space eye | **[guess]** |
| **32** | `0, 0, -1, 0` | forward / near-plane normal | **[guess]** (unit vector down −Z) |
| **33..36** | `±0.7647,0,-0.6444,0` and `0,±0.8823,-0.4708,0` | the four side frustum-plane normals (left, right, bottom, top) | **[guess]** — they are four unit vectors symmetric in x and y about −z, exactly the shape of a symmetric frustum's side planes; verify by checking `atan` of the ratios against the 320×224 field of view |
| 37, 39..47 | zero | unused on the title screen | **[verified]** |
| **327, 328** | `0,0,0,1` and `000077c0 00008220 000fffe0 0` | **output** of entry 0: copies of `TOP+12` and `TOP+13`. 328 is integer data (a GS register block / GIFtag fragment), not floats | **[verified]** as write targets |
| **330..337** | zero on the title screen | GIF template written and `XGKICK`ed only on the flag-bit-1 path (from `TOP+1..TOP+8`) | **[verified]** as that path's targets |
| **340++** | zero on the title screen | **the command list** the dispatcher reads (`.x` word of each qword). Filled by entry 0's `0x458` loop when `header.z != 0` | **[verified]** |
| **400++** | zero on the title screen | vertex/attribute staging, filled by entry 0's `0x390` loop when `header.y != 0` | **[verified]** |
| **423** | `00008000 10000000 0000000e 0` | a second GIF packet base, `XGKICK`ed at `0x50` on the flag-bit-1 path | **[verified]** as that path's `vi6` |

**Per-run input block at `TOP` (VIF-uploaded, double-buffered 424 / 724):**

| offset | contents on the title screen | role | marking |
|---|---|---|---|
| `TOP+0` | `x=0 y=0 z=0 w=1` | header: `x`=`vi3` matrix-source select, `y`=`vi11` vertex count, `z`=`vi4` command-list length, `w`=`vi5` flags | **[verified]** |
| `TOP+1..+4` | identity, with row 3 = `0,0,65535,1` | object matrix | **[verified]** |
| `TOP+5..+11` | eye / eye2 / forward / 4 plane normals | → qwords 30..36 | **[verified]** (copied verbatim) |
| `TOP+12..+13` | `0,0,0,1` and the integer GS block | → qwords 327, 328 | **[verified]** |
| `TOP+14…` | zero | source for the copy loops / alternate matrices | **[verified]** |

Both double buffers hold byte-identical data on the title screen. **[verified]**

---

## (d) Live-in / live-out

**Live-in (read before written) — the empty set.**
Entry 0 on the title screen reads no `vi` and no `vf` register before writing it. Confirmed by
running a dump with `vi1..vi15` set to pseudo-random values and `vf1..vf31` set to pseudo-random
floats: identical 82 pairs, identical 83 cycles, identical end pc, identical `vf0..vf28`,
identical VU-data hash. The only inputs are `TOP` (through `XTOP`) and VU data memory.
**[verified]** — `logs/vu1entry0/scramble_prog0.bin`, `logs/vu1entry0/state_scramble.txt`.

This is the whole reason entry 0 is a good first native handler: it is a pure function of
`(TOP, VU data memory)`.

**Live-out — what the native version must reproduce exactly:**

| kind | set |
|---|---|
| integer registers written | `vi1` (= `TOP & 0x3ff`), `vi3` (= `header.x`), `vi5` (= `header.w`), `vi7` and `vi8` (= `vi1 + 14` on the title path), `vi9` (= `vi5 & 1`), `vi11` (= `header.y`) |
| integer registers *not* written | `vi2`, `vi4`, `vi6`, `vi10`, `vi12`, `vi13`, `vi14`, `vi15` — a native version must **leave these alone**, not zero them |
| float registers written | `vf1`..`vf28` (all of them). `vf0` is the hardwired `(0,0,0,1)`. `vf29`, `vf30`, `vf31` must be left alone. |
| VU data memory | exactly qwords 0, 1, 2, 3, 30, 31, 32, 33, 34, 35, 36, 327, 328 |
| pipeline state | `ACC = bef01fd3,80000000,80000000,00000000`; `mac = 0x087`; `status = 0x0c3`; `clip`, `Q`, `P`, `R`, `I` untouched |
| GIF | no packet, no `XGKICK` |
| end | `pc = 0x1b50`, program ended (E bit taken at `0x1b40`) |

Because the *next* title run is also entry 0 and has no live-in, none of the live-out registers
are actually consumed on the title screen — but in-game the other handlers read `vf1..vf4`
(clip matrix), `vf13..vf16` (view matrix) and `vf5..vf8` (normal matrix) straight out of the
register file, so a native entry 0 must still set them.

**Constants across runs:** all 32 `vf` registers are bit-identical between dumps 0, 12 and 13
(different `top` values), and all `vi` registers match except `vi1`/`vi7`/`vi8`, which track the
buffer. **[verified]**

---

## (e) Hand-back rule for a native implementation

A native entry 0 may only give control back to the interpreted microprogram at a **dispatcher
boundary** — that is, at a pc where the next thing the microprogram does is read a command word:

* `pc = 0x1b50` (full restart: `XTOP` then read `data[340].x`), or
* `pc = 0x1b60` (next command without re-reading `TOP`; `vi14` must already hold the next command
  index), or
* the program *end* (`0x1b40`'s E bit), which is what entry 0 always reaches on the title screen.

At that point every register in the live-out table above must hold exactly the value the
microprogram would have left, `vu.m_state.pc` must be the dispatcher pc (`0x1b50` for the E-bit
end), and the 13 data qwords must already be written. Anything else in the register file is
scratch and must be left **untouched**, not cleared — the scramble test proves the microprogram
does not touch `vi2/vi4/vi6/vi10/vi12-15` or `vf29-31`, and a native version that zeroes them
would diverge from the interpreter on the very next `--state` comparison.

**Bail rule.** If the native handler meets a header it does not implement (any `flags` bit other
than bit 0, or a non-zero `header.x`, `header.y` or `header.z`), it must bail **before its first
store**, with `pc = 0x0` and no register or memory change, and let the interpreter run the whole
handler. Entry 0 has no side effect before `0x178` (the first `SQ`), so `pc 0x0` is a clean bail
point. It must **not** bail part-way through, because the two `XGKICK`s on the flag-bit-1 path
and the two copy loops are not restartable from the middle.

**Suggested first native target.** Implement only the title-screen path — `flags & 2 == 0`,
`flags & 1 == 1`, `header.x == 0`, `header.y == 0` — which is 82 pairs of straight-line code with
no branches taken inside it, no XGKICK and 13 qword stores. Pseudocode:

```
vi1  = TOP & 0x3ff
vi5  = data[vi1].w            // flags
vi3  = data[vi1].x
if (vi5 & 2) -> bail to interpreter at pc 0
vi9  = vi5 & 1; vi7 = vi1 + 1
if (vi9 == 0) -> bail
vf5  = data[vi1+12]; vf6 = data[vi1+13]
data[327] = vf5;  data[328] = vf6
vf17..vf20 = data[vi1+1 .. vi1+4]         // object matrix
if (vi3 != 0) -> bail
vi7  = vi1 + 14
vf9..vf12  = data[4..7]                   // projection
vf21..vf24 = data[16..19]                 // light/normal
vf25..vf28 = data[8..11]                  // view
vf1..vf4   = M(vf9..vf12)  x (vf17..vf20) ; data[0..3] = vf1..vf4
vf9..vf12  = data[20..23]                 // reloaded, left live
vf13..vf16 = M(vf25..vf28) x (vf17..vf20) // left in registers
vi7  = vi7 + vi3
vf6,vf7,vf8   = data[vi1+5], data[vi1+6], data[vi1+7]
vi11 = data[vi1].y
vf28,vf27,vf26,vf25 = data[vi1+8 .. vi1+11]
vf5..vf8   = M(vf21..vf24) x (vf17..vf20) ; vf8 = vf24 (MOVE)
data[33] = vf28(old); data[30] = vf6(old); data[31] = vf7(old); data[32] = vf8(old)
data[34] = vf27; data[35] = vf26; data[36] = vf25
if (vi11 != 0) -> bail
vi8 = vi7
end program: pc = 0x1b50
```

Note the ordering hazard the last block encodes: the stores at `0x328-0x358` use the *loaded*
`vf6/vf7/vf8` from `TOP+5..TOP+7`, while the FMAC results that also land in `vf5/vf6/vf7` are
written by the same instruction pairs. The native version must snapshot the loaded values before
computing the light matrix. **[verified]** — the resulting qwords 30..32 match `TOP+5..TOP+7`
bit-for-bit in the captured dumps.

Matrix concatenation is the PS2 `MULAx / MADDAy / MADDAz / MADDw` chain — a column-combination,
`row_i(out) = M[0]*v_i.x + M[1]*v_i.y + M[2]*v_i.z + M[3]*v_i.w`, with VU float semantics
(round-toward-zero, denormals flushed, no NaN/Inf) and rounding applied after **each** step of
the chain, not one fused multiply-add. Recomputing it with double-precision FMA reproduces
qwords 0..2 exactly and misses qword 3's `z` by 1 ulp (`4b8dc09f` vs the captured `4b8dc09e`),
which is exactly the kind of divergence Task 7's packet comparison will catch: implement the
chain step by step in float32, not as a dot product.

---

## Open questions / what would verify the guesses

1. **Names for qwords 8..11, 16..23 and 12..15.** All are read (or merely resident) on the title
   screen with plausible but unconfirmed roles. Verify by capturing dumps on a screen where the
   camera moves (in-game) and watching which qwords change per frame, and by matching qwords
   12..15 against the XYOFFSET/Z fields of a captured GIF packet (`tools_py/gif_packets.py`).
2. **Qwords 33..36 as frustum planes.** Verify by computing `atan2` of the components against the
   game's field of view, or by moving the camera and checking they stay unit-length and
   symmetric.
3. **Why the title screen renders at all, given zero VU1 packets.** Worth a separate probe: dump
   GIF PATH2/PATH3 traffic on the title screen. If the title image is EE-driven, the native-VU1
   work will not change the title screen's appearance at all, and the first visible payoff is
   the menu / in-game screens.
4. **`vu1_replay --state`'s `data=` hash is not a plain FNV-1a of the dump's 16 KB data
   section.** Independently hashing those bytes gives `e1cbd81b26386243` for `vu1_prog_0.bin`
   while the tool reports `d49e58f799975c95` for a run that provably changes nothing (the
   null-run test above). The hash is still a deterministic function of the post-run data — the
   poison sweep depends only on that, and it is internally consistent — but **Task 2's `--regs`
   comparison must not assume the `data=` field can be reproduced offline**; compare
   tool-hash to tool-hash, or add a `--dumpdata <file>` flag to the tool so the post-run buffer
   can be diffed directly. Reproduce with:
   `python -c "...fnv1a(open('logs/vu1dump_title/vu1_prog_0.bin','rb').read()[16400:32784])..."`
   vs `dist/vu1_replay.exe --state logs/vu1dump_title/vu1_prog_0.bin`.
5. **The flag-bit-1 path emits a 20-byte GIF packet** (seen when the header qword is poisoned:
   `packets=1 bytes=20`). Its content is not decoded here; decode it before implementing that
   path natively.

## Commands used

```bash
mkdir -p logs/vu1entry0
dist/vu1_replay.exe --pchist logs/vu1entry0/title_hist.bin logs/vu1dump_title/*.bin \
  > logs/vu1entry0/title_replay.txt
python tools_py/vu1dis.py --start 0x0    --count 160 logs/vu1dump_title/vu1_prog_0.bin \
  > logs/vu1entry0/entry0_dis.txt
python tools_py/vu1dis.py --start 0x1b30 --count 12  logs/vu1dump_title/vu1_prog_0.bin   # dispatcher
python tools_py/vu1dis.py --start 0x1ba0 --count 120 logs/vu1dump_title/vu1_prog_0.bin   # jump table
dist/vu1_replay.exe --state logs/vu1dump_title/vu1_prog_0.bin > logs/vu1entry0/state_prog0.txt
dist/vu1_replay.exe --trace logs/vu1dump_title/vu1_prog_0.bin   # 82-step pc trace, ended=1
# scramble test (no live-in) and the 1024-qword poison sweeps: see logs/vu1entry0/
```

---

# (f) The dispatcher at entry `pc 0x1b50` — the mission-screen entry point

Added 2026-09-10 as a Task-5 addendum: the native-program work is being retargeted from entry 0
to `0x1b50`, because entry 0 turned out to emit no packets on the title screen.

Corpus: every dump whose header `startPc == 0x1b50` — **83 of 300 in `logs/vu1dump4`**, 52 of 300
in `logs/vu1dump3`, 31 of 150 in `logs/vu1dump2`, 166 in total. The selected list, with each
dump's `top`/`itop` and its microcode FNV, is `logs/vu1entry0/dispatch_dumps.txt`. All 166 run the
same 16 KB image as the title dumps (code FNV `9ecdd7bedda54489`), all have `itop = 0` and
`top ∈ {424, 724}`, all end at `pc = 0x1b50`. The measurements below use the 83 `vu1dump4` dumps.
**[verified]**

Every one of these runs *does* emit GIF packets (4 to 105 per program, 656 to 7140 bytes), unlike
entry 0 on the title screen. **[verified]** (`logs/vu1entry0/dispatch4_replay.txt`)

## f.0 — The command-word encoding (correction to §(a))

`JR vi3` jumps to pair address `vi3`, i.e. byte pc `vi3 * 8`. With `vi3 = vi5 + 884` the handler
pc is `0x1ba0 + 8 * cmd`, and because each jump-table slot is a `B`+delay pair (16 bytes), **the
command word stored in the list is twice the slot index and is always even**. Every command word
observed in the dumps is even, which is the confirming check. So: slot *n* of the table is
selected by command word `2n`. §(a) named slots; this section names command words.
**[verified]**

## f.1 — Execution histogram, 83 dispatcher dumps

`dist/vu1_replay.exe --pchist logs/vu1entry0/dispatch4_hist.bin <the 83 dumps>`
→ 722 distinct instruction pairs executed, 1,020,981 pair-executions.
Contiguous ranges split at jump-table targets (`logs/vu1entry0/dispatch4_handlers.txt`), in
execution-frequency order. "entered" is the count at the range's first pc; for a jump-table
handler that equals its dispatch count.

| rank | pc range | pairs | pair-execs | entered | command word | what it is | marking |
|---|---|---|---|---|---|---|---|
| 1 | `0x3618-0x3d20` | 226 | 549,555 | 760 | — (`BAL vi15` from `0x2070`) | per-primitive clip/transform subroutine; uses `vf13..vf16`; contains the inner `BAL 0x3ad0` / `BAL 0x3a90` helpers. 54 % of all VU1 work in this corpus. | **[verified]** range+counts; name **[guess]** |
| 2 | `0x0f90-0x1100` | 47 | 77,896 | 50 | **`0x10`** | per-vertex distance fade → writes only the `w` lane of the staging quads | **[verified]** (disassembly below) |
| 3 | `0x0df8-0x0f00` | 34 | 58,356 | 50 | **`0x08`** | transform by the clip matrix + perspective divide (research/07's "transform/divide") | **[verified]** |
| 4 | `0x1440-0x15a8` | 46 | 55,512 | 46 | **`0x18`** | lighting (research/07) — reads `vf9..vf11` and qword 27 | **[string-match to research/07]**, prologue **[verified]** |
| 5 | `0x1980-0x1a70` | 31 | 47,825 | 935 | — (`B 0x1980` from `0x1b30`) | shared packet-flush tail; contains `XGKICK vi6` at `0x1a48` and `XGKICK vi5` at `0x1a58` | **[verified]** range; name **[guess]** |
| 6 | `0x1b60-0x1b98` | 8 | 42,200 | **5275** | `0x4a` | **the dispatcher body itself** — 5275 commands over 83 programs = 63.6 commands per program | **[verified]** |
| 7 | `0x1780-0x1960` | 61 | 41,046 | 54 | **`0x28`** | triangle assembly → GIF packet → `XGKICK vi2` at `0x1920` | **[verified]** |
| 8 | `0x1f70-0x20c0` | 43 | 32,217 | 33 | **`0x02`** | world-object setup; `BAL vi15, 0x3618` at `0x2070`; hands back with `B 0x1b60` between primitives | **[verified]** |
| 9 | `0x0b20-0x0c58` | 40 | 29,758 | **83** | **`0x68`** | int→float vertex unpack — **the first command of every list in the corpus** | **[verified]** |
| 10 | `0x1638-0x1768` | 39 | 21,916 | 33 | **`0x06`** | backface cull (research/07); reads the eye at qword 30 | **[verified]** prologue |
| 11 | `0x22a0-0x23a8` | 34 | 11,962 | 4 | `0x30` | — | **[guess]** |
| 12 | `0x1a78-0x1ac0` | 10 | 9,350 | 756 | `0x2a` | packet flush / kick | **[guess]** |
| 13 | `0x05d8-0x0638` | 13 | 9,077 | 46 | **`0x54`** | template fill: broadcast qword **327** into the middle quad of every vertex slot | **[verified]** |
| 14 | `0x20c8-0x2108` | 9 | 7,527 | 1080 | **`0x4c`** | the per-primitive **loop back-edge**: `vi14 = data[340+vi14].y`, `B 0x1f98`; when the count runs out, `B 0x1b40` (END) | **[verified]** |
| 15 | `0x0f08-0x0f38` | 7 | 5,292 | 756 | `0x0a` | `vi4 = 423; XGKICK vi4` at `0x0f10` | **[verified]** |
| 16 | `0x1108-0x1120` | 4 | 3,024 | 756 | `0x12` | — | **[guess]** |
| 17 | `0x15b0-0x15d0` | 5 | 2,695 | 539 | `0x1a` | — | **[guess]** |
| 18 | `0x0640-0x0650` | 3 | 1,617 | 539 | `0x56` | template fill with base qword **150** instead of 40 (`B 0x5e8`) | **[verified]** |
| 19 | `0x04a8-0x04d0` | 6 | 1,098 | 183 | `0x64` | `vi2 = 330; XGKICK vi2; B 0x1b60` | **[verified]** |
| 20 | `0x23b0-0x23d0` | 5 | 895 | 179 | `0x32` | — | **[guess]** |
| 21 | `0x2280-0x2298` | 4 | 732 | 183 | `0x74` | — | **[guess]** |
| 22 | `0x2268-0x2278` | 3 | 549 | 183 | `0x72` | — | **[guess]** |
| 23 | `0x1b50-0x1b58` | 2 | 166 | 83 | `0x44` | the `XTOP` half of the dispatcher — runs exactly once per program | **[verified]** |
| 24 | `0x1b40-0x1b48` | 2 | 166 | 83 | `0x42` | the E-bit end — runs exactly once per program | **[verified]** |

Per-command dispatch counts are in `logs/vu1entry0/dispatch4_cmds.txt`. 41 of the 61 table slots
are never used by this corpus, including **command word `0x00` — entry 0 is never reached through
the command list**; the EE only ever gets there with `MSCAL 0`. **[verified]**

Active XGKICK sites in this corpus (`count` = times the `XGKICK` pair executed):
`0x04b8` (cmd `0x64`) 183, `0x0f10` (cmd `0x0a`) 756, `0x1920` (cmd `0x28`) 858,
`0x1a48` 935, `0x1a58` 935, `0x2310` 183. The two entry-0 XGKICKs (`0x50`, `0xf8`) never
fire here. **[verified]**

## f.2 — The command list at qword 340

**Format.** One command per qword, read by `ILW.x vi5, 340(vi14)` with `vi14` starting at 0 and
incremented by 1 at `0x1b70`. Only the low 16 bits of the `x` word reach `vi5` (it is a 16-bit
integer register), so the encoding per qword is:

| word | meaning | marking |
|---|---|---|
| `x` (low 16 bits) | **command word** = 2 × jump-table slot; handler pc = `0x1ba0 + 8*x` | **[verified]** |
| `x` (high 16 bits) | ignored by the dispatcher (a non-zero upper half appears in some lists, e.g. `0x0005000c`) | **[verified]** |
| `y` | **branch target**: the command index that `0x20e8` (`ILW.y vi14, 340(vi14)`, command `0x4c`) loads to loop the list. Otherwise unused. | **[verified]** |
| `z`, `w` | per-command parameters (seen as small integers and `1.0f`); not read by the dispatcher | **[guess]** — no handler in the corpus was observed reading them; verify by poisoning `z`/`w` of one command qword |

**Terminator:** command word `0x42` → `0x1b40` → the E bit → program ends with `pc = 0x1b50`.
A list can also end implicitly when a handler branches to `0x1b40` itself (command `0x4c` does
this when its primitive counter reaches 0): over the 83 dumps the E bit ran 83 times while
command `0x42` was dispatched only 50 times. **[verified]**

**Length.** The list is uploaded by entry 0's loop at `0x458-0x488`, length `header.z` qwords of
the entry-0 input block (§(a)). In these dumps entry 0 has already run, so the list is resident;
qwords past the terminator hold stale content from a longer earlier list and must not be parsed.
**[verified]**

**Decoded, dump `logs/vu1dump4/vu1_prog_4.bin` (`top = 724`)** — a UI-quad list:

```
 [0] q340 cmd=0x68 -> 0x0b20  int->float vertices        y=0 z=1 w=0
 [1] q341 cmd=0x06 -> 0x1638  backface cull              y=0 z=1 w=0
 [2] q342 cmd=0x08 -> 0x0df8  transform + perspective    y=0 z=1 w=0
 [3] q343 cmd=0x10 -> 0x0f90  per-vertex distance fade   y=2 z=1 w=1.0f
 [4] q344 cmd=0x54 -> 0x05d8  template fill from q327    y=2 z=1 w=1.0f
 [5] q345 cmd=0x18 -> 0x1440  lighting                   y=2 z=1 w=1.0f
 [6] q346 cmd=0x28 -> 0x1780  triangles -> GIF -> XGKICK y=2 z=1 w=0
 [7] q347 cmd=0x42 -> 0x1b40  END (E bit)                y=2 z=1 w=0
```

**Decoded, dump `logs/vu1dump4/vu1_prog_141.bin` (`top = 424`)** — a world-object list:

```
 [0] q340 cmd=0x68 -> 0x0b20  int->float vertices
 [1] q341 cmd=0x02 -> 0x1f70  object setup; BAL 0x3618 per primitive
 [2] q342 cmd=0x0a -> 0x0f08  XGKICK qword 423
 [3] q343 cmd=0x12 -> 0x1108  (unnamed)
 [4] q344 cmd=0x56 -> 0x0640  template fill, base qword 150
 [5] q345 cmd=0x1a -> 0x15b0  (unnamed)
 [6] q346 cmd=0x2a -> 0x1a78  packet flush / kick
 [7] q347 cmd=0x4c -> 0x20c8  loop back  (vi14 <- q(340+vi14).y) or END
 [8] q348 cmd=0x42 -> 0x1b40  END (E bit)
```

Full decode for both: `logs/vu1entry0/dispatch4_cmdlist_decode.txt`.

## f.3 — Live-in at `0x1b50`, and the live set at a re-entry

**Live-in at program entry (`pc 0x1b50`): `vf1`-`vf7` and `vf9`-`vf12`. No `vi` register is
live-in, and `vf8`, `vf13`-`vf16`, `vf17`-`vf31` are not.** **[verified]** by a per-register
perturbation sweep: for each of `vi1..vi15` and `vf1..vf31` in turn, one dump was rewritten with
that register replaced by a pseudo-random value and re-run; only the eleven registers above
change the emitted packets. Packet count, packet bytes, cycle count and end pc never changed for
*any* register — control flow in this microprogram is entirely register-independent at entry.
Sweep run on seven dumps covering all seven list shapes; the union is the set above
(individual lists use a subset: the two C-family lists only read `vf1..vf4`).

This is exactly the register set **entry 0 leaves behind**, and it is the reason entry 0 must
still be executed (or emulated) before a dispatcher run:

| register | produced by entry 0 as | consumed here by |
|---|---|---|
| `vf1`-`vf4` | `M(q4..q7) × M(TOP+1..TOP+4)` — the local→clip matrix | command `0x08` (`0xdf8`), the transform inner loop |
| `vf5`-`vf7` | `M(q16..q19) × M(TOP+1..TOP+4)` — the normal/light matrix | lighting and the `0x3618` subroutine |
| `vf9`-`vf12` | reloaded by entry 0 from data qwords **20..23** (the colour block) | lighting (`0x1440`: `MULy vf13, vf9, vf31y` …) |

`vf13`-`vf16` (entry 0's local→view matrix) are **not** live-in at `0x1b50` — `0x3618` recomputes
them. **[verified]** (perturbing `vf13..vf16` changes nothing.)

**The live set at a dispatcher re-entry (`0x1b60`) is not fixed.** Every handler is re-entered
from `0x1b60` with at least:

* `vi1` — the `XTOP` base, set once at `0x1b50` and never rewritten; **every** handler re-derives
  its pointers from it (`vi3 = vi1 + 4`, `vi9 = ILW.z 2(vi1)`, …). **[verified]** across
  `0xb20`, `0xdf8`, `0xf90`, `0x5d8`, `0x1440`, `0x1638`, `0x1780`, `0x1f70`.
* `vi14` — the command index, incremented at `0x1b70` and rewritten by command `0x4c`.
* the eleven live-in `vf` registers above, which no family-A handler clobbers.
* everything a later handler reads out of VU data memory (f.4).

Beyond that, **family A's handlers are mutually independent** — each recomputes every pointer it
needs — so a native implementation may hand back between any two of them with only `vi1`,
`vi14` and the `vf` set correct. **Family B's `0x02`/`0x4c` pair is not**: `0x1f70` leaves
`vi12` (primitive counter), `vi15` (index-list pointer) and `vi5/vi6/vi7` (the three vertex
indices) live across its `B 0x1b60`, and `0x20c8` reads them. **[verified]** from the
disassembly at `0x1f70`, `0x2060-0x2108`.

**Hand-back rule for `0x1b50` (extends §(e)).** A native program may stop only immediately before
a `ILW.x vi5, 340(vi14)` read, i.e. with `vu.m_state.pc = 0x1b60` and `vi1`/`vi14` set as the
microprogram would have them, or at the program end (`pc = 0x1b50`, ended). Handing back at
`0x1b60` in the middle of a **family-B** list additionally requires reproducing `vi12`, `vi15`
and `vi5/vi6/vi7`; the safe boundaries there are the start of the list (`vi14 = 0`) and the
program end. Registers the microprogram does not write must be left untouched, not zeroed.

## f.4 — The two most-executed handlers, in implementation detail

Both are per-vertex loops over the same staging array. Their shared conventions, all read from
the VIF input block at `vi1 = TOP`:

| location | field | marking |
|---|---|---|
| `TOP+1` | **GIFtag template** for this list. In the corpus: `00008044 303dc000 00000412 00000000` = EOP=1, NLOOP=0x44, NREG=3, REGS = `ST, RGBAQ, XYZF2`. Command `0x28` copies it to qwords 290 and 300 and patches NLOOP to 3. | **[verified]** |
| `TOP+2.x` | byte offset (in qwords, added to `vi1`) of the **triangle index list** | **[verified]** |
| `TOP+2.z` | **vertex count** (`0x44` = 68 in both sampled dumps) — read by `0x0b20`, `0x0df8`, `0x0f90`, `0x05d8`, `0x1440` as `ILW.z 2(vi1)` | **[verified]** |
| `TOP+2.w` | **triangle/primitive count** (`0x2a` = 42, `0x2c` = 44) — read by `0x1638`, `0x1780`, `0x1f70` as `ILW.w 2(vi1)` | **[verified]** |
| `TOP+3` | position bias added by `0x0b20` (`0,0,0,1` in the corpus) | **[verified]** |
| `TOP+4 …` | raw vertex records, 6 qwords per vertex for `0x0b20`'s integer form | **[verified]** |
| qwords **40 … 40+3N-1** | **the staging array**: 3 qwords per vertex — `[0]` = position/misc, `[1]` = colour/ST template, `[2]` = transformed XY + fog | **[verified]** by the poison sweep: qwords **40-243** (68 vertices × 3 = 204) plus the fill-loop overshoot at **245** are exactly the qwords the program overwrites |
| qwords **290-299** and **300-309** | the two ping-pong GIF packet buffers (10 qwords: tag + 3 vertices × 3 regs). Their base addresses live in qword **329** (`x` = 300, `y` = 290) and are swapped per triangle. | **[verified]** (poison sweep marks 290-309 as written; `0x17e0`/`0x17e8` read `329.x`/`329.y`) |

Poison sweep on `logs/vu1dump4/vu1_prog_5.bin` (`logs/vu1entry0/dispatch4_poison_prog5.txt`):
**written** = qwords 40-243, 245, 290-309; **read** (poisoning changes the packets) = 27-30, 38,
327, 329, 340-347 (the command list), 425-428 (`TOP+1..TOP+4`) and the vertex/index data above
440. Note `TOP+0` is *not* read by these lists. **[verified]**

### Command `0x08` → `0xdf8` — transform by the clip matrix + perspective divide

```
vi3 = vi1 + 4                 ; source vertex pointer, stride 3 qwords
vi4 = 40                      ; staging base,          stride 3 qwords
vi9 = ILW.z 2(vi1)            ; vertex count
loop (0xea0..0xee8), once per vertex, vi9--:
    vf20  = LQ 0(vi3)                       ; object-space position
    vf27  = vf1*vf20.x + vf2*vf20.y + vf3*vf20.z + vf4*vf0.w   ; <-- live-in clip matrix
    DIV Q, vf0.w, vf27.w                    ; 1/w   (the only divide in the handler)
    vf17  = vf0 + Q      (xyz)              ; perspective divide
    vf30  = LQ.xy -2(vi3)                   ; the per-vertex extra words
    vf31.w = vf0.w * vf29.w ; vf26 = vf29*vf17 ; vf31.xyz = vf30 * vf17.x
    SQ vf31 -> 40+3k+0 ;  SQ vf24 -> 40+3k+1 ;  SQ vf26 -> 40+3k+2
    vi3 += 3 ; vi4 += 3
B 0x1b60                      ; hand back to the dispatcher
```
`LOI 254 (437e0000)` at `0x0e40` supplies the 254.0 clamp constant. The loop is software-pipelined
two vertices deep (the `LQ` for vertex *k+1* issues in vertex *k*'s slots), so a native version
that processes one vertex at a time is fine as long as the arithmetic order per vertex is kept.
**[verified]** from the disassembly; 34 pairs, 1167 pair-executions per dispatch.

### Command `0x10` → `0xf90` — per-vertex distance fade (writes only the `w` lane)

```
vi9 = ILW.z 2(vi1)            ; vertex count
vi3 = vi1 + 4                 ; source vertex pointer
vi4 = 40                      ; staging base
vf17 = LQ 28(vi0)             ; reference point   (written by entry 0's flag-bit-3 path)
vf18 = LQ 29(vi0)             ; per-axis scale
loop (0x1008..0x10e8), TWO vertices per iteration, vi9 -= 2:
    vf22 = vf20 - vf17 ; vf23 = vf21 - vf17           ; delta from the reference point
    vf26 = vf22 * vf18 ; vf27 = vf23 * vf18           ; scale
    vf26.w = vf26.x + vf26.y + vf26.z                 ; MULAx.w/MADDAy.w/MADDz.w against vf0
    vf14.w = vf30.w * vf18.w + vf17.w                 ; base alpha
    vf14.w = min(vf14.w, 255.0) ; max(.,0)            ; LOI 255 then MAXx.w vf0
    vf26.w = min(vf26.w, 1.0)   ; max(.,0)            ; LOI 1.0
    vf14.w = vf14.w * vf28.w                          ; alpha * fade
    SQ.w vf14 -> (staging quad -4) ; SQ.w vf15 -> (staging quad -1)
    vi3 += 6 ; vi4 += 6
B 0x1b60
```
It touches **only the `w` component** of two staging quads per iteration — `SQ.w`, not `SQ.xyzw` —
so a native version must do a masked store. Odd vertex counts exit through the `IBLTZ vi9,
0x10f8` at `0x10d0` after storing only the first of the pair. **[verified]**; 47 pairs, 1558
pair-executions per dispatch — the single most expensive jump-table handler in the corpus.

### The GIF packet template (command `0x28` → `0x1780`, `XGKICK` at `0x1920`)

Worth recording here because it is the only place the dispatcher corpus writes to the GS from a
UI-quad list:

```
vf20 = LQ 38(vi0)             ; (1,1,1,0.5) -- the fixed-point rounding bias
vf19 = LQ 1(vi1)              ; the GIFtag template from TOP+1
vi4  = ILW.x 2(vi1) + vi1     ; triangle index list
vi13 = ILW.w 2(vi1)           ; triangle count
SQ vf19 -> 290 ; SQ vf19 -> 300 ; ISW.x 0x8003 -> 290 and 300    ; EOP=1, NLOOP=3
vi2 = ILW.x 329(vi0) (=300) ; vi8 = ILW.y 329(vi0) (=290)
per triangle:
    vi5,vi6,vi7 = ILW.x/y/z 0(vi4)        ; the three vertex indices (qword offsets, stride 3)
    vi12        = ILW.w 0(vi4)            ; flags: bit0 = visible (set by the cull handler),
                                          ;        bit1 OR ILW.w 39(vi0) = second gate
    if either gate is clear -> skip to 0x1930
    for each vertex n in (vi5, vi6, vi7):
        vf17 = LQ 40(vin)   ; ST      -> SQ 1/4/7(vi2)
        vf18 = LQ 41(vin)   ; RGBAQ   -> MADD by vf20 + FTOI0  -> SQ 2/5/8(vi2)
        vf19 = LQ 42(vin)   ; XYZF2   -> FTOI4                 -> SQ 3/6/9(vi2)
    XGKICK vi2                            ; 10 qwords: tag + 3 x (ST, RGBAQ, XYZF2)
    swap vi2 <-> vi8                      ; ping-pong 300 <-> 290
    vi4 += 2 ; vi13--
```
One `XGKICK` **per triangle**, which is why `0x1920` fired 858 times over 83 dumps while command
`0x28` was dispatched only 50 times. **[verified]**

## f.5 — UI-quad lists versus world-object lists

Grouping all 83 `vu1dump4` dispatcher dumps by their literal list content
(`logs/vu1entry0/dispatch4_lists.txt`) gives exactly seven shapes in **two families plus a
third, shorter one**:

| dumps | command list | family | marking |
|---|---|---|---|
| 39 | `68 08 10 54 18 28 42` | **A — UI quad / 2D**: unpack → transform+divide → fade → template fill → light → triangles+XGKICK → END. This is research/07's UI-quad chain. | **[verified]** |
| 7 | `68 06 08 10 54 18 28 42` | A, with backface cull inserted | **[verified]** |
| 12 | `68 06 02 0a 12 56 1a 2a 4c 42` | **B — world object / 3D**: unpack → cull → object setup (`BAL 0x3618`) → kick 423 → … → loop → END | **[verified]** |
| 11 | `68 02 0a 12 56 1a 2a 4c 42` | B, without cull | **[verified]** |
| 2 | `68 06 02 0a 12 2a 4c 42` | B, without the template fill | **[verified]** |
| 8 | `68 06 02 0a 64 12 2a 32 …` | **C**: like B but with `0x64` (`XGKICK 330`) and ending through `0x32` (`0x23b0`) rather than a literal `0x42` | **[verified]** as list content; the ending is **[guess]** (a handler rewrites `vi14`, so the static tail is not the executed tail) |
| 4 | `68 06 64 08 10 28 30 …` | C variant | **[verified]** as content |

So a **UI-quad list never uses commands `0x02`/`0x0a`/`0x12`/`0x1a`/`0x2a`/`0x4c` and never enters
`0x3618`**, while a world-object list never uses `0x08`/`0x10`/`0x54`/`0x18`/`0x28`. The single
command common to every list in the corpus is `0x68` (int→float unpack). **[verified]**

Because commands `0x4c`/`0x32` rewrite `vi14`, a purely linear read of the list is the *static*
content, not necessarily the executed order; the dispatch counts in f.1 are the ground truth for
what actually ran. **[verified]**

## f.6 — Tool caveat (applies to §(d) and to Task 2's comparison)

`vu1_replay --state`'s `data=` field is **not** reproducible offline as FNV-1a over the dump's
16 KB data section. For `logs/vu1dump_title/vu1_prog_0.bin` an independent FNV-1a of bytes
`[16400:32784]` gives `e1cbd81b26386243`, while the tool reports `d49e58f799975c95` for a run
that provably changes nothing (start the same dump at `0x1b40`, the E-bit pair: 2 pairs, no
store, same `data=`). The field is still a deterministic function of the post-run buffer — every
differential result in this note (the poison sweeps, the null-run comparison) depends only on
that, and they are internally consistent — but a harness must compare tool-hash to tool-hash and
must not reconstruct the expected value itself. The clean fix is a `--dumpdata <file>` flag on
the tool so the post-run 16 KB can be diffed directly; that would also make the poison sweeps
here unnecessary.

## f.7 — Commands used for §(f)

```bash
python <select startPc==0x1b50 dumps>            # -> logs/vu1entry0/dispatch_dumps.txt (166)
dist/vu1_replay.exe --pchist logs/vu1entry0/dispatch4_hist.bin <the 83 vu1dump4 dumps> \
  > logs/vu1entry0/dispatch4_replay.txt
python <histogram -> ranges split at jump-table targets>   # dispatch4_handlers.txt
python <per-command dispatch counts>                       # dispatch4_cmds.txt
python <list decode / grouping>                            # dispatch4_lists.txt, dispatch4_cmdlist_decode.txt
python tools_py/vu1dis.py --start 0x0 --count 2048 logs/vu1dump_title/vu1_prog_0.bin \
  > logs/vu1entry0/full_dis.txt                            # whole-image listing used for every handler
# per-register live-in sweep (46 perturbed dumps per source dump, 7 source dumps)
# 1024-qword poison sweep on logs/vu1dump4/vu1_prog_5.bin  # dispatch4_poison_prog5.txt
```
