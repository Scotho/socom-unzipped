#pragma once

// Sprint 8 Goal 2b Task 1's counting question, and only that: "are the uploaded bytes identical
// frame to frame?" -- the number that put the goal on the texture cache. It is the [gs-transfer]
// line's identical= field and nothing depends on it, so it is computed ONLY when
// PS2X_GS_UPLOAD_TRACE is set and costs nothing when it is not.
//
// R122's overlap-keyed cache, its content sample, its per-upload invalidation sweep, the shadow
// generation guard and the upload skip itself all lived here and are GONE: measured at 4% of
// uploads skipped for ~84 ms/s of sweep, the fix moved to the consumer (R123,
// gs_gl_texture_identity.h). What is left is the hash, the rectangle key, and a map remembering the
// last packet written to each rectangle.
//
// Header-only and free of GL includes on purpose, so ps2xTest can check the arithmetic without a
// context -- the same reason gs_gl_target_extent.h and gs_gl_upload_trace.h are.

#include <cstddef>
#include <cstdint>
#include <unordered_map>

namespace GsGlUploadIdentity
{
    inline uint64_t hash64(const uint8_t *data, size_t size)
    {
        uint64_t h = 1469598103934665603ull;               // FNV-1a 64 offset basis
        for (size_t i = 0; i < size; ++i)
        {
            h ^= static_cast<uint64_t>(data[i]);
            h *= 1099511628211ull;                          // FNV-1a 64 prime
        }
        return h;
    }

    // One destination rectangle, exactly as executeUpload knows it from m_currentTransfer.
    struct Key
    {
        uint32_t dbp = 0, dbw = 0, dsax = 0, dsay = 0, rrw = 0, rrh = 0;
        uint32_t dpsm = 0;
        bool operator==(const Key &o) const
        {
            return dbp == o.dbp && dbw == o.dbw && dsax == o.dsax && dsay == o.dsay &&
                   rrw == o.rrw && rrh == o.rrh && dpsm == o.dpsm;
        }
    };

    struct KeyHash
    {
        size_t operator()(const Key &k) const
        {
            uint64_t h = 1469598103934665603ull;
            const uint32_t f[7] = {k.dbp, k.dbw, k.dsax, k.dsay, k.rrw, k.rrh, k.dpsm};
            for (uint32_t v : f)
            {
                h ^= static_cast<uint64_t>(v);
                h *= 1099511628211ull;
            }
            return static_cast<size_t>(h);
        }
    };

    // Diagnostic only: the last packet written to each rectangle. Bounded so a long mission cannot
    // grow it without end; at the bound it starts again rather than evict cleverly, because the
    // number it feeds is a percentage over a 1-second interval.
    constexpr size_t kMaxEntries = 8192u;

    class LastUploads
    {
    public:
        bool matches(const Key &k, uint64_t hash, uint64_t size) const
        {
            const auto it = m_entries.find(k);
            return it != m_entries.end() && it->second.first == hash && it->second.second == size;
        }

        void store(const Key &k, uint64_t hash, uint64_t size)
        {
            if (m_entries.size() >= kMaxEntries && m_entries.find(k) == m_entries.end())
                m_entries.clear();
            m_entries[k] = {hash, size};
        }

        void clear() { m_entries.clear(); }
        size_t size() const { return m_entries.size(); }

    private:
        std::unordered_map<Key, std::pair<uint64_t, uint64_t>, KeyHash> m_entries;
    };
}
