#pragma once

// Sprint 7 Task 2e, research/29 section 4: the extra fields the [pc-sampler] line prints so that ONE launch
// separates the two online freeze shapes instead of two.
//
//   shape 1 (thread 1 parked in sceGsSyncV): vsync flat + bp_waiters=1 + bp_wait_ms climbing = the GL thread is
//           starved by host load and the GS back-pressure is doing its job; vsync flat + bp_waiters=0 + idle
//           climbing = the EE executor overslept in waitForEvent, which is a runtime bug.
//   shape 2 (thread 1 "RUNNING" at 0x350d90): seq frozen + dpc frozen + net_wait=1 = no guest instruction ran at
//           all; the main thread is inside the host-blocking libnetb waitReadable poll and the sampled thread
//           table is stale by construction.
//
// The sampler prints from its own thread, so the LINE is what gets tested: this builds it as a pure function of
// the eleven values, and tools_py/parity/freeze_trace.py parses exactly this text
// (tools_py/tests/test_freeze_trace.py SAMPLE carries the same string). Every field is always printed -- an
// omitted one would read downstream as a parse failure, not as "nothing to report".

#include <cstdint>
#include <cstdio>
#include <string>

namespace FreezeFields
{
    struct Sample
    {
        double hostSeconds = 0.0;   // 1. steady_clock since the sampler's epoch: freeze_trace drops the [call] anchors
        uint64_t vsyncTick = 0ull;  // 2. EeScheduler::currentVSyncTick()
        double eeSeconds = 0.0;     // 3. EeKernelSnapshot::eeCycle / kEeClockHz (the guest clock)
        uint64_t sequence = 0ull;   // 3. EeKernelSnapshot::sequence: a repeat marks the thread table stale
        uint32_t debugPc = 0u;      // 4. PS2Runtime::debugPc(): the per-dispatch pc, not the 4096-dispatch copy
        uint64_t idleWaits = 0ull;  // 5. EeScheduler::idleWaitCount()
        uint64_t bpPending = 0ull;  // 6. GsFrameBackpressure::pendingFrames() through the frontend
        uint32_t bpWaiters = 0u;    // 6. GsFrameBackpressure::waiters(): 1 during a shape-1 window is the answer
        uint64_t bpWaitMs = 0ull;   // 7. GsFrameBackpressure::waitNsTotal() in ms, cumulative and non-clearing
        int netWait = 0;            // 8. 1 while inside libnetb's waitReadable/doOpen
        uint64_t netWaitMs = 0ull;  // 8. cumulative ms spent in those waits
    };

    // The fields as they appear on the [pc-sampler] line, leading space included, in research/29 section 4's order.
    inline std::string line(const Sample &s)
    {
        char buffer[256];
        std::snprintf(buffer, sizeof(buffer),
                      " t=%.2f vsync=%llu ee=%.2f seq=%llu dpc=0x%x idle=%llu"
                      " bp_pending=%llu bp_waiters=%u bp_wait_ms=%llu net_wait=%d/%llu",
                      s.hostSeconds, static_cast<unsigned long long>(s.vsyncTick), s.eeSeconds,
                      static_cast<unsigned long long>(s.sequence), static_cast<unsigned>(s.debugPc),
                      static_cast<unsigned long long>(s.idleWaits), static_cast<unsigned long long>(s.bpPending),
                      static_cast<unsigned>(s.bpWaiters), static_cast<unsigned long long>(s.bpWaitMs),
                      s.netWait ? 1 : 0, static_cast<unsigned long long>(s.netWaitMs));
        return std::string(buffer);
    }
}
