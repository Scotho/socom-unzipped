#include "runtime/gs/ps2_gif_arbiter.h"
#include "ps2x/knobs.h"
#include <algorithm>
#include <cstring>
#include <cstdlib>

GifArbiter::GifArbiter(ProcessPacketFn processFn)
    : m_processFn(std::move(processFn))
{
}

bool GifArbiter::isImagePacket(const uint8_t *data, uint32_t sizeBytes)
{
    if (!data || sizeBytes < 16u)
        return false;

    uint64_t tagLo = 0;
    std::memcpy(&tagLo, data, sizeof(tagLo));
    const uint8_t flg = static_cast<uint8_t>((tagLo >> 58) & 0x3u);
    return flg == 2u;
}

// Read on first use, not while the process is still initialising its statics: main() has not seen --dev by then.
static bool prioritySort()
{
    static const bool s_on = ps2x::knobOn("PS2X_GIF_PRIORITY_SORT");
    return s_on;
}

void GifArbiter::submit(GifPathId pathId, const uint8_t *data, uint32_t sizeBytes, bool path2DirectHl)
{
    if (!data || sizeBytes < 16 || !m_processFn)
        return;
    // Packets are processed in submission order and nothing but other submissions happens
    // between a submit and the drain (the DMA emulation is synchronous), so a packet arriving
    // at an empty queue is next in any case: process it from the caller's buffer, no copy
    // (an XGKICK packet was memcpy'd here on every kick, ~7% of the game thread).
    if (m_queueCount == 0u && !prioritySort())
    {
        m_processFn(data, sizeBytes);
        return;
    }

    if (m_queueCount == m_queue.size())
        m_queue.emplace_back();
    GifArbiterPacket &pkt = m_queue[m_queueCount++];
    pkt.pathId = pathId;
    pkt.path2DirectHl = (pathId == GifPathId::Path2) && path2DirectHl;
    pkt.path3Image = (pathId == GifPathId::Path3) && isImagePacket(data, sizeBytes);
    pkt.data.resize(sizeBytes);
    std::memcpy(pkt.data.data(), data, sizeBytes);
}

void GifArbiter::drain()
{
    if (!m_processFn)
        return;

    // Packets are processed in submission order. The GIF only arbitrates between paths that are
    // waiting at the same time, and a packet it has accepted is never overtaken; with the
    // sequential DMA emulation here, submission order is that acceptance order. The old
    // priority sort moved a VU1 XGKICK (PATH1) ahead of PATH3 texture uploads queued by the same
    // DMA chain, which garbled SOCOM II's title-screen text once XGKICK packets were copied at
    // kick time (2026-09-08). PS2X_GIF_PRIORITY_SORT=1 restores the sort for A/B checks.
    if (prioritySort())
    std::stable_sort(m_queue.begin(), m_queue.begin() + static_cast<std::ptrdiff_t>(m_queueCount),
                     [](const GifArbiterPacket &a, const GifArbiterPacket &b)
                     {
                         // DIRECTHL cannot preempt PATH3 IMAGE transfers.
                         if (a.path2DirectHl != b.path2DirectHl || a.path3Image != b.path3Image)
                         {
                             if (a.path3Image && b.path2DirectHl)
                                 return true;
                             if (a.path2DirectHl && b.path3Image)
                                 return false;
                         }
                         return pathPriority(a.pathId) < pathPriority(b.pathId);
                     });

    // Packet slots (and their buffers) are kept for reuse: a submit is one memcpy, no allocation.
    // The count is re-read every iteration so packets appended while draining are processed too.
    for (size_t i = 0; i < m_queueCount; ++i)
    {
        auto &pkt = m_queue[i];
        if (!pkt.data.empty())
        {
            m_processFn(pkt.data.data(), static_cast<uint32_t>(pkt.data.size()));
        }
    }
    m_queueCount = 0;
}

uint8_t GifArbiter::pathPriority(GifPathId id)
{
    return static_cast<uint8_t>(id);
}
