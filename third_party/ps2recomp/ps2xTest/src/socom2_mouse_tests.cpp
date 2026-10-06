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

    MiniTest::Case("Socom2MousePitchLimits", [](TestCase &tc)
    {
        tc.Run("the tuning table's +0x5c/+0x58 are the limits (research/83)", [](TestCase &t)
        {
            std::vector<uint8_t> ram(kRamSize, 0);
            const float lo = -1.22173f, hi = 1.04719f;
            std::memcpy(ram.data() + kTuningTable + 0x5c, &lo, 4);
            std::memcpy(ram.data() + kTuningTable + 0x58, &hi, 4);
            const PitchLimits l = pitchLimitsFrom(ram.data());
            t.Equals(l.lo, lo, "down limit");
            t.Equals(l.hi, hi, "up limit");
        });

        tc.Run("an implausible table (not loaded, garbage) gives the measured constants", [](TestCase &t)
        {
            std::vector<uint8_t> ram(kRamSize, 0);   // zeros: lo == hi
            PitchLimits l = pitchLimitsFrom(ram.data());
            t.Equals(l.lo, kPitchDownLimit, "zeros: measured down");
            t.Equals(l.hi, kPitchUpLimit, "zeros: measured up");
            const float bad = 50.0f;
            std::memcpy(ram.data() + kTuningTable + 0x58, &bad, 4);
            l = pitchLimitsFrom(ram.data());
            t.Equals(l.hi, kPitchUpLimit, "out of range: measured up");
            t.Equals(pitchLimitsFrom(nullptr).lo, kPitchDownLimit, "no RAM");
        });
    });
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

    MiniTest::Case("Socom2MouseAimSens", [](TestCase &tc)
    {
        tc.Run("zoomed in (mode 1 and up) both axes turn by aimSens times the normal amount", [](TestCase &t)
        {
            Config cfg; cfg.aimSens = 0.5f;
            t.Equals(lookScale(cfg, 0), cfg.sens * kRadPerCount, "third person: normal");
            t.Equals(lookScale(cfg, 1), cfg.sens * 0.5f * kRadPerCount, "first person: aim");
            t.Equals(lookScale(cfg, 5), cfg.sens * 0.5f * kRadPerCount, "scoped: aim");
        });

        tc.Run("the knob sets it, the default is 0.6, nonsense falls back", [](TestCase &t)
        {
            t.Equals(ps2_stubs::socom2MouseConfigFrom([](const char *) -> const char * { return nullptr; }).aimSens, 0.6f, "default");
            t.Equals(ps2_stubs::socom2MouseConfigFrom([](const char *n) -> const char * {
                         return std::strcmp(n, "PS2X_MOUSE_AIM_SENS") == 0 ? "0.4" : nullptr; }).aimSens, 0.4f, "set");
            t.Equals(ps2_stubs::socom2MouseConfigFrom([](const char *n) -> const char * {
                         return std::strcmp(n, "PS2X_MOUSE_AIM_SENS") == 0 ? "-1" : nullptr; }).aimSens, 0.6f, "nonsense");
        });
    });

    MiniTest::Case("Socom2MouseScriptedRuns", [](TestCase &tc)
    {
        tc.Run("an input script or input file turns the mouse off unless PS2X_MOUSE says otherwise", [](TestCase &t)
        {
            t.IsFalse(ps2_stubs::socom2MouseConfigFrom([](const char *n) -> const char * {
                          return std::strcmp(n, "PS2X_SOCOM2_INPUT_SCRIPT") == 0 ? "6:START" : nullptr; }).enabled, "script: off");
            t.IsFalse(ps2_stubs::socom2MouseConfigFrom([](const char *n) -> const char * {
                          return std::strcmp(n, "PS2X_SOCOM2_INPUT_FILE") == 0 ? "logs/pad.txt" : nullptr; }).enabled, "file: off");
            t.IsTrue(ps2_stubs::socom2MouseConfigFrom([](const char *n) -> const char * {
                         if (std::strcmp(n, "PS2X_SOCOM2_INPUT_SCRIPT") == 0) return "6:START";
                         return std::strcmp(n, "PS2X_MOUSE") == 0 ? "1" : nullptr; }).enabled, "script + PS2X_MOUSE=1: on");
        });
    });

    MiniTest::Case("Socom2MouseMenuState", [](TestCase &tc)
    {
        tc.Run("the game is interactive only with a valid controller whose m_menustate is 0", [](TestCase &t)
        {
            std::vector<uint8_t> ram(kRamSize, 0);
            auto u = [&](uint32_t a, uint32_t v) { std::memcpy(ram.data() + a, &v, 4); };
            u(kTestActor + 0xC0, kTestCtrl);
            u(kTestCtrl + 4, kTestActor);
            t.IsTrue(interactive(ram.data(), kTestActor), "playing (0)");
            ram[kTestCtrl + kMenuState] = 3;
            t.IsFalse(interactive(ram.data(), kTestActor), "pause menu (3)");
            ram[kTestCtrl + kMenuState] = 5;
            t.IsFalse(interactive(ram.data(), kTestActor), "another menu (5)");
            ram[kTestCtrl + kMenuState] = 0;
            u(kTestCtrl + 4, 0u);
            t.IsFalse(interactive(ram.data(), kTestActor), "no valid controller");
            t.IsFalse(interactive(nullptr, kTestActor), "no RAM");
        });
    });
}
