// SOCOM II: U.S. Navy SEALs (SCUS_972.75, r0001) — game-specific EE overrides.
//
// The retail boot ELF is a loader that (1) looks for the r0004 update on the memory card,
// (2) otherwise loads OVERLAY/REL/DNAS.BIN and uses libdnas2 to decrypt RUN/RAW/APACHE00.ZDB
// into the FTSCore (0x1e7000) and ZSealEtc (0x4c5380) overlays, then (3) jumps to 0x4c53c0.
// Our recompiled image (game/overlays/socom2_game.elf) already contains both overlays in
// plaintext, so the loader's decrypt path is replaced by "success" and the memory-card
// update path by "not found".  See docs/research/05-code-package-and-harness.md.
#include "game_overrides.h"
#include "ps2_stubs.h"
#include "Kernel/Stubs/LibC.h"
#include "Kernel/Stubs/MPEG.h"
#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include "runtime/ps2_memory.h"
#include "runtime/ee_scheduler.h"
#include "runtime/socom2_chat.h"
#include "runtime/socom2_freeze_fields.h"
#include "runtime/socom2_music_trace.h"
#include "runtime/socom2_addresses.h"
#include "runtime/socom2_osk_prefill.h"
#include "runtime/socom2_revision_guard.h"
#include "runtime/ps2_audio.h"
#include "socom2_rsa_key.h"
#include "socom2_host_input.h"
#include "socom2_libnetb.h"
#include "socom2_crypto.h"
#include "Kernel/HleStats.h"
#include "Kernel/SchedTrace.h"
#include <cstring>
#include <cmath>
#include <fstream>
#include <vector>
#include <thread>
#include <unordered_map>
#ifdef _WIN32
#include <windows.h>
#include <tlhelp32.h>
#else
// Sprint 8 Goal 1 design item 3: the Linux halves of the crash handler and of the host PC sampler.
// Nothing here is visible to the Windows build.
#include <cerrno>
#include <csignal>
#include <cstdio>
#include <dlfcn.h>
#include <pthread.h>
#include <execinfo.h>
#include <unistd.h>
#include "ThreadNaming.h"
#if defined(__linux__)
#include <ucontext.h>
#include <sys/syscall.h>
#include <dirent.h>
#include <ctime>
#endif
#endif
#include <chrono>
#include <cstdlib>

#include <cstdint>
#include <atomic>
// Set by PS2X_TRIGGER (see startPcSampler); read by the "trig" trace modes.
std::atomic<bool> g_ps2xTraceArmed{false};
#include <filesystem>
#include <iomanip>
#include "runtime/socom2_lum_readback.h"
#include "runtime/socom2_cull_trace.h"
#include "ps2x/knobs.h"
#include <iostream>
#include <sstream>
#include <algorithm>
#include <array>
#include <utility>

// Bound at recompile time via recomp/socom2.toml: "socom2_RsaGenerateKeyPair@0x0062B168".
// rt_crypt FUN_0062b168(LargeInt *n, LargeInt *d) generates a 512-bit RSA key pair with two random
// 256-bit primes (e = 17); the prime search takes minutes under recompiled code and a fixed key
// pair is equivalent for a private server, so the precomputed limbs are written instead.
namespace ps2_stubs
{
    void socom2_RsaGenerateKeyPair(uint8_t *rdram, R5900Context *ctx, PS2Runtime *)
    {
        const uint32_t nAddr = GPR_U32(ctx, 4);
        const uint32_t dAddr = GPR_U32(ctx, 5);
        // PS2X_SOCOM2_RSA_KEY=b selects the second precomputed pair: two instances of the exe on
        // one host otherwise publish the *same* public key in their DME 0x18 client record, while
        // two PCSX2 clients publish distinct random keys (server/logs/console-DME.log).
        const char *keyEnv = ps2x::knob("PS2X_SOCOM2_RSA_KEY");
        const bool keyB = keyEnv && (*keyEnv == 'b' || *keyEnv == 'B' || *keyEnv == '1');
        std::memcpy(rdram + (nAddr & PS2_RAM_MASK), keyB ? kSocom2RsaNb : kSocom2RsaN, sizeof(kSocom2RsaN));
        std::memcpy(rdram + (dAddr & PS2_RAM_MASK), keyB ? kSocom2RsaDb : kSocom2RsaD, sizeof(kSocom2RsaD));
        std::cout << "[socom2] rt_crypt RSA key pair -> fixed precomputed key " << (keyB ? "B" : "A") << std::endl;
        ctx->pc = GPR_U32(ctx, 31);
    }

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

    // ---- SIF sreg handshake (ONLINE path) ------------------------------------------------------
    // After loading the network IRX set (NETCNF, INET, INETCTL, PPP, PPPOE, SMAP, MSIFRPC,
    // LIBNETB) the game's FUN_001bcd80 registers a SIF command handler (0x80000018), sends the
    // system command SETSREG (0x80000001, {reg=1, val=1}) to the IOP and then spins on its own
    // EE-side sreg table (`sceSifGetSreg` = DAT_001da6c0[reg]) until the IOP module answers with
    // the same SETSREG towards the EE. There is no IOP module here to answer, so mirror the write
    // into the EE table immediately; the generic stub then copies the payload and returns 1.
    void socom2_SifSendCmd(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint32_t cid = GPR_U32(ctx, 4);
        const uint32_t packet = GPR_U32(ctx, 5);
        if (cid == 0x80000001u && packet != 0u)
        {
            const uint32_t reg = *reinterpret_cast<const uint32_t *>(rdram + ((packet + 16u) & PS2_RAM_MASK));
            const uint32_t val = *reinterpret_cast<const uint32_t *>(rdram + ((packet + 20u) & PS2_RAM_MASK));
            if (reg < 32u)
            {
                *reinterpret_cast<uint32_t *>(rdram + ((0x001da6c0u + reg * 4u) & PS2_RAM_MASK)) = val;
                std::cout << "[socom2] SIF SETSREG reg=" << reg << " val=" << val
                          << " mirrored into the EE sreg table" << std::endl;
            }
        }
        ps2_stubs::sceSifSendCmd(rdram, ctx, runtime);
    }

    // ---- msifrpc (multi-SIF RPC) HLE ----------------------------------------------------------
    // SCE-RT's libnetb EE library (0x245ad8..0x2472xx) talks to LIBNETB.IRX through msifrpc:
    // FUN_001bd050 bind(client, sid, 0, bufSize, p5, p6) -> SIF cmd 0x80000019 + WaitSema,
    // FUN_001bd320 call(client, fno, 0, send, sendSize, recv, recvSize, cb, cbArg) -> 0x8000001a,
    // FUN_001bd200 unbind(client, 0) -> 0x8000001d. The replies come back as SIF commands handled
    // by FUN_001bcf20, which fills the client struct and signals the semaphores. With no IOP the
    // calls are answered synchronously here: the libnetb service (sid 0x80001201) is dispatched
    // by function number to a host implementation; the result word the EE wrappers read is the
    // first u32 of the receive buffer.
    // Client struct (u32 index): [0] packet, [1] ?, [2] reply sema, [4] sid, [5] IOP buffer,
    // [9] IOP handle (non-zero = bound), [10] mutex sema, [11] unbind result,
    // [12] buffer size (wrappers check it as +0x30), [13],[14] bind extras.
    constexpr uint32_t kLibnetbSid = 0x80001201u;

    uint32_t rd32(const uint8_t *rdram, uint32_t addr)
    {
        uint32_t v;
        std::memcpy(&v, rdram + (addr & PS2_RAM_MASK), 4);
        return v;
    }

    void wr32(uint8_t *rdram, uint32_t addr, uint32_t v)
    {
        std::memcpy(rdram + (addr & PS2_RAM_MASK), &v, 4);
    }

    // libnetb service 0x80001201: dispatched in socom2_libnetb.cpp (docs/research/10-libnetb-rpc.md).
    void socom2LibnetbCall(uint8_t *rdram, uint32_t fno, uint32_t send, uint32_t sendSize,
                           uint32_t recv, uint32_t recvSize)
    {
        static const bool s_netTrace = ps2x::knob("PS2X_SOCOM2_NET_TRACE") != nullptr;   // was a getenv on every libnetb RPC
        if (s_netTrace)
            std::cout << "[socom2/msifrpc] libnetb fno=0x" << std::hex << fno << std::dec << " send=" << sendSize << " recv=" << recvSize << std::endl;
        socom2_libnetb::call(rdram, fno, send, sendSize, recv, recvSize);
    }

    void socom2_MsifBind(uint8_t *rdram, R5900Context *ctx, PS2Runtime *)
    {
        const uint32_t client = GPR_U32(ctx, 4);
        const uint32_t sid = GPR_U32(ctx, 5);
        const uint32_t bufSize = GPR_U32(ctx, 7);
        wr32(rdram, client + 4u * 4u, sid);
        wr32(rdram, client + 5u * 4u, 0u);
        wr32(rdram, client + 9u * 4u, 1u);          // "bound"
        wr32(rdram, client + 11u * 4u, 0u);
        wr32(rdram, client + 12u * 4u, bufSize);
        std::cout << "[socom2/msifrpc] bind sid=0x" << std::hex << sid << " bufSize=0x" << bufSize << std::dec
                  << " -> host HLE" << std::endl;
        SET_GPR_U32(ctx, 2, 0u);
        ctx->pc = GPR_U32(ctx, 31);
    }

    void socom2_MsifUnbind(uint8_t *rdram, R5900Context *ctx, PS2Runtime *)
    {
        const uint32_t client = GPR_U32(ctx, 4);
        wr32(rdram, client + 9u * 4u, 0u);
        SET_GPR_U32(ctx, 2, 1u);                    // the wrapper loops until unbind returns 1
        ctx->pc = GPR_U32(ctx, 31);
    }

    void socom2_MsifCall(uint8_t *rdram, R5900Context *ctx, PS2Runtime *)
    {
        const uint32_t client = GPR_U32(ctx, 4);
        const uint32_t fno = GPR_U32(ctx, 5);
        const uint32_t mode = GPR_U32(ctx, 6);
        const uint32_t send = GPR_U32(ctx, 7);
        // EE ABI: arguments 5..8 travel in t0..t3, the 9th on the stack.
        const uint32_t sendSize = GPR_U32(ctx, 8);
        const uint32_t recv = GPR_U32(ctx, 9);
        const uint32_t recvSize = GPR_U32(ctx, 10);
        int32_t result = -1;
        if (mode == 0u)
        {
            const uint32_t sid = rd32(rdram, client + 4u * 4u);
            if (sid == kLibnetbSid)
            {
                socom2LibnetbCall(rdram, fno, send, sendSize, recv, recvSize);
                result = 0;                          // transport ok; the result word is in recv[0]
            }
            else
            {
                std::cout << "[socom2/msifrpc] call to unknown sid=0x" << std::hex << sid << " fno=0x" << fno << std::dec << std::endl;
            }
        }
        SET_GPR_U32(ctx, 2, static_cast<uint32_t>(result));
        ctx->pc = GPR_U32(ctx, 31);
    }

    // FUN_001bcd80: msifrpc init (SIF handler + sreg handshake). Nothing to set up on the host.
    void socom2_MsifInit(uint8_t *, R5900Context *ctx, PS2Runtime *)
    {
        ctx->pc = GPR_U32(ctx, 31);
    }

    // FUN_002cc670: the DNAS authentication state tick (creates the libdnas2 object on the first
    // call, returns 1 when authentication has finished). A private server needs no DNAS, so the
    // tick reports "done" immediately; this is what the published r0001 pnach (`jr ra` at the
    // entry, with v0 still holding the previous call's 1) achieves on PCSX2.
    void socom2_DnasTickDone(uint8_t *, R5900Context *ctx, PS2Runtime *)
    {
        SET_GPR_U32(ctx, 2, 1u);
        ctx->pc = GPR_U32(ctx, 31);
    }

    // ---- libpad2 (scePad2*) HLE ----------------------------------------------------------------
    // The game statically links Sony's socket-based libpad2 (scePad2Init/CreateSocket/Read/
    // GetState/GetButtonInfo) which RPCs to SIO2MAN/DS2U on the IOP. Those IOP drivers are not
    // emulated, so the wrappers were stubbed to return 0 and the game's per-frame reader
    // (FUN_002da930) saw no controller. We HLE the five top-level entry points to report one
    // connected DualShock2 on port 0 with neutral input, bypassing the IOP path entirely.
    // Button ids 0x10-0x13 are the analog axes (center 0x80); 0x00-0x0F are the digital buttons
    // (0 = released). Host input injection (real button presses) hooks the same shared state later.
    Socom2PadState g_socom2Pad;   // refreshed from the host by socom2HostInputPoll (socom2_host_input.cpp)

    // The pad HLE is on by default (Sprint 9 Goal 3, R160); PS2X_SOCOM2_PAD=0 boots with no controller, as
    // every boot did before input worked. When disabled these behave like the previous ret0 stubs (no
    // controller).
    bool socom2PadEnabled()
    {
        static const bool on = ps2x::knobOn("PS2X_SOCOM2_PAD", true);   // R160: on unless 0
        return on;
    }

    void scePad2Init(uint8_t *, R5900Context *ctx, PS2Runtime *)
    {
        SET_GPR_U32(ctx, 2, socom2PadEnabled() ? 1u : 0u);   // > 0 = ok
        ctx->pc = GPR_U32(ctx, 31);
    }

    // One DualShock2 only: socket 0 (the first CreateSocket) is connected; every other socket the
    // game opens (port 2, multitap slots) reports "no controller". Reporting all of them connected
    // made the shell count several local players and route the UI to a pad that never gets data.
    uint32_t g_socom2NextSocket = 0u;

    void scePad2CreateSocket(uint8_t *rdram, R5900Context *ctx, PS2Runtime *)
    {
        const uint32_t descriptor = GPR_U32(ctx, 4);
        const uint32_t socket = g_socom2NextSocket++;
        if (ps2x::knob("PS2X_SOCOM2_PAD_TRACE"))
        {
            uint32_t words[2] = {0u, 0u};
            if (descriptor != 0u)
                std::memcpy(words, rdram + (descriptor & PS2_RAM_MASK), sizeof(words));
            std::cout << "[pad-trace] CreateSocket desc=0x" << std::hex << descriptor << " [" << words[0] << " " << words[1]
                      << "] -> socket " << std::dec << socket << std::endl;
        }
        SET_GPR_U32(ctx, 2, socket);
        ctx->pc = GPR_U32(ctx, 31);
    }

    void scePad2GetState(uint8_t *, R5900Context *ctx, PS2Runtime *)
    {
        // The game opens a socket for its controller check at boot, deletes it, then opens the
        // one it actually reads; the HLE never sees the delete, so treat the newest socket as the
        // live one.
        const uint32_t socket = GPR_U32(ctx, 4);
        const bool connected = socom2PadEnabled() && g_socom2NextSocket != 0u && socket == g_socom2NextSocket - 1u;
        SET_GPR_U32(ctx, 2, connected ? 1u : 0u);   // 1 = connected/ready, 0 = nothing on this socket
        ctx->pc = GPR_U32(ctx, 31);
    }

    void scePad2Read(uint8_t *rdram, R5900Context *ctx, PS2Runtime *)
    {
        // Write a standard DualShock2 poll report into the caller's buffer (a1) for any code that
        // reads it raw, and return a positive data length so FUN_002da930 proceeds.
        const uint32_t buf = GPR_U32(ctx, 5) & PS2_RAM_MASK;
        if (socom2PadEnabled())
            socom2HostInputPoll(g_socom2Pad);
        uint8_t report[32] = {0};
        report[0] = 0x00;
        report[1] = 0x79;                   // DS2 analog + pressure mode
        report[2] = 0x5Au;
        report[3] = 0xFFu;                  // digital buttons, active-low
        report[4] = 0xFFu;
        for (int id = 0; id < 16; ++id)
        {
            if (g_socom2Pad.button[id])
                report[3 + id / 8] = static_cast<uint8_t>(report[3 + id / 8] & ~(1u << (id % 8)));
        }
        report[5] = g_socom2Pad.axis[0];    // RX
        report[6] = g_socom2Pad.axis[1];    // RY
        report[7] = g_socom2Pad.axis[2];    // LX
        report[8] = g_socom2Pad.axis[3];    // LY
        for (int field = 0; field < 12; ++field)
            report[9 + field] = socom2PressureOf(g_socom2Pad, field);   // R139: Triangle's may be light
        std::memcpy(rdram + buf, report, sizeof(report));
        // PS2X_SOCOM2_PAD_TRACE=1: log the first non-neutral reports the game reads.
        static const bool s_padTrace = ps2x::knob("PS2X_SOCOM2_PAD_TRACE") != nullptr;
        if (s_padTrace && (report[3] != 0xFFu || report[4] != 0xFFu))
        {
            static uint32_t s_lines = 0;
            if (s_lines++ < 40u)
                std::cout << "[pad-trace] read: buttons=" << std::hex << (unsigned)report[3] << " " << (unsigned)report[4]
                          << " axes=" << (unsigned)report[5] << "," << (unsigned)report[6] << "," << (unsigned)report[7] << "," << (unsigned)report[8]
                          << std::dec << std::endl;
        }
        SET_GPR_U32(ctx, 2, static_cast<uint32_t>(sizeof(report)));
        ctx->pc = GPR_U32(ctx, 31);
    }

    void scePad2GetButtonInfo(uint8_t *, R5900Context *ctx, PS2Runtime *)
    {
        // a2 = button id. 0x10-0x13 = analog axes (center 0x80); else digital button pressure.
        const uint32_t id = GPR_U32(ctx, 6);
        uint32_t value;
        if (id >= 0x10u && id <= 0x13u)
            value = g_socom2Pad.axis[id - 0x10u];
        else if (id < 0x10u)
            value = g_socom2Pad.button[id];
        else if (id >= 0x14u && id <= 0x1fu)
            value = socom2PressureOf(g_socom2Pad, static_cast<int>(id - 0x14u));   // R139: Triangle's may be light
        else
            value = 0u;
        // PS2X_SOCOM2_PAD_TRACE=1: which ids does the game poll, and what did it get for pressed ones?
        static const bool s_padTrace = ps2x::knob("PS2X_SOCOM2_PAD_TRACE") != nullptr;
        if (s_padTrace)
        {
            static uint32_t s_seenMask = 0u;
            static uint32_t s_pressedLines = 0u;
            const uint32_t bit = id < 32u ? (1u << id) : 0u;
            if (bit && !(s_seenMask & bit))
            {
                s_seenMask |= bit;
                std::cout << "[pad-trace] GetButtonInfo polls id 0x" << std::hex << id << std::dec << std::endl;
            }
            static uint32_t s_lastValue[32] = {0};
            if (id < 32u && value != s_lastValue[id] && s_pressedLines++ < 200u)
            {
                std::cout << "[pad-trace] GetButtonInfo id 0x" << std::hex << id << " " << s_lastValue[id] << " -> " << value << std::dec << std::endl;
                s_lastValue[id] = value;
            }
        }
        SET_GPR_U32(ctx, 2, value);
        ctx->pc = GPR_U32(ctx, 31);
    }

