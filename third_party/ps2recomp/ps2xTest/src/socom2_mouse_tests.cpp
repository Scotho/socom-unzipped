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
