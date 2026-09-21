// Sprint 9 Goal 3 (Task 4 H): the one knob read that used to live in ps2_runtime_macros.h, the header every
// generated unit includes. It is its own translation unit on purpose: ps2_fpu_trap_enabled() is inline in that
// header and reached from the VU code, so whatever defines this function is pulled into every executable that
// links ps2_runtime -- vu1_replay included, which links no game stubs. In ps2_runtime.cpp it dragged the whole
// PS2Runtime object (host input, the profiler, the recompiled function table) into the tool's link.
#include "ps2x/knobs.h"

#include <cstdlib>

double ps2_fpu_trap_after_seconds()
{
    const char *e = ps2x::knob("PS2X_FPU_TRAP");
    return e ? std::atof(e) : -1.0;
}
