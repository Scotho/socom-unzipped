# 25 — Single-player teleports: the turn layer's root motion

**Status: zero-run research (Sprint 6 candidate, 2026-09-14). Draft, uncommitted.** No build, no
launch, no fix attempted. Each claim is marked:
- **[verified]**: read from a log, a frame, the decomp, the recompiled output or the runtime source during this wave.
- **[inference]**: reasoned from those sources, not observed.

Sources:
- runs 2/3/4: `logs/run_sp_20260913_{103014,104229,111931}.log`, with `logs/parity/s5_t2_death{2,3,4}/timeline.json`, read through `tools_py.parity.sp_death_probe.build_rows`;
- gate stamp `logs/parity/gate/s5_head_1x_b/` (2026-09-14 00:53, after `b625291`);
- `game/analysis/socom2_game.elf.decomp.c`, `recomp/output/`, `recomp/socom2.toml`, `third_party/ps2recomp/`.

The scratch scripts (`steps.py`, `holds.py`, `state.py`, `w20c.py`, `scan.py`) were kept in the
session scratchpad only. Each one is ~30 lines over `build_rows`.

Axes: y is up. Ground at the spawn is y = −145.9 (research/17), and the stream bed reads y = −155.4.

---

## 0. Condition sentence

> **The actor teleports when a right-stick turn outside the dead zone (|rx − 0x80| ≥ 64) is held in
> single player, in or out of the water. The cause: during the turn, the animation update
> `FUN_0057a330` → `FUN_0028c250` writes a root-motion velocity of 250–3100 units/s, with large
> vertical components, into `actor+0x2c..+0x34`. The same function gives the expected (0, 0, −65)
> for a forward walk and (0, 0, +37) for a back walk.** The actor rises up to 131 units, travels up
> to 380 units per 4 Hz row, falls, and takes fall damage. **Which input of the accumulate is wrong
> is unexplained**: the key index, the key data, the node weight `+0x08`/`+0x24`, or the `1/+0x18`
> scale. §4 ranks the candidates, and §5 gives the one run that separates them.

---

## 1. Characterisation (Phase 1.1)

### 1.1 Every step > 30 units [verified]

Columns: t = seconds from the first peek row, d = row-to-row Δ, vel = `actor+0x2c/+0x30/+0x34` as
floats, pad = (rx, ry, lx, ly), and `20c` = `actor+0x20c` (see §1.3).

| run | row | t | \|d\| | d (x, y, z) | vel on/just before the step | pad rx | 20c | hp |
|---|---|---|---|---|---|---|---|---|
| 2 | 979 | 245.5 | 43.4 | (43.0, 6.3, 0.3) | (−257.9, 268.6, −7.0) | 64 | 0xc | 1.0 |
| 2 | 980–982 | 245.8–246.3 | 30.5–53.6 | x −30..−53, y +19.6 at 982 | (268.0, −6.6, −3.9) | 64 | 0xc→4 | 1.0 |
| 2 | 993 | 249.0 | 107.3 | (94.4, −19.9, 46.9) | (−222.9, −87.1, −148.3) | 224 | 0xc | 1.0 |
| 2 | 994 | 249.3 | 81.0 | (−35.7, 19.4, −70.0) | **(1672.6, −2462.4, 979.5)** | 224 | 8 | 1.0 |
| 2 | 995–996 | 249.5–249.8 | 292.0, 148.8 | (−178.2, **+30.0**, −229.4) … | 0 | 224→128 | 0x12 | 1.0 |
| 2 | 1042–1047 | 261.3–262.6 | 67.9 → 174.3 → 183.0 → 55 → 59 → 31 | y −109.5 → **−24.3** then falls −13/−23/−32/−19 | (−865.0, 434.1, 293.4) | 32 | 4 | **1.0 → 0.392** at 1047 |
| 2 | 1060 | 265.9 | 33.8 | (−2.0, −1.4, 33.7) | 0 | 255 released | 4 | 0.392 |
| 2 | 1086–1092 | 272.4–273.9 | 49.8, 167.3, 84.5, 208.8, 210.0, 54, 59 | y −147.9 → **−35.1** (+112.8 in one row) then falls | (1592.9, −131.8, 184.0), (802.5, −1322.1, 1756.2) | 1 | 4/0xf | 0.392 |
| 3 | 991–994 | 248.5–249.3 | 29.4, 42.0, 46.7, 48.3 | y −147.1 → −123.3 | **(289.7, −292.2, −5.3) → (4.9, 289.7, −289.4)** | 192 | **6** → 4 → 0x12 | 1.0 |
| 3 | 1050–1053 | 263.3–264.1 | 32.4, 47.4, 59.9 | y −128.8 → −155.4 | (−206.1, −200.2, −92.7), (114.9, −189.3, 251.5) | 64 | 0x12→0xc | 1.0 |
| 3 | 1064–1070 | 266.8–268.4 | 76.7, 81.8, 87.8, 81.0, **360.5, 380.4**, 220.8 | y −155.4 → −57.0, z 974 → 51 | (−1031.6, −795.7, −407.8), (−349.8, −249.6, −173.2), **(1672.6, −2462.4, 979.5)** | 224 | 0xc→6→4→0x12 | 1.0 |
| 3 | 1073 | 269.1 | 53.4 | (−12.3, −10.7, −50.8) → z = 0.0 | 0 | released | 0x12 | **0.978** |
| 3 | 1096 | 274.9 | 52.1 | (52.0, 1.4, 0.7) | 0 | neutral | 0x12 | 0.978 |
| 3 | 1118–1121 | 280.4–281.1 | 191.7, 36.8, 32.4 | y −129.9 → **−39.1** then falls | (2152.4, −134.2, 231.0) | 32 | 6/7 | 0.978 → **0.721** |
| 3 | 1132–1137 | 283.9–285.2 | 84.9, 34.0, 142.1, 195.0, 156.1, 71.1 | y −150.6 → −89.7 | **(−2152.4, 134.2, −231.0)**, (−933.0, −653.4, 399.1) | 255 | 4/6/0x12 | 0.721; destroyed at +286.7 (mission failure) |
| 4 | 1216 | 305.2 | 86.3 | (−25.1, 10.9, −81.8), from the stream (y −155.1) back to (927, −144.2, 863) near the spawn | 0 on both rows | neutral (after a pop-up CROSS and R1) | — | 1.0 |

### 1.2 Direction: horizontal-dominant, with climbs that read as "into the sky" [verified]

- The steps are mostly horizontal: 100–380 units in x/z. Many rows also carry **climbs of +19 to
  +113 units in one row**:
  - run 2, row 1043: +85.2;
  - run 2, row 1089: +112.8;
  - run 3, row 1068: +73.5;
  - run 3, row 1118: +87.1.
- After each climb, the actor falls 10–40 units per row. The highest point is y = −24.3, 131 units
  above the stream bed.
- **Every health drop lands at the end of one of these falls**: 0.392 (run 2, row 1047), 0.978
  (run 3, row 1073) and 0.721 (run 3, row 1121). This fits fall damage [inference, as research/22 §2].
- The camera stays with the actor, so on screen it ends high on a hillside (gate s36). That is the
  owner's "fly into the sky".

### 1.3 Water: present before most jumps, but not required

