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
