#include "HleStats.h"

#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include "ps2x/knobs.h"

#include <array>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <mutex>
#include <sstream>
#include <thread>
#include <utility>

namespace ps2_hle_stats
{
    namespace
    {
        constexpr int kMaxSlots = 512;
        constexpr uint32_t kMaxDistinct = 64u;

        struct Slot
        {
            std::string name;
            uint32_t addr = 0u;
            PS2Runtime::RecompiledFunction original = nullptr;
            bool floatReturn = false;
            uint64_t calls = 0u;
            uint64_t returns = 0u;
            uint64_t first = 0u;
            uint64_t last = 0u;
            uint32_t distinctCount = 0u;
            bool saturated = false;
            std::array<uint64_t, kMaxDistinct> distinct{};
        };

        std::mutex g_mutex;
        Slot g_slots[kMaxSlots];
        int g_slotCount = 0;
        std::chrono::steady_clock::time_point g_start = std::chrono::steady_clock::now();

        bool envOn(const char *name)
        {
            const char *e = ps2x::knob(name);
            if (!e || !*e)
                return false;
            return !(std::strcmp(e, "0") == 0 || std::strcmp(e, "false") == 0 || std::strcmp(e, "off") == 0);
        }

        bool isFloatReturn(const std::string &name)
        {
            return name == "__kernel_cosf" || name == "__kernel_sinf";
        }

        void recordReturn(int n, const R5900Context *ctx)
        {
            Slot &s = g_slots[n];
            uint64_t value = 0u;
            if (s.floatReturn)
            {
                uint32_t bits = 0u;
                std::memcpy(&bits, &ctx->f[0], sizeof(bits));
                value = bits;
            }
            else
            {
                value = GPR_U64(ctx, 2);
            }

            std::lock_guard<std::mutex> lock(g_mutex);
            if (s.returns == 0u)
                s.first = value;
            s.last = value;
            ++s.returns;
            if (s.saturated)
                return;
            for (uint32_t i = 0; i < s.distinctCount; ++i)
            {
                if (s.distinct[i] == value)
                    return;
            }
            if (s.distinctCount < kMaxDistinct)
                s.distinct[s.distinctCount++] = value;
            else
                s.saturated = true;
        }

        template <int N>
        void statsThunk(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
        {
            {
                std::lock_guard<std::mutex> lock(g_mutex);
                ++g_slots[N].calls;
            }
            g_slots[N].original(rdram, ctx, runtime);
            recordReturn(N, ctx);
        }

        template <int... Is>
        constexpr std::array<PS2Runtime::RecompiledFunction, sizeof...(Is)> makeThunks(std::integer_sequence<int, Is...>)
        {
            return {{&statsThunk<Is>...}};
        }

        const std::array<PS2Runtime::RecompiledFunction, kMaxSlots> &thunks()
        {
            static const auto s_thunks = makeThunks(std::make_integer_sequence<int, kMaxSlots>{});
            return s_thunks;
        }

        std::string formatValue(const Slot &s, uint64_t value)
        {
            char buf[48];
            if (s.floatReturn)
            {
                float f = 0.0f;
                const uint32_t bits = static_cast<uint32_t>(value);
                std::memcpy(&f, &bits, sizeof(f));
                std::snprintf(buf, sizeof(buf), "f0=%g", static_cast<double>(f));
            }
            else if ((value >> 32) == 0u)
            {
                std::snprintf(buf, sizeof(buf), "0x%08x", static_cast<uint32_t>(value));
            }
            else
            {
                std::snprintf(buf, sizeof(buf), "0x%016llx", static_cast<unsigned long long>(value));
            }
            return buf;
        }

        void printTable(const char *reason)
        {
            std::cout << formatTable(reason) << std::flush;
        }
    }

    bool enabled()
    {
        static const bool s_on = envOn("PS2X_HLE_STATS");
        return s_on;
    }

    std::vector<StubSpec> parseTomlStubs(std::istream &in)
    {
        std::vector<StubSpec> out;
        std::string line;
        bool inStubs = false;
        while (std::getline(in, line))
        {
            if (!line.empty() && line.back() == '\r')
                line.pop_back();
            size_t p = line.find_first_not_of(" \t");
            if (p == std::string::npos)
                continue;
            const std::string body = line.substr(p);
            if (!inStubs)
            {
                if (body.rfind("stubs", 0) == 0)
                {
                    size_t q = body.find_first_not_of(" \t", 5);
                    if (q != std::string::npos && body[q] == '=' && body.find('[', q) != std::string::npos)
                        inStubs = true;
                }
                if (!inStubs)
                    continue;
                // an entry may follow the '[' on the same line: fall through to the quoted scan
            }
            if (body[0] == '#')
                continue;
            size_t pos = 0;
            while (true)
            {
                const size_t a = body.find('"', pos);
                if (a == std::string::npos)
                    break;
                const size_t b = body.find('"', a + 1);
                if (b == std::string::npos)
                    break;
                const std::string entry = body.substr(a + 1, b - a - 1);
                pos = b + 1;
                const size_t at = entry.rfind('@');
                if (at == std::string::npos || at == 0)
                    continue;
                StubSpec spec;
                spec.name = entry.substr(0, at);
                spec.addr = static_cast<uint32_t>(std::strtoul(entry.c_str() + at + 1, nullptr, 0));
                out.push_back(std::move(spec));
            }
            const size_t hash = body.find('#');
            const size_t close = body.find(']');
            if (close != std::string::npos && (hash == std::string::npos || close < hash))
                break;
        }
        return out;
    }