- **Entering the stream** [verified]:
  - Walking forward from the spawn takes the actor down the bank: y −145.9 → −150.5 → −153 → −155.4
    at z ≈ 890–947.
  - `actor+0x20c` changes **0 → 6** at the first move and **6 → 0xc** on the row where y drops
    below about −149. This happens in runs 2, 3 and 4.
  - A dry-vs-stream scan of every peeked actor word (runs 2 and 4) finds exactly one word that
    separates the two sets: `+0x20c`.
  - Its later values (4, 7, 8, 0xf, 0x12) change on landings.
- **Meaning of `+0x20c`** [inference]: the surface/material class under the actor, with 0xc = water.
  The decomp writers of `+0x20c` were not traced to a surface table.
- **State fields do not flag water** [verified]:
  - `+0x174` (short) is 1 through walking, standing and the stream. It reads 0 only on some airborne
    rows.
  - `+0xF78`/`+0xF79` do not change in the stream.
  - `+0x174` is not a swim state.
- **Frames** [verified]:
  - Run 2's `popup_241s.png`, 4 s before its first teleport, shows the player **submerged to the
    head, with ripples**.
  - Gate s29 shows the player crouched on the translucent water quads.
  - s30 shows him sunk to the shoulders.
  - s32–s35 show the camera at water level and no player model.
  - The ELF has `water`, `wateranimnode`, `water_factor_slope`, `min_water_factor`,
    `seal_fall_in_water` and `UNDERWATER` strings (`0x48d250`, `0x48ece0`, `0x490f90`,
    `0x490fb0`, `0x491bd0`, `0x2e2dd0`). No decomp xref was found by address.
- **Not water-specific** [verified, one clean instance]:
  - Run 3's first teleport (rows 991–994, rx = 192) started at **(917, −142.1, 848), `+0x20c` = 6**.
  - That is on the bank near the spawn (z 857), after the actor had walked back out of the stream
    (`+0x20c` 0xc → 6 at row 965).
  - The velocity words were already (289.7, −292.2, −5.3) there.
- **Correlation with the turn is total** [verified]:
  - In runs 2 and 3, every rx hold with |Δ| ≥ 64 moved the actor: 10 of 10 holds. Nine of the ten
    had steps of 42–380 units. The tenth (run 2, rx = 255 at +264.6 s) moved 33.8 units with the
    velocity words at 0.
  - The exceptions are only holds where the game was held:
    - run 2, rx = 192 at +236 s: pop-up, axis 0;
    - run 2, rx = 255 at +275.7/+283.2 s: position frozen through that hold and the neighbouring
      forward holds.
  - Every dead-zone hold (|Δ| ≤ 48) moved 0.0.
  - **No effective rx hold was ever made on the post-`vf0` exe with peeks.** Run 4 was `--no-yaw`.
    The post-`vf0` evidence is the gate frames only: s36 turns and leaves the mission area.
- **Run 4, row 1216** (86 units with no stick input, velocity words 0 on both rows) is the one
  exception. It moved the actor from the stream bed back to near the spawn ground. It may be a
  different mechanism, such as a game "unstick" or respawn-to-valid-ground [inference, unexplained].

### 1.4 Fingerprints [verified values; readings are inference]

- **The same velocity triple appears in two runs**: (1672.6, −2462.4, 979.5) at run 2, row 994, and
  run 3, row 1067. Both were rx = 224 holds.
  → Deterministic. It is sampled from data, not uninitialised or racy memory [inference].
- **Exact negation between turn directions**:
  - run 3, rx = 32 (left) gave (2152.4, −134.2, 231.0);
  - rx = 255 (right) gave (−2152.4, 134.2, −231.0).

  → Both directions sample **the same key pair** and apply opposite signs, as if one clip plays
  forward and backward [inference]. That points at a fixed key index (a clip boundary) rather than
  a random position.
- **Component rotation**: run 3's (289.7, −292.2, −5.3) became (4.9, 289.7, −289.4) three rows later,
  i.e. (x, y, z) → (≈ −z, x, y).
  → A one-short (2-byte) misalignment inside the 6-byte key stride [inference]. Either the read is
  past the clip's key array into the next structure, or the key data itself is laid out differently.

---

## 2. The turn / root-motion path in the decomp (Phase 1.2)

- **Caller: `FUN_0057a330(actor)`, the per-frame animation update** [verified]. It gets the controller
  through `FUN_00555170(actor+0x1c0)`, i.e. `*(*(actor+0x1c0) + 4 * *(actor+0x1c8))`.
  - If `controller+0x28 & 0x40`, it builds up to two nodes per channel:
    - `FUN_0058c9e0(actor, id, byte actor+0xF79)` picks the clip id;
    - the second node's weight comes from the envelope `FUN_00286b80(actor+0x458)`;
    - `FUN_0028bdd0` links the nodes.
  - It then calls, in order: `FUN_0028c4f0(actor[0xb8], ctl, 1)` (advance time), `FUN_0028c380(ctl)`
    (per-node time → key index) and **`FUN_0028c250(ctl, actor + 0xb)`**.
- **`actor + 0xb` in `int*` arithmetic is `actor+0x2c`** [verified]. The accumulate's output is exactly
  the "velocity words".
  - After it, a wall-response block reads `actor[0x3da]`/`[0x3db]`/`[0x4ce]` and may rewrite
    `[0xb]`/`[0xd]`.
  - This explains velocity rows reading 0 inside a moving hold [inference].
- **`FUN_0028c250`** [verified]:
  - starts from `DAT_003f6510` (zero);
  - for each node on `ctl+0x30`:
    - `FUN_00289bb0(keys = *(node+4)+0x44, clip = *(node+4), idx = node+0x20, idx+1, tmp)`;
    - `FUN_00309180(node+0x24, tmp)`: scalar ×;
    - unless `ctl+0x28 & 0x40`: `FUN_001bfe68(1.0 / node+0x18, tmp)`, a VU0 scalar ×;
    - `FUN_00309280(node+0x08, acc, tmp)`: acc += tmp × weight, as VU0 `vmulx` + `vadd`;
  - writes acc.xyz to `actor+0x2c`.
- **`FUN_00289bb0` (key sample)** [verified]:
  - If `keys+8 & 2`, the result is zero.
  - Else, if `idx+1 == (clip+4 & 0x3ff)` (the frame count n), it shifts both indices down by one.
  - It reads two keys as 3 × int16 at `*keys + 6·i`, VU0 `vitof0` × 0x3b800000 (= 1/1024).
  - It returns `key[idx+1] − key[idx]` (`FUN_00309200`), × n / `clip+0x10` (`FUN_00309180`).
  - Each component is therefore bounded by 64 × n / `clip+0x10`.
  - **There is no guard for `idx ≥ n`**: with idx = n, it reads `key[n+1] − key[n]`, past the array.
