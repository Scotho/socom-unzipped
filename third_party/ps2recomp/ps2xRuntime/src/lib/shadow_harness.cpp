// Sprint 19 task E2: the shadow harness. What it runs, compares and skips, and why: runtime/shadow_harness.h.
#include "runtime/shadow_harness.h"

#include "runtime/shadow_write_log.h"
#include "ps2x/knobs.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <mutex>
#include <sstream>
#include <thread>
#include <unordered_map>
#include <utility>

namespace ps2_shadow
{
    WriteLog *g_writeLog = nullptr;

    namespace
    {
        constexpr size_t kMaxLinesKept = 32;     // per address, for mismatchLines()
        constexpr uint64_t kMaxCallsPrinted = 20; // mismatching calls printed per address
        constexpr size_t kMaxDiffsPerCall = 6;
        constexpr uint32_t kRdramKeyEnd = 0x02000000u;

        const char *const kRegNames[32] = {
            "zero", "at", "v0", "v1", "a0", "a1", "a2", "a3", "t0", "t1", "t2", "t3", "t4", "t5", "t6", "t7",
            "s0", "s1", "s2", "s3", "s4", "s5", "s6", "s7", "t8", "t9", "k0", "k1", "gp", "sp", "fp", "ra"};

        struct Slot
        {
            uint32_t addr = 0;
            std::string name;
            Fn original = nullptr;
            Fn body = nullptr;
            Mode mode;
            std::atomic<uint64_t> calls{0}, compared{0}, matched{0}, mismatched{0}, skippedUnwound{0}, skippedIo{0},
                passedThrough{0};
            std::mutex linesMutex;
            std::vector<std::string> lines;

            void reset()
            {
                addr = 0;
                name.clear();
                original = body = nullptr;
                mode = Mode{};
                calls = compared = matched = mismatched = skippedUnwound = skippedIo = passedThrough = 0;
                std::lock_guard<std::mutex> lock(linesMutex);
                lines.clear();
            }
        };

        Slot g_slots[kMaxSlots];
        int g_slotCount = 0;
        std::mutex g_installMutex;
        std::vector<uint32_t> g_listed;   // PS2X_SHADOW as read, for "listed without an override body"

        uint64_t lo64(const __m128i &v)
        {
            uint64_t parts[2];
            std::memcpy(parts, &v, sizeof(parts));
            return parts[0];
        }

        uint64_t hi64(const __m128i &v)
        {
            uint64_t parts[2];
            std::memcpy(parts, &v, sizeof(parts));
            return parts[1];
        }

        uint32_t floatBits(float f)
        {
            uint32_t b = 0;
            std::memcpy(&b, &f, sizeof(b));
            return b;
        }

        std::string hex(uint64_t v)
        {
            std::ostringstream o;
            o << "0x" << std::hex << v;
            return o.str();
        }

        // Registers: low 64 bits of r1..r31, the upper 64 of v0 and v1, pc, f0's bits.
        void compareRegisters(const R5900Context &orig, const R5900Context &body, std::vector<std::string> &diffs)
        {
            for (int r = 1; r < 32; ++r)
            {
                if (lo64(orig.r[r]) != lo64(body.r[r]))
                    diffs.push_back(std::string(kRegNames[r]) + " orig=" + hex(lo64(orig.r[r])) + " body=" +
                                    hex(lo64(body.r[r])));
                if ((r == 2 || r == 3) && hi64(orig.r[r]) != hi64(body.r[r]))
                    diffs.push_back(std::string(kRegNames[r]) + "[127:64] orig=" + hex(hi64(orig.r[r])) + " body=" +
                                    hex(hi64(body.r[r])));
            }
            if (orig.pc != body.pc)
                diffs.push_back("pc orig=" + hex(orig.pc) + " body=" + hex(body.pc));
            if (floatBits(orig.f[0]) != floatBits(body.f[0]))
                diffs.push_back("f0 orig=" + hex(floatBits(orig.f[0])) + " body=" + hex(floatBits(body.f[0])));
        }