    // The three remaining libpad2 entry points the game calls each frame (FUN_002da930) are
    // *not* covered by the socket HLE above: natively they read the DMA double buffer registered
    // by scePad2CreateSocket (never set up by the HLE) and talk to DBCMAN through libdbc
    // (sceDbcReceiveData / SendData2). Answering them here keeps the pad state machine consistent
    // (state 0 -> 1 needs GetButtonProfile >= 0 and sceVibGetProfile >= 0) and keeps libdbc idle.
    void scePad2GetButtonProfile(uint8_t *rdram, R5900Context *ctx, PS2Runtime *)
    {
        // a1 = destination for the 40-bit button profile (bit n = button n supported). A DualShock2
        // reports the 16 digital buttons and the 16 analog/pressure fields (ids 0x00-0x1f).
        const uint32_t buf = GPR_U32(ctx, 5) & PS2_RAM_MASK;
        static const uint8_t kDs2Profile[5] = {0xFFu, 0xFFu, 0xFFu, 0xFFu, 0x00u};
        uint32_t length = 0u;
        if (socom2PadEnabled())
        {
            std::memcpy(rdram + buf, kDs2Profile, sizeof(kDs2Profile));
            length = static_cast<uint32_t>(sizeof(kDs2Profile));
        }
        SET_GPR_U32(ctx, 2, socom2PadEnabled() ? length : 0xFFFFFFFFu);
        ctx->pc = GPR_U32(ctx, 31);
    }

    void sceVibGetProfile(uint8_t *rdram, R5900Context *ctx, PS2Runtime *)
    {
        // a1 = actuator profile buffer; the game only sends SetActParam when byte 0 is nonzero.
        // Report no actuators (0 bytes, buffer zeroed) so no vibration traffic is generated.
        const uint32_t buf = GPR_U32(ctx, 5) & PS2_RAM_MASK;
        std::memset(rdram + buf, 0, 2);
        SET_GPR_U32(ctx, 2, 0u);            // count 0, >= 0 = success
        ctx->pc = GPR_U32(ctx, 31);
    }

    void sceVibSetActParam(uint8_t *, R5900Context *ctx, PS2Runtime *)
    {
        SET_GPR_U32(ctx, 2, 1u);            // accepted
        ctx->pc = GPR_U32(ctx, 31);
    }
}

namespace
{
    inline void returnTo(R5900Context *ctx, uint32_t value)
    {
        SET_GPR_U32(ctx, 2, value);
        ctx->pc = GPR_U32(ctx, 31);
    }

    // The loader's crt0 zero-fills 0x1d5600..0x686f80 (its own bss, which spans the overlay
    // slots) *after* our ELF loader placed the overlays there.  Restore them from the ELF file.
    bool reloadOverlaySegments(uint8_t *rdram)
    {
        const auto elfPath = PS2Runtime::getIoPaths().elfPath;
        std::ifstream f(elfPath, std::ios::binary);
        if (!f)
            return false;
        std::vector<uint8_t> hdr(52);
        f.read(reinterpret_cast<char *>(hdr.data()), 52);
        uint32_t phoff, phnum;
        std::memcpy(&phoff, hdr.data() + 0x1c, 4);
        uint16_t phnum16;
        std::memcpy(&phnum16, hdr.data() + 0x2c, 2);
        phnum = phnum16;
        int restored = 0;
        for (uint32_t i = 0; i < phnum; ++i)
        {
            uint8_t ph[32];
            f.seekg(phoff + i * 32);
            f.read(reinterpret_cast<char *>(ph), 32);
            uint32_t type, off, vaddr, filesz, memsz;
            std::memcpy(&type, ph + 0, 4);
            std::memcpy(&off, ph + 4, 4);
            std::memcpy(&vaddr, ph + 8, 4);
            std::memcpy(&filesz, ph + 16, 4);
            std::memcpy(&memsz, ph + 20, 4);
            // 0x1e7000 is the FIRST OVERLAY'S LOAD ADDRESS -- where FTSCore starts, so everything at or
            // above it is overlay content to restore. It is not the same boundary as
            // socom2_addresses::kOverlayBase (0x1d5600), which is the end of the LOADER'S DATA: the gap
            // between them belongs to neither, and the table's invariant only has to exclude the loader.
            if (type != 1 || vaddr < 0x001e7000u || memsz == 0)
                continue;
            uint8_t *dst = getMemPtr(rdram, vaddr);
            if (!dst)
                continue;
            if (filesz)
            {
                f.seekg(off);
                f.read(reinterpret_cast<char *>(dst), filesz);
            }
            if (memsz > filesz)
                std::memset(dst + filesz, 0, memsz - filesz);
            ++restored;
        }
        std::cout << "[socom2] restored " << restored << " overlay segments from " << elfPath.filename().string() << std::endl;
        return restored > 0;
    }

    // FUN_001c59c0: load DNAS.BIN from disc, decrypt APACHE00.ZDB into both overlay slots and run
    // each overlay's static constructors (loader FUN_00182840(ctor_start, ctor_end, 0, 0)).
    // Here: restore the plaintext overlays and invoke the constructors as guest calls.
    void socom2_LoadGameCodeFromDisc(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        std::cout << "[socom2] LoadGameCodeFromDisc -> restoring overlays, running static constructors" << std::endl;
        reloadOverlaySegments(rdram);

        // Loader's __initialize_cpp_rts(ctor_start, ctor_end, 0, 0) walks a table and calls each
        // constructor; one guest call per overlay keeps the scheduler's invocation stack shallow.
        constexpr uint32_t kInitCppRts = 0x00182840u;
        // beginField/endField name the socom2_addresses::Table members these two came out of, so the
        // guard below can say which field a revision failed to place rather than just which overlay.
        struct Table { uint32_t begin, end; const char *beginField, *endField, *name; };
        const socom2_addresses::Table &addr = socom2_addresses::current();
        const Table tables[] = {{addr.ctorTableFtsBegin, addr.ctorTableFtsEnd,
                                 "ctorTableFtsBegin", "ctorTableFtsEnd", "FTSCore"},
                                {addr.ctorTableZsealBegin, addr.ctorTableZsealEnd,
                                 "ctorTableZsealBegin", "ctorTableZsealEnd", "ZSealEtc"}};
        std::vector<GuestInvocation> invocations;
        if (!runtime->hasFunction(kInitCppRts))
        {
            std::cout << "[socom2] __initialize_cpp_rts (0x182840) has no recompiled body!" << std::endl;
        }
        else
        {
            for (const Table &t : tables)
            {
                // A revision whose column could not place this table says so and runs no constructors
                // for that overlay -- running r0001's table addresses against another build's data
                // would call whatever happens to sit there.
                if (!socom2_addresses::require(t.begin, t.beginField) ||
                    !socom2_addresses::require(t.end, t.endField))
                    continue;
                GuestInvocation inv{};
                inv.kind = GuestInvocationKind::HleCall;
                inv.context = *ctx;
                inv.context.pc = kInitCppRts;
                SET_GPR_U32(&inv.context, 4, t.begin);
                SET_GPR_U32(&inv.context, 5, t.end);
                SET_GPR_U32(&inv.context, 6, 0u);
                SET_GPR_U32(&inv.context, 7, 0u);
                SET_GPR_U32(&inv.context, 29, 0u);   // scheduler assigns an invocation stack
                SET_GPR_U32(&inv.context, 31, 0u);   // scheduler supplies the return trampoline
                invocations.push_back(std::move(inv));
                std::cout << "[socom2]   " << t.name << ": " << ((t.end - t.begin) / 4) << " static constructors via __initialize_cpp_rts" << std::endl;
            }
        }

        // resume state of the caller once the constructors have run
        returnTo(ctx, 1);
        if (invocations.empty())
            return;
        EeScheduler &scheduler = runtime->eeScheduler();
        scheduler.bindMainContextForSyscall(*ctx, rdram);
        scheduler.invokeCurrentSequence(std::move(invocations));
    }

    // FUN_001c5b30(port): load the r0004 update from the memory card.  0 = not present.
    //
    // Task 11 (Sprint 11 Goal D), so the launcher's GAME VERSION selector is not misread against this:
    // a revision is COMPILED IN here, never hot-loaded. On the console r0004 arrived as game code on a
    // memory card and this function pulled it in at runtime; a recompilation cannot, because the code it
    // would load has to have been through the recompiler. An r0004 build is therefore a SECOND
    // executable (launcher::kGameRevisions names it socom2_r0004.exe), not this one patching itself --
    // which is why BOTH builds answer "no update present" here, and why the answer stays 0 even in the
    // r0004 build, where the update is not an update but the whole game.
    void socom2_LoadGameCodeFromMemcard(uint8_t *, R5900Context *ctx, PS2Runtime *)
    {
        std::cout << "[socom2] LoadGameCodeFromMemcard -> none" << std::endl;
        returnTo(ctx, 0);
    }

    // FUN_00181c90(path, dest): load an MWo3 overlay file (only used for DNAS.BIN).
    void socom2_LoadOverlayFile(uint8_t *, R5900Context *ctx, PS2Runtime *)
    {
        std::cout << "[socom2] LoadOverlayFile(" << std::hex << GPR_U32(ctx, 4) << ", "
                  << GPR_U32(ctx, 5) << std::dec << ") -> stubbed" << std::endl;
        returnTo(ctx, 1);
    }

    // The engine reads the ISO9660 volume descriptor / directory records itself (sector 16...)
    // and then reads files by LBN, so the disc must be available as a raw image.  Look for an
    // .iso next to the ELF or one directory up; otherwise honour PS2X_CD_IMAGE.
    void configureCdImage()
    {
        PS2Runtime::IoPaths paths = PS2Runtime::getIoPaths();
        if (!paths.cdImage.empty())
            return;
        if (const char *env = ps2x::knob("PS2X_CD_IMAGE"); env && *env)
        {
            paths.cdImage = env;
        }
        else
        {
            std::error_code ec;
            for (const auto &dir : {paths.elfDirectory, paths.elfDirectory.parent_path()})
            {
                for (const auto &e : std::filesystem::directory_iterator(dir, ec))
                {
                    auto ext = e.path().extension().string();
                    for (auto &c : ext) c = static_cast<char>(std::tolower(c));
                    if (ext == ".iso") { paths.cdImage = e.path(); break; }
                }
                if (!paths.cdImage.empty()) break;
            }
        }
        if (paths.cdImage.empty())
        {
            std::cout << "[socom2] WARNING: no .iso found; raw sector reads will fail" << std::endl;
            return;
        }
        std::cout << "[socom2] CD image: " << paths.cdImage.string() << std::endl;
        PS2Runtime::setIoPaths(paths);
    }

