// vu1_replay: run one VU1 program dump (PS2X_VU1_DUMP=<dir> -> vu1_prog_N.bin) through the runtime's
// VU1 interpreter offline and save every XGKICK packet it produces.
//
//   vu1_replay <dump.bin> [--out packets.bin] [--trace] [--state]
//   vu1_replay --batch <outdir> [--repeat N] [--state] <dump.bin>...
//   vu1_replay --gen <out.cpp> [--pchist hist.bin] <dump.bin>...   (VU1 image -> known-program C++)
//
// Dump layout: uint32 startPc, top, itop, codeSize; 16 KB code; 16 KB data; int32 vi[16]; float
// vf[32][4] (the register file at program start — VU registers persist across MSCALs, so the dump
// restores them before running). The packet file is a sequence of (uint32 length, bytes) records;
// tools_py/gif_packets.py parses them into vertices.
//
// Batch mode writes <outdir>/<dump basename>.pk per dump and <outdir>/state.txt with one line per
// dump (packet count/bytes/FNV hash, cycles, end pc, every register as hex, VU data memory hash) —
// the "golden" used to verify a faster execution path packet-for-packet and register-for-register.
// --repeat N runs every program N times (fresh data memory each time) and reports host ns/cycle.
#include <atomic>
#include <algorithm>
#include <chrono>
#include <fstream>
#include <map>
#include <sstream>
#include <thread>
#include <unordered_map>
#include <windows.h>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <set>
#include <string>
#include <vector>

#define private public
#include "runtime/ps2_vu1.h"
#undef private
#include "runtime/gs/gs_frontend.h"
#include "runtime/ps2_memory.h"

// Defined in the game runner (game_overrides_socom2.cpp); the interpreter references it for the
// triggered program dump. Never armed here.
std::atomic<bool> g_ps2xTraceArmed{false};
extern uint32_t *g_vu1PcHist; // ps2_vu1_core.cpp: per-pair execution counts of the fast path
extern uint32_t *g_vu1JrHist; // computed-jump targets
extern uint32_t *g_vu1BailHist; // per-pc hand-backs of the generated code
extern uint64_t g_vu1GenEntered, g_vu1GenEnded, g_vu1GenSkipped;
int vu1GenerateKnownProgram(const uint8_t *code, uint64_t hash, const std::set<uint32_t> &seeds, const std::set<uint32_t> &unknownEntries, const std::string &outPath);

namespace
{
    struct Dump
    {
        std::string path;
        uint32_t hdr[4] = {0, 0, 0, 0};
        std::vector<uint8_t> code, data;
        int32_t vi[16] = {0};
        float vf[32][4] = {};
    };

    bool loadDump(const char *path, Dump &d)
    {
        FILE *fp = std::fopen(path, "rb");
        if (!fp)
        {
            std::fprintf(stderr, "cannot open %s\n", path);
            return false;
        }
        d.path = path;
        d.code.assign(0x4000, 0);
        d.data.assign(0x4000, 0);
        const bool ok = std::fread(d.hdr, sizeof(d.hdr), 1, fp) == 1 &&
                        std::fread(d.code.data(), 1, d.code.size(), fp) == d.code.size() &&
                        std::fread(d.data.data(), 1, d.data.size(), fp) == d.data.size() &&
                        std::fread(d.vi, sizeof(d.vi), 1, fp) == 1 &&
                        std::fread(d.vf, sizeof(d.vf), 1, fp) == 1;
        std::fclose(fp);
        if (!ok)
            std::fprintf(stderr, "short dump file %s\n", path);
        return ok;
    }

    uint64_t fnv1a(const uint8_t *p, size_t n, uint64_t h = 1469598103934665603ull)
    {
        for (size_t i = 0; i < n; ++i)
        {
            h ^= p[i];
            h *= 1099511628211ull;
        }
        return h;
    }

