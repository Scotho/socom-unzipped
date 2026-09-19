#pragma once

// Sprint 8 Goal 2 Task 1: what a texture upload actually costs, per call.
//
// The [gs-gl stats] line says the menus spend 80-133 ms/s in `upload=` against gameplay's 20-28
// (KNOWN section 1, the 2026-09-18 re-measure), and that 100% of the traced uploads are 16x16
// PSMCT32 tiles of exactly 1024 bytes. What it does NOT say is which term of the tile path that
// time is: the shadow swizzle, the page/rect marking, the record under the queue mutex, the CPU
// convert in refreshDirtyRows, or glTexSubImage2D itself. Those live in three different functions
// and only the first two are inside the `upload=` bucket at all (gs_gl_backend.cpp:1577-1581 times
// executeUpload; the two glTexSubImage2D sites are in refreshDirtyRows and are charged to clear=,
// submit= and present=). This accumulator straddles them and prints one line.
//
// Header-only and free of GL includes on purpose, so ps2xTest can check the arithmetic without a
// context -- the same reason gs_gl_target_extent.h is.

#include <algorithm>
#include <cstdint>
#include <cstdio>
#include <string>
#include <vector>

namespace GsGlUploadTrace
{
    constexpr int kBuckets = 8;
    // 1024 bytes is a 16x16 PSMCT32 tile: the entire menu upload population, per the [gs-pages]
    // trace. Each later bucket is a doubling, so a full 8 KB page and a 64 KB movie strip are
    // visibly separate columns rather than one "everything else".
    constexpr const char *kBucketLabels[kBuckets] = {"1k", "2k", "4k", "8k", "16k", "32k", "64k", "big"};

    inline int bucketFor(size_t bytes)
    {
        if (bytes <= 1024u)
            return 0;
        int b = 0;
        size_t limit = 1024u;
        while (b < kBuckets - 1 && bytes > limit)
        {
            limit <<= 1;
            ++b;
        }
        return b;
    }

    struct Accum
    {
        uint64_t sizes[kBuckets] = {0, 0, 0, 0, 0, 0, 0, 0};
        uint64_t uploads = 0;        // CmdType::Upload commands replayed
        uint64_t rectsMarked = 0;    // exact rectangles pushed onto rt.dirtyRects
        uint64_t glCalls = 0;        // glTexSubImage2D calls made by refreshDirtyRows
        double shadowUs = 0.0;       // (a) m_shadow->UploadImage: the CPU swizzle into shadow VRAM
        double markUs = 0.0;         // (a) markShadowPages + refreshRenderTargetsFromShadow
        double recordUs = 0.0;       // (c) GSGlBackend::record, game thread, under m_queueMutex
        double convertUs = 0.0;      // (a) the readVramRaw + convert + replicate loops feeding a GL upload
        double glUs = 0.0;           // (b) glTexSubImage2D itself
        // Distinct destination texture objects touched in the interval. Bounded: a menu screen has
        // a handful of render targets, and an unbounded set would be the trace's own hot spot.
        std::vector<uint32_t> dstTextures;
    };

    inline void noteDst(Accum &a, uint32_t texture)
    {
        if (a.dstTextures.size() >= 256u)
            return;
        const auto it = std::lower_bound(a.dstTextures.begin(), a.dstTextures.end(), texture);
        if (it == a.dstTextures.end() || *it != texture)
            a.dstTextures.insert(it, texture);
    }

    inline void noteUpload(Accum &a, size_t bytes, double shadowUs, double markUs)
    {
        ++a.uploads;
        ++a.sizes[bucketFor(bytes)];
        a.shadowUs += shadowUs;
        a.markUs += markUs;
    }

    inline void noteRecord(Accum &a, double us) { a.recordUs += us; }

    inline void noteRect(Accum &a) { ++a.rectsMarked; }

    inline void noteGlUpload(Accum &a, uint32_t texture, double convertUs, double glUs)
    {
        ++a.glCalls;
        a.convertUs += convertUs;
        a.glUs += glUs;
        noteDst(a, texture);
    }

    inline void reset(Accum &a) { a = Accum{}; }

    // One line: every count per second, every per-call figure in microseconds to one decimal.
    inline std::string format(const Accum &a, double elapsedMs)
    {
        const double perSec = elapsedMs > 0.0 ? 1000.0 / elapsedMs : 0.0;
        auto per = [](double total, uint64_t n) { return n ? total / static_cast<double>(n) : 0.0; };
        char buf[640];
        int n = std::snprintf(buf, sizeof(buf),
                              "[gs-upload] elapsed=%.0fms uploads=%.0f/s rects=%.0f/s gl_calls=%.0f/s sizes:",
                              elapsedMs, static_cast<double>(a.uploads) * perSec,
                              static_cast<double>(a.rectsMarked) * perSec,
                              static_cast<double>(a.glCalls) * perSec);
        for (int b = 0; b < kBuckets && n < 480; ++b)
            if (a.sizes[b])
                n += std::snprintf(buf + n, sizeof(buf) - n, " %s=%llu", kBucketLabels[b], (unsigned long long)a.sizes[b]);
        std::snprintf(buf + n, sizeof(buf) - n,
                      " us/upload: shadow=%.1f mark=%.1f record=%.1f us/gl_call: convert=%.1f gl=%.1f dst_textures=%zu",
                      per(a.shadowUs, a.uploads), per(a.markUs, a.uploads), per(a.recordUs, a.uploads),
                      per(a.convertUs, a.glCalls), per(a.glUs, a.glCalls), a.dstTextures.size());
        return std::string(buf);
    }
}
