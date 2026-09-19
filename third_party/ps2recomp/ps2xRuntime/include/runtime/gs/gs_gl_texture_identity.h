#pragma once

// Sprint 8 Goal 2b, R123: the fix moves to the CONSUMER.
//
// Task 1 measured the menus' transfer= column and found 89-93% of it inside flushBatch, and 85-93%
// of THAT inside resolveTexture: 551-1385 texture decodes a second, every one of them replacing a
// live cache entry, against 26-52 cached textures. The whole texture cache is thrown away and
// rebuilt every frame. The reason is not that the menu atlas changed -- it does not -- but that
// markShadowPages (gs_gl_backend.cpp:1843-1848) bumps m_generation on every upload, and
// resolveTexture's gate compares generations, not content.
//
// R122 tried to stop the bumps at the source by skipping identical uploads. It is implemented,
// measured and superseded: it fired on 4% of uploads (R118's render-target guard legitimately
// refusing 84% of the identical ones) and its per-upload invalidation sweep cost ~84 ms/s, more
// than it saved. So the entry, not the write, is what gets the content test: a cached texture
// carries a 64-bit hash of the exact source bytes it was decoded from, and the stale-generation
// branch re-hashes the current shadow before it deletes anything. Same bytes -> the GL texture is
// still correct -> restamp its generation and hand it back.
//
// What is hashed, and in what order, is decodeTexture's own read order (gs_gl_backend.cpp:3164
// onward): GSMem::ReadSpan(psm, vram, tbp0, tbw, 0, y, width, row) for y in [0, height), each row's
// `width` texel values mixed in left to right; then, for an indexed format, the 256 CLUT entries
// the decode resolved (through resolveClutIndex, so csa / csm / cou / cov are already applied).
// Mixing the RESOLVED entries rather than the raw palette block is deliberate: a palette write
// outside this texture's csa window is never read by its decode and must not force one.
//
// Header-only and free of GL includes on purpose, so ps2xTest can check the arithmetic without a
// context -- the same reason gs_gl_target_extent.h and gs_gl_upload_trace.h are.

#include <cstddef>
#include <cstdint>

#include "runtime/gs/ps2_gs_memory.h"

namespace GsGlTextureIdentity
{
    // 0 is the sentinel for "this source cannot be hashed": the caller must then decode as before.
    constexpr uint64_t kUnhashable = 0u;

    inline uint64_t seed() { return 1469598103934665603ull; }   // FNV-1a 64 offset basis

    inline uint64_t mix(uint64_t h, uint64_t v)
    {
        h ^= v;
        h *= 1099511628211ull;                                   // FNV-1a 64 prime
        return h;
    }

    // The texel source, exactly as decodeTexture reads it. `rowScratch` must hold `width` uint32_t.
    // Returns kUnhashable when GSMem has no span reader for the format, so the caller falls back to
    // today's delete-and-decode instead of guessing.
    inline uint64_t hashTexels(const uint8_t *vram, uint32_t psm, uint32_t tbp0, uint32_t tbw,
                               uint32_t width, uint32_t height, uint32_t *rowScratch, uint64_t h)
    {
        if (vram == nullptr || rowScratch == nullptr || width == 0u || height == 0u)
            return kUnhashable;
        if (!GSMem::ReadSpan(psm, const_cast<uint8_t *>(vram), tbp0, tbw, 0u, 0u, 0u, rowScratch))
            return kUnhashable;
        // The extent is part of the identity: the same bytes at another width or height are a
        // different texture, and the cache key already says so -- this keeps the hash honest if it
        // is ever compared across keys.
        h = mix(h, (static_cast<uint64_t>(width) << 32) | height);
        h = mix(h, (static_cast<uint64_t>(psm) << 32) | tbw);
        for (uint32_t y = 0; y < height; ++y)
        {
            GSMem::ReadSpan(psm, const_cast<uint8_t *>(vram), tbp0, tbw, 0u, y, width, rowScratch);
            for (uint32_t x = 0; x < width; ++x)
                h = mix(h, rowScratch[x]);
        }
        return h == kUnhashable ? 1u : h;    // never collide with the sentinel
    }

    // The 256 CLUT entries the decode resolved, in index order.
    inline uint64_t hashClut(const uint32_t *clut256, uint64_t h)
    {
        if (clut256 == nullptr)
            return h;
        for (uint32_t i = 0; i < 256u; ++i)
            h = mix(h, clut256[i]);
        return h == kUnhashable ? 1u : h;
    }
}