- **`FUN_0028d670` (time → index)** [verified]:
  - wraps t into [0, 1] with `while (1.0 < t) t -= 1` and `while (t < 0) t += 1`, so **t = 1.0 is kept**;
  - `node+0x1c = t·n`;
  - `idx = (short)(int)floorf(t·n)` (`FUN_001b3648` = `floorf`, recompiled, not an HLE stub: `FUN_001b3648_0x1b3648.cpp`);
  - clamps `idx ≤ n − 2` **only when bit 6 of `clip+0x49` is clear**.
  - So for a clip with that bit set (looping, by `FUN_0028ada0`'s use of the same bit) **t = 1.0 gives
    idx = n**, and the sampler reads outside the clip. This is game logic, and the console shares it.
- **`FUN_0028c4f0` (time advance)** [verified]: `t += Σ rate · node+0x08 · node+0x24 / (clip+0x10 · FUN_0028ada0(clip))`,
  then the same wrap (loop) or clamp to `ctl+0xc` (one-shot).
- **No swim/wade branch was found on this path.** The only stance input is `actor+0xF79`, via
  `FUN_0058c9e0`/`FUN_0058c970`/`FUN_0058c820`, which pick alternate clip ids from `*(actor+0x528)+0x5c`
  when it is 1 or 2. The `wateranimnode` string suggests a water blend node elsewhere, not found by
  address xref [inference].
- **Online contrast** [verified in research/22, not re-read]: online full-deflection turns kept the
  velocity words at 0. Either the online actor does not run this layer, or its turn clips have no
  root channel (`keys+8 & 2`) [inference].

---

## 3. Recompiled-code suspects on the path (Phase 1.3)

| suspect | instruction / stub | blow-up input | status |
|---|---|---|---|
| float→int saturation | `FUN_0028d670` `cvt.w.s $f1,$f0` at 0x28d718 → `ps2_fpu_cvt_w` | NaN/Inf t → 0x7FFFFFFF → `(short)` = −1 → key[−1]/key[0] | [verified] the macro truncates and saturates like the EE. NaN cannot reach it: every `FPU_*_S` saturates Inf/NaN to ±FLT_MAX, and `ps2_fpu_div` returns ±FLT_MAX for a zero divisor. FLT_MAX·n → 0x7FFFFFFF → idx −1 is possible only if `clip+0x10` or `FUN_0028ada0` is 0. **Low** [inference] |
| rounding mode | `FUN_0028c4f0` `add.s` (0x28c5d0-ish, `FPU_ADD_S`) and `FUN_0028d670` `sub.s`/`add.s` wraps | a sum just below 1.0 rounding **up** to exactly 1.0 (round-to-nearest) → idx = n → out-of-range key pair; PS2 chop never rounds up | [verified] the game thread runs `fesetround(FE_TOWARDZERO)` (`ps2_runtime.cpp`, unless `PS2X_EE_ROUND=nearest`), and guest threads run on that thread's scheduler [inference]. **Weakened**, unless some path restores nearest. `ps2_vu1_core.cpp` saves and restores MXCSR around VU1 [verified]. Worth one assert in the run |
| out-of-range key index | `FUN_0028d670` clamp gated by `clip+0x49` bit 6; `FUN_00289bb0` no `idx ≥ n` guard | t = 1.0 on a looping clip → idx = n | [verified] logic; shared with the console. It fits "same pair in both directions" and the component rotation. **Prime structural suspect**, if our t hits 1.0 (or idx ≥ n) where the console does not |
| trig / `rem_pio2f` / soft-double | not on this path | — | [verified] `FUN_0028c250`/`c380`/`c4f0`/`d670`/`89bb0` call no trig and no soft-double. Trig can only enter through the rate `actor[0xb8]` or the envelope `FUN_00286b80` (plain arithmetic, [verified]). **Not a suspect** on the accumulate |
| VU0 w-term / vf0 | `FUN_00289bb0` `vitof0`, `vmulx`; `FUN_00309280` `vmulx`+`vadd`; `FUN_001bfe68` `vmulx` | — | [verified] no vf0 operand, and the w word is preserved explicitly in `FUN_00309280`. The vf0 fix is irrelevant here, and the post-`vf0` gate still shows the defect. `QMTC2` copies the whole GPR into vf (`GPR_VEC`), and only field x is used. **Low** |
| divide by zero / normalise | `FUN_0028c250` `1.0 / node+0x18`; `FUN_0028c4f0` `/ (clip+0x10 · FUN_0028ada0)`; `FUN_00286b80` `/ *param_1` | speed `+0x18` = 0 → ±FLT_MAX scale, saturated to ±FLT_MAX in the position | [verified] the division saturates as on the EE. Observed velocities are ≤ 3100, not FLT_MAX, so a zero divide is **not** what produced the observed rows [inference]. A small-but-nonzero `+0x18` (e.g. 0.02 → ×50) would amplify a legitimate 60-unit/s root. **Open** |
| quaternion normalise | `FUN_001bfcc0`/`FUN_001bfd48` | — | not on the accumulate path [verified by call list]. They could affect the local→world rotation of `+0x2c` downstream, but the magnitudes are wrong before rotation. **Not a suspect** |
| HLE math stubs | `recomp/socom2.toml` | — | `floorf@0x1B3648` is listed under `untracked_stubs` ("informational only … recompiles them normally"), and the function is recompiled [verified]. None of the path's callees is an HLE stub [verified for the functions read] |

---

## 4. Ranked candidates [inference]

1. **The turn clip's key index reaches n (or beyond), and `FUN_00289bb0` samples past the key array.**
   - This fits the deterministic triple, the exact negation between directions and the component
     rotation.
   - Open question: why ours reaches it and the console (believed) does not. Possibilities:
     - the time advance for turn clips differs: the rate `actor[0xb8]`, the axis `+0x23c` > 1.0
       (1.118 at full deflection), or the envelope weight;
     - a rounding path that is not chop.
2. **Legitimate key pair, wrong scale.** `node+0x18` (speed) or `node+0x24`/`+0x08` (weights) are far
   from 1 for the turn layer: a stale or uninitialised node from `FUN_0028d860`/`FUN_0028d780`
   reuse in `FUN_0057a330`'s two-node build.
3. **Clip data differs in memory**: a wrong clip id from `FUN_0058c9e0` with `actor+0xF79`, or a
   decode or relocation defect in the clip loader. This alone would not explain why walk clips are
   correct.

---

## 5. The one run (Phase 2)

**Script**: a single-player probe on the current exe (`sp_death_probe` style, same pop-up handling).
After the HUD with lit bands, and before any walking (dry spawn, `+0x20c` = 6):
- rx = 224 for 1.0 s, 2.5 s neutral, three times;
- then `ly = 0` for 6 s (into the stream: `+0x20c` = 0xc, y ≤ −154);
- then rx = 224 for 1.0 s, three times;
- then rx = 32 for 1.0 s, twice (the negation check).

A gate-style drive script would do: `hold+1.0:L` / `wait+2.5:NONE` ×3, `hold+6.0:W`,
`hold+1.0:L` ×3, `hold+1.0:J` ×2. It must keep the pop-up clearing, which `drive.py` alone does not.

**Env**:
```
PS2X_PEEK=<sp_death_probe.PEEK_SPEC>,*0x408c58+0x1c0:4,*0x408c58+0x2e0:1,*0x408c58+0x458:4
PS2X_PC_SAMPLER=0.25
PS2X_CALL_TRACE=0x28c250:RootAcc,0x289bb0:KeySample,0x28d670:AnimTime
PS2X_CALL_TRACE_EVERY=1
PS2X_CALL_TRACE_DUMP=RootAcc:a1:3,RootAcc:a0:16,KeySample:a1:20,KeySample:a0:3,AnimTime:a1:10
```

**What each item gives**:
- `RootAcc a1` after return is the accumulated `actor+0x2c`. Keep only calls whose a1 = actor+0x2c.
- `KeySample` logs a2 = idx and a3 = idx+1. Its `a1` dump gives the clip header: `+4 & 0x3ff` = n,
  `+0x10`, `+0x44`, `+0x48` flags.
- `AnimTime`'s entry f12 = t is **not** logged: the trace logs a0–a3 only. The `a1` dump after return
  gives node `+0x08` weight, `+0x14` t, `+0x18` speed, `+0x1c` frac, `+0x20` idx and `+0x24` weight.

**Readout** (for every RootAcc call on the player with |acc| > 150): take the KeySample and AnimTime
calls on the same controller in that frame.
- **Candidate 1** is proven if a3 > n (idx ≥ n) or t = 1.0 with the clip `+0x49` bit 6 set.
- **Candidate 2** is proven if idx is in range and `+0x18`/`+0x24`/`+0x08` are far from 1.
- **Candidate 3** is left if the index and weights are sane and the key shorts differ by > 60/frame.
- **Water**: the dry-spawn holds versus the stream holds settle it on the post-`vf0` exe.
- **Controls**: the walk holds must show in-range indices and weights near 1.

**Volume concern**: `EVERY=1` on three hot functions for every actor (squad and enemies) is large.
It is 60 Hz × nodes × actors, believed to be 10⁵–10⁶ lines over 2 minutes. If the log is too large,
trace `0x28c250` alone at `EVERY=1` for the first pass. The call trace also misses tail calls
(KNOWN).

**PCSX2 comparison: feasible, with one tooling addition** [inference from the tools]:
- PINE memory reads work: `tools_py/parity/pine.py`, used by `probe_poll.py` and `cam_poll.py`.
- Savestate slot 8 is the spawn of this mission: `spawn_pcsx2.rdram` has the player at
  (939.4, −126.3, 832.2), and ours spawns at x 939.
- The actor static `*0x408c58` is in the same ELF.
- **Missing**: `tools/pcsx2/inis/PCSX2.ini` binds I/J/K/L to face buttons, and no right-stick axis is
  bound. The run needs a keyboard binding for the right stick X in the pad section, or a PINE write
  of the pad buffer.
- Then: load slot 8, and hold right-stick-right 1 s on the spawn ground and again after walking into
  the stream. Poll `*0x408c58` words 7–13 (position, `+0x2c` velocity) and `+0x20c` at the PINE
  rate. Expected console result: the velocity words stay small during the turn and there is no
  climb.
- A console reading of a sane turn (|+0x2c| < ~70) confirms that ours is the defect and makes the
  trace run above the discriminator.
- The same PCSX2 session settles whether the player really sinks to y −155.4, head-deep, in that
  stream (§1.3).

---

## 6. Blind classes and open items

- **Only frames on the post-`vf0` exe**: no peeked rx hold exists after `b625291`.
- **The meaning of `+0x20c` is inferred.** "Water" rests on the y drop, the frames and a one-word scan.
- **Run 4, row 1216's 86-unit move had no stick input and no velocity words.** It is not explained by
  this path.
- **Head-deep submersion (s30, `popup_241s`) is unverified against the console.** It could be its own
  defect (collision or water height), or research/17's root-node decay rendering the body and camera
  5.4 low. It is not the teleport, which happens on dry ground too.
- **4 Hz peek rows undersample a per-frame velocity.** A row reading 0 inside a jump means only that
  the sampled frame had 0.

---

## 7. Settling run (2026-09-14)

**Exe:** `dist/socom2.exe`, sha256 `234b4772cd0a8bf8fe0e76e96f10faade78abba1e9829adddd5d004f0bf54532`, built
2026-09-14 00:28:43 −0300. It was the checkout on `fix/gl-depth-precision`, and that fix is render-only. No build and
no code change were made.

### 7.1 Condition sentence

> **The root motion blows up because the turn-in-place clip (id 0x15, n = 19, duration 0.4 s, clip header `0xa34420`)
> has a keys descriptor at `clip+0x44` that is not a valid descriptor in our memory.** Its flag byte (`+8` = `0xe4`)
> lacks bit 1 ("no root channel"), so `FUN_00289bb0` samples. Its data pointer leads to a quaternion-like track, with
> one component ≈ 32760 rotating through x/y/z key by key. Consecutive keys then differ by ≈ ±32 700 in one component,
> × 1/256 × n/dur (47.5) ≈ ±6 000 units/s, × the node weight `+0x24` (ramping ±0.067 → ±0.3). **On the console the same
> clip's descriptor is valid and has bit 1 set, so root motion is zero. This is our load diverging from the console,
> not game logic.**

### 7.2 Commands

```
powershell -NoProfile -File scripts/kill_stale_drivers.ps1
bash scripts/run_detached.sh --owner sp-settle --purpose launch-sp-settle \
     logs/parity/sp_turn_settle/tools/settle_job.sh logs/sp_turn_settle.detached
#   (the job runs PYTHONPATH=<repo> python sp_turn_settle.py --out logs/parity/sp_turn_settle,
#    i.e. sp_death_probe's launch / HUD / pop-up / liveness with a fixed sequence)
python logs/parity/sp_turn_settle/tools/settle_an.py logs/run_sp_20260914_122711.log \
       logs/parity/sp_turn_settle/timeline.json 0x1a5ebd0 > logs/parity/sp_turn_settle/rootacc_player.txt
python logs/parity/sp_turn_settle/tools/clipkeys.py logs/parity/spawn_ours_vf0.rdram logs/parity/spawn_pcsx2.rdram
```

**Env** (set by `sp_turn_settle.py`):
- `PS2X_PEEK` = `sp_death_probe.PEEK_SPEC` + controller/node/clip chains;
- `PS2X_PC_SAMPLER=0.25`;
- `PS2X_CALL_TRACE=0x28c250:RootAcc,0x28d670:AnimTime`;
- `PS2X_CALL_TRACE_EVERY=1`;
- `PS2X_CALL_TRACE_DUMP=RootAcc:a1:3,RootAcc:a0:16,RootAcc:a0+0x34*+0x4*:12,RootAcc:a0+0x34*+0x4*+0x4*:20,RootAcc:a0+0x34*+0x8*+0x4*:14,RootAcc:a0+0x34*+0x8*+0x4*+0x4*:21,AnimTime:a1:10`.

**Sequence** (after the HUD, pop-ups cleared, liveness forward hold 1 s):
- rx = 224 for 1 s, 3 s gap, three times;
- forward walk ly = 0 for 6 s;
- rx = 224 for 1 s, three times;
- rx = 32 for 1 s, twice.

**Result:** `DONE`. The run log is 16.9 MB, with 6 226 RootAcc calls (608 on the player, ≈ 10–12 per second) and 1 264 peek rows.

**Why KeySample was not traced:**
- `EVERY` is global: `callTraceShouldLog` has no per-slot sampling.
- The RootAcc chain dumps record each top-level node's `+0x20` index and its clip header after the call.
- `FUN_0028c250` does not write nodes, so those dumps equal KeySample's `a2`/`a3`/`a1`.
- With volume this small, KeySample could be added to a rerun at no real cost.

### 7.3 Evidence

**Index against frame count, and weights** [verified, `rootacc_player.txt`]:
- All 57 player calls with |acc| > 150 are on clip `0xa34420` (id 0x15, n = 19, dur 0.400, `+0x49` = `0xe4`, loop bit set).
- **Every index is in range, 0..18.** idx 18 = n − 1 takes the sampler's own shift-down guard. No call had idx ≥ n, and
  t never read exactly 1.0 (max 0.999187). **Candidate 1 is refuted.**
- Speed `+0x18` = 1.000 and `+0x08` = 1.000 on every row. The controller flag `+0x28` = `0x40`, so the 1/speed scale is skipped.
- `+0x24` ramps 0.067 → 0.3 on rx = 224 holds and −0.067 → −0.3 on rx = 32 holds, with t running backward.
- **Candidate 2 is refuted.** The weights are small; the exact negation between turn directions (§1.4) is the sign of
  `+0x24`, not the data.

**Recomputation from the key bytes** [verified]:
- In `spawn_ours_vf0.rdram` (clip at the same `0xa34420`, `+0x44` = `0x90fd60`, identical in every dump of ours since
  09-08), keys = (338, −73, 470), (32762, 129, −81), (472, 32763, −168), (−91, 471, 32763), …
- Each traced velocity equals (k[i+1] − k[i]) × (1/256) × 19/0.4 × `+0x24`, e.g.:

| row | idx | `+0x24` | recomputed | traced |
|---|---|---|---|---|
| #1429 | 12 | 0.3 | (1875.3, −45.3, −17.7) | (1875.2, −45.3, −17.6) |
| #1449 | 13 | 0.3 | (−1816.8, 1872.9, −26.7) | (−1816.9, 1873.0, −26.8) |
| #1419 | 11 | 0.3 | (−48.6, −23.7, −1811.4) | (−48.7, −23.7, −1811.5) |

- The component rotation in §1.4 is this track's layout: the big component moves one axis per key. It is not a read stride error.
- **Correction to §2:** the key scale `0x3b800000` is **1/256**, not 1/1024.

**Walk control** [verified]:
- The walk clip `0xa3ee80` (id 4, n = 19, dur 0.633) has a valid descriptor in ours: data = struct + 0x294.
- Its keys are (41, 2638, 7233 − 492.5·i). The derived −58/s × `+0x24` 1.1265 = −65, matching the traced (0, 0, −65).
- The console's equivalent clip (`0xa45260`) has byte-identical keys.

**Dry against stream** [verified]:
- The blow-up fires identically on all three dry rx = 224 holds (the first, from (940, −149, 876) on spawn ground) and in
  every later hold, with the same velocity triples (e.g. (−401.8, 418.5, −11.0) opens every rx = 224 hold).
- **Water plays no part in it.** After the first dry hold the actor was already displaced (positions in `sp_turn_settle.detached.log`).

**Console against ours, in memory** [verified, `clipkeys.py` plus a whole-image scan]:
- `spawn_pcsx2.rdram` (PCSX2 slot 8) has the console's clip with the same header shape (n = 19, dur 0.4, `+0x49` =
  `0xe4`, word 3 `0x660001`) at `0xa39630`.
