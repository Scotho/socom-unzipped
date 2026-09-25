// The runtime's definition of the PS2X_TRIGGER latch (runtime/ps2_trace_armed.h). A TU of its own so that any
// executable whose link pulls one of its readers (vu1_replay pulls the VU1 core, not ps2_runtime.cpp) gets it.
#include "runtime/ps2_trace_armed.h"

std::atomic<bool> g_ps2xTraceArmed{false};
