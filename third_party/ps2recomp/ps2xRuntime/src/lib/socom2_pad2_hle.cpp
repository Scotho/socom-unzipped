// SOCOM II's libpad2 HLE: one DualShock2 on the first socket, fed by the host (socom2_host_input.cpp).
// Moved out of game_overrides_socom2.cpp by Sprint 13 Task C8 (audit F8) so ps2x_tests compiles and tests the
// real handlers (pad2_hle_tests.cpp) instead of linking return-to-caller stand-ins. Runner-only like its
// neighbours: the handlers are bound by name through the runtime's stub table (ps2_call_list.h).
#include "socom2_pad2_hle.h"
#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include "ps2_stubs.h"
#include "runtime/ps2_memory.h"
#include "ps2x/knobs.h"

#include <cstdint>
#include <cstring>
#include <iostream>

namespace ps2_stubs
{
    // ---- libpad2 (scePad2*) HLE ----------------------------------------------------------------
    // The game statically links Sony's socket-based libpad2 (scePad2Init/CreateSocket/Read/
    // GetState/GetButtonInfo) which RPCs to SIO2MAN/DS2U on the IOP. Those IOP drivers are not
    // emulated, so the wrappers were stubbed to return 0 and the game's per-frame reader
    // (FUN_002da930) saw no controller. We HLE the five top-level entry points to report one
    // connected DualShock2 on port 0 with neutral input, bypassing the IOP path entirely.
    // Button ids 0x10-0x13 are the analog axes (center 0x80); 0x00-0x0F are the digital buttons
    // (0 = released). Host input injection (real button presses) hooks the same shared state later.
    Socom2PadState g_socom2Pad;   // refreshed from the host by socom2HostInputPoll (socom2_host_input.cpp)

    // The pad HLE is on by default (Sprint 9 Goal 3, R160); PS2X_SOCOM2_PAD=0 boots with no controller, as
    // every boot did before input worked. When disabled these behave like the previous ret0 stubs (no
    // controller).
    bool socom2PadEnabled()
    {
        static const bool on = ps2x::knobOn("PS2X_SOCOM2_PAD", true);   // R160: on unless 0
        return on;
    }

    void scePad2Init(uint8_t *, R5900Context *ctx, PS2Runtime *)
    {
        SET_GPR_U32(ctx, 2, socom2PadEnabled() ? 1u : 0u);   // > 0 = ok
        ctx->pc = GPR_U32(ctx, 31);
    }

    // One DualShock2 only: socket 0 (the first CreateSocket) is connected; every other socket the
    // game opens (port 2, multitap slots) reports "no controller". Reporting all of them connected
    // made the shell count several local players and route the UI to a pad that never gets data.
    uint32_t g_socom2NextSocket = 0u;

    void scePad2CreateSocket(uint8_t *rdram, R5900Context *ctx, PS2Runtime *)
    {
        const uint32_t descriptor = GPR_U32(ctx, 4);
        const uint32_t socket = g_socom2NextSocket++;
        if (ps2x::knob("PS2X_SOCOM2_PAD_TRACE"))
        {
            uint32_t words[2] = {0u, 0u};
            if (descriptor != 0u)
                std::memcpy(words, rdram + (descriptor & PS2_RAM_MASK), sizeof(words));
            std::cout << "[pad-trace] CreateSocket desc=0x" << std::hex << descriptor << " [" << words[0] << " " << words[1]
                      << "] -> socket " << std::dec << socket << std::endl;
        }
        SET_GPR_U32(ctx, 2, socket);
        ctx->pc = GPR_U32(ctx, 31);
    }

    void scePad2GetState(uint8_t *, R5900Context *ctx, PS2Runtime *)
    {
        // The game opens a socket for its controller check at boot, deletes it, then opens the
        // one it actually reads; the HLE never sees the delete, so treat the newest socket as the
        // live one.
        const uint32_t socket = GPR_U32(ctx, 4);
        const bool connected = socom2PadEnabled() && g_socom2NextSocket != 0u && socket == g_socom2NextSocket - 1u;
        SET_GPR_U32(ctx, 2, connected ? 1u : 0u);   // 1 = connected/ready, 0 = nothing on this socket
        ctx->pc = GPR_U32(ctx, 31);
    }

    void scePad2Read(uint8_t *rdram, R5900Context *ctx, PS2Runtime *)
    {
        // Write a standard DualShock2 poll report into the caller's buffer (a1) for any code that
        // reads it raw, and return a positive data length so FUN_002da930 proceeds.
        const uint32_t buf = GPR_U32(ctx, 5) & PS2_RAM_MASK;
        if (socom2PadEnabled())
            socom2HostInputPoll(g_socom2Pad);
        uint8_t report[32] = {0};
        report[0] = 0x00;
        report[1] = 0x79;                   // DS2 analog + pressure mode
        report[2] = 0x5Au;
        report[3] = 0xFFu;                  // digital buttons, active-low
        report[4] = 0xFFu;
        for (int id = 0; id < 16; ++id)
        {
            if (g_socom2Pad.button[id])
                report[3 + id / 8] = static_cast<uint8_t>(report[3 + id / 8] & ~(1u << (id % 8)));
        }
        report[5] = g_socom2Pad.axis[0];    // RX
        report[6] = g_socom2Pad.axis[1];    // RY
        report[7] = g_socom2Pad.axis[2];    // LX
        report[8] = g_socom2Pad.axis[3];    // LY
        for (int field = 0; field < 12; ++field)
            report[9 + field] = socom2PressureOf(g_socom2Pad, field);   // R139: Triangle's may be light
        std::memcpy(rdram + buf, report, sizeof(report));
        // PS2X_SOCOM2_PAD_TRACE=1: log the first non-neutral reports the game reads.
        static const bool s_padTrace = ps2x::knob("PS2X_SOCOM2_PAD_TRACE") != nullptr;
        if (s_padTrace && (report[3] != 0xFFu || report[4] != 0xFFu))
        {
            static uint32_t s_lines = 0;
            if (s_lines++ < 40u)
                std::cout << "[pad-trace] read: buttons=" << std::hex << (unsigned)report[3] << " " << (unsigned)report[4]
                          << " axes=" << (unsigned)report[5] << "," << (unsigned)report[6] << "," << (unsigned)report[7] << "," << (unsigned)report[8]
                          << std::dec << std::endl;
        }
        SET_GPR_U32(ctx, 2, static_cast<uint32_t>(sizeof(report)));
        ctx->pc = GPR_U32(ctx, 31);
    }

