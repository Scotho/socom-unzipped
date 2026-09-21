#pragma once

// PS2X_HOST_GAMEPAD=0 disables every read of the host gamepad (the libpad HLE in Kernel/Stubs/Pad.cpp, the generic
// pad path in ps2_pad.cpp, and the SOCOM host-input poll in socom2_host_input.cpp). The parity gate and the online
// launch scripts set it: with an Xbox controller plugged in, the libpad HLE reported a configured controller and the
// game skipped its PRECISION SHOOTER CONFIGURATION screens and the "save to memory card?" dialog at boot
// (s6_gamepad / s6_gamepad2, 2026-09-16), which the transition stage keys on -- a harness run must not depend on what
// is plugged into the host. Unset, empty, or anything but "0" leaves the gamepad enabled (the player's default).

#include <cstdlib>
#include <cstring>
#include "ps2x/knobs.h"

inline bool hostGamepadAllowed(const char *env)
{
    return env == nullptr || *env == 0 || std::strcmp(env, "0") != 0;
}

inline bool hostGamepadEnabled()
{
    static const bool s_enabled = hostGamepadAllowed(ps2x::knob("PS2X_HOST_GAMEPAD"));
    return s_enabled;
}
