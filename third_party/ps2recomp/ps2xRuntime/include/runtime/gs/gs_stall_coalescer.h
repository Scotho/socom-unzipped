#pragma once

#include "runtime/gs/gs_types.h"

#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <unordered_map>
#include <vector>

// Sprint 10 Goal 11 (Q6): the third bound on the GL backend's command queue -- the STATE-carrying
// stream while the replay is latched stalled.
//
// The first two bounds are in gs_frame_backpressure.h: GsFrameBackpressure bounds the FRAMES the
// recorder may run ahead of the replay (R35), and GsPendingCap bounds the queue's BYTES once the
// replay latches stalled by dropping draw work, which the next guest frame records again (Sprint 7
// Task 1b). Neither could touch the commands that carry state -- an upload, a transfer, a CLUT
// snapshot, a VRAM write -- because dropping one corrupts every frame drawn after the stall. So
// that stream stayed unbounded (KNOWN: "once the replay latches stalled, GsPendingCap::admit keeps
// every state-carrying command unbounded"), R124 put a 1 GB ceiling under it that the recorder
// waits at (with a 5 s per-command escape that admits anyway), and the 8 GB VM with no swap died
// of std::bad_alloc under a hung GL thread on the title movie (s8_vm_title_audio3).
//
// What that stream is made of, per guest frame of a latched stall: the title movie is ~1040
// BeginTransfer+Upload pairs (one 16x16 CT32 tile each: two Cmd records and 1 KB of pixels),
// gameplay is streamed textures plus one ClutLoad (a 2 KB palette snapshot) per palette alternation
// -- SOCOM II alternates palettes on consecutive draws -- plus one Present. Every one of them is a
// write into a memory whose FINAL state the game thread already holds: the game-thread GSCpuBackend
// applies each upload, transfer and VRAM write to the real VRAM before the command is recorded
// (GSGlBackend::UploadImage calls m_cpu->UploadImage first), and a palette snapshot is keyed by
// its content (GS::loadClutIfNeeded: the same bytes get the same id). Replaying that stream after
// the stall only ever reproduces the state the game thread has now. So the policy is: while the
// stall is latched and the byte cap is reached, ABSORB the state-carrying commands instead of
// pending them -- remember WHERE they wrote (a merged destination rectangle per (dbp, dbw, dpsm),
// the touched pages, the newest snapshot per palette id) and nothing else -- and when the latch
// clears, RE-ANCHOR the replay from the game thread's VRAM: one synthesized host->local transfer
// per rectangle carrying the rectangle's bytes as they are now, one ClutLoad per palette id, and
// the in-flight transfer's own state so the chunks the game sends next land where they belong.
// The synthesized commands go through the ordinary Upload path on the render thread (the shadow
// VRAM, the page generations the texture cache revalidates by, the render-target refresh), so the
// frame after the stall is drawn from exactly the VRAM the game has: correct by construction, not
// by replaying history.
//
// Why a rectangle and not a page: refreshRenderTargetsFromShadow refreshes exactly the rows a
// transfer wrote when the transfer is in the target's own layout; a whole page would resurrect the
// rows around it (the movie strip on the typing screen, user report 2026-09-09). Rectangles that
// tile (the movie's blocks) merge into one; disjoint ones stay apart, up to a few per key; past
// kMaxRects keys or kVramBytes of rectangle data the plan falls back to one 64x32 CT32 rectangle
// per touched page -- still exact bytes (every PSM shares the page's 8 KB), coarser refresh.
//
// Bounds, all of them independent of how long the stall lasts: kMaxRects rectangles, kMaxCluts
// palette snapshots, and a re-anchor of at most kVramBytes (VRAM's size) plus those commands. The
// working set during the stall is the rectangle table and the palette table; the pending queue
// stays at GsPendingCap's cap plus one command.
//
// Who decides: GsPendingCap::admit (gs_frame_backpressure.h), the seam that always decided what
// the queue takes -- it now refuses a state-carrying command at the cap while latched and stays
// "absorbing" until the latch clears; this class only remembers and plans. Threads: the recorder's
// (game) thread owns everything but the one cumulative counter the [gs-gl stats] line reads.
class GsStallCoalescer
{
public:
    static constexpr size_t kMaxRects = 512u;              // merged destination rectangles, all keys together
    static constexpr size_t kMaxRectsPerKey = 8u;          // disjoint rectangles kept per (dbp, dbw, dpsm) before they collapse to one
    static constexpr size_t kMaxCluts = 256u;              // palette snapshots kept (the replay's own eviction window is 256 loads)
    static constexpr uint64_t kVramBytes = 4u * 1024u * 1024u;
    static constexpr uint32_t kPageCount = 512u;

