// vu1_replay: run one VU1 program dump (PS2X_VU1_DUMP=<dir> -> vu1_prog_N.bin) through the runtime's
// VU1 interpreter offline and save every XGKICK packet it produces.
//
//   vu1_replay <dump.bin> [--out packets.bin] [--trace]
//
// Dump layout: uint32 startPc, top, itop, codeSize; 16 KB code; 16 KB data; int32 vi[16]; float
// vf[32][4] (the register file at program start — VU registers persist across MSCALs, so the dump
// restores them before running). The packet file is a sequence of (uint32 length, bytes) records;
// tools_py/gif_packets.py parses them into vertices.
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
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

int main(int argc, char **argv)
{
    if (argc < 2)
    {
        std::fprintf(stderr, "usage: vu1_replay <dump.bin> [--out packets.bin] [--trace]\n");
        return 2;
    }
    std::string outPath = "vu1_packets.bin";
    bool trace = false;
    for (int i = 2; i < argc; ++i)
    {
        if (!std::strcmp(argv[i], "--out") && i + 1 < argc)
            outPath = argv[++i];
        else if (!std::strcmp(argv[i], "--trace"))
            trace = true;
    }

    FILE *fp = std::fopen(argv[1], "rb");
    if (!fp)
    {
        std::fprintf(stderr, "cannot open %s\n", argv[1]);
        return 1;
    }
    uint32_t hdr[4] = {0, 0, 0, 0};
    std::vector<uint8_t> code(0x4000), data(0x4000);
    int32_t vi[16] = {0};
    float vf[32][4] = {};
    if (std::fread(hdr, sizeof(hdr), 1, fp) != 1 ||
        std::fread(code.data(), 1, code.size(), fp) != code.size() ||
        std::fread(data.data(), 1, data.size(), fp) != data.size() ||
        std::fread(vi, sizeof(vi), 1, fp) != 1 ||
        std::fread(vf, sizeof(vf), 1, fp) != 1)
    {
        std::fprintf(stderr, "short dump file\n");
        return 1;
    }
    std::fclose(fp);

    _putenv("PS2X_GS_BACKEND=cpu");
    if (trace)
        _putenv("PS2X_TRACE_VU=0");

    GS gs;
    PS2Memory memory;
    std::vector<uint8_t> packets;
    uint32_t packetCount = 0;
    memory.setGifPacketCallback([&](const uint8_t *p, uint32_t n) {
        const uint32_t len = n;
        packets.insert(packets.end(), reinterpret_cast<const uint8_t *>(&len), reinterpret_cast<const uint8_t *>(&len) + 4);
        packets.insert(packets.end(), p, p + n);
        ++packetCount;
    });

    VU1Interpreter vu(VU1Interpreter::Unit::VU1);
    vu.reset();
    std::memcpy(vu.m_state.vi, vi, sizeof(vi));
    std::memcpy(vu.m_state.vf, vf, sizeof(vf));
    vu.execute(code.data(), static_cast<uint32_t>(code.size()), data.data(), static_cast<uint32_t>(data.size()),
               gs, &memory, hdr[0], hdr[1], hdr[2], 1u << 28);

    std::printf("pc=0x%x top=0x%x itop=0x%x: %u packets, %zu bytes, %llu cycles, end pc=0x%x\n",
                hdr[0], hdr[1], hdr[2], packetCount, packets.size(), (unsigned long long)vu.m_cycle, vu.m_state.pc);
    if (FILE *out = std::fopen(outPath.c_str(), "wb"))
    {
        std::fwrite(packets.data(), 1, packets.size(), out);
        std::fclose(out);
    }
    return 0;
}