    size_t install(PS2Runtime &runtime, const std::vector<StubSpec> &stubs)
    {
        size_t wrapped = 0u;
        std::lock_guard<std::mutex> lock(g_mutex);
        g_start = std::chrono::steady_clock::now();
        for (const StubSpec &spec : stubs)
        {
            if (g_slotCount >= kMaxSlots)
            {
                std::cout << "[hle-stats] slot table full (" << kMaxSlots << "), " << spec.name
                          << " and later stubs are not listed" << std::endl;
                break;
            }
            const int n = g_slotCount++;
            Slot &s = g_slots[n];
            s = Slot{};
            s.name = spec.name;
            s.addr = spec.addr;
            s.floatReturn = isFloatReturn(spec.name);
            if (!runtime.hasFunction(spec.addr))
                continue;                               // listed as unbound
            s.original = runtime.lookupFunction(spec.addr);
            if (runtime.replaceFunction(spec.addr, thunks()[static_cast<size_t>(n)]))
                ++wrapped;
            else
                s.original = nullptr;
        }
        return wrapped;
    }

    void uninstall(PS2Runtime &runtime)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        for (int n = 0; n < g_slotCount; ++n)
        {
            if (g_slots[n].original)
                runtime.replaceFunction(g_slots[n].addr, g_slots[n].original);
            g_slots[n] = Slot{};
        }
        g_slotCount = 0;
    }

    std::string formatTable(const std::string &reason)
    {
        std::lock_guard<std::mutex> lock(g_mutex);
        int called = 0;
        int unbound = 0;
        for (int n = 0; n < g_slotCount; ++n)
        {
            called += g_slots[n].calls != 0u ? 1 : 0;
            unbound += g_slots[n].original == nullptr ? 1 : 0;
        }
        const double secs = std::chrono::duration<double>(std::chrono::steady_clock::now() - g_start).count();
        std::ostringstream o;
        char buf[256];
        std::snprintf(buf, sizeof(buf), "[hle-stats] table (%s, t=%.1fs) stubs=%d called=%d zero-call=%d unbound=%d\n",
                      reason.c_str(), secs, g_slotCount, called, g_slotCount - called, unbound);
        o << buf;
        std::snprintf(buf, sizeof(buf), "[hle-stats] %-10s %-28s %10s %10s %8s  %-18s %-18s\n",
                      "addr", "name", "calls", "rets", "distinct", "first", "last");
        o << buf;
        for (int n = 0; n < g_slotCount; ++n)
        {
            const Slot &s = g_slots[n];
            std::string distinct = s.saturated ? std::string(">64") : std::to_string(s.distinctCount);
            std::string first = s.returns ? formatValue(s, s.first) : std::string("-");
            std::string last = s.returns ? formatValue(s, s.last) : std::string("-");
            if (!s.original)
            {
                distinct = "unbound";
            }
            std::snprintf(buf, sizeof(buf), "[hle-stats] 0x%08x %-28s %10llu %10llu %8s  %-18s %-18s\n",
                          s.addr, s.name.c_str(), static_cast<unsigned long long>(s.calls),
                          static_cast<unsigned long long>(s.returns), distinct.c_str(), first.c_str(), last.c_str());
            o << buf;
        }
        return o.str();
    }

    void installFromEnvironment(PS2Runtime &runtime)
    {
        if (!enabled())
            return;

        std::vector<std::string> candidates;
        if (const char *e = ps2x::knob("PS2X_HLE_STATS_TOML"); e && *e)
            candidates.emplace_back(e);
        else
        {
            candidates.emplace_back("recomp/socom2.toml");
            candidates.emplace_back("../recomp/socom2.toml");
        }

        std::vector<StubSpec> stubs;
        std::string used;
        for (const std::string &path : candidates)
        {
            std::ifstream in(path);
            if (!in)
                continue;
            stubs = parseTomlStubs(in);
            used = path;
            break;
        }
        if (stubs.empty())
        {
            std::cout << "[hle-stats] PS2X_HLE_STATS=1 but no stub list was read (tried";
            for (const std::string &path : candidates)
                std::cout << " " << path;
            std::cout << "); set PS2X_HLE_STATS_TOML. NO TABLE WILL BE PRINTED." << std::endl;
            return;
        }

        const size_t wrapped = install(runtime, stubs);
        std::cout << "[hle-stats] PS2X_HLE_STATS=1: " << stubs.size() << " bound stubs from " << used << ", "
                  << wrapped << " wrapped" << std::endl;

        static const unsigned s_period = [] {
            const char *e = ps2x::knob("PS2X_HLE_STATS_PERIOD");
            const unsigned v = e ? static_cast<unsigned>(std::strtoul(e, nullptr, 0)) : 30u;
            return v == 0u ? 30u : v;
        }();
        std::thread([] {
            for (;;)
            {
                std::this_thread::sleep_for(std::chrono::seconds(s_period));
                printTable("periodic");
            }
        }).detach();
        std::atexit([] { printTable("exit"); });
    }
}
