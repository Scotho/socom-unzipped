#pragma once
// Sprint 11 Task 8b: the per-subsystem *RuntimeState split, adapted from the MrCoolTheCucumber fork
// (research/41-cucumber-fork.md). One NAMED struct with ONE instance for the whole program, in place
// of the anonymous-namespace block in Helpers/Support.h that handed each of the nineteen stub
// translation units its own private copy (docs/KNOWN.md #4, the reverted 955539c).
//
// This group is the DMA stub's software model of an in-flight transfer, plus its log budget.
// The stubs that read it:
//   Stubs/DMA.cpp  sceDmaSend / sceDmaSendI / sceDmaSendM / sceDmaSendN
//                    -> Support.h's submitDmaSend marks the channel pending and spends stubLogCount
//                  sceDmaSync / sceDmaSyncN
//                    -> Support.h's submitDmaSync consumes the pending mark and reports busy
//
// Behaviour note: submitDmaSend and submitDmaSync are called from Stubs/DMA.cpp and nowhere else, so
// DMA.cpp's copy was the only live one; the other eighteen were never written. Sharing one is a
// no-op for the guest. The pending mark IS guest-visible (sceDmaSync's return value), which is
// exactly why the test drives it through the stub rather than only comparing addresses.

#include <cstdint>
#include <mutex>
#include <unordered_map>

namespace ps2_stubs
{
    inline constexpr uint32_t kMaxDmaStubLogs = 64;

    struct DmaRuntimeState
    {
        std::mutex mutex;
        // channel base address -> polls still owed before the model calls the transfer done.
        std::unordered_map<uint32_t, uint32_t> pendingPolls;
        uint32_t stubLogCount = 0;
    };

    // The single instance. A function-local static inside an `inline` function has exactly one
    // definition across every translation unit that includes this header -- which is precisely what
    // the anonymous namespace did not give us. ps2xTest/src/runtime_state_tests.cpp pins that.
    inline DmaRuntimeState &dmaRuntimeState()
    {
        static DmaRuntimeState state;
        return state;
    }
}
