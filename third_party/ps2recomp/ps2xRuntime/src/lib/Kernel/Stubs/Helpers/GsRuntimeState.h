#pragma once
// Sprint 11 Task 8b: the per-subsystem *RuntimeState split, adapted from the MrCoolTheCucumber fork
// (research/41-cucumber-fork.md). One NAMED struct per subsystem, OWNED BY THE PS2Runtime that the
// stub was called with -- a std::unique_ptr member reached as runtime->gsRuntimeState(), which is
// the fork's shape (its ps2_runtime.h:2341-2344). It replaces the anonymous-namespace block in
// Helpers/Support.h that handed each of the nineteen stub translation units its own private copy
// (docs/KNOWN.md #4, the reverted 955539c), and it replaces the process-wide singleton that the
// first pass of this task put in its place.
//
// This group is the GS graphics parameter block -- the four bytes sceGsGetGParam hands the guest.
// The stubs that read it:
//   Stubs/GS.cpp             sceGsResetGraph  -> writes gparam.interlace / .omode / .ffmode
//                            sceGsGetGParam   -> copies gparam into the scratchpad (via Support.h's
//                                                writeGsGParamToScratch, the only other reader)
//                            the two SMODE2 paths and the field-order pick read .interlace/.ffmode
//
// Behaviour note: GS.cpp is the ONLY translation unit that reaches this state today (Support.h's
// writeGsGParamToScratch is called from GS.cpp alone), so the other eighteen copies were
// write-never-read. Making it per-runtime is a no-op for a single-runtime game; what it buys is
// that a second runtime in the same process cannot inherit the first one's video mode.

#include <cstdint>

class PS2Runtime;

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

        // Back to a freshly constructed runtime's GParam. PS2Runtime::resetStubRuntimeState()
        // calls it; no guest path does, because sceGsResetGraph sets the block rather than
        // clearing it -- it is the entry point a save-state restore (Task 8c) needs.
        void reset()
        {
            gparam = GsGParam{1, 2, 1, 3};
        }
    };

    // The state `runtime` owns. A null runtime is a stub reached with no runtime at all -- which
    // sceGsResetGraph allows, since its GIF packet and scratchpad copy sit behind `if (runtime)` --
    // and gets one process-wide fallback instance, the only instance here that is not per-runtime.
    GsRuntimeState &gsRuntimeStateFor(PS2Runtime *runtime);
}