        void compareGpr(const R5900Context &orig, const R5900Context &body, int r, bool full,
                        std::vector<std::string> &diffs)
        {
            if (lo64(orig.r[r]) != lo64(body.r[r]))
                diffs.push_back(std::string(kRegNames[r]) + " orig=" + hex(lo64(orig.r[r])) + " body=" +
                                hex(lo64(body.r[r])));
            if (full && hi64(orig.r[r]) != hi64(body.r[r]))
                diffs.push_back(std::string(kRegNames[r]) + "[127:64] orig=" + hex(hi64(orig.r[r])) + " body=" +
                                hex(hi64(body.r[r])));
        }

        void compareFpr(const R5900Context &orig, const R5900Context &body, int f, std::vector<std::string> &diffs)
        {
            if (floatBits(orig.f[f]) != floatBits(body.f[f]))
                diffs.push_back("f" + std::to_string(f) + " orig=" + hex(floatBits(orig.f[f])) + " body=" +
                                hex(floatBits(body.f[f])));
        }

        // Compare::Abi: the returned registers, the callee-saved state, pc. Nothing a caller cannot observe.
        void compareAbi(const R5900Context &orig, const R5900Context &body, uint32_t returns,
                        std::vector<std::string> &diffs)
        {
            const bool wide = (returns & kReturnsWide) != 0u;
            if (returns & kReturnsV0)
                compareGpr(orig, body, 2, wide, diffs);
            if (returns & kReturnsV1)
                compareGpr(orig, body, 3, wide, diffs);
            for (int r : {16, 17, 18, 19, 20, 21, 22, 23, 28, 29, 30, 31})
                compareGpr(orig, body, r, false, diffs);
            if (orig.pc != body.pc)
                diffs.push_back("pc orig=" + hex(orig.pc) + " body=" + hex(body.pc));
            if (returns & kReturnsF0)
                compareFpr(orig, body, 0, diffs);
            if (returns & kReturnsF1)
                compareFpr(orig, body, 1, diffs);
            for (int f = 20; f < 32; ++f)
                compareFpr(orig, body, f, diffs);
        }

        bool deadStack(uint32_t key, uint32_t entrySp)
        {
            if (key >= kRdramKeyEnd)
                return false;
            const uint32_t sp = entrySp & (kRdramKeyEnd - 1u);
            return key < sp && sp - key <= kDeadStackBytes;
        }

