#pragma once

// Sprint 13 V2 (#32): WHY a host->local upload reached the shadow, and the one kind that need not.
//
// The [gs-gl stats] line says how much the menus upload (7-11k 16x16 tiles a second, 67-114 ms/s of
// upload= on 2026-09-25's run_A_20260925_194529 lobby rows) and never why. research/41 section 4
// (ADAPT item 2) is the instrument: a count per reason, printed on the same 60-call cadence as a
// sibling [gs-gl stats] reasons line. The upload reasons are the real branches of an Upload
// command, in the order Gate::decide tests them:
//
//   chunked         the rectangle arrives in several IMAGE packets (R119), or its format has no block
//                   map here (Z formats): never a candidate
//   new             the first whole upload to this rectangle the gate remembers
//   changed         the same rectangle with different bytes
//   same_rewritten  the same bytes as its last upload, but something wrote into its 256-byte blocks
//                   since (another upload, a VRAM write, a local copy, a render-target download) or the
//                   render-target set changed: the shadow may no longer hold them
//   same_gpu        the same bytes, untouched in the shadow, but a render target has GPU-drawn rows
//                   over the rectangle since its last download: the GPU texture may not hold them --
//                   R122's R118 guard, which refused 84% of the identical uploads on the login screen
//   same_free       the same bytes, and nothing anywhere has changed them: the upload is a no-op.
//                   Skipped when PS2X_GS_UPLOAD_SKIP=1 (skipped=); only counted otherwise
//
// and the texture side (resolveTexture's branches, the consumer R123 fixed): hit, rt (a render
// target sampled directly), revalidated (generation moved, bytes did not), redecoded (generation
// moved and the bytes did -- a changed texture or a changed palette window), new (a key never
// cached: first use, or a new CLUT snapshot id or TEX0 field).
//
// Why the skip is correct where R122's was not affordable: R122 kept a remembered hash per
// rectangle valid "until a write of different content overlaps it", which needed a sweep over the
// remembered rectangles on every write (~84 ms/s). Here validity is a generation compare: every
// upload stamps the GS blocks it writes, every other shadow writer stamps its pages, and a
// remembered upload is still in the shadow iff none of its blocks or pages carry a newer stamp.
// A sibling tile in the same page writes other blocks and leaves it valid; that is the case R118's
// page-granular guard could never pass (91.6% refused by the generation clause).
//
// Header-only and free of GL includes on purpose, so ps2xTest drives the same Gate the backend
// runs -- the reason gs_gl_upload_trace.h and gs_gl_upload_identity.h are headers too.

#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <unordered_map>
#include <vector>

#include "runtime/gs/gs_types.h"
#include "runtime/gs/gs_gl_upload_identity.h"
#include "runtime/gs/ps2_gs_psmct16.h"
#include "runtime/gs/ps2_gs_psmct32.h"
#include "runtime/gs/ps2_gs_psmt4.h"
#include "runtime/gs/ps2_gs_psmt8.h"

namespace GsGlUploadReasons
{
    enum class Reason : uint8_t { Chunked, New, Changed, SameRewritten, SameUnderGpu, SameFree, Count };
    constexpr const char *kReasonLabels[] = {"chunked", "new", "changed", "same_rewritten", "same_gpu", "same_free"};

    enum class Tex : uint8_t { Hit, RtDirect, Revalidated, Redecoded, New, Count };
    constexpr const char *kTexLabels[] = {"hit", "rt", "revalidated", "redecoded", "new"};

    constexpr uint32_t kBlocks = 16384u;   // 4 MB of GS local memory in 256-byte blocks
    constexpr uint32_t kPages = 512u;      // ... in 8 KB pages (32 blocks)
    constexpr size_t kMaxRects = 8192u;    // bounded like GsGlUploadIdentity::LastUploads

