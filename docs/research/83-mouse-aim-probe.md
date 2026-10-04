# 83 — The mouse aim probe: the view mode under D-pad pulses, and the game's pitch limits (2026-10-04, macOS fork)

Context: `docs/superpowers/specs/2026-10-03-mouse-look-design.md` section 4.4 (the probe that decides right-click
aim-hold) and its revision of 2026-10-04 (look by direct writes; pitch limits from the game). r0001, single-player
mission, default loadout, owner at the keyboard, `PS2X_MOUSE_TRACE=1 PS2X_MOUSE_PROBE=1`. Logs (git-ignored):
`logs/probe2.log`, `logs/probe_shots/`.

## Findings

- **Pad reads: ~28 per second** (`[mouse] reads=` lines: 24-30/s in a mission) while the window presents ~54 fps
  (`[gs-gl stats]`). The game reads the pad once per logic frame at about 30 Hz, so a pulse of 2 held + 2 released
  reads lasts ~130 ms.
- **The ratchet test passes.** The probe key queued 50 UP/DOWN pairs at that timing in third person: 100 of 100 pulses
  changed the mode by exactly one step; it started and ended at mode 0. The ratchet in research/30 section 5 (DOWN/UP
  netting upward on instance B) does not reproduce at this timing; the blind-press drop rate in HAZARDS (1 in 20 at
  59 fps) belongs to presses with no hold guarantee.
- **The cycler, default rifle:** UP goes 0 -> 1 -> 5 (third person, first person, the rifle's one zoom level: modes 2-4
  are skipped); DOWN goes 5 -> 1 -> 0. **Both ends stop**: UP at 5 stays at 5, DOWN at 0 stays at 0. No wrap.
- **Match rule: exact mode.** DOWN from a zoom level lands on 1, the first-person mode a hold starts from, so the
  "modes 1-3 as one class" alternative is not needed.
- **Pitch limits:** with the keyboard's look keys held to each end, `CSealCtrl::m_aimPitch` stops at **+1.04719** (up,
  60 degrees) and **-1.22173** (down, -70 degrees). Both are in the Seal tuning table (r0001 `0x44c250`, research/17):
  `+0x58 = 1.04719`, `+0x5c = -1.22173` (the eight aim-limit floats at +0x54..+0x70 read
  `-0.16, 1.047, -1.222, 1.484, 0.436, -0.349, 0.785, 1.047`). The game does **not** clamp a written `m_aimPitch`
  (spike B reached +1.2), so direct look clamps to these two, read from the table each mission. Standing only: the
  crouched and prone limits were not measured (the table's other pairs are candidates).

## Verdict

**PASS** for closed-loop aim-hold (spec 4.3). Every pulse was answered, the ends stop rather than wrap, and the match
is exact. The abort rules (START, actor change, keyboard zoom, two unanswered presses) stand as specified.
