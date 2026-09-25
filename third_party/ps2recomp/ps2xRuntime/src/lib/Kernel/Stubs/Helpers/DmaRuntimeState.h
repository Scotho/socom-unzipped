#pragma once
// Sprint 11 Task 8b: the per-subsystem *RuntimeState split, adapted from the MrCoolTheCucumber fork
// (research/41-cucumber-fork.md). One NAMED struct per subsystem, OWNED BY THE PS2Runtime that the
// stub was called with -- a std::unique_ptr member reached as runtime->dmaRuntimeState(), which is
// the fork's shape (its ps2_runtime.h:2341-2344, Stubs/DMA.cpp:127, Helpers/Support.h:1418). It
// replaces the anonymous-namespace block in Helpers/Support.h that handed each of the nineteen stub
// translation units its own private copy (docs/KNOWN.md #4, the reverted 955539c), and it replaces
// the process-wide singleton that the first pass of this task put in its place.
//
// This group is the DMA stub's software model of an in-flight transfer, the DMA environment block
// the guest reads back, and the stub's log budget. The stubs that read it:
//   Stubs/DMA.cpp  sceDmaSend / sceDmaSendI / sceDmaSendM / sceDmaSendN
//                    -> Support.h's submitDmaSend marks the channel pending and spends stubLogCount
//                  sceDmaSync / sceDmaSyncN
//                    -> Support.h's submitDmaSync consumes the pending mark and reports busy
//                  sceDmaGetEnv / sceDmaPutEnv  -> environmentMutex, currentEnvironment
//                  sceDmaReset                  -> reset()
//
// Behaviour note: submitDmaSend and submitDmaSync are called from Stubs/DMA.cpp and nowhere else, so
// DMA.cpp's copy was the only live one; the other eighteen were never written. The pending mark IS
// guest-visible (sceDmaSync's return value), which is exactly why the test drives it through the
// stub rather than only comparing addresses. One change of guest-visible behaviour rides with this
// header: sceDmaReset now clears the pending-poll map as well as the environment block, because a
// controller reset means no transfer is in flight -- that is the fork's reset() (its DMA.cpp:91-97)
// and it closes an asymmetry our version had.

#include <cstdint>
#include <mutex>
#include <unordered_map>

class PS2Runtime;

namespace ps2_stubs
{
    inline constexpr uint32_t kMaxDmaStubLogs = 64;

    // The guest ABI of sceDmaEnv, read back verbatim by sceDmaGetEnv.
    struct SceDmaEnv
    {
        uint8_t sts = 0;
        uint8_t std = 0;
        uint8_t mfd = 0;
        uint8_t rele = 0;
        uint32_t pcr = 0;
        uint32_t sqwc = 0;
        uint32_t rbor = 0;
        uint32_t rbsr = 0;
    };

    static_assert(sizeof(SceDmaEnv) == 0x14, "sceDmaEnv must match the guest ABI");

    struct DmaRuntimeState
    {
        std::mutex mutex;
        // channel base address -> polls still owed before the model calls the transfer done.
        std::unordered_map<uint32_t, uint32_t> pendingPolls;
        uint32_t stubLogCount = 0;

        std::mutex environmentMutex;
        SceDmaEnv currentEnvironment;

        // Back to a freshly constructed runtime's DMA state. sceDmaReset calls it, which is the
        // fork's wiring; PS2Runtime::resetStubRuntimeState() calls it too.
        void reset()
        {
            {
                std::lock_guard<std::mutex> lock(mutex);
                pendingPolls.clear();
                stubLogCount = 0;
            }
            std::lock_guard<std::mutex> envLock(environmentMutex);
            currentEnvironment = {};
        }
    };

    // The state `runtime` owns. A null runtime is a stub reached with no runtime at all and gets
    // one process-wide fallback instance, the only instance here that is not per-runtime.
    DmaRuntimeState &dmaRuntimeStateFor(PS2Runtime *runtime);
}
