#pragma once

#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <mutex>

// Back-pressure between the thread that records a GPU backend's GS command stream (the EE
// executor, once per guest VBlankStart) and the thread that replays it (the GL/main thread, once
// per host frame). Sprint 5 ruling R35: without it the recorder runs vsync-paced at 60 guest
// frames/s whatever the replay costs, so when replay is slower (SP gameplay, ~14 frames/s) the
// pending command buffer grows without bound (275 MB -> 13 GB in 4 min) and every host frame
// drains a larger backlog (stall-report.md).
//
// Policy: after recording frame k, the recorder waits while more than maxPendingFrames frames are
// recorded but not yet replayed. The wait is capped: a timeout latches "consumer stalled" and no
// further frame waits until the consumer reports progress, so a stuck or exited GL thread costs
// one cap, not one cap per frame. release() ends all waiting for good (shutdown).
// maxPendingFrames == 0 is unbounded (the pre-R35 behaviour); PS2X_GS_MAX_PENDING_FRAMES sets it.
class GsFrameBackpressure
{
public:
    static constexpr uint32_t kDefaultMaxPendingFrames = 3u;
    static constexpr std::chrono::milliseconds kDefaultWaitCap{2000};

    enum class WaitResult
    {
        NotNeeded, // at or under the bound (or unbounded / released): returned at once
        Waited,    // over the bound; the consumer caught up (or release()) within the cap
        TimedOut,  // over the bound; the cap expired (latches the stalled state)
        Skipped,   // over the bound, but the consumer is latched stalled: no wait
    };

    struct Stats
    {
        uint64_t frames = 0;   // frameRecorded calls
        uint64_t waits = 0;    // Waited results
        uint64_t timeouts = 0; // TimedOut results
        uint64_t skipped = 0;  // Skipped results
        double waitMs = 0.0;   // time spent inside Waited and TimedOut waits
    };

    // nullptr (unset) or an unparsable value -> fallback; "0" -> 0 (unbounded); "<n>" -> n.
    static uint32_t parseMaxPendingFrames(const char *value, uint32_t fallback = kDefaultMaxPendingFrames);

    explicit GsFrameBackpressure(uint32_t maxPendingFrames = kDefaultMaxPendingFrames,
                                 std::chrono::milliseconds waitCap = kDefaultWaitCap);

    void setMaxPendingFrames(uint32_t maxPendingFrames);
    uint32_t maxPendingFrames() const;

    // Recorder: one more guest frame's commands are fully recorded. May block (capped).
    WaitResult frameRecorded();

    // Consumer: the number of frames recorded so far. Read it while holding the lock that takes
    // the pending command buffer, so it counts exactly the frames that buffer holds.
    uint64_t recordedFrames() const;
    // Consumer: every frame up to `recordedCount` (a recordedFrames() value) has been replayed.
    void framesReplayed(uint64_t recordedCount);

    // Shutdown: wake any waiter; no frame waits again.
    void release();

    uint64_t pendingFrames() const;
    Stats takeStats(); // returns and clears the counters

private:
    mutable std::mutex m_mutex;
    std::condition_variable m_cv;
    uint32_t m_maxPendingFrames;
    std::chrono::milliseconds m_waitCap;
    uint64_t m_recorded = 0;
    uint64_t m_replayed = 0;
    bool m_consumerStalled = false;
    bool m_released = false;
    Stats m_stats{};
};
