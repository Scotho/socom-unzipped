#pragma once

#include <atomic>
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
// recorded but not yet replayed. The cap bounds how long the consumer may make NO progress
// (ruling R40): the consumer bumps a heartbeat (consumerProgress) while it executes, so a live GL
// thread replaying a big batch keeps the recorder waiting past the cap. Only a consumer silent for
// the whole cap (window drag in the modal pump, hang, exit) latches "consumer stalled": frames then
// do not wait, and the latch clears on the next heartbeat or completed replay. So a stuck GL
// thread costs one cap, not one cap per frame. release() ends all waiting for good (shutdown).
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
        TimedOut,  // over the bound; no consumer progress for a whole cap (latches the stalled state)
        Skipped,   // over the bound, but the consumer is latched stalled: no wait
    };

    struct Stats
    {
        uint64_t frames = 0;   // frameRecorded calls
        uint64_t waits = 0;    // Waited results
        uint64_t timeouts = 0; // TimedOut results (= latches taken)
        uint64_t unlatched = 0; // latches cleared (heartbeat or replay after a latch)
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
    // Consumer: a heartbeat while it executes (lock-free; call per command chunk). Extends a
    // producer's wait past the cap and clears a stalled latch.
    void consumerProgress() { m_progress.fetch_add(1u, std::memory_order_relaxed); }
    // Consumer: every frame up to `recordedCount` (a recordedFrames() value) has been replayed.
    void framesReplayed(uint64_t recordedCount);

    // Shutdown: wake any waiter; no frame waits again.
    void release();

    uint64_t pendingFrames() const;
    // Consumer latched stalled (Sprint 7 Task 1b reads it to bound the pending BYTES too).
    bool latched() const;
    uint32_t waiters() const; // producers currently inside the wait (tests)
    Stats takeStats(); // returns and clears the counters
    // Cumulative time spent inside Waited/TimedOut waits, in nanoseconds, NEVER cleared. Stats::waitMs is only
    // reachable through takeStats(), which clears and belongs to the 60-present [gs-gl stats] printer; the
    // pc-sampler reads this instead so the two instruments do not race each other (research/29 section 4 item 7).
    uint64_t waitNsTotal() const { return m_waitNsTotal.load(std::memory_order_relaxed); }

private:
    mutable std::mutex m_mutex;
    std::condition_variable m_cv;
    uint32_t m_maxPendingFrames;
    std::chrono::milliseconds m_waitCap;
    uint64_t m_recorded = 0;
    uint64_t m_replayed = 0;
    bool m_consumerStalled = false;
    uint64_t m_progressAtLatch = 0;
    uint32_t m_waiters = 0;
    std::atomic<uint64_t> m_progress{0};
    std::atomic<uint64_t> m_waitNsTotal{0};
    bool m_released = false;
    Stats m_stats{};
};

// Sprint 7 Task 1b (audit 2026-09-17 section 2.2 F3, gap G7): the byte side of the same queue.
// GsFrameBackpressure bounds how many guest FRAMES may be recorded ahead of the replay, but once
// the consumer latches stalled (a title-bar drag holds the GL thread in the modal size-move loop
// for as long as the mouse is down) frames stop waiting and the pending command buffer grows for
// the whole drag: KNOWN section 4's ~15 GB working set. GsPendingCap bounds it in bytes instead.
//
// Policy: while the consumer is latched, a command that carries no state (draw work: it will be
// re-submitted next guest frame) is dropped once the pending bytes reach the cap; a command that
// carries state (an upload, a transfer, a CLUT load, a VRAM write, anything the replay cannot
// reconstruct) is always admitted, so no drag can corrupt what the game draws after it. Nothing is
// ever dropped while the consumer is live. capBytes == 0 is unbounded (the pre-1b behaviour);
// PS2X_GS_PENDING_CAP_MB sets it, default 64 MB.
//
// The counters are atomic: admit() runs on the recorder's thread (under the queue lock) and the
// stats line reads them on the render thread.
class GsPendingCap
{
public:
    static constexpr uint64_t kDefaultCapMb = 64u;

    explicit GsPendingCap(uint64_t capBytes);

    // Returns false when the command must be dropped: only ever when the consumer is latched, the
    // command carries no state, and the pending bytes are already at the cap.
    bool admit(bool latched, bool carriesState, uint64_t bytes);
    // The replay took `bytes` of the pending buffer (call it with the buffer's size at the swap).
    void onReplayed(uint64_t bytes);

    uint64_t bytes() const;    // pending, as accounted by admit()/onReplayed()
    uint64_t capBytes() const; // 0 = unbounded
    uint64_t droppedCommands() const;
    uint64_t droppedBytes() const;

    // nullptr (unset) or an unparsable value -> fallbackMb; "0" -> 0 (unbounded); "<n>" -> n.
    static uint64_t parseCapMb(const char *value, uint64_t fallbackMb = kDefaultCapMb);

private:
    uint64_t m_capBytes;
    std::atomic<uint64_t> m_bytes{0};
    std::atomic<uint64_t> m_droppedCommands{0};
    std::atomic<uint64_t> m_droppedBytes{0};
};