    // PS2X_PC_SAMPLER=<seconds>: print the live guest PC and the scheduler thread table
    // periodically (diagnosing silent hangs).
    void startPcSampler(PS2Runtime &runtime)
    {
        // PS2X_WATCH="0xADDR[,0xADDR...]": poll guest words every ~0.5 ms and print every change with
        // the host time, the new value and the live guest pc/ra — a poor man's write watchpoint
        // (which code cuts a linked list, at what moment relative to the call trace).
        if (const char *watch = ps2x::knob("PS2X_WATCH"))
        {
            std::vector<uint32_t> addrs;
            std::string spec(watch);
            size_t pos = 0;
            while (pos < spec.size())
            {
                size_t end = spec.find(',', pos);
                if (end == std::string::npos)
                    end = spec.size();
                addrs.push_back(static_cast<uint32_t>(std::strtoul(spec.substr(pos, end - pos).c_str(), nullptr, 0)));
                pos = end + 1;
            }
            // PS2X_WATCH_HUGE="0xADDR:words": scan a range every ~0.5 ms and print the first 60
            // words that turn from a sane float (|x| < 1e9) into a huge one (|x| >= 1e15 or NaN),
            // with the host time and the word's offset — where an object's state first explodes.
            std::vector<std::pair<uint32_t, uint32_t>> hugeRanges;
            if (const char *hw = ps2x::knob("PS2X_WATCH_HUGE"))
            {
                std::string hs(hw);
                size_t p = 0;
                while (p < hs.size())
                {
                    size_t e = hs.find(',', p);
                    if (e == std::string::npos)
                        e = hs.size();
                    std::string item = hs.substr(p, e - p);
                    p = e + 1;
                    uint32_t words = 64;
                    const size_t colon = item.find(':');
                    if (colon != std::string::npos)
                    {
                        words = static_cast<uint32_t>(std::strtoul(item.c_str() + colon + 1, nullptr, 0));
                        item = item.substr(0, colon);
                    }
                    hugeRanges.emplace_back(static_cast<uint32_t>(std::strtoul(item.c_str(), nullptr, 0)), words);
                }
            }
            std::thread([&runtime, addrs, hugeRanges]() {
                std::vector<uint32_t> last(addrs.size(), 0xDEADBEEFu);
                std::vector<std::vector<uint8_t>> hugeState;
                for (const auto &r : hugeRanges)
                    hugeState.emplace_back(r.second, 0u);   // 0 unknown, 1 sane, 2 huge
                int hugePrinted = 0;
                const auto epoch = std::chrono::steady_clock::now();
                for (;;)
                {
                    std::this_thread::sleep_for(std::chrono::microseconds(500));
                    const uint8_t *rdram = runtime.memory().getRDRAM();
                    for (size_t r = 0; r < hugeRanges.size() && hugePrinted < 60; ++r)
                    {
                        for (uint32_t w = 0; w < hugeRanges[r].second && hugePrinted < 60; ++w)
                        {
                            uint32_t bits = 0;
                            std::memcpy(&bits, rdram + ((hugeRanges[r].first + w * 4u) & PS2_RAM_MASK), sizeof(bits));
                            float x;
                            std::memcpy(&x, &bits, sizeof(x));
                            const bool isHuge = (x != x) || std::fabs(x) >= 1e15f;
                            const bool isSane = !isHuge && std::fabs(x) < 1e9f && (bits & 0x7F800000u) != 0u;
                            uint8_t &st = hugeState[r][w];
                            if (isSane)
                                st = 1;
                            else if (isHuge && st == 1)
                            {
                                st = 2;
                                const R5900Context *c = &runtime.cpu();
                                const double t = std::chrono::duration<double>(std::chrono::steady_clock::now() - epoch).count();
                                std::printf("[watch-huge] %.3fs @%08x (+0x%x) = %08x (%g) pc=0x%x ra=0x%x\n", t,
                                            hugeRanges[r].first + w * 4u, w * 4u, bits, x, c->pc, GPR_U32(c, 31));
                                ++hugePrinted;
                            }
                        }
                    }
                    for (size_t i = 0; i < addrs.size(); ++i)
                    {
                        uint32_t v = 0;
                        std::memcpy(&v, rdram + (addrs[i] & PS2_RAM_MASK), sizeof(v));
                        if (v != last[i])
                        {
                            const R5900Context *c = &runtime.cpu();
                            const double t = std::chrono::duration<double>(std::chrono::steady_clock::now() - epoch).count();
                            std::printf("[watch] %.3fs @%08x = %08x (was %08x) pc=0x%x ra=0x%x\n", t, addrs[i], v, last[i],
                                        c->pc, GPR_U32(c, 31));
                            last[i] = v;
                        }
                    }
                }
            }).detach();
        }
        const char *env = ps2x::knob("PS2X_PC_SAMPLER");
        if (!env || !*env)
            return;
        const double period = std::max(0.01, std::atof(env));   // fractional seconds allowed (0.05 = 20 Hz profile)
        std::thread([&runtime, period]() {
            const auto samplerEpoch = std::chrono::steady_clock::now();
            for (;;)
            {
                std::this_thread::sleep_for(std::chrono::duration<double>(period));
                const R5900Context *c = &runtime.cpu();
                std::ostringstream o;
                o << "[pc-sampler] live pc=0x" << std::hex << c->pc << " ra=0x" << GPR_U32(c, 31)
                  << " sp=0x" << GPR_U32(c, 29) << std::dec;
                const EeKernelSnapshot snap = runtime.eeScheduler().snapshot();
                // Sprint 7 Task 2e / research/29 section 4: host time, the vsync tick, the guest clock and its
                // snapshot sequence, the per-dispatch pc, the executor's idle count, the GS back-pressure and the
                // libnetb wait -- one line that tells the two freeze shapes apart without a second launch.
                FreezeFields::Sample fs;
                fs.hostSeconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - samplerEpoch).count();
                fs.vsyncTick = runtime.eeScheduler().currentVSyncTick();
                fs.eeSeconds = static_cast<double>(snap.eeCycle) / static_cast<double>(EeScheduler::kEeClockHz);
                fs.sequence = snap.sequence;
                fs.debugPc = runtime.debugPc();
                fs.idleWaits = runtime.eeScheduler().idleWaitCount();
                fs.bpPending = runtime.gs().pendingGuestFrames();
                fs.bpWaiters = runtime.gs().backpressureWaiters();
                fs.bpWaitMs = runtime.gs().backpressureWaitNs() / 1000000ull;
                const std::pair<int, uint64_t> net = socom2_libnetb::netWaitState();
                fs.netWait = net.first;
                fs.netWaitMs = net.second;
                o << FreezeFields::line(fs);
                o << " running=" << snap.runningThreadId << " threads:";
                for (const auto &t : snap.threads)
                    o << " [" << t.id << " pc=0x" << std::hex << t.pc << " ra=0x" << t.ra << " sp=0x" << t.sp << std::dec << " st=" << static_cast<int>(t.status)
                      << " prio=" << t.currentPriority   // Task 2a: SOCOM's thread priorities, logged with every sample
                      << " wait=" << static_cast<int>(t.waitReason) << "/" << t.waitId << "]";
                std::cout << o.str() << std::endl;
                // PS2X_PEEK="0xADDR[:words][,...]": dump guest words (hex + float) with each sample.
                if (const char *peek = ps2x::knob("PS2X_PEEK"))
                {
                    std::string spec(peek);
                    size_t pos = 0;
                    std::ostringstream po;
                    po << "[peek]";
                    uint32_t itemCounter = 0;
                    while (pos < spec.size())
                    {
                        size_t end = spec.find(',', pos);
                        if (end == std::string::npos)
                            end = spec.size();
                        std::string item = spec.substr(pos, end - pos);
                        pos = end + 1;
                        const uint32_t itemIndex = itemCounter++;
                        uint32_t words = 1;
                        const size_t colon = item.find(':');
                        if (colon != std::string::npos)
                        {
                            words = static_cast<uint32_t>(std::strtoul(item.c_str() + colon + 1, nullptr, 0));
                            item = item.substr(0, colon);
                        }
                        // Pointer chains: "*0xADDR+0xOFF*+0xOFF2": '*' follows the pointer at the current
                        // address, "+0x.." adds an offset, in the order written. E.g. the mission camera is
                        // "*0x488de8" (static scene 0x4887c0 + 0x628) and the actor it follows
                        // "*0x488de8+0xbc*" (its transform at +0x1070, translation at +0x10a0).
                        uint32_t addr = 0;
                        bool bad = false;
                        {
                            size_t i = 0;
                            bool haveBase = false;
                            while (i < item.size() && !bad)
                            {
                                const char ch = item[i];
                                if (ch == '*')
                                {
                                    if (!haveBase)
                                    {
                                        // leading '*': parse the base number that follows first
                                        size_t j = i + 1;
                                        while (j < item.size() && item[j] != '*' && item[j] != '+')
                                            ++j;
                                        addr = static_cast<uint32_t>(std::strtoul(item.substr(i + 1, j - i - 1).c_str(), nullptr, 0));
                                        haveBase = true;
                                        i = j;
                                    }
                                    else
                                        ++i;
                                    const uint8_t *pp = getConstMemPtr(runtime.memory().getRDRAM(), addr & PS2_RAM_MASK);
                                    if (!pp)
                                    {
                                        bad = true;
                                        break;
                                    }
                                    std::memcpy(&addr, pp, sizeof(addr));
                                    if (addr == 0u)
                                        bad = true;
                                }
                                else if (ch == '+')
                                {
                                    size_t j = i + 1;
                                    while (j < item.size() && item[j] != '*' && item[j] != '+')
                                        ++j;
                                    addr += static_cast<uint32_t>(std::strtoul(item.substr(i + 1, j - i - 1).c_str(), nullptr, 0));
                                    i = j;
                                }
                                else
                                {
                                    size_t j = i;
                                    while (j < item.size() && item[j] != '*' && item[j] != '+')
                                        ++j;
                                    addr = static_cast<uint32_t>(std::strtoul(item.substr(i, j - i).c_str(), nullptr, 0));
                                    haveBase = true;
                                    i = j;
                                }
                            }
                        }
                        if (bad)
                            continue;
                        const uint8_t *p = getConstMemPtr(runtime.memory().getRDRAM(), addr & PS2_RAM_MASK);
                        if (!p)
                            continue;
                        po << " @" << std::hex << addr << ":";
                        for (uint32_t w = 0; w < words && w < 64u; ++w)
                        {
                            uint32_t v = 0;
                            std::memcpy(&v, p + w * 4u, sizeof(v));
                            float fv = 0.0f;
                            std::memcpy(&fv, &v, sizeof(fv));
                            po << " " << std::setw(8) << std::setfill('0') << v << "(" << fv << ")";
                            // PS2X_TRIGGER="lo:hi": when the first word of the first PS2X_PEEK item, read as
                            // a float, lies in [lo, hi], arm the "trig" mode of PS2X_GS_TRACE_CMDS /
                            // PS2X_TRACE_VIF (traces of the exact game state, e.g. the gameplay camera).
                            static const char *s_trig = ps2x::knob("PS2X_TRIGGER");
                            if (s_trig && w == 0u && itemIndex == 0u && !g_ps2xTraceArmed.load())
                            {
                                const double lo = std::atof(s_trig);
                                const char *c = std::strchr(s_trig, ':');
                                const double hi = c ? std::atof(c + 1) : lo;
                                if (fv >= lo && fv <= hi)
                                {
                                    g_ps2xTraceArmed.store(true);
                                    std::printf("[trigger] armed: first peek word %g in [%g, %g]\n", (double)fv, lo, hi);
                                }
                            }
                        }
                        po << std::dec << std::setfill(' ');
                    }
                    std::cout << po.str() << std::endl;
                }
            }
        }).detach();
    }

    // PS2X_RDRAM_DUMP="<path>:<seconds>": write the whole 32 MB guest RAM to <path> once, <seconds>
    // after start (offline inspection of heap structures with Python; heap addresses are
    // deterministic for a given input script).
    void writeRdramDump(const uint8_t *rdram, const std::string &path, const std::string &when)
    {
        std::ofstream f(path, std::ios::binary);
        f.write(reinterpret_cast<const char *>(rdram), PS2_RAM_SIZE);
        std::cout << "[rdram-dump] wrote " << PS2_RAM_SIZE << " bytes to " << path << " at " << when << std::endl;
    }

    // PS2X_RDRAM_DUMP_AT="<path>:<Name>#<n>": dump when the n-th call of the PS2X_CALL_TRACE
    // function <Name> is entered (before it runs).
    std::string g_dumpAtPath, g_dumpAtName;
    uint32_t g_dumpAtCount = 0;
    void initRdramDumpAt()
    {
        const char *env = ps2x::knob("PS2X_RDRAM_DUMP_AT");
        if (!env || !*env)
            return;
        std::string spec(env);
        const size_t hash = spec.rfind('#');
        const size_t colon = spec.rfind(':', hash);
        if (hash == std::string::npos || colon == std::string::npos)
            return;
        g_dumpAtPath = spec.substr(0, colon);
        g_dumpAtName = spec.substr(colon + 1, hash - colon - 1);
        g_dumpAtCount = static_cast<uint32_t>(std::strtoul(spec.c_str() + hash + 1, nullptr, 0));
    }

    void startRdramDump(PS2Runtime &runtime)
    {
        initRdramDumpAt();
        const char *env = ps2x::knob("PS2X_RDRAM_DUMP");
        if (!env || !*env)
            return;
        std::string spec(env);
        const size_t colon = spec.rfind(':');
        int seconds = 10;
        std::string path = spec;
        if (colon != std::string::npos && colon > 1)
        {
            seconds = std::max(1, std::atoi(spec.c_str() + colon + 1));
            path = spec.substr(0, colon);
        }
        std::thread([&runtime, seconds, path]() {
            std::this_thread::sleep_for(std::chrono::seconds(seconds));
            std::ofstream f(path, std::ios::binary);
            f.write(reinterpret_cast<const char *>(runtime.memory().getRDRAM()), PS2_RAM_SIZE);
            std::cout << "[rdram-dump] wrote " << PS2_RAM_SIZE << " bytes to " << path << " at " << seconds << "s" << std::endl;
        }).detach();
    }

    // Host crash reporter: prints the faulting host address relative to the module base (symbolize
    // with `llvm-nm -n dist/socom2.exe`), a host backtrace, and the guest thread table.
    PS2Runtime *g_runtimeForCrash = nullptr;
#ifdef _WIN32
    LONG WINAPI crashHandler(EXCEPTION_POINTERS *info)
    {
        const auto *rec = info->ExceptionRecord;
        // C++ throws (0x20474343 'GCC') and debugger/breakpoint codes are not crashes.
        const DWORD code = rec->ExceptionCode;
        if (code != EXCEPTION_ACCESS_VIOLATION && code != EXCEPTION_ILLEGAL_INSTRUCTION &&
            code != EXCEPTION_STACK_OVERFLOW && code != EXCEPTION_INT_DIVIDE_BY_ZERO &&
            code != EXCEPTION_IN_PAGE_ERROR && code != EXCEPTION_PRIV_INSTRUCTION)
            return EXCEPTION_CONTINUE_SEARCH;
        static int reported = 0;
        if (reported++ > 2)
            return EXCEPTION_CONTINUE_SEARCH;
        const auto base = reinterpret_cast<uintptr_t>(GetModuleHandleA(nullptr));
        const auto addr = reinterpret_cast<uintptr_t>(rec->ExceptionAddress);
        std::ostringstream o;
        o << "[crash] code=0x" << std::hex << rec->ExceptionCode << " host=0x" << addr
          << " module+0x" << (addr >= base ? addr - base : 0);
        if (rec->ExceptionCode == EXCEPTION_ACCESS_VIOLATION && rec->NumberParameters >= 2)
            o << " access=" << (rec->ExceptionInformation[0] ? "write" : "read") << " at 0x" << rec->ExceptionInformation[1];
        o << std::dec << std::endl;
        void *frames[48];
        const USHORT n = RtlCaptureStackBackTrace(0, 48, frames, nullptr);
        o << "[crash] backtrace (module-relative):";
        for (USHORT i = 0; i < n; ++i)
        {
            const auto f = reinterpret_cast<uintptr_t>(frames[i]);
            o << " " << std::hex << (f >= base ? f - base : f) << std::dec;
        }
        o << std::endl;
        if (g_runtimeForCrash)
        {
            const R5900Context *c = &g_runtimeForCrash->cpu();
            o << "[crash] guest live pc=0x" << std::hex << c->pc << " ra=0x" << GPR_U32(c, 31) << std::dec;
            const EeKernelSnapshot snap = g_runtimeForCrash->eeScheduler().snapshot();
            o << " running=" << snap.runningThreadId << " threads:";
            for (const auto &t : snap.threads)
                o << " [" << t.id << " pc=0x" << std::hex << t.pc << " ra=0x" << t.ra << std::dec << " st=" << static_cast<int>(t.status) << "]";
            o << std::endl;
        }
        std::cerr << o.str() << std::flush;
        std::cout << o.str() << std::flush;
        return EXCEPTION_CONTINUE_SEARCH;
    }
#elif defined(__linux__)
    // Sprint 8 Goal 1 design item 3, the Linux half of the reporter above: sigaction for SIGSEGV,
    // SIGBUS, SIGILL and SIGFPE on an alternate stack (a stack overflow faults with no usable stack
    // left), printing the same line shape the vectored handler prints -- the fault code and its
    // name, the faulting host address and that address relative to the module base (dladdr on the
    // instruction pointer instead of GetModuleHandleA), the module-relative backtrace, then the
    // guest pc/ra and thread table out of the same globals -- after which the default action is
    // restored and the signal re-raised, so the process still dies the way it would have.
    //
    // This runs in a signal handler, so it formats with snprintf into a stack buffer and writes
    // with write(2) rather than through ostringstream/std::cout (the iostreams above are safe on
    // Windows only because a vectored handler is not a signal handler).
    const char *crashSignalName(int sig)
    {
        switch (sig)
        {
        case SIGSEGV: return "SIGSEGV";
        case SIGBUS: return "SIGBUS";
        case SIGILL: return "SIGILL";
        case SIGFPE: return "SIGFPE";
        default: return "SIG?";
        }
    }

    // stderr and stdout both, as the Windows handler prints to both.
    void crashWrite(const char *text, int n)
    {
        if (n <= 0)
            return;
        for (int fd : {STDERR_FILENO, STDOUT_FILENO})
        {
            int off = 0;
            while (off < n)
            {
                const ssize_t w = ::write(fd, text + off, static_cast<size_t>(n - off));
                if (w <= 0)
                    break;
                off += static_cast<int>(w);
            }
        }
    }

    [[noreturn]] void crashReraise(int sig)
    {
        struct sigaction sa;
        std::memset(&sa, 0, sizeof(sa));
        sa.sa_handler = SIG_DFL;
        sigemptyset(&sa.sa_mask);
        ::sigaction(sig, &sa, nullptr);
        // The signal is blocked while its own handler runs: unblock it so the re-raise is taken.
        sigset_t unblock;
        sigemptyset(&unblock);
        sigaddset(&unblock, sig);
        ::pthread_sigmask(SIG_UNBLOCK, &unblock, nullptr);
        ::raise(sig);
        ::_exit(128 + sig);
    }

    void crashHandler(int sig, siginfo_t *info, void *ucontext)
    {
        static std::atomic<int> reported{0};
        if (reported.fetch_add(1, std::memory_order_relaxed) > 2)
            crashReraise(sig);
        uintptr_t ip = 0;
#if defined(__x86_64__)
        if (ucontext)
            ip = static_cast<uintptr_t>(reinterpret_cast<const ucontext_t *>(ucontext)->uc_mcontext.gregs[REG_RIP]);
#endif
        uintptr_t base = 0;
        Dl_info dli;
        if (ip && ::dladdr(reinterpret_cast<void *>(ip), &dli) && dli.dli_fbase)
            base = reinterpret_cast<uintptr_t>(dli.dli_fbase);
        char buf[4096];
        int n = std::snprintf(buf, sizeof(buf), "[crash] code=0x%x (%s) host=0x%llx module+0x%llx",
                              static_cast<unsigned>(sig), crashSignalName(sig),
                              static_cast<unsigned long long>(ip),
                              static_cast<unsigned long long>(ip >= base ? ip - base : 0));
        if ((sig == SIGSEGV || sig == SIGBUS) && info)
        {
            bool isWrite = false;
#if defined(__x86_64__)
            // The page-fault error code the kernel leaves in the context: bit 1 is write.
            if (ucontext)
                isWrite = (reinterpret_cast<const ucontext_t *>(ucontext)->uc_mcontext.gregs[REG_ERR] & 2) != 0;
#endif
            n += std::snprintf(buf + n, sizeof(buf) - n, " access=%s at 0x%llx", isWrite ? "write" : "read",
                               static_cast<unsigned long long>(reinterpret_cast<uintptr_t>(info->si_addr)));
        }
        n += std::snprintf(buf + n, sizeof(buf) - n, "\n[crash] backtrace (module-relative):");
        void *frames[48];
        const int frameCount = ::backtrace(frames, 48);
        for (int i = 0; i < frameCount && n < static_cast<int>(sizeof(buf)) - 64; ++i)
        {
            const uintptr_t f = reinterpret_cast<uintptr_t>(frames[i]);
            n += std::snprintf(buf + n, sizeof(buf) - n, " %llx",
                               static_cast<unsigned long long>(f >= base ? f - base : f));
        }
        n += std::snprintf(buf + n, sizeof(buf) - n, "\n");
        crashWrite(buf, n);
        if (g_runtimeForCrash)
        {
            const R5900Context *c = &g_runtimeForCrash->cpu();
            n = std::snprintf(buf, sizeof(buf), "[crash] guest live pc=0x%x ra=0x%x",
                              static_cast<unsigned>(c->pc), static_cast<unsigned>(GPR_U32(c, 31)));
            // F2: NOT snapshot(). That takes m_snapshotMutex and returns three std::vectors --
            // three mallocs -- and a fault taken while publishSnapshot() holds that mutex, or
            // inside the allocator, would deadlock this handler and hang the process instead of
            // printing the report. crashThreadTable() is a preallocated POD double buffer read
            // with one acquire load: no lock, no allocation, nothing to deadlock on.
            const EeCrashThreadTable &table = g_runtimeForCrash->eeScheduler().crashThreadTable();
            n += std::snprintf(buf + n, sizeof(buf) - n, " running=%d seq=%llu threads:",
                               static_cast<int>(table.runningThreadId),
                               static_cast<unsigned long long>(table.sequence));
            const uint32_t count = table.count <= kEeCrashThreadMax
                                       ? table.count
                                       : static_cast<uint32_t>(kEeCrashThreadMax);
            if (count == 0)
                n += std::snprintf(buf + n, sizeof(buf) - n, " unavailable (never published)");
            for (uint32_t i = 0; i < count; ++i)
            {
                if (n >= static_cast<int>(sizeof(buf)) - 96)
                    break;
                const EeCrashThread &t = table.threads[i];
                n += std::snprintf(buf + n, sizeof(buf) - n, " [%d pc=0x%x ra=0x%x sp=0x%x st=%d prio=%d wait=%d]",
                                   static_cast<int>(t.id), static_cast<unsigned>(t.pc),
                                   static_cast<unsigned>(t.ra), static_cast<unsigned>(t.sp),
                                   static_cast<int>(t.state), static_cast<int>(t.prio),
                                   static_cast<int>(t.wait));
            }
            n += std::snprintf(buf + n, sizeof(buf) - n, "\n");
            crashWrite(buf, n);
        }
        crashReraise(sig);
    }

    void installPosixCrashHandler()
    {
        // 64 KB alternate stack, allocated once and never freed: the handler must have a stack even
        // when the fault IS the stack.
        static bool installed = false;
        if (installed)
            return;
        installed = true;
        static std::vector<char> altStack(64u * 1024u);
        stack_t ss;
        std::memset(&ss, 0, sizeof(ss));
        ss.ss_sp = altStack.data();
        ss.ss_size = altStack.size();
        ss.ss_flags = 0;
        if (::sigaltstack(&ss, nullptr) != 0)
            std::cerr << "[crash] sigaltstack failed: " << errno << std::endl;
        // F3: the first ::backtrace() in a process makes libgcc load and allocate its unwinder.
        // Doing that INSIDE the SIGSEGV handler is a malloc on a possibly-corrupt heap, so it is
        // done here instead -- the same pre-warm the SIGPROF sampler does before arming its timers.
        {
            void *warm[4];
            (void)::backtrace(warm, 4);
        }
        struct sigaction sa;
        std::memset(&sa, 0, sizeof(sa));
        sa.sa_sigaction = crashHandler;
        sa.sa_flags = SA_SIGINFO | SA_ONSTACK | SA_RESTART;
        sigemptyset(&sa.sa_mask);
        for (int sig : {SIGSEGV, SIGBUS, SIGILL, SIGFPE})
            ::sigaction(sig, &sa, nullptr);
    }