- Its descriptor is `[0x912cf4, 0x912cfc, 0x006f6677]`: data = struct + 0x294, flag byte `0x77`, bit 1 set, so the
  sample is zero.
- **Ours** reads `[0xa10260, 0x05646c73, 0x00a0fee4]` there. Word 1 is a tag, not a pointer.
- Scanning every clip header (`word1 >> 16 == 0x1c1a`) and checking whether `*(clip+0x44)` is a descriptor (two
  in-RAM pointers < 0x1000 apart):
  - **ours: 78 valid, 65 invalid;**
  - **console: 144 valid, 0 invalid.**
  - The invalid ones in ours point into key-like or random data (e.g. `0x93f9dc` → `7fff0000 0000000c ffca01da`).
- The console's turn key bytes (`9dff8105e5fe1202…`) occur **nowhere** in our 32 MB image.
- The 0x880000–0x9ae000 region differs almost wholesale. A uniform relocation offset does **not** explain it
  (checked, then retracted: the +0x2d00 match was coincidental).

### 7.4 Verdict

- **Ours diverges** [verified at memory level]. About 45 % of our clip headers carry a descriptor pointer that does not
  land on a descriptor. The console has none.
- **The mechanism is open** [inference]. Candidates: the animation file loader or relocation pass (the pointer fix-ups
  inside the loaded animation pack), a short or misordered file read, or a decompression defect. The `clip+0x44` writer
  was not found by a simple grep; the relocation is likely a table-driven loop.
