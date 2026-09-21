#include "runtime/gs/gs_stall_coalescer.h"
#include "runtime/gs/ps2_gs_memory.h"

#include <algorithm>
#include <cstring>

void GsStallCoalescer::engage()
{
    m_active = true;
    m_pagesOnly = false;
    m_engagementCommands = 0;
    m_engagementBytes = 0;
}

// ---------------------------------------------------------------------------------------------
// Absorbing: remember where, never what
// ---------------------------------------------------------------------------------------------
namespace
{
    uint64_t rectArea(const GsStallCoalescer::Rect &r)
    {
        return static_cast<uint64_t>(r.x1 - r.x0) * (r.y1 - r.y0);
    }

    uint64_t overlapArea(const GsStallCoalescer::Rect &a, const GsStallCoalescer::Rect &b)
    {
        const uint32_t x0 = std::max(a.x0, b.x0), x1 = std::min(a.x1, b.x1);
        const uint32_t y0 = std::max(a.y0, b.y0), y1 = std::min(a.y1, b.y1);
        if (x1 <= x0 || y1 <= y0)
            return 0u;
        return static_cast<uint64_t>(x1 - x0) * (y1 - y0);
    }

    GsStallCoalescer::Rect boundingBox(const GsStallCoalescer::Rect &a, const GsStallCoalescer::Rect &b)
    {
        GsStallCoalescer::Rect u = a;
        u.x0 = std::min(a.x0, b.x0);
        u.y0 = std::min(a.y0, b.y0);
        u.x1 = std::max(a.x1, b.x1);
        u.y1 = std::max(a.y1, b.y1);
        return u;
    }

    bool contains(const GsStallCoalescer::Rect &outer, const GsStallCoalescer::Rect &inner)
    {
        return inner.x0 >= outer.x0 && inner.y0 >= outer.y0 && inner.x1 <= outer.x1 && inner.y1 <= outer.y1;
    }

    GsStallCoalescer::Rect rectOfTransfer(const GSTransferCommand &t)
    {
        GsStallCoalescer::Rect r;
        r.dbp = t.bitbltbuf.dbp;
        r.dbw = t.bitbltbuf.dbw;
        r.dpsm = t.bitbltbuf.dpsm;
        r.x0 = t.trxpos.dsax;
        r.y0 = t.trxpos.dsay;
        r.x1 = r.x0 + t.trxreg.rrw;
        r.y1 = r.y0 + t.trxreg.rrh;
        return r;
    }
}

void GsStallCoalescer::markPages(uint32_t page, uint32_t pageCount)
{
    for (uint32_t p = page; p < page + pageCount && p < kPageCount; ++p)
        m_pages[p / 64u] |= 1ull << (p % 64u);
}

