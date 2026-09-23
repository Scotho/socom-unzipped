// Sprint 11 audio-out (2026-09-23): the per-callback trace that says whether a 50 ms hole at the endpoint was a
// callback the device thread serviced late. Pure: synthetic timestamps in, counts and CSV out; no device.
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
        tc.Run("on-time callbacks are neither jitter nor holes; a gap past the buffer is a hole whose silence is the gap minus one period", [](TestCase &t)
        {
            ps2x::AudioCallbackTrace trace(16, 20000, 4);   // 20 ms x 4: jitter over 30 ms, a hole over 60 ms
            const int64_t entries[] = {0, 20000, 40000, 115000, 135000};   // the fourth arrives 75 ms after the third
            uint64_t outFrame = 0;
            for (int64_t e : entries)
            {
                outFrame += 960;
                t.IsTrue(trace.record(e, e + 600, 960u, outFrame), "recorded");
            }
            const auto s = trace.stats();
            t.Equals(s.calls, static_cast<uint64_t>(5), "five callbacks");
            t.Equals(s.jittered, static_cast<uint64_t>(1), "one gap over 1.5 periods");
            t.Equals(s.holes, static_cast<uint64_t>(1), "one gap over three periods: the buffer ran dry");
            t.Equals(s.holeUsSum, static_cast<int64_t>(75000 - 20000), "the hole's silence: the gap less the period it was due at");
            t.Equals(s.maxGapUs, static_cast<int64_t>(75000), "the longest gap");
            t.Equals(s.maxRenderUs, static_cast<int64_t>(600), "the longest render");
            const std::vector<size_t> holes = trace.holes();
            t.Equals(holes.size(), static_cast<size_t>(1), "one hole listed");
            t.Equals(holes[0], static_cast<size_t>(3), "at the fourth callback");
            t.Equals(trace.at(3).outFrame, static_cast<uint64_t>(4 * 960), "the output-frame clock after that callback");
        });

        tc.Run("a full trace drops records but keeps counting", [](TestCase &t)
        {
            ps2x::AudioCallbackTrace trace(2, 20000, 4);
            t.IsTrue(trace.record(0, 100, 960u, 960), "first fits");
            t.IsTrue(trace.record(20000, 20100, 960u, 1920), "second fits");
            t.IsTrue(!trace.record(40000, 40100, 960u, 2880), "the third does not");
            t.Equals(trace.size(), static_cast<size_t>(2), "two records kept");
            t.Equals(trace.dropped(), static_cast<uint64_t>(1), "one dropped");
            t.Equals(trace.stats().calls, static_cast<uint64_t>(3), "but three callbacks counted");
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
            t.IsTrue(text.rfind("# audio callback trace: t0_epoch_us=1700000000123456 period_us=20000 jitter_us=30000 hole_us=60000 capacity=8\n", 0) == 0,
                     "the header names t0, the period, both thresholds and the capacity");
            t.IsTrue(text.find("\nseq,entry_us,exit_us,frames,out_frame,gap_us,render_us\n") != std::string::npos, "the column names");
            t.IsTrue(text.find("\n0,0,500,960,960,0,500\n") != std::string::npos, "the first row: no gap yet");
            t.IsTrue(text.find("\n1,20000,20600,960,1920,20000,600\n") != std::string::npos, "the second row: its gap and render");
            trace.record(45000, 45400, 960u, 2880);
            std::ostringstream more;
            t.Equals(trace.flush(more, next, false, 0), static_cast<size_t>(3), "the next flush starts where the last one stopped");
            t.Equals(more.str(), std::string("2,45000,45400,960,2880,25000,400\n"), "only the new row, no header");
        });

        tc.Run("the thresholds come from the device spec: 20 ms x 4 means jitter over 30 ms and a hole over 60 ms", [](TestCase &t)
        {
            const ps2x::MixDeviceSpec spec = ps2x::mixDeviceSpec();
            ps2x::AudioCallbackTrace trace(4, static_cast<int64_t>(spec.periodMs) * 1000, spec.periods);
            t.Equals(trace.jitterThresholdUs(), static_cast<int64_t>(30000), "1.5 periods");
            t.Equals(trace.holeThresholdUs(), static_cast<int64_t>(60000), "the buffer less one period: what the engine can still cover");
        });
    });
}
