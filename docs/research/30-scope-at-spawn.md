# 30 — Instance B spawns in the sniper scope (2026-09-15, s6_ladder4, read-only)

Symptom: on the block-pointer exe (a81eb74, with the GL depth fix f6a4434) instance B (persona `socome`,
TERRORISTS, Frostfire) is in a circular scope view with "ZOOM: 3.0x" from its first in-game frame
(`logs/parity/s6_ladder4/B_19_ready.png`) and walks at scope speed (18-25 units / 2 s hold vs 54 in
Sprint 5; `RESULT NO-CONTROL side=B`). Instance A is normal. The merged pad trace shows B read only
CROSS/UP/DOWN/LEFT/RIGHT words, never L1/L3/R3. This note answers the four questions from the decomp,
reCOM, research/19, research/25 §9-§10 and `GS.cpp`. No build, no run, no tracked edit.

## 0. Condition sentence

> **The scope is the game's zoom cycler doing what it was asked.** "ZOOM: %2.1fx" is drawn from the
> local actor's view-mode byte `A+0x200` (A = `*0x408c58` = `*0x415ff0+0xbc`), the mode is raised only
> by `FUN_005445b0` ("zoom in"), and that runs from `PlayerUpd` (`FUN_00594cf0`) on a **D-pad UP
> press edge** (input slot 4, byte `+5` of the actor's input object `*(A+0x28)`); D-pad DOWN (slot 5,
> byte `+6`) is "zoom out". The harness's lobby cursor search pressed DOWN,UP,DOWN,UP,DOWN,UP,DOWN,UP
> (1.0 s each) on B at 393.1-400.7 s, after the host readied at 392.9 s, and B was off the lobby screen
> by 404.8 s. The UP edges that landed while `PlayerUpd` was already running walked the mode up to a
> weapon zoom level whose table value is 3.0. Sprint 5 ladder2 ran the same wiggle (419.2-424.7 s,
> host READY 419.0 s, B off-lobby by 431.0 s) and stayed unscoped, so the change is **when B's actor
> became controllable relative to the wiggle**, not the loadout and not a memory write [inference; the
> chain is verified, the timing overlap is inferred from the drive logs, see §4 for the settling peek].

## 1. Where the scope state lives and what sets it (Q1)

- **The string.** `ZOOM: %2.1fx` is at `0x3e3098`, `RANGE(m): %.0f` / `RANGE(m): ----` at
  `0x3e4850`/`0x3e4860` (`socom2_game.elf.strings.txt` lines 629, 815-816) [verified].
- **The drawer** `FUN_001f6ce0` (decomp 56028-56066) takes `iVar1 = *(DAT_00415ff0+0xbc)` (the local
  actor, research/19 F5) and switches on `*(byte*)(iVar1+0x200)`: modes 2,3 -> zoom 0; mode 4 -> 9.0;
  modes 5..0xc -> `FUN_005be660(iVar1+0x5e0)`; then prints only if the value is > 1.01 [verified].
- **The zoom value** `FUN_005be660` (475059) = `FUN_003c5980(weapon)` = `*(weapon+0x288)[i]` when
  `i = mode-4 < *(weapon+0x284)` (317040-317052) [verified]. The weapon-definition parser fills that
  table from the keys `NumZoomModes` (`0x3fc988`) and `ZoomMode%d` (`0x3fc998`) via `FUN_003c5e70`
  (322377-322386) [verified]. So "3.0x" is a **data value from the equipped weapon's ZoomMode table**,
  selected by the actor's mode index; there is no per-persona zoom setting on this path. reCOM names
  the same shape (`zweapon.h:572-574 m_first/second/thirdZoomLevel`, `zseal.h:877 m_zoomlevel`) [hint].
