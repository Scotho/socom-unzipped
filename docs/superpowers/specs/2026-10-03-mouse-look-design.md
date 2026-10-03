# Mouse look and right-click aim — design (fork only)

Date: 2026-10-03. Branch: `feat-mouse-look`. Scope: the macOS fork (Grswld/socom-unzipped-macos) only.
Upstream removed the mouse on purpose (Sprint 10 Q3, ruling R210, `8ff45e7c`); this is not an upstream PR.

## 1. Intent

The owner plays SOCOM II on the Mac with keyboard and mouse and no pad. The mouse aims and turns like a PC
shooter; left click fires; right click is hold-to-aim. Menus stay on the keyboard (out of scope for this step).

Plan of record (owner, 2026-10-03):

- **A** — stick emulation done properly: raw deltas, accumulated, overflow carried, dead-zone offset,
  later linearised against the game's measured stick-to-turn curve. Ship first.
- **Spike B** — one time-boxed session on direct camera yaw/pitch writes (Section 6).
- Mouse code in its own module, to keep upstream syncs cheap.
- Follow-up, not this step: a keyboard-and-mouse switch separate from developer mode.

Success: in a mission the view turns with the mouse with no acceleration and no lost motion; left click fires;
holding right click aims and releasing it returns to the view held before, in every case of Section 4's probe;
`PS2X_MOUSE=0` is byte-identical to the runtime before this work.

## 2. Bindings

| Host | PS2 | Notes |
|---|---|---|
| Mouse X / Y | right stick RX / RY | Section 3 |
| Left button | R1 (fire) | held while held |
| Right button | aim-hold via D-pad UP / DOWN pulses | Section 4 |
| Scroll wheel | nothing | |

## 3. Architecture and mouse look

### 3.1 Files

New (ours):

- `ps2xRuntime/include/runtime/socom2_mouse.h` — the pure core: the accumulator, `curve()`, the aim-hold state
  machine, the knob parsing. No raylib, no OS call, no environment read. This is what the unit tests drive.
- `ps2xRuntime/src/lib/socom2_mouse.cpp` — the glue: knobs, the guest read, the main-thread frame hook.
- `ps2xRuntime/src/lib/socom2_mouse_gc.mm` — macOS only: `GCMouse` raw deltas into the accumulator.
- `ps2xTest/src/socom2_mouse_tests.cpp` — the unit tests.

Upstream files, each a one-line or one-row touch:

- `socom2_host_input.cpp` — `socom2MouseApply(rdram, next)` after the keyboard is applied.
- `socom2_pad2_hle.cpp` — pass `rdram` to the poll.
- `ps2_runtime.cpp` — `socom2MouseFrame()` once per frame on the main thread.
- `ps2xRuntime/CMakeLists.txt` and the test CMake — the new sources; `GameController.framework` on Apple.
- `ps2xShared/include/ps2x/knobs.h`, `docs/KNOBS.md` (generated) — the knob rows the registry tests demand.

### 3.2 Data flow

1. **Raw deltas.** `GCMouse.current.mouseInput.mouseMovedHandler` delivers unaccelerated HID counts. The handler
   adds them to a lock-free accumulator (two `std::atomic<int64_t>`, fixed point 1/256 count). If no `GCMouse`
   appears within 2 s of the window, the frame hook feeds raylib's `GetMouseDelta()` instead (accelerated) and
   logs `[mouse] raw deltas unavailable, using GetMouseDelta` once.
2. **Each pad read (game thread, `scePad2Read`).** Drain the accumulator (exchange with 0). Add the carry. Apply
   `PS2X_MOUSE_SENS` and `PS2X_MOUSE_INVERT_Y`. Map with `curve()`: identity scale, plus the dead-zone offset
   (`PS2X_MOUSE_DEADZONE`) on any non-zero value, then (Section 3.4) the linearisation table. Clamp to full
   deflection; the excess becomes the carry for the next read.
   - Carry cap: at most what full deflection consumes in 100 ms of reads; anything beyond is dropped, so a big
     flick cannot keep the view turning after the hand stops.
   - When the mouse contributes motion on a read, it overrides IJKL on RX/RY; otherwise the keyboard's value stands.
