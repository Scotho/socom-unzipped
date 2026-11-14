// Sprint 19 task B1: the function-coverage bitmap. What it records and its blind spot: runtime/coverage_bitmap.h.
#include "runtime/coverage_bitmap.h"

#include "ps2x/knobs.h"

#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <filesystem>
#include <iostream>
#include <mutex>
#include <string>
#include <system_error>
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
        // A raw pointer, not a static unique_ptr: on the std::exit path (the LoadExecPS2 reboot) static destruction
        // would free the bitmap while the EE thread can still mark it. Only disable() (tests) frees it; at process
        // exit it is deliberately left to the OS.
        std::atomic<uint8_t> *s_storage = nullptr;
        uint32_t s_tableBase = 0u;
        uint32_t s_byteCount = 0u;
        std::string s_dumpPath;
        std::mutex s_writeMutex;   // serialises writeDump with enable/disable

        // The periodic writer. Heap-allocated and never freed, so no static destructor meets a joinable thread;
        // flush() stops and joins it before the final write.
        struct Writer
        {
            std::mutex mutex;
            std::condition_variable cv;
            bool stop = false;
            std::thread thread;
        };
        Writer *s_writer = nullptr;

        void putLe32(std::vector<uint8_t> &out, uint32_t v)
        {
            for (int i = 0; i < 4; ++i)
                out.push_back(static_cast<uint8_t>(v >> (8 * i)));
        }

        void freeLocked()
        {
            detail::g_bits = nullptr;
            detail::g_slotCount = 0u;
            delete[] s_storage;
            s_storage = nullptr;
            s_byteCount = 0u;
            s_tableBase = 0u;
            s_dumpPath.clear();
        }

        void stopWriter()
        {
            Writer *w = s_writer;
            if (!w || !w->thread.joinable() || w->thread.get_id() == std::this_thread::get_id())
                return;
            {
                std::lock_guard<std::mutex> lock(w->mutex);
                w->stop = true;
            }
            w->cv.notify_all();
            w->thread.join();
        }
    }

    void enable(uint32_t tableBase, uint32_t slotCount, const std::string &dumpPath)
    {
        std::lock_guard<std::mutex> lock(s_writeMutex);
        freeLocked();
        s_byteCount = (slotCount + 7u) / 8u;
        s_storage = new std::atomic<uint8_t>[s_byteCount];
        for (uint32_t i = 0; i < s_byteCount; ++i)
            s_storage[i].store(0u, std::memory_order_relaxed);
        s_tableBase = tableBase;
        s_dumpPath = dumpPath;
        detail::g_slotCount = slotCount;
        detail::g_bits = s_storage;
    }

    void disable()
    {
        std::lock_guard<std::mutex> lock(s_writeMutex);
        freeLocked();
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
        // std::filesystem::rename replaces an existing file (MoveFileExW with REPLACE_EXISTING on Windows), so the
        // old dump is never removed first: a kill at any point leaves a whole dump at path.
        std::error_code ec;
        std::filesystem::rename(tmp, path, ec);
        if (ec)
        {
            std::remove(tmp.c_str());
            return false;
        }
        return true;
    }

    bool flush()
    {
        stopWriter();
        std::string path;
        {
            std::lock_guard<std::mutex> lock(s_writeMutex);
            if (!detail::g_bits || s_dumpPath.empty())
                return false;
            path = s_dumpPath;
        }
        if (!writeDump(path))
        {
            std::cout << "[coverage] exit: could not write " << path << std::endl;
            return false;
        }
        std::cout << "[coverage] exit: " << hitCount() << " slots hit, written to " << path << std::endl;
        return true;
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
        const std::string path(e);
        enable(tableBase, slotCount, path);
        std::cout << "[coverage] PS2X_COVERAGE: " << slotCount << " table slots from 0x" << std::hex << tableBase
                  << std::dec << ", written to " << path
                  << " every 10 s and when the runner exits (a killed run keeps the last 10 s write)" << std::endl;
        Writer *writer = new Writer;
        s_writer = writer;
        writer->thread = std::thread([writer, path] {
            Writer *w = writer;
            std::unique_lock<std::mutex> lock(w->mutex);
            while (!w->cv.wait_for(lock, std::chrono::seconds(10), [w] { return w->stop; }))
            {
                lock.unlock();
                writeDump(path);
                lock.lock();
            }
        });
        // The runner's own endings call flush() before std::_Exit (main.cpp), which runs no atexit hook; this one
        // covers the std::exit paths (the LoadExecPS2 reboot).
        std::atexit([] { (void)flush(); });
    }
}
