# Mouse Look and Right-Click Aim-Hold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In a SOCOM II mission on macOS, the mouse turns the view with raw, unaccelerated, lossless motion; left click fires; holding right click aims and releasing returns the view held before.

**Architecture:** A pure core header (`socom2_mouse_core.h`: accumulator, look curve with carried overflow, guest mode reader, pulse queue, aim-hold state machine, capture state machine) driven by unit tests; a thin glue file (`socom2_mouse.cpp`) that reads knobs, owns the globals and is called from the existing pad poll (game thread) and the frame loop (main thread); and a macOS-only `GCMouse` source of raw deltas (`socom2_mouse_gc.mm`). Upstream files get one-line touches only.

**Tech Stack:** C++20, AppleClang 17, raylib 5.5 (GLFW), Apple GameController framework (Objective-C++), MiniTest (`ps2x_tests`), Python `unittest` (knob registry).

**Spec:** `docs/superpowers/specs/2026-10-03-mouse-look-design.md`

## Global Constraints

- Fork only (Grswld/socom-unzipped-macos). Not an upstream PR. Branch `feat-mouse-look`.
- Commits name their paths: `git commit -m ... -- <paths>`; never `git add -A` / `git add .`. Subject <= 120 chars. End every message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- No `/Users/<name>/` paths in committed files (leak check): write `$HOME/...` or repo-relative.
- Never commit disc data, generated C++, `logs/`, `.DS_Store`, or the two hook-script mode changes already in the tree (`scripts/hooks/claude_pretool.sh`, `scripts/hooks/claude_session_end.sh`).
- Use `/opt/homebrew` tools only; never `/usr/local`. One build or game at a time on the host (CLAUDE.md "The lock").
- No guest memory writes anywhere in this plan (Spike B is a separate session).
- `PS2X_MOUSE=0` must be byte-identical to the runtime before this work.
- `ps2x::knobOn(name, dflt)` ignores the knobs.h default column: every read passes its default in code.
- The mouse is active only when the keyboard scope is `KeyboardScope::Full` (developer mode, `PS2X_DEV=1`).
- Pulse timing: every synthesized D-pad press is held 2 pad reads, then released 2 pad reads before the next.
- Aim-hold restore cap: 4 presses. Unanswered press: wait 6 reads after the pulse ends.
- Refinement over the spec (reason: HAZARDS' measured 1-in-20 dropped edge): an unanswered restore press is re-sent once (counting toward the cap); two unanswered in a row abort with `unanswered`.
- Carry cap: 6 pad reads' worth of full deflection (~100 ms at 59 reads/s).

## Review Focus

1. **The game thread and the main thread both touch mouse state.** Raw deltas arrive on GCMouse's handler queue, capture runs on the main thread, the drain on the game thread. Expected: no lost or double-counted motion and no torn reads. Pinned by Task 1's two-thread accumulator test, and by Task 4's rule that cross-thread state is atomics only.
2. **A synthesized D-pad press while the pause menu is open.** It would move the menu cursor. Expected: none is ever sent after START. Pinned by Task 7's `pause aborts and sends nothing more` test.
3. **The recapture click firing a shot.** Expected: a click that recaptures does nothing in the game, even when held. Pinned by Task 3's `the recapturing click is swallowed until every button is up`.
4. **Leaving a mission (death, quit to menu) with right click held.** Expected: no presses into the menus, and right click does nothing until the actor is readable again. Pinned by Task 7's `actor change aborts` and `unreadable mode means right click does nothing`.
5. **Huge single deltas (a flick across the desk, a 4000 dpi mouse).** Expected: the view turns at most full speed, and stops within ~100 ms of the hand stopping. Pinned by Task 1's `the carry is capped`.

---

## File Structure

| File | Status | Responsibility |
|---|---|---|
| `third_party/ps2recomp/ps2xRuntime/include/runtime/socom2_mouse_core.h` | Create | Pure core: everything testable. No raylib, OS or environment. |
| `third_party/ps2recomp/ps2xRuntime/src/lib/socom2_mouse.h` | Create | Glue API: `socom2MouseApply`, `socom2MouseFrame`, `socom2MouseAddRaw`, `socom2MouseGcStart` |
| `third_party/ps2recomp/ps2xRuntime/src/lib/socom2_mouse.cpp` | Create | Glue: knobs, globals, raylib calls, trace, probe key |
| `third_party/ps2recomp/ps2xRuntime/src/lib/socom2_mouse_gc.mm` | Create | macOS: GCMouse raw deltas to `socom2MouseAddRaw` |
| `third_party/ps2recomp/ps2xRuntime/src/lib/socom2_mouse_gc_stub.cpp` | Create | Non-Apple: `socom2MouseGcStart` returns false |
| `third_party/ps2recomp/ps2xTest/src/socom2_mouse_tests.cpp` | Create | Unit tests for the core |
| `third_party/ps2recomp/ps2xRuntime/src/lib/socom2_host_input.{h,cpp}` | Modify | Poll takes `rdram`; one call to `socom2MouseApply` |
| `third_party/ps2recomp/ps2xRuntime/src/lib/socom2_pad2_hle.cpp:81` | Modify | Pass `rdram` |
| `third_party/ps2recomp/ps2xRuntime/src/lib/ps2_runtime.cpp:3081` | Modify | One `socom2MouseFrame()` call before `BeginDrawing()` |
| `third_party/ps2recomp/ps2xRuntime/CMakeLists.txt:528` | Modify | New sources; OBJCXX + GameController on Apple |
| `third_party/ps2recomp/ps2xTest/CMakeLists.txt:58,177` | Modify | Test file; glue sources linked into `ps2x_tests` |
| `third_party/ps2recomp/ps2xTest/src/main.cpp` | Modify | `register_socom2_mouse_tests()` |
| `third_party/ps2recomp/ps2xShared/include/ps2x/knobs.h` | Modify | Six Dev rows |
| `docs/KNOBS.md` | Regenerate | `python -m tools_py.knobs write` |
| `docs/research/86-mouse-aim-probe.md` | Create (Task 6) | Probe findings and the pass/fail decision |

Commands used throughout (from the repo root, `$HOME/socom-unzipped`):

- Build and run C++ tests: `cmake --build third_party/ps2recomp/build-macos --target ps2x_tests -j 8 && (cd third_party/ps2recomp/build-macos/ps2xTest && ./ps2x_tests 2>&1 | grep -E -A30 "\[Suite\]: Socom2Mouse" | head -60; ./ps2x_tests 2>&1 | tail -3)`. Call this **RUN_CXX**.
- Python knob tests: `.venv/bin/python -m unittest tools_py.tests.test_knobs_registry tools_py.tests.test_knob_read_sites tools_py.tests.test_knob_flag_defaults -v`. Call this **RUN_PY_KNOBS**.
- Game build: `bash scripts/build_macos.sh runtime`. Call this **BUILD_GAME**.
- Full suite before merge: `bash scripts/build_macos.sh test`.

---

### Task 1: The look core — accumulator and curve with carried overflow

**Files:**
- Create: `third_party/ps2recomp/ps2xRuntime/include/runtime/socom2_mouse_core.h`
- Create: `third_party/ps2recomp/ps2xTest/src/socom2_mouse_tests.cpp`
- Modify: `third_party/ps2recomp/ps2xTest/CMakeLists.txt` (add `src/socom2_mouse_tests.cpp` after line 58, `src/gs_gl_flush_reasons_tests.cpp`)
- Modify: `third_party/ps2recomp/ps2xTest/src/main.cpp` (declare and call `register_socom2_mouse_tests()`, after `register_socom2_msg_bounds_tests();`)

**Interfaces:**
- Produces (namespace `socom2_mouse`):
  - `struct Config { bool enabled = true; float sens = 1.0f; bool invertY = false; int deadzone = 0x18; bool trace = false; bool probe = false; };`
  - `class Accumulator { void add(double dx, double dy); void drain(double &dx, double &dy); void clear(); };`
  - `struct LookState { double carryX = 0.0, carryY = 0.0; };`
  - `struct LookOut { bool moved; uint8_t rx; uint8_t ry; };`
  - `LookOut look(const Config &cfg, double dx, double dy, LookState &state);`
  - `constexpr int kCarryCapReads = 6;`

- [ ] **Step 1: Write the failing tests**

`third_party/ps2recomp/ps2xTest/src/socom2_mouse_tests.cpp`:

```cpp
// Mouse look and right-click aim-hold (macOS fork, spec docs/superpowers/specs/2026-10-03-mouse-look-design.md).
#include "MiniTest.h"
#include "runtime/socom2_mouse_core.h"

#include <thread>

using namespace socom2_mouse;

void register_socom2_mouse_tests()
{
    MiniTest::Case("Socom2MouseLook", [](TestCase &tc)
    {
        tc.Run("deltas between reads sum, and a drain returns them once", [](TestCase &t)
        {
            Accumulator acc;
            acc.add(1.5, -2.0);
            acc.add(2.5, 1.0);
            double dx = 0, dy = 0;
            acc.drain(dx, dy);
            t.Equals(dx, 4.0, "x summed");
            t.Equals(dy, -1.0, "y summed");
            acc.drain(dx, dy);
            t.Equals(dx, 0.0, "second drain x is empty");
            t.Equals(dy, 0.0, "second drain y is empty");
        });

        tc.Run("adds from another thread are not lost against concurrent drains", [](TestCase &t)
        {
            Accumulator acc;
            double total = 0, dy = 0, dx = 0;
            std::thread producer([&] { for (int i = 0; i < 100000; ++i) acc.add(1.0, 0.0); });
            for (int i = 0; i < 1000; ++i) { acc.drain(dx, dy); total += dx; }
            producer.join();
            acc.drain(dx, dy);
            total += dx;
            t.Equals(total, 100000.0, "every count arrives exactly once");
        });

        tc.Run("no motion and no carry leaves the stick to the keyboard", [](TestCase &t)
        {
            Config cfg; LookState s;
            const LookOut out = look(cfg, 0.0, 0.0, s);
            t.IsFalse(out.moved, "not moved");
        });

        tc.Run("sensitivity scales, the dead-zone offset is added to non-zero output only", [](TestCase &t)
        {
            Config cfg; cfg.sens = 2.0f; cfg.deadzone = 0x18; LookState s;
            const LookOut out = look(cfg, 10.0, 0.0, s);   // 20 stick units + 0x18
            t.IsTrue(out.moved, "moved");
            t.Equals(static_cast<int>(out.rx), 0x80 + 0x18 + 20, "rx = centre + dead zone + scaled delta");
            t.Equals(static_cast<int>(out.ry), 0x80, "ry untouched stays centred");
            const LookOut neg = look(cfg, -10.0, 0.0, s);
            t.Equals(static_cast<int>(neg.rx), 0x80 - 0x18 - 20, "negative mirrors");
        });

        tc.Run("invert Y flips the vertical axis", [](TestCase &t)
        {
            Config cfg; cfg.deadzone = 0; cfg.invertY = true; LookState s;
            const LookOut out = look(cfg, 0.0, 10.0, s);
            t.Equals(static_cast<int>(out.ry), 0x80 - 10, "mouse down looks up when inverted");
        });

        tc.Run("output clamps to full deflection and the excess is carried to the next read", [](TestCase &t)
        {
            Config cfg; cfg.deadzone = 0x18; LookState s;
            // Full positive deflection is 0xFF = centre + 127: 127 - 0x18 = 103 units of motion fit in a read.
            const LookOut first = look(cfg, 150.0, 0.0, s);
            t.Equals(static_cast<int>(first.rx), 0xFF, "first read is full right");
            t.Equals(s.carryX, 47.0, "150 - 103 carried");
            const LookOut second = look(cfg, 0.0, 0.0, s);
            t.IsTrue(second.moved, "the carry moves the stick with the mouse still");
            t.Equals(static_cast<int>(second.rx), 0x80 + 0x18 + 47, "the carry is spent");
            t.Equals(s.carryX, 0.0, "nothing left");
            // Full negative deflection is 0x00 = centre - 128; the usable span is kept symmetric at 127.
            LookState n;
            const LookOut neg = look(cfg, -150.0, 0.0, n);
            t.Equals(static_cast<int>(neg.rx), 0x80 - 127, "full left");
            t.Equals(n.carryX, -47.0, "negative carry");
        });

        tc.Run("the carry is capped at six reads of full deflection", [](TestCase &t)
        {
            Config cfg; cfg.deadzone = 0x18; LookState s;
            look(cfg, 100000.0, 0.0, s);
            t.Equals(s.carryX, static_cast<double>(kCarryCapReads * (127 - 0x18)), "a flick cannot turn forever");
            int reads = 0;
            while (look(cfg, 0.0, 0.0, s).moved && reads < 100) ++reads;
            t.Equals(reads, kCarryCapReads, "the view stops after exactly the cap's reads");
        });

        tc.Run("fractional motion below one unit is carried, not lost", [](TestCase &t)
        {
            Config cfg; cfg.deadzone = 0; cfg.sens = 0.25f; LookState s;
            int total = 0;
            for (int i = 0; i < 8; ++i)
            {
                const LookOut out = look(cfg, 1.0, 0.0, s);
                if (out.moved) total += out.rx - 0x80;
            }
            t.Equals(total, 2, "eight quarter-units arrive as two whole units");
        });
    });
}
```

Register it: in `ps2xTest/src/main.cpp` add `void register_socom2_mouse_tests();` beside the other declarations and `register_socom2_mouse_tests();` after `register_socom2_msg_bounds_tests();`. Add `src/socom2_mouse_tests.cpp   # macOS fork: mouse look and aim-hold` to `ps2_test_lib`'s list in `ps2xTest/CMakeLists.txt` after the `gs_gl_flush_reasons_tests.cpp` line.

- [ ] **Step 2: Run to verify it fails**

Run: RUN_CXX. Expected: a compile error, `'runtime/socom2_mouse_core.h' file not found`.

- [ ] **Step 3: Write the implementation**

`third_party/ps2recomp/ps2xRuntime/include/runtime/socom2_mouse_core.h`:

```cpp
#pragma once
// Mouse look and right-click aim-hold -- the macOS fork's own module (spec:
// docs/superpowers/specs/2026-10-03-mouse-look-design.md). Upstream removed the mouse on purpose (R210), so this
// lives here, apart, to keep upstream syncs cheap.
//
// Pure: no raylib, no OS call, no environment read. socom2_mouse.cpp is the glue.
#include <algorithm>
#include <atomic>
#include <cmath>
#include <cstdint>

namespace socom2_mouse
{
    struct Config
    {
        bool enabled = true;     // PS2X_MOUSE
        float sens = 1.0f;       // PS2X_MOUSE_SENS: stick units per raw count
        bool invertY = false;    // PS2X_MOUSE_INVERT_Y
        int deadzone = 0x18;     // PS2X_MOUSE_DEADZONE: stick units added to any non-zero output (to be measured)
        bool trace = false;      // PS2X_MOUSE_TRACE
        bool probe = false;      // PS2X_MOUSE_PROBE
    };

    // Raw counts from any thread, drained by the game thread at each pad read. Fixed point (1/256 count) so the
    // add is one atomic fetch_add and a drain is one exchange per axis: nothing is lost or counted twice.
    class Accumulator
    {
    public:
        void add(double dx, double dy)
        {
            m_x.fetch_add(toFixed(dx), std::memory_order_relaxed);
            m_y.fetch_add(toFixed(dy), std::memory_order_relaxed);
        }
        void drain(double &dx, double &dy)
        {
            dx = static_cast<double>(m_x.exchange(0, std::memory_order_relaxed)) / kOne;
            dy = static_cast<double>(m_y.exchange(0, std::memory_order_relaxed)) / kOne;
        }
        void clear()
        {
            m_x.store(0, std::memory_order_relaxed);
            m_y.store(0, std::memory_order_relaxed);
        }

    private:
        static constexpr double kOne = 256.0;
        static int64_t toFixed(double v) { return static_cast<int64_t>(std::llround(v * kOne)); }
        std::atomic<int64_t> m_x{0};
        std::atomic<int64_t> m_y{0};
    };

    constexpr int kStickSpan = 127;      // usable deflection either side of 0x80, kept symmetric
    constexpr int kCarryCapReads = 6;    // ~100 ms of reads at 59/s

    struct LookState
    {
        double carryX = 0.0;
        double carryY = 0.0;
    };

    struct LookOut
    {
        bool moved = false;
        uint8_t rx = 0x80u;
        uint8_t ry = 0x80u;
    };

    namespace detail
    {
        // One axis: `units` of wanted motion (this read's scaled delta plus the carry) -> the axis byte, with what
        // does not fit (the excess past full deflection, and the fraction under one unit) left in `carry`.
        inline uint8_t axis(double units, int deadzone, double &carry, bool &moved)
        {
            const int room = std::max(1, kStickSpan - deadzone);
            const double cap = static_cast<double>(kCarryCapReads * room);
            const double sign = units < 0.0 ? -1.0 : 1.0;
            const double magnitude = std::fabs(units);
            const int whole = static_cast<int>(std::min<double>(std::floor(magnitude), room));
            carry = std::min(magnitude - whole, cap) * sign;
            if (whole == 0)
                return 0x80u;
            moved = true;
            return static_cast<uint8_t>(0x80 + static_cast<int>(sign) * (deadzone + whole));
        }
    }

    // One pad read's look: the drained delta, scaled and offset, clamped, overflow carried.
    inline LookOut look(const Config &cfg, double dx, double dy, LookState &state)
    {
        LookOut out;
        const double wantX = dx * cfg.sens + state.carryX;
        const double wantY = dy * cfg.sens * (cfg.invertY ? -1.0 : 1.0) + state.carryY;
        out.rx = detail::axis(wantX, cfg.deadzone, state.carryX, out.moved);
        out.ry = detail::axis(wantY, cfg.deadzone, state.carryY, out.moved);
        return out;
    }
}
```

- [ ] **Step 4: Run to verify it passes**

Run: RUN_CXX. Expected: suite `Socom2MouseLook` all passed; the total `Failed: 0`.

Check the "full left" case: 0x80 - 0x18 - 103 = 0x01. The test expects `0x80 - 127` = 0x01. They agree.

- [ ] **Step 5: Commit**

```bash
git add third_party/ps2recomp/ps2xRuntime/include/runtime/socom2_mouse_core.h third_party/ps2recomp/ps2xTest/src/socom2_mouse_tests.cpp
git commit -m "feat(mouse): the look core -- raw counts accumulated, a dead-zone offset, the overflow carried and capped" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- third_party/ps2recomp/ps2xRuntime/include/runtime/socom2_mouse_core.h third_party/ps2recomp/ps2xTest/src/socom2_mouse_tests.cpp third_party/ps2recomp/ps2xTest/CMakeLists.txt third_party/ps2recomp/ps2xTest/src/main.cpp
```

---

### Task 2: The guest mode reader and the pulse queue

**Files:**
- Modify: `third_party/ps2recomp/ps2xRuntime/include/runtime/socom2_mouse_core.h`
- Modify: `third_party/ps2recomp/ps2xTest/src/socom2_mouse_tests.cpp`

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces:
  - `struct Revision { const char *name; uint32_t playerActor; uint32_t actorVtable; };`
  - `const Revision *revisionFor(const char *name);` (nullptr for unknown)
  - `struct ModeRead { bool ok = false; uint32_t actor = 0; uint8_t mode = 0; };`
  - `ModeRead readMode(const uint8_t *rdram, const Revision *rev);` (rdram is the 32 MB guest RAM or nullptr)
  - `constexpr uint32_t kModeOffset = 0x200;  constexpr uint32_t kRamSize = 32u * 1024u * 1024u;`
  - `enum class Pulse : uint8_t { None, Up, Down };`
  - `class PulseQueue { void push(Pulse p); Pulse tick(); bool idle() const; void clear(); };`
  - `constexpr int kPulseHeldReads = 2, kPulseGapReads = 2;`

- [ ] **Step 1: Write the failing tests**

Append inside `register_socom2_mouse_tests()` in `socom2_mouse_tests.cpp`:

```cpp
    MiniTest::Case("Socom2MouseModeRead", [](TestCase &tc)
    {
        auto put32 = [](std::vector<uint8_t> &ram, uint32_t addr, uint32_t v)
        {
            for (int i = 0; i < 4; ++i) ram[addr + i] = static_cast<uint8_t>(v >> (8 * i));
        };

        tc.Run("the two revisions are known, anything else is not", [](TestCase &t)
        {
            t.IsNotNull(revisionFor("r0001"), "r0001");
            t.IsNotNull(revisionFor("r0004"), "r0004");
            t.IsNull(revisionFor("r0002"), "unknown");
            t.IsNull(revisionFor(nullptr), "null");
            t.Equals(revisionFor("r0001")->playerActor, 0x00408C58u, "r0001 player_actor (guest_addresses.py)");
            t.Equals(revisionFor("r0004")->actorVtable, 0x00668B20u, "r0004 actor_vtable (guest_addresses.py)");
        });

        tc.Run("a live actor's mode byte is read", [&](TestCase &t)
        {
            std::vector<uint8_t> ram(kRamSize, 0);
            const Revision *r = revisionFor("r0001");
            put32(ram, r->playerActor, 0x00D00000u);
            put32(ram, 0x00D00000u, r->actorVtable);
            ram[0x00D00000u + kModeOffset] = 5;
            const ModeRead m = readMode(ram.data(), r);
            t.IsTrue(m.ok, "readable");
            t.Equals(m.actor, 0x00D00000u, "actor");
            t.Equals(static_cast<int>(m.mode), 5, "mode");
        });

        tc.Run("a KSEG pointer is masked into RAM", [&](TestCase &t)
        {
            std::vector<uint8_t> ram(kRamSize, 0);
            const Revision *r = revisionFor("r0001");
            put32(ram, r->playerActor, 0x20D00000u);   // uncached alias
            put32(ram, 0x00D00000u, r->actorVtable);
            ram[0x00D00000u + kModeOffset] = 1;
            t.IsTrue(readMode(ram.data(), r).ok, "the alias reads the same object");
        });

        tc.Run("null actor, wrong vtable, out of range, no RAM, unknown revision: not readable", [&](TestCase &t)
        {
            std::vector<uint8_t> ram(kRamSize, 0);
            const Revision *r = revisionFor("r0001");
            t.IsFalse(readMode(ram.data(), r).ok, "null actor");
            put32(ram, r->playerActor, 0x00D00000u);
            put32(ram, 0x00D00000u, 0x12345678u);
            t.IsFalse(readMode(ram.data(), r).ok, "wrong vtable");
            put32(ram, r->playerActor, kRamSize - 0x100u);
            t.IsFalse(readMode(ram.data(), r).ok, "the mode byte would be past the end of RAM");
            t.IsFalse(readMode(nullptr, r).ok, "no RAM");
            t.IsFalse(readMode(ram.data(), nullptr).ok, "unknown revision");
        });
    });

    MiniTest::Case("Socom2MousePulseQueue", [](TestCase &tc)
    {
        tc.Run("a pulse is held two reads, then released two before the next", [](TestCase &t)
        {
            PulseQueue q;
            q.push(Pulse::Up);
            q.push(Pulse::Down);
            const Pulse expected[] = {Pulse::Up, Pulse::Up, Pulse::None, Pulse::None,
                                      Pulse::Down, Pulse::Down, Pulse::None, Pulse::None, Pulse::None};
            for (int i = 0; i < 9; ++i)
                t.Equals(static_cast<int>(q.tick()), static_cast<int>(expected[i]), "read " + std::to_string(i));
            t.IsTrue(q.idle(), "idle after both pulses and their gaps");
        });

        tc.Run("idle only once the last gap has passed", [](TestCase &t)
        {
            PulseQueue q;
            t.IsTrue(q.idle(), "a new queue is idle");
            q.push(Pulse::Up);
            t.IsFalse(q.idle(), "queued");
            q.tick(); q.tick(); q.tick();
            t.IsFalse(q.idle(), "still in the gap");
            q.tick();
            t.IsTrue(q.idle(), "gap done");
        });

        tc.Run("clear drops the queue and any pulse in flight", [](TestCase &t)
        {
            PulseQueue q;
            q.push(Pulse::Up); q.push(Pulse::Up);
            q.tick();
            q.clear();
            t.IsTrue(q.idle(), "idle");
            t.Equals(static_cast<int>(q.tick()), static_cast<int>(Pulse::None), "nothing sent");
        });
    });
```

Add `#include <string>` and `#include <vector>` to the test file's includes.

- [ ] **Step 2: Run to verify it fails**

Run: RUN_CXX. Expected: compile errors, `use of undeclared identifier 'revisionFor'` and `'PulseQueue'`.

- [ ] **Step 3: Write the implementation**

Append to `socom2_mouse_core.h`, inside `namespace socom2_mouse` (add `#include <cstring>` and `#include <deque>` at the top):

```cpp
    // ---- Reading the view mode (read-only; spec section 4.2) ------------------------------------------------
    // From tools_py/parity/guest_addresses.py (player_actor, actor_vtable), kept here rather than in upstream's
    // socom2_addresses.h to keep the fork's diff of upstream files small. The mode byte is A+0x200
    // (docs/research/30-scope-at-spawn.md); r0004's inserted actor word is at +0x1334, above it.
    struct Revision
    {
        const char *name;
        uint32_t playerActor;   // the global holding the local player actor's pointer
        uint32_t actorVtable;   // word 0 of a live actor
    };

    inline constexpr Revision kRevisions[] = {
        {"r0001", 0x00408C58u, 0x006691A0u},
        {"r0004", 0x00435618u, 0x00668B20u},
    };

    inline const Revision *revisionFor(const char *name)
    {
        if (name == nullptr)
            return nullptr;
        for (const Revision &r : kRevisions)
            if (std::strcmp(r.name, name) == 0)
                return &r;
        return nullptr;
    }

    constexpr uint32_t kModeOffset = 0x200u;
    constexpr uint32_t kRamSize = 32u * 1024u * 1024u;   // == PS2_RAM_SIZE (ps2_memory.h)

    struct ModeRead
    {
        bool ok = false;
        uint32_t actor = 0;
        uint8_t mode = 0;
    };

    namespace detail
    {
        inline uint32_t read32(const uint8_t *ram, uint32_t addr)
        {
            uint32_t v;
            std::memcpy(&v, ram + addr, sizeof(v));   // little-endian host and guest
            return v;
        }
    }

    inline ModeRead readMode(const uint8_t *rdram, const Revision *rev)
    {
        ModeRead m;
        if (rdram == nullptr || rev == nullptr)
            return m;
        const uint32_t pointer = detail::read32(rdram, rev->playerActor & 0x1FFFFFFFu);
        const uint32_t actor = pointer & 0x1FFFFFFFu;   // KSEG0/KSEG1 and the uncached alias fold onto RAM
        if (actor == 0u || actor + kModeOffset >= kRamSize || (actor & 3u) != 0u)
            return m;
        if (detail::read32(rdram, actor) != rev->actorVtable)
            return m;
        m.ok = true;
        m.actor = actor;
        m.mode = rdram[actor + kModeOffset];
        return m;
    }

    // ---- Synthesized D-pad presses (spec section 4.3) -------------------------------------------------------
    // The game's per-frame reader turns a button into 0 -> 1 (press edge) -> 2 (held) -> 3 (release) -> 0, so a
    // press is only a press if it was seen released first. Each pulse: held 2 reads, released 2 reads.
    enum class Pulse : uint8_t { None, Up, Down };

    constexpr int kPulseHeldReads = 2;
    constexpr int kPulseGapReads = 2;

    class PulseQueue
    {
    public:
        void push(Pulse p) { m_queue.push_back(p); }
        Pulse tick()
        {
            if (m_phase == 0)
            {
                if (m_queue.empty())
                    return Pulse::None;
                m_current = m_queue.front();
                m_queue.pop_front();
                m_phase = kPulseHeldReads + kPulseGapReads;
            }
            const Pulse out = m_phase > kPulseGapReads ? m_current : Pulse::None;
            --m_phase;
            return out;
        }
        bool idle() const { return m_phase == 0 && m_queue.empty(); }
        void clear()
        {
            m_queue.clear();
            m_phase = 0;
        }

    private:
        std::deque<Pulse> m_queue;
        Pulse m_current = Pulse::None;
        int m_phase = 0;   // reads left in the pulse in flight (held reads, then gap reads)
    };
```

- [ ] **Step 4: Run to verify it passes**

Run: RUN_CXX. Expected: `Socom2MouseLook`, `Socom2MouseModeRead` and `Socom2MousePulseQueue` all passed; `Failed: 0`.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(mouse): read the actor's view mode (read-only, vtable-checked) and queue D-pad pulses at 2+2 reads" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- third_party/ps2recomp/ps2xRuntime/include/runtime/socom2_mouse_core.h third_party/ps2recomp/ps2xTest/src/socom2_mouse_tests.cpp
```

---

### Task 3: The capture state machine

**Files:**
- Modify: `third_party/ps2recomp/ps2xRuntime/include/runtime/socom2_mouse_core.h`
- Modify: `third_party/ps2recomp/ps2xTest/src/socom2_mouse_tests.cpp`

**Interfaces:**
- Produces:
  - `struct CaptureInputs { bool enabled; bool focused; bool inMission; bool clickPressed; bool escPressed; bool buttonsDown; };`
  - `enum class CaptureAction : uint8_t { None, Capture, Release };`
  - `class Capture { CaptureAction step(const CaptureInputs &in); bool captured() const; bool buttonsLive() const; };`

Rules (spec 3.2 step 3): auto-capture on entering a mission, focused. Release when the mouse is disabled, when leaving the mission, on focus loss, or on Esc. After focus loss or Esc, only a click recaptures, and that click is swallowed until every button is up. Leaving the mission resets the rules, so the next mission auto-captures.

- [ ] **Step 1: Write the failing tests**

Append inside `register_socom2_mouse_tests()`:

```cpp
    MiniTest::Case("Socom2MouseCapture", [](TestCase &tc)
    {
        auto in = [](bool focused, bool inMission, bool click = false, bool esc = false, bool down = false)
        {
            return CaptureInputs{true, focused, inMission, click, esc, down};
        };

        tc.Run("entering a mission focused captures; leaving it releases", [&](TestCase &t)
        {
            Capture c;
            t.Equals(static_cast<int>(c.step(in(true, false))), static_cast<int>(CaptureAction::None), "menus: nothing");
            t.Equals(static_cast<int>(c.step(in(true, true))), static_cast<int>(CaptureAction::Capture), "mission: capture");
            t.IsTrue(c.buttonsLive(), "buttons reach the game");
            t.Equals(static_cast<int>(c.step(in(true, true))), static_cast<int>(CaptureAction::None), "steady");
            t.Equals(static_cast<int>(c.step(in(true, false))), static_cast<int>(CaptureAction::Release), "menus: release");
            t.IsFalse(c.buttonsLive(), "no buttons while released");
        });

        tc.Run("focus loss releases, and only a click recaptures", [&](TestCase &t)
        {
            Capture c;
            c.step(in(true, true));
            t.Equals(static_cast<int>(c.step(in(false, true))), static_cast<int>(CaptureAction::Release), "focus lost");
            t.Equals(static_cast<int>(c.step(in(true, true))), static_cast<int>(CaptureAction::None), "focus back: still released");
            t.Equals(static_cast<int>(c.step(in(true, true, true, false, true))), static_cast<int>(CaptureAction::Capture), "click");
        });

        tc.Run("the recapturing click is swallowed until every button is up", [&](TestCase &t)
        {
            Capture c;
            c.step(in(true, true));
            c.step(in(false, true));
            c.step(in(true, true, true, false, true));
            t.IsTrue(c.captured(), "captured");
            t.IsFalse(c.buttonsLive(), "the click does not fire");
            c.step(in(true, true, false, false, true));
            t.IsFalse(c.buttonsLive(), "still held: still swallowed");
            c.step(in(true, true, false, false, false));
            t.IsTrue(c.buttonsLive(), "released: live again");
        });

        tc.Run("Esc releases; a click recaptures", [&](TestCase &t)
        {
            Capture c;
            c.step(in(true, true));
            t.Equals(static_cast<int>(c.step(in(true, true, false, true))), static_cast<int>(CaptureAction::Release), "esc");
            t.Equals(static_cast<int>(c.step(in(true, true))), static_cast<int>(CaptureAction::None), "stays released");
            t.Equals(static_cast<int>(c.step(in(true, true, true, false, true))), static_cast<int>(CaptureAction::Capture), "click");
        });

        tc.Run("a new mission auto-captures again after an Esc in the last one", [&](TestCase &t)
        {
            Capture c;
            c.step(in(true, true));
            c.step(in(true, true, false, true));   // esc
            c.step(in(true, false));               // back to menus
            t.Equals(static_cast<int>(c.step(in(true, true))), static_cast<int>(CaptureAction::Capture), "next mission");
        });

        tc.Run("disabled never captures and releases a capture", [&](TestCase &t)
        {
            Capture c;
            c.step(in(true, true));
            CaptureInputs off = in(true, true);
            off.enabled = false;
            t.Equals(static_cast<int>(c.step(off)), static_cast<int>(CaptureAction::Release), "release");
            t.Equals(static_cast<int>(c.step(off)), static_cast<int>(CaptureAction::None), "stays off");
        });
    });
```

- [ ] **Step 2: Run to verify it fails**

Run: RUN_CXX. Expected: compile error, `unknown type name 'Capture'`.

- [ ] **Step 3: Write the implementation**

Append to `socom2_mouse_core.h` inside the namespace:

```cpp
    // ---- Cursor capture (spec section 3.2, step 3) ----------------------------------------------------------
    struct CaptureInputs
    {
        bool enabled = false;       // the mouse is on (knob and keyboard scope)
        bool focused = false;       // the game window has focus
        bool inMission = false;     // the player actor is readable (readMode().ok)
        bool clickPressed = false;  // a mouse button went down this frame
        bool escPressed = false;    // Esc went down this frame
        bool buttonsDown = false;   // any mouse button is down now
    };

    enum class CaptureAction : uint8_t { None, Capture, Release };

    class Capture
    {
    public:
        CaptureAction step(const CaptureInputs &in)
        {
            CaptureAction action = CaptureAction::None;
            if (!in.enabled || !in.inMission || !in.focused)
            {
                if (!in.focused && in.inMission)
                    m_userReleased = true;   // focus loss: a click must recapture
                if (!in.inMission)
                    m_userReleased = false;  // a new mission starts fresh
                if (m_captured)
                    action = CaptureAction::Release;
                m_captured = false;
            }
            else if (m_captured && in.escPressed)
            {
                m_userReleased = true;
                m_captured = false;
                action = CaptureAction::Release;
            }
            else if (!m_captured && (in.clickPressed || !m_userReleased))
            {
                m_captured = true;
                m_swallow = in.clickPressed;
                m_userReleased = false;
                action = CaptureAction::Capture;
            }
            if (m_swallow && !in.buttonsDown)
                m_swallow = false;
            return action;
        }
        bool captured() const { return m_captured; }
        bool buttonsLive() const { return m_captured && !m_swallow; }

    private:
        bool m_captured = false;
        bool m_userReleased = false;
        bool m_swallow = false;
    };
```

Check "focus back: still released": after focus loss `m_userReleased = true`; focused again with no click → `!m_captured && (false || false)` → None. Correct. Check "entering a mission focused captures": `m_userReleased` false → Capture with `m_swallow = false`. Correct.

- [ ] **Step 4: Run to verify it passes**

Run: RUN_CXX. Expected: `Socom2MouseCapture` all passed; `Failed: 0`.

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(mouse): cursor capture -- auto in a mission, released on focus loss and Esc, the recapturing click swallowed" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- third_party/ps2recomp/ps2xRuntime/include/runtime/socom2_mouse_core.h third_party/ps2recomp/ps2xTest/src/socom2_mouse_tests.cpp
```

---

### Task 4: Knobs, glue and wiring (look, fire, capture, trace, probe key)

After this task the game has mouse look, left-click fire, capture, the trace, and the probe key. Right click does nothing yet (Task 7).

**Files:**
- Modify: `third_party/ps2recomp/ps2xShared/include/ps2x/knobs.h` (six rows, alphabetical, before `PS2X_MPEG_TRACE`)
- Regenerate: `docs/KNOBS.md`
- Create: `third_party/ps2recomp/ps2xRuntime/src/lib/socom2_mouse.h`
- Create: `third_party/ps2recomp/ps2xRuntime/src/lib/socom2_mouse.cpp`
- Create: `third_party/ps2recomp/ps2xRuntime/src/lib/socom2_mouse_gc_stub.cpp` (every platform until Task 5 replaces it on Apple)
- Modify: `third_party/ps2recomp/ps2xRuntime/src/lib/socom2_host_input.h` (poll signature)
- Modify: `third_party/ps2recomp/ps2xRuntime/src/lib/socom2_host_input.cpp:351` (signature, one call)
- Modify: `third_party/ps2recomp/ps2xRuntime/src/lib/socom2_pad2_hle.cpp:81`
- Modify: `third_party/ps2recomp/ps2xRuntime/src/lib/ps2_runtime.cpp:3081`
- Modify: `third_party/ps2recomp/ps2xRuntime/CMakeLists.txt:528`
- Modify: `third_party/ps2recomp/ps2xTest/CMakeLists.txt:177`
- Modify: `third_party/ps2recomp/ps2xTest/src/socom2_mouse_tests.cpp`

**Interfaces:**
- Consumes: everything in Tasks 1-3.
- Produces (namespace `ps2_stubs`, header `socom2_mouse.h`):
  - `void socom2MouseApply(const uint8_t *rdram, KeyboardScope scope, Socom2PadState &next);` (game thread)
  - `void socom2MouseFrame();` (main thread, once per frame)
  - `void socom2MouseAddRaw(double dx, double dy);` (any thread)
  - `bool socom2MouseGcStart();` (main thread; true when a raw source is attached)
  - `socom2_mouse::Config socom2MouseConfigFrom(const char *(*knob)(const char *));` (pure parse, tested)
- Changes: `void socom2HostInputPoll(Socom2PadState &pad, const uint8_t *rdram = nullptr);`

- [ ] **Step 1: Write the failing tests (config parse and the off switch)**

Append inside `register_socom2_mouse_tests()`, and add `#include "socom2_mouse.h"` and `#include <cstring>` to the test file:

```cpp
    MiniTest::Case("Socom2MouseConfig", [](TestCase &tc)
    {
        tc.Run("unset knobs give the defaults", [](TestCase &t)
        {
            const Config c = ps2_stubs::socom2MouseConfigFrom([](const char *) -> const char * { return nullptr; });
            t.IsTrue(c.enabled, "on by default");
            t.Equals(c.sens, 1.0f, "sens 1");
            t.IsFalse(c.invertY, "not inverted");
            t.Equals(c.deadzone, 0x18, "dead zone 0x18");
            t.IsFalse(c.trace, "no trace");
            t.IsFalse(c.probe, "no probe");
        });

        tc.Run("set knobs are honoured, and nonsense falls back to the default", [](TestCase &t)
        {
            const Config c = ps2_stubs::socom2MouseConfigFrom([](const char *n) -> const char * {
                if (std::strcmp(n, "PS2X_MOUSE") == 0) return "0";
                if (std::strcmp(n, "PS2X_MOUSE_SENS") == 0) return "2.5";
                if (std::strcmp(n, "PS2X_MOUSE_INVERT_Y") == 0) return "1";
                if (std::strcmp(n, "PS2X_MOUSE_DEADZONE") == 0) return "200";   // out of 0..126: default
                if (std::strcmp(n, "PS2X_MOUSE_TRACE") == 0) return "1";
                return nullptr;
            });
            t.IsFalse(c.enabled, "off");
            t.Equals(c.sens, 2.5f, "sens");
            t.IsTrue(c.invertY, "inverted");
            t.Equals(c.deadzone, 0x18, "bad dead zone ignored");
            t.IsTrue(c.trace, "trace");
            const Config bad = ps2_stubs::socom2MouseConfigFrom([](const char *n) -> const char * {
                return std::strcmp(n, "PS2X_MOUSE_SENS") == 0 ? "fast" : nullptr;
            });
            t.Equals(bad.sens, 1.0f, "unparseable sens ignored");
        });

        tc.Run("Menus scope or PS2X_MOUSE=0: the pad state is left byte for byte", [](TestCase &t)
        {
            ps2_stubs::Socom2PadState before;
            before.axis[0] = 0x33; before.button[ps2_stubs::kPadR1] = 0; before.button[ps2_stubs::kPadUp] = 1;
            ps2_stubs::Socom2PadState after = before;
            ps2_stubs::socom2MouseAddRaw(500.0, 500.0);
            ps2_stubs::socom2MouseApply(nullptr, ps2_stubs::KeyboardScope::Menus, after);
            t.IsTrue(std::memcmp(&before, &after, sizeof(before)) == 0, "Menus scope: untouched");
        });
    });
```

`PS2X_MOUSE=0` and `Full` together go through the same early return as `Menus`. The test covers `Menus` because the glue's config is a process static; the `enabled` branch shares that one line.

- [ ] **Step 2: Run to verify it fails**

Run: RUN_CXX. Expected: compile error, `'socom2_mouse.h' file not found`.

- [ ] **Step 3: Add the knob rows**

In `knobs.h`, immediately before the `X("PS2X_MPEG_TRACE", ...` line:

```cpp
    X("PS2X_MOUSE", Dev, Flag, "1", "macOS fork: mouse look (right stick), left click R1, right click aim-hold; 0 = off, byte-identical.") \
    X("PS2X_MOUSE_DEADZONE", Dev, Int, "24", "macOS fork: stick units (0-126) added to any non-zero mouse output, past the game's dead zone.") \
    X("PS2X_MOUSE_INVERT_Y", Dev, Flag, "0", "macOS fork: 1 inverts the mouse's vertical look.") \
    X("PS2X_MOUSE_PROBE", Dev, Presence, "", "macOS fork: the O key queues 50 D-pad UP/DOWN pairs at the aim-hold timing (the ratchet probe).") \
    X("PS2X_MOUSE_SENS", Dev, Float, "1.0", "macOS fork: right-stick units per raw mouse count.") \
    X("PS2X_MOUSE_TRACE", Dev, Presence, "", "macOS fork: [mouse] lines -- deltas, carry, axes, aim-hold state, the view mode -- when any changes.") \
```

- [ ] **Step 4: Write the glue header**

`third_party/ps2recomp/ps2xRuntime/src/lib/socom2_mouse.h`:

```cpp
#pragma once
// Mouse look and right-click aim-hold -- the macOS fork's glue (spec docs/superpowers/specs/2026-10-03-mouse-look-design.md).
// The pure core is runtime/socom2_mouse_core.h. Threads: socom2MouseApply on the game thread (scePad2Read),
// socom2MouseFrame on the main thread, socom2MouseAddRaw from any thread. Shared state is atomics only.
#include "runtime/socom2_mouse_core.h"
#include "socom2_host_input.h"

#include <cstdint>

namespace ps2_stubs
{
    socom2_mouse::Config socom2MouseConfigFrom(const char *(*knob)(const char *));
    void socom2MouseApply(const uint8_t *rdram, KeyboardScope scope, Socom2PadState &next);
    void socom2MouseFrame();
    void socom2MouseAddRaw(double dx, double dy);
    bool socom2MouseGcStart();   // socom2_mouse_gc.mm on Apple; socom2_mouse_gc_stub.cpp elsewhere
}
```

- [ ] **Step 5: Write the glue**

`third_party/ps2recomp/ps2xRuntime/src/lib/socom2_mouse.cpp`:

```cpp
// Mouse look and right-click aim-hold -- the macOS fork's glue. See socom2_mouse.h.
#include "socom2_mouse.h"

#include "ps2x/knobs.h"
#include "runtime/socom2_addresses.h"
#include "raylib.h"

#include <atomic>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <iostream>

namespace ps2_stubs
{
    namespace
    {
        using namespace socom2_mouse;

        // Main thread -> game thread.
        std::atomic<bool> g_captured{false};
        std::atomic<bool> g_left{false};        // left button, already gated by Capture::buttonsLive
        std::atomic<bool> g_right{false};       // right button, likewise
        std::atomic<bool> g_resetLook{false};   // a release cleared the motion; the game thread drops its carry
        std::atomic<bool> g_probeKey{false};    // O pressed with PS2X_MOUSE_PROBE
        // Game thread -> main thread.
        std::atomic<bool> g_inMission{false};
        std::atomic<bool> g_active{false};      // enabled and Full scope, as of the last pad read

        Accumulator g_acc;
        std::atomic<bool> g_rawSource{false};   // GCMouse delivered at least one event

        const Config &config()
        {
            static const Config cfg = socom2MouseConfigFrom(ps2x::knob);
            return cfg;
        }

        // Game thread only.
        LookState g_look;
        PulseQueue g_probeQueue;
        uint8_t g_lastMode = 0xFF;
    }

    socom2_mouse::Config socom2MouseConfigFrom(const char *(*knob)(const char *))
    {
        Config c;
        auto flag = [&](const char *name, bool dflt) {
            const char *v = knob(name);
            return ps2x::knobs::flagValue(v, dflt);
        };
        c.enabled = flag("PS2X_MOUSE", true);
        c.invertY = flag("PS2X_MOUSE_INVERT_Y", false);
        if (const char *v = knob("PS2X_MOUSE_SENS"))
        {
            char *end = nullptr;
            const float f = std::strtof(v, &end);
            if (end != v && *end == '\0' && f > 0.0f && f < 1000.0f)
                c.sens = f;
        }
        if (const char *v = knob("PS2X_MOUSE_DEADZONE"))
        {
            char *end = nullptr;
            const long n = std::strtol(v, &end, 0);
            if (end != v && *end == '\0' && n >= 0 && n < kStickSpan)
                c.deadzone = static_cast<int>(n);
        }
        c.trace = knob("PS2X_MOUSE_TRACE") != nullptr;
        c.probe = knob("PS2X_MOUSE_PROBE") != nullptr;
        return c;
    }

    void socom2MouseAddRaw(double dx, double dy)
    {
        g_rawSource.store(true, std::memory_order_relaxed);
        if (g_captured.load(std::memory_order_relaxed))
            g_acc.add(dx, dy);
    }

    void socom2MouseApply(const uint8_t *rdram, KeyboardScope scope, Socom2PadState &next)
    {
        const Config &cfg = config();
        const bool active = cfg.enabled && scope == KeyboardScope::Full;
        g_active.store(active, std::memory_order_relaxed);
        if (!active)
            return;

        const ModeRead mode = readMode(rdram, revisionFor(socom2_addresses::current().revision));
        g_inMission.store(mode.ok, std::memory_order_relaxed);

        if (g_resetLook.exchange(false, std::memory_order_relaxed))
            g_look = LookState{};
        double dx = 0.0, dy = 0.0;
        g_acc.drain(dx, dy);
        const LookOut look = socom2_mouse::look(cfg, dx, dy, g_look);
        if (look.moved)
        {
            next.axis[0] = look.rx;
            next.axis[1] = look.ry;
        }
        if (g_left.load(std::memory_order_relaxed))
            next.button[kPadR1] = 1u;

        if (cfg.probe && g_probeKey.exchange(false, std::memory_order_relaxed))
        {
            for (int i = 0; i < 50; ++i)
            {
                g_probeQueue.push(Pulse::Up);
                g_probeQueue.push(Pulse::Down);
            }
            std::cout << "[mouse] probe: 50 UP/DOWN pairs queued, mode " << (mode.ok ? int(mode.mode) : -1) << std::endl;
        }
        const Pulse probe = g_probeQueue.tick();
        if (probe == Pulse::Up)
            next.button[kPadUp] = 1u;
        else if (probe == Pulse::Down)
            next.button[kPadDown] = 1u;

        if (cfg.trace)
        {
            const uint8_t m = mode.ok ? mode.mode : 0xFFu;
            if (look.moved || m != g_lastMode || probe != Pulse::None || next.button[kPadUp] || next.button[kPadDown])
                std::cout << "[mouse] dx=" << dx << " dy=" << dy << " carry=" << g_look.carryX << "," << g_look.carryY
                          << " rx=" << int(next.axis[0]) << " ry=" << int(next.axis[1])
                          << " up=" << int(next.button[kPadUp]) << " down=" << int(next.button[kPadDown])
                          << " mode=" << (mode.ok ? int(mode.mode) : -1) << " actor=0x" << std::hex << mode.actor
                          << std::dec << std::endl;
            g_lastMode = m;
        }
    }

    void socom2MouseFrame()
    {
        static Capture capture;
        static bool started = false;
        static std::chrono::steady_clock::time_point startedAt;
        static bool fallbackLogged = false;
        if (!started)
        {
            started = true;
            startedAt = std::chrono::steady_clock::now();
            socom2MouseGcStart();
        }

        const bool left = IsMouseButtonDown(MOUSE_BUTTON_LEFT);
        const bool right = IsMouseButtonDown(MOUSE_BUTTON_RIGHT);
        CaptureInputs in;
        in.enabled = g_active.load(std::memory_order_relaxed);
        in.focused = IsWindowFocused();
        in.inMission = g_inMission.load(std::memory_order_relaxed);
        in.clickPressed = IsMouseButtonPressed(MOUSE_BUTTON_LEFT) || IsMouseButtonPressed(MOUSE_BUTTON_RIGHT);
        in.escPressed = IsKeyPressed(KEY_ESCAPE);
        in.buttonsDown = left || right;
        switch (capture.step(in))
        {
        case CaptureAction::Capture:
            DisableCursor();
            break;
        case CaptureAction::Release:
            EnableCursor();
            g_acc.clear();
            g_resetLook.store(true, std::memory_order_relaxed);
            break;
        case CaptureAction::None:
            break;
        }
        g_captured.store(capture.captured(), std::memory_order_relaxed);
        g_left.store(capture.buttonsLive() && left, std::memory_order_relaxed);
        g_right.store(capture.buttonsLive() && right, std::memory_order_relaxed);
        if (config().probe && IsKeyPressed(KEY_O))
            g_probeKey.store(true, std::memory_order_relaxed);

        // No GCMouse events 2 s after start: raylib's (accelerated) deltas instead, once said.
        if (!g_rawSource.load(std::memory_order_relaxed) &&
            std::chrono::steady_clock::now() - startedAt > std::chrono::seconds(2))
        {
            if (!fallbackLogged)
            {
                fallbackLogged = true;
                std::cout << "[mouse] raw deltas unavailable, using GetMouseDelta" << std::endl;
            }
            if (capture.captured())
            {
                const Vector2 d = GetMouseDelta();
                g_acc.add(d.x, d.y);
            }
        }
    }
}
```

`socom2_addresses::current()` is never null: it is the r0001 column until the image selects another (`socom2_addresses.h:320-350`), the same table every other SOCOM II override reads.

The fallback has a known edge: until the first GCMouse event, both paths could feed. In practice GCMouse either never arrives (fallback only) or arrives on the first motion (before 2 s of play in a mission). Accept it; the Task 6 probe log shows which path ran.

`third_party/ps2recomp/ps2xRuntime/src/lib/socom2_mouse_gc_stub.cpp`:

```cpp
// Non-Apple builds: no GCMouse. socom2MouseFrame falls back to raylib's GetMouseDelta after 2 s.
#include "socom2_mouse.h"

namespace ps2_stubs
{
    bool socom2MouseGcStart() { return false; }
}
```

- [ ] **Step 6: Wire it in**

`socom2_host_input.h`: change the poll's declaration to

```cpp
    // Refresh `pad` from the host. Safe to call before the window exists (does nothing then). `rdram` is the
    // guest's RAM (scePad2Read passes it) for the mouse's view-mode read; nullptr reads nothing.
    void socom2HostInputPoll(Socom2PadState &pad, const uint8_t *rdram = nullptr);
```

`socom2_host_input.cpp`: add `#include "socom2_mouse.h"` with the other includes; change the definition at line 351 to `void socom2HostInputPoll(Socom2PadState &pad, const uint8_t *rdram)`. Immediately after the line `socom2ApplyKeyboard(g_config.mapping, g_config.keyboardScope, IsKeyDown, next);` add

```cpp
        socom2MouseApply(rdram, g_config.keyboardScope, next);   // macOS fork: the mouse (socom2_mouse.h)
```

`socom2_pad2_hle.cpp:81`: `socom2HostInputPoll(g_socom2Pad, rdram);` (the function's first parameter is already named `rdram`).

`ps2_runtime.cpp`: add `#include "socom2_mouse.h"` after line 8's `#include "socom2_host_input.h"`; immediately before `BeginDrawing();` at line 3081 add

```cpp
        ps2_stubs::socom2MouseFrame();   // macOS fork: cursor capture and the mouse buttons (socom2_mouse.h)
```

`ps2xRuntime/CMakeLists.txt`, after line 528 (`target_sources(ps2EntryRunner PRIVATE src/lib/socom2_host_input.cpp)`):

```cmake
target_sources(ps2EntryRunner PRIVATE src/lib/socom2_mouse.cpp src/lib/socom2_mouse_gc_stub.cpp)   # macOS fork: the mouse
```

`ps2xTest/CMakeLists.txt`, inside the `target_sources(ps2x_tests PRIVATE ...socom2_host_input.cpp)` block at line 177, add

```cmake
    ${CMAKE_SOURCE_DIR}/ps2xRuntime/src/lib/socom2_mouse.cpp
    ${CMAKE_SOURCE_DIR}/ps2xRuntime/src/lib/socom2_mouse_gc_stub.cpp
```

- [ ] **Step 7: Regenerate KNOBS.md and run every affected suite**

Run: `.venv/bin/python -m tools_py.knobs write`, then RUN_PY_KNOBS, then RUN_CXX.
Expected: Python OK, with the six new rows read by `socom2_mouse.cpp`. C++: `Socom2MouseConfig` passes, `Knobs` passes, `Failed: 0`.

If `test_knob_read_sites` or `test_knobs_registry` complains that a knob is read through a variable rather than a literal (`ps2x::knob` is passed as a function pointer to `socom2MouseConfigFrom`), the registry's scanner needs literal reads. In that case add, at the top of `socom2MouseConfigFrom`, a comment naming all six literals. If the scanner wants literals at call sites, keep the six `knob("PS2X_MOUSE...")` calls exactly as written above; they are literals already. Read the failure text before changing anything.

- [ ] **Step 8: Build the game and smoke-test**

Run BUILD_GAME. Expected: `built dist-macos: ... socom2 ...`.
Smoke run (Claude launches; the owner plays): `caffeinate -u -t 5; PS2X_MOUSE_TRACE=1 bash logs/playtest.sh` in the background. The owner reaches a mission and moves the mouse. Check `grep -m5 '\[mouse\]' logs/playtest.log` shows `mode=` values that are not -1 in the mission, and `rx=` changing with motion. The fallback line is expected until Task 5.

- [ ] **Step 9: Commit**

```bash
git commit -m "feat(mouse): mouse look, left-click fire and capture wired into the pad poll and the frame loop; six Dev knobs" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- \
  third_party/ps2recomp/ps2xShared/include/ps2x/knobs.h docs/KNOBS.md \
  third_party/ps2recomp/ps2xRuntime/src/lib/socom2_mouse.h third_party/ps2recomp/ps2xRuntime/src/lib/socom2_mouse.cpp \
  third_party/ps2recomp/ps2xRuntime/src/lib/socom2_mouse_gc_stub.cpp \
  third_party/ps2recomp/ps2xRuntime/src/lib/socom2_host_input.h third_party/ps2recomp/ps2xRuntime/src/lib/socom2_host_input.cpp \
  third_party/ps2recomp/ps2xRuntime/src/lib/socom2_pad2_hle.cpp third_party/ps2recomp/ps2xRuntime/src/lib/ps2_runtime.cpp \
  third_party/ps2recomp/ps2xRuntime/CMakeLists.txt third_party/ps2recomp/ps2xTest/CMakeLists.txt \
  third_party/ps2recomp/ps2xTest/src/socom2_mouse_tests.cpp
```

---

### Task 5: Raw deltas from GCMouse (macOS)

**Files:**
- Create: `third_party/ps2recomp/ps2xRuntime/src/lib/socom2_mouse_gc.mm`
- Modify: `third_party/ps2recomp/ps2xRuntime/CMakeLists.txt` (the line added in Task 4)
- Modify: `third_party/ps2recomp/ps2xTest/CMakeLists.txt` (the two lines added in Task 4)

**Interfaces:**
- Consumes: `ps2_stubs::socom2MouseAddRaw(double, double)`.
- Produces: `ps2_stubs::socom2MouseGcStart()` on Apple.

There's no unit test: this is the OS boundary, and the core it feeds is tested. Verification is the log line, plus motion in game with the fallback line absent.

- [ ] **Step 1: Write the source**

`third_party/ps2recomp/ps2xRuntime/src/lib/socom2_mouse_gc.mm`:

```objc
// macOS fork: raw, unaccelerated mouse deltas from the GameController framework (macOS 11+). GLFW cannot give
// raw motion on Cocoa (its deltas are NSEvent's, after acceleration), so the mouse module reads GCMouse here
// and raylib only hides and locks the cursor.
#include "socom2_mouse.h"

#import <Foundation/Foundation.h>
#import <GameController/GameController.h>

#include <iostream>

namespace
{
    void attach(GCMouse *mouse)
    {
        if (mouse == nil || mouse.mouseInput == nil)
            return;
        // GCMouse reports +y up; the stick's +y is down (RY 0xFF = look down). Negate y so the mouse matches the
        // pad: mouse forward looks up.
        mouse.mouseInput.mouseMovedHandler = ^(GCMouseInput *, float deltaX, float deltaY) {
            ps2_stubs::socom2MouseAddRaw(static_cast<double>(deltaX), -static_cast<double>(deltaY));
        };
        std::cout << "[mouse] raw deltas: GCMouse \"" << (mouse.vendorName ? mouse.vendorName.UTF8String : "mouse")
                  << "\"" << std::endl;
    }
}

namespace ps2_stubs
{
    bool socom2MouseGcStart()
    {
        if (@available(macOS 11.0, *))
        {
            for (GCMouse *mouse in GCMouse.mice)
                attach(mouse);
            [[NSNotificationCenter defaultCenter] addObserverForName:GCMouseDidConnectNotification
                                                              object:nil
                                                               queue:nil
                                                          usingBlock:^(NSNotification *note) { attach(note.object); }];
            return true;
        }
        return false;
    }
}
```

The sign of Y is checked in Step 3. If mouse-forward looks down, drop the negation and say so in the commit.

- [ ] **Step 2: CMake**

`ps2xRuntime/CMakeLists.txt`: replace the Task 4 line with

```cmake
if(APPLE)
    enable_language(OBJCXX)
    target_sources(ps2EntryRunner PRIVATE src/lib/socom2_mouse.cpp src/lib/socom2_mouse_gc.mm)   # macOS fork: the mouse
    target_link_libraries(ps2EntryRunner PRIVATE "-framework GameController" "-framework Foundation")
else()
    target_sources(ps2EntryRunner PRIVATE src/lib/socom2_mouse.cpp src/lib/socom2_mouse_gc_stub.cpp)
endif()
```

`ps2xTest/CMakeLists.txt`: keep `socom2_mouse_gc_stub.cpp` in `ps2x_tests` on every platform. The tests never start GCMouse, and the stub avoids linking frameworks into the test binary.

`enable_language(OBJCXX)` must run at directory scope before the target uses a `.mm`. If CMake complains, move it next to the `project()` call in `third_party/ps2recomp/CMakeLists.txt` inside `if(APPLE)`. If the unity build pulls the `.mm` in, set `set_source_files_properties(src/lib/socom2_mouse_gc.mm PROPERTIES SKIP_UNITY_BUILD_INCLUSION TRUE)`.

- [ ] **Step 3: Build and verify in game**

Run BUILD_GAME, then RUN_CXX (it must still pass). Launch as in Task 4 Step 8.
Expected in `logs/playtest.log`: `[mouse] raw deltas: GCMouse "..."`, and **no** `raw deltas unavailable` line. In a mission, moving the mouse turns the view. The owner confirms that the vertical direction matches the pad (mouse forward = look up), and that a slow drag and a fast flick of the same distance turn about the same amount. Before linearisation, a fast flick may turn somewhat more, because the game's stick curve is not linear yet.

- [ ] **Step 4: Commit**

```bash
git commit -m "feat(mouse): raw unaccelerated deltas from GCMouse on macOS; GLFW's are NSEvent's, after acceleration" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- third_party/ps2recomp/ps2xRuntime/src/lib/socom2_mouse_gc.mm third_party/ps2recomp/ps2xRuntime/CMakeLists.txt third_party/ps2recomp/ps2xTest/CMakeLists.txt
```

---

### Task 6: The aim probe (in game; decides Task 7)

**Files:**
- Create: `docs/research/86-mouse-aim-probe.md` (check `ls docs/research | tail -3` first and take the next free number if 70 is used)

The owner plays and Claude reads the trace. Launch: `caffeinate -u -t 5; PS2X_MOUSE_TRACE=1 PS2X_MOUSE_PROBE=1 PS2X_HOST_SCREENSHOT=logs/probe_shots:1 bash logs/playtest.sh` (background), then filter with `grep '\[mouse\]' logs/playtest.log`. The arrow keys are the D-pad and work in every scope.

- [ ] **Step 1: Run the cases.** For each case, the owner says when they start it and Claude notes the log line range. The mode sequence comes from the `mode=` field.
  1. Third person (mode 0) with the default rifle: Up, then Down. Repeat with a scoped weapon (from the armory, or a mission's default sniper rifle).
  2. The same from first person.
  3. Up repeatedly past the last zoom level: does the mode stop or wrap?
  4. Down at mode 0: does it stop or wrap?
  5. While zoomed, swap weapons: what does the mode become?
  6. While zoomed, die and respawn: does `actor` change, and what is the mode after?
  7. While zoomed, press Esc (pause), wait, unpause: does the mode change, and does an arrow press during pause move the menu?
  8. While zoomed, press the arrow Up/Down: the mode follows the presses (baseline for the takeover rule).
  9. Stand still at mode 0, press **O**: 50 UP/DOWN pairs run at the aim-hold timing (about 7 s). Read the final mode and count the UP/DOWN pulses that did not change the mode.

- [ ] **Step 2: Write the findings** into `docs/research/86-mouse-aim-probe.md`, one section per case: the mode sequence, the screenshot names, and a one-line conclusion. End with:
  - **Verdict:** PASS or FAIL against the spec's 4.4 criterion. "Every case returns or aborts by rule, no press reaches the pause menu, case 9 ends where it started."
  - **Match rule:** exact mode, or modes 1-3 as one class (from cases 1-2: does Down from a zoom level ever land on the stored first-person mode?).
  - **Drop rate:** case 9's unanswered pulses / 100.
  - **Dead-zone note:** in case 1, did the 0x18 default move the view on the smallest motion (owner's impression)?

- [ ] **Step 3: Commit**

```bash
git commit -m "docs(research): the aim probe -- the view mode under D-pad pulses, at the ends, across swap, death and pause" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- docs/research/86-mouse-aim-probe.md
```

- [ ] **Step 4: Decide.** PASS: do Task 7. FAIL: do Task 7-FALLBACK instead, and add the direct mode write ("C") to Spike B's brief in Task 10. Tell the owner which one and why, in one line.

---

### Task 7: Right-click aim-hold, closed loop

**Files:**
- Modify: `third_party/ps2recomp/ps2xRuntime/include/runtime/socom2_mouse_core.h`
- Modify: `third_party/ps2recomp/ps2xRuntime/src/lib/socom2_mouse.cpp`
- Modify: `third_party/ps2recomp/ps2xTest/src/socom2_mouse_tests.cpp`

**Interfaces:**
- Consumes: `ModeRead`, `Pulse`, `PulseQueue`, `kPulseHeldReads`, `kPulseGapReads` (Task 2).
- Produces:
  - `bool modesMatch(uint8_t now, uint8_t stored);`
  - `struct AimInputs { bool right; ModeRead mode; bool start; bool kbZoom; };`
  - `enum class AimState : uint8_t { Idle, Holding, Restoring };`
  - `class AimHold { Pulse tick(const AimInputs &in); AimState state() const; const char *lastEvent() const; };`
  - `constexpr int kRestoreCap = 4, kAnswerReads = 6;`

- [ ] **Step 1: Write the failing tests, with a model of the game's cycler**

Append inside `register_socom2_mouse_tests()`:

```cpp
    MiniTest::Case("Socom2MouseAimHold", [](TestCase &tc)
    {
        // The game's side, as research/30 describes it: a press edge (seen up, then down) on UP zooms in one mode,
        // on DOWN out one. Configurable ends, dropped edges and a game that ignores input (paused).
        struct Cycler
        {
            uint8_t mode = 0;
            uint8_t top = 6;          // highest mode
            bool wrapTop = false, wrapBottom = false;
            int dropEvery = 0;        // drop every Nth edge (0 = none)
            bool responsive = true;
            uint32_t actor = 0x00D00000u;
            bool live = true;
            bool prevUp = false, prevDown = false;
            int edges = 0;
            ModeRead read() const { ModeRead m; m.ok = live; m.actor = actor; m.mode = mode; return m; }
            void see(bool up, bool down)
            {
                const bool upEdge = up && !prevUp, downEdge = down && !prevDown;
                prevUp = up; prevDown = down;
                if (!responsive || (!upEdge && !downEdge)) return;
                if (dropEvery && (++edges % dropEvery) == 0) return;
                if (upEdge) mode = mode < top ? mode + 1 : (wrapTop ? 0 : top);
                if (downEdge) mode = mode > 0 ? mode - 1 : (wrapBottom ? top : 0);
            }
        };

        // One pad read: the game reads what we sent last read, then we decide this read.
        struct Rig
        {
            Cycler game;
            AimHold aim;
            int ups = 0, downs = 0;
            void read(bool right, bool start = false, bool kbZoom = false)
            {
                const Pulse p = aim.tick(AimInputs{right, game.read(), start, kbZoom});
                if (p == Pulse::Up) ++ups;
                if (p == Pulse::Down) ++downs;
                game.see(p == Pulse::Up, p == Pulse::Down);
            }
            void reads(int n, bool right) { for (int i = 0; i < n; ++i) read(right); }
        };

        tc.Run("hold zooms in one mode, release returns to the stored mode", [](TestCase &t)
        {
            Rig r;
            r.reads(10, true);
            t.Equals(int(r.game.mode), 1, "one UP: mode 1");
            t.Equals(int(r.aim.state()), int(AimState::Holding), "holding");
            r.reads(20, false);
            t.Equals(int(r.game.mode), 0, "back to 0");
            t.Equals(int(r.aim.state()), int(AimState::Idle), "idle");
            t.Equals(r.ups, 2, "UP held two reads");
            t.Equals(r.downs, 2, "DOWN held two reads");
        });

        tc.Run("a dropped restore press is re-sent once and the view still returns", [](TestCase &t)
        {
            Rig r;
            r.game.mode = 2;
            r.game.dropEvery = 2;   // the UP lands, the first DOWN is dropped
            r.reads(10, true);
            t.Equals(int(r.game.mode), 3, "zoomed");
            r.reads(40, false);
            t.Equals(int(r.game.mode), 2, "restored by the re-send");
        });

        tc.Run("two unanswered presses in a row abort", [](TestCase &t)
        {
            Rig r;
            r.reads(10, true);
            r.game.responsive = false;
            r.reads(60, false);
            t.Equals(int(r.aim.state()), int(AimState::Idle), "gave up");
            t.Equals(std::string(r.aim.lastEvent()), std::string("unanswered"), "said why");
            t.Equals(r.downs, 4, "two DOWN pulses, two reads each, and no more");
        });

        tc.Run("pause aborts and sends nothing more", [](TestCase &t)
        {
            Rig r;
            r.reads(10, true);
            r.read(true, true);   // START while holding
            const int before = r.ups + r.downs;
            r.reads(40, false);
            t.Equals(r.ups + r.downs, before, "no press after START");
            t.Equals(std::string(r.aim.lastEvent()), std::string("pause"), "said why");
        });

        tc.Run("START during the restore stops it at once", [](TestCase &t)
        {
            Rig r;
            r.game.mode = 0;
            r.reads(10, true);
            r.read(false);         // release: restore begins
            r.read(false, true);   // START
            const int before = r.downs;
            r.reads(40, false);
            t.Equals(r.downs, before, "no press after START");
        });

        tc.Run("actor change aborts (death, respawn)", [](TestCase &t)
        {
            Rig r;
            r.reads(10, true);
            r.game.actor = 0x00E00000u;
            r.game.mode = 0;
            r.reads(30, false);
            t.Equals(r.downs, 0, "nothing sent to the new actor");
            t.Equals(std::string(r.aim.lastEvent()), std::string("actor"), "said why");
        });

        tc.Run("unreadable mode means right click does nothing", [](TestCase &t)
        {
            Rig r;
            r.game.live = false;
            r.reads(10, true);
            r.reads(10, false);
            t.Equals(r.ups + r.downs, 0, "no presses in menus");
            t.Equals(int(r.aim.state()), int(AimState::Idle), "idle");
        });

        tc.Run("keyboard zoom while holding hands the zoom to the player: no restore", [](TestCase &t)
        {
            Rig r;
            r.reads(10, true);
            r.read(true, false, true);
            r.reads(30, false);
            t.Equals(r.downs, 0, "no restore");
            t.Equals(std::string(r.aim.lastEvent()), std::string("takeover"), "said why");
        });

        tc.Run("the restore stops at the cap", [](TestCase &t)
        {
            Rig r;
            r.game.mode = 0;
            r.reads(10, true);
            r.game.mode = 6;   // something (a weapon swap) moved the view far away
            r.reads(80, false);
            t.Equals(r.downs, 2 * kRestoreCap, "four DOWN pulses, no more");
            t.Equals(int(r.game.mode), 2, "6 - 4");
            t.Equals(std::string(r.aim.lastEvent()), std::string("cap"), "said why");
        });

        tc.Run("a re-press during the restore keeps the stored mode", [](TestCase &t)
        {
            Rig r;
            r.game.mode = 0;
            r.reads(10, true);     // mode 1
            r.read(false);         // restore starts
            r.reads(3, true);      // clicked again before the DOWN landed
            r.reads(10, true);
            r.reads(40, false);
            t.Equals(int(r.game.mode), 0, "back to the first hold's mode");
        });

        tc.Run("down at the bottom wrapping does not loop forever", [](TestCase &t)
        {
            Rig r;
            r.game.mode = 0; r.game.wrapBottom = true; r.game.top = 6;
            r.reads(10, true);
            r.reads(100, false);
            t.Equals(int(r.game.mode), 0, "returns to 0 in one DOWN");
            t.IsTrue(r.downs <= 2 * kRestoreCap, "bounded");
        });

        tc.Run("fifty hold-release cycles end where they started (the ratchet)", [](TestCase &t)
        {
            Rig r;
            r.game.mode = 0;
            r.game.dropEvery = 20;   // the measured 1-in-20
            for (int i = 0; i < 50; ++i) { r.reads(10, true); r.reads(30, false); }
            t.Equals(int(r.game.mode), 0, "no drift");
        });
    });
```

- [ ] **Step 2: Run to verify it fails**

Run: RUN_CXX. Expected: compile error, `unknown type name 'AimHold'`.

- [ ] **Step 3: Write the implementation**

Append to `socom2_mouse_core.h` inside the namespace. Set `modesMatch` per Task 6's match rule: as written it's exact. If the probe said "class", replace its body with `auto cls = [](uint8_t m) { return (m >= 1 && m <= 3) ? uint8_t(1) : m; }; return cls(now) == cls(stored);` and add a test `modes 1-3 match each other` with `t.IsTrue(modesMatch(3, 1), ...)` and `t.IsFalse(modesMatch(4, 1), ...)`.

```cpp
    // ---- Right-click aim-hold, closed loop (spec section 4.3) -----------------------------------------------
    constexpr int kRestoreCap = 4;    // restore presses at most
    constexpr int kAnswerReads = 6;   // reads after a pulse ends for the mode to move

    // Task 6's match rule (docs/research/86-mouse-aim-probe.md).
    inline bool modesMatch(uint8_t now, uint8_t stored) { return now == stored; }

    struct AimInputs
    {
        bool right = false;   // right button down (already gated by capture)
        ModeRead mode;        // this read's view mode
        bool start = false;   // START pressed by the keyboard this read
        bool kbZoom = false;  // the keyboard's D-pad UP or DOWN down this read
    };

    enum class AimState : uint8_t { Idle, Holding, Restoring };

    class AimHold
    {
    public:
        Pulse tick(const AimInputs &in)
        {
            // Edge first, before any early return: a hold that aborted (pause) must not re-arm on the same
            // still-held button the moment START is let go.
            const bool pressed = in.right && !m_rightWas;
            m_rightWas = in.right;
            if (m_state != AimState::Idle)
            {
                if (in.start)
                    return abort("pause");
                if (!in.mode.ok || in.mode.actor != m_actor)
                    return abort("actor");
                if (in.kbZoom)
                    return abort("takeover");
            }
            switch (m_state)
            {
            case AimState::Idle:
                if (pressed && in.mode.ok)
                {
                    m_stored = in.mode.mode;
                    m_actor = in.mode.actor;
                    m_queue.push(Pulse::Up);
                    m_state = AimState::Holding;
                    m_event = "hold";
                }
                break;
            case AimState::Holding:
                if (!in.right)
                    beginRestore();
                break;
            case AimState::Restoring:
                if (pressed)
                {
                    m_queue.clear();
                    m_queue.push(Pulse::Up);   // the stored mode is kept: the view never got back
                    m_state = AimState::Holding;
                    m_event = "rehold";
                    break;
                }
                restoreStep(in.mode.mode);
                break;
            }
            return m_queue.tick();
        }
        AimState state() const { return m_state; }
        const char *lastEvent() const { return m_event; }

    private:
        void beginRestore()
        {
            m_state = AimState::Restoring;
            m_sent = 0;
            m_unanswered = 0;
            m_waiting = false;
            m_event = "release";
        }
        void restoreStep(uint8_t mode)
        {
            if (!m_queue.idle())
                return;   // the pulse in flight finishes first
            if (m_waiting)
            {
                if (mode != m_modeAtSend)
                {
                    m_waiting = false;
                    m_unanswered = 0;
                }
                else if (++m_waitReads < kAnswerReads)
                    return;
                else
                {
                    m_waiting = false;
                    if (++m_unanswered >= 2)
                    {
                        idle("unanswered");
                        return;
                    }
                    send(m_lastPulse, mode);   // re-send once: an edge can be dropped (HAZARDS, 1 in 20)
                    return;
                }
            }
            if (modesMatch(mode, m_stored))
            {
                idle("restored");
                return;
            }
            send(mode > m_stored ? Pulse::Down : Pulse::Up, mode);
        }
        void send(Pulse p, uint8_t mode)
        {
            if (m_sent >= kRestoreCap)
            {
                idle("cap");
                return;
            }
            ++m_sent;
            m_lastPulse = p;
            m_modeAtSend = mode;
            m_waiting = true;
            m_waitReads = 0;
            m_queue.push(p);
        }
        void idle(const char *why)
        {
            m_queue.clear();
            m_state = AimState::Idle;
            m_event = why;
        }
        Pulse abort(const char *why)
        {
            idle(why);
            return Pulse::None;
        }

        AimState m_state = AimState::Idle;
        PulseQueue m_queue;
        uint8_t m_stored = 0;
        uint32_t m_actor = 0;
        bool m_rightWas = false;
        int m_sent = 0;
        int m_unanswered = 0;
        bool m_waiting = false;
        int m_waitReads = 0;
        uint8_t m_modeAtSend = 0;
        Pulse m_lastPulse = Pulse::None;
        const char *m_event = "idle";
    };
```

Points to check against the tests while making them pass:
- A re-press during the restore, before its first DOWN is sent, queues an UP from the zoomed mode (one level further in); the release then walks back to the stored mode. That is the spec's "one UP is queued as for a fresh hold"; the `re-press` test checks the final mode, not the path.
- The `waitReads` counter is advanced only while the queue is idle, so `kAnswerReads` counts reads after the pulse's gap. That's what the `unanswered` test's `downs == 4` relies on.
- "two unanswered presses in a row abort": the first DOWN is unanswered, so it's re-sent; the re-send is unanswered too, so it aborts. That makes 2 pulses × 2 held reads = 4. Matches.

- [ ] **Step 4: Run to verify it passes**

Run: RUN_CXX. Expected: `Socom2MouseAimHold` all passed; `Failed: 0`. If a timing test misses by one read, fix the state machine, not the test. The tests encode the spec's timing.

- [ ] **Step 5: Wire it into the glue**

In `socom2_mouse.cpp`, add `AimHold g_aim;` to the game-thread globals. In `socom2MouseApply`, after the left-button line, add:

```cpp
        // Right click: aim-hold (spec 4.3). START, and the keyboard's own zoom, are read from `next` as the
        // keyboard left it -- this runs before the pad is OR-ed in.
        const bool kbZoom = next.button[kPadUp] != 0 || next.button[kPadDown] != 0;
        const Pulse aim = g_aim.tick(AimInputs{g_right.load(std::memory_order_relaxed), mode, next.button[kPadStart] != 0, kbZoom});
        if (aim == Pulse::Up)
            next.button[kPadUp] = 1u;
        else if (aim == Pulse::Down)
            next.button[kPadDown] = 1u;
```

`next.button[kPadStart]` is a level, not an edge. While Esc is held, aim-hold stays idle, which is correct. In the trace line add ` aim=" << int(g_aim.state()) << " ev=" << g_aim.lastEvent()`, and add `aim != Pulse::None` to the trace's when-condition. This block sits above the probe block, so `kbZoom` sees only the keyboard and the probe's own pulses never read as a takeover.

- [ ] **Step 6: Build and verify in game**

Run BUILD_GAME and RUN_CXX. The owner plays with `PS2X_MOUSE_TRACE=1` and repeats Task 6's cases 1, 5, 6 and 7 with the right button instead of the arrows. Expected: each `ev=` ends `restored`, or `actor` / `pause` as the case dictates, and nothing moves in the pause menu.

- [ ] **Step 7: Commit**

```bash
git commit -m "feat(mouse): right-click aim-hold -- one UP on press, a closed-loop return to the stored view mode on release" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>" -- third_party/ps2recomp/ps2xRuntime/include/runtime/socom2_mouse_core.h third_party/ps2recomp/ps2xRuntime/src/lib/socom2_mouse.cpp third_party/ps2recomp/ps2xTest/src/socom2_mouse_tests.cpp
```

### Task 7-FALLBACK (only if Task 6 failed): right click = one zoom step

**Files:** the same three as Task 7.

- [ ] **Step 1: Test** (append to the tests):

```cpp
    MiniTest::Case("Socom2MouseZoomStep", [](TestCase &tc)
    {
        tc.Run("each right click sends exactly one UP pulse; holding sends no more", [](TestCase &t)
        {
            ZoomStep z;
            int ups = 0;
            for (int i = 0; i < 20; ++i) if (z.tick(true) == Pulse::Up) ++ups;
            for (int i = 0; i < 5; ++i) z.tick(false);
            for (int i = 0; i < 20; ++i) if (z.tick(true) == Pulse::Up) ++ups;
            t.Equals(ups, 4, "two clicks, two reads each");
        });
    });
```

- [ ] **Step 2: Run, see it fail** (`unknown type name 'ZoomStep'`).
- [ ] **Step 3: Implement** in the core:

```cpp
    class ZoomStep
    {
    public:
        Pulse tick(bool right)
        {
            if (right && !m_was)
                m_queue.push(Pulse::Up);
            m_was = right;
            return m_queue.tick();
        }
    private:
        PulseQueue m_queue;
        bool m_was = false;
    };
```

In the glue: `ZoomStep g_zoom;` and `if (g_zoom.tick(g_right.load(std::memory_order_relaxed)) == Pulse::Up) next.button[kPadUp] = 1u;`. Zooming out is the keyboard's Down arrow (D-pad Down), already bound.
- [ ] **Step 4: Run, see it pass; build; owner check.**
- [ ] **Step 5: Commit** with subject `feat(mouse): right click is one zoom step (the aim probe failed closed-loop hold; research/70)`.

---

### Task 8: The owner's play test and tuning

- [ ] **Step 1:** Claude launches `bash logs/playtest.sh` (developer mode; the mouse is on by default). The owner plays a full mission.
- [ ] **Step 2:** Collect the owner's notes on sensitivity, dead zone, invert, and the aim-hold feel. Adjust only knob *values* by relaunching with `PS2X_MOUSE_SENS=...` / `PS2X_MOUSE_DEADZONE=...`. Once the owner settles on values, change the defaults in `socom2MouseConfigFrom`'s `Config` initialisers, in the `knobs.h` rows, and in the `unset knobs give the defaults` test. Regenerate `docs/KNOBS.md`, then run RUN_CXX and RUN_PY_KNOBS.
- [ ] **Step 3: Commit** (if defaults changed) with subject `feat(mouse): the owner's play-tested defaults -- sens <s>, dead zone <d>`, filling in `<s>` and `<d>` with the settled values, naming the four paths.

---

### Task 9: Linearise against the game's stick-to-turn curve

**Files:**
- Modify: `third_party/ps2recomp/ps2xRuntime/include/runtime/socom2_mouse_core.h`
- Modify: `third_party/ps2recomp/ps2xTest/src/socom2_mouse_tests.cpp`
- Create: `research/71-stick-turn-curve.md (never written: Task 9 dropped)` (next free number)

- [ ] **Step 1: Measure.** Use a scripted run: `PS2X_SOCOM2_INPUT_SCRIPT` holds `RX=<v>` for 2 s each, for v = 0x88, 0x90, ... 0xF8, 0xFF, starting at a time the owner gives once in a mission (they say "go" and Claude computes the offset from the log's first-poll time). Alternatively, the owner presses O with a throwaway probe variant. Record the yaw. The camera yaw comes from Spike B's map if it has run; otherwise use screen-space motion between `PS2X_HOST_SCREENSHOT` frames at 0.1 s. Write the table of (deflection, degrees/s or px/s) into `research/71-stick-turn-curve.md (never written: Task 9 dropped)`, along with the lowest deflection that turns (the game's dead zone).
- [ ] **Step 2: Failing test:**

```cpp
        tc.Run("the linearised curve makes turn rate proportional to mouse speed", [](TestCase &t)
        {
            // The measured rate per deflection (research/71), interpolated, applied to the curve's output, must be
            // linear in the input units within 5% across the range.
            double lastRatio = -1;
            for (int units = 8; units <= kStickSpan - 0x18; units += 8)
            {
                const int defl = linearised(units) - 0x80;
                const double ratio = measuredRate(defl) / units;
                if (lastRatio > 0) t.IsTrue(std::fabs(ratio - lastRatio) / lastRatio < 0.05, "units " + std::to_string(units));
                lastRatio = ratio;
            }
        });
```

`measuredRate(int deflection)` and `linearised(int units)` go in the core. `measuredRate` interpolates the research/71 table, entered as a `constexpr` array. `linearised` is its inverse, also built at compile time from the same array.
- [ ] **Step 3:** Implement both. Apply `linearised` in `detail::axis` in place of `deadzone + whole`. Set the dead-zone default from the measurement. Rerun the Task 1 tests: the dead-zone and clamp tests now go through the table, so update their expected values to `linearised(...)`, keeping their intent: centre untouched, sign mirrored, clamp, carry.
- [ ] **Step 4:** RUN_CXX green; BUILD_GAME; the owner confirms that a flick and a drag of equal distance turn equally.
- [ ] **Step 5: Commit** with subject `feat(mouse): linearised against the game's measured stick-to-turn curve (research/71)`.

---

### Task 10: Spike B brief (a separate, one-session spike; not implemented in this plan)

Run as its own session under the brainstorming skill's spike path:

- Question: can the host steer the view by writing the camera's yaw and pitch directly?
- Starting map: the SOCOM I class layouts in reCOM PR #4 (`gamez_types.h`), against SOCOM II's actor (`player_actor`) and `cameraHolder` (`0x415ff0`, `socom2_addresses.h`). Find candidate floats with `PS2X_WATCH` while turning with the mouse.
- Pass: the writes steer the view in third person, first person/scoped, and while zoomed, without the game fighting them.
- If Task 6 failed: also prove the direct aim-mode write ("C") through the game's setter `FUN_005448a0`.
- Time box: one session; stop and write up if not found. Anything built is throwaway.

---

### Task 11: Finish

- [ ] **Step 1:** `bash scripts/build_macos.sh test`. Expected: `tests: Python  : ok`, `tests: C++    : ok`, `tests: VU1    : ok`. Paste the three lines into the merge message body.
- [ ] **Step 2:** Use superpowers:finishing-a-development-branch. The merge subject must be <= 120 chars (it becomes the changelog line), e.g. `merge feat-mouse-look: mouse look with raw deltas and a carried overflow, left-click fire, right-click aim-hold`. Push to `fork` only after the owner's go.

---

## Revision 2026-10-04 — direct look (spec "Revision 2026-10-04")

Owner approved spike B's recommendation. Order from here: **5a, 5b, 5c, 6, 7 (or 7-FALLBACK), 8, 11.** Task 9 is dropped
(no stick curve in the path). Global Constraints change: "No guest memory writes" now reads "guest writes for look only:
actor+0x70, actor+0x50 and controller+0x130, from the game thread in `scePad2Read`".

### Task 5a: The direct-look core (pure, TDD)

**Files:** `socom2_mouse_core.h`, `socom2_mouse_tests.cpp`.

**Produces:** `constexpr float kRadPerCount = 0.002f;` `struct PitchLimits { float lo = -1.2f; float hi = 1.2f; };`
`uint32_t controlOf(const uint8_t *ram, uint32_t actor);` (0 unless actor+0xc0 points at an object whose +4 points back)
`bool directLook(uint8_t *ram, uint32_t actor, double dx, double dy, const Config &cfg, const PitchLimits &lim);`
(false and nothing written when the controller does not validate; true otherwise, writing only when there is motion).
Yaw: q' = r ⊗ q, r = rotation about +Y by −dx·k (k = sens × kRadPerCount), written to +0x70 and +0x50 from +0x70's value.
Pitch: m_aimPitch − dy·k (invert Y negates), clamped to `lim`.

Tests (suite `Socom2MouseDirectLook`): yaw turns by exactly −dx·k and both copies match; the quaternion stays unit length
after 10 000 small turns; sensitivity scales both axes equally; pitch moves by −dy·k, inverts, clamps at both ends; a
controller whose back-pointer is wrong (or a null controller) writes nothing and returns false; no motion writes nothing
(RAM `memcmp`-equal).

### Task 5b: Glue — direct look first, stick as fallback; the pitch limits measured

**Files:** `socom2_mouse.cpp`, `socom2_mouse.h`, `socom2_host_input.{h,cpp}` (`rdram` becomes `uint8_t *`), tests.
In `socom2MouseApply`: on r0001 with the mode readable, `directLook(...)`; when it returns true the stick look is skipped,
else the Task 4 stick path runs. The trace adds `pitch=<m_aimPitch>`. Then one owner session: hold I fully up and K fully
down with the keyboard; the trace's `pitch=` extremes are the game's limits; match them to the tuning table's aim limits
(+0x54..0x70, printed by the trace's tuning line, extended to those eight floats). If one pair matches, `PitchLimits` is
read from the table each mission; if none does, the measured constants are written into `PitchLimits`' defaults with the
measurement cited.

### Task 5c: Mouse delivery off the main queue, measured

**Files:** `socom2_mouse_gc.mm`, `socom2_mouse_gc_stub.cpp`, `socom2_mouse.{h,cpp}`, `knobs.h` (+`PS2X_MOUSE_GC_MAINQ`,
Dev Flag, default 0), `docs/KNOBS.md`.
`mouse.handlerQueue` = a serial `dispatch_queue_create("socom2.mouse", ...)` unless `PS2X_MOUSE_GC_MAINQ=1`. The .mm counts
events, events delivered on the main thread, and the largest gap between successive events while moving;
`socom2MouseGcReport()` prints `[mouse] gc events=<n>/s main=<pct> maxgap=<ms>` every 5 s under the trace. One owner session
per setting (main queue, then own queue): moving the mouse continuously for 10 s each. Expected with the own queue:
main=0%, maxgap near the mouse's report interval (1-8 ms) instead of a frame (16-33 ms).