void GsStallCoalescer::mergeRect(const Rect &r)
{
    if (r.x1 <= r.x0 || r.y1 <= r.y0)
        return; // an empty transfer writes nothing
    // A format the packer cannot read back goes the page way, which is CT32 and always readable.
    // The page fallback gives up the rectangle table for good: from here on only the page mask
    // grows, and it is 64 bytes.
    const auto fallbackToPages = [this]
    {
        m_pagesOnly = true;
        m_rects.clear();
        m_rectCount = 0;
        m_rectBytes = 0;
    };
    if (m_pagesOnly)
        return;
    if (streamBitsPerPixel(r.dpsm) == 0u)
    {
        fallbackToPages();
        return;
    }
    const Key key{r.dbp, r.dbw, r.dpsm};
    auto it = m_rects.find(key);
    if (it == m_rects.end())
    {
        if (m_rectCount >= kMaxRects)
        {
            fallbackToPages();
            return;
        }
        KeyRects kr;
        kr.rects.push_back(r);
        kr.order = ++m_touchSerial;
        m_rects.emplace(key, std::move(kr));
        ++m_rectCount;
        m_rectBytes += rectBytes(r);
    }
    else
    {
        KeyRects &kr = it->second;
        kr.order = ++m_touchSerial;
        // Tiling: the union is exactly the two rectangles (the movie's 16x16 blocks growing a row,
        // a completed row joining the rows above it), so merging loses no exactness.
        const auto tight = [](const Rect &a, const Rect &b, Rect &u)
        {
            u = boundingBox(a, b);
            return rectArea(u) == rectArea(a) + rectArea(b) - overlapArea(a, b);
        };
        bool placed = false;
        for (Rect &e : kr.rects)
        {
            if (contains(e, r))
            {
                placed = true; // already covered: the re-anchor reads the final bytes anyway
                break;
            }
            Rect u;
            if (tight(e, r, u))
            {
                m_rectBytes -= rectBytes(e);
                e = u;
                m_rectBytes += rectBytes(e);
                placed = true;
                break;
            }
        }
        if (!placed)
        {
            if (kr.rects.size() >= kMaxRectsPerKey)
            {
                // Too many disjoint pieces at one destination: their bounding box, which is what a
                // whole-frame tiling ends as anyway.
                Rect box = r;
                for (const Rect &e : kr.rects)
                {
                    box = boundingBox(box, e);
                    m_rectBytes -= rectBytes(e);
                }
                m_rectCount -= kr.rects.size() - 1u;
                kr.rects.clear();
                kr.rects.push_back(box);
                m_rectBytes += rectBytes(box);
            }
            else
            {
                kr.rects.push_back(r);
                ++m_rectCount;
                m_rectBytes += rectBytes(r);
            }
        }
        // Compaction: a piece that just grew may now tile with another (the row that completed
        // against the rows above it). At most kMaxRectsPerKey pieces, so this is cheap.
        for (bool merged = true; merged;)
        {
            merged = false;
            for (size_t i = 0; i < kr.rects.size() && !merged; ++i)
                for (size_t j = i + 1u; j < kr.rects.size() && !merged; ++j)
                {
                    Rect u;
                    if (contains(kr.rects[i], kr.rects[j]) || contains(kr.rects[j], kr.rects[i]) || tight(kr.rects[i], kr.rects[j], u))
                    {
                        if (!tight(kr.rects[i], kr.rects[j], u))
                            u = boundingBox(kr.rects[i], kr.rects[j]);
                        m_rectBytes -= rectBytes(kr.rects[i]) + rectBytes(kr.rects[j]);
                        kr.rects[i] = u;
                        kr.rects.erase(kr.rects.begin() + static_cast<std::ptrdiff_t>(j));
                        --m_rectCount;
                        m_rectBytes += rectBytes(u);
                        merged = true;
                    }
                }
        }
    }
    if (m_rectCount > kMaxRects || m_rectBytes > kVramBytes)
        fallbackToPages();
}

void GsStallCoalescer::noteTransfer(const GSTransferCommand &t, uint32_t page, uint32_t pageCount, uint64_t bytes)
{
    ++m_engagementCommands;
    m_engagementBytes += bytes;
    // host->local (0) writes as its chunks arrive; local->local (2) wrote at BeginTransfer on the
    // game thread; local->host (1) reads and writes nothing; 3 is no transfer.
    if (t.direction == 0u || t.direction == 2u)
    {
        mergeRect(rectOfTransfer(t));
        markPages(page, pageCount);
    }
}

void GsStallCoalescer::noteUpload(const GSTransferCommand &t, uint32_t page, uint32_t pageCount, uint64_t bytes)
{
    ++m_engagementCommands;
    m_engagementBytes += bytes;
    // The chunk's transfer may have been admitted before the engagement (its BeginTransfer is in
    // the queue, its later chunks are not): the rectangle is merged from here too, idempotently.
    if (t.direction == 0u)
    {
        mergeRect(rectOfTransfer(t));
        markPages(page, pageCount);
    }
}

void GsStallCoalescer::noteWriteVram(uint32_t psm, uint32_t base, uint32_t bw, uint32_t x, uint32_t y, uint32_t page, uint64_t bytes)
{
    ++m_engagementCommands;
    m_engagementBytes += bytes;
    Rect r;
    r.dbp = base;
    r.dbw = static_cast<uint8_t>(std::min<uint32_t>(bw, 255u));
    r.dpsm = static_cast<uint8_t>(psm);
    r.x0 = x;
    r.y0 = y;
    r.x1 = x + 1u;
    r.y1 = y + 1u;
    mergeRect(r);
    markPages(page, 1u);
}

void GsStallCoalescer::noteClut(const GSClutLoad &load, uint64_t bytes)
{
    ++m_engagementCommands;
    m_engagementBytes += bytes;
    auto it = m_cluts.find(load.id);
    if (it != m_cluts.end())
    {
        it->second.lastUse = ++m_touchSerial; // same id, same bytes (content-keyed): only the age moves
        return;
    }
    if (m_cluts.size() >= kMaxCluts)
    {
        auto oldest = m_cluts.begin();
        for (auto c = m_cluts.begin(); c != m_cluts.end(); ++c)
            if (c->second.lastUse < oldest->second.lastUse)
                oldest = c;
        m_cluts.erase(oldest);
    }
    ClutEntry &e = m_cluts[load.id];
    e.load = load;
    e.lastUse = ++m_touchSerial;
}

void GsStallCoalescer::noteReset()
{
    m_rects.clear();
    m_rectCount = 0;
    m_rectBytes = 0;
    m_pagesOnly = false;
    m_pages.fill(0u);
    m_cluts.clear();
}

