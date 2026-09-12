# 15 — VU1 dispatcher: the fourth command family (`0x70`/`0x52`/`0x66`/`0x40`) and `0x34`

Sprint 3, Task 6. Research only — no code was written or changed for this note.

Companion to research/12 §(f) (the dispatcher at entry pc `0x1b50`, the command encoding, the
register roles, the staging array, the hand-back rules) and research/13 (families B and C). Read
§(f) of 12 first; everything here uses its conventions without restating them.

**Subject:** the 43 of 166 dispatcher dumps that Sprints 1–2 left to the interpreter —
42 lists of the three "fourth family" shapes and the single `0x34` list.

---

## 0. Headline results

1. **`0x70` → `0x0cb8` is `0x68` with two instructions changed.** Same 40-pair body, same
   software-pipelined two-vertices-per-iteration loop, same in-place stores. The only differences:
   the position lanes convert with `ITOF15` instead of `ITOF4`, and the `TOP+3` quad is applied as
   a **multiply by its `w` lane** (`MULw.xyz`) instead of an **add of its `xyz`** (`ADD.xyz`).
   Over the full 40-pair body, **30 pairs are byte-identical and 10 differ**: the 8 substitution
   sites, one prologue `IADDIU vi3, vi3, 6` moved two pairs earlier, and the relocated loop-head
   target (`IBGTZ vi9, 0xbd0` → `0xd68`). **[verified]**

2. **`0x40` → `0x1968` is a three-pair shim into `0x28`'s body** at `0x1790`, exactly the way
   `0x0a`/`0x12`/`0x1a`/`0x56` shim into other handlers. It swaps the GIFtag template (data qword
   **26** instead of `TOP+1`) and — this is the trap — **skips `0x28`'s `LQ vf20, 38(vi0)`**, so
   the whole RGBAQ computation runs on a `vf20` it *inherits from the previous handler*.
   **[verified]** (disassembly + poison test + end-state registers).

3. **`0x52` → `0x3100` is a weighted-skinning accumulator that ends the program.** It never
   returns to the dispatcher: it falls into the E bit at `0x33b8`, so the program ends at
   `pc = 0x33c8`, emits **zero** GIF packets, and the EE re-`MSCAL`s at `0x33c8` for the next bone
   pass. The rest of the list (`66 08 40 42`) runs in a *different dump*. **[verified]** — 25
   dumps in `logs/vu1dump3` have `startPc = 0x33c8`; three of them return to `0x1b60` and dispatch
   exactly `0x66 0x08 0x40 0x42`.

4. **`0x66` → `0x2e28` recomputes the per-triangle face normal** (`(v2-v1) × (v0-v1)`, `FTOI15`,
   stored to index-record qword `[1]`) — the slot `0x06` reads. It is the natural partner of
   `0x52`: skinning moves the vertices, so the normals must be rebuilt. **`0x66` is never
   dispatched from a `0x1b50` program in the whole corpus** — only from the `0x33c8` entry.
   **[verified]**

5. **`0x34` → `0x2690` is sphere-map (reflection) UV generation plus a rim-alpha ramp**, with an
   11-qword inline block: a 6-qword GIF packet it kicks, a 3×3 basis whose `w` lanes carry the eye
   position, a base-colour quad and a parameter quad. It ends by `JR`-ing into `0x28`'s body, so
   it draws. **[verified]**

6. **The same-lane write conflict at `0x2760` resolves in favour of the UPPER instruction.** The
   interpreter's decoder sets `suppressedLowerVf` and drops the lower `MR32.w vf27, vf30`
   entirely; the generated C++ emits only the upper `ADDx.w vf27, vf0, vf30x`. So
   `vf27.w = 1.0f + vf30.x`, not `vf30.x`. **[verified]** — proved by experiment, not only by
   reading code (§6.4).

7. **The generated C++ already reproduces all 43 runs bit-exactly, register file included.**
   `vu1_replay --verify <dir>/state.txt --regs all --native` over the 43 dumps: 43 `OK` lines,
   `PASS: 0 mismatching field(s)`, exit 0. Task 7's job is to move them from generated to native
   without changing a bit; that same command is the regression check. **[verified]**

   **Correction (Task 7).** The golden this compares against must be taken with `--no-native`
   (or `PS2X_VU1_NATIVE=0`), not with `PS2X_VU1_FAST=0 PS2X_VU1_GEN=0` alone: those two knobs
   disable the fast and generated paths and **leave the native registry on**, so a `--batch`
   run with only them prints a non-zero `native entered=..` and the native path becomes its own
   oracle for every already-implemented list. It happened not to matter for these particular 43,
   which the native dispatcher refused whole, but it silently invalidates a golden taken over any
   wider set — see §9.8. **[verified]** (Task 7, and reproduced independently by its reviewer.)

8. **Settled scope (controller ruling, §9.3): Task 7 implements `0x70` and `0x40`. `0x52` and
   `0x66` stay unimplemented and are a documented residual — 4 dumps of 166.** `0x70` and `0x40`
   are 38 dispatches each and ordinary hand-back-at-`0x1b60` handlers. `0x52` emits nothing, ends
   the program, and its correctness spans two `MSCAL`s (§4.5); `0x66` is never dispatched from
   `0x1b50` at all, so the corpus cannot verify it. `0x34` is outside Task 7's scope.

---

## 1. Corpus, selection and histogram

### 1.1 Selection

Grouping all 166 dispatcher dumps (`logs/vu1entry0/famBC_dumps.txt`, whose `cmds=` column is the
static linear decode of the list at qword 340) by list content gives 14 shapes. Sprints 1–2 cover
the first eleven. The residual four are:

| dumps | list (static, linear read) | family | example | marking |
|---|---|---|---|---|
| 30 | `70 06 08 40 42` | fourth, with cull | `logs/vu1dump3/vu1_prog_31.bin` | **[verified]** |
| 8 | `70 08 40 42` | fourth, no cull | `logs/vu1dump3/vu1_prog_66.bin` | **[verified]** |
| 4 | `52 66 08 40 42` | fourth, skinned | `logs/vu1dump3/vu1_prog_121.bin` | **[verified]** |
| 1 | `68 06 64 08 10 28 72 34 …` | C over A, `0x34` variant | `logs/vu1dump3/vu1_prog_27.bin` | **[verified]** |

42 + 1 = 43. **All 43 live in `logs/vu1dump3`** — neither `vu1dump2` nor `vu1dump4` contains a
single one. `top ∈ {424, 724}`, `itop = 0`, code FNV `9ecdd7bedda54489` for all of them, like the
rest of the corpus. **[verified]**

The `…` in the `0x34` row is research/13 §3.2's embedded-GIF-packet artefact: the linear decode
runs into the inline block. The executed list is `68 06 64 08 10 28 72 34 74 42` (§1.3).

### 1.2 Jump-table slots

Handler pc = `0x1ba0 + 8 * cmd` (research/12 §f.0). The five slots this note is about:

| cmd | slot pc | handler pc | marking |
|---|---|---|---|
| `0x34` | `0x1d40` | `0x2690` | **[verified]** |
| `0x40` | `0x1da0` | `0x1968` | **[verified]** |
| `0x52` | `0x1e30` | `0x3100` | **[verified]** |
| `0x66` | `0x1ed0` | `0x2e28` | **[verified]** |
| `0x70` | `0x1f20` | `0x0cb8` | **[verified]** |

### 1.3 Execution histogram

`dist/vu1_replay.exe --pchist <hist.bin> <the 42 dumps>` → **250 distinct pairs, 102,790
pair-executions**. Ranges split at jump-table targets; `entered` = count at the range's first pc.
**[verified]**

| pc range | pairs | pair-execs | entered | cmd | what it is | marking |
|---|---|---|---|---|---|---|
| `0x1790-0x1960` | 59 | 42,174 | 38 | — | `0x28`'s body, entered from `0x40`'s shim at `0x1970`. **`0x1780`/`0x1788` never execute in this corpus.** | **[verified]** |
| `0x1638-0x1768` | 39 | 20,408 | 30 | `0x06` | backface cull (research/13 §4.2) | **[verified]** |
| `0x0df8-0x0f00` | 34 | 20,245 | 38 | `0x08` | transform + perspective divide (research/12 §f.4) | **[verified]** |
| `0x0cb8-0x0df0` | 40 | 14,925 | 38 | **`0x70`** | scaled int→float vertex unpack (§2) | **[verified]** |
| `0x3100-0x3280` | 49 | 2,896 | 4 | **`0x52`** | skinning first pass (§4) | **[verified]** |
| `0x1b60-0x1b98` | 8 | 1,488 | 186 | — | the dispatcher body; 186 commands over 42 programs | **[verified]** |
| `0x1968-0x1978` | 3 | 114 | 38 | **`0x40`** | the shim (§3) | **[verified]** |
| `0x1b50-0x1b58` | 2 | 84 | 42 | — | the `XTOP` half, once per program | **[verified]** |
| `0x1b40-0x1b48` | 2 | 76 | 38 | `0x42` | the E bit — **only 38 of 42**; the four `0x52` programs end elsewhere | **[verified]** |
| `0x33b8-0x33c0` | 2 | 8 | 4 | — | `0x52`'s E bit; end pc `0x33c8` | **[verified]** |

Per-command dispatch counts read from the jump-table slot pcs, 42 dumps, 186 dispatches:
`0x70` 38, `0x08` 38, `0x40` 38, `0x42` 38, `0x06` 30, `0x52` 4. **`0x66` is dispatched zero
times.** **[verified]**