    // The GS block (byte address / 256) pixel (x, y) of a buffer lives in. False for a format with no
    // map here: the Z formats' page layout differs, and an upload into one is simply never skipped.
    inline bool blockOf(uint32_t psm, uint32_t bp, uint32_t bw, uint32_t x, uint32_t y, uint32_t &block)
    {
        uint32_t byteAddr = 0u;
        switch (psm)
        {
        case GS_PSM_CT32: case GS_PSM_CT24: case GS_PSM_T8H: case GS_PSM_T4HL: case GS_PSM_T4HH:
            byteAddr = GSPSMCT32::addrPSMCT32(bp, bw, x, y);
            break;
        case GS_PSM_CT16: byteAddr = GSPSMCT16::addrPSMCT16(bp, bw, x, y); break;
        case GS_PSM_CT16S: byteAddr = GSPSMCT16::addrPSMCT16S(bp, bw, x, y); break;
        case GS_PSM_T8: byteAddr = GSPSMT8::addrPSMT8(bp, bw, x, y); break;
        case GS_PSM_T4: byteAddr = GSPSMT4::addrPSMT4(bp, bw, x, y) >> 1; break;   // a nibble address
        default: return false;
        }
        block = (byteAddr >> 8) & (kBlocks - 1u);
        return true;
    }

    // Every block a w x h rectangle at (x0, y0) writes, sorted and unique. No block of any mapped
    // format is narrower or shorter than 8 pixels and blocks tile on that grid, so sampling every
    // 8th column and row plus the last one visits each block at least once.
    inline void blocksOf(uint32_t psm, uint32_t bp, uint32_t bw, uint32_t x0, uint32_t y0, uint32_t w, uint32_t h,
                         std::vector<uint32_t> &out)
    {
        out.clear();
        if (w == 0u || h == 0u)
            return;
        for (uint32_t y = y0;; y = std::min<uint32_t>(y + 8u, y0 + h - 1u))
        {
            for (uint32_t x = x0;; x = std::min<uint32_t>(x + 8u, x0 + w - 1u))
            {
                uint32_t b = 0u;
                if (!blockOf(psm, bp, bw, x, y, b))
                {
                    out.clear();
                    return;
                }
                out.push_back(b);
                if (x == x0 + w - 1u)
                    break;
            }
            if (y == y0 + h - 1u)
                break;
        }
        std::sort(out.begin(), out.end());
        out.erase(std::unique(out.begin(), out.end()), out.end());
    }

    // 8 bytes a step: FNV-1a's byte loop is ~1 us on a 1 KB tile, a tenth of the tile's whole cost.
    inline uint64_t hashBytes(const uint8_t *data, size_t size)
    {
        uint64_t h = 0x9E3779B97F4A7C15ull ^ (static_cast<uint64_t>(size) * 0xFF51AFD7ED558CCDull);
        size_t i = 0;
        for (; i + 8u <= size; i += 8u)
        {
            uint64_t w = 0;
            std::memcpy(&w, data + i, sizeof(w));
            h = (h ^ w) * 0x9E3779B97F4A7C15ull;
            h ^= h >> 32;
        }
        for (; i < size; ++i)
            h = (h ^ data[i]) * 0x100000001B3ull;
        return h ^ (h >> 29);
    }

    struct Tally
    {
        uint64_t uploads[static_cast<size_t>(Reason::Count)] = {};
        uint64_t skipped = 0;
        uint64_t tex[static_cast<size_t>(Tex::Count)] = {};
    };

    // One line, raw counts over the interval (the calls line's own unit), printed beside it.
    inline std::string format(const Tally &t, bool skipOn)
    {
        char buf[512];
        int n = std::snprintf(buf, sizeof(buf), "[gs-gl stats] reasons uploads:");
        for (size_t i = 0; i < static_cast<size_t>(Reason::Count); ++i)
            n += std::snprintf(buf + n, sizeof(buf) - static_cast<size_t>(n), " %s=%llu", kReasonLabels[i],
                               (unsigned long long)t.uploads[i]);
        n += std::snprintf(buf + n, sizeof(buf) - static_cast<size_t>(n), " skipped=%llu skip=%s textures:",
                           (unsigned long long)t.skipped, skipOn ? "on" : "off");
        for (size_t i = 0; i < static_cast<size_t>(Tex::Count); ++i)
            n += std::snprintf(buf + n, sizeof(buf) - static_cast<size_t>(n), " %s=%llu", kTexLabels[i],
                               (unsigned long long)t.tex[i]);
        return std::string(buf);
    }

    class Gate
    {
    public:
        struct Decision
        {
            Reason reason = Reason::Chunked;
            bool skip = false;
        };

