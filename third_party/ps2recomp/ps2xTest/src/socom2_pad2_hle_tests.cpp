// Sprint 13 Task C8 (audit F8): SOCOM II's libpad2 HLE (socom2_pad2_hle.cpp) under test.
//
// Until C8 the test binary linked return-to-caller stand-ins for these handlers (the deleted socom2_link_stubs.cpp),
// so the player's controller path was proven only by the gate. These cases drive the real handlers with the values
// the game reads: the socket that is connected, the raw report scePad2Read writes, the per-id values
// scePad2GetButtonInfo answers (FUN_002da930 polls ids 0x00..0x1f), the button profile and the vibration profile.
// Documentation of the handlers' behaviour, not a defect's RED: reading them against these values found none.
// The suite runs with PS2X_SOCOM2_PAD unset, i.e. the HLE on (R160), and no window, so socom2HostInputPoll leaves
// the pad state the case wrote untouched.
#include "MiniTest.h"
#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include "ps2_stubs.h"
#include "runtime/ps2_memory.h"
#include "socom2_pad2_hle.h"

#include <cstdint>
#include <cstring>
#include <vector>

namespace
{
    constexpr uint32_t kRa = 0x002da9a0u;       // any return address: every handler leaves through $ra
    constexpr uint32_t kBuf = 0x00010000u;

    using Handler = void (*)(uint8_t *, R5900Context *, PS2Runtime *);

    struct Guest
    {
        std::vector<uint8_t> rdram = std::vector<uint8_t>(PS2_RAM_SIZE, 0u);
        R5900Context ctx{};

        // Call `fn` with a0..a2 as given; returns v0. The handler must set pc to $ra.
        uint32_t call(Handler fn, uint32_t a0 = 0u, uint32_t a1 = 0u, uint32_t a2 = 0u)
        {
            SET_GPR_U32(&ctx, 4, a0);
            SET_GPR_U32(&ctx, 5, a1);
            SET_GPR_U32(&ctx, 6, a2);
            SET_GPR_U32(&ctx, 31, kRa);
            ctx.pc = 0u;
            fn(rdram.data(), &ctx, nullptr);
            return GPR_U32((&ctx), 2);
        }
    };

    void fresh()
    {
        ps2_stubs::socom2PadTestReset();
    }
}