    void scePad2GetButtonInfo(uint8_t *, R5900Context *ctx, PS2Runtime *)
    {
        // a2 = button id. 0x10-0x13 = analog axes (center 0x80); else digital button pressure.
        const uint32_t id = GPR_U32(ctx, 6);
        uint32_t value;
        if (id >= 0x10u && id <= 0x13u)
            value = g_socom2Pad.axis[id - 0x10u];
        else if (id < 0x10u)
            value = g_socom2Pad.button[id];
        else if (id >= 0x14u && id <= 0x1fu)
            value = socom2PressureOf(g_socom2Pad, static_cast<int>(id - 0x14u));   // R139: Triangle's may be light
        else
            value = 0u;
        // PS2X_SOCOM2_PAD_TRACE=1: which ids does the game poll, and what did it get for pressed ones?
        static const bool s_padTrace = ps2x::knob("PS2X_SOCOM2_PAD_TRACE") != nullptr;
        if (s_padTrace)
        {
            static uint32_t s_seenMask = 0u;
            static uint32_t s_pressedLines = 0u;
            const uint32_t bit = id < 32u ? (1u << id) : 0u;
            if (bit && !(s_seenMask & bit))
            {
                s_seenMask |= bit;
                std::cout << "[pad-trace] GetButtonInfo polls id 0x" << std::hex << id << std::dec << std::endl;
            }
            static uint32_t s_lastValue[32] = {0};
            if (id < 32u && value != s_lastValue[id] && s_pressedLines++ < 200u)
            {
                std::cout << "[pad-trace] GetButtonInfo id 0x" << std::hex << id << " " << s_lastValue[id] << " -> " << value << std::dec << std::endl;
                s_lastValue[id] = value;
            }
        }
        SET_GPR_U32(ctx, 2, value);
        ctx->pc = GPR_U32(ctx, 31);
    }

    // The three remaining libpad2 entry points the game calls each frame (FUN_002da930) are
    // *not* covered by the socket HLE above: natively they read the DMA double buffer registered
    // by scePad2CreateSocket (never set up by the HLE) and talk to DBCMAN through libdbc
    // (sceDbcReceiveData / SendData2). Answering them here keeps the pad state machine consistent
    // (state 0 -> 1 needs GetButtonProfile >= 0 and sceVibGetProfile >= 0) and keeps libdbc idle.
    void scePad2GetButtonProfile(uint8_t *rdram, R5900Context *ctx, PS2Runtime *)
    {
        // a1 = destination for the 40-bit button profile (bit n = button n supported). A DualShock2
        // reports the 16 digital buttons and the 16 analog/pressure fields (ids 0x00-0x1f).
        const uint32_t buf = GPR_U32(ctx, 5) & PS2_RAM_MASK;
        static const uint8_t kDs2Profile[5] = {0xFFu, 0xFFu, 0xFFu, 0xFFu, 0x00u};
        uint32_t length = 0u;
        if (socom2PadEnabled())
        {
            std::memcpy(rdram + buf, kDs2Profile, sizeof(kDs2Profile));
            length = static_cast<uint32_t>(sizeof(kDs2Profile));
        }
        SET_GPR_U32(ctx, 2, socom2PadEnabled() ? length : 0xFFFFFFFFu);
        ctx->pc = GPR_U32(ctx, 31);
    }

    void sceVibGetProfile(uint8_t *rdram, R5900Context *ctx, PS2Runtime *)
    {
        // a1 = actuator profile buffer; the game only sends SetActParam when byte 0 is nonzero.
        // Report no actuators (0 bytes, buffer zeroed) so no vibration traffic is generated.
        const uint32_t buf = GPR_U32(ctx, 5) & PS2_RAM_MASK;
        std::memset(rdram + buf, 0, 2);
        SET_GPR_U32(ctx, 2, 0u);            // count 0, >= 0 = success
        ctx->pc = GPR_U32(ctx, 31);
    }

    void sceVibSetActParam(uint8_t *, R5900Context *ctx, PS2Runtime *)
    {
        SET_GPR_U32(ctx, 2, 1u);            // accepted
        ctx->pc = GPR_U32(ctx, 31);
    }

    void socom2PadTestReset()
    {
        g_socom2Pad = Socom2PadState{};
        g_socom2NextSocket = 0u;
    }
}
