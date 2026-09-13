# 24 — Frostfire walkability: collision geometry, connectivity, and a route between the spawns

**Status: zero-run research wave rw24 (Sprint 5, 2026-09-13).** No build, no launch. Inputs: the two
post-vf0 Frostfire images `logs/parity/frost{A,B}_probe600_vf0.rdram`, the launch 3c actor rows
(`logs/run_[AB]_20260913_115809.log` via `verdict_core.parse_log`), research/23 §1.1 and §7, and the decomp
of `FUN_002d3030`, `FUN_003084f0`, `FUN_00307fa0`, `FUN_001bfc30`, `FUN_002dc620`. Scripts lived in the
session scratchpad (`rw24/`) and will not survive; §2 lists enough to rebuild them.

- **[verified]** = computed from the RDRAM image, the decomp or the 3c rows during this wave.
- **[inference]** = reasoned from those, not observed in the game.

Output route table: `tools_py/parity/routes/frostfire_v2.json` (same loader schema as `frostfire.json`;
`route_for("frostfire_v2", "A")` loads it).

---

## 0. Bottom line

1. **The spawns connect on geometry.** A's spawn (796, 100, 614) and B's spawn (536, 143, 1254) are in the
   same walkable component at body radius 3.5, 4.5 and 5.5 (24394 / 22820 / 20375 nodes). [verified]
2. **The connection is on the lower floor, not the upper.** A route A→B runs A's lower trail, then an
   **underpass beneath the walkway deck** (x 705–735, z 975–1000), then B's lower trail and **B's own ramp**
   (entered square at (705, 100, 1223), climbed on its centreline z 1223.5) up to B's floor. It is 865
   units long, 590 of them unwalked in 3c, minimum clearance 11.1. The reverse is the same corridor, 857
   long, 574 unwalked, clearance 10.2. Every leg re-validates on the geometry every 2 units.
   [verified on geometry; walkability in the game is inference, §7]. Revised after independent review (§9).
3. **The upper floor is split into two regions by a closed door.** A's walkway region (x 530–760,
   z 730–1110) and B's upper region (x 290–600, z 1100–1270) come within 15 units at a door leaf
   (`door_slab` model, image A `0x122c8c0`, x 576–589, z 1117–1118, y 142–165). With that door leaf removed they join, and the
   walkway-to-B-spawn path is 420 units. [verified geometry; that it is a door that opens is inference]
4. **The "z ≈ 994–1022 barrier" is not a same-floor barrier.** A (y 142) stopped against the walkway's
   north railing at z 999–1000 (13 high); beyond it there is no floor at y 142, only the y 100 floor 42
   below. B (y 100) paused at (743, 100, 1023) on open floor, 23 units from the nearest wall, then turned
   west. It was not blocked. The two stops are on different floors. [verified geometry; B's pause as a
   controller event is inference]
5. **A's climb in 3c was the wrong way.** A's ramp (x 680–705, z 891–975) leads only to the walkway deck.
   The deck is a dead end at y 142: railing to the north, closed doors east (764.5, 984.5) and, via the
   building, north-west (582.5, 1117.5). [verified]

---

## 1. Collision data in the image

### 1.1 What was extracted [verified]

The walk covers every atom in every cell of the 8×9 grid (dimension 160, origin 0): 72 `CCell` nodes
(type 10, children at `+0xf0[..+0xec]`, child model at `+0x64`), 414 type-1 models and 117 type-2 atoms.
Each model is visited once, with its **world matrix composed** down the tree:

- `FUN_003084f0(m)` tests for identity: translation 0 and diagonal 1.0. A non-identity model is pushed with
  `FUN_00307fa0(0x44d750, m, 1)`, which runs `FUN_001bfc30(top+0x40, top, m)`. In row-vector form that is
  `world(m) = local(m) × world(parent)`. `FUN_003085c0` transforms `(x, y, z, 1)` by it.
- Model gate: `+0x5c` bit 0 and `+0x5d` bit 4. Every surface extracted has vtable `0x406690` (`CDIPoly`).
  The grid does hold 50 `CDIBBox` surfaces (vtable `0x406670`), all in the two player actor models, which
  are skipped. [verified by review; corrects the first version of this note]
