#pragma once
// research/36 item 14 (2026-09-20): the movie decoder, off the guest thread.
//
// The MPEG HLE decoded pictures with ffmpeg on the CALLING guest thread -- SOCOM's video thread, which also
// demuxes the PSS and feeds the movie's audio into the 989snd PCM ring (GetPicture -> the STOPDMA callback ->
// DemuxPss). A slow decode burst held that thread for 200-700 ms while the EE's ticks advanced, so the 128 ms
// ring ran dry: the intro's and the briefing's 100-700 ms holes (the instrumented captures s10_r4l/r4m: the
// ring's feed at 0 bytes for 0.3-0.7 s, no guest park, the CD stream always readable).
//
// DecodeAhead wraps a decoder behind one worker thread. The feeder hands packets over and returns at once;
// the worker decodes in arrival order into a ready queue; readers drain what is ready. Picture order and the
// decoder's own semantics are unchanged: the same packets, the same flush, the same frames. A failed decode
// is reported by the NEXT feed (one packet late), which the caller already treats as "resync to the sequence
// header". `pending()` counts undecoded packets so back-pressure can hold the demux the way it held it when
// frames appeared synchronously; `idle()` says the worker has nothing in hand, so an end-of-stream check never
// runs ahead of a flush's tail frames. The destructor stops the worker after the packet in hand and joins.
//
// Decoder: default-constructible, with
//     bool feed(const uint8_t *data, size_t size, std::deque<Frame> &out, int64_t pts90k, int64_t dts90k);
//     bool flush(std::deque<Frame> &out);
// used from the worker thread only once the wrapper exists (the ffmpeg contexts are opened there too).
#include <condition_variable>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <mutex>
#include <thread>
#include <utility>
#include <vector>

namespace ps2x
{
    template <class Frame, class Decoder>
    class DecodeAhead
    {
    public:
        DecodeAhead() : m_thread([this] { run(); }) {}
        ~DecodeAhead()
        {
            {
                std::lock_guard<std::mutex> lock(m_mutex);
                m_stop = true;
            }
            m_cv.notify_all();
            if (m_thread.joinable())
                m_thread.join();
        }
        DecodeAhead(const DecodeAhead &) = delete;
        DecodeAhead &operator=(const DecodeAhead &) = delete;

        // Hands a packet to the worker. False once a previous packet failed to decode (the caller resyncs).
        bool feed(const uint8_t *data, size_t size, int64_t pts90k = -1, int64_t dts90k = -1)
        {
            if (!data || size == 0)
                return true;
            {
                std::lock_guard<std::mutex> lock(m_mutex);
                if (m_failed)
                    return false;
                m_pending.push_back(Packet{std::vector<uint8_t>(data, data + size), pts90k, dts90k, false});
            }
            m_cv.notify_all();
            return true;
        }

        // Asks the worker to flush the decoder once everything before it has been decoded.
        void flush()
        {
            {
                std::lock_guard<std::mutex> lock(m_mutex);
                m_pending.push_back(Packet{{}, -1, -1, true});
            }
            m_cv.notify_all();
        }

        // Moves every decoded frame into `out`, in decode order.
        void drain(std::deque<Frame> &out)
        {
            std::lock_guard<std::mutex> lock(m_mutex);
            while (!m_ready.empty())
            {
                out.push_back(std::move(m_ready.front()));
                m_ready.pop_front();
            }
        }

        // Packets not yet decoded, the one in the worker's hands included.
        size_t pending() const
        {
            std::lock_guard<std::mutex> lock(m_mutex);
            return m_pending.size() + (m_busy ? 1u : 0u);
        }
        bool idle() const
        {
            std::lock_guard<std::mutex> lock(m_mutex);
            return m_pending.empty() && !m_busy;
        }
        bool failed() const
        {
            std::lock_guard<std::mutex> lock(m_mutex);
            return m_failed;
        }
        // The wrapped decoder (a test's fake reaches its knobs here; never touched while the worker decodes).
        Decoder &decoder() { return m_decoder; }

    private:
        struct Packet
        {
            std::vector<uint8_t> bytes;
            int64_t pts90k = -1;
            int64_t dts90k = -1;
            bool flush = false;
        };

        void run()
        {
            for (;;)
            {
                Packet packet;
                {
                    std::unique_lock<std::mutex> lock(m_mutex);
                    m_cv.wait(lock, [this] { return m_stop || !m_pending.empty(); });
                    if (m_stop)
                        return;
                    packet = std::move(m_pending.front());
                    m_pending.pop_front();
                    m_busy = true;
                }
                std::deque<Frame> out;
                const bool ok = packet.flush ? m_decoder.flush(out)
                                             : m_decoder.feed(packet.bytes.data(), packet.bytes.size(), out, packet.pts90k, packet.dts90k);
                {
                    std::lock_guard<std::mutex> lock(m_mutex);
                    for (Frame &f : out)
                        m_ready.push_back(std::move(f));
                    if (!ok)
                        m_failed = true;
                    m_busy = false;
                }
                m_cv.notify_all();
            }
        }

        Decoder m_decoder;
        mutable std::mutex m_mutex;
        std::condition_variable m_cv;
        std::deque<Packet> m_pending;
        std::deque<Frame> m_ready;
        bool m_stop = false;
        bool m_busy = false;
        bool m_failed = false;
        std::thread m_thread;   // last: it runs against the members above
    };
}