- The t = 1.0 over-read in §2 still exists but did not occur here. It is not the cause.
- **PCSX2 behavioural run (run 2): not run.** The console's own RDRAM already answers ours-vs-console for this clip:
  bit 1 set means zero root motion by the decomp.
- **Not verified on the console:** a live console turn keeping `+0x2c` at 0. A PINE poll after rx holds from slot 8
  would confirm it.

### 7.5 Instrument notes

- **`AnimTime` (`FUN_0028d670(float t, node)`) takes the node in `a0`, not `a1`.** §5's `AnimTime:a1:10` dumps
  garbage (`@40`, `@2`).
- **The call trace prints f12/f13/f14 with `setprecision(1)`**, so t = 0.96 and 1.0 read the same. Use the node's
  `+0x14` in a ret-dump instead.
- **The player's controller is not array index 0.** `*(actor+0x1c0)**` resolves to `0x119956c`, while RootAcc's
  controller is `0x1199404`. The peek's key chains therefore captured the wrong clip, and the key bytes came from the
  RDRAM dumps instead.

### 7.6 Blind classes

- **The console clip is matched by header shape**, not by a name or file id: same n, duration, flags and word 3.
- **Ours "invalid" is a heuristic** (two in-RAM pointers < 0x1000 apart). Some of the 65 may use another descriptor
  form, though the console has none that fail it.
- **The game ran at ≈ 10–12 player updates per second under the trace.** This does not change the per-key arithmetic.
- **Run 4's 86-unit move without stick input (§6)** is not explained by this run.

---

## 8. Verification and loader root cause (2026-09-14, zero-run, PAUSED by owner before the writer was named)

**Scope.** Read-only. No build, no run. I re-derived everything with my own scripts, which are in the session scratchpad under
`clips/` (`packdump.py`, `namecmp.py`, `bufdiff.py`, `chunkmap.py`, `subrange.py`, `scanall.py`, `period.py`,
`where.py`, `final_counts.py`). I did not reuse §7's `tools/`. Sources were the decomp, the recompiled output, the
runtime and IOP sources, `game/disc/RUN/MOTION_P.ZAR`, the ISO directory (parsed by my own code) and 25 RDRAM images.

### 8.1 Clip layout, from the decomp [verified]

