#pragma once

// Injected pad latch: the harness writes a pad-state file (PS2X_SOCOM2_INPUT_FILE) and holds a
// press for ~0.09 s of wall clock. The runtime used to read that file only inside the game's own
// pad poll, once per rendered frame, so below ~11 fps a whole press fell between two polls and was
// never seen (ten driven launches, 2026-09-18). A sampler thread now observes the file at a few
// hundred Hz and this latch remembers every button it saw, so the poll path takes a sample whose
// buttons carry everything pressed since the previous poll: a press is delivered late, never
// dropped.

#include <cstdint>
#include <cstdio>
#include <cstring>
#include <mutex>

namespace ps2x
{
    struct InjectedPadSample
    {
        uint32_t buttons = 0;
        uint8_t rx = 128;
        uint8_t ry = 128;
        uint8_t lx = 128;
        uint8_t ly = 128;
    };

    // The one line the harness writes: "b=<hex> rx=<u> ry=<u> lx=<u> ly=<u>". All five fields are
    // required; anything else leaves out untouched and returns false. Axes clamp to 0..255.
    inline bool parseInjectedPadLine(const char *line, InjectedPadSample &out)
    {
        if (line == nullptr)
            return false;

        unsigned mask = 0, rx = 128, ry = 128, lx = 128, ly = 128;
        if (std::sscanf(line, "b=%x rx=%u ry=%u lx=%u ly=%u", &mask, &rx, &ry, &lx, &ly) != 5)
            return false;

        const auto clamp255 = [](unsigned v) -> uint8_t
        {
            return static_cast<uint8_t>(v > 255u ? 255u : v);
        };

        out.buttons = static_cast<uint32_t>(mask);
        out.rx = clamp255(rx);
        out.ry = clamp255(ry);
        out.lx = clamp255(lx);
        out.ly = clamp255(ly);
        return true;
    }

    // A sampler thread calls observe() at a few hundred Hz with what the file says now; the game's
    // pad poll calls take(). take() returns the latest sample with its buttons OR-ed with every
    // button seen since the previous take(), so a press that lived entirely between two polls is
    // delivered to exactly one poll (as down), then released.
    class InjectedPadLatch
    {
    public:
        void observe(const InjectedPadSample &s)
        {
            std::lock_guard<std::mutex> lock(m_);
            latest_ = s;
            seen_ |= s.buttons;
        }

        InjectedPadSample take()
        {
            std::lock_guard<std::mutex> lock(m_);
            InjectedPadSample r = latest_;
            r.buttons |= seen_;
            seen_ = 0;
            return r;
        }

    private:
        std::mutex m_;
        InjectedPadSample latest_;
        uint32_t seen_ = 0;
    };
}