- Model addresses in this note are valid in image A (`frostA_probe600_vf0.rdram`) only. The polygons are
  identical in B, but the models sit elsewhere: B's door slabs are `0x122dda0`, `0x122f650` and
  `0x122f9a0`.
- Type-2 atoms: two are the player actors (`+0x5c = 0x8184b857`, bounds 24×20×28, at both spawns). They are
  skipped. The other 64 are props with their own polygons: 20 crates of 10×13×10, 13 objects of 40×30×40,
  and larger roof and tree pieces. **They are included.** The research/23 walker skipped them, and it
  flagged rather than applied model transforms.

Result: **3318 world-space polygons**, identical in both images (3318/3318 vertex-equal). Geometry bounds:
x 120–1200, y 40–241, z 322–1280. The grid extent x 0–1280, z 0–1440 holds nothing outside these bounds.

### 1.2 Surface bits, as used here

| bit (`surf+8`) | meaning here | evidence |
|---|---|---|
| 0 | ground: the type-1 vertical probe tests it | `FUN_002d3030` type-1 branch [verified]; 100 % agreement with 3c (§3) [verified] |
| 1 | type-2 probe (column/side) tests it; set on **all 3318** polygons, so it does not discriminate, and the wall test is effectively bit 18 plus the normal | `FUN_002d3030` type-2 branch [verified]; that movement walls use these polygons is [inference] |
| 18 | skipped when `DAT_0044d758 == 0` | decomp [verified]; the 3c trails pass through such polygons (§4.1) [verified] |
| 10..17 | material; flag word `0x44f358[m]+0x3c` bit 0 = VOLUMETRIC, bit 1 = LIQUID | no ground polygon on Frostfire uses a flagged material (0, 3, 7, 25, 26, 28, 30 only) [verified] |

Record layer masks are `0x23` (layers 0, 1, 5). Every polygon is on layer 0, 1 or 5, so none is masked
out. [verified]

---

## 2. Method

1. **Height field.** A 5-unit lattice over the geometry bounds (x 115–1205, z 320–1285): 42486 columns.
   Each column gets **every** ground hit: bit 0 set, bit 18 clear, material not VOLUMETRIC/LIQUID, point
   inside the polygon in xz, y from the Newell-normal plane. Hits within 0.5 are merged.
   - Columns by hit count: 0 → 14229, 1 → 15463, 2 → 10509, 3 → 2065, 4 → 217, 5 → 3.
   - The walkway at y 142 over the ground at y 100 is a 2-hit column.
2. **Node validity.** A hit is a standable node when all of the following hold:
   - surface |n_y| ≥ 0.85;
   - no polygon over the point at y+6..y+20 (1441 hits fail);
   - **the game's own selection reproduces it**: first hit per model in surface order, origin y+5, the
     highest candidate ≤ origin+1 else the lowest, reject if > y+20, result within 2.5 of the node
     (1007 fail, mostly under ramps);
   - clearance ≥ body radius (below).

   35254 nodes remain at radius 3.5.
3. **Walls.**
   - A wall is any polygon with bit 1 set, bit 18 clear and |n_y| < 0.7. Bit 1 is set on all 3318
     polygons, so in practice the test is bit 18 plus the normal.
   - That these polygons block the mover is [inference]. The movement-collision routine is not decompiled;
     the support is the 3c stand-off distances of 4.4–5.8 at wall planes (§4.1).
   - **Body column:** y+6..y+20. The 20 comes from the actor bounds (height 20) and from 3c: A crossed
     polygons whose base sat 23 units above its feet (§4.1). The 6 is the selection step window.
   - **Clearance:** the minimum 3-D distance from the column to the wall polygons.
   - **Radius:** 3c rows never come closer than 3.6 at a corner or 4.4 at a plane (§4.1). Radius 3.5 is used
     for connectivity, and 4.5 and 5.5 for sensitivity.
   - **Edges:** an edge is blocked when the segment between the two nodes crosses a wall polygon at y+6,
     +13 or +20.

   **Walls are visible to this method.** They are polygons in the same model lists, so the vertical-probe
   blind spot does not apply. The blind class that remains is whether the mover really collides with them
   (§7).