**Clip header.** From `FUN_00289bb0`, `FUN_0028c250`, `FUN_0028d670`, `FUN_0028ada0` and `FUN_0028a100`:
- `+0x00` points at the clip **name string**;
- `+0x04 & 0x3ff` = n;
- `+0x08` = `+0x44` = keys descriptor, both set by `FUN_0028a100` to `blob+8`;
- `+0x10` = duration;
- `+0x49` bit 6 = loop.

**Descriptor.** It is a 16-byte record. `FUN_00289bb0` reads:
- `*desc` = key array: 3 x int16, stride 6, scaled by `0x3b800000` = 1/256;
- **`lbu 8(a0)`** (`sub_00289BB0` at 0x289bc4): bit 1 set means a zero root channel.

**Owning table.** The clip id resolves through `FUN_005e3d90` to `FUN_002892b0()`/`FUN_002892a0()` = `0x415d40`/`0x415e60`,
then to `+0xf8[index]`, with the count at `+0x100`.

**The motion pack is `0x415d40`.**
- It is loaded by `FUN_00288b80` from `run/motion_p.zar` (fallback `run/motion.zar`), resource `motion.rdr`.
- The ZAR open `FUN_00258000` reads the data section in one stream read (vtbl `0x408180+0x24` = `FUN_0039e690`) into a
  `malloc` buffer (`FUN_0034ec30` -> `malloc@0x194C30`).
- `FUN_00257f90` hands the buffer to `DAT_00415e08` (pack `+0xc8`), with the size at `+0xcc` = 0x1c26a0 = file size
  0x1c5400 - TOC 0x2d60.
- `FUN_0025a390(zar, 0x28a860, pack)` then builds one clip per member through `FUN_0028a860` -> vtable `0x4060c0+0x10` =
  `FUN_0028a100`/`FUN_00289380`, the per-track pointer fix-up.
- ISO: `RUN/MOTION_P.ZAR;1` is at LBN 0xeb506, size 1 856 512, matching the extracted file.

### 8.2 Phase 1: counts, identity, arithmetic

- **Validity, structural** [verified]. Clips are matched **by owning-table index and name**, not header shape. A descriptor
  counts as valid when its relative layout (key ptr - desc, word1 - word0) and tag word equal the console's, and its address
  differs from the console's by exactly the buffer delta.
  - Result: **99 clips; 12 with a null `+0x44`; 39 valid; 48 invalid**. `spawn_ours3` and `spawn_ours_vf0` give identical counts.
  - **All 48 invalid descriptors sit at motion-buffer offsets < 0x140000. All 39 valid ones sit at offsets >= 0x140000.**
  - §7's 78/65 came from a header-shape scan over a different population, so the counts differ; the direction is **confirmed**.
- **Identity** [verified]. Index 64 in the motion pack is **`seal_crouch_step`** on both sides: ours clip `0xa34420`, console
  `0xa39630`. Both name pointers lead to the same string. n = 19, dur `0x3ecccccd`, `+0x49` = 0xe4 on both.
  - ours: `desc@0x90fd60 = 00a10260 05646c73 00a0fee4` -> flag byte 0xe4, bit 1 = 0 -> sampled;
  - console: `desc@0x912a60 = 00912cf4 00912cfc 006f6677` -> flag byte 0x77, bit 1 = 1 -> zero root motion.
  - §7.1's clip ("id 0x15") is confirmed by name.
  - Three header-byte differences remain unexplained: index 57 `w1` 0x1c1b0022 vs 0x1a1b0022, and indices 77/78 `+0x49`.
- **Arithmetic** [verified], row #1429 (idx 12, `+0x24` = 0.3):
  - our key bytes at `*desc + 72` are `5afcafffd000 f17f81fc93ff` -> k12 = (-934, -81, 208), k13 = (32753, -895, -109);
  - (k13 - k12) / 256 x 19 / 0.4 x 0.3 = **(1875.2, -45.3, -17.6)**, which equals the trace.
  - "Key index in range, speed and `+0x08` = 1.0" was not re-derived; it was read from `rootacc_player.txt` only.

### 8.3 What is actually wrong in the bytes [verified]

- **Divergence mechanism.** Every relocated pointer in our pack differs from the console's by a uniform -0x2d00, which is exactly
  the buffer delta (ours `0x86d840`, console `0x870540`). The corruption is in the **buffer content**, not the relocation.
- **Chunk map.** Split the 0x1c26a0 buffer into 0x40000 chunks. Our chunks 0..4 hold **file chunks 6, 5, 6, 5, 6**, and chunks
  5, 6 and 7 are correct.
  - The switch is at exact buffer offsets k*0x40000.
  - The 0x2a0-byte head and the 0x560-byte tail of each chunk are wrong in the same way. On a sector-aligned read those bytes
    come from the bounce buffer, so the damage is on buffer-aligned blocks, after assembly.
  - Equivalently, RAM `[0x86e000, 0xa2d000)` is **periodic with period 0x80000**, seeded by buffer offsets 0x140000..0x1bffff.
    That is the signature of an overlapping block move executed in the wrong order (high to low with dst < src), not of a bad
    sector read.
- **Timeline** across all 25 images, at the same base `0x86d840`:
  - **intact**: `menu*`, `rank*` (09-07), `title_ours` (09-09 00:38), `frostA/B_probe600[_vf0]` (online, 09-13);
  - **reused by other data**, on the console too: `postload_ours`, `postload_pcsx2`, `spawn_ours_vf0_t200`. The pack pointer
    stays stale, and chunk 7 is still in place;
  - **smeared identically**: every SP `spawn_*`/`rest_*` image of ours, 09-08 to 09-13;
  - the console's spawn is intact.
  - **So the first load is correct, and the corruption appears when the motion bytes are restored during the
    single-player mission load.**
- **Read path at that time.** At title, `0x488fb0` = 0 and `0x4a15f8` = 0: fio open and read. At spawn both are set:
  - the TOC stream `FUN_0039e690` -> `FUN_0039d960`/`FUN_0039dca0`;
  - then `FUN_0033f420`, which queues 989snd **fno 0x38 `snd_StreamSafeCdRead`** {lbn, sectors, buf} in the fno 0x4d batch;
  - the HLE is `ps2xIOP/src/modules/snd989.cpp` `streamSafeCdRead`: one synchronous forward read, 64 KiB host pieces, 16 MiB cap.
  - The run log lists only 7 fno 0x38 lines (log cap), so the mission-time motion read was **not** observed.
- **Unexplained artefact.** In `spawn_ours_vf0_t200` and `spawn_ours_vf0`, 21-23 of 131 4 KiB blocks of file offsets >= 0x140000
  sit at an implied base `0x1bab1b0` (RAM around 0x1d2b000+). The block is absent in `title_ours` and in the console image. Its
  owner is unknown. It could be a staging copy that sources the restore [inference].

### 8.4 Candidates for the writer, ranked [inference]

The shape of the corruption is verified. The writer is **not identified zero-run**.

1. **An overlapping block move** (|delta| = 0x80000, 0x40000-aligned blocks, high to low) in the SP-mission restore of the motion
   bytes.
   - For: fits the chunk map, the byte-level alignment and the "first load clean" timeline.
   - Check (**one run**): a guest write watch on `[0x86d840, 0x9ad840)` from mission start to HUD, logging pc/ra, plus the
     src/dst of any memcpy/memmove/fioRead/StreamSafeCdRead that hits it (the stubs already call `ps2TraceGuestRangeWrite`).
