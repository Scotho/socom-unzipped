#pragma once
// Sprint 11 Task 8b: the per-subsystem *RuntimeState split, adapted from the MrCoolTheCucumber fork
// (research/41-cucumber-fork.md). One NAMED struct with ONE instance for the whole program, in place
// of the anonymous-namespace block in Helpers/Support.h that handed each of the nineteen stub
// translation units its own private copy (docs/KNOWN.md #4, the reverted 955539c).
//
// This group is the GS graphics parameter block -- the four bytes sceGsGetGParam hands the guest.
// The stubs that read it:
//   Stubs/GS.cpp             sceGsResetGraph  -> writes gparam.interlace / .omode / .ffmode
//                            sceGsGetGParam   -> copies gparam into the scratchpad (via Support.h's
//                                                writeGsGParamToScratch, the only other reader)
//                            sceGsSetDefaultDrawEnv paths -> read gparam.interlace / .ffmode
//
// Behaviour note: GS.cpp is the ONLY translation unit that reaches this state today (the two
// Support.h helpers that touch it, writeGsGParamToScratch, are called from GS.cpp alone), so the
// other eighteen copies were write-never-read. Sharing one is a no-op for the guest; what it buys
// is that a second TU cannot silently acquire a stale duplicate later.

#include <cstdint>

namespace ps2_stubs
{
    // The guest-visible layout of sceGsGetGParam's four bytes. Copied to the scratchpad verbatim.
    struct GsGParam
    {
        uint8_t interlace;
        uint8_t omode;
        uint8_t ffmode;
        uint8_t version;
    };

    static_assert(sizeof(GsGParam) == 4, "sceGsGetGParam hands the guest exactly four bytes");

    struct GsRuntimeState
    {
        // Default: interlaced NTSC, frame mode -- the value the anonymous-namespace definition had.
        GsGParam gparam{1, 2, 1, 3};
    };

    // The single instance. A function-local static inside an `inline` function has exactly one
    // definition across every translation unit that includes this header -- which is precisely what
    // the anonymous namespace did not give us. ps2xTest/src/runtime_state_tests.cpp pins that.
    inline GsRuntimeState &gsRuntimeState()
    {
        static GsRuntimeState state;
        return state;
    }
}