        void runShadowed(Slot &s, uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
        {
            const uint64_t n = s.calls.fetch_add(1, std::memory_order_relaxed);
            // A resume pc that reached this slot, or a call nested inside another shadowed call (its stores belong
            // to the outer call's log): the original, untouched.
            if (ctx->pc != s.addr || g_writeLog != nullptr)
            {
                s.passedThrough.fetch_add(1, std::memory_order_relaxed);
                s.original(rdram, ctx, runtime);
                return;
            }

            const R5900Context entry = *ctx;
            const uint32_t entryRa = static_cast<uint32_t>(lo64(entry.r[31]));
            const uint32_t entrySp = static_cast<uint32_t>(lo64(entry.r[29]));

            WriteLog origLog;
            g_writeLog = &origLog;
            s.original(rdram, ctx, runtime);
            g_writeLog = nullptr;

            // The eeCheckpointDue() back-edge return (or any unwind below): the guest is parked inside the original
            // and resumes there later without this thunk. Its state is the truth; there is nothing to compare.
            if (runtime->dispatchUnwinding() || ctx->pc != entryRa)
            {
                s.skippedUnwound.fetch_add(1, std::memory_order_relaxed);
                return;
            }
            if (origLog.ioStores != 0u)
            {
                s.skippedIo.fetch_add(1, std::memory_order_relaxed);
                return;
            }

            const R5900Context afterOrig = *ctx;
            std::vector<std::pair<uint8_t *, uint8_t>> origFinal;
            origFinal.reserve(origLog.bytes.size());
            for (const WriteLog::Byte &b : origLog.bytes)
                origFinal.emplace_back(b.host, *b.host);
            origLog.undo();
            *ctx = entry;

            WriteLog bodyLog;
            g_writeLog = &bodyLog;
            s.body(rdram, ctx, runtime);
            g_writeLog = nullptr;

            std::vector<std::string> diffs;
            if (s.mode.compare == Compare::Abi)
                compareAbi(afterOrig, *ctx, s.mode.returns, diffs);
            else
                compareRegisters(afterOrig, *ctx, diffs);
            if (bodyLog.ioStores != 0u)
                diffs.push_back("the body stored to an I/O address " + hex(bodyLog.firstIoAddress));
            if (!origLog.bytes.empty() || !bodyLog.bytes.empty())
            {
                // Memory now holds the body's result. The original's is origFinal over the bytes it stored; over
                // the bytes only the body stored it is the value before the call (the body log's first old value).
                std::unordered_map<uint32_t, std::pair<uint8_t *, uint8_t>> expect;
                for (size_t i = 0; i < origLog.bytes.size(); ++i)
                    expect[origLog.bytes[i].key] = {origLog.bytes[i].host, origFinal[i].second};
                for (const WriteLog::Byte &b : bodyLog.bytes)
                    expect.emplace(b.key, std::make_pair(b.host, b.old));
                std::vector<uint32_t> keys;
                for (const auto &kv : expect)
                    if (!deadStack(kv.first, entrySp) && *kv.second.first != kv.second.second)
                        keys.push_back(kv.first);
                std::sort(keys.begin(), keys.end());
                for (uint32_t k : keys)
                {
                    const auto &e = expect[k];
                    diffs.push_back("mem " + hex(k) + " orig=" + hex(e.second) + " body=" + hex(*e.first));
                }
            }

            s.compared.fetch_add(1, std::memory_order_relaxed);
            if (diffs.empty())
            {
                s.matched.fetch_add(1, std::memory_order_relaxed);
                return;
            }

            const uint64_t bad = s.mismatched.fetch_add(1, std::memory_order_relaxed);
            {
                std::ostringstream o;
                o << "[shadow-mismatch] " << s.name << " 0x" << std::hex << std::setw(8) << std::setfill('0') << s.addr
                  << std::dec << " call #" << n << " a0=" << hex(lo64(entry.r[4])) << " a1=" << hex(lo64(entry.r[5]))
                  << " ra=" << hex(entryRa) << ":";
                for (size_t i = 0; i < diffs.size() && i < kMaxDiffsPerCall; ++i)
                    o << (i ? "; " : " ") << diffs[i];
                if (diffs.size() > kMaxDiffsPerCall)
                    o << "; +" << (diffs.size() - kMaxDiffsPerCall) << " more";
                const std::string line = o.str();
                if (bad < kMaxCallsPrinted)
                    std::cout << line << std::endl;
                std::lock_guard<std::mutex> lock(s.linesMutex);
                if (s.lines.size() < kMaxLinesKept)
                    s.lines.push_back(line);
            }

            // The original's result back, so a shadow run plays as the unmodified game.
            bodyLog.undo();
            for (const auto &hv : origFinal)
                *hv.first = hv.second;
            *ctx = afterOrig;
        }

        template <int N>
        void thunk(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
        {
            runShadowed(g_slots[N], rdram, ctx, runtime);
        }

        template <int... Is>
        constexpr std::array<Fn, sizeof...(Is)> makeThunks(std::integer_sequence<int, Is...>)
        {
            return {{&thunk<Is>...}};
        }

        const std::array<Fn, kMaxSlots> &thunks()
        {
            static const auto t = makeThunks(std::make_integer_sequence<int, kMaxSlots>{});
            return t;
        }

        Slot *find(uint32_t addr)
        {
            for (int i = 0; i < g_slotCount; ++i)
                if (g_slots[i].addr == addr)
                    return &g_slots[i];
            return nullptr;
        }

        Counts snapshot(const Slot &s)
        {
            Counts c;
            c.calls = s.calls.load();
            c.compared = s.compared.load();
            c.matched = s.matched.load();
            c.mismatched = s.mismatched.load();
            c.skippedUnwound = s.skippedUnwound.load();
            c.skippedIo = s.skippedIo.load();
            c.passedThrough = s.passedThrough.load();
            return c;
        }

        void startReports()
        {
            static bool s_started = false;
            if (s_started)
                return;
            s_started = true;
            std::thread([] {
                for (;;)
                {
                    std::this_thread::sleep_for(std::chrono::seconds(10));
                    std::cout << formatReport("periodic") << std::flush;
                }
            }).detach();
            std::atexit([] { std::cout << formatReport("exit") << std::flush; });
        }
    }

    int add(PS2Runtime &runtime, uint32_t addr, const std::string &name, Fn original, Fn body, Mode mode)
    {
        std::lock_guard<std::mutex> lock(g_installMutex);
        if (!original || !body || g_slotCount >= kMaxSlots || find(addr))
            return -1;
        const int i = g_slotCount;
        Slot &s = g_slots[i];
        s.reset();
        s.addr = addr;
        s.name = name;
        s.original = original;
        s.body = body;
        s.mode = mode;
        if (!runtime.replaceFunction(addr, thunks()[static_cast<size_t>(i)]))
        {
            s.reset();
            return -1;
        }
        ++g_slotCount;
        return i;
    }

    Counts counts(uint32_t addr)
    {
        const Slot *s = find(addr);
        return s ? snapshot(*s) : Counts{};
    }

    bool verified(uint32_t addr)
    {
        const Counts c = counts(addr);
        return c.compared > 0 && c.mismatched == 0;
    }

    std::vector<std::string> mismatchLines(uint32_t addr)
    {
        Slot *s = find(addr);
        if (!s)
            return {};
        std::lock_guard<std::mutex> lock(s->linesMutex);
        return s->lines;
    }

    std::string formatReport(const std::string &reason)
    {
        std::ostringstream o;
        Counts total;
        for (int i = 0; i < g_slotCount; ++i)
        {
            const Slot &s = g_slots[i];
            const Counts c = snapshot(s);
            o << "[shadow] " << reason << ": 0x" << std::hex << std::setw(8) << std::setfill('0') << s.addr << std::dec
              << " " << s.name << " compare=" << (s.mode.compare == Compare::Abi ? "abi" : "all")
              << " calls=" << c.calls << " compared=" << c.compared << " matched=" << c.matched
              << " mismatched=" << c.mismatched << " skipped_unwound=" << c.skippedUnwound << " skipped_io="
              << c.skippedIo << " passed_through=" << c.passedThrough << " verified="
              << ((c.compared > 0 && c.mismatched == 0) ? "yes" : "no") << "\n";
            total.calls += c.calls;
            total.compared += c.compared;
            total.mismatched += c.mismatched;
            total.skippedUnwound += c.skippedUnwound;
            total.skippedIo += c.skippedIo;
        }
        o << "[shadow] " << reason << ": total shadowed=" << g_slotCount << " calls=" << total.calls << " compared="
          << total.compared << " mismatched=" << total.mismatched << " skipped_unwound=" << total.skippedUnwound
          << " skipped_io=" << total.skippedIo;
        bool any = false;
        for (uint32_t a : g_listed)
            if (!find(a))
            {
                o << (any ? " " : "; listed without an override body:") << " 0x" << std::hex << a << std::dec;
                any = true;
            }
        o << "\n";
        return o.str();
    }

    void uninstall(PS2Runtime &runtime)
    {
        std::lock_guard<std::mutex> lock(g_installMutex);
        for (int i = 0; i < g_slotCount; ++i)
        {
            runtime.replaceFunction(g_slots[i].addr, g_slots[i].original);
            g_slots[i].reset();
        }
        g_slotCount = 0;
        g_writeLog = nullptr;
    }

    bool parseSpec(const char *spec, std::vector<uint32_t> &out)
    {
        out.clear();
        if (!spec)
            return true;
        std::string s(spec);
        size_t pos = 0;
        while (pos <= s.size())
        {
            size_t end = s.find(',', pos);
            if (end == std::string::npos)
                end = s.size();
            std::string item = s.substr(pos, end - pos);
            item.erase(0, item.find_first_not_of(" \t"));
            item.erase(item.find_last_not_of(" \t") + 1);
            pos = end + 1;
            if (item.empty())
                continue;
            char *stop = nullptr;
            const unsigned long v = std::strtoul(item.c_str(), &stop, 0);
            if (!stop || *stop != '\0')
                return false;
            out.push_back(static_cast<uint32_t>(v));
        }
        return true;
    }

    bool writeLogBuilt()
    {
#if defined(PS2X_SHADOW_WRITE_LOG) && PS2X_SHADOW_WRITE_LOG
        return true;
#else
        return false;
#endif
    }

    Installed installOverride(PS2Runtime &runtime, uint32_t addr, const char *name, Fn body,
                              const std::vector<uint32_t> &shadowList, bool writeLog)
    {
        return installOverride(runtime, addr, name, body, Mode{}, shadowList, writeLog);
    }

    Installed installOverride(PS2Runtime &runtime, uint32_t addr, const char *name, Fn body, Mode mode,
                              const std::vector<uint32_t> &shadowList, bool writeLog)
    {
        const bool listed = std::find(shadowList.begin(), shadowList.end(), addr) != shadowList.end();
        if (!listed)
        {
            if (!runtime.replaceFunction(addr, body))
                return Installed::Refused;
            std::cout << "[override] " << name << " 0x" << std::hex << addr << std::dec << ": the body replaces the original"
                      << std::endl;
            return Installed::Override;
        }
        if (!writeLog)
        {
            std::cout << "[shadow] " << name << " 0x" << std::hex << addr << std::dec
                      << ": REFUSED, this build has no write log (configure with PS2X_SHADOW_WRITE_LOG=ON); "
                         "the original runs and the body is not used"
                      << std::endl;
            return Installed::Refused;
        }
        const Fn original = runtime.hasFunction(addr) ? runtime.lookupFunction(addr) : nullptr;
        if (add(runtime, addr, name, original, body, mode) < 0)
        {
            std::cout << "[shadow] " << name << " 0x" << std::hex << addr << std::dec
                      << ": REFUSED (no original in the table, the address is shadowed already, or all " << kMaxSlots
                      << " slots are taken)" << std::endl;
            return Installed::Refused;
        }
        std::cout << "[shadow] " << name << " 0x" << std::hex << addr << std::dec
                  << ": original and body both run on every call and are compared ("
                  << (mode.compare == Compare::Abi ? "ABI" : "all registers") << ")" << std::endl;
        return Installed::Shadow;
    }

    Installed installOverride(PS2Runtime &runtime, uint32_t addr, const char *name, Fn body, Mode mode)
    {
        static const std::vector<uint32_t> s_list = [] {
            std::vector<uint32_t> v;
            const char *spec = ps2x::knob("PS2X_SHADOW");
            if (spec && *spec && !parseSpec(spec, v))
            {
                std::cout << "[shadow] PS2X_SHADOW='" << spec << "' is not a list of addresses; nothing is shadowed"
                          << std::endl;
                v.clear();
            }
            else if (!v.empty())
                std::cout << "[shadow] PS2X_SHADOW lists " << v.size() << " address(es); write log "
                          << (writeLogBuilt() ? "built in" : "NOT built in") << std::endl;
            return v;
        }();
        g_listed = s_list;
        const Installed what = installOverride(runtime, addr, name, body, mode, s_list, writeLogBuilt());
        if (what == Installed::Shadow)
            startReports();
        return what;
    }
}
