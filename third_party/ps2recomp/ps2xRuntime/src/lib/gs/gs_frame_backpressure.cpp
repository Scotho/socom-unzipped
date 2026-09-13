#include "runtime/gs/gs_frame_backpressure.h"

#include <algorithm>
#include <cstdio>
#include <cstdlib>

uint32_t GsFrameBackpressure::parseMaxPendingFrames(const char *value, uint32_t fallback)
{
    if (!value || *value == 0)
        return fallback;
    char *end = nullptr;
    const unsigned long parsed = std::strtoul(value, &end, 10);
    // strtoul accepts a leading '-' (and wraps it): only plain decimal digits count.
    if (*value < '0' || *value > '9' || !end || *end != 0 || parsed > 0xFFFFul)
    {
        static bool s_logged = false;
        if (!s_logged)
        {
            s_logged = true;
            std::fprintf(stderr, "[gs-gl] PS2X_GS_MAX_PENDING_FRAMES=%s is not a decimal in 0..65535; using %u\n", value, fallback);
        }
        return fallback;
    }
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
    uint64_t lastProgress = m_progress.load(std::memory_order_relaxed);
    if (m_consumerStalled)
    {
        // R40: the latch clears as soon as the consumer shows any sign of life, not only when a
        // replay completes.
        if (lastProgress == m_progressAtLatch)
        {
            ++m_stats.skipped;
            return WaitResult::Skipped;
        }
        m_consumerStalled = false;
        ++m_stats.unlatched;
    }
    // Wait in slices so the heartbeat (a lock-free counter, no notify) is seen; the cap bounds the
    // time WITHOUT progress, so a live consumer replaying a big batch keeps the wait armed.
    const auto slice = std::clamp(m_waitCap / 8, std::chrono::milliseconds(1), std::chrono::milliseconds(50));
    const auto t0 = std::chrono::steady_clock::now();
    auto lastProgressTime = t0;
    ++m_waiters;
    WaitResult result = WaitResult::Waited;
    for (;;)
    {
        if (m_cv.wait_for(lock, slice, withinBound))
            break;
        const auto now = std::chrono::steady_clock::now();
        const uint64_t progress = m_progress.load(std::memory_order_relaxed);
        if (progress != lastProgress)
        {
            lastProgress = progress;
            lastProgressTime = now;
        }
        else if (now - lastProgressTime >= m_waitCap)
        {
            result = WaitResult::TimedOut;
            break;
        }
    }
    --m_waiters;
    m_stats.waitMs += std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
    if (result == WaitResult::Waited)
    {
        ++m_stats.waits;
        return result;
    }
    m_consumerStalled = true;
    m_progressAtLatch = lastProgress;
    ++m_stats.timeouts;
    return result;
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
        if (m_consumerStalled)
        {
            m_consumerStalled = false;
            ++m_stats.unlatched;
        }
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

uint32_t GsFrameBackpressure::waiters() const
{
    std::lock_guard<std::mutex> lock(m_mutex);
    return m_waiters;
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