#endif


    // ------------------------------------------------------------------------------------------
    // PS2X_CALL_TRACE="0xADDR[:name][,0xADDR[:name]...]": log every call of the listed guest
    // functions (time, name, a0-a3, ra, and any argument that points at printable text). Works
    // through the dense function table, so direct JALs are caught too. First 300 calls per
    // function, then every 500th.
    // ------------------------------------------------------------------------------------------
    struct CallTraceSlot
    {
        uint32_t addr = 0;
        std::string name;
        PS2Runtime::RecompiledFunction original = nullptr;
        uint32_t count = 0;
    };
    constexpr int kCallTraceSlots = 320;
    CallTraceSlot g_callTrace[kCallTraceSlots];
    int g_callTraceCount = 0;
    std::chrono::steady_clock::time_point g_callTraceStart;

    std::string callTraceGuestString(const uint8_t *rdram, uint32_t addr)
    {
        if (addr < 0x100000u || addr >= PS2_RAM_SIZE - 64u)
            return {};
        const uint8_t *p = getConstMemPtr(rdram, addr);
        if (!p)
            return {};
        std::string s;
        for (int i = 0; i < 48 && p[i]; ++i)
        {
            if (p[i] < 0x20 || p[i] > 0x7e)
                return {};
            s.push_back(static_cast<char>(p[i]));
        }
        return s.size() >= 3 ? s : std::string{};
    }

    bool callTraceShouldLog(uint32_t n)
    {
        // PS2X_CALL_TRACE_EVERY=<k>: after the first 300 calls log every k-th (default 500; 1 = all).
        static const uint32_t s_every = [] {
            const char *e = ps2x::knob("PS2X_CALL_TRACE_EVERY");
            const uint32_t v = e ? static_cast<uint32_t>(std::strtoul(e, nullptr, 0)) : 500u;
            return v == 0u ? 500u : v;
        }();
        return n < 300u || (n % s_every) == 0u;
    }

    void callTraceLog(int slot, const uint8_t *rdram, const R5900Context *ctx)
    {
        CallTraceSlot &t = g_callTrace[slot];
        const uint32_t n = t.count++;
        if (!callTraceShouldLog(n))
            return;
        const double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - g_callTraceStart).count();
        std::ostringstream o;
        o << "[call] " << std::fixed << std::setprecision(1) << (ms / 1000.0) << "s " << t.name << " #" << n << std::hex;
        for (int r = 4; r <= 7; ++r)
            o << " a" << (r - 4) << "=0x" << GPR_U32(ctx, r);
        o << " ra=0x" << GPR_U32(ctx, 31) << std::dec;
        {
            float f12 = 0.0f, f13 = 0.0f, f14 = 0.0f;
            std::memcpy(&f12, &ctx->f[12], sizeof(f12));
            std::memcpy(&f13, &ctx->f[13], sizeof(f13));
            std::memcpy(&f14, &ctx->f[14], sizeof(f14));
            o << " f12=" << f12 << " f13=" << f13 << " f14=" << f14;
        }
        for (int r = 4; r <= 6; ++r)
        {
            const std::string s = callTraceGuestString(rdram, GPR_U32(ctx, r));
            if (!s.empty())
                o << " a" << (r - 4) << "=\"" << s << "\"";
        }
        std::cout << o.str() << std::endl;
    }

    template <int N>
    void callTraceThunk(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint32_t n = g_callTrace[N].count;
        callTraceLog(N, rdram, ctx);
        if (!g_dumpAtName.empty() && n == g_dumpAtCount && g_callTrace[N].name == g_dumpAtName)
            writeRdramDump(rdram, g_dumpAtPath, g_dumpAtName + "#" + std::to_string(n));
        // Callee-saved registers at entry (s0-s7, gp, sp, fp) and the return address: on a real
        // return (pc == ra) any difference means the callee, or something it called, clobbered them.
        uint32_t savedRegs[11];
        for (int r = 16; r <= 23; ++r)
            savedRegs[r - 16] = GPR_U32(ctx, r);
        savedRegs[8] = GPR_U32(ctx, 28);
        savedRegs[9] = GPR_U32(ctx, 29);
        savedRegs[10] = GPR_U32(ctx, 30);
        const uint32_t entryRa = GPR_U32(ctx, 31);
        uint32_t entryArgs[4];
        for (int r = 4; r <= 7; ++r)
            entryArgs[r - 4] = GPR_U32(ctx, r);
        g_callTrace[N].original(rdram, ctx, runtime);
        if (ctx->pc == entryRa)
        {
            for (int i = 0; i < 11; ++i)
            {
                const int r = i < 8 ? 16 + i : (i == 8 ? 28 : (i == 9 ? 29 : 30));
                const uint32_t now = GPR_U32(ctx, r);
                if (now != savedRegs[i])
                    std::cout << "[ret-clobber] " << g_callTrace[N].name << " #" << n << " r" << r << " (s" << i
                              << ") was 0x" << std::hex << savedRegs[i] << " now 0x" << now << " ra=0x" << entryRa
                              << std::dec << std::endl;
            }
        }
        else
        {
            std::cout << "[ret-unwound] " << g_callTrace[N].name << " #" << n << " pc=0x" << std::hex << ctx->pc
                      << " ra=0x" << entryRa << std::dec << std::endl;
        }
        // The generated function returned normally: report v0 (and f0 for float returns).
        if (callTraceShouldLog(n))
        {
            float f0 = 0.0f;
            std::memcpy(&f0, &ctx->f[0], sizeof(f0));
            std::cout << "[ret] " << g_callTrace[N].name << " #" << n << " v0=0x" << std::hex << GPR_U32(ctx, 2) << std::dec << " f0=" << f0 << std::endl;
            // PS2X_CALL_TRACE_DUMP="<Name>:a<k>[+0xOFF][*[+0xOFF]]:<words>[,...]": after the traced
            // function returns, follow the chain from the entry value of argument k and print
            // <words> guest words (hex + float) — e.g. the collision query object's ray and hit
            // records for every GroundQuery call ("GroundQuery:a1:20,GroundQuery:a1+0x48*:16").
            static const char *const dumpSpec = ps2x::knob("PS2X_CALL_TRACE_DUMP");
            if (dumpSpec && *dumpSpec)
            {
                std::string spec(dumpSpec);
                size_t p = 0;
                while (p < spec.size())
                {
                    size_t e = spec.find(',', p);
                    if (e == std::string::npos)
                        e = spec.size();
                    const std::string item = spec.substr(p, e - p);
                    p = e + 1;
                    const size_t c1 = item.find(':');
                    const size_t c2 = item.rfind(':');
                    if (c1 == std::string::npos || c2 == c1 || item.substr(0, c1) != g_callTrace[N].name)
                        continue;
                    const std::string chain = item.substr(c1 + 1, c2 - c1 - 1);
                    const uint32_t words = static_cast<uint32_t>(std::strtoul(item.c_str() + c2 + 1, nullptr, 0));
                    if (chain.size() < 2 || chain[0] != 'a')
                        continue;
                    const int k = chain[1] - '0';
                    if (k < 0 || k > 3)
                        continue;
                    uint32_t addr = entryArgs[k];
                    size_t i = 2;
                    bool ok = true;
                    while (i < chain.size() && ok)
                    {
                        if (chain[i] == '*')
                        {
                            if ((addr & 0x1FFFFFF) + 4 > PS2_RAM_SIZE)
                            {
                                ok = false;
                                break;
                            }
                            std::memcpy(&addr, rdram + (addr & 0x1FFFFFF), 4);
                            ++i;
                        }
                        else if (chain[i] == '+')
                        {
                            char *endp = nullptr;
                            addr += static_cast<uint32_t>(std::strtoul(chain.c_str() + i + 1, &endp, 0));
                            i = static_cast<size_t>(endp - chain.c_str());
                        }
                        else
                            ok = false;
                    }
                    if (!ok || addr == 0 || (addr & 0x1FFFFFF) + words * 4 > PS2_RAM_SIZE)
                        continue;
                    std::ostringstream o;
                    o << "[ret-dump] " << g_callTrace[N].name << " #" << n << " @" << std::hex << (addr & 0x1FFFFFF) << ":";
                    for (uint32_t w = 0; w < words; ++w)
                    {
                        uint32_t v = 0;
                        float fv = 0.0f;
                        std::memcpy(&v, rdram + ((addr & 0x1FFFFFF) + w * 4), 4);
                        std::memcpy(&fv, &v, 4);
                        o << " " << std::hex << std::setw(8) << std::setfill('0') << v << "(" << std::dec << fv << ")";
                    }
                    std::cout << o.str() << std::endl;
                }
            }
        }
    }

    template <int... Is>
    constexpr std::array<PS2Runtime::RecompiledFunction, sizeof...(Is)> makeCallTraceThunks(std::integer_sequence<int, Is...>)
    {
        return {{&callTraceThunk<Is>...}};
    }

    void installCallTrace(PS2Runtime &runtime)
    {
        const char *env = ps2x::knob("PS2X_CALL_TRACE");
        if (!env || !*env)
            return;
        static const auto thunks = makeCallTraceThunks(std::make_integer_sequence<int, kCallTraceSlots>{});
        g_callTraceStart = std::chrono::steady_clock::now();
        std::string spec(env);
        size_t pos = 0;
        while (pos < spec.size() && g_callTraceCount < kCallTraceSlots)
        {
            size_t end = spec.find(',', pos);
            if (end == std::string::npos)
                end = spec.size();
            std::string item = spec.substr(pos, end - pos);
            pos = end + 1;
            if (item.empty())
                continue;
            std::string name;
            const size_t colon = item.find(':');
            if (colon != std::string::npos)
            {
                name = item.substr(colon + 1);
                item = item.substr(0, colon);
            }
            const uint32_t addr = static_cast<uint32_t>(std::strtoul(item.c_str(), nullptr, 0));
            if (!runtime.hasFunction(addr))
            {
                std::cout << "[call-trace] no function at 0x" << std::hex << addr << std::dec << std::endl;
                continue;
            }
            CallTraceSlot &t = g_callTrace[g_callTraceCount];
            t.addr = addr;
            t.original = runtime.lookupFunction(addr);
            if (name.empty())
            {
                std::ostringstream o;
                o << "FUN_" << std::hex << std::setw(8) << std::setfill('0') << addr;
                name = o.str();
            }
            t.name = name;
            if (runtime.replaceFunction(addr, thunks[static_cast<size_t>(g_callTraceCount)]))
                ++g_callTraceCount;
        }
        std::cout << "[call-trace] tracing " << g_callTraceCount << " guest functions" << std::endl;
    }

    // ------------------------------------------------------------------------------------------
    // PS2X_SOCOM2_MUSIC_TRACE=1 (research/36 item 8, 2026-09-20): the EE's music manager, traced. The driven
    // mission plays 10-22 s of digital silence between stems where the console plays on; the IOP-side trace
    // shows the manager idle with an EMPTY cue queue (no play refused, no handle left pending). This says why:
    // every state change of FUN_0034afd0 (manager+9: 4 reset, 3 idle, 1 playing, 0/2 extension) with its cue
    // entry (+0x34), and every FUN_0034b6c0 cue push with its arguments and whether the IRX-side decision
    // (runtime/socom2_music_trace.h) queued, refused or dropped it. Both run the original afterwards; both are
    // stamped with the mixer's output-frame clock, the one the [audio] events carry.
    // ------------------------------------------------------------------------------------------
    PS2Runtime::RecompiledFunction g_musicMgrOriginal = nullptr;
    PS2Runtime::RecompiledFunction g_musicPushOriginal = nullptr;

    uint32_t musicRead32(const uint8_t *rdram, uint32_t addr)
    {
        uint32_t v = 0u;
        if (const uint8_t *p = getConstMemPtr(rdram, addr))
            std::memcpy(&v, p, sizeof(v));
        return v;
    }

    uint8_t musicRead8(const uint8_t *rdram, uint32_t addr)
    {
        const uint8_t *p = getConstMemPtr(rdram, addr);
        return p ? *p : 0u;
    }

    void socom2_MusicManagerTrace(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        static uint32_t s_calls = 0u;
        const uint32_t mgr = GPR_U32(ctx, 4);
        const uint8_t stateBefore = musicRead8(rdram, mgr + 9u);
        const uint32_t entryBefore = musicRead32(rdram, mgr + 0x34u);
        const uint8_t interrupt = musicRead8(rdram, mgr + 10u);
        g_musicMgrOriginal(rdram, ctx, runtime);
        const uint8_t stateAfter = musicRead8(rdram, mgr + 9u);
        const uint32_t entryAfter = musicRead32(rdram, mgr + 0x34u);
        const uint32_t n = s_calls++;
        if (n == 0u || stateBefore != stateAfter || entryBefore != entryAfter)
        {
            std::fprintf(stderr, "[music] mgr 0x%08x state %u->%u entry 0x%08x->0x%08x interrupt=%u queue=%u free=%u flagB=%u frame=%llu call#%u\n",
                         mgr, stateBefore, stateAfter, entryBefore, entryAfter, interrupt, musicRead32(rdram, mgr + 0x1cu),
                         musicRead32(rdram, mgr + 0x28u), musicRead8(rdram, mgr + 0xbu),
                         static_cast<unsigned long long>(runtime->audioBackend().mixerRenderedFrames()), n);
        }
    }

    void socom2_MusicPushTrace(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint32_t mgr = GPR_U32(ctx, 4), name = GPR_U32(ctx, 5), def = GPR_U32(ctx, 6), vol = GPR_U32(ctx, 7);
        const uint32_t freeBefore = musicRead32(rdram, mgr + 0x28u);
        const uint32_t queueBefore = musicRead32(rdram, mgr + 0x1cu);
        const uint8_t flagB = musicRead8(rdram, mgr + 0xbu);
        const uint8_t f1c = musicRead8(rdram, def + 0x1cu), f1d = musicRead8(rdram, def + 0x1du);
        g_musicPushOriginal(rdram, ctx, runtime);
        const uint32_t ret = GPR_U32(ctx, 2);
        const uint32_t queueAfter = musicRead32(rdram, mgr + 0x1cu);
        const socom2_music::PushVerdict v = socom2_music::pushVerdict(freeBefore, flagB, f1c, f1d, ret, queueBefore, queueAfter);
        const std::string text = callTraceGuestString(rdram, name);
        std::fprintf(stderr, "[music] push name=0x%08x%s%s%s def=0x%08x type=%u flags1c=0x%02x vol=%u -> %s (%s) ret=%u queue %u->%u free %u->%u flagB=%u frame=%llu ra=0x%08x\n",
                     name, text.empty() ? "" : " \"", text.c_str(), text.empty() ? "" : "\"", def, f1d >> 5, f1c, vol, v.label, v.reason, ret,
                     queueBefore, queueAfter, freeBefore, musicRead32(rdram, mgr + 0x28u), flagB,
                     static_cast<unsigned long long>(runtime->audioBackend().mixerRenderedFrames()), GPR_U32(ctx, 31));
    }

    void installMusicTrace(PS2Runtime &runtime)
    {
        if (!ps2x::knob("PS2X_SOCOM2_MUSIC_TRACE"))
            return;
        const uint32_t kManager = socom2_addresses::current().musicManager;   // r0001: FUN_0034afd0, the per-frame music manager
        const uint32_t kPush = socom2_addresses::current().cuePush;           // r0001: FUN_0034b6c0, the cue push
        if (!runtime.hasFunction(kManager) || !runtime.hasFunction(kPush))
        {
            std::cout << "[music] trace: 0x" << std::hex << kManager << " / 0x" << kPush << std::dec
                      << " not in the function table" << std::endl;
            return;
        }
        g_musicMgrOriginal = runtime.lookupFunction(kManager);
        g_musicPushOriginal = runtime.lookupFunction(kPush);
        runtime.replaceFunction(kManager, socom2_MusicManagerTrace);
        runtime.replaceFunction(kPush, socom2_MusicPushTrace);
        std::cout << "[music] tracing FUN_0034afd0 (manager state) and FUN_0034b6c0 (cue push)" << std::endl;
    }

    // ------------------------------------------------------------------------------------------
    // PS2X_SOCOM2_UDP_SHIFT and the guest's OWN port number.
    //
    // A second instance on the same host cannot bind the game's fixed peer UDP ports (3658/3659),
    // so socom2_libnetb::doCreate shifts the host bind. That shift was invisible to the guest:
    // rt_net FUN_00620648 writes the base port 3658 into its config object at +0xC and the client
    // publishes THAT value as the internal address of its DME 0x18 client record -- so instance B
    // advertised 127.0.0.1/192.168.2.10:3658 (A's port) internally while its external slot said
    // :3660. PCSX2's client B carries :3660 in BOTH slots, because its pnach
    // (patch=1,EE,20620678,extended,24040E4C) rewrites the same constant in the guest.
    // This wrapper does what the pnach does: after the original ran, rewrite the base port field.
    // ------------------------------------------------------------------------------------------
    int32_t socom2UdpShift()
    {
        static const int32_t s_shift = [] {
            const char *e = ps2x::knob("PS2X_SOCOM2_UDP_SHIFT");
            return e ? static_cast<int32_t>(std::atoi(e)) : 0;
        }();
        return s_shift;
    }

    PS2Runtime::RecompiledFunction g_rtNetCfgOriginal = nullptr;

    void socom2_RtNetConfigInit(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint32_t obj = GPR_U32(ctx, 4);
        if (g_rtNetCfgOriginal)
            g_rtNetCfgOriginal(rdram, ctx, runtime);
        if (obj == 0)
            return;
        const uint32_t field = (obj + 0xCu) & PS2_RAM_MASK;
        if (field + 4u > PS2_RAM_SIZE)
            return;
        uint32_t port = 0;
        std::memcpy(&port, rdram + field, 4);
        if (port != 3658u)
            return;                                  // not the base-port field we know
        port = static_cast<uint32_t>(3658 + socom2UdpShift());
        std::memcpy(rdram + field, &port, 4);
        static bool s_said = false;
        if (!s_said)
        {
            s_said = true;
            std::cout << "[socom2] rt_net base peer UDP port -> " << port << " (PS2X_SOCOM2_UDP_SHIFT)" << std::endl;
        }
    }

    void installRtNetPortShift(PS2Runtime &runtime)
    {
        if (socom2UdpShift() == 0)
            return;
        const uint32_t kRtNetCfgInit = socom2_addresses::current().rtNetConfigInit;   // r0001: FUN_00620648
        if (!runtime.hasFunction(kRtNetCfgInit))
        {
            std::cout << "[socom2] no function at 0x" << std::hex << kRtNetCfgInit << std::dec
                      << "; peer UDP port shift stays host-side only" << std::endl;
            return;
        }
        g_rtNetCfgOriginal = runtime.lookupFunction(kRtNetCfgInit);
        runtime.replaceFunction(kRtNetCfgInit, socom2_RtNetConfigInit);
    }

    // ------------------------------------------------------------------------------------------
    // Sprint 10 Goal 9 (research/38): the on-screen keyboard opens holding the launcher's persona name and
    // password. The game's login screen opens both keyboards through the UI action "GetTextInput", whose one
    // handler is FUN_0038d770(msg, ctx); the handler passes the keyboard a fixed initial-text buffer at
    // 0x49ec70 that nothing in the game ever writes. This wrapper reads the action's argument block (the
    // Purpose key and the keyboard name say which field it is; MaxChars/MaxBytes say the cap), writes the
    // matching PS2X_SOCOM2_LOGIN_NAME / _PASS string into that buffer -- or zeros, so the next keyboard, a chat
    // line, a game name, opens empty as before -- and lets the original open the keyboard (it lays the text
    // out and puts the cursor after it). NOTHING RUNS AFTER THE ORIGINAL: a recompiled call can leave through
    // an EE scheduler checkpoint and resume later (the third driven login, s10_g9_prefill_diag3: `[ret-unwound]
    // OskActivate pc=0x3766a0`), so code placed after `g_oskOpenOriginal(...)` runs before the game has read the
    // buffer -- the first version blanked it there and every keyboard opened empty. Nothing is submitted
    // (R180): ENTER applies the text to the UI variable exactly as typed text would. With neither variable set
    // the wrapper is never installed.
    // ------------------------------------------------------------------------------------------
    PS2Runtime::RecompiledFunction g_oskOpenOriginal = nullptr;

    void socom2_OskOpenPrefill(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint32_t msgAddr = GPR_U32(ctx, 4) & PS2_RAM_MASK;
        const uint32_t bufAddr = socom2_addresses::current().oskTextBuffer & PS2_RAM_MASK;
        socom2_osk::Request req;
        std::string text;
        if (msgAddr != 0 && msgAddr + socom2_osk::kArgBlockBytes <= PS2_RAM_SIZE)
        {
            req = socom2_osk::readRequest(rdram + msgAddr);
            text = socom2_osk::prefillFor(req.field, ps2x::knob("PS2X_SOCOM2_LOGIN_NAME"), ps2x::knob("PS2X_SOCOM2_LOGIN_PASS"),
                                          socom2_osk::capFor(req.maxChars, req.maxBytes, socom2_osk::kOskTextBufferBytes));
        }
        // The buffer's whole image, before the original and never after it (the header comment): the text for
        // a login field, zeros for any other keyboard, so what the previous open left never shows.
        if (bufAddr + socom2_osk::kOskTextBufferBytes <= PS2_RAM_SIZE)
            socom2_osk::writeBuffer(rdram + bufAddr, socom2_osk::kOskTextBufferBytes, text);
        // One line per keyboard, whatever was decided: the first driven login is research/38's dynamic
        // confirmation (the live purpose, keyboard and caps), and never the text itself.
        std::cout << "[socom2] on-screen keyboard open: purpose=\"" << req.purpose << "\" skb=\"" << req.skbName
                  << "\" MaxChars=" << req.maxChars << " MaxBytes=" << req.maxBytes << " -> "
                  << (text.empty() ? std::string("not prefilled")
                                   : std::string("prefilled: ") + socom2_osk::fieldLabel(req.field) + " (" + std::to_string(text.size()) + " chars)")
                  << std::endl;
        if (g_oskOpenOriginal)
            g_oskOpenOriginal(rdram, ctx, runtime);
        // Nothing here: the original may have unwound through a scheduler checkpoint with the keyboard still
        // to be laid out, and resumes later without passing through this wrapper again.
    }

    void installOskPrefill(PS2Runtime &runtime)
    {
        const char *name = ps2x::knob("PS2X_SOCOM2_LOGIN_NAME");
        const char *pass = ps2x::knob("PS2X_SOCOM2_LOGIN_PASS");
        const bool haveName = name != nullptr && *name != '\0';
        const bool havePass = pass != nullptr && *pass != '\0';
        if (!haveName && !havePass)
            return;
        // All three of the keyboard's addresses are revision-bound and all three come from one place
        // (runtime/socom2_addresses.h): the handler, the thunk the UI action table actually dispatches
        // through, and the initial-text buffer the wrapper writes.
        const socom2_addresses::Table &addr = socom2_addresses::current();
        if (!runtime.hasFunction(addr.oskOpen))
        {
            std::cout << "[socom2] no function at 0x" << std::hex << addr.oskOpen << std::dec
                      << "; the keyboards open empty (PS2X_SOCOM2_LOGIN_NAME/_PASS ignored)" << std::endl;
            return;
        }
        // The original is the handler itself; the wrap sits on the handler AND on the thunk the action table
        // dispatches through (kOskOpenEntries), because the recompiled thunk calls the handler directly and a
        // replacement at the handler alone is never reached (the first two driven logins: armed, 0 of 5 filled).
        g_oskOpenOriginal = runtime.lookupFunction(addr.oskOpen);
        const uint32_t entries[] = {addr.oskOpenThunk, addr.oskOpen};
        int installed = 0;
        for (uint32_t entry : entries)
        {
            if (runtime.hasFunction(entry))
            {
                runtime.replaceFunction(entry, socom2_OskOpenPrefill);
                ++installed;
            }
        }
        std::cout << "[socom2] on-screen keyboard prefill wraps " << installed << " of "
                  << (sizeof(entries) / sizeof(entries[0])) << " entries" << std::endl;
        std::cout << "[socom2] on-screen keyboard prefill armed: persona name " << (haveName ? std::to_string(std::strlen(name)) + " chars" : "unset")
                  << ", password " << (havePass ? std::to_string(std::strlen(pass)) + " chars" : "unset") << std::endl;
    }

    // Sprint 11 milestone S: hardening of the chat receive path. Two fixed-width fields are given the terminator
    // the game's readers assume, BEFORE the original runs and never after (the OSK wrap's rule above: the original
    // may unwind through a scheduler checkpoint, so host code placed after the call runs too late). Nothing
    // further about it is written up here (SECURITY.md).
    // Both wraps below keep the same books and obey the same rate limit, so they keep them in one place: one
    // instance per wrap, and a change to how either is logged is a change in one function.
    //   seen    every call the wrap was entered on
    //   fixed   the calls that changed something
    //   skipped what the wrap declined to touch on that call (nothing it declines is ever passed over silently)
    struct BoundWrapLog
    {
        std::atomic<uint32_t> seen{0}, fixed{0}, skipped{0};
        std::atomic<bool> saidDeclined{false};

        // The first call always says so; after that only the calls that changed something, and of those the
        // first 8 and then every 64th -- a busy room must not turn the log into this one line.
        void note(const char *tag, int changed, uint32_t skips)
        {
            const uint32_t n = seen.fetch_add(1) + 1;
            const uint32_t f = changed ? fixed.fetch_add(1) + 1 : fixed.load();
            // The running total stops at the top rather than coming round to a small number (socom2_chat::satAdd).
            uint32_t s = skipped.load();
            while (skips != 0)
            {
                const uint32_t next = socom2_chat::satAdd(s, skips);
                if (skipped.compare_exchange_weak(s, next))
                {
                    s = next;
                    break;
                }
            }
            if (n == 1 || (changed != 0 && (f <= 8 || f % 64 == 0)))
                std::cout << "[socom2] " << tag << ": seen=" << n << " fixed=" << f << " skipped=" << s << std::endl;
        }

        // Once, so that "the wrap ran and declined what it was given" is distinguishable from "the wrap was
        // never entered" when a run's log is read back.
        void declinedOnce(const char *tag, const char *what)
        {
            if (!saidDeclined.exchange(true))
                std::cerr << "[socom2] " << tag << ": " << what << " (reported once)" << std::endl;
        }
    };

    PS2Runtime::RecompiledFunction g_chatFanoutOriginal = nullptr;
    // Written from whatever guest thread runs the callback; only the log line reads them.
    BoundWrapLog g_chatFanoutLog;

    void socom2_ChatFanoutBound(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        // The mask is the OSK wrap's precedent (it indexes rdram the same way); getMemPtr is not a one-line swap here.
        const uint32_t pkt = GPR_U32(ctx, 7) & PS2_RAM_MASK;      // $a3
        int changed = 0;
        uint32_t skipped = 0;
        if (pkt != 0 && pkt + socom2_chat::kPacketBytes <= PS2_RAM_SIZE)
        {
            changed = socom2_chat::terminateFields(rdram + pkt);
        }
        else
        {
            skipped = 1;
            g_chatFanoutLog.declinedOnce("chat receive bound", "the packet does not fit in memory; skipped");
        }
        g_chatFanoutLog.note("chat receive bound", changed, skipped);
        if (g_chatFanoutOriginal)
            g_chatFanoutOriginal(rdram, ctx, runtime);
        // Nothing here: the original may leave through a scheduler checkpoint and resume later.
    }

    // Sprint 11 Task 2b: the same two fields, at the second reader of the same records. That reader is handed a
    // run of them rather than one, so each record in the run is given the guarantee before the original walks it,
    // by the rule above (before, never after). Nothing read out of guest memory is trusted: a run is walked only
    // when socom2_chat::spanFits says it is whole and inside RAM.
    PS2Runtime::RecompiledFunction g_chatListOriginal = nullptr;
    // Written from whatever guest thread runs the reader; only the log line reads them.
    BoundWrapLog g_chatListLog;

    void socom2_ChatListBound(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const socom2_addresses::Table &addr = socom2_addresses::current();
        const uint32_t holders = Ps2FastRead32(rdram, addr.chatListHolders + socom2_chat::kHolderCountOff);
        const uint32_t holderBase = Ps2FastRead32(rdram, addr.chatListHolders + socom2_chat::kHolderDataOff) & PS2_RAM_MASK;
        // The ceiling cuts the walk, it never calls it off: a list longer than the ceiling still gets the
        // guarantee as far as the ceiling reaches. Not fitting in memory is the one thing that declines a walk,
        // and having nothing to walk is not that: an empty list returns quietly, saying nothing.
        const uint32_t walkHolders = socom2_chat::walkCount(holders, socom2_chat::kMaxHolders);
        uint32_t budget = socom2_chat::kRecordsPerCall;   // spent across this call, carried to no other
        int changed = 0;
        uint32_t skipped = holders - walkHolders;
        if (socom2_chat::declines(walkHolders, holderBase, socom2_chat::kHolderPtrBytes, PS2_RAM_SIZE))
        {
            skipped = socom2_chat::satAdd(skipped, walkHolders);
            g_chatListLog.declinedOnce("chat list bound", "the holder list does not fit in memory; skipped");
        }
        else
        {
            // Every holder in the list, not only the one this reader selects: the selection is a name match
            // the guest makes for itself, and walking the whole list covers it without repeating that match
            // here -- including a holder another reader reaches.
            for (uint32_t i = 0; i < walkHolders; ++i)
            {
                const uint32_t holder = Ps2FastRead32(rdram, holderBase + i * socom2_chat::kHolderPtrBytes) & PS2_RAM_MASK;
                if (!socom2_chat::spanFits(holder, 1, socom2_chat::kListHeaderBytes, PS2_RAM_SIZE))
                {
                    skipped = socom2_chat::satAdd(skipped, 1);
                    continue;
                }
                const uint32_t count = Ps2FastRead32(rdram, holder + socom2_chat::kListCountOff);
                const uint32_t base = Ps2FastRead32(rdram, holder + socom2_chat::kListDataOff) & PS2_RAM_MASK;
                // Once the call's budget is gone every remaining walk is nothing; the rest of the loop only
                // finishes the count of what was left alone, which is a handful of reads per holder.
                const uint32_t walk = socom2_chat::walkWithin(count, socom2_chat::kMaxRecords, budget);
                budget -= walk;
                skipped = socom2_chat::satAdd(skipped, count - walk);
                if (socom2_chat::declines(walk, base, socom2_chat::kRecordBytes, PS2_RAM_SIZE))
                {
                    skipped = socom2_chat::satAdd(skipped, walk);
                    continue;
                }
                changed += socom2_chat::terminateRecords(rdram + base, walk);
            }
        }
        g_chatListLog.note("chat list bound", changed, skipped);
        if (g_chatListOriginal)
            g_chatListOriginal(rdram, ctx, runtime);
        // Nothing here: the original may leave through a scheduler checkpoint and resume later.
    }

    void installChatBound(PS2Runtime &runtime)
    {
        // Both addresses come from the revision table, which is the only place either is written down.
        const uint32_t fanoutRecv = socom2_addresses::current().chatFanoutRecv;
        if (!runtime.hasFunction(fanoutRecv))
        {
            std::cout << "[socom2] no function at 0x" << std::hex << fanoutRecv << std::dec << "; chat receive not bound" << std::endl;
        }
        else
        {
            g_chatFanoutOriginal = runtime.lookupFunction(fanoutRecv);
            runtime.replaceFunction(fanoutRecv, socom2_ChatFanoutBound);
            std::cout << "[socom2] chat receive bound (name 32, message 64)" << std::endl;
        }
        // The two wraps are independent: one missing from the loaded image must not take the other with it.
        const uint32_t listRender = socom2_addresses::current().chatListRender;
        if (!runtime.hasFunction(listRender))
        {
            std::cout << "[socom2] no function at 0x" << std::hex << listRender << std::dec << "; chat list not bound" << std::endl;
            return;
        }
        g_chatListOriginal = runtime.lookupFunction(listRender);
        runtime.replaceFunction(listRender, socom2_ChatListBound);
        std::cout << "[socom2] chat list bound (name 32, message 64)" << std::endl;
    }

    // ------------------------------------------------------------------------------------------
    // PS2X_CULL_TRACE="<file>:t<seconds>[:<count>]" -- research/31 section 16. From <seconds> after start,
    // log the next <count> (default 4000) calls of the object box-frustum cull FUN_00290c30(camera,
    // corners[8], flagsOut, occlusion): the eight world-space corners, the camera's 4x4 (camera + 0x330)
    // and plane mask (camera + 0x564), the guest's result (v0: 2 culled, 1 visible, 0 partial) and mask,
    // and the same judgement recomputed in IEEE arithmetic (socom2_cull::boxClipMasks), one line per call.
    PS2Runtime::RecompiledFunction g_cullOriginal = nullptr;
    std::FILE *g_cullTraceFile = nullptr;
    double g_cullTraceAfter = 0.0;
    int g_cullTraceLeft = 0;
    std::chrono::steady_clock::time_point g_cullTraceStart;

    void socom2_CullTrace(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint32_t camera = GPR_U32(ctx, 4);
        const uint32_t cornersAddr = GPR_U32(ctx, 5);
        const uint32_t flagsAddr = GPR_U32(ctx, 6);
        const uint32_t occl = GPR_U32(ctx, 7);
        float corners[8][4] = {};
        float m[16] = {};
        uint32_t planeMask = 0;
        float lodScale[2] = {0.0f, 0.0f};
        static const float s_forceLod = ps2x::knob("PS2X_LOD_SCALE") ? static_cast<float>(std::atof(ps2x::knob("PS2X_LOD_SCALE"))) : 0.0f;
        if (s_forceLod > 0.0f)
        {
            if (uint8_t *pw = rdram + (camera & PS2_RAM_MASK) + 0x2c8u; camera != 0)
            {
                std::memcpy(pw, &s_forceLod, 4);
                std::memcpy(pw + 4, &s_forceLod, 4);
            }
        }
        if (const uint8_t *pl = getConstMemPtr(rdram, camera + 0x2c8u))
            std::memcpy(lodScale, pl, sizeof(lodScale));
        const uint8_t *pc = getConstMemPtr(rdram, cornersAddr);
        const uint8_t *pm = getConstMemPtr(rdram, camera + 0x330u);
        const uint8_t *pk = getConstMemPtr(rdram, camera + 0x564u);
        if (pc) std::memcpy(corners, pc, sizeof(corners));
        if (pm) std::memcpy(m, pm, sizeof(m));
        if (pk) std::memcpy(&planeMask, pk, sizeof(planeMask));
        g_cullOriginal(rdram, ctx, runtime);
        // PS2X_CULL_PARTIAL_CLIP=1 (experiment, research/31 section 16): a box the frustum test marks partial
        // (OR mask nonzero) that the guest then judged 'inside the guard band' (result 1) is answered 0, the
        // 'needs clipping' verdict the hardware's flag latency gives FUN_00294a30 -- the clipped VU1 family.
        {
            static const bool s_partialClip = ps2x::knob("PS2X_CULL_PARTIAL_CLIP") && std::atoi(ps2x::knob("PS2X_CULL_PARTIAL_CLIP")) != 0;
            if (s_partialClip && GPR_U32(ctx, 2) == 1u)
            {
                uint32_t andMaskX = 0, orMaskX = 0;
                socom2_cull::boxClipMasks(m, corners, andMaskX, orMaskX);
                if ((orMaskX & planeMask & 0x3Fu) != 0u)
                    SET_GPR_U32(ctx, 2, 0u);
            }
        }
        const double sec = std::chrono::duration<double>(std::chrono::steady_clock::now() - g_cullTraceStart).count();
        if (!g_cullTraceFile || g_cullTraceLeft <= 0 || sec < g_cullTraceAfter)
            return;
        --g_cullTraceLeft;
        uint32_t guestMask = 0;
        if (const uint8_t *pf = (flagsAddr ? getConstMemPtr(rdram, flagsAddr) : nullptr))
            std::memcpy(&guestMask, pf, sizeof(guestMask));
        uint32_t andMask = 0, orMask = 0;
        socom2_cull::boxClipMasks(m, corners, andMask, orMask);
        float lo[3] = {corners[0][0], corners[0][1], corners[0][2]}, hi[3] = {corners[0][0], corners[0][1], corners[0][2]};
        for (int i = 1; i < 8; ++i)
            for (int a = 0; a < 3; ++a)
            {
                lo[a] = corners[i][a] < lo[a] ? corners[i][a] : lo[a];
                hi[a] = corners[i][a] > hi[a] ? corners[i][a] : hi[a];
            }
        std::fprintf(g_cullTraceFile,
                     "t=%.3f cam=%08x occl=%u result=%u guestMask=%06x planeMask=%06x ieee=%06x lod=%g/%g box=(%.1f,%.1f,%.1f)-(%.1f,%.1f,%.1f)",
                     sec, camera, occl, GPR_U32(ctx, 2), guestMask, planeMask, socom2_cull::packResult(andMask, orMask), lodScale[0], lodScale[1],
                     lo[0], lo[1], lo[2], hi[0], hi[1], hi[2]);
        std::fprintf(g_cullTraceFile, " m=");
        for (int i = 0; i < 16; ++i)
            std::fprintf(g_cullTraceFile, "%s%.6g", i ? "," : "", m[i]);
        std::fprintf(g_cullTraceFile, " corners=");
        for (int i = 0; i < 8; ++i)
            std::fprintf(g_cullTraceFile, "%s(%.1f,%.1f,%.1f,%.3g)", i ? ";" : "", corners[i][0], corners[i][1], corners[i][2], corners[i][3]);
        std::fprintf(g_cullTraceFile, "\n");
        if (g_cullTraceLeft == 0)
            std::fflush(g_cullTraceFile);
    }

    // The scene-node traversal FUN_00338480(scene, node, parentComponent, ?, cullResult) that decides whether a
    // node reaches the box cull at all: logged on the same file, one "node=" line per entry with the fields its
    // gates read (node + 0x5c flags, + 0x5d, + 0x9c the fade/scale float, + 0x88 component presence).
    PS2Runtime::RecompiledFunction g_nodeOriginal = nullptr;
    PS2Runtime::RecompiledFunction g_nodeOriginal2 = nullptr;

    void nodeTraceLine(const char *which, uint8_t *rdram, R5900Context *ctx);

    void nodeTraceLine(const char *which, uint8_t *rdram, R5900Context *ctx)
    {
        const double sec = std::chrono::duration<double>(std::chrono::steady_clock::now() - g_cullTraceStart).count();
        if (g_cullTraceFile && g_cullTraceLeft > 0 && sec >= g_cullTraceAfter)
        {
            const uint32_t node = GPR_U32(ctx, 5);
            const uint8_t *pn = getConstMemPtr(rdram, node);
            uint32_t f5c = 0, c88 = 0, c8c = 0; float f9c = 0.0f; uint8_t a1 = 0;
            if (pn)
            {
                std::memcpy(&f5c, pn + 0x5c, 4);
                std::memcpy(&f9c, pn + 0x9c, 4);
                std::memcpy(&c88, pn + 0x88, 4);
                std::memcpy(&c8c, pn + 0x8c, 4);
                a1 = pn[0xa1];
            }
            uint32_t comp = 0; uint8_t compKind = 0;
            if (c88 && c8c)
            {
                const uint8_t *pp = getConstMemPtr(rdram, c8c);
                if (pp) std::memcpy(&comp, pp, 4);
                const uint8_t *pc = comp ? getConstMemPtr(rdram, comp) : nullptr;
                if (pc) compKind = pc[4];
            }
            std::fprintf(g_cullTraceFile, "node t=%.3f via=%s obj=%08x f5c=%08x f9c=%g c88=%08x comp=%08x kind=%u a1=%02x scene=%08x arg2=%08x\n",
                         sec, which, node, f5c, f9c, c88, comp, compKind, a1, GPR_U32(ctx, 4), GPR_U32(ctx, 6));
        }
    }

    void socom2_NodeTrace(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        nodeTraceLine("scene", rdram, ctx);
        g_nodeOriginal(rdram, ctx, runtime);
    }

    void socom2_NodeTrace2(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        nodeTraceLine("world", rdram, ctx);
        g_nodeOriginal2(rdram, ctx, runtime);
    }

    // The per-component LOD band test FUN_003b7b90(dist, component, lodEntry, &fade) that FUN_003374c0 runs before
    // drawing a component whose LOD group (component + 5) is set: dist is camera+0x2c8 times the squared camera-space
    // distance, the entry is {nearMin, nearFadeEnd, nearSlope, farFadeStart, farMax, farSlope, flags}; 0 = skip.
    PS2Runtime::RecompiledFunction g_lodOriginal = nullptr;

    void socom2_LodTrace(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        float dist = 0.0f;
        std::memcpy(&dist, &ctx->f[12], sizeof(dist));
        const uint32_t comp = GPR_U32(ctx, 4), entry = GPR_U32(ctx, 5), fadeAddr = GPR_U32(ctx, 6);
        float e[7] = {};
        if (const uint8_t *pe = getConstMemPtr(rdram, entry))
            std::memcpy(e, pe, sizeof(e));
        float fadeIn = 0.0f;
        if (const uint8_t *pf = fadeAddr ? getConstMemPtr(rdram, fadeAddr) : nullptr)
            std::memcpy(&fadeIn, pf, sizeof(fadeIn));
        g_lodOriginal(rdram, ctx, runtime);
        const double sec = std::chrono::duration<double>(std::chrono::steady_clock::now() - g_cullTraceStart).count();
        if (!g_cullTraceFile || g_cullTraceLeft <= 0 || sec < g_cullTraceAfter)
            return;
        float fadeOut = 0.0f;
        if (const uint8_t *pf = fadeAddr ? getConstMemPtr(rdram, fadeAddr) : nullptr)
            std::memcpy(&fadeOut, pf, sizeof(fadeOut));
        uint32_t flags = 0;
        std::memcpy(&flags, &e[6], sizeof(flags));
        std::fprintf(g_cullTraceFile, "lod t=%.3f comp=%08x dist=%g entry=%08x near=%g/%g/%g far=%g/%g/%g flags=%08x fade=%g->%g result=%u\n",
                     sec, comp, dist, entry, e[0], e[1], e[2], e[3], e[4], e[5], flags, fadeIn, fadeOut, GPR_U32(ctx, 2));
    }

    // FUN_003b6e10(component): picks the component's triangle-count for this draw from its distance table --
    // DAT_004b4a98 (0x4b4a98) is camera+0x2c8 * squared camera-space distance computed in FUN_003374c0,
    // DAT_004b4a88 (0x4b4a88) whether it fell under a table threshold, DAT_004b4ad0 (0x4b4ad0) the count.
    // Logged after the call: the distance, the flag, the full and chosen counts, the table (up to 4 entries).
    PS2Runtime::RecompiledFunction g_detailOriginal = nullptr;

    void socom2_DetailTrace(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint32_t comp = GPR_U32(ctx, 4);
        static const bool s_forceFar = ps2x::knob("PS2X_DETAIL_FAR") && std::atoi(ps2x::knob("PS2X_DETAIL_FAR")) != 0;
        if (s_forceFar)
            rdram[0x4b4a88u & PS2_RAM_MASK] = 0;
        g_detailOriginal(rdram, ctx, runtime);
        const double sec = std::chrono::duration<double>(std::chrono::steady_clock::now() - g_cullTraceStart).count();
        if (!g_cullTraceFile || g_cullTraceLeft <= 0 || sec < g_cullTraceAfter)
            return;
        float dist = 0.0f; uint8_t nearFlag = 0; uint32_t count = 0, flags = 0, table = 0, tableCount = 0;
        if (const uint8_t *q = getConstMemPtr(rdram, 0x4b4a98u)) std::memcpy(&dist, q, 4);
        if (const uint8_t *q = getConstMemPtr(rdram, 0x4b4a88u)) nearFlag = *q;
        if (const uint8_t *q = getConstMemPtr(rdram, 0x4b4ad0u)) std::memcpy(&count, q, 4);
        uint16_t full = 0;
        if (const uint8_t *pc = getConstMemPtr(rdram, comp))
        {
            std::memcpy(&flags, pc, 4);
            std::memcpy(&table, pc + 0x18 * 4, 4);
            std::memcpy(&tableCount, pc + 0x19 * 4, 4);
        }
        std::fprintf(g_cullTraceFile, "detail t=%.3f comp=%08x flags=%08x dist=%g near=%u count=%u table=%08x n=%u", sec, comp, flags, dist, nearFlag, count, table, tableCount);
        if (table && tableCount && tableCount < 16)
        {
            for (uint32_t i = 0; i < tableCount; ++i)
            {
                const uint8_t *pe = getConstMemPtr(rdram, table + i * 16u);
                if (!pe) break;
                float thr = 0.0f; uint16_t c8 = 0, ca = 0;
                std::memcpy(&thr, pe, 4); std::memcpy(&c8, pe + 8, 2); std::memcpy(&ca, pe + 10, 2);
                std::fprintf(g_cullTraceFile, " [%g:%u,%u]", thr, c8, ca);
            }
        }
        uint32_t ec0 = 0, ec8 = 0, ed0 = 0, ad8 = 0, ac8 = 0; uint8_t ed8 = 0;
        if (const uint8_t *q = getConstMemPtr(rdram, 0x4b4ec0u)) std::memcpy(&ec0, q, 4);
        if (const uint8_t *q = getConstMemPtr(rdram, 0x4b4ec8u)) std::memcpy(&ec8, q, 4);
        if (const uint8_t *q = getConstMemPtr(rdram, 0x4b4ed0u)) std::memcpy(&ed0, q, 4);
        if (const uint8_t *q = getConstMemPtr(rdram, 0x4b4ed8u)) ed8 = *q;
        if (const uint8_t *q = getConstMemPtr(rdram, 0x4b4ac8u)) std::memcpy(&ac8, q, 4);
        std::fprintf(g_cullTraceFile, " extra=%08x/%u off=%u near2=%u geom=%08x", ec0, ec8, ed0, ed8, ac8);
        // the variant header: geom - 16 bytes is the ushort[8] header FUN_003b6e10 read (count at [0], [6] offset, [7] extra)
        if (ac8 >= 16u)
        {
            if (const uint8_t *ph = getConstMemPtr(rdram, ac8 - 16u))
            {
                uint16_t h[8]; std::memcpy(h, ph, sizeof(h));
                std::fprintf(g_cullTraceFile, " hdr=%u,%u,%u,%u,%u,%u,%u,%u", h[0], h[1], h[2], h[3], h[4], h[5], h[6], h[7]);
            }
        }
        uint32_t stk[4] = {};
        if (const uint8_t *q = getConstMemPtr(rdram, 0x4b4a40u)) std::memcpy(stk, q, sizeof(stk));
        std::fprintf(g_cullTraceFile, " vstack=%08x,%08x,%08x,%08x ret=%u\n", stk[0], stk[1], stk[2], stk[3], GPR_U32(ctx, 2));
        (void)full;
    }

    // FUN_002918b0(t, record, out): applies a camera configuration record (piecewise tables at record + 0x22 /
    // 0x24 / 0x26) to the active camera (DAT_00415ff0 -> + 0xb4), including its LOD base scale (camera + 0x2cc).
    PS2Runtime::RecompiledFunction g_camCfgOriginal = nullptr;

    void socom2_CamCfgTrace(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        float t = 0.0f;
        std::memcpy(&t, &ctx->f[12], sizeof(t));
        const uint32_t rec = GPR_U32(ctx, 4);
        uint16_t o22 = 0, o24 = 0, o26 = 0; uint8_t b4 = 0;
        if (const uint8_t *pr = getConstMemPtr(rdram, rec))
        {
            std::memcpy(&o22, pr + 0x22, 2); std::memcpy(&o24, pr + 0x24, 2); std::memcpy(&o26, pr + 0x26, 2); b4 = pr[4];
        }
        g_camCfgOriginal(rdram, ctx, runtime);
        if (!g_cullTraceFile)
            return;
        uint32_t holder = 0, cam = 0; float lod[2] = {0.0f, 0.0f};
        if (const uint8_t *ph = getConstMemPtr(rdram, socom2_addresses::current().cameraHolder)) std::memcpy(&holder, ph, 4);
        if (holder) if (const uint8_t *pc = getConstMemPtr(rdram, holder + 0xb4u)) std::memcpy(&cam, pc, 4);
        if (cam) if (const uint8_t *pl = getConstMemPtr(rdram, cam + 0x2c8u)) std::memcpy(lod, pl, sizeof(lod));
        const double sec = std::chrono::duration<double>(std::chrono::steady_clock::now() - g_cullTraceStart).count();
        std::fprintf(g_cullTraceFile, "camcfg t=%.3f arg=%g rec=%08x b4=%02x o22=%u o24=%u o26=%u cam=%08x lod=%g/%g ret=%u\n",
                     sec, t, rec, b4, o22, o24, o26, cam, lod[0], lod[1], GPR_U32(ctx, 2));
    }

    // PS2X_PACK_TRACE=<file>: log every FUN_0025a5d0(archive, name, out, size) -- the level loader's "does this
    // inner file exist and can I read its first <size> bytes" probe (research/31 section 16: the per-instance
    // mesh variants "N%03d_I%03d_V%02d" fall back to variant 0 when it answers false) -- with its answer.
    PS2Runtime::RecompiledFunction g_packOriginal = nullptr;
    std::FILE *g_packTraceFile = nullptr;

    void socom2_PackTrace(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint32_t archive = GPR_U32(ctx, 4), nameAddr = GPR_U32(ctx, 5), size = GPR_U32(ctx, 7);
        char name[96] = {};
        if (const uint8_t *pn = getConstMemPtr(rdram, nameAddr))
        {
            for (int i = 0; i < 95 && pn[i]; ++i)
                name[i] = static_cast<char>(pn[i] >= 0x20 && pn[i] < 0x7f ? pn[i] : '?');
        }
        g_packOriginal(rdram, ctx, runtime);
        if (g_packTraceFile)
        {
            static uint32_t s_n = 0;
            std::fprintf(g_packTraceFile, "#%u archive=%08x size=%u name=%s -> %u\n", s_n++, archive, size, name, GPR_U32(ctx, 2) & 0xFFu);
            if ((s_n & 63u) == 0u)
                std::fflush(g_packTraceFile);
        }
    }

    void installPackTrace(PS2Runtime &runtime)
    {
        const char *path = ps2x::knob("PS2X_PACK_TRACE");
        const uint32_t kPack = socom2_addresses::current().packTrace;   // r0001: FUN_0025a5d0
        if (!path || !*path || !runtime.hasFunction(kPack))
            return;
        g_packTraceFile = std::fopen(path, "w");
        if (!g_packTraceFile)
            return;
        g_packOriginal = runtime.lookupFunction(kPack);
        runtime.replaceFunction(kPack, socom2_PackTrace);
        std::cout << "[pack-trace] 0x" << std::hex << kPack << std::dec << " -> " << path << std::endl;
    }

    // The deferred (sorted, translucent) draw list -- research/31 section 16: components whose flags carry bit 0 are
    // not drawn in place by FUN_003374c0 but queued through FUN_003371b0(object, list, a, b, component, cullResult)
    // into the bump buffer at scene + 0x638 and drawn later by FUN_00336cb0(list). Logged on the trace file:
    // "defer" per enqueue (list bump state, component, its flags) and "flush" per FUN_00336cb0 call with the
    // number of entries walked.
    PS2Runtime::RecompiledFunction g_deferOriginal = nullptr;
    PS2Runtime::RecompiledFunction g_flushOriginal = nullptr;

    void socom2_DeferTrace(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint32_t list = GPR_U32(ctx, 4), obj = GPR_U32(ctx, 5), comp = GPR_U32(ctx, 7), cullRes = GPR_U32(ctx, 8);
        uint32_t base = 0, bump = 0, cflags = 0;
        if (const uint8_t *pl = getConstMemPtr(rdram, list)) { std::memcpy(&base, pl + 4, 4); std::memcpy(&bump, pl + 8, 4); }
        if (const uint8_t *pc = getConstMemPtr(rdram, comp)) std::memcpy(&cflags, pc, 4);
        g_deferOriginal(rdram, ctx, runtime);
        const double sec = std::chrono::duration<double>(std::chrono::steady_clock::now() - g_cullTraceStart).count();
        if (!g_cullTraceFile || g_cullTraceLeft <= 0 || sec < g_cullTraceAfter)
            return;
        uint32_t bumpAfter = 0;
        if (const uint8_t *pl = getConstMemPtr(rdram, list)) std::memcpy(&bumpAfter, pl + 8, 4);
        std::fprintf(g_cullTraceFile, "defer t=%.3f obj=%08x list=%08x base=%08x bump=%08x->%08x used=%u comp=%08x cflags=%08x cull=%u\n",
                     sec, obj, list, base, bump, bumpAfter, bumpAfter >= base ? (bumpAfter - base) / 0x70u : 0u, comp, cflags, cullRes & 0xFFu);
    }

    void socom2_FlushTrace(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint32_t list = GPR_U32(ctx, 4);
        // count the linked entries: head at list + 0x14 (the node after the sentinel at list + 0x10), next at +4
        uint32_t n = 0, cur = 0;
        if (const uint8_t *pl = getConstMemPtr(rdram, list)) std::memcpy(&cur, pl + 0x14, 4);
        const uint32_t sentinel = list + 0x10u;
        while (cur && cur != sentinel && n < 100000)
        {
            const uint8_t *pn = getConstMemPtr(rdram, cur);
            if (!pn) break;
            std::memcpy(&cur, pn + 4, 4); ++n;
        }
        uint32_t c0c = 0, bump = 0, base = 0;
        if (const uint8_t *pl = getConstMemPtr(rdram, list)) { std::memcpy(&c0c, pl + 0xc, 4); std::memcpy(&base, pl + 4, 4); std::memcpy(&bump, pl + 8, 4); }
        g_flushOriginal(rdram, ctx, runtime);
        const double sec = std::chrono::duration<double>(std::chrono::steady_clock::now() - g_cullTraceStart).count();
        if (!g_cullTraceFile || g_cullTraceLeft <= 0 || sec < g_cullTraceAfter)
            return;
        std::fprintf(g_cullTraceFile, "flush t=%.3f list=%08x entries=%u field0c=%08x used=%u\n", sec, list, n, c0c, bump >= base ? (bump - base) / 0x70u : 0u);
    }

    void installCullTrace(PS2Runtime &runtime)
    {
        const socom2_addresses::Table &addr = socom2_addresses::current();
        const char *spec = ps2x::knob("PS2X_CULL_TRACE");
        if (!spec || !*spec)
        {
            if (ps2x::knob("PS2X_CULL_PARTIAL_CLIP") && runtime.hasFunction(addr.cull))
            {
                g_cullTraceStart = std::chrono::steady_clock::now();
                g_cullOriginal = runtime.lookupFunction(addr.cull);
                runtime.replaceFunction(addr.cull, socom2_CullTrace);
                std::cout << "[cull-trace] PS2X_CULL_PARTIAL_CLIP: partial boxes take the clipped family" << std::endl;
            }
            return;
        }
        std::string path = spec;
        int count = 4000;
        // "<file>:t<seconds>[:<count>]" -- the drive letter's colon is not a separator.
        size_t pos = path.find(":t");
        if (pos == std::string::npos)
        {
            std::cout << "[cull-trace] PS2X_CULL_TRACE needs <file>:t<seconds>[:<count>]" << std::endl;
            return;
        }
        std::string rest = path.substr(pos + 2);
        path = path.substr(0, pos);
        const size_t colon = rest.find(':');
        if (colon != std::string::npos)
        {
            count = std::atoi(rest.c_str() + colon + 1);
            rest = rest.substr(0, colon);
        }
        g_cullTraceAfter = std::atof(rest.c_str());
        if (!runtime.hasFunction(addr.cull))
        {
            std::cout << "[cull-trace] no function at 0x" << std::hex << addr.cull << std::dec << std::endl;
            return;
        }
        g_cullTraceFile = std::fopen(path.c_str(), "w");
        if (!g_cullTraceFile)
        {
            std::cout << "[cull-trace] cannot open " << path << std::endl;
            return;
        }
        g_cullTraceLeft = count > 0 ? count : 4000;
        g_cullTraceStart = std::chrono::steady_clock::now();
        g_cullOriginal = runtime.lookupFunction(addr.cull);
        runtime.replaceFunction(addr.cull, socom2_CullTrace);
        if (runtime.hasFunction(addr.node))
        {
            g_nodeOriginal = runtime.lookupFunction(addr.node);
            runtime.replaceFunction(addr.node, socom2_NodeTrace);
        }
        if (runtime.hasFunction(addr.node2))
        {
            g_nodeOriginal2 = runtime.lookupFunction(addr.node2);
            runtime.replaceFunction(addr.node2, socom2_NodeTrace2);
        }
        if (runtime.hasFunction(addr.lod))
        {
            g_lodOriginal = runtime.lookupFunction(addr.lod);
            runtime.replaceFunction(addr.lod, socom2_LodTrace);
        }
        if (runtime.hasFunction(addr.detail))
        {
            g_detailOriginal = runtime.lookupFunction(addr.detail);
            runtime.replaceFunction(addr.detail, socom2_DetailTrace);
        }
        if (runtime.hasFunction(addr.camCfg))
        {
            g_camCfgOriginal = runtime.lookupFunction(addr.camCfg);
            runtime.replaceFunction(addr.camCfg, socom2_CamCfgTrace);
        }
        if (runtime.hasFunction(addr.defer))
        {
            g_deferOriginal = runtime.lookupFunction(addr.defer);
            runtime.replaceFunction(addr.defer, socom2_DeferTrace);
        }
        if (runtime.hasFunction(addr.flush))
        {
            g_flushOriginal = runtime.lookupFunction(addr.flush);
            runtime.replaceFunction(addr.flush, socom2_FlushTrace);
        }
        std::cout << "[cull-trace] 0x" << std::hex << addr.cull << std::dec << " -> " << path
                  << " from t=" << g_cullTraceAfter << "s, " << g_cullTraceLeft << " calls" << std::endl;
    }

    void installCrashHandler(PS2Runtime &runtime)
    {
        g_runtimeForCrash = &runtime;
#ifdef _WIN32
        AddVectoredExceptionHandler(1, crashHandler);
#elif defined(__linux__)
        installPosixCrashHandler();
#endif
    }

    // The reader socom2_addresses::selectFromImage probes each column's build stamp through. Forty bytes
    // is the whole stamp ("SOCOM 2 rNNNN HH:MM:SS Mon DD YYYY" and its terminator); an address holding
    // anything else -- code, zeros, another build's data -- simply names no revision.
    std::string readGuestStamp(uint32_t addr, void *user)
    {
        const uint8_t *p = getConstMemPtr(static_cast<const uint8_t *>(user), addr);
        std::string s;
        for (int i = 0; p && i < 40 && p[i]; ++i)
            s.push_back(static_cast<char>(p[i]));
        std::cout << "[socom2] mem@0x" << std::hex << addr << std::dec << " = \"" << s << "\"" << std::endl;
        return s;
    }

    void applySocom2(PS2Runtime &runtime)
    {
        std::cout << "[socom2] applying SOCOM II overrides" << std::endl;
        installCrashHandler(runtime);
        {
            // The FTSCore data segment carries the build stamp ("SOCOM 2 r0001 17:22:21 Oct 11 2003",
            // "SOCOM 2 r0004 10:14:38 Nov  3 2004"). Reading it here does double duty: it proves the
            // overlay is resident, and it chooses the address column every install below reads
            // (runtime/socom2_addresses.h). It has to run first: an install that ran before the choice
            // would have wrapped an r0001 address in another build.
            //
            // The stamp is read at EVERY column's own versionString, not at r0001's: the banner moves with
            // the relink (r0001 0x003e17e0, r0004 0x0040cc60), and in an r0004 image r0001's address is
            // code. Reading only r0001's is exactly what made the r0004 exe run on r0001's addresses.
            socom2_addresses::selectFromImage(readGuestStamp, runtime.memory().getRDRAM());

            // Task 19 round 3: and now the OTHER half of the question. Which column to read is one thing;
            // whether this executable's generated code belongs on this image at all is another, and until
            // here nothing asked it. On 2026-09-23 two parity gates ran the r0004 executable against
            // r0001's image (the launch scripts hard-coded game/disc/socom2_game.elf): it booted, walked
            // r0001's constructor table into r0004 function bodies, and hung at the loading screen on a
            // jalr through a slot the constructors never filled -- with nothing in the log to say the code
            // and the image disagreed. One comparison, and a refusal rather than a warning: past a
            // mismatch every address, every table and every body is the other build's.
            socom2_revision::enforce(socom2_addresses::imageRevision().c_str(),
                                     PS2Runtime::getIoPaths().elfPath.string(),
                                     socom2_addresses::imageBanner());
        }
        startPcSampler(runtime);
        startRdramDump(runtime);
        installCallTrace(runtime);
        installMusicTrace(runtime);
        installCullTrace(runtime);
        installPackTrace(runtime);
        // newlib rand()/srand() share `struct _reent._rand_next`: _impure_ptr lives at 0x001cc750
        // and points at 0x001cc460, _rand_next is at +0xa8 (SCUS_972.75 FUN_00197728/FUN_00197740).
        // rand() is stubbed (recomp/socom2.toml) but srand() is not, and the game boots with
        // `srand(<RTC>); srand(rand());` -- both halves have to write the same word.
        ps2_stubs::setLibcRandState(0x001CC750u, 0xA8u);
        ps2_stubs::setMpegDemuxIdleYields(true);   // research/32 section 7.1: the movie thread re-polls the demux in a loop
        configureCdImage();
        // The addresses below socom2_addresses::kOverlayBase (0x1d5600) are the BOOT LOADER's and stay
        // literal on purpose: the loader is the same binary in every pressing of the game -- it is what
        // loads the overlays that differ -- so there is nothing for a per-revision table to vary. Only
        // overlay addresses belong in socom2_addresses.h, and its suite fails on a loader address in it.
        runtime.replaceFunction(0x001c59c0u, socom2_LoadGameCodeFromDisc);
        runtime.replaceFunction(0x001c5b30u, socom2_LoadGameCodeFromMemcard);
        runtime.replaceFunction(0x00181c90u, socom2_LoadOverlayFile);
        runtime.replaceFunction(0x001a6110u, ps2_stubs::socom2_SifSendCmd); // sceSifSendCmd: sreg handshake echo
        // msifrpc (libnetb transport) answered on the host; see the "msifrpc HLE" section.
        runtime.replaceFunction(0x001bcd80u, ps2_stubs::socom2_MsifInit);
        runtime.replaceFunction(0x001bd050u, ps2_stubs::socom2_MsifBind);
        runtime.replaceFunction(0x001bd320u, ps2_stubs::socom2_MsifCall);
        runtime.replaceFunction(0x001bd200u, ps2_stubs::socom2_MsifUnbind);
        // libnetb_ex ring-buffer path -> host sockets (socom2_libnetb.cpp). Task 19: these and the
        // libdnas2 crypto entry points below are columns of socom2_addresses.h now, not literals. They
        // were the last overlay addresses an r0004 image still reached at r0001 values -- libnetb_ex
        // happens not to have moved, but that is a fact the table records, not one the code may assume.
        {
            const socom2_addresses::Table &addr = socom2_addresses::current();
            struct Bind { uint32_t address; const char *field; PS2Runtime::RecompiledFunction fn; };
            const Bind netb[] = {
                {addr.netbExOpen, "netbExOpen", socom2_libnetb::exOpen},
                {addr.netbExTcpRecv, "netbExTcpRecv", socom2_libnetb::exTcpRecv},
                {addr.netbExTcpSend, "netbExTcpSend", socom2_libnetb::exTcpSend},
                {addr.netbExUdpRecv, "netbExUdpRecv", socom2_libnetb::exUdpRecv},
                {addr.netbExUdpSend, "netbExUdpSend", socom2_libnetb::exUdpSend},
                {addr.netbExAvailable, "netbExAvailable", socom2_libnetb::exAvailable},
                {addr.netbExConnected, "netbExConnected", socom2_libnetb::exConnected},
                {addr.netbExStartAsync, "netbExStartAsync", socom2_libnetb::exStartAsync},
                {addr.netbExStartAsync2, "netbExStartAsync2", socom2_libnetb::exStartAsync},
            };
            for (const Bind &b : netb)
                if (socom2_addresses::require(b.address, b.field))
                    runtime.replaceFunction(b.address, b.fn);
        }
        installRtNetPortShift(runtime);
        installOskPrefill(runtime);   // Sprint 10 Goal 9: only when PS2X_SOCOM2_LOGIN_NAME/_PASS is set
        installChatBound(runtime);    // Sprint 11 milestone S: unconditional, no knob

        {
            const socom2_addresses::Table &addr = socom2_addresses::current();
            if (socom2_addresses::require(addr.netbExDescriptorDma, "netbExDescriptorDma"))
                ps2_game_overrides::bindAddressHandler(runtime, addr.netbExDescriptorDma, "ret0");   // descriptor DMA helper
            // rt_crypt: RSA block transform, SHA-1 and RC4 on the host (socom2_crypto.cpp). libdnas2
            // moved wholesale between the two builds (+0x7ac0), which is exactly what a column is for.
            struct Bind { uint32_t address; const char *field; PS2Runtime::RecompiledFunction fn; };
            const Bind crypto[] = {
                {addr.dnasRsaBlock, "dnasRsaBlock", socom2_crypto::rsaBlock},
                {addr.dnasSha1Hash, "dnasSha1Hash", socom2_crypto::sha1Hash},
                {addr.dnasRc4SetKeyHash, "dnasRc4SetKeyHash", socom2_crypto::rc4SetKeyHash},
                {addr.dnasRc4SetKey, "dnasRc4SetKey", socom2_crypto::rc4SetKey},
                {addr.dnasRc4Encrypt, "dnasRc4Encrypt", socom2_crypto::rc4EncryptFn},
                {addr.dnasRc4Decrypt, "dnasRc4Decrypt", socom2_crypto::rc4DecryptFn},
            };
            for (const Bind &b : crypto)
                if (socom2_addresses::require(b.address, b.field))
                    runtime.replaceFunction(b.address, b.fn);
        }
        // DNAS authentication object (FTSCore FUN_002cc670 in r0001, FUN_002cf330 in r0004 -- the same
        // address the r0004 capsule's second patch table writes): the published r0001 bypass patches
        // `jr ra` at its entry; a private Horizon server needs no DNAS. This is the login gate, so a
        // column that could not place it must say so rather than patch the other revision's address.
        {
            const uint32_t dnas = socom2_addresses::current().dnasCheck;
            if (socom2_addresses::require(dnas, "dnasCheck") && runtime.hasFunction(dnas))
                runtime.replaceFunction(dnas, ps2_stubs::socom2_DnasTickDone);
            else if (socom2_addresses::available(dnas))
                std::cout << "[socom2] no function at 0x" << std::hex << dnas << std::dec
                          << "; the DNAS tick is the game's own" << std::endl;
        }
        // _InitSys kernel-patch search (FindAddress loop over the BIOS): nothing to find here.
        ps2_game_overrides::bindAddressHandler(runtime, 0x001ac9d8u, "ret0");
        // PS2X_HLE_STATS=1 wraps the bound stubs' table entries: last, so it wraps whatever
        // handler each address finally carries (Kernel/HleStats.h).
        ps2_hle_stats::installFromEnvironment(runtime);
        // PS2X_SCHED_TRACE=1 (research/36 item 16) times the same stubs; after the stats so it wraps them too.
        ps2_sched_trace::installFromEnvironment(runtime);
    }
}