    std::string baseName(const std::string &path)
    {
        const size_t slash = path.find_last_of("/\\");
        std::string base = slash == std::string::npos ? path : path.substr(slash + 1);
        const size_t dot = base.find_last_of('.');
        if (dot != std::string::npos)
            base = base.substr(0, dot);
        return base;
    }

    std::string stateLine(const char *name, const VU1Interpreter &vu, uint32_t packetCount,
                          const std::vector<uint8_t> &packets, uint64_t cycles, const std::vector<uint8_t> &data)
    {
        const VU1State &s = vu.m_state;
        std::string out;
        char buf[128];
        auto add = [&](const char *fmt, auto... args) { std::snprintf(buf, sizeof(buf), fmt, args...); out += buf; };
        add("%s packets=%u bytes=%zu hash=%016llx cycles=%llu endpc=0x%x", name, packetCount, packets.size(),
            (unsigned long long)fnv1a(packets.data(), packets.size()), (unsigned long long)cycles, s.pc);
        add(" mac=%03x status=%03x clip=%06x r=%08x", s.mac, s.status, s.clip, s.r);
        uint32_t w = 0;
        std::memcpy(&w, &s.q, 4); add(" q=%08x", w);
        std::memcpy(&w, &s.p, 4); add(" p=%08x", w);
        std::memcpy(&w, &s.i, 4); add(" i=%08x", w);
        out += " vi=";
        for (int r = 0; r < 16; ++r) add("%s%04x", r ? "," : "", (unsigned)(s.vi[r] & 0xFFFF));
        out += " acc=";
        for (int c = 0; c < 4; ++c) { std::memcpy(&w, &s.acc[c], 4); add("%s%08x", c ? "," : "", w); }
        out += " vf=";
        for (int r = 0; r < 32; ++r)
            for (int c = 0; c < 4; ++c) { std::memcpy(&w, &s.vf[r][c], 4); add("%s%08x", (r || c) ? "," : "", w); }
        add(" data=%016llx\n", (unsigned long long)fnv1a(data.data(), data.size()));
        return out;
    }

    void printState(FILE *out, const char *name, const VU1Interpreter &vu, uint32_t packetCount,
                    const std::vector<uint8_t> &packets, uint64_t cycles, const std::vector<uint8_t> &data)
    {
        const std::string line = stateLine(name, vu, packetCount, packets, cycles, data);
        std::fputs(line.c_str(), out);
    }

    // "name k=v k=v ..." -> map; the first token is the dump name.
    std::map<std::string, std::string> parseStateLine(const std::string &line, std::string &name)
    {
        std::map<std::string, std::string> kv;
        std::istringstream in(line);
        in >> name;
        std::string tok;
        while (in >> tok)
        {
            const size_t eq = tok.find('=');
            if (eq != std::string::npos)
                kv[tok.substr(0, eq)] = tok.substr(eq + 1);
        }
        return kv;
    }

    std::map<std::string, std::map<std::string, std::string>> loadGolden(const char *path)
    {
        std::map<std::string, std::map<std::string, std::string>> golden;
        std::ifstream in(path);
        std::string line, name;
        while (std::getline(in, line))
        {
            if (line.empty()) continue;
            auto kv = parseStateLine(line, name);
            golden[name] = std::move(kv);
        }
        return golden;
    }

    // Returns the number of mismatching fields; prints one MISMATCH line per field.
    int compareState(const std::string &name, const std::map<std::string, std::string> &golden,
                     const std::map<std::string, std::string> &got, bool regs)
    {
        std::vector<const char *> fields = {"packets", "bytes", "hash", "endpc", "data"};
        if (regs)
            for (const char *f : {"vi", "vf", "acc", "q", "p", "i", "mac", "status", "clip", "r"})
                fields.push_back(f);
        int bad = 0;
        for (const char *f : fields)
        {
            const auto g = golden.find(f), o = got.find(f);
            const std::string gv = g == golden.end() ? "<missing>" : g->second;
            const std::string ov = o == got.end() ? "<missing>" : o->second;
            if (gv != ov)
            {
                ++bad;
                std::printf("MISMATCH %s %s golden=%s got=%s\n", name.c_str(), f, gv.c_str(), ov.c_str());
            }
        }
        return bad;
    }
}