2. **Heap placement** (`guestMalloc` vs newlib) makes a guest copy overlap here that does not overlap on the console.
   - For: the console has a newlib header `0x001c26b1` before its buffer and ours has none; our pack arrays sit below the buffer,
     the console's above. This could explain "console clean" even when the copying code is shared, but it still needs a
     non-memmove copy.
   - Check: log `guestMalloc`/`guestFree` blocks that intersect the buffer during the mission load.
3. **The 989snd `StreamSafeCdRead` HLE or the TOC reader** delivers wrong chunks.
   - Against: it is a forward single pass, and the corruption covers the bounce-copied head and tail on buffer-aligned boundaries.
   - Check: trace fno 0x38 args during the mission load with the log cap lifted.
4. **The `memcpy` stub on overlap** (one host `::memcpy` per call, llvm-mingw CRT).
   - Against: the smear is seeded at the top, while a forward-copy smear is seeded at the bottom.
   - Check: the same write watch, restricted to the stubs.
- **Ruled out** [verified]:
  - relocation base: uniform -0x2d00, and correct at title;
  - decompression: the member is stored raw;
  - struct size: clean clips outside the smear;
  - first-load short read and `iso_lbn`: `title_ours` is intact at the same base, and the LBN was parsed independently.

**Memcpy/memmove audit** [verified in source, `LibC.cpp`, `ps2_runtime.cpp`]:
- `memcpy` resolves both pointers and does one `::memcpy` bounded by the RAM end. It has no forward-copy guarantee on overlap
  (newlib copies forward; the host CRT is undefined, memmove-like in practice).
- `memmove` copies through a temporary vector, so it is correct in both directions.
- `guestRealloc` uses `std::memmove`, which is correct.
- None of the three produces a top-seeded period smear by itself.

### 8.5 Condition sentence

> **48 of the 87 non-null clip descriptors in the motion pack (`run/motion_p.zar` -> `DAT_00415e08`) are corrupt because
> buffer offsets 0..0x13ffff are overwritten during the single-player mission load by a period-0x80000 repetition of
> offsets 0x140000..0x1bffff (chunks 6, 5, 6, 5, 6). This destroys `seal_crouch_step`'s descriptor, whose flag bit 1 then
> reads 0.** The first load (title) is byte-correct. The writer (block move, restore read or placement overlap) is
> unidentified, and §8.4 item 1 is the one run that names it.

### 8.6 Proposed fix path and test (not implemented)

- **No code fix yet.** Name the writer first with the §8.4 item 1 watch run.
- **Offline regression test**, needing no run. For a spawn RDRAM, check that every motion-pack clip descriptor matches the console
  by name, and that the buffer's non-pointer words equal `MOTION_P.ZAR[0x2d60:]`. Today it fails with 48; after the fix it must
  pass.
- **Live check.** In rx = 224 holds, `RootAcc` |v| stays < 150, and the gate mission stage does not end in "left the mission area".
- **Not recommended** except as a diagnostic: re-reading the motion pack after the mission load. It would mask the writer, which may
  corrupt other heap blocks.

### 8.7 Open when resumed

- The writer of the smear (§8.4).
- Whether the motion data is freed and re-read or copied back during the mission load. The pack pointer stays at the base while
  the region holds other data, on both sides.
- The owner of the partial high-RAM copy at implied base `0x1bab1b0`.
- The three clip-header byte differences (§8.2).

---

## 9. Overwriter (2026-09-14, zero-run)

**Scope.** Read-only: the decomp, the runtime sources, `game/disc/RUN/MOTION_P.ZAR` and the existing
RDRAM images. No build, no launch, no code change. The loop lock was held by another owner
(`depthfix`) throughout; no run was needed.

### 9.1 Condition sentence

> **The motion buffer is overwritten by our own `sceGsExecStoreImage` HLE, because
> `ps2xRuntime/src/lib/Kernel/Stubs/GS.cpp` converts the libgraph `vram_addr` into a BITBLTBUF block
> pointer as `vram_addr * 2048 / 256` (x8) in both `sceGsExecLoadImage` (line 641) and
> `sceGsExecStoreImage` (line 706). The game parks the top 1.75 MB of GS VRAM in the motion pack
> buffer during the single-player load — `FUN_003b1990(0x2400, FUN_00288930(), 0x1c0000)` stores
> VRAM -> buffer and `FUN_003b18d0(0x2400, ..., 0x1c0000)` loads it back, in seven 256x256 PSMCT32
> pieces of 0x40000 bytes with `vram_addr` stepping 0x400 — and with the x8 the seven block pointers
> (0x12000, 0x14000 ... 0x1e000) mask to 14 bits (`& 0x3FFF`) as 0x2000, 0, 0x2000, 0, 0x2000, 0,
> 0x2000. Seven distinct VRAM regions collapse onto two, so the store reads piece i back from the
> aliased block and writes `[6, 5, 6, 5, 6, 5, 6]` over buffer chunks 0..6.** Chunks 5 and 6 land on
> their own content by luck, and chunk 7 (file offsets 0x1c0000..0x1c26a0) lies outside the game's
> 0x1c0000 length, which is why they survive. This is our defect, not game logic: the console runs
> the same two calls with correct block pointers and the round trip is lossless.

### 9.2 Evidence

- **The call pair** [verified, decomp]. `FUN_003b1990` = `sceGsSetDefStoreImage@0x1a2708` +
  `sceGsExecStoreImage@0x1a29c8` (GS -> EE); `FUN_003b18d0` = `sceGsSetDefLoadImage@0x1a2520` +
  `sceGsExecLoadImage@0x1a2848` (EE -> GS). Both loop `param_3 -= 0x40000`, `param_2 += 0x40000`,
  `param_1 += 0x400`, i.e. seven iterations for 0x1c0000. The call sites pass
  `0x2400, FUN_00288930(), 0x1c0000`, and `FUN_00288930()` returns `DAT_00415e08`, the motion buffer
  (decomp lines 51132 and 51301).
- **`vram_addr` is in 256-byte blocks** [verified, three independent call sites]:
  `FUN_001a2520(..., (short)(iVar4 >> 8), ...)` (byte address / 256, line 45100);
  `FUN_001a2708(0x4a43e0, (short)(DAT_004a44b4 << 5), ...)` (page of 8192 -> 256-byte blocks, line
  305403); and 0x2400 * 256 = 0x240000, plus 7 * 0x40000 = exactly 0x400000, the end of the 4 MB
  VRAM. A x2048 reading would put the base at 18 MB, outside VRAM.
- **The transfer parameters match** [verified, `title_ours.rdram`, `spawn_ours_vf0.rdram`]:
  `DAT_003e1410` = 256 (so the store's `vram_width` = 256 >> 6 = 4, the same as the load's literal 4),
  `DAT_004a4540` = 0 (PSMCT32). 256 x 256 x 4 = 0x40000 per piece, and `DAT_00415e08` = 0x86d840.
