#include "MiniTest.h"
#include "runtime/gs/gs_frame_backpressure.h"
#include "runtime/socom2_freeze_fields.h"
#include "runtime/gs/gs_frontend.h"
#include "runtime/gs/gs_cpu_backend.h"
#include "runtime/ee_scheduler.h"
#include "ps2_runtime.h"
#include "ps2_stubs.h"
#include "ps2_syscalls.h"
#include "Stubs/Helpers/Support.h"
#include "Stubs/GS.h"

#include <algorithm>
#include <cstdio>
#include <atomic>
#include <chrono>
#include <memory>
#include <string>
#include <thread>
#include <vector>

namespace
{
    using bp_clock = std::chrono::steady_clock;

    // A CPU backend whose recorder hook stalls once for 600 ms (a stand-in for GSGlBackend's
    // back-pressure wait, or for any other executor stall such as a level load when it reports no
    // wait), optionally followed on the next VBlank by a short reported wait, so the scheduler's R41
    // re-anchor can be observed.
    constexpr uint32_t kBpStallAt = 20u;
    constexpr size_t kBpWakes = 75u;
    constexpr uint32_t kBpVSyncLoopPc = 0x0011F200u;
    std::vector<bp_clock::time_point> g_bpWakes;
    std::vector<uint64_t> g_bpWakeTicks;
    std::vector<uint64_t> g_bpWakeIdleWaits;

    void bpSetRegU32(R5900Context &ctx, int reg, uint32_t value)
    {
        ctx.r[reg] = _mm_set_epi64x(0, static_cast<int64_t>(value));
    }

    class StallingFrameBackend final : public GSRasterBackend
    {
    public:
        StallingFrameBackend(bool stallReportsWait, bool followupWait)
            : m_stallReportsWait(stallReportsWait), m_followupWait(followupWait)
        {
        }
        uint32_t calls = 0u;
        bp_clock::time_point stallEnd{};
        void Initialize(uint8_t *vram, uint32_t vramSize) override { m_cpu.Initialize(vram, vramSize); }
        void Reset() override { m_cpu.Reset(); }
        void Submit(const GSPrimitiveBatch &batch) override { m_cpu.Submit(batch); }
        void BeginTransfer(const GSTransferCommand &command) override { m_cpu.BeginTransfer(command); }
        void UploadImage(const uint8_t *data, uint32_t sizeBytes) override { m_cpu.UploadImage(data, sizeBytes); }
        void Flush() override { m_cpu.Flush(); }
        void TextureFlush() override { m_cpu.TextureFlush(); }
        void Sync(GSSyncReason reason) override { m_cpu.Sync(reason); }
        PresentationFrame Present(const GSPresentationRequest &request) override { return m_cpu.Present(request); }
        bool ClearFramebuffer(const GSContext &context, uint32_t rgba) override { return m_cpu.ClearFramebuffer(context, rgba); }
        uint32_t ConsumeLocalToHostBytes(uint8_t *dst, uint32_t maxBytes) override { return m_cpu.ConsumeLocalToHostBytes(dst, maxBytes); }
        uint32_t ReadVram(uint32_t psm, uint32_t base, uint32_t bw, uint32_t x, uint32_t y) const override { return m_cpu.ReadVram(psm, base, bw, x, y); }
        void WriteVram(uint32_t psm, uint32_t base, uint32_t bw, uint32_t x, uint32_t y, uint32_t value) override { m_cpu.WriteVram(psm, base, bw, x, y, value); }
        void SnapshotVram(std::vector<uint8_t> &out) const override { m_cpu.SnapshotVram(out); }
        GSTransferSnapshot GetTransferSnapshot() const override { return m_cpu.GetTransferSnapshot(); }
        bool GuestFrameBoundary() override
        {
            ++calls;
            if (calls == kBpStallAt)
            {
                std::this_thread::sleep_for(std::chrono::milliseconds(600));
                stallEnd = bp_clock::now();
                return m_stallReportsWait;
            }
            if (calls == kBpStallAt + 1u && m_followupWait)
            {
                std::this_thread::sleep_for(std::chrono::milliseconds(10));
                stallEnd = bp_clock::now();
                return true;
            }
            return false;
        }

    private:
        GSCpuBackend m_cpu;
        bool m_stallReportsWait;
        bool m_followupWait;
    };