PS2_REGISTER_GAME_OVERRIDE("socom2-us", "socom2_game.elf", 0x00180008u, 0u, applySocom2)

#if defined(__linux__) && defined(__x86_64__)
namespace
{
    // ---- Sprint 8 Goal 1 design item 3: the Linux half of the host PC sampler -------------------
    // Windows suspends the sampled thread and reads CONTEXT.Rip from the sampler thread. Linux has
    // no such call, so the kernel interrupts the sampled thread itself: a SIGPROF interval timer
    // (timer_create with SIGEV_THREAD_ID, which takes the thread's KERNEL tid) at the Windows
    // sampler's period, and the handler records uc_mcontext.gregs[REG_RIP] into this ring exactly
    // as the Windows path stores the context RIP. Everything after the sample -- the histogram, the
    // module resolution, the hostprof.txt dump -- is the same code shape on both platforms.
    constexpr uint32_t kHostProfMaxFrames = 24u;
    constexpr uint32_t kHostProfRing = 4096u;   // power of two
    struct HostProfSample
    {
        std::atomic<uint64_t> rip{0};   // published last, with release; 0 = the slot is not ready
        uint32_t tid = 0;
        uint32_t frameCount = 0;
        uint64_t frames[kHostProfMaxFrames] = {};
    };
    HostProfSample g_hostProfRing[kHostProfRing];
    std::atomic<uint64_t> g_hostProfWrite{0};
    std::atomic<bool> g_hostProfStacks{false};
    uint64_t g_hostProfRead = 0;    // the drain thread alone
    uint64_t g_hostProfLost = 0;    // samples the drain thread could not keep up with