4. **Step limit, derived from 3c.** Every non-zero per-row y change in 3c lies on a ramp polygon at grade
   0.5 (A: 83 rows, B: 12). The only off-ramp change is 0.93, the spawn settle. The link rule is therefore
   |Δy| ≤ 0.5·d + 1.0: continuous surfaces and grade-0.5 ramps, no ledges. [verified]
5. **Connectivity.** 8-neighbour links, kept only when present in both directions. Connected components
   come from a flood fill. Upper-only floods (y ≥ 140.5) are started from A's walkway and from B's spawn.
6. **Route.**
   - A* from each spawn to a node on the other side's floor (|y − floor| < 1) within 35 units in xz of the
     other spawn.
   - Cost: 1.0 per unit on ground within 6 units horizontally and 2.5 vertically of any 3c row, 1.5
     elsewhere, plus 0.25 × (10 − clearance) when the clearance is under 10.
   - The path is thinned greedily to legs of ≤ 55 units that keep clearance ≥ 6. Waypoints were then
     moved by hand: to x 718–720, away from the ramp side wall (x 705) and the underpass jambs; and, after
     review (§9), onto B's ramp centreline and past the container at x ≈ 806.
   - Along a leg the height follows the game's own selection from the current y. That is how a mover on
     the y 100 floor steps onto the ramp foot.
   - **Every leg is re-walked on the raw geometry every 2 units:** a ground hit continuous with the last,
     |n_y| ≥ 0.85, game selection reproduced, clearance, and no wall crossing at y+6/+13/+20. All 41 legs
     of the revised routes pass.

---

## 3. Height-field agreement with launch 3c [verified]

| side | unique rows | a ground hit within [−3, +1] of the actor y | game selection returns the actor's floor (±1.5) | residual median / p99 / max |
|---|---|---|---|---|
| A | 569 | 569 (100.0 %) | 569 (100.0 %) | 0.004 / 0.006 / 0.007 |
| B | 583 | 583 (100.0 %) | 583 (100.0 %) | 0.000 / 0.004 / 0.933 (spawn settle) |

The composed transforms are therefore right. Before composition, the ground under A (T = (960, 0, 800)) would
not have matched.

---

## 4. Walls, radius, and the 3c stops

### 4.1 What 3c's trails say about collision [verified]

- **Crossings.** Consecutive 3c rows under 15 units apart were tested against every non-horizontal polygon
  at body heights 3/8/15/25/40. Only three kinds of polygon are crossed:
  - bit-18 polygons: `0x11ab0f0` #0/#1 at x 676/680, z 980–995, y 142–166, a doorway volume. Crossed at +3;
  - polygons whose base is ≥ 23 above the feet: `0x11ac4c0` #15/#16 and `0x11aa4b0` #19 at y 165+, while
    A was at 142;
  - one polygon at +40.

  **No bit-18-clear polygon is crossed inside y+3..y+20.**
- **Minimum clearance** from 1152 unique rows to such walls: A 3.6 at a wall corner (758, 142, 988), then 4.4
  to 4.9 at planes; B 4.4 to 5.5 at planes (the review measured 4.4–5.8). The mover appears to slide along
  walls at about 4.4–5.8. That these walls are what stops it is [inference]: the movement-collision routine is
  not decompiled.

### 4.2 The z ≈ 994–1022 stops

**A** (t 550–630 and 650–670, y 142, x 713–758, z 982–994):
- It stands on the walkway deck `0x11acad0` surface 0 (y 142, x 680–760, z 975–1000).
- The deck's north edge carries a **railing** `0x11acad0` #5/#6 (z 999/1000, y 142–155, 13 high). At radius
  about 5, A stops at z ≈ 994–995.
- North of z 1000 there is **no y 142 floor**. The only ground there is `0x11a8280` at y 100, 42 below.
- The deck's east end is a door leaf `0x122e170` (x 764–766, z 978–991, y 142–165, with handle cut-out
  `0x122e280`, material 9) inside wall `0x11b0940`. A's corner contact at (758.4, 142, 987.8) is at that
  door.

This is a floor edge with a railing, not a wall between two walkable areas. [verified]

**B** (t 582.3–586.1, y 100, x 743, z 1023):
- It stood still for about 4 s, **23 units** from the nearest wall. That wall is `0x11acad0` #12 (x 735–760,
  z 1000, y 100–142), one jamb of the underpass mouth.