        // A shadow write that is not a host->local upload (a VRAM write, a local->local copy, a render
        // target downloaded into the shadow), at page granularity.
        void noteForeignWrite(uint32_t page, uint32_t count)
        {
            ++m_gen;
            for (uint32_t i = 0; i < count && i < kPages; ++i)
                m_pageGen[(page + i) & (kPages - 1u)] = m_gen;
        }

        // A render target was created, grown or dropped: its texture's contents came from somewhere
        // other than the uploads the gate saw.
        void noteTargetsChanged() { m_targetsGen = ++m_gen; }

        void noteTex(Tex reason) { ++m_tally.tex[static_cast<size_t>(reason)]; }

        void reset()
        {
            m_rects.clear();
            m_blockGen.fill(0u);
            m_pageGen.fill(0u);
            m_targetsGen = 0u;
            m_gen = 1u;
        }

        // One call per Upload command. `whole`: this call carries the entire rectangle. `blocks`: what
        // blocksOf returned for the rectangle (empty = no map). `page`/`span`: the pages the backend
        // marks for it (the fallback stamp when there is no block map). `underGpu`: a render target
        // has GPU-drawn rows over the rectangle since its last download. `skipEnabled`: the knob.
        // When the result says skip, the caller must not write the shadow and must not mark anything.
        Decision decide(const GsGlUploadIdentity::Key &key, const uint8_t *data, size_t size, bool whole,
                        const std::vector<uint32_t> &blocks, uint32_t page, uint32_t span, bool underGpu,
                        bool skipEnabled)
        {
            Decision d;
            uint64_t hash = 0u;
            if (whole && !blocks.empty())
            {
                hash = hashBytes(data, size);
                const auto it = m_rects.find(key);
                if (it == m_rects.end())
                    d.reason = Reason::New;
                else if (it->second.hash != hash || it->second.size != size)
                    d.reason = Reason::Changed;
                else if (!untouchedSince(it->second.stamp, blocks))
                    d.reason = Reason::SameRewritten;
                else if (underGpu)
                    d.reason = Reason::SameUnderGpu;
                else
                    d.reason = Reason::SameFree;
            }
            d.skip = skipEnabled && d.reason == Reason::SameFree;
            ++m_tally.uploads[static_cast<size_t>(d.reason)];
            if (d.skip)
            {
                ++m_tally.skipped;
                return d;
            }
            // Performed: stamp what it writes, then remember it (whole rectangles only).
            ++m_gen;
            if (blocks.empty())
            {
                for (uint32_t i = 0; i < span && i < kPages; ++i)
                    m_pageGen[(page + i) & (kPages - 1u)] = m_gen;
            }
            else
            {
                for (uint32_t b : blocks)
                    m_blockGen[b & (kBlocks - 1u)] = m_gen;
            }
            if (whole && !blocks.empty())
            {
                if (m_rects.size() >= kMaxRects && m_rects.find(key) == m_rects.end())
                    m_rects.clear();
                m_rects[key] = Entry{hash, static_cast<uint64_t>(size), m_gen};
            }
            return d;
        }

        Tally take()
        {
            const Tally t = m_tally;
            m_tally = Tally{};
            return t;
        }
        const Tally &tally() const { return m_tally; }

    private:
        struct Entry
        {
            uint64_t hash = 0;
            uint64_t size = 0;
            uint64_t stamp = 0;   // m_gen when this upload stamped its blocks
        };

        bool untouchedSince(uint64_t stamp, const std::vector<uint32_t> &blocks) const
        {
            if (m_targetsGen > stamp)
                return false;
            for (uint32_t b : blocks)
                if (m_blockGen[b & (kBlocks - 1u)] > stamp || m_pageGen[(b >> 5) & (kPages - 1u)] > stamp)
                    return false;
            return true;
        }

        std::unordered_map<GsGlUploadIdentity::Key, Entry, GsGlUploadIdentity::KeyHash> m_rects;
        std::array<uint64_t, kBlocks> m_blockGen{};
        std::array<uint64_t, kPages> m_pageGen{};
        uint64_t m_targetsGen = 0;
        uint64_t m_gen = 1;
        Tally m_tally;
    };
}