void register_socom2_pad2_hle_tests()
{
    MiniTest::Case("SOCOM2Pad2Hle", [](TestCase &tc)
    {
        tc.Run("scePad2Init reports success and returns to the caller", [](TestCase &t)
        {
            fresh();
            Guest g;
            t.IsTrue(ps2_stubs::socom2PadEnabled(), "the HLE is on by default (R160)");
            t.Equals(g.call(ps2_stubs::scePad2Init), 1u, "Init > 0 is ok");
            t.Equals(g.ctx.pc, kRa, "pc = $ra");
        });

        tc.Run("only the newest socket reports a connected pad", [](TestCase &t)
        {
            fresh();
            Guest g;
            t.Equals(g.call(ps2_stubs::scePad2GetState, 0u), 0u, "no socket opened yet: nothing connected");
            t.Equals(g.call(ps2_stubs::scePad2CreateSocket, 0u), 0u, "the first socket is 0");
            t.Equals(g.call(ps2_stubs::scePad2GetState, 0u), 1u, "socket 0 is the connected pad");
            // The game's boot check opens a socket, deletes it (the HLE never sees the delete) and opens the one it reads.
            t.Equals(g.call(ps2_stubs::scePad2CreateSocket, 0u), 1u, "the second socket is 1");
            t.Equals(g.call(ps2_stubs::scePad2GetState, 1u), 1u, "the newest socket is the live one");
            t.Equals(g.call(ps2_stubs::scePad2GetState, 0u), 0u, "an older socket reads as no controller");
            t.Equals(g.call(ps2_stubs::scePad2GetState, 7u), 0u, "a socket never opened reads as no controller");
            t.Equals(g.ctx.pc, kRa, "pc = $ra");
        });

        tc.Run("scePad2Read writes a neutral DualShock2 report and returns its length", [](TestCase &t)
        {
            fresh();
            Guest g;
            std::memset(g.rdram.data() + kBuf, 0xCC, 64);
            t.Equals(g.call(ps2_stubs::scePad2Read, 0u, kBuf), 32u, "a positive data length (FUN_002da930 proceeds)");
            const uint8_t *r = g.rdram.data() + kBuf;
            t.Equals(static_cast<unsigned>(r[0]), 0x00u, "byte 0");
            t.Equals(static_cast<unsigned>(r[1]), 0x79u, "byte 1: DS2 analog + pressure mode");
            t.Equals(static_cast<unsigned>(r[2]), 0x5Au, "byte 2");
            t.Equals(static_cast<unsigned>(r[3]), 0xFFu, "digital byte 1, active-low: nothing pressed");
            t.Equals(static_cast<unsigned>(r[4]), 0xFFu, "digital byte 2, active-low: nothing pressed");
            for (int i = 5; i <= 8; ++i)
                t.Equals(static_cast<unsigned>(r[i]), 0x80u, "the four axes centred");
            for (int i = 9; i < 32; ++i)
                t.Equals(static_cast<unsigned>(r[i]), 0x00u, "no pressure, then zero padding");
            t.Equals(static_cast<unsigned>(r[32]), 0xCCu, "nothing written past the 32-byte report");
            t.Equals(g.ctx.pc, kRa, "pc = $ra");
        });

        tc.Run("scePad2Read carries the pad state: active-low buttons, axes, pressures", [](TestCase &t)
        {
            fresh();
            Guest g;
            ps2_stubs::g_socom2Pad.button[ps2_stubs::kPadUp] = 1u;       // id 4: byte 3 bit 4
            ps2_stubs::g_socom2Pad.button[ps2_stubs::kPadCross] = 1u;    // id 14: byte 4 bit 6
            ps2_stubs::g_socom2Pad.button[ps2_stubs::kPadTriangle] = 1u; // id 12: byte 4 bit 4
            ps2_stubs::g_socom2Pad.trianglePressure = 0x40u;             // R139: a light Triangle (the crouch shortcut)
            ps2_stubs::g_socom2Pad.axis[0] = 0x11u;                      // RX
            ps2_stubs::g_socom2Pad.axis[1] = 0x22u;                      // RY
            ps2_stubs::g_socom2Pad.axis[2] = 0x33u;                      // LX
            ps2_stubs::g_socom2Pad.axis[3] = 0x44u;                      // LY
            // Masked like every guest pointer: an uncached-segment alias of kBuf lands at kBuf.
            g.call(ps2_stubs::scePad2Read, 0u, 0x20000000u | kBuf);
            const uint8_t *r = g.rdram.data() + kBuf;
            t.Equals(static_cast<unsigned>(r[3]), 0xEFu, "UP clears bit 4 of byte 3");
            t.Equals(static_cast<unsigned>(r[4]), 0xAFu, "CROSS and TRIANGLE clear bits 6 and 4 of byte 4");
            t.Equals(static_cast<unsigned>(r[5]), 0x11u, "byte 5 = RX");
            t.Equals(static_cast<unsigned>(r[6]), 0x22u, "byte 6 = RY");
            t.Equals(static_cast<unsigned>(r[7]), 0x33u, "byte 7 = LX");
            t.Equals(static_cast<unsigned>(r[8]), 0x44u, "byte 8 = LY");
            // Pressure fields 9..20: RIGHT, LEFT, UP, DOWN, TRIANGLE, CIRCLE, CROSS, SQUARE, L1, R1, L2, R2.
            t.Equals(static_cast<unsigned>(r[9 + 2]), 0xFFu, "UP's pressure is full");
            t.Equals(static_cast<unsigned>(r[9 + 4]), 0x40u, "TRIANGLE's pressure is the state's own (R139)");
            t.Equals(static_cast<unsigned>(r[9 + 6]), 0xFFu, "CROSS's pressure is full");
            t.Equals(static_cast<unsigned>(r[9 + 0]), 0x00u, "RIGHT is up: no pressure");
            t.Equals(static_cast<unsigned>(r[9 + 7]), 0x00u, "SQUARE is up: no pressure");
        });

        tc.Run("scePad2GetButtonInfo answers the id the game polls", [](TestCase &t)
        {
            fresh();
            Guest g;
            ps2_stubs::g_socom2Pad.button[ps2_stubs::kPadCross] = 1u;
            ps2_stubs::g_socom2Pad.button[ps2_stubs::kPadTriangle] = 1u;
            ps2_stubs::g_socom2Pad.trianglePressure = 0x40u;
            ps2_stubs::g_socom2Pad.axis[2] = 0x05u;   // LX hard left
            // a2 = the button id (a0 the socket, a1 unused here).
            t.Equals(g.call(ps2_stubs::scePad2GetButtonInfo, 0u, 0u, 0x0Eu), 1u, "id 0x0e CROSS: pressed = 1");
            t.Equals(g.call(ps2_stubs::scePad2GetButtonInfo, 0u, 0u, 0x0Fu), 0u, "id 0x0f SQUARE: released = 0");
            t.Equals(g.call(ps2_stubs::scePad2GetButtonInfo, 0u, 0u, 0x10u), 0x80u, "id 0x10 RX: centred");
            t.Equals(g.call(ps2_stubs::scePad2GetButtonInfo, 0u, 0u, 0x12u), 0x05u, "id 0x12 LX: the axis");
            t.Equals(g.call(ps2_stubs::scePad2GetButtonInfo, 0u, 0u, 0x14u + 6u), 0xFFu, "id 0x1a: CROSS's pressure");
            t.Equals(g.call(ps2_stubs::scePad2GetButtonInfo, 0u, 0u, 0x14u + 4u), 0x40u, "id 0x18: TRIANGLE's light pressure");
            t.Equals(g.call(ps2_stubs::scePad2GetButtonInfo, 0u, 0u, 0x14u + 0u), 0u, "id 0x14: RIGHT released");
            t.Equals(g.call(ps2_stubs::scePad2GetButtonInfo, 0u, 0u, 0x20u), 0u, "an id past the profile answers 0");
            t.Equals(g.ctx.pc, kRa, "pc = $ra");
        });

        tc.Run("scePad2GetButtonProfile reports the 32 DualShock2 ids and its length", [](TestCase &t)
        {
            fresh();
            Guest g;
            std::memset(g.rdram.data() + kBuf, 0xCC, 16);
            t.Equals(g.call(ps2_stubs::scePad2GetButtonProfile, 0u, kBuf), 5u, "the 40-bit profile's byte count");
            const uint8_t *p = g.rdram.data() + kBuf;
            const uint8_t expected[5] = {0xFFu, 0xFFu, 0xFFu, 0xFFu, 0x00u};
            t.IsTrue(std::memcmp(p, expected, 5) == 0, "bits 0..31 set (ids 0x00..0x1f), bits 32..39 clear");
            t.Equals(static_cast<unsigned>(p[5]), 0xCCu, "nothing written past the profile");
            t.Equals(g.ctx.pc, kRa, "pc = $ra");
        });

        tc.Run("the vibration calls report no actuators and accept a parameter", [](TestCase &t)
        {
            fresh();
            Guest g;
            std::memset(g.rdram.data() + kBuf, 0xCC, 4);
            t.Equals(g.call(ps2_stubs::sceVibGetProfile, 0u, kBuf), 0u, "count 0 (>= 0 = success)");
            const uint8_t *p = g.rdram.data() + kBuf;
            t.Equals(static_cast<unsigned>(p[0]), 0u, "byte 0 zero: the game sends no SetActParam");
            t.Equals(static_cast<unsigned>(p[1]), 0u, "byte 1 zero");
            t.Equals(static_cast<unsigned>(p[2]), 0xCCu, "two bytes written, no more");
            t.Equals(g.call(ps2_stubs::sceVibSetActParam, 0u, kBuf), 1u, "SetActParam accepted");
            t.Equals(g.ctx.pc, kRa, "pc = $ra");
        });
    });
}