- Every node from z 1000 to 1030 at x 710–760 is open, with clearance ≥ 11.
- B then turned west to (693, 1033). A mover pushing into a wall would sit about 5 units from it, not 23.

**B was not blocked** [verified geometry]. Its pause is a controller event [inference]. At that moment A was
at (735.8, 142, 992.8), directly above and 52.4 away in 3-D. That is KNOWN's closest approach.

**Why "a barrier" appeared.** Both stops lie in one xz band, but 42 apart vertically, on either side of the
deck edge. From below, the lower floor continues south under the deck through a 30-wide underpass:
- side walls `0x11acad0` #13/#14 at x 705 and x 735 (z 975–1000, y 100–141);
- end walls #11 (x 680–705) and #12 (x 735–760) at z 1000, and #15/#16 at z 975, which leave x 705–735
  open;
- the deck overhead at 42, well above the body height of 20.

---

## 5. Component map

### 5.1 Components (radius 3.5) [verified]

| component | nodes | x | z | y | contents |
|---|---|---|---|---|---|
| c0 | 24394 | 130–1190 | 330–1270 | 63–143 | both spawns; the whole lower floor; both ramps; the walkway deck; B's upper region |
| c87 | 2241 | 760–980 | 740–1000 | 230 | roof |
| c43 | 1481 | 520–680 | 880–1120 | 202 | roof over the walkway building |
| c8, c38, c40, c65, c1, c3, c56 … | ≤ 723 each | — | — | 155–216 | roofs and tops; 100-level boxed pockets (c41, c66) |

Inside c0, the upper floor is two regions when only y ≥ 140.5 nodes may be used:

| upper-only region | nodes | x | z | reached from lower by |
|---|---|---|---|---|
| **W**, A's walkway region (from (720, 142, 985)) | 1041 | 530–760 | 730–1110 | A's ramp (x 680–705, z 891–975) |
| **U**, B's upper region (from B's spawn) | 1703 | 290–600 | 1100–1270 | B's ramp (x 600–680, z ≈ 1212–1235) |
| gap | — | closest (545, 142, 1110) ↔ (545, 142, 1125), 15 units | — | door leaf `0x122c8c0` at (576–589, 1117–1118) closed; with it removed, W joins U |

### 5.2 Map

The map is 10-unit cells, x 380–830 (left to right), z 1290 (top) to 580 (bottom).

- `L` = lower floor (y ≤ 101) in c0.
- `r` = ramp or intermediate y.
- `W` / `U` = the upper-only regions above. Lower case means the same cell also has lower-floor ground.
- `u` = other upper c0 ground.
- `.` = no standable node.
- `*` = route cell on lower ground or a ramp; `+` = route cell on upper ground.

