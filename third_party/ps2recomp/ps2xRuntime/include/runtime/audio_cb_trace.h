#pragma once
// Sprint 11 audio-out (2026-09-23): a timestamped trace of every host audio callback, so a 50 ms hole in the
// endpoint recording can be attributed to a callback the device thread serviced late -- or shown not to be one.
//
// KNOWN §2 (2026-09-23): the mission music loses ~50 ms holes, 10-20 dB deep, present in the endpoint loopback and
// absent from the mixer's dump at the aligned time, on a wired endpoint as on Bluetooth. The dump is written from
// the callback itself (ps2_audio.cpp mixerRender), so whatever loses them acts after the callback returns; the
// dump's frame clock cannot see a late callback and the endpoint can. This records, per callback, the wall clock
// at entry and exit, the frames asked for and the output-frame clock afterwards.
//
// Three thresholds on the gap between two callback entries, all derived from the device (ps2x::MixDeviceSpec,
// 20 ms x 4 = an 80 ms buffer):
//   jittered  gap > 1.5 periods (30 ms): the thread was not on time;
//   late      gap > (periods - 1) periods (60 ms): an early warning -- the engine was one period from dry, but
//             the buffer still covered it and NO silence reached the endpoint;
//   dry       gap > periods * period (80 ms): the engine ran out of what we had queued, and the endpoint got
//             about gap - buffer of silence. Only dry callbacks are counted as silence.
//
// Not a ring: the capacity is fixed at open and record() drops once it is used up, counting the drops; the
// flusher writes "# dropped=N recorded=M" on every pass (status()) so a saturated trace says so in the file, not
// only in a close summary the harness may never let run.
//
// Single producer (the audio thread: record()), any number of readers after the fact (flush(), stats()); the
// producer publishes with a release store on the count and never allocates. The running counters the readers may
// look at while the producer runs are atomics, read relaxed: a snapshot, not a sum that must balance.
#include <atomic>
#include <cstdint>
#include <cstddef>
#include <ostream>
#include <vector>

namespace ps2x
{
    struct AudioCallbackRecord
    {
        uint64_t seq = 0;        // 0-based index among RECORDED callbacks (a dropped one leaves no gap here)
        int64_t entryUs = 0;     // microseconds since the trace's t0 (a steady clock) at callback entry
        int64_t exitUs = 0;      // ... at exit, after render, gain, the frame-clock read and the dump's write
        uint32_t frames = 0;     // frames the device asked for
        uint64_t outFrame = 0;   // the mixer's output-frame clock AFTER this callback (the [audio] events' clock)
    };

    class AudioCallbackTrace
    {
    public:
        AudioCallbackTrace(size_t capacity, int64_t periodUs, uint32_t periods)
            : m_records(capacity), m_periodUs(periodUs),
              m_jitterUs(periodUs + periodUs / 2),
              m_lateUs(periods > 1 ? periodUs * static_cast<int64_t>(periods - 1) : periodUs),
              m_dryUs(periodUs * static_cast<int64_t>(periods > 0 ? periods : 1))
        {
        }

        // Audio thread only. Returns false (and counts a drop) once the capacity is used up; the counters keep
        // running past that point so stats() stays true for the whole session.
        bool record(int64_t entryUs, int64_t exitUs, uint32_t frames, uint64_t outFrame)
        {
            const size_t n = m_count.load(std::memory_order_relaxed);
            const int64_t renderUs = exitUs - entryUs;
            if (m_maxRenderUs.load(std::memory_order_relaxed) < renderUs)
                m_maxRenderUs.store(renderUs, std::memory_order_relaxed);
            if (m_calls.load(std::memory_order_relaxed) > 0)
            {
                const int64_t gap = entryUs - m_lastEntryUs;
                if (m_maxGapUs.load(std::memory_order_relaxed) < gap)
                    m_maxGapUs.store(gap, std::memory_order_relaxed);
                if (gap > m_jitterUs)
                    m_jittered.fetch_add(1, std::memory_order_relaxed);
                if (gap > m_lateUs)
                    m_late.fetch_add(1, std::memory_order_relaxed);
                if (gap > m_dryUs)
                {
                    m_dry.fetch_add(1, std::memory_order_relaxed);
                    m_silenceUs.fetch_add(gap - m_dryUs, std::memory_order_relaxed);
                }
            }
            m_lastEntryUs = entryUs;
            m_calls.fetch_add(1, std::memory_order_relaxed);
            if (n >= m_records.size())
            {
                m_dropped.fetch_add(1, std::memory_order_relaxed);
                return false;
            }
            AudioCallbackRecord &r = m_records[n];
            r.seq = n;
            r.entryUs = entryUs;
            r.exitUs = exitUs;
            r.frames = frames;
            r.outFrame = outFrame;
            m_count.store(n + 1, std::memory_order_release);
            return true;
        }