int main(int argc, char **argv)
{
    if (argc < 2)
    {
        std::fprintf(stderr, "usage: vu1_replay <dump.bin> [--out packets.bin] [--trace] [--state]\n"
                             "       vu1_replay --batch <outdir> [--repeat N] [--state] <dump.bin>...\n"
                             "       vu1_replay --verify <golden.txt> [--regs all|none] [--native|--no-native] <dump.bin>...\n");
        return 2;
    }
    std::string outPath = "vu1_packets.bin";
    std::string batchDir;
    std::string verifyPath;
    bool verifyRegs = true;
    std::string profPath;
    std::string genPath;
    std::string pcHistPath;
    std::string seedsPath; // --seeds <file>: extra pcs (hex, one per line; in-game [vu1-bail] pcs) as unknown entries
    bool bailHist = false;
    bool trace = false;
    bool printStateFlag = false;
    int repeat = 1;
    std::vector<std::string> inputs;
    for (int i = 1; i < argc; ++i)
    {
        if (!std::strcmp(argv[i], "--out") && i + 1 < argc)
            outPath = argv[++i];
        else if (!std::strcmp(argv[i], "--batch") && i + 1 < argc)
            batchDir = argv[++i];
        else if (!std::strcmp(argv[i], "--repeat") && i + 1 < argc)
            repeat = std::atoi(argv[++i]);
        else if (!std::strcmp(argv[i], "--prof") && i + 1 < argc)
            profPath = argv[++i];
        else if (!std::strcmp(argv[i], "--gen") && i + 1 < argc)
            genPath = argv[++i];
        else if (!std::strcmp(argv[i], "--pchist") && i + 1 < argc)
            pcHistPath = argv[++i];
        else if (!std::strcmp(argv[i], "--bailhist"))
            bailHist = true;
        else if (!std::strcmp(argv[i], "--seeds") && i + 1 < argc)
            seedsPath = argv[++i];
        else if (!std::strcmp(argv[i], "--trace"))
            trace = true;
        else if (!std::strcmp(argv[i], "--state"))
            printStateFlag = true;
        else if (!std::strcmp(argv[i], "--verify") && i + 1 < argc)
            verifyPath = argv[++i];
        else if (!std::strcmp(argv[i], "--regs") && i + 1 < argc)
            verifyRegs = std::strcmp(argv[++i], "none") != 0;
        else if (!std::strcmp(argv[i], "--native"))
            _putenv("PS2X_VU1_NATIVE=1");
        else if (!std::strcmp(argv[i], "--no-native"))
            _putenv("PS2X_VU1_NATIVE=0");
        else
            inputs.push_back(argv[i]);
    }
    if (inputs.empty())
    {
        std::fprintf(stderr, "no dump given\n");
        return 2;
    }
    if (repeat < 1)
        repeat = 1;

    _putenv("PS2X_GS_BACKEND=cpu");
    if (trace)
        _putenv("PS2X_TRACE_VU=0");
    // The generator needs the interpreter's own execution profile (the generated code keeps none).
    std::vector<uint32_t> bails;
    if (bailHist)
    {
        bails.assign(2048, 0u);
        g_vu1BailHist = bails.data();
    }
    std::vector<uint32_t> pcHist, jrHist;
    if (!genPath.empty() || !pcHistPath.empty())
    {
        _putenv("PS2X_VU1_GEN=0");
        _putenv("PS2X_VU1_FAST=1");
        pcHist.assign(2048, 0u);
        g_vu1PcHist = pcHist.data();
        jrHist.assign(2048, 0u);
        g_vu1JrHist = jrHist.data();
    }

    std::map<std::string, std::map<std::string, std::string>> golden;
    int mismatches = 0;
    if (!verifyPath.empty())
    {
        golden = loadGolden(verifyPath.c_str());
        if (golden.empty())
        {
            std::fprintf(stderr, "--verify: no lines read from %s\n", verifyPath.c_str());
            return 2;
        }
    }

    GS gs;
    PS2Memory memory;
    // The program runs from the memory object's own VU1 buffers so the interpreter's decoded-code
    // cache applies exactly as in the game (a foreign code pointer is decoded pair by pair).
    if (!memory.initialize())
    {
        std::fprintf(stderr, "PS2Memory::initialize failed\n");
        return 1;
    }
    std::vector<uint8_t> packets;
    uint32_t packetCount = 0;
    memory.setGifPacketCallback([&](const uint8_t *p, uint32_t n) {
        const uint32_t len = n;
        packets.insert(packets.end(), reinterpret_cast<const uint8_t *>(&len), reinterpret_cast<const uint8_t *>(&len) + 4);
        packets.insert(packets.end(), p, p + n);
        ++packetCount;
    });

    VU1Interpreter vu(VU1Interpreter::Unit::VU1);
    FILE *stateOut = nullptr;
    if (!batchDir.empty())
    {
        const std::string statePath = batchDir + "/state.txt";
        stateOut = std::fopen(statePath.c_str(), "w");
        if (!stateOut)
        {
            std::fprintf(stderr, "cannot write %s\n", statePath.c_str());
            return 1;
        }
    }

    // --prof <file>: sample this thread's instruction pointer every 0.2 ms from a helper thread and
    // write a PS2X_HOST_PROF-style histogram (symbolize with tools_py/hostprof_symbolize.py --exe).
    std::atomic<bool> profStop{false};
    std::thread profThread;
    if (!profPath.empty())
    {
        HANDLE dup = nullptr;
        DuplicateHandle(GetCurrentProcess(), GetCurrentThread(), GetCurrentProcess(), &dup,
                        THREAD_SUSPEND_RESUME | THREAD_GET_CONTEXT | THREAD_QUERY_INFORMATION, FALSE, 0);
        const uint64_t base = reinterpret_cast<uint64_t>(GetModuleHandleW(nullptr));
        profThread = std::thread([dup, base, profPath, &profStop]() {
            std::unordered_map<uint64_t, uint32_t> counts;
            uint64_t total = 0;
            while (!profStop.load())
            {
                // Sleep granularity on Windows is ~15 ms: spin (yielding) for the sample period.
                const auto until = std::chrono::steady_clock::now() + std::chrono::microseconds(100);
                while (std::chrono::steady_clock::now() < until)
                    std::this_thread::yield();
                if (SuspendThread(dup) == static_cast<DWORD>(-1))
                    continue;
                CONTEXT c;
                std::memset(&c, 0, sizeof(c));
                c.ContextFlags = CONTEXT_CONTROL;
                uint64_t rip = GetThreadContext(dup, &c) ? c.Rip : 0;
                ResumeThread(dup);
                if (rip)
                {
                    ++counts[rip];
                    ++total;
                }
            }
            std::vector<std::pair<uint64_t, uint32_t>> v(counts.begin(), counts.end());
            std::sort(v.begin(), v.end(), [](const auto &a, const auto &b) { return a.second > b.second; });
            std::ofstream f(profPath, std::ios::trunc);
            f << "base 0x" << std::hex << base << std::dec << " total " << total << '\n';
            for (const auto &kv : v)
            {
                HMODULE mod = nullptr;
                const bool inExe = GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                                                      reinterpret_cast<LPCWSTR>(kv.first), &mod) &&
                                   reinterpret_cast<uint64_t>(mod) == base;
                if (inExe)
                    f << std::hex << kv.first - base << std::dec << " " << kv.second << '\n';
                else
                {
                    char name[MAX_PATH] = {0};
                    if (mod)
                        GetModuleFileNameA(mod, name, sizeof(name));
                    f << std::hex << kv.first << std::dec << " " << kv.second << " ext " << (mod ? name : "?") << "+0x"
                      << std::hex << (mod ? kv.first - reinterpret_cast<uint64_t>(mod) : 0) << std::dec << '\n';
                }
            }
        });
    }

    double totalHostNs = 0.0;
    uint64_t totalCycles = 0;
    uint64_t totalPairs = 0;
    std::vector<uint8_t> data;
    std::set<uint32_t> entryPcs;
    std::vector<uint8_t> firstCode;
    for (const std::string &input : inputs)
    {
        Dump d;
        if (!loadDump(input.c_str(), d))
            return 1;
        entryPcs.insert(d.hdr[0]);
        if (firstCode.empty())
            firstCode = d.code;
        else if (!genPath.empty() && firstCode != d.code)
        {
            std::fprintf(stderr, "--gen: %s runs a different microcode image than the first dump\n", input.c_str());
            return 1;
        }
        uint64_t cycles = 0;
        for (int iter = 0; iter < repeat; ++iter)
        {
            packets.clear();
            packetCount = 0;
            uint8_t *code = memory.getVU1Code();
            uint8_t *vuData = memory.getVU1Data();
            if (std::memcmp(code, d.code.data(), PS2_VU1_CODE_SIZE) != 0)
            {
                std::memcpy(code, d.code.data(), PS2_VU1_CODE_SIZE);
                memory.markVU1CodeModified();
            }
            std::memcpy(vuData, d.data.data(), PS2_VU1_DATA_SIZE);
            vu.reset();
            std::memcpy(vu.m_state.vi, d.vi, sizeof(d.vi));
            std::memcpy(vu.m_state.vf, d.vf, sizeof(d.vf));
            const uint64_t startCycle = vu.m_cycle;
            extern std::atomic<uint64_t> g_vuInsnCount;
            const uint64_t startPairs = g_vuInsnCount.load();
            const auto t0 = std::chrono::steady_clock::now();
            vu.execute(code, PS2_VU1_CODE_SIZE, vuData, PS2_VU1_DATA_SIZE,
                       gs, &memory, d.hdr[0], d.hdr[1], d.hdr[2], 1u << 28);
            const auto t1 = std::chrono::steady_clock::now();
            totalHostNs += std::chrono::duration<double, std::nano>(t1 - t0).count();
            cycles = vu.m_cycle - startCycle;
            totalCycles += cycles;
            totalPairs += g_vuInsnCount.load() - startPairs;
            data.assign(vuData, vuData + PS2_VU1_DATA_SIZE);
        }

        if (!verifyPath.empty())
        {
            const std::string base = baseName(input);
            std::string gotName;
            auto got = parseStateLine(stateLine(base.c_str(), vu, packetCount, packets, cycles, data), gotName);
            const auto g = golden.find(base);
            if (g == golden.end())
            {
                std::printf("MISMATCH %s <no golden line>\n", base.c_str());
                ++mismatches;
            }
            else
            {
                const int bad = compareState(base, g->second, got, verifyRegs);
                mismatches += bad;
                if (bad == 0) std::printf("OK %s\n", base.c_str());
            }
            continue;
        }

        if (batchDir.empty())
        {
            std::printf("pc=0x%x top=0x%x itop=0x%x: %u packets, %zu bytes, %llu cycles, end pc=0x%x\n",
                        d.hdr[0], d.hdr[1], d.hdr[2], packetCount, packets.size(), (unsigned long long)cycles, vu.m_state.pc);
            if (FILE *out = std::fopen(outPath.c_str(), "wb"))
            {
                std::fwrite(packets.data(), 1, packets.size(), out);
                std::fclose(out);
            }
            if (printStateFlag)
                printState(stdout, baseName(input).c_str(), vu, packetCount, packets, cycles, data);
        }
        else
        {
            const std::string base = baseName(input);
            const std::string pk = batchDir + "/" + base + ".pk";
            if (FILE *out = std::fopen(pk.c_str(), "wb"))
            {
                std::fwrite(packets.data(), 1, packets.size(), out);
                std::fclose(out);
            }
            printState(stateOut, base.c_str(), vu, packetCount, packets, cycles, data);
        }
    }
    if (stateOut)
        std::fclose(stateOut);
    if (bailHist)
    {
        uint64_t total = 0;
        for (uint32_t i = 0; i < bails.size(); ++i)
            total += bails[i];
        std::fprintf(stderr, "[vu1_replay] generated code: entered %llu, ended %llu, dispatch skipped %llu, hand-backs %llu\n",
                     (unsigned long long)g_vu1GenEntered, (unsigned long long)g_vu1GenEnded, (unsigned long long)g_vu1GenSkipped, (unsigned long long)total);
        for (uint32_t i = 0; i < bails.size(); ++i)
            if (bails[i])
                std::fprintf(stderr, "  pc=0x%04x: %u\n", i * 8u, bails[i]);
    }
    if (!pcHistPath.empty())
    {
        if (FILE *fp = std::fopen(pcHistPath.c_str(), "wb"))
        {
            std::fwrite(pcHist.data(), sizeof(uint32_t), pcHist.size(), fp);
            std::fclose(fp);
        }
    }
    if (!genPath.empty())
    {
        std::set<uint32_t> seeds(entryPcs);
        uint32_t executed = 0;
        for (uint32_t i = 0; i < pcHist.size(); ++i)
            if (pcHist[i])
            {
                seeds.insert(i * 8u);
                ++executed;
            }
        std::set<uint32_t> unknownEntries(entryPcs);
        for (uint32_t i = 0; i < jrHist.size(); ++i)
            if (jrHist[i])
                unknownEntries.insert(i * 8u);
        if (!seedsPath.empty())
        {
            if (FILE *sf = std::fopen(seedsPath.c_str(), "r"))
            {
                char line[128];
                while (std::fgets(line, sizeof(line), sf))
                {
                    const uint32_t pc = static_cast<uint32_t>(std::strtoul(line, nullptr, 0)) & 0x3FF8u;
                    seeds.insert(pc);
                    unknownEntries.insert(pc);
                }
                std::fclose(sf);
            }
            else
                std::fprintf(stderr, "cannot read %s\n", seedsPath.c_str());
        }
        std::fprintf(stderr, "[vu1_gen] %zu entry pcs, %u executed pairs, %zu computed-jump/entry pcs\n", entryPcs.size(), executed, unknownEntries.size());
        const int rc = vu1GenerateKnownProgram(firstCode.data(), fnv1a(firstCode.data(), firstCode.size()), seeds, unknownEntries, genPath);
        if (rc != 0)
            return rc;
    }
    if (profThread.joinable())
    {
        profStop.store(true);
        profThread.join();
    }
    {
        // Native-program registry counters (src/lib/vu/native): entered = runs a native program
        // took over, ended = it ran the whole program to the E bit, handbacks = it gave control
        // back to the microcode. Printed on every run so a --verify without --native shows zeros.
        extern std::atomic<uint64_t> g_vu1NativeEntered, g_vu1NativeEnded, g_vu1NativeHandBacks;
        std::fprintf(stderr, "[vu1_replay] native entered=%llu ended=%llu handbacks=%llu\n",
                     (unsigned long long)g_vu1NativeEntered.load(),
                     (unsigned long long)g_vu1NativeEnded.load(),
                     (unsigned long long)g_vu1NativeHandBacks.load());
    }
    std::fprintf(stderr, "[vu1_replay] %zu programs x%d: %llu cycles, %llu pairs, host %.1f ms, %.1f ns/cycle, %.1f ns/pair\n",
                 inputs.size(), repeat, (unsigned long long)totalCycles, (unsigned long long)totalPairs,
                 totalHostNs / 1e6, totalCycles ? totalHostNs / (double)totalCycles : 0.0,
                 totalPairs ? totalHostNs / (double)totalPairs : 0.0);
    if (!verifyPath.empty())
    {
        std::printf("%s: %d mismatching field(s)\n", mismatches ? "FAIL" : "PASS", mismatches);
        return mismatches ? 1 : 0;
    }
    return 0;
}
