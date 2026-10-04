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
        c.enabled = ps2x::knobs::flagValue(knob("PS2X_MOUSE"), true);
        c.invertY = ps2x::knobs::flagValue(knob("PS2X_MOUSE_INVERT_Y"), false);
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

    void socom2MouseApply(uint8_t *rdram, KeyboardScope scope, Socom2PadState &next)
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
        // Look: written directly on r0001 when the actor's controller validates (spec revision 2026-10-04); the stick
        // otherwise -- an unknown revision, or no controller.
        const bool r0001 = std::strcmp(socom2_addresses::current().revision, "r0001") == 0;
        const bool direct = r0001 && mode.ok && directLook(rdram, mode.actor, dx, dy, cfg, PitchLimits{});
        const LookOut look = direct ? LookOut{} : socom2_mouse::look(cfg, dx, dy, g_look);
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
            // Diagnostic (read-only): the game's turn response. The actor's angular velocity (+0x48, research/50)
            // per read, and once per actor the r0001 Seal tuning table's turn fields (0x44c250, research/17).
            auto f32 = [&](uint32_t addr) {
                float v;
                std::memcpy(&v, rdram + (addr & 0x1FFFFFFFu), sizeof(v));
                return v;
            };
            static uint32_t tunedFor = 0;
            if (mode.ok && r0001 && tunedFor != mode.actor)
            {
                tunedFor = mode.actor;
                const uint32_t t = 0x0044C250u;
                std::cout << "[mouse] tuning stand_turn_factor=" << f32(t + 0x3c) << " turn_maxrate=" << f32(t + 0x40)
                          << " accel=" << f32(t + 0x44) << "," << f32(t + 0x48) << "," << f32(t + 0x4c) << "," << f32(t + 0x50)
                          << " throttle=" << f32(t + 0xf4) << "," << f32(t + 0xf8) << "," << f32(t + 0xfc) << ","
                          << f32(t + 0x100) << "," << f32(t + 0x104) << " throt_exp=" << f32(t + 0x118)
                          << " fb_accel=" << f32(t + 0x110) << " lr_accel=" << f32(t + 0x114) << " aim=";
                for (uint32_t o = 0x54; o <= 0x70; o += 4)
                    std::cout << f32(t + o) << (o < 0x70 ? "," : "");
                std::cout << std::endl;
            }
            float av[3] = {0.0f, 0.0f, 0.0f};
            if (mode.ok)
                for (int i = 0; i < 3; ++i)
                    av[i] = f32(mode.actor + 0x48u + 4u * i);
            const bool turning = av[0] != 0.0f || av[1] != 0.0f || av[2] != 0.0f;
            const bool stick = next.axis[0] != 0x80u || next.axis[1] != 0x80u;
            const uint8_t m = mode.ok ? mode.mode : 0xFFu;
            const uint32_t ctrl = mode.ok ? controlOf(rdram, mode.actor) : 0u;
            const float pitch = ctrl ? f32(ctrl + kAimPitch) : 0.0f;
            static float lastPitch = 0.0f;
            const bool pitched = pitch != lastPitch;
            lastPitch = pitch;
            if (dx != 0.0 || dy != 0.0 || pitched || look.moved || stick || turning || m != g_lastMode || probe != Pulse::None || next.button[kPadUp] ||
                next.button[kPadDown])
                std::cout << "[mouse] dx=" << dx << " dy=" << dy << " carry=" << g_look.carryX << "," << g_look.carryY
                          << " rx=" << int(next.axis[0]) << " ry=" << int(next.axis[1])
                          << " up=" << int(next.button[kPadUp]) << " down=" << int(next.button[kPadDown])
                          << " mode=" << (mode.ok ? int(mode.mode) : -1) << " actor=0x" << std::hex << mode.actor
                          << std::dec << " angvel=" << av[0] << "," << av[1] << "," << av[2] << " direct=" << direct
                          << " pitch=" << pitch << std::endl;
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
            socom2MouseGcStart(ps2x::knobOn("PS2X_MOUSE_GC_MAINQ", false));
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
        if (config().trace)
            socom2MouseGcReport();
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