    // Guest loop: note the host time of each return from sceGsSyncV, then wait for the next VBlank.
    void bpVSyncLoop(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        g_bpWakes.push_back(bp_clock::now());
        g_bpWakeTicks.push_back(runtime->eeScheduler().currentVSyncTick());
        g_bpWakeIdleWaits.push_back(runtime->eeScheduler().idleWaitCount());
        if (g_bpWakes.size() >= kBpWakes)
        {
            ctx->pc = 0u;
            runtime->requestStop();
            return;
        }
        ctx->pc = kBpVSyncLoopPc;
        ps2_stubs::sceGsSyncV(rdram, ctx, runtime);
    }

    // Runs the guest VBlank loop against a StallingFrameBackend and checks that after the stall
    // (and the optional reported wait) the guest wakes on every VBlank at real time.
    void runVBlankStallScenario(TestCase &t, bool stallReportsWait, bool followupWait)
    {
        PS2Runtime runtime;
        t.IsTrue(runtime.memory().initialize(), "runtime memory initialize should succeed");
        std::vector<uint8_t> rdram(PS2_RAM_SIZE, 0u);
        R5900Context resetCtx{};
        bpSetRegU32(resetCtx, 4, 0u);
        bpSetRegU32(resetCtx, 5, 1u);
        bpSetRegU32(resetCtx, 6, 2u);
        bpSetRegU32(resetCtx, 7, 1u);
        ps2_stubs::sceGsResetGraph(rdram.data(), &resetCtx, &runtime);
        auto backend = std::make_unique<StallingFrameBackend>(stallReportsWait, followupWait);
        StallingFrameBackend *stalling = backend.get();
        runtime.gs().setRasterBackend(std::move(backend));
        g_bpWakes.clear();
        g_bpWakeTicks.clear();
        g_bpWakeIdleWaits.clear();
        runtime.registerFunction(kBpVSyncLoopPc, bpVSyncLoop);
        R5900Context mainContext{};
        mainContext.pc = kBpVSyncLoopPc;
        runtime.eeScheduler().reset(rdram.data(), mainContext);
        runtime.eeScheduler().run();

        t.IsTrue(stalling->calls >= kBpStallAt + 20u, "the hook must run once per VBlank, calls=" + std::to_string(stalling->calls));
        t.Equals(g_bpWakes.size(), kBpWakes, "the guest loop ran to its end");
        if (g_bpWakes.size() != kBpWakes || stalling->stallEnd == bp_clock::time_point{})
            return;
        size_t first = 0;
        while (first < g_bpWakes.size() && g_bpWakes[first] < stalling->stallEnd)
            ++first;
        t.IsTrue(first > 0 && first + 21 <= g_bpWakes.size(), "enough wakes before and after the stall");
        if (first == 0 || first + 21 > g_bpWakes.size())
            return;
        // Every VBlank after the stall reaches the guest. A host hiccup in a loaded test run can
        // legitimately merge two VBlanks, so the loose bound is 2 per wake; right after the
        // re-anchor (R54, Minor 2) there must be exactly one: the re-anchored VBlank is a full
        // period away on both clocks, not already due.
        //
        // Sprint 8, the Linux port: a wake is only as prompt as the host's scheduler gives it, and on
        // a VM sharing its cores (or under ASan) a wake lands tens of ms late and then carries every
        // VBlank whose host period has already passed -- 3 to 6 of them, where an idle host sees 1.
        // The same binary passes on a quiet VM and on Windows, so the bound below is per wake and is
        // paid for in host time: one VBlank, plus one for each further period (with a quarter period
        // of grace) that the wake itself was late by. The defect these two lines guard -- the
        // re-anchored VBlank already due, delivered back to back with the next one -- costs no host
        // time at all and still fails here. Wake 0's lateness is measured from the end of the stall,
        // not from the wake before it: the stall itself is the excluded time the re-anchor drops.
        auto ticksAllowed = [&](size_t k)
        {
            const auto since = (k == first && g_bpWakes[k - 1] < stalling->stallEnd) ? stalling->stallEnd : g_bpWakes[k - 1];
            const double lateMs = std::chrono::duration<double, std::milli>(g_bpWakes[k] - since).count();
            return 1u + static_cast<uint64_t>(lateMs / (16.667 * 1.25));
        };
        uint64_t maxTicksPerWake = 0u;
        bool everyWakeWithinItsHostTime = true;
        for (size_t k = first; k < first + 20; ++k)
        {
            const uint64_t wakeTicks = g_bpWakeTicks[k + 1] - g_bpWakeTicks[k];
            maxTicksPerWake = std::max<uint64_t>(maxTicksPerWake, wakeTicks);
            if (wakeTicks > std::max<uint64_t>(2u, ticksAllowed(k + 1)))
                everyWakeWithinItsHostTime = false;
        }
        t.IsTrue(everyWakeWithinItsHostTime, "after the stall the guest must wake on every VBlank (no VBlank before its host period), saw up to " + std::to_string(maxTicksPerWake) + " VBlanks per wake");
        for (size_t k = first; k <= first + 1; ++k)
        {
            const uint64_t wakeTicks = g_bpWakeTicks[k] - g_bpWakeTicks[k - 1];
            const uint64_t allowed = ticksAllowed(k);
            t.IsTrue(wakeTicks <= allowed, "the wakes right after the re-anchor must each see one VBlank per host period (no immediate second VBlank), wake " + std::to_string(k - first) + " saw " + std::to_string(wakeTicks) + " in " + std::to_string(allowed) + " periods of host time");
        }

        // R54: an idle guest sleeps between VBlanks after a wait. When the host deadline was ahead of
        // the cycle deadline, waitForEvent returned at once and re-entered until the cycle clock caught
        // up (a spin of thousands of idle waits per frame); a sleeping guest needs a handful.
        uint64_t maxIdleWaitsPerWake = 0u;
        for (size_t k = first + 1; k < first + 20; ++k)
            maxIdleWaitsPerWake = std::max<uint64_t>(maxIdleWaitsPerWake, g_bpWakeIdleWaits[k + 1] - g_bpWakeIdleWaits[k]);
        t.IsTrue(maxIdleWaitsPerWake <= 20u, "an idle frame after the stall must not busy-loop, saw up to " + std::to_string(maxIdleWaitsPerWake) + " idle waits per frame");

        // The VBlank rate is unchanged: real time, neither repaying debt nor oversleeping.
        const double spanMs = std::chrono::duration<double, std::milli>(g_bpWakes[first + 20] - g_bpWakes[first]).count();
        const uint64_t ticks = g_bpWakeTicks[first + 20] - g_bpWakeTicks[first];
        const double rate = ticks * 1000.0 / std::max(1.0, spanMs);
        t.IsTrue(rate < 75.0 && rate > 45.0, "after the stall VBlanks run at real time (~60/s), were " + std::to_string(rate) + "/s");
        t.IsTrue(spanMs < 1000.0, "20 wakes after the stall take about 333 ms, took " + std::to_string(spanMs) + " ms");
    }
}