    void hostProfSignalHandler(int, siginfo_t *, void *ctx)
    {
        if (!ctx)
            return;
        const uint64_t rip =
            static_cast<uint64_t>(reinterpret_cast<const ucontext_t *>(ctx)->uc_mcontext.gregs[REG_RIP]);
        if (!rip)
            return;
        const uint64_t slot = g_hostProfWrite.fetch_add(1, std::memory_order_relaxed);
        HostProfSample &s = g_hostProfRing[slot & (kHostProfRing - 1u)];
        s.tid = static_cast<uint32_t>(::syscall(SYS_gettid));
        uint32_t frameCount = 0;
        if (g_hostProfStacks.load(std::memory_order_relaxed))
        {
            // backtrace() is pre-warmed before the timers are armed (libgcc allocates once).
            void *frames[kHostProfMaxFrames];
            const int n = ::backtrace(frames, static_cast<int>(kHostProfMaxFrames));
            for (int i = 0; i < n; ++i)
                s.frames[i] = reinterpret_cast<uint64_t>(frames[i]);
            frameCount = n > 0 ? static_cast<uint32_t>(n) : 0u;
        }
        s.frameCount = frameCount;
        s.rip.store(rip, std::memory_order_release);
    }

    bool hostProfInstallSignal()
    {
        // Before any timer is armed: SIGPROF kills the process by default.
        struct sigaction sa;
        std::memset(&sa, 0, sizeof(sa));
        sa.sa_sigaction = hostProfSignalHandler;
        sa.sa_flags = SA_SIGINFO | SA_RESTART;
        sigemptyset(&sa.sa_mask);
        return ::sigaction(SIGPROF, &sa, nullptr) == 0;
    }

