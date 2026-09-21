#pragma once

#include "launcher/mapping.h"

#include <cstdint>

// Host input -> DualShock2 state for the SOCOM II libpad2 HLE (game_overrides_socom2.cpp).
//
// The HLE scePad2Read/scePad2GetButtonInfo stubs read this state; socom2HostInputPoll() refreshes it
// from the host keyboard, mouse and an optional scripted sequence. It is called from the game thread
// once per pad read; raylib's input state is a plain array written by the main thread's
// PollInputEvents, so reading it here is a benign race for a test interface.
//
// libpad2 button ids (bit order of the DS2 report bytes 3-4, then the analog fields):
//   0 SELECT  1 L3  2 R3  3 START  4 UP  5 RIGHT  6 DOWN  7 LEFT
//   8 L2  9 R2  10 L1  11 R1  12 TRIANGLE  13 CIRCLE  14 CROSS  15 SQUARE
//   0x10 RX  0x11 RY  0x12 LX  0x13 LY   (0x80 = centre)
//   0x14..0x1f pressure of RIGHT, LEFT, UP, DOWN, TRIANGLE, CIRCLE, CROSS, SQUARE, L1, R1, L2, R2
//
// Host mapping (keyboard is on whenever the pad is enabled), the DEFAULTS of launcher/mapping.h:
//   arrows = d-pad          WASD = left stick        IJKL = right stick
//   Enter / Escape = START  Backspace = SELECT
//   Z X C V = SQUARE CROSS CIRCLE TRIANGLE   (Space = CROSS too)
//   Q / E = L1 / R1         1 / 3 = L2 / R2          2 / 4 = L3 / R3
//   PS2X_INPUT_MAPPING (the launcher's, from the profile's block in config.json's "mappings") replaces the button tables whole;
//   the sticks are not in the table.
// Mouse (PS2X_SOCOM2_MOUSE=1): motion -> right stick (PS2X_SOCOM2_MOUSE_SENS, default 4),
//   left button = R1, right button = L1. The cursor is not captured (window-relative deltas).
// Script (PS2X_SOCOM2_INPUT_SCRIPT="6:START,9:CROSS,12:DOWN+CROSS:0.5"): at t seconds after the
//   first poll, hold the named buttons (and/or axes as LX=200) for `hold` seconds (default 0.25).

namespace ps2_stubs
{
    struct Socom2PadState
    {
        uint8_t axis[4] = {0x80u, 0x80u, 0x80u, 0x80u}; // ids 0x10-0x13: RX, RY, LX, LY
        uint8_t button[16] = {0};                        // ids 0x00-0x0F, 1 = pressed
        // R139: the pressure reported for TRIANGLE while it is down. 0xFF always, except when only the crouch
        // shortcut holds it (runtime/host_crouch_shortcut.h) -- SOCOM II's stance reads this pressure.
        uint8_t trianglePressure = 0xFFu;
    };

    enum Socom2PadButton : uint8_t
    {
        kPadSelect = 0, kPadL3 = 1, kPadR3 = 2, kPadStart = 3,
        kPadUp = 4, kPadRight = 5, kPadDown = 6, kPadLeft = 7,
        kPadL2 = 8, kPadR2 = 9, kPadL1 = 10, kPadR1 = 11,
        kPadTriangle = 12, kPadCircle = 13, kPadCross = 14, kPadSquare = 15,
    };

    // The keyboard map and the pad map are ONE table since 2026-09-21 (Sprint 10 Goal 8, R174): launcher/mapping.h,
    // resolved once from PS2X_INPUT_MAPPING (unset: the defaults, which are the tables that used to live here --
    // kSocom2Keys and the pad-to-PS2 array -- byte for byte). socom2HostInputMapping() is the resolved table; the
    // runtime prints its hash once at startup ("[socom2] input mapping hash=...") so a gate can pin it.
    const launcher::mapping::Mapping &socom2HostInputMapping();

    // Pressure field order (ids 0x14..0x1f) -> digital button id.
    inline constexpr uint8_t kSocom2PressureButton[12] = {
        kPadRight, kPadLeft, kPadUp, kPadDown, kPadTriangle, kPadCircle,
        kPadCross, kPadSquare, kPadL1, kPadR1, kPadL2, kPadR2};

    // What the game reads for pressure field `field` (id 0x14 + field): 0 when the button is up, else 0xFF --
    // or, for TRIANGLE, the state's own trianglePressure (R139). Both HLE read paths go through here.
    inline uint8_t socom2PressureOf(const Socom2PadState &pad, int field)
    {
        if (field < 0 || field >= 12 || !pad.button[kSocom2PressureButton[field]])
            return 0u;
        return kSocom2PressureButton[field] == kPadTriangle ? pad.trianglePressure : static_cast<uint8_t>(0xFFu);
    }

    // Refresh `pad` from the host. Safe to call before the window exists (does nothing then).
    void socom2HostInputPoll(Socom2PadState &pad);

    // Sprint 7 review finding F12: the PS2X_SOCOM2_INPUT_FILE sampler is a thread, and it used to be joined
    // only by the destructor of a namespace-scope static -- which main never reaches, because it leaves through
    // std::_Exit. These are the explicit half: the poll starts the sampler itself when the variable is set, and
    // PS2Runtime's teardown stops and joins it next to stopHostMic().
    void socom2HostInputStartSampler(const char *path);   // idempotent: the second call does nothing
    void socom2HostInputShutdown();                       // idempotent: stops and joins, then stays stopped
    bool socom2HostInputSamplerRunning();
}