```
       x  4         5         6         7         8
 1270  .UUUUUUUUUUUUUUUUUUUUULLLLLLLLLLLLLLLLLLLL....
 1260  UUUUUUUUUUUUUUUUUUUUUULLLLLLLLLLLLLLLLLLLLL...
 1250  UUUUUUUUUUUUUUU++UUUUULLLLLLLLLLLLLLLLLLLLLL..      B spawn (536,1254)
 1240  UUUUUUUUUUUUUUUU+++UUULLLLLLLLLLLLLL...LLLLLL.
 1230  UUUUUUUUUUUUUUUUUU++++urrrrrrrrLLLLL....LLLLLL      B's ramp z~1225
 1220  UUUUUUUUUUU.UU.UUUU++++********LLLLL.....LLLLL
 1210  uuuuuuuuuuuuuLLuuuuuuuLLL.....**LLLL......LLLL
 1200  uuuuuuuuuuuuuuuuuuuuuuLLLLLLLLL**LLL.......LLL
 1180  UuuUUUUUUUUUUUuuuuuuuuLLLLLLLLLL**LL.........L
 1160  UuuUUUUUUUUUUUUUUuuuuuLLLLLLLLLLL**L..........
 1140  UuuUUUUUUUUUUUUUUUUUUULLLLLLLLLLLL*L..........
 1120  .LLUUUUUUUU.U.UUUUUUUULLLLLLLLLLLL*L..........      door 0x122c8c0 at (582,1117)
 1110  rrrrrrruUULLLL..WWWWW..LLLLLLLLLLL*L..........
 1100  rrrrrrruUULLLL..WWWWWW..LLLLLLLLLL**L.........
 1080  LLLLLLLLLLLLLL..WWWWWW....LLLLLLLLL*LLL.......
 1060  LLLLLLLLLLLLLL...WWWWWWWWWW.LLLLLLL*LLLLLLLLLL
 1040  LLLLLLLLLLLLLL.....WWWWWWWW...LLLLL*LLLLLLLLLL
 1020  LLLLLLLLLLLLLL.WWWWWWWWWWWW...LLLL**LLLLLLLLL.      B paused (743,1023)
 1010  LLLLLLLLLLLLLL.WWWWWWWWWWWW...LLLL**LLLLLLLLL.
 1000  LLLLLLLLLLLLLL.WWWWWW.........LLL***LLLLLLLL..      underpass mouth x705-735
  990  LLLLLLLLLLLLLLLwwWWWWWWWWWWWWWWWW++wWW.uuLLLLL      deck + railing z999; A stuck
  980  LLLLLLLLLLLLLLLwwwwwwWWWWWWWWWWWW++wWWWuuLLLLL      ('+' here = under the deck)
  970  LLLLLLLLLLLLLLLwwwwwwWWWWWWWWWwww**LLL.uuLLLLL
  960  LLLLLLLLLLLLLL.wwwwwwWWWWWWWWWrrr**LLL.uuLLLLL      A's ramp x680-705
  940  ........LLLLLL.LL.LLL...WWWWWWrrr**LLL.uuLLLL.
  920  ........LLLLLL.LL.LLLLLLwWWWWWrrr**LLL.uuLLLLL
  900  ........LLLLLL.LL.....LLwWWWwwrrr*LLLL.rrLLL..
  880  ........LLLLLL.LL.....LLL.LwLLLL**L..L.rrLLL..
  860  ........LLLLLL.LLLL..LLLwwwwwwL**LLLLL.rrLLLLL
  840  ........LLLLLL.......LLLwwwwww**LLLLLLLrrLLL..
  820  ........LLLLLL.......LLLwwwWww*LLLLLLLLLLLLLLL
  800  ........LLLLLL.......LLLwwwWww*LLLLLLLLLLL.LLL
  780  LLLLLLLLLLLLLL.......LLLwwwWww**LLLLLLLLLL.LL.
  760  LLLLLLLLLLLLLL.......LLLwwwWwwL*LLLLLLLLLL.LLL
  740  LLLLLLLLLLLLLL.......LLLwwwwwwL*LLLLLLLLLL....
  720  LLLLLLLLLLLLLL..........LLLLLLL******LLLLLLLLL
  710  LLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLL********LLLL
  700  LLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLL*LLLL
  680  LLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLL....*LLLL
  660  LLLLLLLLLLLLLLLLLLLLLLLLLLLLLL....LLL....**LLL
  640  .......LLLLLLLLLLLLLLLLLLLLLLL....LLLLLLL**LLL
  620  .......LLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLLL*LLLL      A spawn (796,614)
  600  .......LLLLLLLL.......LLLLLLLLLLLLLLL....LLL..
```

Some rows are omitted for width. The `+` at z 980–990 are route cells on the lower floor under the deck; the
cell label shows the deck.

---

## 6. Routes (revised after independent review, §9)

Both are in `frostfire_v2.json` as `routes.A` and `routes.B`; the harness reads only these. The top-level
`mover_A` / `mover_B` sections are kept **for documentation only** and are not read by the harness. Field
meanings:

- **Walked:** each 2-unit sample of the leg is within 6 units horizontally and 2.5 vertically of any 3c row,
  from either side.
- **Clearance:** numeric, the measured minimum distance from the body column to a wall polygon, searched to
  60 units. A leg's value is the minimum over its 2-unit samples.
- **Source:** "3c" cites the nearest row within 6 units. "HF" cites the height-field cell and its ground
  polygon (image-A address).
- The route overlay in the §5.2 map shows the first version. The revised routes differ at the container
  (x ≈ 806) and at B's ramp (z 1223.5).

### 6.1 A → B's floor (y 142): 20 legs, 864.6 long, 274.2 walked, **590.4 unwalked**, min clearance **11.1**, ends 34.7 from B's spawn