    // A destination rectangle in a transfer's layout: pixels [x0, x1) x [y0, y1) of the buffer at
    // block dbp, dbw*64 pixels wide, in format dpsm. transferFor() turns it back into the
    // host->local transfer that writes exactly these pixels.
    struct Rect
    {
        uint32_t dbp = 0;
        uint8_t dbw = 0;
        uint8_t dpsm = 0;
        uint32_t x0 = 0, y0 = 0, x1 = 0, y1 = 0;
    };

    // What the replay needs once the latch clears, in the order it must be applied.
    struct Plan
    {
        std::vector<GSClutLoad> cluts;   // oldest first: the replay evicts by age, so the newest survive
        std::vector<Rect> rects;         // each one a complete synthesized transfer
        bool pagesOnly = false;          // the rects are per-page fallbacks (kMaxRects or kVramBytes was passed)
        uint64_t absorbedCommands = 0;   // what this engagement took instead of pending
        uint64_t absorbedBytes = 0;
    };

    // GsPendingCap::admit decides (the existing seam): at the cap while latched it refuses a
    // state-carrying command and turns "absorbing"; the backend then calls engage() once and
    // noteTransfer/noteUpload/noteWriteVram/noteClut per refused command; when
    // GsPendingCap::reanchorDue says the latch has cleared, finish() hands over the plan.
    void engage();
    bool active() const { return m_active; }

    // Absorbed commands. `bytes` is what the command would have cost the queue (sizeof(Cmd) +
    // data), for the counters; `page`/`pageCount` the destination's page span (GSGlBackend::pageSpan).
    void noteTransfer(const GSTransferCommand &t, uint32_t page, uint32_t pageCount, uint64_t bytes);
    // An Upload chunk: its pixels are already in the game VRAM; `t` is the transfer it belongs to
    // (the last BeginTransfer the game thread saw, admitted or not).
    void noteUpload(const GSTransferCommand &t, uint32_t page, uint32_t pageCount, uint64_t bytes);
    void noteWriteVram(uint32_t psm, uint32_t base, uint32_t bw, uint32_t x, uint32_t y, uint32_t page, uint64_t bytes);
    void noteClut(const GSClutLoad &load, uint64_t bytes);
    // (A Drop verdict is GsPendingCap::noteDropped's: draw work dropped while latched is what its
    // dropped_cmds counter has always meant.)
    // A Reset was posted: both VRAMs are blank after it, so everything remembered so far is moot.
    // Stays engaged -- what the game writes after the Reset still needs re-anchoring.
    void noteReset();

    // The latch cleared: hand over the plan and go idle. Only valid when active().
    Plan finish();

    // The engagement's own memory: the rectangle and palette tables (what "bounded" is measured on).
    uint64_t workingSetBytes() const;
    // Bytes the plan's rectangles would carry if finished now (<= kVramBytes by construction).
    uint64_t plannedRectBytes() const;
    size_t rectCount() const;
    size_t clutCount() const;
    bool pagesOnly() const { return m_pagesOnly; }

