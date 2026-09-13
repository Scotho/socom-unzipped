#include "runtime/gs/gs_frame_backpressure.h"

#include <cstdlib>

uint32_t GsFrameBackpressure::parseMaxPendingFrames(const char *value, uint32_t fallback)
{
    if (!value || *value == 0)
        return fallback;
    char *end = nullptr;
    const unsigned long parsed = std::strtoul(value, &end, 10);
    // strtoul accepts a leading '-' (and wraps it): only plain decimal digits count.
    if (*value < '0' || *value > '9' || !end || *end != 0 || parsed > 0xFFFFul)
        return fallback;
    return static_cast<uint32_t>(parsed);
}

GsFrameBackpressure::GsFrameBackpressure(uint32_t maxPendingFrames, std::chrono::milliseconds waitCap)
    : m_maxPendingFrames(maxPendingFrames), m_waitCap(waitCap)
{
}

void GsFrameBackpressure::setMaxPendingFrames(uint32_t maxPendingFrames)
{
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_maxPendingFrames = maxPendingFrames;
    }
    m_cv.notify_all();
}

uint32_t GsFrameBackpressure::maxPendingFrames() const
{
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_maxPendingFrames;
}

GsFrameBackpressure::WaitResult GsFrameBackpressure::frameRecorded()
{
    std::unique_lock<std::mutex> lock(m_mutex);
    ++m_recorded;
    ++m_stats.frames;
    const auto withinBound = [this]
    { return m_released || m_maxPendingFrames == 0u || m_recorded - m_replayed <= m_maxPendingFrames; };
    if (withinBound())
        return WaitResult::NotNeeded;
    if (m_consumerStalled)
    {
        ++m_stats.skipped;
        return WaitResult::Skipped;
    }
    const auto t0 = std::chrono::steady_clock::now();
    const bool caughtUp = m_cv.wait_for(lock, m_waitCap, withinBound);
    m_stats.waitMs += std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
    if (caughtUp)
    {
        ++m_stats.waits;
        return WaitResult::Waited;
    }
    m_consumerStalled = true;
    ++m_stats.timeouts;
    return WaitResult::TimedOut;
}

uint64_t GsFrameBackpressure::recordedFrames() const
{
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_recorded;
}

void GsFrameBackpressure::framesReplayed(uint64_t recordedCount)
{
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        if (recordedCount <= m_replayed)
            return;
        m_replayed = recordedCount;
        m_consumerStalled = false;
    }
    m_cv.notify_all();
}

void GsFrameBackpressure::release()
{
    {
        std::lock_guard<std::mutex> lock(m_mutex);
        m_released = true;
    }
    m_cv.notify_all();
}

uint64_t GsFrameBackpressure::pendingFrames() const
{
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_recorded - m_replayed;
}

GsFrameBackpressure::Stats GsFrameBackpressure::takeStats()
{
    std::lock_guard<std::mutex> lock(m_mutex);
    Stats s = m_stats;
    m_stats = Stats{};
    return s;
}
