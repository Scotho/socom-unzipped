// Sprint 19 task B1: the function-coverage bitmap. What it records and its blind spot: runtime/coverage_bitmap.h.
#include "runtime/coverage_bitmap.h"

#include "ps2x/knobs.h"

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <memory>
#include <mutex>
#include <string>
#include <thread>

namespace ps2_coverage
{
    namespace detail
    {
        std::atomic<uint8_t> *g_bits = nullptr;
        uint32_t g_slotCount = 0u;
    }

    namespace
    {
        std::unique_ptr<std::atomic<uint8_t>[]> s_storage;
        uint32_t s_tableBase = 0u;
        uint32_t s_byteCount = 0u;
        std::mutex s_writeMutex;

        void putLe32(std::vector<uint8_t> &out, uint32_t v)
        {
            for (int i = 0; i < 4; ++i)
                out.push_back(static_cast<uint8_t>(v >> (8 * i)));
        }
    }

    void enable(uint32_t tableBase, uint32_t slotCount)
    {
        disable();
        s_byteCount = (slotCount + 7u) / 8u;
        s_storage.reset(new std::atomic<uint8_t>[s_byteCount]);
        for (uint32_t i = 0; i < s_byteCount; ++i)
            s_storage[i].store(0u, std::memory_order_relaxed);
        s_tableBase = tableBase;
        detail::g_slotCount = slotCount;
        detail::g_bits = s_storage.get();
    }

    void disable()
    {
        detail::g_bits = nullptr;
        detail::g_slotCount = 0u;
        s_storage.reset();
        s_byteCount = 0u;
        s_tableBase = 0u;
    }

    bool enabled()
    {
        return detail::g_bits != nullptr;
    }

    bool hit(uint32_t slot)
    {
        if (!detail::g_bits || slot >= detail::g_slotCount)
            return false;
        return (detail::g_bits[slot >> 3].load(std::memory_order_relaxed) & (1u << (slot & 7u))) != 0u;
    }

    uint32_t hitCount()
    {
        uint32_t n = 0u;
        for (uint32_t i = 0; detail::g_bits && i < s_byteCount; ++i)
        {
            uint8_t b = detail::g_bits[i].load(std::memory_order_relaxed);
            for (; b != 0u; b &= static_cast<uint8_t>(b - 1u))
                ++n;
        }
        return n;
    }

    std::vector<uint8_t> serialize()
    {
        std::vector<uint8_t> out;
        if (!detail::g_bits)
            return out;
        out.reserve(16u + s_byteCount);
        out.insert(out.end(), {'P', 'S', '2', 'X', 'C', 'O', 'V', '1'});
        putLe32(out, s_tableBase);
        putLe32(out, detail::g_slotCount);
        for (uint32_t i = 0; i < s_byteCount; ++i)
            out.push_back(detail::g_bits[i].load(std::memory_order_relaxed));
        return out;
    }

    bool writeDump(const std::string &path)
    {
        std::lock_guard<std::mutex> lock(s_writeMutex);
        const std::vector<uint8_t> bytes = serialize();
        if (bytes.empty())
            return false;
        const std::string tmp = path + ".tmp";
        std::FILE *f = std::fopen(tmp.c_str(), "wb");
        if (!f)
            return false;
        const bool ok = std::fwrite(bytes.data(), 1, bytes.size(), f) == bytes.size();
        if (std::fclose(f) != 0 || !ok)
        {
            std::remove(tmp.c_str());
            return false;
        }
        std::remove(path.c_str());   // Windows' rename does not replace an existing file
        return std::rename(tmp.c_str(), path.c_str()) == 0;
    }

    void installFromEnvironment(uint32_t tableBase, uint32_t slotCount)
    {
        static bool s_installed = false;
        if (s_installed)
            return;
        const char *e = ps2x::knob("PS2X_COVERAGE");
        if (!e || !*e)
            return;
        s_installed = true;
        static const std::string s_path(e);
        enable(tableBase, slotCount);
        std::cout << "[coverage] PS2X_COVERAGE: " << slotCount << " table slots from 0x" << std::hex << tableBase
                  << std::dec << ", written to " << s_path << " every 10 s and at exit" << std::endl;
        std::thread([] {
            for (;;)
            {
                std::this_thread::sleep_for(std::chrono::seconds(10));
                writeDump(s_path);
            }
        }).detach();
        std::atexit([] {
            if (writeDump(s_path))
                std::cout << "[coverage] exit: " << hitCount() << " slots hit, written to " << s_path << std::endl;
        });
    }
}
