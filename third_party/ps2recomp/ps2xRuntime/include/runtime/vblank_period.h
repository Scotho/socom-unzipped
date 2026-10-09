#pragma once
// macOS fork: the scheduler's VBlank period. The default is the 16,667 us it always used (60.00 Hz); PS2X_VBLANK_NTSC
// selects NTSC's 1001/60000 s (59.94 Hz), the rate T0's hblank clock (15,734 Hz: 262.5 lines a field) and the CD and
// MPEG timing already assume -- so the game's T0-paced frame lock and the VBlank grid stop sliding past each other.
#include <chrono>
#include <cstdint>

namespace ps2x_vblank
{
    inline std::chrono::nanoseconds period(bool ntsc)
    {
        return ntsc ? std::chrono::nanoseconds(16683333) : std::chrono::nanoseconds(16667000);
    }

    // In EE cycles, rounded up (as the scheduler's microsecondsToEeCycles always did).
    inline uint64_t periodCycles(bool ntsc, uint64_t eeClockHz)
    {
        const uint64_t ns = static_cast<uint64_t>(period(ntsc).count());
        return (ns * eeClockHz + 999999999ull) / 1000000000ull;
    }
}
