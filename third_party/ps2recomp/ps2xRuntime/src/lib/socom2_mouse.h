#pragma once
// Mouse look and right-click aim-hold -- the macOS fork's glue (spec docs/superpowers/specs/2026-10-03-mouse-look-design.md).
// The pure core is runtime/socom2_mouse_core.h. Threads: socom2MouseApply on the game thread (scePad2Read),
// socom2MouseFrame on the main thread, socom2MouseAddRaw from any thread. Shared state is atomics only.
#include "runtime/socom2_mouse_core.h"
#include "socom2_host_input.h"

#include <cstdint>

namespace ps2_stubs
{
    socom2_mouse::Config socom2MouseConfigFrom(const char *(*knob)(const char *));
    void socom2MouseApply(uint8_t *rdram, KeyboardScope scope, Socom2PadState &next);   // writes look (spec revision 2026-10-04)
    void socom2MouseFrame();
    void socom2MouseAddRaw(double dx, double dy);
    // socom2_mouse_gc.mm on Apple, socom2_mouse_gc_stub.cpp elsewhere. mainQueue: deliver on the main queue (the
    // PS2X_MOUSE_GC_MAINQ baseline) instead of the mouse's own.
    bool socom2MouseGcStart(bool mainQueue);
    void socom2MouseGcReport();  // the trace's delivery line: events/s, share on the main thread, largest gap
}