3. **Capture (main thread, `socom2MouseFrame`).**
   - Window focused and the mouse enabled: `DisableCursor()` (hidden, locked).
   - Focus lost: `EnableCursor()`; accumulator and carry cleared; a held left/right button is released through
     the normal paths (Section 4's release handling applies).
   - The first click after a release recaptures and is swallowed (it does not fire or aim).
   - Esc / START releases the cursor, so the pause menu and the macOS menu bar are reachable; a click recaptures.

### 3.3 Knobs

| Knob | Default | Meaning |
|---|---|---|
| `PS2X_MOUSE` | 1 | 0 = off, byte-identical to before this work |
| `PS2X_MOUSE_SENS` | 1.0 | stick units per raw count |
| `PS2X_MOUSE_INVERT_Y` | 0 | 1 inverts RY |
| `PS2X_MOUSE_DEADZONE` | measured (probe starts at 0x18) | stick units added to any non-zero output |
| `PS2X_MOUSE_TRACE` | 0 | Dev: one line per pad read with deltas, carry, axis, aim-hold state and mode |

`knobOn(name, dflt)` ignores the knobs.h default column, so every read passes its default in code.

Until the follow-up keyboard-and-mouse switch exists, the mouse is active only when the keyboard scope is Full
(developer mode, `PS2X_DEV=1`); without WASD it would be of no use.

### 3.4 Linearisation (after the first play test)

On the replay rig, hold RX at fixed values from 0x80 to 0xFF in steps of 8 for 2 s each in a mission, record the
camera yaw per frame (the camera fields from Section 6's map, or screen-space motion if Spike B finds none), and
fit yaw rate against deflection. The inverse becomes a 128-entry table in `socom2_mouse.h` that `curve()` applies,
so turn rate is linear in mouse speed. The dead-zone default comes out of the same measurement (the lowest value
that turns).

## 4. Right-click aim-hold (closed loop)

### 4.1 What the game does

`docs/research/30-scope-at-spawn.md`: the view mode is the byte at `A+0x200`, A = the local player actor.
`PlayerUpd` (`FUN_00594cf0`) zooms in one mode on a D-pad UP press edge and out one mode on a D-pad DOWN press
edge. Mode 0 is third person, 1-3 first person (FOV 1.01), 4 and up the weapon's `ZoomMode` table. The press
edge comes from a per-frame 0 → 1 (press) → 2 (held) → 3 (release) → 0 machine, so a press must be seen
released before the next one counts. An unexplained ratchet is on record (alternating DOWN/UP netted upward on
instance B, research/30 §5), and blind presses have been dropped about 1 in 20 at 59 fps (HAZARDS). The loop
below exists because of those two facts.

### 4.2 Reading the mode (read-only)

A per-revision pair, kept in our module (not upstream's `socom2_addresses.h`), from `tools_py/parity/guest_addresses.py`:

| Field | r0001 | r0004 |
|---|---|---|
| `player_actor` (pointer) | `0x00408C58` | `0x00435618` |
| `actor_vtable` (word 0 of a live actor) | `0x006691A0` | `0x00668B20` |

`A = *player_actor`; the mode is readable only when A is non-zero, inside RDRAM, and `*(A+0) == actor_vtable`.
`+0x200` sits below r0004's inserted word at `+0x1334`, so the offset is the same in both. An unknown revision
reads "not readable" and right click does nothing. No guest memory is written.

### 4.3 The state machine (pure, in `socom2_mouse.h`)

Inputs per pad read: right button down; the mode (or not readable); A; START pressed this read; the keyboard's
UP/DOWN pressed this read. Output: UP, DOWN or neither for this read, OR-ed into `next.button`.

- **Pulse queue.** Presses are queued in order. Each is held 2 reads, then released 2 reads before the next.
- **Idle → Holding** on right-button down with the mode readable: store `mode0` and `A0`, queue one UP.
  Not readable (menus, loading, dead): nothing happens.
- **Holding → Restoring** on release. One step at a time, after the queue is empty: if the mode matches `mode0`,
  done (Idle). If above, queue DOWN; if below, queue UP. After each press, wait up to 6 reads for the mode to change.
- **Cap.** At most 4 restore presses; on reaching it, stop and trace `cap`.
- **Aborts** (go Idle, queue cleared, trace the reason):
  - A changed or became unreadable (death, respawn, mission end);
  - START pressed (pause; no press may reach the pause menu);
  - a press went unanswered for 6 reads (paused, cutscene, input ignored);
  - the player pressed the keyboard UP/DOWN while holding (they took the zoom over; no restore).
- **Re-press while Restoring:** the queue is cleared, `mode0` is kept (the view never got back), and one UP is
  queued as for a fresh hold.

Whether modes 1-3 count as one class for "matches" (because the cycler may never land on 2 or 3) is decided by
the probe; the comparison is one function so the answer is one line.

### 4.4 The probe (before the state machine is built)

A Dev trace of the mode per pad read (`PS2X_MOUSE_TRACE`, built first), with D-pad presses sent by script in a
mission. Each case records the mode sequence and a screenshot at every change:

1. UP then DOWN from mode 0 (third person), with the default rifle and with a scoped weapon.
2. The same from first person.
3. UP at maximum zoom: stops or wraps?
4. DOWN at mode 0: stops or wraps?
5. Weapon swap while zoomed.
6. Death and respawn while zoomed.
7. Pause (START) while zoomed, then unpause.
8. Keyboard UP/DOWN pressed while zoomed by the loop.
9. 50 UP/DOWN cycles at the queue's timing: the ratchet test. The mode must end where it started.

**Pass for closed-loop A:** in every case the loop either returns to `mode0` within the cap or aborts by a rule of
4.3, no press reaches the pause menu, and case 9 shows no drift. **Fail:** right click falls back to plain UP per
click (one zoom step), with D-pad DOWN on the keyboard to zoom out, and the direct mode write ("C") moves into
Spike B.

## 5. Testing

Tests first (red, then green), in `ps2xTest/src/socom2_mouse_tests.cpp`:

- Accumulator: deltas between reads sum; a drain returns them once; concurrent adds from a second thread are not lost.
- Curve: sensitivity, invert Y, the dead-zone offset on non-zero only, the clamp, overflow carried to the next read,
  the carry cap, the carry cleared on focus loss.
- Aim-hold: a model of the game's cycler (configurable: stop or wrap at the ends, a ratchet, a 1-in-20 dropped
  edge, an unresponsive game), driving every case of 4.4 and every abort of 4.3; pulse timing (2 held, 2 released).
- Off switch: with `PS2X_MOUSE=0`, `socom2MouseApply` leaves the state `memcmp`-equal.
- Knob rows: the existing registry tests (C++ and `tools_py/tests/test_knobs_registry.py`) with the new rows; `docs/KNOBS.md` regenerated.

In the game: the probe (4.4), then the owner's play test, then the linearisation measurement (3.4). Full suite
(`build_macos.sh test`) green before the merge.

## 6. Spike B — direct camera control (one session)

Question: can the host steer the view by writing the camera's yaw and pitch directly?

- Starting map: the SOCOM I class layouts in reCOM PR #4 (`gamez_types.h`), checked against SOCOM II's actor
  and `cameraHolder` (`0x415ff0`, already in `socom2_addresses.h`).
- Pass: writing yaw and pitch steers the view in third person, first person/scoped, and while zoomed, without the
  game fighting the write.
- Time box: one session. Not found in the time box → stop and write up what was found.
- Also carries "C" (the direct aim-mode write) if closed-loop A fails.
- Output is a recommendation; anything built is throwaway.

## 7. Out of scope

Mouse in menus; the scroll wheel; the keyboard-and-mouse switch separate from developer mode (follow-up);
the launcher's CONTROLLER page; online play testing; Windows/Linux builds of the mouse module beyond the
`GetMouseDelta` fallback compiling.