- **The setter** `FUN_005448a0(actor, mode)` (410929-411020): writes `A+0x201 = old`, `A+0x200 = mode`,
  `A+0x202 = 1`; sets `A+0x204` (FOV/zoom factor) to `1.0` for mode 0, `1.01` for 1-3, `9.0` for 4, and
  the weapon table value for 5..0xc; modes 4+ instantiate a `zoom_control` object (`0x65c398`) at
  `A+0x53c` and call `FUN_005b9180(A+0x5e0)` [verified]. Callers with a constant: mode 0 from the spawn
  and reset paths (413083, 413095, 419128, 438329), mode 1 from 70389, 412019, 412250, 478833, 479404,
  mode 2 from 412254. **Every caller that can pass >= 4 is one of the two cyclers** [verified by grep
  `FUN_005448a0(`].
- **The cyclers.** `FUN_005445b0` (410716, "zoom in": default case `mode+1` while
  `mode-3 < NumZoomModes`) and `FUN_00544400` (410621, "zoom out") [verified]. They are called from
  exactly one site, inside `FUN_00594cf0` = research/21's `PlayerUpd` (453316-453324):
  `*(char*)(iVar12+6)=='\x01'` -> zoom out, `*(char*)(iVar12+5)=='\x01'` -> zoom in, with
  `iVar12 = FUN_0029ed20(A) = *(A+0x28)` (the actor's input object) [verified].
- **Which button.** The per-frame pad reader `FUN_002da930` (179477; research/08 calls it the
  per-frame pad reader) fills the input object with `FUN_002d9ff0(pressure, obj, slot, digital)`,
  which writes `obj+1+slot` with a 0 -> 1 (press edge) -> 2 (held) -> 3 (release edge) -> 0 machine
  [verified, 179820-179862 / `FUN_002d9ff0`]. Slot 4 is filled from libpad2 button id 4 with pressure
  id 0x16, slot 5 from id 6 with 0x17 (179830-179834) [verified]; in libpad2's table id 4 = UP, 6 =
  DOWN, 0x16/0x17 their pressures (consistent with slot 2 = id 5 + 0x14 = RIGHT) [inference on the
  id table; the pairing is verified]. So **`+5 == 1` is "D-pad UP just pressed" and `+6 == 1` is
  "D-pad DOWN just pressed"**. The runtime maps the arrow keys to `kPadUp`/`kPadDown`
  (`socom2_host_input.cpp:185`) [verified].
- Not a button on L1/L3/R3, not the weapon's default, not a saved setting, not spawn init (spawn sets 0).
- Guard worth knowing: the HUD tick forces mode 1 when `FUN_005bd7e0(A+0x5e0) != 0 && mode > 1`
  (70386-70389) [verified]; `FUN_005bd7e0` is a fire-mode/ammo cycle helper (477826) [inference].

## 2. What decides the terrorist spawn loadout (Q2)

- The level data carries a `default_weapons` list (`0x65bf50`) whose entries are read by `wep_name`
  (`0x65bf60`) in the mission-data reader at 406362-406390 (`FUN_0032f0d0(node, "default_weapons")`)
  [verified]. The online armory is a separate path (`InitializeOnlineArmory`, `0x3ee860`) [string only].
- The drive log has no ARMORY step for either side (`logs/parity/drive_s6_ladder4.txt`), and B's
  lobby captures are the plain GAME LOBBY [verified]. So B held the **map default** for its team, the
  same as in Sprint 5 [inference]. The memory card (`game/disc/mc0_b/BASCUS-97275SOCOMII/SaveGame0-6`)
  holds save games; nothing on the zoom path reads it [verified: no mc read in §1's chain].
- "A weapon whose default state is scoped" does not exist in this code: the scoped state is the
  actor's mode, initialised to 0 at spawn (413083/413095) [verified]. What exists is a weapon whose
  ZoomMode table contains 3.0, which B's default primary evidently has [inference from the HUD].

## 3. Could the block-pointer fix cause it? (Q3)

- **Direct write: no.** The only VRAM -> EE readbacks are (a) the motion-pack restore into the buffer
  at `*0x415e08` (research/25 §9), (b) `FUN_003b1800` (305445-305460), a `sceGsExecStoreImage` into
  a caller buffer, whose one caller `FUN_003b0e70` (305171) grabs a single pixel at VRAM block 0x2300
  into a stack word and returns its low byte (a colour probe, called from `FUN_00336810` at 235021),
  and (c) the store descriptor at static `0x4a43e0` set up by `FUN_003b14a0` (305403, screen grab /
  transition freeze, executed at 305664-305714) [verified]. In all three the **destination and byte
  count come from the guest descriptor**; the fix (`GS.cpp:645`, `:711`, `dbp/sbp = vram_addr & 0x3FFF`)
  changes which VRAM block is read, never where the bytes land [verified]. Sites 45100 and 305540 are
  EE -> GS uploads of streamed loading images [verified]; the still-open packet-offset-0x14 defect is
  on the 45100 upload path, so it can only misplace strips **inside VRAM** (a visual defect), not
  write guest memory [verified from research/25 §10 and the call shape].
- **Indirect: plausible.** The fix restores 48 motion-pack clip descriptors, which is exactly the kind
  of change that alters when the actor's controller attaches and `PlayerUpd` starts consuming input
  (research/21 R1/R2a: a detached controller or state-8 actor skips `FUN_00594cf0`). If B's `PlayerUpd`
  now runs during the 393-401 s wiggle where in Sprint 5 it did not, the UP edges become zoom steps
  [inference]. The GL depth fix is render-only and cannot reach `A+0x200` [inference].

## 4. The one peek that settles it (Q4)

Add to B's peek spec (research/19 syntax): **`*0x408c58+0x200:2`** -> two words, `A+0x200..+0x207`.
- Scoped: byte 0 (`A+0x200`) in `5..0x0c`, byte 2 (`A+0x202`) `1` after a change, and word 1
  (`A+0x204`) = `0x40400000` (3.0f) for the observed HUD.
- Not scoped: byte 0 = `0`, word 1 = `0x3f800000`; modes 1-3 give `0x3f8147ae`, mode 4 `0x41100000`.
Pair it with **`*0x408c58+0x28:1`** and a second-level dump of that pointer's bytes `+1..+0x10`
(slot 4 = UP at `+5`, slot 5 = DOWN at `+6`, values 0/1/2/3) to see the press edges the game read.
Call trace to time the transitions against the drive log:
`PS2X_CALL_TRACE=0x5448a0:SetView,0x5445b0:ZoomIn,0x544400:ZoomOut,0x594cf0:PlayerUpd` (SetView's
`a1` is the new mode). Expected on the next launch: `ZoomIn` entries during the cursor wiggle, none
before, and `SetView a1>=5` immediately before the first scoped frame. The harness-side fix that
follows is to stop pressing UP/DOWN once the READY check sees `[None, None]` (B is already in the
game) — `lobby_select` in `tools_py/parity/online_login_ours.py:1160-1178` loops eight times on
`cursor == -1` [verified].

## 5. Open

- The exact ratchet (why alternating DOWN/UP nets upward) is not proven: the Ghidra split of the
  mode-1..3 cases in `FUN_00544400` drops the argument. A zoom-out from modes 1-3 that does not return
  to 0 would explain it [inference]; the call trace above shows it.
- Which weapon in Frostfire's terrorist `default_weapons` carries `ZoomMode` 3.0 was not read from the
  disc (the weapon defs live in the packed RUN data; not grepped here). `*(weapon+0x288)` via
  `A+0x5e0` answers it live.
- B's per-instance runtime log for s6_ladder4 was not found under `logs/run_*.log`, so the pad-trace
  timestamps were not cross-checked; the drive log ordering (host READY 392.9 s, wiggle 393.1-400.7 s,
  READY check off-lobby 404.8 s) is the basis for §0.
