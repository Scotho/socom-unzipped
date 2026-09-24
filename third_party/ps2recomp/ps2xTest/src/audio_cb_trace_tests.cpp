// Sprint 11 audio-out (2026-09-23): the per-callback trace that says whether a 50 ms hole at the endpoint was a
// callback the device thread serviced late. Pure: synthetic timestamps in, counts and CSV out; no device.
// Fix round 1 (I1, I2): three thresholds -- jittered, late (the early warning), dry (silence reached the endpoint)
// -- with the silence estimate tied to the WHOLE buffer, and a status line the flusher can write every pass.
// Fix round 2 (R1): the trace carries its own t0 and reaches the audio thread through a slot, so a callback
// never holds a half-published trace and the device's first callback is the first row.
#include "MiniTest.h"
#include "runtime/audio_cb_trace.h"
#include "runtime/mix_device.h"

#include <chrono>
#include <cstdint>
#include <sstream>
#include <string>
#include <vector>

void register_audio_cb_trace_tests()
{
    MiniTest::Case("AudioCallbackTrace", [](TestCase &tc)
    {
        tc.Run("on-time callbacks are nothing; a 75 ms gap is jittered and late but not dry; a 100 ms gap is dry by 20 ms", [](TestCase &t)
        {
            ps2x::AudioCallbackTrace trace(16, 20000, 4);   // 20 ms x 4: jitter over 30, late over 60, dry over 80 ms
            const int64_t entries[] = {0, 20000, 40000, 115000, 135000, 235000, 255000};
            uint64_t outFrame = 0;
            for (int64_t e : entries)
            {
                outFrame += 960;
                t.IsTrue(trace.record(e, e + 600, 960u, outFrame), "recorded");
            }
            const auto s = trace.stats();
            t.Equals(s.calls, static_cast<uint64_t>(7), "seven callbacks");
            t.Equals(s.jittered, static_cast<uint64_t>(2), "two gaps over 1.5 periods");
            t.Equals(s.late, static_cast<uint64_t>(2), "both over three periods: the engine was one period from dry");
            t.Equals(s.dry, static_cast<uint64_t>(1), "one over the whole 80 ms buffer: the engine ran out");
            t.Equals(s.silenceUs, static_cast<int64_t>(100000 - 80000), "the silence is the gap less the WHOLE buffer, not less one period");
            t.Equals(s.maxGapUs, static_cast<int64_t>(100000), "the longest gap");
            t.Equals(s.maxRenderUs, static_cast<int64_t>(600), "the longest render");
            const std::vector<size_t> late = trace.lateCallbacks();
            t.Equals(late.size(), static_cast<size_t>(2), "two late callbacks listed");
            t.Equals(late[0], static_cast<size_t>(3), "the fourth");
            t.Equals(late[1], static_cast<size_t>(5), "and the sixth");
            t.Equals(trace.at(3).outFrame, static_cast<uint64_t>(4 * 960), "the output-frame clock after the fourth");
        });

        tc.Run("a full trace drops records but keeps every counter running, and the status line says so", [](TestCase &t)
        {
            ps2x::AudioCallbackTrace trace(2, 20000, 4);
            t.IsTrue(trace.record(0, 100, 960u, 960), "first fits");
            t.IsTrue(trace.record(20000, 20100, 960u, 1920), "second fits");
            t.IsTrue(!trace.record(40000, 40100, 960u, 2880), "the third does not");
            t.IsTrue(!trace.record(140000, 140100, 960u, 3840), "nor the fourth, 100 ms late");
            t.Equals(trace.size(), static_cast<size_t>(2), "two records kept");
            t.Equals(trace.dropped(), static_cast<uint64_t>(2), "two dropped");
            const auto s = trace.stats();
            t.Equals(s.calls, static_cast<uint64_t>(4), "but four callbacks counted");
            t.Equals(s.dry, static_cast<uint64_t>(1), "and the dry one past the capacity still counted");
            std::ostringstream status;
            trace.status(status);
            t.Equals(status.str(), std::string("# dropped=2 recorded=2\n"), "the line the flusher appends every pass");
        });

        tc.Run("the CSV carries the header once, then one row per callback with its gap and render time", [](TestCase &t)
        {
            ps2x::AudioCallbackTrace trace(8, 20000, 4);
            trace.record(0, 500, 960u, 960);
            trace.record(20000, 20600, 960u, 1920);
            std::ostringstream first;
            const size_t next = trace.flush(first, 0, true, 1700000000123456LL);
            t.Equals(next, static_cast<size_t>(2), "two rows flushed");
            const std::string text = first.str();
            t.IsTrue(text.rfind("# audio callback trace: t0_epoch_us=1700000000123456 period_us=20000 jitter_us=30000 late_us=60000 dry_us=80000 capacity=8\n", 0) == 0,
                     "the header names t0, the period, the three thresholds and the capacity");
            t.IsTrue(text.find("\nseq,entry_us,exit_us,frames,out_frame,gap_us,render_us\n") != std::string::npos, "the column names");
            t.IsTrue(text.find("\n0,0,500,960,960,0,500\n") != std::string::npos, "the first row: no gap yet");
            t.IsTrue(text.find("\n1,20000,20600,960,1920,20000,600\n") != std::string::npos, "the second row: its gap and render");
            trace.record(45000, 45400, 960u, 2880);
            std::ostringstream more;
            t.Equals(trace.flush(more, next, false, 0), static_cast<size_t>(3), "the next flush starts where the last one stopped");
            t.Equals(more.str(), std::string("2,45000,45400,960,2880,25000,400\n"), "only the new row, no header");
        });

        tc.Run("the thresholds come from the device spec: 20 ms x 4 means jitter over 30, late over 60, dry over 80 ms", [](TestCase &t)
        {
            const ps2x::MixDeviceSpec spec = ps2x::mixDeviceSpec();
            ps2x::AudioCallbackTrace trace(4, static_cast<int64_t>(spec.periodMs) * 1000, spec.periods);
            t.Equals(trace.jitterThresholdUs(), static_cast<int64_t>(30000), "1.5 periods");
            t.Equals(trace.lateThresholdUs(), static_cast<int64_t>(60000), "the buffer less one period: the early warning");
            t.Equals(trace.dryThresholdUs(), static_cast<int64_t>(80000), "the whole buffer: past this the endpoint got silence");
            t.Equals(trace.dryThresholdUs(), static_cast<int64_t>(spec.bufferMs()) * 1000, "and it IS the spec's buffer");
        });

        // Fix round 2, R1: the trace is handed to a LIVE audio thread. Round 1 moved its creation after
        // ma_device_start (so a failed start could not leak the flusher) and set t0 after the pointer was
        // already visible: a data race on the unique_ptr, and a first row stamped against a default clock.
        // The slot is the answer -- the object is complete, t0 and all, before anything can see it.
        tc.Run("a trace carries its own t0: whoever holds one can stamp against it, there is no second step", [](TestCase &t)
        {
            const auto t0 = std::chrono::steady_clock::now();
            ps2x::AudioCallbackTrace trace(8, 20000, 4, t0, 1700000000123456LL);
            t.Equals(trace.stampUs(t0), static_cast<int64_t>(0), "t0 itself is 0 us");
            t.Equals(trace.stampUs(t0 + std::chrono::milliseconds(5)), static_cast<int64_t>(5000), "5 ms after t0");
            t.Equals(trace.t0EpochUs(), static_cast<int64_t>(1700000000123456LL), "and the wall clock of that instant");
            t.IsTrue(trace.t0() == t0, "the clock is the one it was built with");
        });

        tc.Run("the slot publishes a complete trace and nothing before it: the device's first callback is row 0", [](TestCase &t)
        {
            ps2x::AudioCallbackTraceSlot slot;
            t.IsTrue(slot.live() == nullptr, "before it is opened the audio thread gets nothing");
            const auto t0 = std::chrono::steady_clock::now();
            ps2x::AudioCallbackTrace *published = slot.open(8, 20000, 4, t0, 1700000000123456LL);
            t.IsTrue(slot.live() == published, "opened: the callback's acquire load sees it");
            t.IsTrue(slot.live()->t0() == t0, "and it is complete -- a trace is never visible without its t0");

            // The device starts HERE, after the slot is open (openMixerStream's order). Each callback renders one
            // 960-frame period and stamps itself the way mixerRender does: the mixer's frame clock afterwards.
            uint64_t renderedFrames = 0;
            for (int i = 0; i < 6; ++i)
            {
                ps2x::AudioCallbackTrace *tr = slot.live();
                if (tr == nullptr)
                    continue;
                const auto entry = t0 + std::chrono::milliseconds(20 * i);
                renderedFrames += 960;
                tr->record(tr->stampUs(entry), tr->stampUs(entry + std::chrono::microseconds(500)), 960u, renderedFrames);
            }
            t.Equals(slot.get()->size(), static_cast<size_t>(6), "every callback of the device's life is in the trace");
            const ps2x::AudioCallbackRecord &first = slot.get()->at(0);
            t.Equals(first.seq, static_cast<uint64_t>(0), "the first callback is row 0");
            t.Equals(first.entryUs, static_cast<int64_t>(0), "stamped against a t0 that was set before it could run");
            t.Equals(first.outFrame - first.frames, static_cast<uint64_t>(0),
                     "the frame clock BEFORE the first row is 0: no callback ran before the trace existed (the "
                     "2026-09-23 capture's first row was out_frame 5760 -- six callbacks lost)");

            slot.close();
            t.IsTrue(slot.live() == nullptr, "the device is stopped: the audio thread is given nothing more");
            t.IsTrue(slot.get() != nullptr, "but the owner still has it for the last flush and the summary");
            slot.reset();
            t.IsTrue(slot.get() == nullptr && slot.live() == nullptr, "and then it is gone");
        });
    });
}
