#include "MiniTest.h"
#include "runtime/gs/gs_frame_backpressure.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <string>
#include <thread>

// Sprint 5 ruling R35: the GS command queue between the EE executor (records) and the GL thread
// (replays) is bounded in frames recorded but not yet replayed, with a capped wait.
void register_gs_frame_backpressure_tests()
{
    MiniTest::Case("GsFrameBackpressure", [](TestCase &tc)
    {
        using clock = std::chrono::steady_clock;
        using ms = std::chrono::milliseconds;
        auto msSince = [](clock::time_point t0)
        { return static_cast<long long>(std::chrono::duration_cast<ms>(clock::now() - t0).count()); };

        tc.Run("a producer faster than the consumer stays bounded at N pending frames", [](TestCase &t)
        {
            GsFrameBackpressure bp(3u, ms(5000));
            const uint64_t kFrames = 60u;
            std::atomic<bool> producerDone{false};
            uint64_t maxPendingAfterRecord = 0u;
            uint64_t timeouts = 0u;
            std::thread producer([&]
            {
                for (uint64_t i = 0; i < kFrames; ++i)
                {
                    if (bp.frameRecorded() == GsFrameBackpressure::WaitResult::TimedOut)
                        ++timeouts;
                    maxPendingAfterRecord = std::max(maxPendingAfterRecord, bp.pendingFrames());
                }
                producerDone.store(true);
            });
            // The fake consumer takes what is recorded, "replays" it slowly, then reports it.
            std::thread consumer([&]
            {
                while (!producerDone.load() || bp.pendingFrames() != 0u)
                {
                    const uint64_t taken = bp.recordedFrames();
                    std::this_thread::sleep_for(ms(15));
                    bp.framesReplayed(taken);
                }
            });
            producer.join();
            consumer.join();
            const GsFrameBackpressure::Stats stats = bp.takeStats();
            t.IsTrue(maxPendingAfterRecord <= 3u, "pending frames seen by the producer must stay <= N=3, was " + std::to_string(maxPendingAfterRecord));
            t.Equals(timeouts, uint64_t{0}, "a live consumer must never hit the cap");
            t.Equals(bp.recordedFrames(), kFrames, "every frame is recorded");
            t.IsTrue(stats.waits > 0u, "the producer must actually have waited");
        });

        tc.Run("the wait times out when the consumer stops, then does not wait again until progress", [msSince](TestCase &t)
        {
            GsFrameBackpressure bp(2u, ms(100));
            t.IsTrue(bp.frameRecorded() == GsFrameBackpressure::WaitResult::NotNeeded, "frame 1 is under the bound");
            t.IsTrue(bp.frameRecorded() == GsFrameBackpressure::WaitResult::NotNeeded, "frame 2 is at the bound");
            auto t0 = clock::now();
            const auto third = bp.frameRecorded();
            const long long waited = msSince(t0);
            t.IsTrue(third == GsFrameBackpressure::WaitResult::TimedOut, "frame 3 is over the bound with no consumer: TimedOut");
            t.IsTrue(waited >= 80 && waited < 1500, "the timed-out wait honours the 100 ms cap, took " + std::to_string(waited) + " ms");
            t0 = clock::now();
            const auto fourth = bp.frameRecorded();
            const long long skippedMs = msSince(t0);
            t.IsTrue(fourth == GsFrameBackpressure::WaitResult::Skipped, "a latched-stalled consumer is not waited on again");
            t.IsTrue(skippedMs < 50, "the skipped frame returns at once, took " + std::to_string(skippedMs) + " ms");
            bp.framesReplayed(bp.recordedFrames());
            t.IsTrue(bp.frameRecorded() == GsFrameBackpressure::WaitResult::NotNeeded, "progress clears the latch");
            bp.frameRecorded();
            t0 = clock::now();
            t.IsTrue(bp.frameRecorded() == GsFrameBackpressure::WaitResult::TimedOut, "after progress an over-bound frame waits again");
            const long long again = msSince(t0);
            t.IsTrue(again >= 80, "the second wait honours the cap again, took " + std::to_string(again) + " ms");
        });

        tc.Run("release wakes a blocked producer at once and ends waiting (shutdown)", [msSince](TestCase &t)
        {
            GsFrameBackpressure bp(1u, ms(10000));
            bp.frameRecorded();
            GsFrameBackpressure::WaitResult result = GsFrameBackpressure::WaitResult::NotNeeded;
            long long elapsed = 0;
            std::atomic<bool> started{false};
            std::thread producer([&]
            {
                started.store(true);
                const auto t0 = clock::now();
                result = bp.frameRecorded();
                elapsed = msSince(t0);
            });
            while (!started.load())
                std::this_thread::yield();
            std::this_thread::sleep_for(ms(100));
            bp.release();
            producer.join();
            t.IsTrue(elapsed >= 50 && elapsed < 2000, "the producer blocked, then woke on release (not the 10 s cap), took " + std::to_string(elapsed) + " ms");
            t.IsTrue(result == GsFrameBackpressure::WaitResult::Waited, "a released wait reports Waited, not TimedOut");
            const auto t0 = clock::now();
            t.IsTrue(bp.frameRecorded() == GsFrameBackpressure::WaitResult::NotNeeded, "after release no frame waits");
            t.IsTrue(msSince(t0) < 50, "after release frameRecorded returns at once");
        });

        tc.Run("PS2X_GS_MAX_PENDING_FRAMES=0 restores unbounded behaviour", [msSince](TestCase &t)
        {
            t.Equals(GsFrameBackpressure::parseMaxPendingFrames(nullptr), uint32_t{3}, "unset -> default N=3");
            t.Equals(GsFrameBackpressure::parseMaxPendingFrames("0"), uint32_t{0}, "'0' -> 0 (unbounded)");
            t.Equals(GsFrameBackpressure::parseMaxPendingFrames("2"), uint32_t{2}, "'2' -> 2");
            t.Equals(GsFrameBackpressure::parseMaxPendingFrames(""), uint32_t{3}, "empty -> default");
            t.Equals(GsFrameBackpressure::parseMaxPendingFrames("abc"), uint32_t{3}, "garbage -> default");
            t.Equals(GsFrameBackpressure::parseMaxPendingFrames("-1"), uint32_t{3}, "negative -> default");

            GsFrameBackpressure bp(GsFrameBackpressure::parseMaxPendingFrames("0"), ms(200));
            const auto t0 = clock::now();
            bool anyWait = false;
            for (int i = 0; i < 1000; ++i)
                anyWait = (bp.frameRecorded() != GsFrameBackpressure::WaitResult::NotNeeded) || anyWait;
            t.IsFalse(anyWait, "unbounded: no frame ever waits");
            t.Equals(bp.pendingFrames(), uint64_t{1000}, "unbounded: 1000 frames pend with no consumer");
            t.IsTrue(msSince(t0) < 150, "unbounded: 1000 frames record without blocking");
        });
    });
}
