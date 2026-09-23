// Sprint 11 audio-out (2026-09-23): the per-callback trace that says whether a 50 ms hole at the endpoint was a
// callback the device thread serviced late. Pure: synthetic timestamps in, counts and CSV out; no device.
// Fix round 1 (I1, I2): three thresholds -- jittered, late (the early warning), dry (silence reached the endpoint)
// -- with the silence estimate tied to the WHOLE buffer, and a status line the flusher can write every pass.
#include "MiniTest.h"
#include "runtime/audio_cb_trace.h"
#include "runtime/mix_device.h"

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
    });
}
