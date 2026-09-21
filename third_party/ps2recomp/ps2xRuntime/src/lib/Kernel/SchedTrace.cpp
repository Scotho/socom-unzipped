#include "SchedTrace.h"

#include "ps2_runtime.h"
#include "runtime/ee_scheduler.h"
#include "runtime/ps2_audio.h"
#include "ps2x/knobs.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iostream>
#include <mutex>
#include <utility>

namespace ps2_sched_trace
{
    namespace
    {
        constexpr int kMaxSlots = 512;

        struct Slot
        {
            std::string name;
            uint32_t addr = 0u;
            PS2Runtime::RecompiledFunction original = nullptr;
            bool always = false;   // named in PS2X_SCHED_TRACE_STUBS: every call, with arguments and return
        };

        std::mutex g_mutex;   // install / uninstall only; the thunks read their slot without it
        Slot g_slots[kMaxSlots];
        int g_slotCount = 0;

        bool envOn(const char *name)
        {
            const char *e = ps2x::knob(name);
            if (!e || !*e)
                return false;
            return !(std::strcmp(e, "0") == 0 || std::strcmp(e, "false") == 0 || std::strcmp(e, "off") == 0);
        }

        int64_t envMsToNs(const char *name, double defaultMs)
        {
            const char *e = ps2x::knob(name);
            const double ms = (e && *e) ? std::atof(e) : defaultMs;
            return static_cast<int64_t>(ms * 1000000.0);
        }

        std::chrono::steady_clock::time_point epoch()
        {
            static const auto s_epoch = std::chrono::steady_clock::now();
            return s_epoch;
        }

        Stamp stampNow(PS2Runtime *runtime)
        {
            Stamp stamp{};
            if (runtime != nullptr)
            {
                stamp.frame = runtime->audioBackend().mixerRenderedFrames();
                stamp.tick = runtime->eeScheduler().currentVSyncTick();
            }
            stamp.hostMs = hostMs();
            return stamp;
        }

        void report(int n, PS2Runtime *runtime, int tid, std::chrono::steady_clock::time_point start, bool transferred,
                    const uint32_t *args, const R5900Context *ctx)
        {
            const int64_t elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - start).count();
            const Slot &s = g_slots[n];
            if (s.always)
            {
                const uint32_t ret = transferred ? 0u : getRegU32(ctx, 2);
                const std::string line = formatStubCall(stampNow(runtime), s.name, tid, elapsed, args[0], args[1], args[2], transferred, ret);
                std::fprintf(stderr, "%s\n", line.c_str());
                return;
            }
            static const int64_t s_threshold = stubThresholdNs();
            if (!stubReportable(elapsed, s_threshold))
                return;
            const std::string line = formatStub(stampNow(runtime), s.name, tid, elapsed, transferred);
            std::fprintf(stderr, "%s\n", line.c_str());
        }

        template <int N>
        void timingThunk(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
        {
            const auto start = std::chrono::steady_clock::now();
            const int tid = runtime != nullptr ? runtime->eeScheduler().currentThreadId() : 0;
            const uint32_t args[3] = {getRegU32(ctx, 4), getRegU32(ctx, 5), getRegU32(ctx, 6)};
            try
            {
                g_slots[N].original(rdram, ctx, runtime);
            }
            catch (...)
            {
                // EeDispatcherTransfer: the stub blocked or yielded (the C++ call does not come back)
                report(N, runtime, tid, start, true, args, ctx);
                throw;
            }
            report(N, runtime, tid, start, false, args, ctx);
        }

        template <int... Is>
        constexpr std::array<PS2Runtime::RecompiledFunction, sizeof...(Is)> makeThunks(std::integer_sequence<int, Is...>)
        {
            return {{&timingThunk<Is>...}};
        }

        const std::array<PS2Runtime::RecompiledFunction, kMaxSlots> &thunks()
        {
            static const auto s_thunks = makeThunks(std::make_integer_sequence<int, kMaxSlots>{});
            return s_thunks;
        }
    }

    bool enabled()
    {
        static const bool s_on = envOn("PS2X_SCHED_TRACE");
        return s_on;
    }

    int64_t stubThresholdNs()
    {
        static const int64_t s_ns = envMsToNs("PS2X_SCHED_TRACE_STUB_MS", 1.0);
        return s_ns;
    }

    int64_t sampleIntervalNs()
    {
        static const int64_t s_ns = envMsToNs("PS2X_SCHED_TRACE_SAMPLE_MS", 20.0);
        return s_ns;
    }