    // Cumulative bytes the re-anchors pushed back (atomic: read by the stats line on the render
    // thread; the absorbed counts are GsPendingCap's, next to its drops).
    uint64_t reanchorBytes() const { return m_reanchorBytes.load(std::memory_order_relaxed); }
    void noteReanchorBytes(uint64_t bytes) { m_reanchorBytes.fetch_add(bytes, std::memory_order_relaxed); }

    // --- the re-anchor's data, pure functions over a VRAM image (the game thread's snapshot) ---

    // The host->local transfer that writes exactly `r`.
    static GSTransferCommand transferFor(const Rect &r);
    // The 64x32 CT32 rectangle that covers page `page`'s 8 KB whatever format the page holds.
    static Rect pageRect(uint32_t page);
    // Bytes the IMAGE stream carries for `r`: the upload packing (4/3/2/1 bytes per pixel, 4-bit
    // formats two pixels per byte, a trailing nibble rounded up), NOT the storage size.
    static uint64_t rectBytes(const Rect &r);
    // Pack `r`'s pixels from `vram` exactly as an IMAGE upload of transferFor(r) would deliver them
    // (row-major, GSCpuBackend::UploadImage's byte layout), so UploadImage(out) reproduces the
    // bytes. Returns false for a format with no span reader (the caller falls back to pages).
    static bool packRect(const uint8_t *vram, const Rect &r, std::vector<uint8_t> &out);
    // The first `copiedPixels` pixels of transfer `t`'s rectangle, packed the same way: what a
    // BeginTransfer(t) + UploadImage(out) replays to leave the receiver's transfer state exactly
    // where the game thread's is (GSTransferSnapshot::copiedPixels), so the chunks that follow
    // the re-anchor land in their own rows.
    static bool packPrefix(const uint8_t *vram, const GSTransferCommand &t, uint32_t copiedPixels, std::vector<uint8_t> &out);
    // Stream bytes per pixel times 8 (so 4-bit formats are 4): 0 for a format the packer does not know.
    static uint32_t streamBitsPerPixel(uint8_t psm);

private:
    struct Key
    {
        uint32_t dbp;
        uint8_t dbw;
        uint8_t dpsm;
        bool operator==(const Key &o) const { return dbp == o.dbp && dbw == o.dbw && dpsm == o.dpsm; }
    };
    struct KeyHash
    {
        size_t operator()(const Key &k) const { return (static_cast<size_t>(k.dbp) << 16) ^ (static_cast<size_t>(k.dbw) << 8) ^ k.dpsm; }
    };
    struct KeyRects
    {
        std::vector<Rect> rects; // at most kMaxRectsPerKey; collapsed to the bounding box past that
        uint64_t order = 0;      // last touch, for the plan's order (cosmetic: every rect writes the truth)
    };

    void mergeRect(const Rect &r);
    void markPages(uint32_t page, uint32_t pageCount);
    static bool packPixels(const uint8_t *vram, uint32_t psm, uint32_t dbp, uint32_t dbw, uint32_t x0, uint32_t y0,
                           uint32_t width, uint64_t pixelCount, std::vector<uint8_t> &out);

    bool m_active = false;
    bool m_pagesOnly = false;
    std::unordered_map<Key, KeyRects, KeyHash> m_rects;
    size_t m_rectCount = 0;
    uint64_t m_rectBytes = 0;
    uint64_t m_touchSerial = 0;
    std::array<uint64_t, kPageCount / 64u> m_pages{};
    // Palette snapshots by id with their last load; a re-load only stamps the entry (thousands per
    // frame in gameplay), a new id past kMaxCluts evicts the oldest stamp (a scan of 256, only then).
    struct ClutEntry
    {
        GSClutLoad load;
        uint64_t lastUse = 0;
    };
    std::unordered_map<uint64_t, ClutEntry> m_cluts;
    uint64_t m_engagementCommands = 0;
    uint64_t m_engagementBytes = 0;

    std::atomic<uint64_t> m_reanchorBytes{0};
};