| # | x, y, z | leg len / walked | leg min clr | floor y | source |
|---|---|---|---|---|---|
| 0 | 795.7, 100, 613.6 | spawn |  |  | 3c A t=393.12 |
| 1 | 806, 100, 665 | 52.4 / 31.1 | 12.2 | 100 | HF `0x11a4c10` #0 |
| 2 | 806, 100, 712 | 47 / 0 | 16.0 | 100 | HF `0x11bd410` #0 |
| 3 | 760, 100, 720 | 46.7 / 46.7 | 24.4 | 100 | 3c A t=467.26 |
| 4 | 745, 100, 720 | 15 / 15 | 26.3 | 100 | 3c A t=467.53 |
| 5 | 695, 100, 730 | 51 / 43.1 | 15.5 | 100 | 3c A t=469.62 |
| 6 | 690, 100, 780 | 50.2 / 30.9 | 15.9 | 100 | 3c A t=473.51 |
| 7 | 685, 100, 830 | 50.2 / 48.3 | 31.0 | 100 | 3c A t=475.75 |
| 8 | 718, 100, 872 | 53.4 / 5.9 | 17.4 | 100 | HF `0x11a5140` #1 |
| 9 | 720, 100, 915 | 43 / 0 | 13.8 | 100 | HF `0x11a5140` #1 |
| 10 | 720, 100, 960 | 45 / 0 | 15.0 | 100 | HF `0x11a5140` #1 |
| 11 | 720, 100, 1005 | 45 / 0 | 15.0 | 100 | HF `0x11a8280` #3 |
| 12 | 735, 100, 1055 | 52.2 / 11.6 | 16.0 | 100 | HF `0x11a8280` #1 |
| 13 | 720, 100, 1100 | 47.4 / 7.9 | 23.3 | 100 | HF `0x11a8280` #2 |
| 14 | 715, 100, 1155 | 55.2 / 0 | 16.6 | 100 | HF `0x11a8750` #1 |
| 15 | 712, 100, 1190 | 35.1 / 0 | 20.2 | 100 | HF `0x11a8750` #1 |
| 16 | 705, 100, 1223 | 33.7 / 0 | 23.4 | 100 | HF `0x11a8750` #1 |
| 17 | 680, 102, 1223.5 | 25 / 0 | 11.7 | ramp 100–102 | HF `0x11ae600` #0 |
| 18 | 640, 122, 1223.5 | 40 / 0 | 11.7 | ramp 102–122 | HF `0x11ae600` #0 |
| 19 | 600, 142, 1223.5 | 40 / 22 | 11.7 | ramp 122–142 | 3c B t=566.67 |
| 20 | 565, 142, 1235 | 36.8 / 11.6 | 11.1 | 142 | HF `0x11a9160` #7 |

**Confidence: medium-high.**
- Ground, selection and wall geometry are verified on every leg. Wall blocking is [inference] (§7).
- The unwalked share rose from 393 to 590 in the revision. The corrections deliberately leave the 3c trails:
  the container pinch, the square approach to the ramp, and the ramp centreline (B walked z 1229–1231,
  6.5 off it).
