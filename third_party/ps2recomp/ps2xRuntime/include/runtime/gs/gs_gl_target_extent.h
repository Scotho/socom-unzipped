#pragma once

// Sprint 7 Task 1c (audit 2026-09-17 §2.2 F8/F9): how large a render target has to be.
//
// Every RenderTarget used to be allocated at the maximum stride and the maximum height --
// 1024x1024 native pixels, so 1024*S x 1024*S RGBA8 plus a DEPTH32F attachment of the same
// extent, 128 MB per target at scale 4 -- because the game addresses one base page with
// different FRAME widths (1024-wide at boot, 640-wide in the shell) and every draw had to land
// in the same texture regardless of FBW.
//
// choose() sizes a target from what the game says it is using: FBW gives the stride, and the
// rows the scissor (or the DISPLAY rectangle) reaches give the height. The result is always a
// native extent -- VRAM addressing, page/row bookkeeping and usedHeight are all native and never
// scale (research/14 §3); the caller multiplies by renderScale() for the GL texture.
//
// Safety: a target whose use is not known yet (fbw == 0 or usedHeight == 0) keeps the old full
// 1024x1024 allocation, so nothing is ever under-allocated by not knowing. A target whose use
// grows later -- the boot buffer re-addressed at a wider FBW, a draw whose scissor reaches
// further down -- is grown by the backend (GSGlBackend::growRenderTarget); choose() itself is
// pure and never shrinks anything on its own.
//
// Header-only and free of GL includes on purpose, so ps2xTest can check the arithmetic without a
// context.

#include <cstdint>

namespace GsGlTarget
{
    // The largest buffer the GS can address with one FRAME stride, in native pixels.
    constexpr uint32_t kMaxWidth = 1024u;
    constexpr uint32_t kMaxHeight = 1024u;
    // Rows are rounded up to a 32-row band: the dirty-band bookkeeping in the backend works in
    // 32-row units, and PSMCT32 pages are 32 rows tall.
    constexpr uint32_t kRowQuantum = 32u;
    // Never allocate less than one band-pair; a target that exists at all is drawn into.
    constexpr uint32_t kMinHeight = 64u;

    struct Extent
    {
        uint32_t width = kMaxWidth;
        uint32_t height = kMaxHeight;
    };

    // fbw is in 64-pixel units (the FRAME register's FBW); usedHeight is a native row count.
    inline Extent choose(uint32_t fbw, uint32_t usedHeight)
    {
        Extent e;
        if (fbw == 0u || usedHeight == 0u)
            return e;   // unknown use: the old full allocation
        const uint32_t width = fbw * 64u;
        e.width = width > kMaxWidth ? kMaxWidth : width;
        uint32_t height = ((usedHeight + kRowQuantum - 1u) / kRowQuantum) * kRowQuantum;
        if (height < kMinHeight)
            height = kMinHeight;
        if (height > kMaxHeight)
            height = kMaxHeight;
        e.height = height;
        return e;
    }
}