// ---------------------------------------------------------------------------------------------
// The plan
// ---------------------------------------------------------------------------------------------
GsStallCoalescer::Plan GsStallCoalescer::finish()
{
    Plan plan;
    plan.pagesOnly = m_pagesOnly;
    plan.absorbedCommands = m_engagementCommands;
    plan.absorbedBytes = m_engagementBytes;

    std::vector<const ClutEntry *> cluts;
    cluts.reserve(m_cluts.size());
    for (const auto &kv : m_cluts)
        cluts.push_back(&kv.second);
    std::sort(cluts.begin(), cluts.end(), [](const ClutEntry *a, const ClutEntry *b) { return a->lastUse < b->lastUse; });
    plan.cluts.reserve(cluts.size());
    for (const ClutEntry *e : cluts)
        plan.cluts.push_back(e->load);

    if (m_pagesOnly)
    {
        for (uint32_t p = 0; p < kPageCount; ++p)
            if (m_pages[p / 64u] & (1ull << (p % 64u)))
                plan.rects.push_back(pageRect(p));
    }
    else
    {
        std::vector<const KeyRects *> keys;
        keys.reserve(m_rects.size());
        for (const auto &kv : m_rects)
            keys.push_back(&kv.second);
        std::sort(keys.begin(), keys.end(), [](const KeyRects *a, const KeyRects *b) { return a->order < b->order; });
        plan.rects.reserve(m_rectCount);
        for (const KeyRects *kr : keys)
            for (const Rect &r : kr->rects)
                plan.rects.push_back(r);
    }

    m_rects.clear();
    m_rectCount = 0;
    m_rectBytes = 0;
    m_pagesOnly = false;
    m_pages.fill(0u);
    m_cluts.clear();
    m_engagementCommands = 0;
    m_engagementBytes = 0;
    m_active = false;
    return plan;
}

uint64_t GsStallCoalescer::workingSetBytes() const
{
    return static_cast<uint64_t>(m_rects.size()) * (sizeof(Key) + sizeof(KeyRects)) +
           static_cast<uint64_t>(m_rectCount) * sizeof(Rect) +
           static_cast<uint64_t>(m_cluts.size()) * (sizeof(uint64_t) + sizeof(ClutEntry)) +
           sizeof(m_pages);
}

uint64_t GsStallCoalescer::plannedRectBytes() const
{
    if (!m_pagesOnly)
        return m_rectBytes;
    uint64_t pages = 0;
    for (uint64_t word : m_pages)
        for (uint64_t w = word; w != 0u; w &= w - 1u)
            ++pages;
    return pages * 8192ull;
}

size_t GsStallCoalescer::rectCount() const { return m_rectCount; }
size_t GsStallCoalescer::clutCount() const { return m_cluts.size(); }

// ---------------------------------------------------------------------------------------------
// The re-anchor's data: pure functions over a VRAM image
// ---------------------------------------------------------------------------------------------
GSTransferCommand GsStallCoalescer::transferFor(const Rect &r)
{
    GSTransferCommand t;
    t.bitbltbuf.dbp = r.dbp;
    t.bitbltbuf.dbw = r.dbw;
    t.bitbltbuf.dpsm = r.dpsm;
    t.trxpos.dsax = static_cast<uint16_t>(std::min<uint32_t>(r.x0, 0xFFFFu));
    t.trxpos.dsay = static_cast<uint16_t>(std::min<uint32_t>(r.y0, 0xFFFFu));
    t.trxpos.dir = 0u;
    t.trxreg.rrw = static_cast<uint16_t>(std::min<uint32_t>(r.x1 - r.x0, 0xFFFFu));
    t.trxreg.rrh = static_cast<uint16_t>(std::min<uint32_t>(r.y1 - r.y0, 0xFFFFu));
    t.direction = 0u;
    return t;
}

GsStallCoalescer::Rect GsStallCoalescer::pageRect(uint32_t page)
{
    // One GS page is 8 KB whatever its format; as CT32 with a 64-pixel-wide buffer that is exactly
    // the 64x32 pixels at rows 0..31 of block page*32 (32 blocks of 256 bytes).
    Rect r;
    r.dbp = page << 5;
    r.dbw = 1u;
    r.dpsm = static_cast<uint8_t>(GS_PSM_CT32);
    r.x0 = 0u;
    r.y0 = 0u;
    r.x1 = 64u;
    r.y1 = 32u;
    return r;
}

