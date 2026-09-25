#pragma once
// PS2X_TRIGGER's latch: set by the SOCOM II runner's pc sampler (game_overrides_socom2.cpp) when the trigger fires,
// read by the "trig" trace modes of the VIF1 interpreter, the VU1 core and the GL backend.
//
// Sprint 13 Task C8 (audit F22, the same seam as ps2HostProfStart): the runtime reads it, so the runtime defines it
// (ps2_trace_armed.cpp) -- it used to live in the game file, and ps2x_tests and vu1_replay each carried a stand-in
// definition to link. Never armed outside the runner.
#include <atomic>

extern std::atomic<bool> g_ps2xTraceArmed;
