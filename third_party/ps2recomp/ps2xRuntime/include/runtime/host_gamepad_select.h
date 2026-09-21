#pragma once
// Sprint 7 Task 8 (owner request 2026-09-18): WHICH host pad the game reads, in one place.
//
// Three call sites read a raylib gamepad -- the libpad HLE (Kernel/Stubs/Pad.cpp), the generic pad path
// (ps2_pad.cpp) and SOCOM's own poll (socom2_host_input.cpp) -- and all three hard-coded slot 0 or "the first
// available". With two devices plugged in (a wheel, a spare pad, a docked laptop's virtual device) the one that
// answers slot 0 is not the one in the player's hands, so the launcher now picks and passes
// PS2X_HOST_GAMEPAD_INDEX. Unset keeps exactly the old behaviour: the first available pad.
//
// PS2X_HOST_GAMEPAD=0 (host_gamepad.h) still disables every read; it is checked by the callers, not here, so
// that this helper stays pure and testable with a fake `available`.
#include <cstdlib>
#include "ps2x/knobs.h"

// raylib 5.5 tracks four pads (MAX_GAMEPADS); IsGamepadAvailable is false for the rest.
constexpr int kHostGamepadSlots = 4;

// The env index when it parses, is in [0, count) and is available; else the lowest available index; else -1
// (no pad -- the callers then read the keyboard).
inline int hostGamepadSelect(const char *envValue, int count, bool (*available)(int))
{
    if (available == nullptr || count <= 0)
        return -1;
    if (envValue != nullptr && *envValue != 0)
    {
        char *end = nullptr;
        const long wanted = std::strtol(envValue, &end, 10);
        if (end != envValue && wanted >= 0 && wanted < static_cast<long>(count) && available(static_cast<int>(wanted)))
            return static_cast<int>(wanted);
    }
    for (int i = 0; i < count; ++i)
    {
        if (available(i))
            return i;
    }
    return -1;
}

// PS2X_PAD_DEADZONE, read once. 0.15 is what socom2_host_input.cpp has used since 2026-09-16; the other two pad
// paths had no dead zone at all before this task (ruling R95).
inline float hostPadDeadZone()
{
    static const float s_deadZone = []
    {
        const char *const e = ps2x::knob("PS2X_PAD_DEADZONE");
        if (e == nullptr || *e == 0)
            return 0.15f;
        char *end = nullptr;
        const double v = std::strtod(e, &end);
        if (end == e)
            return 0.15f;
        if (v < 0.0)
            return 0.0f;
        if (v > 0.5)
            return 0.5f;
        return static_cast<float>(v);
    }();
    return s_deadZone;
}

// A stick reading with the dead zone taken out: 0 inside it, and the rest rescaled so the value still reaches
// +/-1 at full deflection (a hard cut would make the first usable step a jump).
// PS2X_HOST_GAMEPAD_INDEX, read once. It was a getenv on every pad poll in all three pad paths.
inline const char *hostGamepadIndexKnob()
{
    static const char *const s_value = ps2x::knob("PS2X_HOST_GAMEPAD_INDEX");
    return s_value;
}

inline float hostPadAxis(float v, float deadZone)
{
    if (deadZone <= 0.0f)
        return v;
    const float mag = v < 0.0f ? -v : v;
    if (mag <= deadZone)
        return 0.0f;
    const float scaled = (mag - deadZone) / (1.0f - deadZone);
    return v < 0.0f ? -scaled : scaled;
}