uint32_t GsStallCoalescer::streamBitsPerPixel(uint8_t psm)
{
    // The IMAGE stream's packing (GSCpuBackend::UploadImage), which is NOT the storage size:
    // CT24 travels as three bytes although it occupies a 32-bit word.
    switch (psm)
    {
    case GS_PSM_CT32:
    case GS_PSM_Z32:
        return 32u;
    case GS_PSM_CT24:
    case GS_PSM_Z24:
        return 24u;
    case GS_PSM_CT16:
    case GS_PSM_CT16S:
    case GS_PSM_Z16:
    case GS_PSM_Z16S:
        return 16u;
    case GS_PSM_T8:
    case GS_PSM_T8H:
        return 8u;
    case GS_PSM_T4:
    case GS_PSM_T4HL:
    case GS_PSM_T4HH:
        return 4u;
    default:
        return 0u;
    }
}

uint64_t GsStallCoalescer::rectBytes(const Rect &r)
{
    if (r.x1 <= r.x0 || r.y1 <= r.y0)
        return 0u;
    const uint64_t pixels = rectArea(r);
    return (pixels * streamBitsPerPixel(r.dpsm) + 7u) / 8u;
}

bool GsStallCoalescer::packPixels(const uint8_t *vram, uint32_t psm, uint32_t dbp, uint32_t dbw, uint32_t x0, uint32_t y0,
                                  uint32_t width, uint64_t pixelCount, std::vector<uint8_t> &out)
{
    const uint32_t bits = streamBitsPerPixel(static_cast<uint8_t>(psm));
    if (bits == 0u || width == 0u || !vram)
        return false;
    out.clear();
    if (pixelCount == 0u)
        return true;
    out.resize(static_cast<size_t>((pixelCount * bits + 7u) / 8u), 0u);
    const uint32_t bw = std::max<uint32_t>(dbw, 1u);
    uint8_t *mem = const_cast<uint8_t *>(vram); // GSMem reads through a non-const pointer; nothing is written
    std::vector<uint32_t> row(width);
    uint64_t done = 0u;
    size_t offset = 0u;
    uint64_t nibble = 0u; // 4-bit formats: one continuous nibble stream, low nibble first, across rows
    while (done < pixelCount)
    {
        const uint32_t col = static_cast<uint32_t>(done % width);
        const uint32_t y = y0 + static_cast<uint32_t>(done / width);
        const uint32_t n = static_cast<uint32_t>(std::min<uint64_t>(width - col, pixelCount - done));
        if (!GSMem::ReadSpan(psm, mem, dbp, bw, x0 + col, y, n, row.data()))
            return false;
        for (uint32_t i = 0; i < n; ++i)
        {
            const uint32_t v = row[i];
            switch (bits)
            {
            case 32:
                std::memcpy(out.data() + offset, &v, 4u);
                offset += 4u;
                break;
            case 24:
                out[offset] = static_cast<uint8_t>(v);
                out[offset + 1u] = static_cast<uint8_t>(v >> 8);
                out[offset + 2u] = static_cast<uint8_t>(v >> 16);
                offset += 3u;
                break;
            case 16:
            {
                const uint16_t h = static_cast<uint16_t>(v);
                std::memcpy(out.data() + offset, &h, 2u);
                offset += 2u;
                break;
            }
            case 8:
                out[offset++] = static_cast<uint8_t>(v);
                break;
            default: // 4
                if ((nibble & 1u) == 0u)
                    out[nibble >> 1] = static_cast<uint8_t>(v & 0x0Fu);
                else
                    out[nibble >> 1] |= static_cast<uint8_t>((v & 0x0Fu) << 4);
                ++nibble;
                break;
            }
        }
        done += n;
    }
    return true;
}

bool GsStallCoalescer::packRect(const uint8_t *vram, const Rect &r, std::vector<uint8_t> &out)
{
    if (r.x1 <= r.x0 || r.y1 <= r.y0)
    {
        out.clear();
        return false;
    }
    return packPixels(vram, r.dpsm, r.dbp, r.dbw, r.x0, r.y0, r.x1 - r.x0, rectArea(r), out);
}

bool GsStallCoalescer::packPrefix(const uint8_t *vram, const GSTransferCommand &t, uint32_t copiedPixels, std::vector<uint8_t> &out)
{
    const uint64_t total = static_cast<uint64_t>(t.trxreg.rrw) * t.trxreg.rrh;
    if (t.trxreg.rrw == 0u || total == 0u)
    {
        out.clear();
        return false;
    }
    return packPixels(vram, t.bitbltbuf.dpsm, t.bitbltbuf.dbp, t.bitbltbuf.dbw, t.trxpos.dsax, t.trxpos.dsay, t.trxreg.rrw,
                      std::min<uint64_t>(copiedPixels, total), out);
}
