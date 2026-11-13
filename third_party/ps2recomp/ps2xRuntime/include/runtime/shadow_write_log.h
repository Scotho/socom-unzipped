#pragma once

// Sprint 19 task E2: the guest-memory write log the shadow harness (runtime/shadow_harness.h) compares.
//
// While a shadowed call runs, ps2_shadow::g_writeLog points at a log and every guest store made on the thread that
// armed it is noted BEFORE it lands: the byte's key, where it lives on the host, and its old value. That is enough
// to read what the call wrote (the bytes now) and to undo it (the old values, newest first).
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
#include <thread>
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

        std::thread::id owner = std::this_thread::get_id();
        std::vector<Byte> bytes;
        uint32_t ioStores = 0u;
        uint32_t firstIoAddress = 0u;

        bool mine() const { return std::this_thread::get_id() == owner; }

        void noteRdram(uint8_t *rdram, uint32_t addr, uint32_t size, uint32_t ramMask)
        {
            if (!mine())
                return;
            for (uint32_t i = 0; i < size; ++i)
            {
                const uint32_t off = (addr + i) & ramMask;
                bytes.push_back({off, rdram + off, rdram[off]});
            }
        }

        void noteHost(uint32_t key, uint8_t *host, uint32_t size)
        {
            if (!mine())
                return;
            for (uint32_t i = 0; i < size; ++i)
                bytes.push_back({key + i, host + i, host[i]});
        }

        void noteIo(uint32_t addr)
        {
            if (!mine())
                return;
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

    // Non-null only while a shadowed call runs.
    extern WriteLog *g_writeLog;

    inline void noteIoStore(uint32_t addr)
    {
        if (WriteLog *log = g_writeLog)
            log->noteIo(addr);
    }
}
