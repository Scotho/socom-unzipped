#pragma once
// SOCOM II's auto-exposure pixel readback (FUN_003b24c0, bound as socom2_LumReadPixel): the guest hands a
// 7-quadword VIF1 packet -- VIF codes, a GIF tag and A+D writes of BITBLTBUF / TRXPOS / TRXREG / TRXDIR (a
// local->host transfer, 4x1 pixels of the frame buffer) -- then reads one quadword back through the VIF1
// reverse FIFO into `out` and takes the first pixel's R, G, B. The runtime has no reverse-FIFO DMA, so the
// override reads the pixels straight out of GS memory (the GL backend downloads GPU-drawn pages on read)
// and writes them where the DMA would have. research/31 section 13: the stubbed grey pixel this replaced
// made the exposure thread compute a zero brighten (ALPHA FIX 0 instead of the console's 93) and every
// gameplay frame drew 1.73x too dark, the water's dark bed pass among it.
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <functional>

namespace socom2_lum
{
    struct Transfer
    {
        uint32_t sbp = 0, sbw = 0, spsm = 0;   // BITBLTBUF source
        uint32_t ssax = 0, ssay = 0;           // TRXPOS source origin
        uint32_t rrw = 0, rrh = 0;             // TRXREG
        uint32_t dir = 3;                      // TRXDIR (1 = local -> host)
    };

    // Parse the A+D register writes of a VIF1/GIF packet of `qwords` 16-byte words. Returns false when no
    // TRXDIR write was found.
    inline bool parseTransfer(const uint8_t *packet, size_t qwords, Transfer &t)
    {
        bool sawDir = false;
        for (size_t i = 0; i < qwords; ++i)
        {
            uint64_t lo = 0, hi = 0;
            std::memcpy(&lo, packet + i * 16, 8);
            std::memcpy(&hi, packet + i * 16 + 8, 8);
            switch (hi & 0xFFu)
            {
            case 0x50:   // BITBLTBUF
                t.sbp = static_cast<uint32_t>(lo & 0x3FFFu);
                t.sbw = static_cast<uint32_t>((lo >> 16) & 0x3Fu);
                t.spsm = static_cast<uint32_t>((lo >> 24) & 0x3Fu);
                break;
            case 0x51:   // TRXPOS
                t.ssax = static_cast<uint32_t>(lo & 0x7FFu);
                t.ssay = static_cast<uint32_t>((lo >> 16) & 0x7FFu);
                break;
            case 0x52:   // TRXREG
                t.rrw = static_cast<uint32_t>(lo & 0xFFFu);
                t.rrh = static_cast<uint32_t>((lo >> 32) & 0xFFFu);
                break;
            case 0x53:   // TRXDIR
                t.dir = static_cast<uint32_t>(lo & 3u);
                sawDir = true;
                break;
            default:
                break;
            }
        }
        return sawDir;
    }

    using ReadPixel = std::function<uint32_t(uint32_t psm, uint32_t bp, uint32_t bw, uint32_t x, uint32_t y)>;

    // The GL backend serves a CPU read of GPU-drawn pages by syncing the render thread first, which blocks the EE;
    // the exposure thread reads ~176 cells per pass, so syncing on every one starved the main thread's pad polling
    // (s6_lum5: eighteen unanswered pop-up presses). One sync per SYNC_INTERVAL_MS is plenty for an exposure
    // average; the other cells read the copy that sync left behind.
    constexpr uint64_t kLumSyncIntervalMs = 100;

    inline bool syncDue(uint64_t nowMs, uint64_t lastSyncMs, uint64_t intervalMs = kLumSyncIntervalMs)
    {
        return lastSyncMs == 0 || nowMs < lastSyncMs || nowMs - lastSyncMs >= intervalMs;
    }

    // Perform the readback the guest's reverse DMA would have: up to `outBytes` of pixels (row-major from
    // the TRXPOS origin, 4 bytes each for CT32) into `out`. Returns the number of bytes written; 0 when the
    // packet is not a local->host transfer.
    inline size_t readbackPixels(const uint8_t *packet, size_t qwords, const ReadPixel &read, uint8_t *out, size_t outBytes)
    {
        Transfer t;
        if (!parseTransfer(packet, qwords, t) || t.dir != 1u || t.rrw == 0u || t.rrh == 0u)
            return 0;
        size_t written = 0;
        for (uint32_t y = 0; y < t.rrh && written + 4 <= outBytes; ++y)
            for (uint32_t x = 0; x < t.rrw && written + 4 <= outBytes; ++x)
            {
                const uint32_t px = read(t.spsm, t.sbp, t.sbw, t.ssax + x, t.ssay + y);
                std::memcpy(out + written, &px, 4);
                written += 4;
            }
        return written;
    }
}