// Sprint 5 rulings R35/R40/R41: the GS command queue between the EE executor (records) and the GL
// thread (replays) is bounded in frames recorded but not yet replayed, with a wait capped on consumer
// silence, and the time spent waiting is dropped from the VBlank deadline chain.
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

        tc.Run("R40: a slow big-batch consumer that keeps making progress keeps the producer bounded, with no latch", [msSince](TestCase &t)
        {
            // Each replay batch takes 4x the cap, but the consumer heartbeats every 10 ms.
            GsFrameBackpressure bp(3u, ms(100));
            const uint64_t kFrames = 24u;
            std::atomic<bool> producerDone{false};
            uint64_t maxPendingAfterRecord = 0u;
            uint64_t notWaitedOverBound = 0u;
            std::thread producer([&]
            {
                for (uint64_t i = 0; i < kFrames; ++i)
                {
                    const auto r = bp.frameRecorded();
                    if (r == GsFrameBackpressure::WaitResult::TimedOut || r == GsFrameBackpressure::WaitResult::Skipped)
                        ++notWaitedOverBound;
                    maxPendingAfterRecord = std::max(maxPendingAfterRecord, bp.pendingFrames());
                }
                producerDone.store(true);
            });
            std::thread consumer([&]
            {
                while (!producerDone.load() || bp.pendingFrames() != 0u)
                {
                    const uint64_t taken = bp.recordedFrames();
                    const auto t0 = clock::now();
                    while (msSince(t0) < 400)
                    {
                        bp.consumerProgress();
                        std::this_thread::sleep_for(ms(10));
                    }
                    bp.framesReplayed(taken);
                }
            });
            producer.join();
            consumer.join();
            const GsFrameBackpressure::Stats stats = bp.takeStats();
            t.Equals(notWaitedOverBound, uint64_t{0}, "a progressing consumer must never time out or be skipped");
            t.Equals(stats.timeouts, uint64_t{0}, "no latch while the consumer makes progress");
            t.IsTrue(maxPendingAfterRecord <= 3u, "pending frames must stay <= N=3, was " + std::to_string(maxPendingAfterRecord));
        });

        tc.Run("R40: a consumer that progresses then stops latches one cap after its last heartbeat", [msSince](TestCase &t)
        {
            GsFrameBackpressure bp(1u, ms(150));
            bp.frameRecorded();
            std::thread consumer([&]
            {
                const auto t0 = clock::now();
                while (msSince(t0) < 400)
                {
                    bp.consumerProgress();
                    std::this_thread::sleep_for(ms(10));
                }
            });
            const auto t0 = clock::now();
            const auto r = bp.frameRecorded();
            const long long took = msSince(t0);
            consumer.join();
            t.IsTrue(r == GsFrameBackpressure::WaitResult::TimedOut, "a consumer silent for the whole cap latches");
            t.IsTrue(took >= 450 && took < 2000, "the latch comes a cap after the last heartbeat (~550 ms), took " + std::to_string(took) + " ms");
        });

        tc.Run("R40: a heartbeat clears the latch before any replay completes", [msSince](TestCase &t)
        {
            GsFrameBackpressure bp(1u, ms(100));
            bp.frameRecorded();
            t.IsTrue(bp.frameRecorded() == GsFrameBackpressure::WaitResult::TimedOut, "no consumer: latch");
            t.IsTrue(bp.frameRecorded() == GsFrameBackpressure::WaitResult::Skipped, "latched: skipped");
            bp.consumerProgress();
            const auto t0 = clock::now();
            const auto r = bp.frameRecorded();
            t.IsTrue(r != GsFrameBackpressure::WaitResult::Skipped, "a heartbeat after the latch must re-arm the wait");
            t.IsTrue(msSince(t0) >= 80, "the re-armed frame waits again for a cap");
            t.IsTrue(bp.takeStats().unlatched >= 1u, "the unlatch is counted");
        });

        tc.Run("release wakes a blocked producer at once and ends waiting (shutdown)", [msSince](TestCase &t)
        {
            GsFrameBackpressure bp(1u, ms(10000));
            bp.frameRecorded();
            GsFrameBackpressure::WaitResult result = GsFrameBackpressure::WaitResult::NotNeeded;
            long long elapsed = 0;
            std::thread producer([&]
            {
                const auto t0 = clock::now();
                result = bp.frameRecorded();
                elapsed = msSince(t0);
            });
            // Release only once the producer is inside the wait (no sleep-and-hope).
            const auto pollStart = clock::now();
            while (bp.waiters() == 0u && msSince(pollStart) < 5000)
                std::this_thread::yield();
            t.Equals(bp.waiters(), uint32_t{1}, "the producer must be inside the wait before release");
            bp.release();
            producer.join();
            t.IsTrue(elapsed < 2000, "the producer woke on release (not the 10 s cap), took " + std::to_string(elapsed) + " ms");
            t.IsTrue(result == GsFrameBackpressure::WaitResult::Waited, "a released wait reports Waited, not TimedOut");
            const auto t0 = clock::now();
            t.IsTrue(bp.frameRecorded() == GsFrameBackpressure::WaitResult::NotNeeded, "after release no frame waits");
            t.IsTrue(msSince(t0) < 50, "after release frameRecorded returns at once");
        });

        tc.Run("R41/R54: reanchorVBlankDeadline drops deadline debt but never moves a future deadline", [](TestCase &t)
        {
            const auto now = clock::now();
            const auto period = std::chrono::microseconds(16667);
            const auto past = now - std::chrono::seconds(30);
            t.IsTrue(EeScheduler::reanchorVBlankDeadline(past, now) == now, "a deadline 30 s behind is re-anchored to now");
            t.IsTrue(EeScheduler::reanchorVBlankDeadline(past, now) + period > now, "so the next VBlank is a full period away, not due at once");
            const auto recent = now - std::chrono::microseconds(5000);
            t.IsTrue(EeScheduler::reanchorVBlankDeadline(recent, now) == now, "a deadline a few ms behind is re-anchored to now too (R54)");
            const auto future = now + std::chrono::milliseconds(10);
            t.IsTrue(EeScheduler::reanchorVBlankDeadline(future, now) == future, "a future deadline is unchanged");
        });

        tc.Run("R41: after a long back-pressure wait the scheduler does not fire the missed VBlanks back to back", [](TestCase &t)
        {
            // 600 ms (~36 periods) spent in the wait. Without the re-anchor the missed VBlanks fire
            // back to back once it ends (~172/s until repaid). Re-anchoring the host deadline alone
            // left the wait on the guest cycle clock, so ~36 VBlanks stayed cycle-due and
            // processDueDeadlines paced through them one host period apart without returning to the
            // guest, re-accruing the debt every round: the guest woke once per ~36 VBlanks, forever.
            runVBlankStallScenario(t, true, false);
        });

        tc.Run("R41: a short wait after an unrelated executor stall (level load) re-anchors both clocks", [](TestCase &t)
        {
            // The 600 ms stall is not a back-pressure wait, so it is ordinary guest time and debt on
            // both clocks; the 10 ms wait on the next VBlank then re-anchors. Re-anchoring only the
            // host deadline there left the whole load stall as cycle debt: the same pacing lock-up
            // (the s5_gsbp2 and s5_gsbp2b mission hang right after the intro movie).
            runVBlankStallScenario(t, false, true);
        });

        tc.Run("PS2X_GS_MAX_PENDING_FRAMES=0 restores unbounded behaviour", [msSince](TestCase &t)
        {
            t.Equals(GsFrameBackpressure::parseMaxPendingFrames(nullptr), uint32_t{3}, "unset -> default N=3");
            t.Equals(GsFrameBackpressure::parseMaxPendingFrames("0"), uint32_t{0}, "'0' -> 0 (unbounded)");
            t.Equals(GsFrameBackpressure::parseMaxPendingFrames("2"), uint32_t{2}, "'2' -> 2");
            t.Equals(GsFrameBackpressure::parseMaxPendingFrames(""), uint32_t{3}, "empty -> default");
            t.Equals(GsFrameBackpressure::parseMaxPendingFrames("abc"), uint32_t{3}, "garbage -> default");
            t.Equals(GsFrameBackpressure::parseMaxPendingFrames("-1"), uint32_t{3}, "negative -> default");
            t.Equals(GsFrameBackpressure::parseMaxPendingFrames("70000"), uint32_t{3}, "above 65535 -> default (logged once)");
            t.Equals(GsFrameBackpressure::parseMaxPendingFrames("65535"), uint32_t{65535}, "65535 is accepted");

            GsFrameBackpressure bp(GsFrameBackpressure::parseMaxPendingFrames("0"), ms(200));
            const auto t0 = clock::now();
            bool anyWait = false;
            for (int i = 0; i < 1000; ++i)
                anyWait = (bp.frameRecorded() != GsFrameBackpressure::WaitResult::NotNeeded) || anyWait;
            t.IsFalse(anyWait, "unbounded: no frame ever waits");
            t.Equals(bp.pendingFrames(), uint64_t{1000}, "unbounded: 1000 frames pend with no consumer");
            t.IsTrue(msSince(t0) < 150, "unbounded: 1000 frames record without blocking");
        });

        tc.Run("a latched queue drops guest frames and keeps uploads", [](TestCase &t)
        {
            GsPendingCap cap(1024u);            // 1 KiB, so the cap is reachable in a test
            uint64_t admittedDraws = 0, admittedUploads = 0;
            for (int frame = 0; frame < 200; ++frame)
            {
                if (cap.admit(true, false, 64u)) ++admittedDraws;      // a guest frame's draw work
                if (cap.admit(true, true, 64u))  ++admittedUploads;    // an upload: state, never dropped
            }
            t.Equals(static_cast<int>(admittedUploads), 200, "every upload is admitted while latched");
            t.IsTrue(cap.bytes() <= 1024u + 200u * 64u, "only uploads may exceed the cap");
            t.IsTrue(admittedDraws < 200u, "draws stop being admitted at the cap (" + std::to_string(admittedDraws) + ")");
            t.IsTrue(cap.droppedCommands() > 0u, "the drops are counted");
            t.Equals(static_cast<int>(cap.droppedBytes()), static_cast<int>((200u - admittedDraws) * 64u), "the dropped bytes are counted");
        });

        tc.Run("an unlatched queue admits everything and the replay releases bytes", [](TestCase &t)
        {
            GsPendingCap cap(1024u);
            for (int i = 0; i < 1000; ++i)
                t.IsTrue(cap.admit(false, false, 64u), "nothing is dropped while the consumer is live");
            t.Equals(static_cast<int>(cap.droppedCommands()), 0, "no drops");
            cap.onReplayed(cap.bytes());
            t.Equals(static_cast<int>(cap.bytes()), 0, "a replay empties the accounting");
        });

        tc.Run("PS2X_GS_PENDING_CAP_MB parses like the frame knob", [](TestCase &t)
        {
            t.Equals(static_cast<int>(GsPendingCap::parseCapMb("128", 64u)), 128, "a decimal is taken");
            t.Equals(static_cast<int>(GsPendingCap::parseCapMb("-1", 64u)), 64, "a negative falls back");
            t.Equals(static_cast<int>(GsPendingCap::parseCapMb(nullptr, 64u)), 64, "unset falls back");
        });

        // Sprint 7 Task 2e (research/29 section 4): the [pc-sampler]'s freeze fields are built by a pure
        // function, so the line's shape is a test rather than a launch (the sampler prints from its own thread).
        tc.Run("the pc-sampler's freeze fields print research/29 section 4's values in order", [](TestCase &t)
        {
            FreezeFields::Sample s;
            s.hostSeconds = 612.5;
            s.vsyncTick = 41233ull;
            s.eeSeconds = 612.1;
            s.sequence = 8891ull;
            s.debugPc = 0x350d90u;
            s.idleWaits = 140ull;
            s.bpPending = 0ull;
            s.bpWaiters = 0u;
            s.bpWaitMs = 12ull;
            s.netWait = 1;
            s.netWaitMs = 3300ull;
            t.Equals(FreezeFields::line(s),
                     std::string(" t=612.50 vsync=41233 ee=612.10 seq=8891 dpc=0x350d90 idle=140"
                                 " bp_pending=0 bp_waiters=0 bp_wait_ms=12 net_wait=1/3300"),
                     "freeze_trace.parse reads exactly this (tools_py/tests/test_freeze_trace.py SAMPLE)");
            FreezeFields::Sample quiet;
            quiet.hostSeconds = 3.0;
            quiet.eeSeconds = 2.5;
            t.Equals(FreezeFields::line(quiet),
                     std::string(" t=3.00 vsync=0 ee=2.50 seq=0 dpc=0x0 idle=0 bp_pending=0 bp_waiters=0"
                                 " bp_wait_ms=0 net_wait=0/0"),
                     "a quiet sample still prints every field: a missing one would read as a parse failure");
        });

        tc.Run("waitNsTotal is cumulative and takeStats() does not clear it (the sampler never races the printer)", [](TestCase &t)
        {
            GsFrameBackpressure bp(1u, ms(60));
            t.Equals(bp.waitNsTotal(), uint64_t{0}, "nothing has waited yet");
            bp.frameRecorded();                                   // frame 1: at the bound
            bp.frameRecorded();                                   // frame 2: over it, waits the cap out
            const uint64_t afterWait = bp.waitNsTotal();
            t.IsTrue(afterWait >= 40000000ull, "the 60 ms cap is counted in ns, was " + std::to_string(afterWait));
            const GsFrameBackpressure::Stats stats = bp.takeStats();
            t.IsTrue(stats.waitMs > 0.0, "the 60-present printer still gets its clearing counter");
            t.Equals(bp.waitNsTotal(), afterWait, "the sampler's counter survives that takeStats()");
            t.IsTrue(bp.takeStats().waitMs == 0.0, "... while the clearing one is back to zero");
        });

        tc.Run("a frontend with no GPU back-pressure reports zero pending frames and zero waiters", [](TestCase &t)
        {
            GS gs;
            t.Equals(gs.pendingGuestFrames(), uint64_t{0}, "the CPU path has no pending guest frames");
            t.Equals(static_cast<int>(gs.backpressureWaiters()), 0, "and nobody inside the wait");
        });
    });
}
