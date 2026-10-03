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
#include <cstring>
#include <deque>

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
}
