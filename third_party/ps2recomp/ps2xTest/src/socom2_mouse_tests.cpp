// Mouse look and right-click aim-hold (macOS fork, spec docs/superpowers/specs/2026-10-03-mouse-look-design.md).
#include "MiniTest.h"
#include "runtime/socom2_mouse_core.h"
#include "socom2_mouse.h"

#include <cmath>
#include <cstring>
#include <string>
#include <thread>
#include <vector>

using namespace socom2_mouse;

namespace
{
    constexpr uint32_t kTestActor = 0x00D00000u;   // Socom2MouseDirectLook: a live actor
    constexpr uint32_t kTestCtrl = 0x00E00000u;    // and its controller
}

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

        tc.Run("a live actor's mode byte is read", [=](TestCase &t)
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

        tc.Run("a KSEG pointer is masked into RAM", [=](TestCase &t)
        {
            std::vector<uint8_t> ram(kRamSize, 0);
            const Revision *r = revisionFor("r0001");
            put32(ram, r->playerActor, 0x20D00000u);   // uncached alias
            put32(ram, 0x00D00000u, r->actorVtable);
            ram[0x00D00000u + kModeOffset] = 1;
            t.IsTrue(readMode(ram.data(), r).ok, "the alias reads the same object");
        });

        tc.Run("null actor, wrong vtable, out of range, no RAM, unknown revision: not readable", [=](TestCase &t)
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

    MiniTest::Case("Socom2MouseCapture", [](TestCase &tc)
    {
        auto in = [](bool focused, bool inMission, bool click = false, bool esc = false, bool down = false)
        {
            return CaptureInputs{true, focused, inMission, click, esc, down};
        };

        tc.Run("entering a mission focused captures; leaving it releases", [=](TestCase &t)
        {
            Capture c;
            t.Equals(static_cast<int>(c.step(in(true, false))), static_cast<int>(CaptureAction::None), "menus: nothing");
            t.Equals(static_cast<int>(c.step(in(true, true))), static_cast<int>(CaptureAction::Capture), "mission: capture");
            t.IsTrue(c.buttonsLive(), "buttons reach the game");
            t.Equals(static_cast<int>(c.step(in(true, true))), static_cast<int>(CaptureAction::None), "steady");
            t.Equals(static_cast<int>(c.step(in(true, false))), static_cast<int>(CaptureAction::Release), "menus: release");
            t.IsFalse(c.buttonsLive(), "no buttons while released");
        });

        tc.Run("focus loss releases, and only a click recaptures", [=](TestCase &t)
        {
            Capture c;
            c.step(in(true, true));
            t.Equals(static_cast<int>(c.step(in(false, true))), static_cast<int>(CaptureAction::Release), "focus lost");
            t.Equals(static_cast<int>(c.step(in(true, true))), static_cast<int>(CaptureAction::None), "focus back: still released");
            t.Equals(static_cast<int>(c.step(in(true, true, true, false, true))), static_cast<int>(CaptureAction::Capture), "click");
        });

        tc.Run("the recapturing click is swallowed until every button is up", [=](TestCase &t)
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

        tc.Run("Esc releases; a click recaptures", [=](TestCase &t)
        {
            Capture c;
            c.step(in(true, true));
            t.Equals(static_cast<int>(c.step(in(true, true, false, true))), static_cast<int>(CaptureAction::Release), "esc");
            t.Equals(static_cast<int>(c.step(in(true, true))), static_cast<int>(CaptureAction::None), "stays released");
            t.Equals(static_cast<int>(c.step(in(true, true, true, false, true))), static_cast<int>(CaptureAction::Capture), "click");
        });

        tc.Run("a new mission auto-captures again after an Esc in the last one", [=](TestCase &t)
        {
            Capture c;
            c.step(in(true, true));
            c.step(in(true, true, false, true));   // esc
            c.step(in(true, false));               // back to menus
            t.Equals(static_cast<int>(c.step(in(true, true))), static_cast<int>(CaptureAction::Capture), "next mission");
        });

        tc.Run("disabled never captures and releases a capture", [=](TestCase &t)
        {
            Capture c;
            c.step(in(true, true));
            CaptureInputs off = in(true, true);
            off.enabled = false;
            t.Equals(static_cast<int>(c.step(off)), static_cast<int>(CaptureAction::Release), "release");
            t.Equals(static_cast<int>(c.step(off)), static_cast<int>(CaptureAction::None), "stays off");
        });
    });

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

    MiniTest::Case("Socom2MouseDirectLook", [](TestCase &tc)
    {
        // A live actor at 0x00D00000 (identity-yaw quaternion in both copies) with its controller at 0x00E00000.
        struct World
        {
            std::vector<uint8_t> ram = std::vector<uint8_t>(kRamSize, 0);
            void f(uint32_t a, float v) { std::memcpy(ram.data() + a, &v, 4); }
            float f(uint32_t a) const { float v; std::memcpy(&v, ram.data() + a, 4); return v; }
            void u(uint32_t a, uint32_t v) { std::memcpy(ram.data() + a, &v, 4); }
            World()
            {
                for (uint32_t q : {0x50u, 0x70u}) { f(kTestActor + q + 12, 1.0f); }   // (0,0,0,1)
                u(kTestActor + 0xC0, kTestCtrl);
                u(kTestCtrl + 4, kTestActor);
                f(kTestCtrl + 0x130, 0.1f);
            }
            float yaw(uint32_t q = 0x70u) const { return 2.0f * std::atan2(f(kTestActor + q + 4), f(kTestActor + q + 12)); }
        };
        auto near = [](double a, double b, double eps = 1e-5) { return std::fabs(a - b) < eps; };

        tc.Run("the controller validates by its back-pointer", [](TestCase &t)
        {
            World w;
            t.Equals(controlOf(w.ram.data(), kTestActor), kTestCtrl, "valid");
            w.u(kTestCtrl + 4, 0x1234u);
            t.Equals(controlOf(w.ram.data(), kTestActor), 0u, "wrong back-pointer");
            w.u(kTestActor + 0xC0, 0u);
            t.Equals(controlOf(w.ram.data(), kTestActor), 0u, "null controller");
            w.u(kTestActor + 0xC0, kRamSize - 2u);
            t.Equals(controlOf(w.ram.data(), kTestActor), 0u, "out of RAM");
        });

        tc.Run("yaw turns by exactly -dx*k and both copies match", [=](TestCase &t)
        {
            World w; Config cfg;
            t.IsTrue(directLook(w.ram.data(), kTestActor, 100.0, 0.0, cfg, PitchLimits{}), "written");
            t.IsTrue(near(w.yaw(), -100.0 * kRadPerCount), "turned -0.2 rad");
            t.IsTrue(near(w.yaw(0x50u), w.yaw(0x70u)), "m_quat follows m_next_quat");
            t.IsTrue(near(w.f(kTestCtrl + 0x130), 0.1), "pitch untouched by x");
        });

        tc.Run("the quaternion stays unit length over many small turns", [=](TestCase &t)
        {
            World w; Config cfg;
            for (int i = 0; i < 10000; ++i) directLook(w.ram.data(), kTestActor, 3.0, 0.0, cfg, PitchLimits{});
            double n = 0; for (int i = 0; i < 4; ++i) n += double(w.f(kTestActor + 0x70 + 4 * i)) * w.f(kTestActor + 0x70 + 4 * i);
            t.IsTrue(near(std::sqrt(n), 1.0, 1e-4), "unit");
            t.IsTrue(near(w.f(kTestActor + 0x70), 0.0) && near(w.f(kTestActor + 0x78), 0.0), "still a pure yaw");
        });

        tc.Run("sensitivity scales both axes equally", [=](TestCase &t)
        {
            World w; Config cfg; cfg.sens = 2.0f;
            directLook(w.ram.data(), kTestActor, 10.0, 10.0, cfg, PitchLimits{});
            t.IsTrue(near(w.yaw(), -20.0 * kRadPerCount), "yaw doubled");
            t.IsTrue(near(w.f(kTestCtrl + 0x130), 0.1 - 20.0 * kRadPerCount), "pitch doubled");
        });

        tc.Run("pitch moves by -dy*k, inverts, and clamps at both ends", [=](TestCase &t)
        {
            World w; Config cfg;
            directLook(w.ram.data(), kTestActor, 0.0, 25.0, cfg, PitchLimits{});
            t.IsTrue(near(w.f(kTestCtrl + 0x130), 0.05), "0.1 - 0.05");
            cfg.invertY = true;
            directLook(w.ram.data(), kTestActor, 0.0, 25.0, cfg, PitchLimits{});
            t.IsTrue(near(w.f(kTestCtrl + 0x130), 0.1), "inverted back up");
            const PitchLimits lim{-0.3f, 0.4f};
            directLook(w.ram.data(), kTestActor, 0.0, 100000.0, cfg, lim);
            t.IsTrue(near(w.f(kTestCtrl + 0x130), 0.4), "clamped high");
            directLook(w.ram.data(), kTestActor, 0.0, -100000.0, cfg, lim);
            t.IsTrue(near(w.f(kTestCtrl + 0x130), -0.3), "clamped low");
        });

        tc.Run("an invalid controller writes nothing and says so", [](TestCase &t)
        {
            World w; Config cfg;
            w.u(kTestCtrl + 4, 0u);
            const std::vector<uint8_t> before = w.ram;
            t.IsFalse(directLook(w.ram.data(), kTestActor, 50.0, 50.0, cfg, PitchLimits{}), "falls back");
            t.IsTrue(w.ram == before, "RAM untouched");
        });

        tc.Run("no motion writes nothing", [](TestCase &t)
        {
            World w; Config cfg;
            const std::vector<uint8_t> before = w.ram;
            t.IsTrue(directLook(w.ram.data(), kTestActor, 0.0, 0.0, cfg, PitchLimits{}), "valid");
            t.IsTrue(w.ram == before, "RAM untouched");
        });
    });
}
