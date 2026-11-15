#pragma once

// Sprint 19 task E2: the guest-memory write log the shadow harness (runtime/shadow_harness.h) compares.
//
// While a shadowed call runs, ps2_shadow::g_writeLog -- THREAD-LOCAL -- points at a log on the thread that runs the
// call, and every guest store that thread makes is noted BEFORE it lands: the byte's key, where it lives on the
// host, and its old value. That is enough to read what the call wrote (the bytes now) and to undo it (the old
// values, newest first). Any other host thread (IOP, DMA, audio, render) sees its own g_writeLog, null: it never
// reads, notes into or outlives a log armed elsewhere. (The log once carried its owner's thread id and filtered on
// it; thread_local makes that check always true, so it is gone.)
//
// Where the notes come from:
//   * RDRAM and scratchpad stores of the generated code and of anything else built on ps2_runtime_macros.h's
//     Ps2FastWrite* / WRITE* helpers. Those are inline and run hundreds of thousands of times a frame, so the hook is
//     compiled in only where PS2X_SHADOW_WRITE_LOG is 1 (CMake option PS2X_SHADOW_WRITE_LOG, OFF by default: the
//     default build's stores are unchanged).
//   * The runtime's slow path (PS2Runtime::Store8..128: hardware registers, anything not plain memory) is always
//     hooked, and counts as an I/O store: such a call cannot be run twice, so the harness keeps the original's
//     result and skips the comparison.
//
// Keys: an RDRAM byte is its offset in RDRAM (below 0x02000000); a scratchpad byte is 0x70000000 + its offset.

#include <cstdint>
#include <vector>

namespace ps2_shadow
{
    constexpr uint32_t kScratchpadKeyBase = 0x70000000u;

    struct WriteLog
    {
        struct Byte
        {
            uint32_t key;
            uint8_t *host;
            uint8_t old;
        };

        std::vector<Byte> bytes;
        uint32_t ioStores = 0u;
        uint32_t firstIoAddress = 0u;

        void noteRdram(uint8_t *rdram, uint32_t addr, uint32_t size, uint32_t ramMask)
        {
            for (uint32_t i = 0; i < size; ++i)
            {
                const uint32_t off = (addr + i) & ramMask;
                bytes.push_back({off, rdram + off, rdram[off]});
            }
        }

        void noteHost(uint32_t key, uint8_t *host, uint32_t size)
        {
            for (uint32_t i = 0; i < size; ++i)
                bytes.push_back({key + i, host + i, host[i]});
        }

        void noteIo(uint32_t addr)
        {
            if (ioStores++ == 0u)
                firstIoAddress = addr;
        }

        // Puts every noted byte back to its value before the first note, newest first.
        void undo() const
        {
            for (auto it = bytes.rbegin(); it != bytes.rend(); ++it)
                *it->host = it->old;
        }
    };

    // This thread's armed log: non-null only while this thread runs a shadowed call's original or body.
    extern thread_local constinit WriteLog *g_writeLog;   // constinit: no per-access TLS init check

    inline void noteIoStore(uint32_t addr)
    {
        if (WriteLog *log = g_writeLog)
            log->noteIo(addr);
    }
}