    // One periodic timer delivering SIGPROF to ONE thread. CLOCK_MONOTONIC, not
    // CLOCK_THREAD_CPUTIME_ID: the Windows sampler samples on a wall-clock period, and a thread CPU
    // clock can only ever be the clock of the thread that calls timer_create.
    bool hostProfArmTimer(int tid, double periodMs, timer_t *out)
    {
        struct sigevent sev;
        std::memset(&sev, 0, sizeof(sev));
        sev.sigev_notify = SIGEV_THREAD_ID;
        sev.sigev_signo = SIGPROF;
#if defined(sigev_notify_thread_id)
        sev.sigev_notify_thread_id = tid;
#else
        sev._sigev_un._tid = tid;
#endif
        timer_t timer{};
        if (::timer_create(CLOCK_MONOTONIC, &sev, &timer) != 0)
            return false;
        struct itimerspec its;
        std::memset(&its, 0, sizeof(its));
        const long long ns = static_cast<long long>(periodMs * 1e6);
        its.it_interval.tv_sec = static_cast<time_t>(ns / 1000000000LL);
        its.it_interval.tv_nsec = static_cast<long>(ns % 1000000000LL);
        its.it_value = its.it_interval;
        if (::timer_settime(timer, 0, &its, nullptr) != 0)
        {
            ::timer_delete(timer);
            return false;
        }
        *out = timer;
        return true;
    }

    // The mirror of GetModuleHandleW(nullptr): the load address of the main executable.
    uint64_t hostProfModuleBase()
    {
        Dl_info dli;
        if (::dladdr(reinterpret_cast<void *>(&hostProfModuleBase), &dli) && dli.dli_fbase)
            return reinterpret_cast<uint64_t>(dli.dli_fbase);
        return 0;
    }

    // The mirror of GetThreadDescription: /proc/self/task/<tid>/comm.
    std::string hostProfThreadName(int tid)
    {
        char path[64];
        std::snprintf(path, sizeof(path), "/proc/self/task/%d/comm", tid);
        std::ifstream f(path);
        std::string name;
        std::getline(f, name);
        return name;
    }