        size_t size() const { return m_count.load(std::memory_order_acquire); }
        size_t capacity() const { return m_records.size(); }
        uint64_t dropped() const { return m_dropped.load(std::memory_order_relaxed); }
        const AudioCallbackRecord &at(size_t i) const { return m_records[i]; }

        struct Stats
        {
            uint64_t calls = 0;      // recorded + dropped
            uint64_t jittered = 0;   // gap > 1.5 periods
            uint64_t late = 0;       // gap > (periods - 1) periods: one period from dry, still covered
            uint64_t dry = 0;        // gap > periods * period: the buffer ran out
            int64_t silenceUs = 0;   // the silence the dry callbacks put in the endpoint: sum of (gap - buffer)
            int64_t maxGapUs = 0;
            int64_t maxRenderUs = 0;
        };
        Stats stats() const
        {
            Stats s;
            s.calls = m_calls.load(std::memory_order_relaxed);
            s.jittered = m_jittered.load(std::memory_order_relaxed);
            s.late = m_late.load(std::memory_order_relaxed);
            s.dry = m_dry.load(std::memory_order_relaxed);
            s.silenceUs = m_silenceUs.load(std::memory_order_relaxed);
            s.maxGapUs = m_maxGapUs.load(std::memory_order_relaxed);
            s.maxRenderUs = m_maxRenderUs.load(std::memory_order_relaxed);
            return s;
        }
        int64_t jitterThresholdUs() const { return m_jitterUs; }
        int64_t lateThresholdUs() const { return m_lateUs; }
        int64_t dryThresholdUs() const { return m_dryUs; }

        // Indices of the recorded callbacks whose gap to the previous record exceeds the late threshold.
        std::vector<size_t> lateCallbacks() const
        {
            std::vector<size_t> out;
            const size_t n = size();
            for (size_t i = 1; i < n; ++i)
                if (m_records[i].entryUs - m_records[i - 1].entryUs > m_lateUs)
                    out.push_back(i);
            return out;
        }

        // CSV: the header when `header` is set, then one row per record from index `from` up to size(). Returns
        // the index the next flush starts from. `t0EpochUs` (the steady clock's t0 as a wall-clock epoch, in
        // microseconds) goes in the header so a recorder's own wall-clock stamp can be aligned to the rows.
        size_t flush(std::ostream &out, size_t from, bool header, int64_t t0EpochUs) const
        {
            const size_t n = size();
            if (header)
            {
                out << "# audio callback trace: t0_epoch_us=" << t0EpochUs << " period_us=" << m_periodUs
                    << " jitter_us=" << m_jitterUs << " late_us=" << m_lateUs << " dry_us=" << m_dryUs
                    << " capacity=" << m_records.size() << "\n";
                out << "seq,entry_us,exit_us,frames,out_frame,gap_us,render_us\n";
            }
            for (size_t i = from; i < n; ++i)
            {
                const AudioCallbackRecord &r = m_records[i];
                const int64_t gap = i > 0 ? r.entryUs - m_records[i - 1].entryUs : 0;
                out << r.seq << ',' << r.entryUs << ',' << r.exitUs << ',' << r.frames << ',' << r.outFrame << ','
                    << gap << ',' << (r.exitUs - r.entryUs) << '\n';
            }
            return n;
        }

        // The status line the flusher appends on every pass, so a saturated trace is visible in the file itself.
        void status(std::ostream &out) const
        {
            out << "# dropped=" << dropped() << " recorded=" << size() << "\n";
        }

    private:
        std::vector<AudioCallbackRecord> m_records;
        std::atomic<size_t> m_count{0};
        int64_t m_periodUs;
        int64_t m_jitterUs;
        int64_t m_lateUs;
        int64_t m_dryUs;
        int64_t m_lastEntryUs = 0;                 // producer-owned
        std::atomic<uint64_t> m_calls{0};
        std::atomic<uint64_t> m_dropped{0};
        std::atomic<uint64_t> m_jittered{0};
        std::atomic<uint64_t> m_late{0};
        std::atomic<uint64_t> m_dry{0};
        std::atomic<int64_t> m_silenceUs{0};
        std::atomic<int64_t> m_maxGapUs{0};
        std::atomic<int64_t> m_maxRenderUs{0};
    };
}
