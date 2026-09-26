// SOCOM II's libpad2 HLE (socom2_pad2_hle.cpp): the state its handlers share. The handlers themselves
// (scePad2Init/CreateSocket/GetState/Read/GetButtonInfo/GetButtonProfile, sceVibGetProfile/SetActParam) are
// declared by ps2_stubs.h through PS2_STUB_LIST.
#pragma once
#include "socom2_host_input.h"

#include <cstdint>

namespace ps2_stubs
{
    // The one pad the game reads: refreshed from the host by socom2HostInputPoll on every scePad2Read.
    extern Socom2PadState g_socom2Pad;
    // The next socket scePad2CreateSocket hands out; the newest one is the connected pad.
    extern uint32_t g_socom2NextSocket;
    // PS2X_SOCOM2_PAD (R160: on unless 0), read once per process.
    bool socom2PadEnabled();
    // Test only: a fresh pad state and no sockets opened.
    void socom2PadTestReset();
}