- **Pinch points:**
  - waypoints 8–10 stay at x ≥ 712, clear of the ramp side wall at x 705 (z 891–975) and the pillar
    `0x12397b0` (x 733–745, z 881–893);
  - waypoint 11 is the underpass centre (jambs at x 705 and x 735);
  - waypoints 16–19 enter B's ramp square: the mouth spans z 1211.6–1235.2, and the centreline z 1223.5
    gives 11.7 clearance;
  - waypoints 1–2 pass the container climb `0x1222480` (walls #2/#3) at x 806.

### 6.2 B → A's floor (y 100): 21 legs, 856.8 long, 283.2 walked, **573.5 unwalked**, min clearance **10.2**, ends 33.0 from A's spawn

| # | x, y, z | leg len / walked | leg min clr | floor y | source |
|---|---|---|---|---|---|
| 0 | 535.7, 142, 1253.6 | spawn |  |  | 3c B t=387.12 |
| 1 | 580, 142, 1235 | 48 / 23.1 | 19.3 | 142 | HF `0x11a9160` #7 |
| 2 | 600, 142, 1223.5 | 23.1 / 7.7 | 10.2 | 142 | 3c B t=566.67 |
| 3 | 640, 122, 1223.5 | 40 / 20 | 11.7 | ramp 122–142 | HF `0x11ae600` #0 |
| 4 | 680, 102, 1223.5 | 40 / 0 | 11.7 | ramp 102–122 | HF `0x11ae600` #0 |
| 5 | 705, 100, 1223 | 25 / 0 | 11.9 | ramp 100–102 | HF `0x11a8750` #1 |
| 6 | 712, 100, 1190 | 33.7 / 0 | 23.0 | 100 | HF `0x11a8750` #1 |
| 7 | 715, 100, 1155 | 35.1 / 0 | 20.0 | 100 | HF `0x11a8750` #1 |
| 8 | 720, 100, 1100 | 55.2 / 0 | 16.6 | 100 | HF `0x11a8280` #2 |
| 9 | 735, 100, 1055 | 47.4 / 7.9 | 24.2 | 100 | HF `0x11a8280` #1 |
| 10 | 728, 100, 1030 | 26 / 2 | 30.8 | 100 | 3c B t=586.64 |
| 11 | 720, 100, 985 | 45.7 / 9.9 | 12.2 | 100 | HF `0x11a8280` #3 |
| 12 | 720, 100, 935 | 50 / 0 | 15.0 | 100 | HF `0x11a5140` #1 |
| 13 | 720, 100, 890 | 45 / 0 | 12.8 | 100 | HF `0x11a5140` #1 |
| 14 | 700, 100, 860 | 36.1 / 0 | 13.9 | 100 | HF `0x11a5140` #0 |
| 15 | 685, 100, 840 | 25 / 7.7 | 28.6 | 100 | 3c A t=476.00 |
| 16 | 690, 100, 790 | 50.2 / 50.2 | 31.2 | 100 | 3c A t=473.75 |
| 17 | 690, 100, 735 | 55 / 51.1 | 13.5 | 100 | 3c A t=472.54 |
| 18 | 740, 100, 715 | 53.9 / 39.9 | 14.4 | 100 | 3c A t=467.79 |
| 19 | 790, 100, 712 | 50.1 / 44.3 | 22.0 | 100 | 3c A t=462.68 |
| 20 | 806, 100, 690 | 27.2 / 19.4 | 12.9 | 100 | HF `0x11a4c10` #0 |
| 21 | 806, 100, 645 | 45 / 0 | 16.0 | 100 | HF `0x11a4c10` #0 |

**Confidence: medium-high**, for the same reasons. The 10.2 minimum is at (595, 142, 1226), where the path
turns from B's upper floor onto the ramp top.

### 6.3 Alternatives [verified geometry / inference]

- **Upper-floor route** (walkway → building x 523–599 → door (582.5, 142, 1117.5) → B's region): 420 units
  from the deck to B's spawn, and 807 from A's spawn to B's spawn. It needs the door leaf `0x122c8c0`
  **open**, and the doorway is 13 wide (576–589) against a radius of about 4.5. Not recommended.
- **The 3c `frostfire.json` A route** climbs A's ramp onto the deck, a dead end for reaching B's floor.
  Its B route does descend correctly, via B's ramp.

---

## 7. Blind classes

1. **Movement collision primitive [inference].** Walls are taken to be bit-18-clear, non-horizontal
   `CDIPoly`s (bit 1 is set on every polygon) against a column y+6..y+20 of radius about 3.5–5.8. The
   movement-collision routine is **not decompiled**, so wall blocking is an inference. It is supported by 3c:
   no such wall crossed, stand-off distances of 4.4–5.8 at wall planes, and crossings only of bit-18 or high
   polygons.
2. **Dynamic doors [verified geometry / inference state].** Three models named `door_slab` (name pointer at
   model `+0x90`), with handle cut-outs (material 9), are in the grid. Their positions in both images, and at
   3c round start, are consistent with closed:
   - (582.5, 142, 1117.5): image A `0x122c8c0`;
   - (764.5, 142, 984.5): image A `0x122e170`;
   - (891, 100, 996): image A `0x122e4c0`.

   Image B's slabs are `0x122dda0`, `0x122f650` and `0x122f9a0`. The ELF carries "OPEN DOOR" / "CLOSE DOOR"
   strings, so doors are interactive and their live state is **not guaranteed**. Neither route passes a door.
3. **Props and actors.** The 64 prop objects are included **at their positions in the images**. Crates at
   (756–768, 100, 750–774) sit 7–19 units from the old diagonal, which is why the route follows A's trail.
   Props that move, break or respawn per round, other players' actors, and AI actors are not modelled.
4. **Ledges and drops.** Links allow only continuous grade ≤ 0.5. The selection window would accept a
   step-up of up to about +6, and dropping off a deck edge (for example 142 → 100) is physically possible.
   Neither is used. Both could create shorter real paths the graph does not show.
5. **Sampling.** Nodes are 5 units apart. Thin walls are covered by segment tests, but a gap narrower than
   about 10 between two nodes could be under- or over-counted. Both revised routes keep clearance ≥ 10.2.
6. **Mover behaviour.** Camera-steered steps, corner sliding and overshoot are not modelled. Waypoints are ≤ 55
   apart and centred in corridors. The harness counts a waypoint reached within 20 units and aims within
   ±12°. The review's Monte Carlo on the first version put 21 of 37 ramp approaches within 4.5 of the ramp
   side walls; the revision squares that approach (§9). The underpass mouths (30 wide) are the remaining
   drift risk. The Monte Carlo was not re-run in this wave.
7. **Not blind:** walls invisible to a vertical probe. The polygons are read directly, so this class does
   not apply here.

---

## 8. Claims index

| claim | status |
|---|---|
| Both spawns in one walkable component at r = 3.5 / 4.5 / 5.5 | [verified] |
| Height field matches 3c: 1152/1152 rows, game selection 1152/1152 | [verified] |
| Model transforms compose `local × parent` (row vectors) | [verified] decomp `FUN_001bfc30` / `FUN_00307fa0` |
| Upper floor split between W and U at door leaf `0x122c8c0`; joined with it removed | [verified] geometry |
| Underpass x 705–735, z 975–1000 at y 100, deck 42 overhead | [verified] |
| A's 3c stop = railing at z 999–1000 plus closed east door | [verified] geometry, consistent with the rows |
| B's 3c pause at z 1023 was not a collision | [verified] 23 units of clearance; controller cause [inference] |
| Both routes walkable in the game | [inference]: geometry [verified] per leg; blind classes §7 |
| The three `door_slab` models are interactive (OPEN/CLOSE DOOR strings); live state not guaranteed | [verified by review] strings and names; live behaviour [inference] |
| 50 CDIBBox surfaces exist, all in the skipped player actor models | [verified by review] |
| Wall polygons block the mover | [inference]: collision routine not decompiled; 3c stand-offs 4.4–5.8 |

---

## 9. Corrections after independent review (2026-09-13)

The review independently confirmed the geometry: 3318 polygons, identical in both images; floor and clearance
along both routes every 2 units; underpass headroom 41.25; 1175/1175 3c rows agree. Changes made:

1. **Ramp-foot drift (route A, mirrored on B).**
   - The old 45° approach from (700, 1205) is replaced by a square approach: (712, 1190), then
     (705, 100, 1223).
   - The ramp waypoints are (680, 102, 1223.5), (640, 122, 1223.5) and (600, 142, 1223.5), on the mouth's
     centreline (the mouth spans z 1211.6–1235.2). Clearance there is 11.7.
   - Route B uses the same points in reverse.
2. **Container pinch at (790, 690).** The first version passed at 6.1–7.2 from walls #2/#3 of `0x1222480`,
   the `climb` model under `container_blue01`. Waypoints now run along x 806, where clearance is 12.2–16.0
   on route A and 12.9–16.0 on route B.
3. **Clearance re-check** every 2 units on all 41 legs, measured to 60 units. Minimum clearance is now 11.1 on
   A (at (596, 1225)) and 10.2 on B (at (595, 1226)). Nothing failed.
4. **Wording:** CDIBBox (§1.1), image-B addresses (§1.1, §7), `door_slab` naming and OPEN/CLOSE DOOR (§7),
   bit 1 on every polygon (§1.2, §2), and wall blocking labelled [inference] (§2, §4.1, §7).
5. **JSON:** `row_t` is null on every height-field waypoint; `clearance` and `min_clearance` are numeric
   everywhere; `mover_A` / `mover_B` are kept for documentation only.