The single `0x34` dump (`logs/vu1dump3/vu1_prog_27.bin`): **353 distinct pairs, 11,778
pair-executions**, 10 dispatches, 128 packets / 20,864 bytes, end pc `0x1b50`.
`0x2690-0x2950` 89 pairs / 2,993 execs / entered 1; `0x1780-0x1960` entered **2** (one dispatched
`0x28`, one from `0x34`'s `JR vi6`). **[verified]**

The 25 `startPc = 0x33c8` dumps (the `0x52` follow-ons): **228 distinct pairs, 13,901
pair-executions**; `0x3288-0x3498` entered 22, `0x3100-0x3168` entered 22, and **12 dispatches**
— `0x66` 3, `0x08` 3, `0x40` 3, `0x42` 3. **[verified]**

### 1.4 Executed command order

From `PS2X_TRACE_VU_STEPS=4000000 vu1_replay --trace`, taking the jump-table slot two steps after
each `0x1b90` (`JR vi3`). **[verified]**

```
vu1_prog_31.bin  (70 06 08 40 42)   ->  70  06  08  40  42
vu1_prog_66.bin  (70 08 40 42)      ->  70  08  40  42
vu1_prog_121.bin (52 66 08 40 42)   ->  52                      (program ends inside 0x52)
vu1_prog_27.bin  (0x34 list)        ->  68  06  64  08  10  28  72  34  74  42
```

`0x34` consumes eleven list qwords, so the dispatcher's next read after it lands on q359 = `0x74`,
then q360 = `0x42`. **[verified]** — this is the direct confirmation of the `vi14 += 11` at
`0x2740`.

### 1.5 XGKICK sites

| corpus | pc | register | value | who | kicks | marking |
|---|---|---|---|---|---|---|
| the 42 | `0x1920` | `vi2` | 300/290 | `0x40` (per triangle) | 798 | **[verified]** |
| the `0x34` dump | `0x04b8` | `vi2` | 330 | `0x64` | 1 | **[verified]** |
| | `0x1920` | `vi2` | 300/290 | `0x28` ×63 + `0x34`'s pass ×63 | 126 | **[verified]** |
| | `0x26f8` | `vi5` | `340 + vi14` | `0x34` (per outer iteration) | 1 | **[verified]** |
| the 25 `0x33c8` | `0x1920` | `vi2` | 300/290 | `0x40` | 85 | **[verified]** |

`0x70`, `0x52` and `0x66` contain no `XGKICK` at all. **[verified]**

---

## 2. `0x70` → `0x0cb8` — scaled int→float vertex unpack

### 2.1 Body

Structurally identical to `0x68` (research/13 §4.1). Diffing the **full 40-pair body**,
`0x0b20-0x0c58` against `0x0cb8-0x0df0`, pair-aligned: **30 identical, 10 differing**.
The ten are

* 4 × `ITOF4.xyz` → `ITOF15.xyz` (the position conversion: two in the prologue, two in the loop),
* 4 × `ADD.xyz vfOut, vfOut, vf27` → `MULw.xyz vfOut, vfOut, vf27w` (same two/two split),
* 1 prologue `IADDIU vi3, vi3, 6` moved two pairs earlier — scheduling only, so this one is inert
  for an implementation. **Correction (Task 7):** the reason is *not* "every `LQ` that uses `vi3`
  still precedes it", which is false as worded in both handlers — `0x70`'s prologue loads at
  `0x0cd0`–`0x0cf8` and `0x68`'s at `0x0b38`–`0x0b60` precede the increment, and the loads that
  follow it read the *next* pair of records, which is the point of the prefetch. The real
  invariant is that **nothing between the two candidate positions reads `vi3` at all**: the
  increment sits at `0x0d18` in `0x70` and at `0x0b98`'s counterpart `0x0d30` in `0x68`'s
  schedule, and the pairs in between (`0x0d20` `ITOF0.xyzw vf23`, `0x0d28`/`0x0d30` the two
  `MULw.xyz`) touch only `vf` registers. The native path never advances `m_cycle` either, so
  there is no timing to match,
* 1 relocated loop-head target, `IBGTZ vi9, 0xbd0` → `IBGTZ vi9, 0xd68`.

**[verified]**

**Register allocation — this is what a bit-exact handler has to get right.** `--verify --regs all`
compares the whole `vf` file, and the loop is software-pipelined two vertices deep, so on exit the
register file holds the conversion of one pair of records *past* the end of the array. The
microcode uses two three-register lanes, A (even vertex) and B (odd vertex), plus the bias/scale
quad — thirteen `vf` registers in total, identical to `0x68`:

| role | lane A (vertex `k`) | lane B (vertex `k+1`) | marking |
|---|---|---|---|
| raw record `q+0` (position) | `vf20` | `vf26` | **[verified]** |
| raw record `q+1` (UV) | `vf30` | `vf18` | **[verified]** |
| raw record `q+2` (colour) | `vf19` | `vf24` | **[verified]** |
| converted `q+0` → stored at `-6`/`-3(vi3)` | `vf21` | `vf25` | **[verified]** |
| converted `q+1` → stored at `-5`/`-2(vi3)` | `vf31` | `vf17` | **[verified]** |
| converted `q+2` → stored at `-4`/`-1(vi3)` | `vf22` | `vf23` | **[verified]** |
| `TOP+3` (the scale quad; `0x68`'s bias quad) | `vf27` | `vf27` | **[verified]** |

Integer registers: `vi3` = the record cursor in qwords, `vi9` = vertices remaining
(decremented by two per iteration). **[verified]**

```
vi3  = vi1 + 4                     ; the vertex block
vi9  = ILW.z 2(vi1)                ; vertex count
vf27 = LQ 3(vi1)                   ; TOP+3 -- only its .w lane is used

loop, TWO vertices per iteration, vi9 -= 2, vi3 += 6:      ; loop head 0x0d68
    ; vertex k occupies qwords vi3+0..vi3+2, vertex k+1 qwords vi3+3..vi3+5
    ; lane A, vertex k  (lane B, vertex k+1, is the same with vf26/vf18/vf24 -> vf25/vf17/vf23)
    q+0 : vf20 = LQ(q+0)
          vf21.xyz = ITOF15.xyz(vf20)       ;  value / 32768
          vf21.xyz = vf21.xyz * vf27.w      ;  <-- MULTIPLY by TOP+3.w  (0x68 ADDs TOP+3.xyz)
          vf21.w   = ITOF15.w(vf20)         ;  value / 32768, NOT scaled (written after the mul)
    q+1 : vf30 = LQ(q+1)
          vf31.xy = ITOF12.xy(vf30)         ;  U,V  value / 4096
          vf31.zw = ITOF15.zw(vf30)         ;  value / 32768
    q+2 : vf19 = LQ(q+2)
          vf22 = ITOF0.xyzw(vf19)           ;  straight int->float (the colour quad)
    SQ vf21 -> -6(vi3) ; SQ vf31 -> -5(vi3) ; SQ vf22 -> -4(vi3)
    (lane B: SQ vf25 -> -3(vi3) ; SQ vf17 -> -2(vi3) ; SQ vf23 -> -1(vi3))
IBLTZ vi9, 0x1b60  at 0x0d80        ; odd-count early exit, after storing the first of the pair
B 0x1b60           at 0x0de8
```

**Implementation recipe for Task 7** — verified against the disassembly and the generated C++,
not taken on trust:

> Clone `cmdUnpackVertices` (`third_party/ps2recomp/ps2xRuntime/src/lib/vu/native/socom2_dispatch_0x1b50.cpp:840`,
> 235 lines) and make exactly two substitutions.

1. `itof<4, …>` → `itof<15, …>`. There are **exactly four** `itof<4,` call sites in that function
   (`kRawA0`/`kRawB0` in the prologue and again in the loop) and they are precisely the four
   `ITOF4.xyz` pairs in the diff. Every other `itof<15,…>`, `itof<12,…>`, `itof<0,…>` stays —
   note in particular that the `.w`-lane conversions are *already* `itof<15, kRawA0/kRawB0>` and
   must not be touched.
2. `fmac<vu1ops::ArithAdd, Vu1Gen::SrcVt, 0, kXYZ, kOutA0|kOutB0, kBias, false, false, true>`
   → `fmac<vu1ops::ArithMul, Vu1Gen::SrcBc, 3, kXYZ, kOutA0|kOutB0, kBias, false, false, true>`.
   There are **exactly four** such `ArithAdd, SrcVt, 0, kXYZ` sites. Only the first two template
   arguments change (`Add`→`Mul`, `SrcVt`→`SrcBc`) plus the broadcast lane `0`→`3` (`w`); the dest
   mask, `fs`, `ft` and the three flags are unchanged. This is exactly the delta the generated
   code shows between `L_0xb90` and `L_0xd28`:
   `fmac<ArithAdd, SrcVt, 0, 14, 21, 27, false,false,true>` vs
   `fmac<ArithMul, SrcBc, 3, 14, 21, 27, false,false,true>`. **[verified]**

The third diff line — the prologue `IADDIU vi3, vi3, 6` two pairs earlier — needs **no** change to
the clone. In `cmdUnpackVertices` the cursor increment sits between the two bias `fmac`s; moving
it before both is semantically identical (neither `fmac` reads `vi3`, and every `loadQword` that
does still follows it), and the native path never advances `m_cycle`, so there is no timing to
match either. **[verified]** — stated explicitly because the recipe as first written could be read
as requiring a code change here.

| item | value | marking |
|---|---|---|
| loop count | `TOP+2.z` (`ILW.z 2(vi1)` at `0x0cc0`) | **[verified]** |
| scale source | `TOP+3.w` only — poisoning `TOP+3.x` or `TOP+3.y` changes nothing; poisoning `TOP+3.w` changes the packets | **[verified]** (poison test) |
| conversion | positions `ITOF15` (÷32768) then `× TOP+3.w`; `w` lane `ITOF15` unscaled; UV `ITOF12` (÷4096); UV `zw` `ITOF15`; colour `ITOF0` | **[verified]** (disassembly) |
| destination | **in place** — the store offsets `-6..-1` after `vi3 += 6` are exactly the qwords just read | **[verified]** |
| early exit | `IBLTZ vi9, 0x1b60` at `0x0d80`, delay slot `SQ vf22, -4(vi3)` executes | **[verified]** |
| reads one vertex past the end | yes, the same software-pipelined read-ahead as `0x68` | **[verified]** |
| hand-back | `B 0x1b60` (or the `IBLTZ` shortcut) — an ordinary handler, nothing crosses | **[verified]** |
| XGKICK | none | **[verified]** |

### 2.2 Why the two variants exist

`0x68` is `position = raw/16 + TOP+3.xyz` — a 12.4 fixed-point local coordinate with an integer
offset. `0x70` is `position = (raw/32768) * TOP+3.w` — a normalised 1.15 coordinate with a
per-object scale. Sanity check on `vu1_prog_31.bin`: `TOP+3.w = 2.3232f`, so the effective factor
is 7.09e-5; `TOP+4 = (19777, -10884, -2548, …)` maps to `(1.402, -0.772, -0.181)`, plausible
object space. **[verified]** for the arithmetic; the "per-object scale" reading is **[guess]**.

### 2.3 Live-in / live-out

Nothing is live-in. `0x70` writes the thirteen `vf` registers of §2.1's allocation table —
`vf17`–`vf27`, `vf30`, `vf31` — plus `vi3` and `vi9`, and reads only `vi1` and VU memory. All
thirteen are part of the compared end-of-program state under `--regs all`, and because of the
two-deep pipelining nine of them (both lanes' raw and converted quads) hold the *record past the
end* on exit; reproducing that is not optional. A per-register perturbation sweep (all of `vf1..vf31`, `vi1..vi15`, one register replaced
per run, packets compared against an exact golden) over `vu1_prog_31.bin` and `vu1_prog_66.bin`
gives live-in = **`vf1`–`vf4` only**, and those are `0x08`'s clip matrix, not `0x70`'s.
**[verified]**

---

## 3. `0x40` → `0x1968` — untextured black triangles (a shim into `0x28`)

### 3.1 The shim

```
0x1968:  LQ.xyzw vf19, 26(vi0)      ; the GIFtag template -- from data qword 26
0x1970:  B 0x1790                   ; into 0x28's body, TWO PAIRS PAST ITS HEAD
0x1978:  NOP                        ; delay slot
```

compared with `0x28`'s own head:

```
0x1780:  LQ.xyzw vf20, 38(vi0)      ; (1,1,1,0.5) -- the fixed-point rounding bias
0x1788:  LQ.xyzw vf19, 1(vi1)       ; the GIFtag template -- from TOP+1
```

So `0x40` differs from `0x28` in exactly two ways: the tag comes from qword **26**, and **`vf20`
is not loaded**. Everything from `0x1790` on is research/12 §f.4's packet builder, unchanged:
one `XGKICK` per visible triangle, 10 qwords (tag + 3 × `ST, RGBAQ, XYZF2`), ping-ponged between
qwords 300 and 290 whose bases live in qword 329, `NLOOP` patched to 3 via
`IADDIU vi11, vi0, 32767` / `IADDIU vi11, vi11, 4` (= `0x8003`), gated by index-record `[0].w`
bit 0 (cull) and bit 1 `OR` qword `39.w`. **[verified]**

| item | value | marking |
|---|---|---|
| loop count | `TOP+2.w` (`ILW.w vi13, 2(vi1)` at `0x17d0`), `IBGTZ` — zero is safe | **[verified]** |
| index list | `vi4 = ILW.x 2(vi1) + vi1`, 2 qwords per triangle | **[verified]** |
| GIFtag template | data qword **26**; poisoning qword 26 changes the packets, poisoning qword 38 does **not** | **[verified]** (poison test) |
| packets emitted | 798 over the 38 dumps, all with tag `00008003 3025c000 00000412 00000000` | **[verified]** |
| hand-back | `ISW.x vi2 -> 329` / `ISW.y vi8 -> 329` then `B 0x1b60` (`0x1950`–`0x1960`) | **[verified]** |

### 3.2 The packet template

Data qword 26 is byte-identical in all 38 dumps: `00008000 3025c000 00000412 00000000`.

| field | value | meaning | marking |
|---|---|---|---|
| `NLOOP` | 0 in the template, patched to **3** | three vertices per kick | **[verified]** |
| `EOP` | 1 | | **[verified]** |
| `NREG` | 3 | | **[verified]** |
| `FLG` | 0 | PACKED | **[verified]** |
| `PRE` | 1 | the tag writes PRIM | **[verified]** |
| `PRIM` | `0x4B` = PRIM 3 (triangle), IIP 1, **TME 0**, **FGE 0**, ABE 1 | gouraud, **untextured**, **unfogged**, alpha-blended | **[verified]** |
| `REGS` | `0x412` = `ST, RGBAQ, XYZF2` | same three as `0x28` | **[verified]** |

`0x28`'s `TOP+1` template in the same dumps is `0000xxxx 303dc000 00000412 00000000`, PRIM `0x7B`
— identical except **TME 1, FGE 1**. So `0x40` is "the same triangles again, untextured and
unfogged". **[verified]**

### 3.3 The inherited `vf20` — the one genuinely dangerous thing in this note

The shared body at `0x1790` opens with

```
0x1790:  ADDAw.xyz ACC, vf0, vf20w      ; ACC.xyz = 0 + vf20.w
0x1798:  SUBAw.w   ACC, vf0, vf0w       ; ACC.w   = 0
  …
0x17d8:  LQ.w vf20, 327(vi0)            ; vf20.w := qword 327.w   (xyz left alone)
  …
0x1880:  MADD.xyzw vf18, vf18, vf20     ; RGBAQ = ACC + staging_RGBAQ * vf20
0x18a0:  FTOI0.xyzw vf18, vf18
```

For `0x28`, `vf20` was just loaded from qword 38 = `(1,1,1,0.5)`, so `ACC = (0.5,0.5,0.5,0)` and
`vf20 = (1,1,1,q327.w)` — i.e. "round-to-nearest bias on RGB, scale alpha by q327.w". For
**`0x40` neither the `ACC` nor the `vf20.xyz` used here belong to `0x40` at all**: they are
whatever the previously dispatched handler left in `vf20`.

In every one of the 38 observed dispatches the previous command is `0x08` (`0x0df8`), whose
software-pipelined loop exits with `vf20 = LQ 0(vi3)` one read past the end:

```
vf20_at_0x40 = data qword  TOP + 4 + 3 * (TOP+2.z + 2)
```

**[verified]** twice by poison test — on `vu1_prog_31.bin` (`top=424`, `N=42`, qword 560) and on
`vu1_prog_66.bin` (`top=724`, `N=65`, qword 929): poisoning that qword changes the emitted
packets, poisoning either neighbour (±1 vertex stride) does not. The end-state register dump
confirms the value directly: `vf20 = 0000000c,00000015,0000000f,3f800000` for `vu1_prog_31`,
which is qword 560's `xyz` with `w` replaced by `q327.w = 1.0f`.

Consequences, all **[verified]**:

* In all 38 dumps the index list begins immediately after the vertex block
  (`TOP+2.x == 4 + 3*TOP+2.z`), so that read always lands **inside the index list**, on an index
  record whose four words are small integers (`0000000c 00000015 0000000f 00000003`).
* Reinterpreted as floats those are **denormals**, which the VU flushes to zero — the end state
  shows `acc = 00000000,00000000,00000000,00000000`.
* Therefore `R' = 0 + R*0 = 0`, `G' = B' = 0`, and `A' = 0 + A * q327.w`.
* Measured: across all 798 packets / 2394 vertices of the 38 dumps there is exactly **one**
  distinct `(R,G,B)` triple, `(0, 0, 0)`. Alpha varies.

So `0x40` in practice draws **pure-black alpha-blended untextured triangles** — a shadow /
darkening pass. The interpretation is **[guess]**; the black is **[verified]**.

**What Task 7 must do.** Reproduce the inheritance, do not hardcode. Concretely: the native
`0x08` handler must leave `vf20` holding `data[TOP+4 + 3*(vertexCount+2)]` exactly as the
microcode does (if it already runs the loop faithfully it does), and the native `0x40` handler
must **not** reload `vf20` and must compute `ACC.xyz` from the inherited `vf20.w` *before*
overwriting `vf20.w` with `q327.w`. Hardcoding `RGB = 0` would be correct for all 43 dumps in the
corpus and silently wrong the first time a list puts a different handler before `0x40`.
If a fast path is wanted, guard it: `RGB = 0` is only safe when the three inherited `vf20.xyz`
*and* `vf20.w` all flush to zero.

### 3.4 Live-in / live-out

Live-in over `vu1_prog_31.bin` / `vu1_prog_66.bin`, per-register sweep against an exact golden:
**`vf1`–`vf4` only** (`0x08`'s clip matrix, produced by entry 0). No `vi` register is live-in.
**[verified]**

Across the hand-back inside the list, `0x40` needs: `vi1`, `vi14`, and `vf20` (§3.3). Live-out:
`vi2`/`vi8` swapped back into qword 329, the staging array untouched, qwords 290–309 rewritten.
**[verified]**

---

## 4. `0x52` → `0x3100` — the weighted-skinning accumulator that ends the program

### 4.1 What the VIF chunk looks like

For a `0x52` list, `TOP+0..TOP+3` are **not** the header research/12 §f.4 describes — they are a
bone matrix. This is why `tools_py/vu1_headers.py` reports nonsense for these four dumps
(`vertices = 12384, -21943, -21943, -22066; triangles = 0`): it is reading matrix floats as
`ILW` words. **[verified]**

| qword | contents | marking |
|---|---|---|
| `TOP+0` | bone matrix row 0 (`vf23`) | **[verified]** |
| `TOP+1` | bone matrix row 1 (`vf24`) | **[verified]** |
| `TOP+2` | bone matrix row 2 (`vf25`) | **[verified]** |
| `TOP+3` | bone matrix translation (`vf26`), `w = 1.0f` | **[verified]** |
| `TOP+4.x` | **flags**: bit 0 = "accumulate" (not the first bone), bit 2 = "last bone" | **[verified]** |
| `TOP+4.w` | **count** = number of vertices in this bone's list (`vi10`) | **[verified]** |
| `TOP+5 + 2k` | vertex `k`: `xyz` = position in 1.15 fixed point, `w` = **destination offset** into the staging array | **[verified]** |
| `TOP+6 + 2k` | vertex `k`: `xyz` = normal in 1.15 fixed point, `w` = **the bone weight** in 1.15 fixed point | **[verified]** |

Observed flags across the corpus: `0x2` (first pass, not last), `0x1` (accumulate, not last),
`0x5` (accumulate + last). `0x0` and `0x4` never appear. **[verified]**

### 4.2 First pass (`0x3170`–`0x3278`)

```
0x3100  vi4  = vi1                       ; LQI vf23,vf24,vf25,vf26 from TOP+0..TOP+3 (vi4 -> TOP+4)
0x3130  vi5  = ILW.x 0(vi4)              ; flags
0x3138  vi10 = ILW.w 0(vi4)              ; count
0x3108  vi2  = vi1 + 5                   ; the vertex stream
0x3140  vi4  = ILW.w 0(vi2)              ; first destination offset
0x3150  vi7  = vi5 & 1
0x3160  IBGTZ vi7, 0x3288                ; bit 0 set -> the accumulate path (§4.3)
------- first-pass path -------
0x3170  vi3  = 40                        ; the staging base
0x3178  ISW.x vi3 -> 37(vi0)             ; PERSISTED: qword 37.x := 40
0x3180  vi6  = vi3 + vi4                 ; the destination
0x3188  vi9  = vi10                      ; save the count for the 0x33c8 fixup loop
loop (head 0x31d8), vi10 times:
    vf19 = ITOF15.xyz(LQ 0(vi2)) * 10.0  ; position, 1.15 fixed point, x10
    vf20 = ITOF15.xyzw(LQ 1(vi2))        ; normal (xyz) and WEIGHT (w)
    vf19.xyz *= vf20.w                   ; weight the position
    vf20.xyz *= vf20.w                   ; weight the normal
    vi2  += 2 ; vi10 -= 1
    vi4   = ILW.w 0(vi2)                 ; the NEXT vertex's destination offset (read ahead)
    vf27.xyz = vf23*vf19.x + vf24*vf19.y + vf25*vf19.z + vf26*vf20.w   ; 4x4, translation weighted
    vf28.xyz = vf23*vf20.x + vf24*vf20.y + vf25*vf20.z                 ; 3x3, no translation
    SQ.xyz vf27 -> 0(vi6)                ; staging[dst+0] = skinned position
    SQ.xyz vf28 -> 1(vi6)                ; staging[dst+1] = skinned normal
    vi6 = vi3 + vi4
    IBNE vi10, vi0, 0x31d8
0x3278  B 0x33b8                          ; -> the E bit
```

The `LOI 10.0` is applied to the position only, never the normal. **[verified]**

### 4.3 Accumulate pass (`0x3288`–`0x33b0`)

Same loop with two additions: `vi3` is restored from qword **37.x** rather than set to 40, and
before each MADD chain the existing staging value is loaded and pre-multiplied into the ACC —
`MULAw.xyz ACC, vf29, vf0w` for the position (`vf29 = LQ 0(vi6)`) and `MULAw.xyz ACC, vf30, vf0w`
for the normal (`vf30 = LQ 1(vi6)`) — so each bone's weighted contribution is **added** to what is
already there. The count is the new chunk's `TOP+4.w`; `vi9` is *not* rewritten, so it keeps the
first pass's vertex count. Falls through to `0x33b8`. **[verified]**

### 4.4 The E bit at `0x33b8` and the second entry at `0x33c8`

```
0x33b8:  NOP | NOP   [E]
0x33c0:  NOP | NOP
0x33c8:  XTOP vi1                       ; <-- the NEXT MSCAL starts here
0x33d0:  vi7 = 4
0x33d8:  vi7 = vi5 & 4                  ; vi5 is LIVE-IN from the program that just ended
0x33e8:  IBEQ vi7, vi0, 0x3100          ; not the last bone -> another pass
------- last bone: repack the staging array into the vertex block -------
0x33f8:  vi2 = ILW.x 37(vi0)            ; = 40
0x3400:  vi3 = vi1 + 4
0x3408:  vf28 = LQ 338(vi0)             ; a constant quad -> every vertex's colour slot
loop (head 0x3410), vi9 times:
    vf27 = LQ 1(vi3)                    ; the destination vertex's UV qword (still integer)
    vf29 = LQ 0(vi2) ; vf30 = LQ 1(vi2) ; vi2 += 2     ; skinned position, skinned normal
    vf30.w = vf30.z ; vf30.z = vf30.y   ; shift the normal's y,z up into z,w
    vf27.xy = ITOF12.xy(vf27)           ; U,V
    vf29.w  = vf30.x                    ; MR32.w -- the normal's x into the position's w
    SQ.xy vf27 -> 1(vi3) ; SQ.zw vf30 -> 1(vi3)
    SQ.xyzw vf28 -> 2(vi3)
    SQ.xyzw vf29 -> 0(vi3)
    vi3 += 3
0x3490:  B 0x1b60                        ; back into the dispatcher, at vi14 = 1 -> command 0x66
```

Measured, 25 dumps with `startPc = 0x33c8`: **22** take the `B 0x3100` branch (0 packets, end pc
`0x33c8` again) and **3** (`vu1_prog_128`, `141`, `144`) take the fixup path and return to the
dispatcher, where they dispatch exactly `0x66 0x08 0x40 0x42`. All three have `vi14 = 1` live-in,
so the list resumes at q341 = `0x66`. All three have `vi5 = 5` live-in (bit 0 accumulate + bit 2
last). **[verified]**

**The vertex record this produces is exactly the one `0x34` reads** (§6.2): position `xyz` with
**`w = normal.x`**, UV `xy` with **`zw = normal.y, normal.z`**, and a constant colour quad. The
same packing `0x68`/`0x70` produce with their `ITOF15.w` on the position quad and `ITOF15.zw` on
the UV quad. **[verified]** — this is the cross-check that pins down what `0x68`'s odd `w`-lane
conversions are *for*.

### 4.5 Live-in / live-out and the hand-back rule

A per-register perturbation sweep on `vu1_prog_121.bin`, comparing the full end state (packets,
cycles, end pc **and the VU-data hash**, since this program emits no packets at all):
**no register is live-in.** `0x52` derives everything from `vi1` and VU memory. **[verified]**

Live-**out** is the problem. The program ends; the follow-on program at `0x33c8` is a *separate*
`MSCAL` that this project has no native implementation for, so the interpreter will run it from
whatever register file the native handler leaves. Exact end state of `vu1_prog_121.bin`:

```
endpc=0x33c8  packets=0  cycles=623  mac=000  status=0c0  q=3f800000  p=00000000
vi = 0,424,487,40,0,2,40,0,2,29,0,0,2,0,1,948
       ^   ^   ^  ^ ^  ^  ^ ^  ^        ^   ^
       |   |   |  | |  |  | |  |        |   vi15 (stale)
       |   |   |  | |  |  | |  vi9 = 29 = the saved vertex count  <-- READ at 0x33c8
       |   |   |  | |  |  | vi8 (stale)
       |   |   |  | |  |  vi7 = 0
       |   |   |  | |  vi6 = vi3 + vi4 = 40
       |   |   |  | vi5 = 2 = the flags word                      <-- READ at 0x33d8
       |   |   |  vi4 = 0 = the last destination offset read
       |   |   vi3 = 40 = the staging base
       |   vi2 = 487 = TOP+5+2*29, the source pointer past the end
       vi1 = 424 = XTOP
vi14 = 1  <-- the command index the dispatcher resumes at
```

`vf23`–`vf26` still hold the bone matrix, and qword **37.x** holds 40.

**Hand-back rule.** A native `0x52` must end the program with `pc = 0x33c8`, `ended = true`, and
*all* of `vi1..vi15`, `vf23..vf26`, `q`, `p`, `mac`, `status` and the VU data image exactly as
above — because `vi5`, `vi9` and `vi14` are read by the very next program and `vi2`/`vi3`/`vi4`
are read by the accumulate path if the EE issues one. This is the only handler in the corpus whose
correctness condition spans two `MSCAL`s. **[verified]**

Given 4 dumps, 0 packets and that cost, §0's recommendation stands: leave `0x52` to the
interpreter. Refusing it is free — the current native dispatcher already hands back on the first
command word.

---

## 5. `0x66` → `0x2e28` — recompute the per-triangle face normal

```
vi4  = ILW.x 2(vi1) + vi1          ; the index list
vi3  = vi1 + 4                     ; the vertex block
vi13 = ILW.w 2(vi1)                ; triangle count
per triangle (vi4 += 2, vi13--, IBGTZ):
    vi5,vi6,vi7 = ILW.x/y/z 0(vi4)          ; the three vertex qword offsets (stride 3)
    vf17 = LQ 0(vi3 + vi5)                  ; v0
    vf18 = LQ 0(vi3 + vi6)                  ; v1
    vf19 = LQ 0(vi3 + vi7)                  ; v2
    vf26.xyz = vf17.xyz - vf18.xyz          ; v0 - v1
    vf28.xyz = vf19.xyz - vf18.xyz          ; v2 - v1
    OPMULA.xyz ACC,  vf28, vf26
    OPMSUB.xyz vf29, vf26, vf28             ; vf29.xyz = vf28 x vf26 = (v2-v1) x (v0-v1)
    vf29.xyz = FTOI15.xyz(vf29)             ; back to 1.15 fixed point
    SQ.xyzw vf29 -> -1(vi4)                 ; index record [1] := the face normal
B 0x1b60
```

**[verified]**. This writes exactly the slot research/13 §4.2 identified as the face normal read
by `0x06` (`vf29 = ITOF15(LQ 1(vi4))`), which is why `0x66` sits between `0x52` (which moves the
vertices) and `0x08`/`0x40` in the list.

| item | value | marking |
|---|---|---|
| loop count | `TOP+2.w`, `IBGTZ` — zero is safe | **[verified]** |
| index record stride | 2 qwords, `[1]` is the normal | **[verified]** |
| gating | none — every triangle is processed, the cull flag is not consulted | **[verified]** |
| XGKICK | none | **[verified]** |
| hand-back | `B 0x1b60` at `0x2f20` | **[verified]** |
| **dispatched from `0x1b50`** | **never** in this corpus — only from the `0x33c8` entry, 3 times | **[verified]** |

**The `w`-lane trap.** `OPMSUB.xyz` and `FTOI15.xyz` write only `xyz`, but the store is
`SQ.xyzw`. So index record `[1].w` receives **`vf29.w` inherited from before the handler**. In the
`0x33c8` programs that is whatever the fixup loop at `0x3410` left there (`vf29.w = normal.x` of
the last vertex). It never reaches the GS — `0x06` only uses the `xyz` of that quad — but it *is*
written to VU data memory, and `--batch`'s `state.txt` carries a `data=` hash of the whole 16 KB,
so a native `0x66` that zeroes it would fail an exact-golden comparison. **[verified]** from the
disassembly; **[guess]** that no other handler reads it.

---

## 6. `0x34` → `0x2690` — sphere-map ST + rim alpha, over an 11-qword inline block

Executed **once** in the whole 166-dump corpus, in `logs/vu1dump3/vu1_prog_27.bin`, with the
outer-loop count `N = 1`. Everything below is read from that single run plus the disassembly and
the generated C++; the `N > 1` path is **[guess]** throughout.

### 6.1 Skeleton and the inline block

```
0x2690  vi3 = vi1 + 4                       ; source vertex block, stride 3
0x2698  vi4 = 40                            ; staging base, stride 3
0x26a0  vi6 = 752                           ; = pc 0x1780 -- the tail-jump target
0x26a8  vi9 = ILW.z 2(vi1)                  ; vertex count
0x26b0  vi5 = vi14 + 340                    ; <-- COMPUTED OUTSIDE THE OUTER LOOP
0x26b8  ISW.x vi3 / ISW.y vi4 / ISW.z vi9 -> 339(vi0)       ; save the three pointers
0x26d0  vi7 = ILW.z 339(vi14)               ; N = the z field of THIS COMMAND's own list qword
------- outer loop, head 0x26d8, N times -------
0x26d8  restore vi3 / vi4 / vi9 from qword 339
0x26f0  vi7 -= 1
0x26f8  XGKICK vi5                          ; kick the block's GIF packet
0x2708  vf17 = LQ 6(vi5) ; vf18 = LQ 7(vi5) ; vf19 = LQ 8(vi5)
0x2720  vf27 = LQ 9(vi5) ; vf23 = LQ.xyw 10(vi5)
0x2730  vf20.x = vf17.w ; vf20.y = vf18.w ; vf20.z = vf19.w  ; the EYE position
0x2740  vi14 += 11                          ; <-- ELEVEN list qwords consumed
0x2748  vf30.x = vf27.w ; vf20.w = LQ.w 2(vi3)               ; vertex colour quad's w
        vf24 = LQ 0(vi3) ; vf25 = LQ 1(vi3)
------- inner loop, head 0x2758, vi9 times (§6.2) -------
0x2928  IBNE vi9, vi0, 0x2758
0x2938  IBNE vi7, vi0, 0x26d8
0x2948  JR vi6                              ; -> pc 0x1780, i.e. 0x28's FULL body
```

Note `vi14` has already been incremented by the dispatcher at `0x1b70`, so `339(vi14)` is the
command's own qword and `vi5 = 340 + vi14` is the **first qword after it**. Same convention as
`0x30`/`0x32` (research/13 §4.8). **[verified]** — confirmed end to end by §1.4: after `0x34` at
list index 7 the next command read is q359, i.e. `1 + 11` qwords later.

**Inline block layout**, `vi5 = 348` in the sampled dump:

| offset | qword | contents (sampled) | role | marking |
|---|---|---|---|---|
| `0(vi5)` | q348 | `00008005 10000000 0000000e 0104e0b0` | **GIFtag**: NLOOP 5, EOP 1, NREG 1, REGS0 = `0xE` = `A+D` → 6 qwords are kicked. The fourth word is the **upper half of `REGS`** (descriptors 8–15); with `NREG = 1` it is simply unused. | **[verified]** |
| `1..5(vi5)` | q349–353 | 5 × A+D register writes: `ALPHA_1 (0x42)`, `TEX1_1 (0x14)`, `TEX0_1 (0x06)`, `TEST_1 (0x47)`, `CLAMP_1 (0x08)` | GS state for this pass | **[verified]** for the tag/count; the specific five registers are per-object data, **[guess]** as a rule |
| `6(vi5)` | q354 | `(0, 1, 0, 938.75)` | basis row 0 (`vf17`), `w` = eye.x | **[verified]** |
| `7(vi5)` | q355 | `(0, 0, 1, -125.03)` | basis row 1 (`vf18`), `w` = eye.y | **[verified]** |
| `8(vi5)` | q356 | `(1, 0, 0, 832.17)` | basis row 2 (`vf19`), `w` = eye.z | **[verified]** |
| `9(vi5)` | q357 | `(33, 33, 33, 65)` | base colour `vf27`; `w` feeds the alpha (§6.4) | **[verified]** |
| `10(vi5)` | q358 | `(1.5, 100, —, 0.01)` — `LQ.xyw`, `z` not loaded | `vf23`: `x` = UV scale, `y` = rim offset, `w` = rim slope | **[verified]** |

11 qwords: 6 kicked + 5 VU-only. **[verified]**

### 6.2 The per-vertex body (`0x2758`–`0x2930`)

`vf24 = LQ 0(vi3)` (position, `w` = normal.x), `vf25 = LQ 1(vi3)` (UV, `zw` = normal.y/z),
`vf20.w` = the vertex colour quad's `w` (§6.1). `vf1`–`vf4` are entry 0's clip matrix.

```
vf28.xyz = vf24.xyz - vf20.xyz          ; V  = vertex - eye                      (0x2758 upper)
vf29.y   = vf25.z ; vf29.z = vf25.w     ; MR32.yz                                (0x2758 lower)
vf27.w   = 1.0f + vf30.x                ; the CONFLICT pair, see §6.4            (0x2760)
vf29.x   = vf24.w                       ; N = (pos.w, uv.z, uv.w)                (0x2768 upper)
ERLENG P, vf28                          ; P = 1 / |V|, 24-cycle EFU              (0x2768 lower)
vf24     = vf1*vf24.x + vf2*vf24.y + vf3*vf24.z + vf4      ; clip space          (0x2770-0x2788)
vf21.xyz = vf28 * vf29                                                            (0x2790)
vf21.w   = vf21.x + vf21.y + vf21.z     ; dot(V, N)                              (0x2798-0x27a8)
DIV Q, vf0.w, vf24.w                    ; Q = 1 / w_clip                         (0x27a8 lower)
vf20.w  *= 0.0078125f                   ; = 1/128, the colour scale              (0x27b0)
vf21.w  *= -2.0f                                                                  (0x27c8)
vf31.y   = 0.5f                                                                   (0x27e0)
vf22.xyz = vf29.xyz * vf21.w            ; -2 dot(V,N) N                          (0x27e8)
vi9 -= 1 ; vi3 += 3 ; vi4 += 3
vf24     = LQ 0(vi3)                    ; read-ahead of the next position         (0x2800)
vf26.xyz = vf22.xyz + vf28.xyz          ; R = V - 2 dot(V,N) N   <-- REFLECTION   (0x2808)
vf23.z   = 1.0f                                                                   (0x2818)
vf26.xyz = vf17*vf26.x + vf18*vf26.y + vf19*vf26.z          ; R into the basis    (0x2828-0x2838)
MFP.w vf31, P                           ; vf31.w = 1/|V|, from the 0x2768 ERLENG  (0x2838 lower)
vi5 = 32 ; FMAND vi13, vi5              ; vi13 = MAC & bit5 = Sz of the MADDz     (0x2848-0x2858)
IBEQ vi13, vi0, 0x28b0                  ; R'.z >= 0  ->  skip the rim block       (0x2860)
    vf23.z = vf26.z + vf23.y            ; R'.z + 100                              (0x2870)
    vf26.z = max(vf26.z, 0.0f)                                                    (0x2878)
    ERLENG P, vf26 ; WAITP ; MFP.w vf31, P      ; vf31.w = 1/|R' with z clamped|  (0x2880-0x2890)
    vf23.z *= vf23.w                    ; * 0.01                                  (0x2890 upper)
0x28b0:
vf26.xy  *= vf31.w                      ; normalise R'.xy
vf23.z    = max(vf23.z, 0.0f)
vf27.w   *= vf20.w                      ; alpha *= colour.w / 128
vf26.xy  *= vf23.x                      ; * 1.5           (lower: vf25 = LQ 1(vi3), read-ahead)
vf27.w   *= vf23.z                      ; alpha *= the rim ramp
vf26.xy  += vf31.y                      ; + 0.5           (lower: vf20.w = LQ.w 2(vi3), read-ahead)
vf26.xy  *= Q                           ; perspective-correct
SQ.xyzw vf27 -> -2(vi4)                 ; staging[+1] = RGBAQ
SQ.xy   vf26 -> -3(vi4)                 ; staging[+0] = ST, xy ONLY
```

Key points, all **[verified]**:

* The loop is software-pipelined one vertex deep: `vf24` (position) is re-read at `0x2800`,
  `vf25` (UV) at `0x28d0` and `vf20.w` (colour `w`) at `0x28f8`, all *after* `vi3 += 3`, so each
  iteration reads the **next** vertex's three qwords and reads one vertex past the end. The
  prologue at `0x2730`–`0x2748` primes the first vertex.
* **`0x34` writes only the `ST.xy` and the whole `RGBAQ` staging lanes.** It never touches
  `XYZF2` (`+2`) and never touches `ST.z` (the `Q` the PACKED ST format uses) — those come from
  the earlier `0x08`. That is why a `0x34` list always contains `0x08` before it.
* The normal is read as `(position.w, uv.z, uv.w)` — the packing `0x68`/`0x70` produce and the
  `0x52` fixup loop reproduces (§4.4).
* `vf26.z` is clamped to `>= 0` *before* the second `ERLENG`; when the branch is skipped the
  first `ERLENG`'s `1/|V|` is reused, which is correct because the basis is orthonormal and a
  reflection about a unit normal preserves length. Interpretation **[guess]**; the code path
  **[verified]**.
* `FMAND` mask 32 = `0x20` = MAC bit 5 = **`Sz`**. The interpreter builds MAC as
  `zero` in bits 0–3 and `sign` in bits 4–7, with lane bit = `1 << (3 - component)`, so
  x→`0x80`, y→`0x40`, z→`0x20`, w→`0x10`. This matches research/13 §4.2's "mask 16 = `Sw`".
  The MAC the `FMAND` reads is the one written by the `MADDz.xyz vf26` at `0x2838` — 4 pairs
  earlier, exactly `kFmacLatency = 4`. **[verified]**
* `JR vi6` with `vi6 = 752` jumps to pc `0x1780`, i.e. `0x28`'s **full** body including its
  `LQ vf20, 38(vi0)` and `LQ vf19, 1(vi1)`. So unlike `0x40`, `0x34`'s draw uses the normal
  `(1,1,1,0.5)` bias and the `TOP+1` textured/fogged tag. The dispatcher-visible hand-back is
  `0x28`'s own `B 0x1b60` at `0x1958`. **[verified]**
* In the sampled list `0x72` (draw gate off) precedes `0x34` and `0x74` (gate on) follows it, so
  `0x34`'s pass is gated by each triangle's own flag bit 1. All 63 triangles passed.
  **[verified]**
* Side effect on VU memory: qword **339**`.x/.y/.z` is overwritten with `vi1+4`, `40` and
  `TOP+2.z`. Same scratch slot `0x30`/`0x32` use. Note `339(vi14)` (the command qword) and
  `339(vi0)` (the scratch slot) only alias if `vi14 == 0`, which the dispatcher's pre-increment
  makes impossible. **[verified]**
* **Latent `N > 1` bug**, carried over from research/13 §4.8: `vi5` is computed at `0x26b0`,
  *outside* the outer loop, so a second outer iteration would re-kick the same block and re-read
  the same parameters, while `vi14` would still advance by another 11. `0x30`/`0x32` recompute
  `vi5` each iteration. Untested — `N` was 1. **[verified]** from the disassembly; the consequence
  is **[guess]**.

### 6.3 EFU semantics the interpreter models

From `third_party/ps2recomp/ps2xRuntime/src/lib/vu/ps2_vu1_lower.cpp` and `ps2_vu1_core.cpp`:

| op | opcode | semantics | latency | marking |
|---|---|---|---|---|
| `ERLENG P, vfS` | `0x73` | `len = sqrt(x²+y²+z²)` over `normalizeOperand(vfS.xyz)`; `P = len != 0 ? 1/len : len` — a **zero-length input yields `P = 0`, not infinity** | `queueP(..., 24)` → `readyCycle = m_cycle + 24` | **[verified]** |
| `MFP.w vfT, P` | `0x64` | `applyDest(vfT, {p,p,p,p}, dest)` — reads `m_state.p` as it stands, **no stall of its own** | 0 | **[verified]** |
| `WAITP` | `0x7B` | a **no-op in the opcode switch**; the stall lives in the scheduler | stalls to `max(m_cycle, m_efuResourceReady, every valid EFU entry's readyCycle)` | **[verified]** |

`queueP` also sets `m_efuResourceReady = m_cycle + latency - 1` ("EFU throughput is one cycle
shorter than result visibility"), and every EFU-issuing pair waits on it — this is what serialises
two `ERLENG`s.

`fastCommit()` lands results: it drains the flag pipeline in order, then `Q`, then **EFU entries
in ready order**, assigning `m_state.p = oldest->value` in a loop so that when several have landed
`P` ends up holding the newest. It is called at the top of any pair whose `m_cycle` has reached
`m_nextReadyCycle`. **[verified]**

**The `0x2768` → `0x2838` hazard, and why it is safe.** The first `ERLENG` has **no `WAITP`**
before its `MFP`. `(0x2838 - 0x2768) / 8 = 26` pairs, and every pair does `++m_cycle`, so at
`L_0x2838` the cycle counter is at least `issue + 26 >= issue + 24` and `fastCommit()` has landed
`P`. The generated code at `L_0x2838` confirms it: a bare
`if (vu.m_cycle >= vu.m_nextReadyCycle) vu.fastCommit();` followed by the `MFP`, with no EFU wait.
**[verified]**. For a native handler this means: compute `1/|V|` eagerly and use it at the `MFP`
point — there is no stale-`P` case to emulate on this path. The second `ERLENG` at `0x2880` *is*
followed by `WAITP`, so it is unconditionally synchronous.

### 6.4 The same-lane write conflict at `0x2760`

```
0x2760:   ADDx.w vf27, vf0, vf30x        (upper)   ->  vf27.w = vf0.w + vf30.x = 1.0f + vf30.x
          MR32.w vf27, vf30              (lower)   ->  vf27.w = vf30.x
```

Both halves of the pair write `vf27.w`. They differ by exactly `1.0f`.

**How the interpreter resolves it.** `ps2_vu1_core.cpp`, in the pair decoder:

```cpp
const uint8_t upperWriteReg = decoded.upperUsage.vfWrite.reg;
if (upperWriteReg != 0u && (vfReadLanes(decoded.lowerUsage, upperWriteReg) != 0u ||
                            decoded.lowerUsage.vfWrite.reg == upperWriteReg))
{
    decoded.upperVfShadowReg = upperWriteReg;
    if (decoded.lowerUsage.vfWrite.reg == upperWriteReg)
        decoded.suppressedLowerVf = upperWriteReg;
}
```

and at issue time `hasLowerWrite` is `lowerWrite.reg != 0 && decoded.suppressedLowerVf !=
lowerWrite.reg`, so the lower's `queueVfWrite` never happens. **The upper wins; the lower's vf
write is dropped.** Two properties worth spelling out:

* The suppression is **register-granular, not lane-granular**. A lower write to a *different*
  lane of the same register would also be dropped. (Here both write `.w`, so it is moot — but
  Task 7 should not implement a lane-merge.)
* The related `upperVfShadowReg` machinery separately guarantees that a lower instruction which
  *reads* the upper's destination sees the **old** value. At `0x2760` the lower reads `vf30`, so
  only the suppression applies.

**How the generated code resolves it.** `vu1_d418194495c25213.cpp`, `L_0x2760`:

```c
    up = Vu1Gen::fmac<vu1ops::ArithAdd, Vu1Gen::SrcBc, 0, 1, 0, 30, false, false, false>(vu, vf, acc);
    Vu1Gen::storeVf<27, 1>(vu, vf, up);
    Vu1Gen::markVf<27, 1, 4>(vu, vf);
```

— the `ADDx.w` (dest mask `1` = `w`) and nothing else. There is **no `execLower` call in this
pair at all**; compare `L_0x2768`, which does emit `Vu1Gen::execLower(vu, vf, 0x81c0e73fu)` for
its `ERLENG`. The `MR32` is simply not generated. **[verified]**

**Proved by experiment, not only by reading code.** The alpha the packet carries is
`FTOI0(staging_alpha * q327.w)` with `staging_alpha = vf27.w * (colour.w/128) * vf23.z`, so
scaling `q327.w` up makes the two hypotheses separable. Patching `logs/vu1dump3/vu1_prog_27.bin`:

| patch | predicted A if **upper** wins | predicted A if **lower** wins | measured A (exact interpreter golden) |
|---|---|---|---|
| `q357.w = 65.0f` (original), `q327.w = 255.0f` | `∝ 66` | `∝ 65` | **4887** |
| `q357.w = 0.0f`, `q327.w = 255.0f` | `∝ 1` (non-zero) | `∝ 0` (**zero**) | **74** |

`4887 / 74 = 66.04 ≈ 66/1`. With the lower winning the second row would have been exactly 0.
**[verified] — the upper instruction's result is the one that reaches `vf27.w`, i.e.
`vf27.w = 1.0f + block[9].w`.**

Caveat worth recording honestly: this establishes what *this codebase* does (interpreter and
generated code agree, and the generated path passes `--verify` against the interpreter on this
dump). Whether real PS2 silicon resolves an upper/lower same-register conflict the same way is
**not** established here — there is no hardware capture in the corpus to check against. Everything
downstream in this project is defined against the interpreter, so a native handler must match the
table above. **[guess]** for silicon.

### 6.5 Live-in / live-out

Per-register perturbation sweep on `vu1_prog_27.bin` against an exact golden: live-in =
**`vf1`–`vf4` only**. No `vi` is live-in. **[verified]**

Inside the list, `0x34` needs `vi1` and `vi14` at its entry, leaves `vi14` advanced by 11, and
hands back through `0x28`'s `B 0x1b60`, i.e. with `vi14` pointing at the command **after** the
block. Between `0x34` and the `0x28` body nothing crosses that `0x28` does not re-derive (`0x1780`
reloads `vf19`, `vf20`, `vi4`, `vi13`, `vi2`, `vi8`). **[verified]**

---

## 7. Loop counts, measured maxima, and the clamps Task 7 must write

Every count below is guest data and needs a ceiling, exactly like `kMaxVertices` /
`kMaxTriangles` in `socom2_dispatch_0x1b50.cpp`. Maxima measured with
`python -m tools_py.vu1_headers --quiet <dumps>` and, for the counts that tool does not know
about, with a direct scan of the dumps.

| handler | count | where it is read | exit test | corpus maximum | marking |
|---|---|---|---|---|---|
| `0x70` | vertex count | `ILW.z 2(vi1)` at `0x0cc0` | `IBLTZ` / `IBGTZ` — **0 is safe** | **73** (`vu1_prog_59.bin`) over the 38 | **[verified]** |
| `0x40` | triangle count | `ILW.w 2(vi1)` at `0x17d0` | `IBGTZ` — **0 is safe** | **73** (`vu1_prog_102.bin`) over the 38 | **[verified]** |
| `0x34` outer | `N` | `ILW.z 339(vi14)` — the command qword's `z` | `IBNE vi7, vi0` — **0 means 65536 and a wrapping `vi14`; must be >= 1** | **1** (the only dispatch) | **[verified]** |
| `0x34` inner | vertex count | `ILW.z 2(vi1)` at `0x26a8` | `IBNE vi9, vi0` — **0 means 65536; must be >= 1** | **53** (`vu1_prog_27.bin`) | **[verified]** |
| `0x66` | triangle count | `ILW.w 2(vi1)` at `0x2e40` | `IBGTZ` — **0 is safe** | **38** (`vu1_prog_141.bin`, at the `0x33c8` entry) | **[verified]** |
| `0x52` | vertex count | `ILWR.w vi10, (vi4)` at `0x3138`, `vi4 = vi1 + 4` — i.e. `TOP+4.w` | `IBNE vi10, vi0` — **0 means 65536; must be >= 1** | **49** (`vu1_prog_145.bin`) over the four | **[verified]** |
| `0x52` | destination offset | `ILW.w 0(vi2)` per vertex | none — it is an unchecked store index | **0 … 96**, always even; staging qwords touched **40 … 137** | **[verified]** |

Existing maxima for context (research/12, and the comment block in `socom2_dispatch_0x1b50.cpp`):
dump2 vertices 50 / triangles 31, dump3 vertices 78 / triangles 73, dump4 vertices 76 /
triangles 44. **The residual 43 do not move those numbers**: 73 and 73 are inside the existing
`kMaxVertices = kMaxTriangles = 256`, which keeps a factor of 3.5. **[verified]**

Three clamp notes Task 7 must not miss:

1. **The `52 66 08 40 42` shape's `TOP+2` is not a header.** For those four dumps `TOP+2` is a
   bone-matrix row, and reading it as `ILW` gives `vertices = 12384 / -21943 / -21943 / -22066`
   and `triangles = 0`. The existing pre-scan refuses these lists on the first command word,
   before any header check runs — which is why the current ceiling comment can say "no list in
   the corpus is refused *by* these ceilings". **If `0x52` is ever added to the implemented set,
   the header ceiling must be skipped for lists whose first command is `0x52`, or the clamp will
   refuse every one of them.** **[verified]**

2. `0x34`'s destination range is the ordinary staging array, `40 … 40 + 3*vertexCount - 1`
   (`40 … 198` for the sampled dump), and it writes only lanes `xy` of `+0` and all lanes of `+1`.
   It also writes qword **339**. **[verified]**

3. `0x52`'s destination range is `40 … 40 + max(dstOffset) + 1` with a **stride of 2**, not 3 —
   a different layout in the same array. `40 … 137` measured. A native `0x52` would have to clamp
   each per-vertex `dstOffset` individually (it is read fresh from the stream each iteration),
   not just the count. **[verified]**

---

## 8. Live-in / live-out summary and the hand-back rules

Per-register perturbation sweeps (each of `vf1..vf31` and `vi1..vi15` replaced in turn with a
distinct value, re-run, compared against an exact `PS2X_VU1_FAST=0 PS2X_VU1_GEN=0 --no-native`
golden (the `--no-native` is the §0.7 correction; it was not needed for these dumps, which the
native dispatcher refused, but it is what makes the recipe safe in general) —
packets for the drawing shapes, packets **plus cycles, end pc and the VU-data hash** for
`0x52`, which emits nothing):

| dump | shape | live-in at `pc 0x1b50` | marking |
|---|---|---|---|
| `vu1_prog_31.bin` | `70 06 08 40 42` | `vf1 vf2 vf3 vf4` | **[verified]** |
| `vu1_prog_66.bin` | `70 08 40 42` | `vf1 vf2 vf3 vf4` | **[verified]** |
| `vu1_prog_27.bin` | the `0x34` list | `vf1 vf2 vf3 vf4` | **[verified]** |
| `vu1_prog_121.bin` | `52 66 08 40 42` | **none** | **[verified]** |
| `vu1_prog_141.bin` | (entry `0x33c8`) | `vf1 vf2 vf3 vf4`, `vi5`, `vi9`, `vi14` | **[verified]** |

So the fourth family reads a **strict subset** of research/12 §f.3's live-in set: only the
local→clip matrix `vf1`–`vf4`. None of these lists light, so `vf5`–`vf7` and `vf9`–`vf12` are
dead here.

> Caveat on the `0x33c8` row: the sweep perturbed `vi5` to `0x128`, whose bit 2 happens to be 0 —
> the same branch the original `vi5 = 2` takes — so the 22 loop-back dumps report `vi5` as not
> live. The disassembly at `0x33d8` (`IAND vi7, vi5, 4`) shows it is. `vu1_prog_141` (`vi5 = 5`)
> does flip and does report it. **[verified]**

**Hand-back rules**, on top of research/12 §f.3 and research/13 §6.3:

| handler | where it may hand back | extra requirement | marking |
|---|---|---|---|
| `0x70` | `pc = 0x1b60`, `vi1`/`vi14` correct | none — self-contained | **[verified]** |
| `0x40` | `pc = 0x1b60`, `vi1`/`vi14` correct | **`vf20` must carry the previous handler's value into it** (§3.3) | **[verified]** |
| `0x66` | `pc = 0x1b60` | `vf29.w` must be the inherited value, because it is stored to memory (§5) | **[verified]** |
| `0x34` | `pc = 0x1b60` via `0x28`'s tail, `vi14` advanced by `1 + 11` | qword 339 must be written; `0x08` must have run first (it supplies `XYZF2` and `ST.z`) | **[verified]** |
| `0x52` | **`pc = 0x33c8`, program ENDED, 0 packets** | the full `vi1..vi15` + `vf23..vf26` + `q`/`p`/`mac`/`status` + VU data image (§4.5) | **[verified]** |

---

## 9. What is still a guess, and what Task 7/8 should watch out for

1. **The `N > 1` path of `0x34`** is unexercised, and the `vi5`-outside-the-loop scheduling means
   the microcode's behaviour there is probably not what the author intended. Whoever implements
   `0x34` should refuse `N != 1` (the existing pre-scan already refuses `N < 1` for `0x30`/`0x32`
   and would need a `kInlineBlockQwords = 11` variant for `0x34` anyway). **[guess]**

2. **`0x40`'s inherited `vf20`** is the single highest-risk item in this note. It is verified, but
   it makes `0x40` the first handler in this project that is *not* self-contained in the family-A
   sense. If Task 7 implements the handlers in isolation and unit-tests them one at a time, this
   will pass every isolated test and fail the whole-list golden. Implement `0x08` and `0x40`
   together, and check the register file, not only the packets.

3. **Scope decision — settled, not a recommendation.** The controller has ruled: **Task 7
   implements `0x70` and `0x40` only. `0x52` and `0x66` stay unimplemented and are a documented
   residual**, which the sprint spec's definition of done explicitly allows. `0x34` is outside
   Task 7's scope. The reasons, for the record:
   * **`0x52` — 4 dumps of 166.** It emits zero GIF packets, it ends the program rather than
     handing back to the dispatcher, and its correctness condition spans two `MSCAL`s: the
     follow-on program at `0x33c8` is interpreted and reads `vi5`, `vi9`, `vi14` — and, on the
     accumulate path, `vi2`/`vi3`/`vi4` and `vf23`–`vf26` — out of whatever the native handler
     leaves behind (§4.5). Refusing it costs nothing; the pre-scan already hands back on the
     first command word. **[verified]**
   * **`0x66` — never dispatched from `0x1b50` at all** (0 of 5,092 + 186 dispatches in the whole
     corpus; its 3 dispatches all come from the `0x33c8` entry). A native `0x66` could only ever
     fire if a native `0x52` *and* a native `0x33c8` entry existed, so the corpus cannot verify
     it. Shipping an unverifiable handler inside the dispatcher is the larger risk.
     **[verified]**

4. **The `0x52` shape emits zero GIF packets**, so a packet-only comparison cannot validate it at
   all. Any work on `0x52` has to be validated on `state.txt`'s `vi=`, `vf=` and `data=` fields.
   **[verified]**

5. **Whether real hardware resolves `0x2760` the way this codebase does** is untested (§6.4).
   Every downstream check in this project is against the interpreter, so this is not a blocker,
   but it is the kind of thing that would show up as a 1/66 alpha error in a screenshot diff
   against a real console.

6. **Denormal flushing carries semantic weight** in §3.3: `0x40`'s black is produced by denormal
   operands being flushed to zero. A native handler that used plain IEEE arithmetic on the raw
   bit patterns would produce *almost* zero instead of zero, and `FTOI0` would still give 0 — so
   it would probably pass. Probably. Use the interpreter's `normalizeOperand` semantics anyway.

7. `vu1_headers.py` currently reports garbage for the four `0x52` dumps because it assumes
   `TOP+2` is a header (§7 note 1). Not a bug in the tool — a reason to read its output for those
   four as "not applicable" rather than "out of range".

8. **Tool caveats found while doing this work:**
   * **`PS2X_VU1_FAST=0 PS2X_VU1_GEN=0` does NOT disable the native dispatcher.** They turn off
     the fast interpreter path and the generated translation; the native registry is separate and
     defaults on (`kVu1NativeDefault`), so a golden taken with only those two knobs is produced by
     the very code it is supposed to check for every list the native dispatcher already implements.
     A `--batch` run over the 166-dump corpus with exactly that command prints a **non-zero**
     `[vu1_replay] native entered=166 ended=.. handbacks=..` (123/43 before Task 7, 161/5 after).
     Add **`--no-native`** (or `PS2X_VU1_NATIVE=0`); a correct golden run prints
     `entered=0 ended=0 handbacks=0`, and that line is the check that the golden is a golden.
     **[verified]** — added by Task 7; §0.7 and §10 are corrected accordingly.
   * **Dump basenames collide across the three dump sets, and `--batch`/`--verify` key on the
     basename.** 23 of them do (`vu1_prog_13.bin`, `vu1_prog_143.bin`, …), so a single `--batch`
     directory over `logs/vu1dump2` + `3` + `4` writes one `state.txt` whose lines `--verify` then
     matches to the *wrong* programs. On a completely unmodified tree that reports
     `FAIL: 247 mismatching field(s)` — and it does so with `--no-native` too, i.e. the interpreter
     failing against its own golden, which is proof it is a keying artefact and not a code defect.
     **Build and verify goldens per dump set.** This is the caveat most likely to look like a
     regression that is not one. **[verified]** — added by Task 7, confirmed by its reviewer.
   * `vu1_replay.exe` does **not** accept absolute `C:/...` dump paths through this shell — it
     reports `cannot open …` for a file that demonstrably exists. Run it with `cwd` at the repo
     root and relative paths. **[verified]**
   * `--verify` wants the golden **`state.txt` file**, not the `--batch` directory. Passing the
     directory prints `--verify: no lines read from <dir>` and **exits 2** — a clean, loud
     failure (`vu1_replay.cpp:578` is `return 2`), so nothing here needs fixing in the tool; it
     is only a usage note. The brief's `--verify <golden>` should be read as
     `--verify <dir>/state.txt`. **[verified]** — an earlier draft of this note claimed exit 0 and
     asked for a tool fix; that was a measurement error (`$?` read after a pipe, so it was
     `tail`'s status). Confirmed by re-running without a pipe.
   * `--trace` writes `vu1_packets.bin` into the **current working directory** and
     `logs/vu1_data_0.bin` / `logs/vu1_code.bin` into `logs/`. `logs/` is gitignored;
     `vu1_packets.bin` at the repo root is not — delete it after tracing.
   * Copy `vu1_replay.exe` **and the DLLs next to it** (`libunwind.dll`, `libc++.dll`,
     `libwinpthread-1.dll`, …) when running a private copy; the exe alone fails with
     `error while loading shared libraries: libunwind.dll`.

---

## 10. Commands used

```bash
# selection: group all 166 dispatcher dumps by list content
awk -F'cmds=' '{print $2}' logs/vu1entry0/famBC_dumps.txt | sort | uniq -c | sort -rn

# histograms (42 fourth-family dumps, the one 0x34 dump, the 25 startPc=0x33c8 dumps)
dist/vu1_replay.exe --pchist <hist.bin> <dumps>
python <hist.bin -> ranges split at jump-table targets, and per-command counts from slot pcs>

# the jump table itself
python tools_py/vu1dis.py --start 0x1ba0 --count 128 logs/vu1dump3/vu1_prog_27.bin

# handler disassembly
python tools_py/vu1dis.py --start 0x0cb8 --count 42 logs/vu1dump3/vu1_prog_31.bin   # 0x70
python tools_py/vu1dis.py --start 0x1950 --count 10 logs/vu1dump3/vu1_prog_31.bin   # 0x40
python tools_py/vu1dis.py --start 0x3100 --count 60 logs/vu1dump3/vu1_prog_121.bin  # 0x52
python tools_py/vu1dis.py --start 0x2e28 --count 36 logs/vu1dump3/vu1_prog_121.bin  # 0x66
python tools_py/vu1dis.py --start 0x2690 --count 90 logs/vu1dump3/vu1_prog_27.bin   # 0x34

# executed command order (default step cap is far too low)
PS2X_TRACE_VU_STEPS=4000000 dist/vu1_replay.exe --trace logs/vu1dump3/vu1_prog_31.bin
python <pc two steps after each 0x1b90 -> jump-table slot -> command word>

# exact goldens, and the regression check for Task 7
# ... note --no-native: FAST/GEN do NOT disable the native registry (section 9.8), and goldens
# must be built PER DUMP SET, because basenames collide across vu1dump2/3/4 (section 9.8).
PS2X_VU1_FAST=0 PS2X_VU1_GEN=0 dist/vu1_replay.exe --batch <dir> --no-native <that set's dumps>
dist/vu1_replay.exe --verify <dir>/state.txt --native --regs all <that set's dumps>

# poison tests (patch one data qword of a COPY, re-batch, compare the .pk byte for byte)
#   q26 / q38 / TOP+3.w / q327.w        -> 0x40's tag source and 0x70's scale
#   TOP+4 + 3*(TOP+2.z + 2)             -> 0x40's inherited vf20 (two dumps, plus neighbours)
#   q357.w with q327.w = 255.0f         -> the 0x2760 upper-vs-lower decision

# per-register live-in sweep (vf1..vf31, vi1..vi15, one at a time, vs an exact golden)
python <sweep; compare .pk for drawing shapes, state.txt fields for 0x52>

# measured maxima
python -m tools_py.vu1_headers --quiet <dumps>
python <scan TOP+4.x / TOP+4.w / (TOP+5+2k).w for the 0x52 shape>
```

Interpreter / generated-code references used for §6.3 and §6.4:
`third_party/ps2recomp/ps2xRuntime/src/lib/vu/ps2_vu1_lower.cpp` (cases `0x64` `MFP`, `0x73`
`ERLENG`, `0x7B` `WAITP`), `…/vu/ps2_vu1_core.cpp` (`queueP`, `fastCommit`, `updateFmacFlags`,
`laneForComponent`, the `suppressedLowerVf` / `upperVfShadowReg` decode),
`…/include/runtime/ps2_vu1.h` (`kFmacLatency = 4`), and
`…/vu/generated/vu1_d418194495c25213.cpp` (`L_0x2760`, `L_0x2838`, `L_0x2858`, `L_0x2880`,
`L_0x2888`).
