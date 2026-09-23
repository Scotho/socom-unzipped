#pragma once
// Sprint 11 audio-out (2026-09-23): a timestamped trace of every host audio callback, so a 50 ms hole in the
// endpoint recording can be attributed to a callback the device thread serviced late -- or shown not to be one.
//
// KNOWN §2 (2026-09-23): the mission music loses ~50 ms holes, 10-20 dB deep, present in the endpoint loopback and
// absent from the mixer's dump at the aligned time, on a wired endpoint as on Bluetooth. The dump is written from
// the callback itself (ps2_audio.cpp mixerRender), so whatever loses them acts after the callback returns; the
// dump's frame clock cannot see a late callback and the endpoint can. This records, per callback, the wall clock
// at entry and exit, the frames asked for and the output-frame clock afterwards. A gap between two entries longer
// than the device's whole buffer minus one period is a callback the engine could not have waited for: a hole.
//
// Single producer (the audio thread: record()), any number of readers after the fact (flush(), stats()); the
// producer publishes with a release store on the count and never allocates -- the capacity is fixed at open.
#include <atomic>
#include <cstdint>
#include <cstddef>
#include <ostream>
#include <vector>

namespace ps2x
{
    struct AudioCallbackRecord
    {
        uint64_t seq = 0;        // 0-based callback index
        int64_t entryUs = 0;     // microseconds since the trace's t0 (a steady clock) at callback entry
        int64_t exitUs = 0;      // ... at exit, after render, gain and the dump's write
        uint32_t frames = 0;     // frames the device asked for
        uint64_t outFrame = 0;   // the mixer's output-frame clock AFTER this callback (the [audio] events' clock)
    };

    class AudioCallbackTrace
    {
    public:
        // periodUs and periods describe the device (ps2x::MixDeviceSpec): a gap over periodUs * 1.5 is "jittered",
        // a gap over periodUs * (periods - 1) is a "hole" -- the engine ran out of what we had queued.
        AudioCallbackTrace(size_t capacity, int64_t periodUs, uint32_t periods)
            : m_records(capacity), m_periodUs(periodUs),
              m_jitterUs(periodUs + periodUs / 2), m_holeUs(periods > 1 ? periodUs * static_cast<int64_t>(periods - 1) : periodUs)
        {
        }

        // Audio thread only. Returns false (and counts a drop) once the capacity is used up.
        bool record(int64_t entryUs, int64_t exitUs, uint32_t frames, uint64_t outFrame)
        {
            const size_t n = m_count.load(std::memory_order_relaxed);
            const int64_t renderUs = exitUs - entryUs;
            if (m_maxRenderUs < renderUs)
                m_maxRenderUs = renderUs;
            if (n > 0)
            {
                const int64_t gap = entryUs - m_lastEntryUs;
                if (m_maxGapUs < gap)
                    m_maxGapUs = gap;
                if (gap > m_jitterUs)
                    ++m_jittered;
                if (gap > m_holeUs)
                {
                    ++m_holes;
                    m_holeUsSum += gap - m_periodUs;
                }
            }
            m_lastEntryUs = entryUs;
            if (n >= m_records.size())
            {
                ++m_dropped;
                return false;
            }
            AudioCallbackRecord &r = m_records[n];
            r.seq = m_seq++;
            r.entryUs = entryUs;
            r.exitUs = exitUs;
            r.frames = frames;
            r.outFrame = outFrame;
            m_count.store(n + 1, std::memory_order_release);
            return true;
        }

        size_t size() const { return m_count.load(std::memory_order_acquire); }
        size_t capacity() const { return m_records.size(); }
        uint64_t dropped() const { return m_dropped; }
        const AudioCallbackRecord &at(size_t i) const { return m_records[i]; }

        struct Stats
        {
            uint64_t calls = 0;      // recorded + dropped
            uint64_t jittered = 0;   // gap > 1.5 periods
            uint64_t holes = 0;      // gap > (periods - 1) periods: the buffer ran dry
            int64_t holeUsSum = 0;   // the silence those holes put in the endpoint, roughly: sum of (gap - period)
            int64_t maxGapUs = 0;
            int64_t maxRenderUs = 0;
        };
        // Running counters kept by record(); readable from any thread once the producer is quiet, and from the
        // producer itself at any time (the [audio-trace] summary).
        Stats stats() const
        {
            Stats s;
            s.calls = m_seq + m_dropped;
            s.jittered = m_jittered;
            s.holes = m_holes;
            s.holeUsSum = m_holeUsSum;
            s.maxGapUs = m_maxGapUs;
            s.maxRenderUs = m_maxRenderUs;
            return s;
        }
        int64_t holeThresholdUs() const { return m_holeUs; }
        int64_t jitterThresholdUs() const { return m_jitterUs; }

        // Indices of the records whose gap to the previous record exceeds the hole threshold.
        std::vector<size_t> holes() const
        {
            std::vector<size_t> out;
            const size_t n = size();
            for (size_t i = 1; i < n; ++i)
                if (m_records[i].entryUs - m_records[i - 1].entryUs > m_holeUs)
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
                    << " jitter_us=" << m_jitterUs << " hole_us=" << m_holeUs << " capacity=" << m_records.size() << "\n";
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

    private:
        std::vector<AudioCallbackRecord> m_records;
        std::atomic<size_t> m_count{0};
        int64_t m_periodUs;
        int64_t m_jitterUs;
        int64_t m_holeUs;
        // producer-owned running state (read by others only when the producer is quiet, or by the producer)
        uint64_t m_seq = 0;
        uint64_t m_dropped = 0;
        uint64_t m_jittered = 0;
        uint64_t m_holes = 0;
        int64_t m_holeUsSum = 0;
        int64_t m_maxGapUs = 0;
        int64_t m_maxRenderUs = 0;
        int64_t m_lastEntryUs = 0;
    };
}
