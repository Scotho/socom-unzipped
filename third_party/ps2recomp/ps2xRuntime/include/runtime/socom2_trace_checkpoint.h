// Sprint 13 Task C3 (audit F11): where a tracing wrap may read the values its original leaves behind.
//
// A tracing wrap calls the recompiled original and then logs what it changed -- a result in v0, a fade the
// callee wrote back, a queue's new length. That "after" read is only true at one point: when the original has
// run to its own `jr ra`. A recompiled call can instead leave through an EE scheduler checkpoint (any dispatch
// inside it may take one): the C++ call chain unwinds, control comes back to the wrap at once with the guest
// thread parked INSIDE the original, and the thread later resumes there without passing through the wrap
// again. An "after" read taken on that path reads a half-done call -- v0 is whatever the last callee left, the
// written-back fields are the old ones -- and logs it as the call's result (the OSK wrap's third driven login
// is the case on record: `[ret-unwound] OskActivate pc=0x3766a0`).
//
// The checkpoint that tells the two apart is the pc the original leaves in the context: a whole call leaves
// it on the return address the wrap was entered with (the generated `jr ra` sets pc = ra and returns); an
// unwound one leaves it inside the callee, and the runtime's unwind flag set. So every wrap takes `entryRa`
// before the call, reads its after
// values only when reachedReturn() says so, and otherwise writes a row that says the call unwound instead of
// numbers that are not the call's. The same test guards any after-WRITE (PS2X_CULL_PARTIAL_CLIP's v0 rewrite):
// on the unwound path v0 is not the result yet, so it is left alone.
#pragma once

#include <atomic>
#include <cstdint>

namespace socom2_trace
{
    // True when the original ran to its own return: the only point at which its effects are final. Two tests,
    // both needed: the pc must be back on the entry ra, AND the runtime must not be unwinding
    // (PS2Runtime::dispatchUnwinding(), passed in so this header needs no runtime). The pc alone cannot tell a
    // recursive callee that unwound at a pc equal to the ra from a real return -- the runtime's own
    // dispatchGuestBranch checks the flag first for exactly that case (ps2_runtime.h, markDispatchUnwind).
    inline bool reachedReturn(uint32_t pcAfterCall, uint32_t entryRa, bool dispatchUnwinding)
    {
        return !dispatchUnwinding && pcAfterCall == entryRa;
    }

    // What a trace prints in place of its after-values when the call unwound, so a reader counts the call
    // and knows its row has no result -- never a number from the middle of the call.
    constexpr const char *kUnwoundMark = "unwound";

    // A per-wrap count of unwound calls: the first one is worth a line, the rest a running total.
    struct UnwoundCount
    {
        std::atomic<uint32_t> n{0};

        // True on the first unwound call only.
        bool note()
        {
            return n.fetch_add(1) == 0u;
        }
    };
}