- **The alias** [verified, arithmetic on GS.cpp]: `dbp = vram_addr * 8`, and the BITBLTBUF field keeps
  14 bits. 0x2400 -> 0x12000 & 0x3FFF = 0x2000; 0x2800 -> 0x14000 & 0x3FFF = 0; and so on, period 2.
  After the load, VRAM block 0x2000 holds buffer chunk 6 and block 0 holds chunk 5. The store then
  reads those two blocks back into all seven destinations.
- **The readback really is VRAM-addressed** [verified]: `sceGsExecStoreImage` issues the
  BITBLTBUF / TRXPOS / TRXREG / TRXDIR A+D packet and then
  `gs().consumeLocalToHostBytes(dst, totalImageBytes)`; `GSCpuBackend` fills `m_localToHostBuffer`
  from `ReadVramUnlocked(spsm, m_transfer.bitbltbuf.sbp, sbw, ...)` and the GL backend forwards to it.
- **The bytes agree** [verified, block scan of the images, scratchpad `locate.py`]. Locating every
  4 KiB block of `MOTION_P.ZAR[0x2d60:]` in each image gives, for `spawn_ours` and `spawn_ours_vf0`:
  base 0x86d840 chunks 5, 6, 7; base 0x7ed840 (= base - 0x80000) chunks 5, 6; base 0x76d840 chunks
  5, 6; base 0x6ed840 chunk 6. Read as buffer chunks that is exactly
  **[6, 5, 6, 5, 6, 5, 6, 7-original]**, the predicted pattern, including the two accidentally
  correct chunks.
- **The leftover packet is the load's** [verified]. `sceGsExecLoadImage` `guestMalloc`s
  `(6 + 0x4000) * 16` bytes, memcpy's the source image into it, and frees it without zeroing. The
  unexplained artefact of §8.3 — one 0x40000 copy of buffer chunk 6 at ~0x1d2ac80 / 0x1d2b1b0 /
  0x1d2b8d0 (run-dependent) — is that freed packet holding the **last** load piece (buffer offsets
  0x180000..0x1bffff). The console image has no such copy, as expected.
- **The timeline fits** [verified]. `spawn_ours_vf0_t200` and `spawn_ours_vf0` share the packet base
  0x1bab1b0, i.e. one run: at t200 the buffer holds the stored VRAM image (the game's own save, which
  the console does too — `postload_pcsx2` shows the same region reused and chunks 6/7 left), and the
  load packet already exists; by the spawn dump the buffer holds the aliased read-back.

### 9.3 Verdict on the §8.4 candidates

| candidate | verdict |
|---|---|
| 1. overlapping block move | **Refuted as stated, right in shape** [verified]. There is no guest `memmove`; the "block move" is our GS load/store round trip through aliased VRAM. |
| 2. heap placement / `guestMalloc` | **Not the cause** [verified]. The buffer sits at 0x86d840 with a uniform -0x2d00 delta to the console, and the freed 0x40000 load packet is a symptom, not the writer. |
| 3. 989snd `StreamSafeCdRead` | **Cleared** [verified, `ps2xIOP/src/modules/snd989.cpp:1436`]. It writes into **EE RDRAM** at the guest-supplied `destination` (`normalizeGuestAddress`, rejected at or beyond 32 MB), reads `sectors * 2048` from the CD image capped at 16 MB and at the RAM end, copies forward in 64 KiB host pieces with a monotone cursor, and stops on a short read. No ring or bounce buffer in guest RAM, no modular arithmetic, no 0x40000/0x80000 constant, nothing keyed to 0x1d2b000; `handleRpc` runs under a mutex and `handleBatch` walks the batch in order, so it is synchronous. It can only deliver disc bytes, never a self-similar RAM smear. |
| 4. `memcpy` stub on overlap | **Cleared for this defect** [verified]. `LibC.cpp` `memcpy` does a host `::memcpy` per contiguous span and `memmove` goes through a temporary; neither is on this path. Note that `ps2TraceGuestRangeWrite` is now a **no-op** (`ps2_runtime.h:261`), so §8.4's "the stubs already call it" yields no logging. |

### 9.4 Commands (all read-only)

```
grep -n "sceGsExecLoadImage\|sceGsExecStoreImage" third_party/ps2recomp/ps2xRuntime/src/lib/Kernel/Stubs/GS.cpp
sed -n '600,760p' third_party/ps2recomp/ps2xRuntime/src/lib/Kernel/Stubs/GS.cpp     # dbp/sbp = vram_addr * 2048 / 256
sed -n '305468,305510p' game/analysis/socom2_game.elf.decomp.c                      # FUN_003b18d0 / FUN_003b1990
sed -n '51125,51135p;51295,51305p' game/analysis/socom2_game.elf.decomp.c           # the two call sites
sed -n '1600,1690p' third_party/ps2recomp/ps2xRuntime/src/lib/gs/gs_cpu_backend.cpp # ReadVramUnlocked(sbp) readback
python <scratchpad>/locate.py title_ours postload_ours postload_pcsx2 spawn_ours \
       spawn_ours_vf0_t200 spawn_ours_vf0 spawn_pcsx2                               # block-location scan
```

### 9.5 Proposed fix and tests (not implemented)

- **Fix** (2 lines): in `GS.cpp`, `sceGsExecLoadImage` line 641 and `sceGsExecStoreImage` line 706,
  use `img.vram_addr` directly as the BITBLTBUF block pointer instead of `vram_addr * 2048 / 256`.
  The libgraph `vram_addr` is already in units of 64 words (256 bytes), which is the DBP/SBP unit.
- **Unit test** (`ps2xTest/src/ps2_gs_tests.cpp` already has a single-region round trip at line 3989;
  a single region is lossless either way, which is why it never caught this): add a **seven-region**
  round trip — `vram_addr` 0x2400 stepping 0x400, 256x256 PSMCT32, `vram_width` 4 — writing seven
  distinct patterns and asserting each reads back its own. Today it returns the 6/5 alternation.
  Assert `sbp == vram_addr` for at least one case.
- **Offline regression** (no run, as §8.6): for a spawn RDRAM, every motion-pack clip descriptor must
  match the console by name, and the buffer's non-pointer words must equal `MOTION_P.ZAR[0x2d60:]`.
  Today: 48 corrupt descriptors of 87 non-null; after the fix: 0.
- **Live check**: on rx = 224 holds `RootAcc` |v| stays < 150, and the gate mission stage no longer
  ends in "left the mission area".

### 9.6 Concerns

- **Blast radius.** Every `sceGsExecLoadImage`/`StoreImage` caller changes destination: the decomp has
  other call sites (lines 45100, 305403, 305456, 305540) that pass `vram_addr` as a byte address >> 8
  or FBP << 5. They alias today whenever `vram_addr >= 0x800` (VRAM byte 0x80000), so the fix may move
  loading-screen, movie and texture uploads that other code may have been tuned around. The full gate
  must run after it.
- **Not verified**: that the console's live turn keeps `+0x2c` small (§7.4 still open), and that the
  corrupt descriptors are the only cause of the teleport — §8.2's arithmetic makes it very likely.
- **Chronology** of the store/load pair inside the mission load was inferred from three dumps
  (`t200` -> `spawn` in one run), not traced. It does not affect the mechanism: the pattern, the
  masking arithmetic and the leftover load packet agree independently.
- **Still unexplained**: the three clip-header byte differences (§8.2) and run 4's 86-unit move (§6).