    double hostMs()
    {
        return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - epoch()).count();
    }

    std::string prefix(const Stamp &stamp)
    {
        char buf[96];
        std::snprintf(buf, sizeof(buf), "[sched] frame=%llu tick=%llu host=%.1f ",
                      static_cast<unsigned long long>(stamp.frame), static_cast<unsigned long long>(stamp.tick), stamp.hostMs);
        return buf;
    }

    bool stubReportable(int64_t elapsedNs, int64_t thresholdNs)
    {
        if (thresholdNs < 0)
            return false;
        return elapsedNs >= thresholdNs;
    }

    std::string formatStub(const Stamp &stamp, const std::string &name, int tid, int64_t elapsedNs, bool transferred)
    {
        char buf[128];
        std::snprintf(buf, sizeof(buf), "stub %s tid=%d ms=%.2f%s", name.c_str(), tid,
                      static_cast<double>(elapsedNs) / 1000000.0, transferred ? " transfer" : "");
        return prefix(stamp) + buf;
    }

    std::vector<std::string> parseStubNames(const char *list)
    {
        std::vector<std::string> names;
        if (!list)
            return names;
        std::string current;
        for (const char *p = list;; ++p)
        {
            if (*p == ',' || *p == '\0')
            {
                const size_t a = current.find_first_not_of(" \t");
                const size_t b = current.find_last_not_of(" \t");
                if (a != std::string::npos)
                    names.push_back(current.substr(a, b - a + 1));
                current.clear();
                if (*p == '\0')
                    break;
            }
            else
                current.push_back(*p);
        }
        return names;
    }

    std::string formatStubCall(const Stamp &stamp, const std::string &name, int tid, int64_t elapsedNs,
                               uint32_t a0, uint32_t a1, uint32_t a2, bool transferred, uint32_t ret)
    {
        char buf[192];
        if (transferred)
            std::snprintf(buf, sizeof(buf), "stub %s tid=%d ms=%.2f a0=0x%x a1=0x%x a2=0x%x transfer", name.c_str(), tid,
                          static_cast<double>(elapsedNs) / 1000000.0, a0, a1, a2);
        else
            std::snprintf(buf, sizeof(buf), "stub %s tid=%d ms=%.2f a0=0x%x a1=0x%x a2=0x%x ret=0x%x", name.c_str(), tid,
                          static_cast<double>(elapsedNs) / 1000000.0, a0, a1, a2, ret);
        return prefix(stamp) + buf;
    }

    size_t installStubTiming(PS2Runtime &runtime, const std::vector<ps2_hle_stats::StubSpec> &stubs)
    {
        size_t wrapped = 0u;
        std::lock_guard<std::mutex> lock(g_mutex);
        static const std::vector<std::string> s_always = parseStubNames(ps2x::knob("PS2X_SCHED_TRACE_STUBS"));
        for (const ps2_hle_stats::StubSpec &spec : stubs)
        {
            if (g_slotCount >= kMaxSlots)
            {
                std::cerr << "[sched] slot table full (" << kMaxSlots << "), " << spec.name
                          << " and later stubs are not timed" << std::endl;
                break;
            }
            if (!runtime.hasFunction(spec.addr))
                continue;
            const int n = g_slotCount++;
            Slot &s = g_slots[n];
            s = Slot{};
            s.name = spec.name;
            s.addr = spec.addr;
            s.always = std::find(s_always.begin(), s_always.end(), spec.name) != s_always.end();
            s.original = runtime.lookupFunction(spec.addr);
            if (runtime.replaceFunction(spec.addr, thunks()[static_cast<size_t>(n)]))
                ++wrapped;
            else
                s.original = nullptr;
        }
        return wrapped;
    }

    void uninstallStubTiming(PS2Runtime &runtime)
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

    void installFromEnvironment(PS2Runtime &runtime)
    {
        if (!enabled())
            return;

        std::vector<std::string> candidates;
        if (const char *e = ps2x::knob("PS2X_SCHED_TRACE_TOML"); e && *e)
            candidates.emplace_back(e);
        else
        {
            candidates.emplace_back("recomp/socom2.toml");
            candidates.emplace_back("../recomp/socom2.toml");
        }

        std::vector<ps2_hle_stats::StubSpec> stubs;
        std::string used;
        for (const std::string &path : candidates)
        {
            std::ifstream in(path);
            if (!in)
                continue;
            stubs = ps2_hle_stats::parseTomlStubs(in);
            used = path;
            break;
        }
        if (stubs.empty())
        {
            std::cerr << "[sched] PS2X_SCHED_TRACE=1 but no stub list was read (tried";
            for (const std::string &path : candidates)
                std::cerr << " " << path;
            std::cerr << "); set PS2X_SCHED_TRACE_TOML. Stub timing is OFF; the thread trace is on." << std::endl;
            return;
        }
        const size_t wrapped = installStubTiming(runtime, stubs);
        std::cerr << "[sched] PS2X_SCHED_TRACE=1: " << wrapped << " bound stubs timed from " << used
                  << " (threshold " << static_cast<double>(stubThresholdNs()) / 1000000.0 << " ms, sample "
                  << static_cast<double>(sampleIntervalNs()) / 1000000.0 << " ms";
        if (const char *always = ps2x::knob("PS2X_SCHED_TRACE_STUBS"); always && *always)
            std::cerr << ", every call of: " << always;
        std::cerr << ")" << std::endl;
    }
}
