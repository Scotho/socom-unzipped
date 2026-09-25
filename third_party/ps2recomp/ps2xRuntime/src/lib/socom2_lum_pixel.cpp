// SOCOM II's auto-exposure readback (FUN_003b24c0) answered from GS memory.
// Moved out of game_overrides_socom2.cpp by Sprint 13 Task C8 so the test binary links the real handler rather
// than a stand-in. Runner-only; bound by name through the runtime's stub table (ps2_call_list.h).
#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include "ps2_stubs.h"
#include "runtime/ps2_memory.h"
#include "runtime/socom2_lum_readback.h"

#include <chrono>
#include <cstdint>
#include <iostream>

namespace ps2_stubs
{
    // Bound at recompile time via recomp/socom2.toml: "socom2_LumReadPixel@0x003B24C0".
    // FUN_003b24c0(packet, out) is the auto-exposure thread's framebuffer readback: it sends a 7-qword VIF1
    // packet (BITBLTBUF/TRXPOS/TRXREG/TRXDIR local->host, a 1x4 column of the frame), waits for FINISH,
    // sets BUSDIR and reads one quadword back through the VIF1 FIFO in reverse mode into `out`; the caller
    // (FUN_003b1dd0) takes the first pixel's R, G, B. The runtime has no reverse-FIFO DMA path, and until
    // 2026-09-16 this answered a constant mid-grey pixel -- which made the exposure compute a zero brighten
    // (ALPHA FIX 0 where the console writes 93) and every gameplay frame drew 1.73x too dark (research/31
    // section 13). Now the pixels are read straight out of GS memory (the GL backend downloads GPU-drawn
    // pages on read) and written where the DMA would have put them.
    void socom2_LumReadPixel(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint32_t packetAddr = GPR_U32(ctx, 4);
        const uint32_t outAddr = GPR_U32(ctx, 5);
        const uint8_t *packet = rdram + (packetAddr & PS2_RAM_MASK);
        uint8_t *out = rdram + (outAddr & PS2_RAM_MASK);
        size_t n = 0;
        if (runtime)
        {
            GS &gs = runtime->gs();
            // Never wait on the GPU here (it would hold the single EE host thread for the GL backlog): ask for an
            // asynchronous download once per socom2_lum::kLumSyncIntervalMs and read whatever the last one left.
            static uint64_t s_lastRequestMs = 0;
            const uint64_t nowMs = static_cast<uint64_t>(std::chrono::duration_cast<std::chrono::milliseconds>(
                                                             std::chrono::steady_clock::now().time_since_epoch()).count());
            if (socom2_lum::syncDue(nowMs, s_lastRequestMs))
            {
                s_lastRequestMs = nowMs;
                gs.requestVramReadback();
            }
            n = socom2_lum::readbackPixels(packet, 7, [&](uint32_t psm, uint32_t bp, uint32_t bw, uint32_t x, uint32_t y)
                                           { return gs.PeekVram(psm, bp, bw, x, y); }, out, 16);
        }
        if (n == 0)
        {
            out[0] = 0x80;
            out[1] = 0x80;
            out[2] = 0x80;
            out[3] = 0x80;
        }
        static int logged = 0;
        if (logged++ < 3)
            std::cout << "[socom2] exposure readback FUN_003b24c0 -> " << n << " bytes from GS memory"
                      << (n ? "" : " (no transfer in the packet: grey pixel)") << std::endl;
        SET_GPR_U32(ctx, 2, 0u);
        ctx->pc = GPR_U32(ctx, 31);
    }
}
