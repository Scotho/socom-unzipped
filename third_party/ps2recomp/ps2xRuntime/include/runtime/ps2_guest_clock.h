#pragma once

#include <atomic>
#include <cstdint>

// Host nanoseconds spent emulating units other than the EE on the game thread (the VU1
// interpreter runs inside the VIF1 DMA kick). The EE cycle accounting subtracts them, so guest
// time advances only while the EE itself is being emulated: an emulator that cannot keep up slows
// the whole machine down, it does not let the guest measure the host's stall as elapsed time.
// (SOCOM II integrates its camera spring with the T0 time between flips; at 3 flips/s it saw
// dt = 300 ms and the camera position diverged to +/-FLT_MAX.)
// Included only by the VU1 core and the scheduler — not by ps2_runtime.h, so editing it does not
// recompile the generated code.
inline std::atomic<int64_t> &ps2GuestClockExcludedNs()
{
    static std::atomic<int64_t> ns{0};
    return ns;
}