    // -> samples consumed. Everything the handlers have published since the last call.
    uint64_t hostProfDrain(std::unordered_map<uint64_t, uint32_t> &counts,
                           std::unordered_map<std::string, uint32_t> &stackCounts,
                           std::unordered_map<int, uint64_t> &perThread, bool stacks)
    {
        const uint64_t head = g_hostProfWrite.load(std::memory_order_acquire);
        if (head - g_hostProfRead > kHostProfRing)
        {
            g_hostProfLost += head - g_hostProfRead - kHostProfRing;
            g_hostProfRead = head - kHostProfRing;
        }
        uint64_t n = 0;
        for (; g_hostProfRead < head; ++g_hostProfRead)
        {
            HostProfSample &s = g_hostProfRing[g_hostProfRead & (kHostProfRing - 1u)];
            const uint64_t rip = s.rip.load(std::memory_order_acquire);
            if (!rip)
            {
                // The handler reserved the slot but has not published it yet: one lost sample.
                ++g_hostProfLost;
                continue;
            }
            ++counts[rip];
            ++perThread[static_cast<int>(s.tid)];
            if (stacks && s.frameCount > 0)
            {
                std::string key;
                key.reserve(s.frameCount * 13u);
                char b[24];
                for (uint32_t i = 0; i < s.frameCount && i < kHostProfMaxFrames; ++i)
                {
                    std::snprintf(b, sizeof(b), "%llx", static_cast<unsigned long long>(s.frames[i]));
                    if (i)
                        key += ';';
                    key += b;
                }
                ++stackCounts[key];
            }
            s.rip.store(0, std::memory_order_relaxed);
            ++n;
        }
        return n;
    }
}
#endif

// PS2X_HOST_PROF=<ms>: sample the game thread's host instruction pointer every <ms> (SuspendThread +
// GetThreadContext) and write the histogram to PS2X_HOST_PROF_OUT (default logs/hostprof.txt) every
// 10 s: "rva count" lines, RVA relative to the exe's load address, plus the load address itself.
// Symbolize offline with tools_py/hostprof_symbolize.py (llvm-nm on dist/socom2.exe). Guest-level
// samplers only say which recompiled function is hot; this says which *host* code is hot inside it.
void ps2HostProfStart(std::thread::native_handle_type nativeHandle)
{
#ifdef _WIN32
    const char *env = ps2x::knob("PS2X_HOST_PROF");
    if (!env || !*env)
        return;
    const double periodMs = std::max(0.2, std::atof(env));
    const char *outEnv = ps2x::knob("PS2X_HOST_PROF_OUT");
    const std::string outPath = outEnv && *outEnv ? outEnv : "logs/hostprof.txt";
    // PS2X_HOST_PROF_ALL=1: sample every thread of the process (the game thread alone may show only
    // part of the work). Samples are merged into one histogram plus a per-thread table; addresses
    // outside the exe are written with their module name ("ext <module>+off").
    const bool allThreads = ps2x::knob("PS2X_HOST_PROF_ALL") != nullptr;
    // PS2X_HOST_PROF_MAIN=1: sample the calling (main / GL render) thread instead of the game thread.
    const bool mainThread = ps2x::knob("PS2X_HOST_PROF_MAIN") != nullptr;
    HANDLE dup = nullptr;
    if (!DuplicateHandle(GetCurrentProcess(), mainThread ? GetCurrentThread() : static_cast<HANDLE>(nativeHandle), GetCurrentProcess(), &dup,
                         THREAD_SUSPEND_RESUME | THREAD_GET_CONTEXT | THREAD_QUERY_INFORMATION, FALSE, 0))
    {
        std::cerr << "[host-prof] DuplicateHandle failed: " << GetLastError() << std::endl;
        return;
    }
    const uint64_t base = reinterpret_cast<uint64_t>(GetModuleHandleW(nullptr));
    std::cout << "[host-prof] sampling every " << periodMs << " ms -> " << outPath << " (base 0x" << std::hex << base << std::dec
              << (allThreads ? ", all threads" : "") << ")" << std::endl;
    std::thread([dup, periodMs, outPath, base, allThreads]() {
        SetThreadPriority(GetCurrentThread(), THREAD_PRIORITY_TIME_CRITICAL);
        std::unordered_map<uint64_t, uint32_t> counts;
        // PS2X_HOST_PROF_STACKS=1: also record the call stack of every sample ("stack <n> a;b;c"
        // lines, leaf first, raw addresses; tools_py/hostprof_stacks.py folds and symbolizes).
        const bool stacks = ps2x::knob("PS2X_HOST_PROF_STACKS") != nullptr;
        constexpr uint32_t kMaxFrames = 24u;
        std::unordered_map<std::string, uint32_t> stackCounts;
        std::unordered_map<DWORD, uint64_t> perThread;
        std::unordered_map<DWORD, HANDLE> handles;
        uint64_t total = 0, suspendFail = 0;
        auto lastDump = std::chrono::steady_clock::now();
        auto lastScan = std::chrono::steady_clock::time_point{};
        const DWORD self = GetCurrentThreadId();
        const DWORD pid = GetCurrentProcessId();
        typedef HRESULT(WINAPI * GetThreadDescriptionFn)(HANDLE, PWSTR *);
        const GetThreadDescriptionFn getDesc = reinterpret_cast<GetThreadDescriptionFn>(
            reinterpret_cast<void *>(GetProcAddress(GetModuleHandleW(L"kernel32.dll"), "GetThreadDescription")));
        for (;;)
        {
            std::this_thread::sleep_for(std::chrono::duration<double, std::milli>(periodMs));
            const auto now = std::chrono::steady_clock::now();
            if (allThreads && now - lastScan >= std::chrono::seconds(2))
            {
                lastScan = now;
                HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPTHREAD, 0);
                if (snap != INVALID_HANDLE_VALUE)
                {
                    THREADENTRY32 te;
                    te.dwSize = sizeof(te);
                    if (Thread32First(snap, &te))
                    {
                        do
                        {
                            if (te.th32OwnerProcessID != pid || te.th32ThreadID == self || handles.count(te.th32ThreadID))
                                continue;
                            HANDLE h = OpenThread(THREAD_SUSPEND_RESUME | THREAD_GET_CONTEXT | THREAD_QUERY_INFORMATION, FALSE, te.th32ThreadID);
                            if (h)
                                handles[te.th32ThreadID] = h;
                        } while (Thread32Next(snap, &te));
                    }
                    CloseHandle(snap);
                }
            }
            auto sampleOne = [&](HANDLE h, DWORD tid) {
                if (SuspendThread(h) == static_cast<DWORD>(-1))
                {
                    ++suspendFail;
                    return;
                }
                CONTEXT c;
                std::memset(&c, 0, sizeof(c));
                c.ContextFlags = CONTEXT_FULL;
                uint64_t rip = 0;
                uint64_t frames[kMaxFrames];
                uint32_t frameCount = 0;
                if (GetThreadContext(h, &c))
                {
                    rip = c.Rip;
                    if (stacks)
                    {
                        // x64 unwind through the module unwind tables (no allocation while the
                        // thread is suspended; the stack memory stays mapped, so a stale read
                        // costs at most a garbage frame).
                        CONTEXT u = c;
                        for (; frameCount < kMaxFrames && u.Rip != 0; ++frameCount)
                        {
                            frames[frameCount] = u.Rip;
                            DWORD64 imageBase = 0;
                            PRUNTIME_FUNCTION fn = RtlLookupFunctionEntry(u.Rip, &imageBase, nullptr);
                            if (!fn)
                            {
                                // leaf function without unwind info: the return address is at [rsp]
                                if (u.Rsp == 0 || IsBadReadPtr(reinterpret_cast<void *>(u.Rsp), 8))
                                    break;
                                u.Rip = *reinterpret_cast<uint64_t *>(u.Rsp);
                                u.Rsp += 8;
                                continue;
                            }
                            void *handlerData = nullptr;
                            DWORD64 establisher = 0;
                            RtlVirtualUnwind(UNW_FLAG_NHANDLER, imageBase, u.Rip, fn, &u, &handlerData, &establisher, nullptr);
                        }
                    }
                }
                ResumeThread(h);
                if (rip)
                {
                    ++counts[rip];
                    ++perThread[tid];
                    ++total;
                    if (stacks && frameCount > 0)
                    {
                        std::string key;
                        key.reserve(frameCount * 13);
                        char b[24];
                        for (uint32_t i = 0; i < frameCount; ++i)
                        {
                            std::snprintf(b, sizeof(b), "%llx", static_cast<unsigned long long>(frames[i]));
                            if (i)
                                key += ';';
                            key += b;
                        }
                        ++stackCounts[key];
                    }
                }
            };
            if (allThreads)
            {
                for (auto &kv : handles)
                    sampleOne(kv.second, kv.first);
            }
            else
                sampleOne(dup, 0);
            if (now - lastDump >= std::chrono::seconds(10))
            {
                lastDump = now;
                std::vector<std::pair<uint64_t, uint32_t>> v(counts.begin(), counts.end());
                std::sort(v.begin(), v.end(), [](const auto &a, const auto &b) { return a.second > b.second; });
                std::ofstream f(outPath + ".tmp", std::ios::trunc);
                f << "base 0x" << std::hex << base << std::dec << " total " << total << "\n";
                size_t n = 0;
                for (const auto &kv : v)
                {
                    HMODULE mod = nullptr;
                    const bool inExe = GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                                                          reinterpret_cast<LPCWSTR>(kv.first), &mod) &&
                                       reinterpret_cast<uint64_t>(mod) == base;
                    if (inExe)
                        f << std::hex << kv.first - base << std::dec << " " << kv.second << "\n";
                    else
                    {
                        char name[MAX_PATH] = {0};
                        if (mod)
                            GetModuleFileNameA(mod, name, sizeof(name));
                        const char *slash = std::strrchr(name, '\\');
                        f << std::hex << kv.first << std::dec << " " << kv.second << " ext " << (mod ? (slash ? slash + 1 : name) : "?")
                          << "+0x" << std::hex << (mod ? kv.first - reinterpret_cast<uint64_t>(mod) : 0) << std::dec << "\n";
                    }
                    if (++n >= 40000u)
                        break;
                }
                if (stacks)
                {
                    std::vector<std::pair<std::string, uint32_t>> sv(stackCounts.begin(), stackCounts.end());
                    std::sort(sv.begin(), sv.end(), [](const auto &a, const auto &b) { return a.second > b.second; });
                    size_t m = 0;
                    for (const auto &kv : sv)
                    {
                        f << "stack " << kv.second << " " << kv.first << "\n";
                        if (++m >= 20000u)
                            break;
                    }
                }
                if (allThreads)
                {
                    for (const auto &kv : perThread)
                    {
                        std::string desc;
                        auto it = handles.find(kv.first);
                        if (it != handles.end() && getDesc)
                        {
                            PWSTR w = nullptr;
                            if (SUCCEEDED(getDesc(it->second, &w)) && w)
                            {
                                for (PWSTR q = w; *q; ++q)
                                    desc += static_cast<char>(*q < 128 ? *q : '?');
                                LocalFree(w);
                            }
                        }
                        f << "thread " << kv.first << " " << kv.second << " " << desc << "\n";
                    }
                }
                f.close();
                std::error_code ec;
                std::filesystem::rename(outPath + ".tmp", outPath, ec);
                if (ec)
                {
                    std::filesystem::remove(outPath, ec);
                    std::filesystem::rename(outPath + ".tmp", outPath, ec);
                }
            }
        }
    }).detach();
#elif defined(__linux__) && defined(__x86_64__)
    // The Linux half (Sprint 8 Goal 1 design item 3). Same environment knobs, same [host-prof] line,
    // same hostprof.txt shape, so tools_py/hostprof_symbolize.py reads either platform's file.
    const char *env = ps2x::knob("PS2X_HOST_PROF");
    if (!env || !*env)
        return;
    const double periodMs = std::max(0.2, std::atof(env));
    const char *outEnv = ps2x::knob("PS2X_HOST_PROF_OUT");
    const std::string outPath = outEnv && *outEnv ? outEnv : "logs/hostprof.txt";
    const bool allThreads = ps2x::knob("PS2X_HOST_PROF_ALL") != nullptr;
    const bool mainThread = ps2x::knob("PS2X_HOST_PROF_MAIN") != nullptr;
    const bool stacks = ps2x::knob("PS2X_HOST_PROF_STACKS") != nullptr;
    // nativeHandle is the game thread pthread_t, which no call turns into a kernel tid; the tid was
    // recorded on the thread itself when it named itself GameThread (include/ThreadNaming.h), which
    // is where the Windows path duplicates the thread handle.
    (void)nativeHandle;
    const int mainTid = ThreadNaming::currentThreadTid();
    const uint64_t base = hostProfModuleBase();
    g_hostProfStacks.store(stacks, std::memory_order_relaxed);
    std::cout << "[host-prof] sampling every " << periodMs << " ms -> " << outPath << " (base 0x" << std::hex << base << std::dec
              << (allThreads ? ", all threads" : "") << ")" << std::endl;
    std::thread([periodMs, outPath, base, allThreads, mainThread, stacks, mainTid]() {
        // No TIME_CRITICAL equivalent is needed: the kernel timer takes the samples, this thread
        // only drains the ring and writes the file.
        if (!hostProfInstallSignal())
        {
            std::cerr << "[host-prof] sigaction(SIGPROF) failed: " << errno << std::endl;
            return;
        }
        if (stacks)
        {
            void *warm[4];
            (void)::backtrace(warm, 4);   // libgcc allocates on the first unwind, never in the handler
        }
        const int selfTid = ThreadNaming::currentThreadTid();
        int eeTid = mainThread ? mainTid : 0;
        if (!mainThread)
        {
            // ps2HostProfStart is called right after the game thread is created; wait (up to 5 s)
            // for it to name itself.
            for (int i = 0; i < 1000 && eeTid == 0; ++i)
            {
                eeTid = ThreadNaming::gameThreadTid();
                if (eeTid == 0)
                    std::this_thread::sleep_for(std::chrono::milliseconds(5));
            }
            if (eeTid == 0)
            {
                std::cerr << "[host-prof] the game thread never named itself; nothing to sample" << std::endl;
                return;
            }
        }
        std::unordered_map<int, timer_t> timers;
        if (!allThreads)
        {
            timer_t t{};
            if (!hostProfArmTimer(eeTid, periodMs, &t))
            {
                std::cerr << "[host-prof] timer_create failed: " << errno << std::endl;
                return;
            }
            timers[eeTid] = t;
        }
        std::unordered_map<uint64_t, uint32_t> counts;
        std::unordered_map<std::string, uint32_t> stackCounts;
        std::unordered_map<int, uint64_t> perThread;
        uint64_t total = 0;
        auto lastDump = std::chrono::steady_clock::now();
        auto lastScan = std::chrono::steady_clock::time_point{};
        for (;;)
        {
            std::this_thread::sleep_for(std::chrono::duration<double, std::milli>(std::max(1.0, periodMs)));
            const auto now = std::chrono::steady_clock::now();
            if (allThreads && now - lastScan >= std::chrono::seconds(2))
            {
                // The mirror of the Toolhelp thread snapshot: every task of this process.
                lastScan = now;
                if (DIR *d = ::opendir("/proc/self/task"))
                {
                    while (const dirent *e = ::readdir(d))
                    {
                        const int tid = std::atoi(e->d_name);
                        if (tid <= 0 || tid == selfTid || timers.count(tid))
                            continue;
                        timer_t t{};
                        if (hostProfArmTimer(tid, periodMs, &t))
                            timers[tid] = t;
                    }
                    ::closedir(d);
                }
            }
            total += hostProfDrain(counts, stackCounts, perThread, stacks);
            if (now - lastDump >= std::chrono::seconds(10))
            {
                lastDump = now;
                std::vector<std::pair<uint64_t, uint32_t>> v(counts.begin(), counts.end());
                std::sort(v.begin(), v.end(), [](const auto &a, const auto &b) { return a.second > b.second; });
                std::ofstream f(outPath + ".tmp", std::ios::trunc);
                f << "base 0x" << std::hex << base << std::dec << " total " << total << "\n";
                size_t n = 0;
                for (const auto &kv : v)
                {
                    // dladdr is the mirror of GetModuleHandleExW(FROM_ADDRESS) + GetModuleFileNameA.
                    Dl_info dli;
                    const bool known = ::dladdr(reinterpret_cast<void *>(kv.first), &dli) != 0 && dli.dli_fbase != nullptr;
                    const uint64_t modBase = known ? reinterpret_cast<uint64_t>(dli.dli_fbase) : 0ull;
                    if (known && modBase == base)
                        f << std::hex << kv.first - base << std::dec << " " << kv.second << "\n";
                    else
                    {
                        const char *name = known ? dli.dli_fname : nullptr;
                        const char *slash = name ? std::strrchr(name, '/') : nullptr;
                        f << std::hex << kv.first << std::dec << " " << kv.second << " ext " << (name ? (slash ? slash + 1 : name) : "?")
                          << "+0x" << std::hex << (modBase ? kv.first - modBase : 0ull) << std::dec << "\n";
                    }
                    if (++n >= 40000u)
                        break;
                }
                if (stacks)
                {
                    std::vector<std::pair<std::string, uint32_t>> sv(stackCounts.begin(), stackCounts.end());
                    std::sort(sv.begin(), sv.end(), [](const auto &a, const auto &b) { return a.second > b.second; });
                    size_t m = 0;
                    for (const auto &kv : sv)
                    {
                        f << "stack " << kv.second << " " << kv.first << "\n";
                        if (++m >= 20000u)
                            break;
                    }
                }
                if (allThreads)
                {
                    for (const auto &kv : perThread)
                        f << "thread " << kv.first << " " << kv.second << " " << hostProfThreadName(kv.first) << "\n";
                }
                f.close();
                std::error_code ec;
                std::filesystem::rename(outPath + ".tmp", outPath, ec);
                if (ec)
                {
                    std::filesystem::remove(outPath, ec);
                    std::filesystem::rename(outPath + ".tmp", outPath, ec);
                }
            }
        }
    }).detach();
#else
    // Any other UNIX (no ucontext gregs / no POSIX timers we can point at one thread): a no-op that
    // says so once, rather than a silent knob.
    (void)nativeHandle;
    if (const char *env = ps2x::knob("PS2X_HOST_PROF"); env && *env)
        std::cout << "[host-prof] not supported on this platform; PS2X_HOST_PROF ignored" << std::endl;
#endif
}
