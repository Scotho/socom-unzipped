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
#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include "runtime/ps2_memory.h"
#include "runtime/ee_scheduler.h"
#include "socom2_rsa_key.h"
#include "socom2_host_input.h"
#include "socom2_libnetb.h"
#include "socom2_crypto.h"
#include <cstring>
#include <fstream>
#include <vector>
#include <thread>
#ifdef _WIN32
#include <windows.h>
#endif
#include <chrono>
#include <cstdlib>

#include <cstdint>
#include <filesystem>
#include <iomanip>
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
        std::memcpy(rdram + (nAddr & PS2_RAM_MASK), kSocom2RsaN, sizeof(kSocom2RsaN));
        std::memcpy(rdram + (dAddr & PS2_RAM_MASK), kSocom2RsaD, sizeof(kSocom2RsaD));
        std::cout << "[socom2] rt_crypt RSA key pair -> fixed precomputed key" << std::endl;
        ctx->pc = GPR_U32(ctx, 31);
    }

    // Bound at recompile time via recomp/socom2.toml: "socom2_LumReadPixel@0x003B24C0".
    // FUN_003b24c0(packet, out) is the auto-exposure thread's one-pixel framebuffer readback: it
    // sends a 7-qword VIF1 packet (BITBLTBUF/TRXPOS/TRXREG/TRXDIR local->host), waits for FINISH,
    // sets BUSDIR and reads the pixel back through the VIF1 FIFO in reverse mode (VIF1_STAT FQC).
    // The runtime has no reverse-FIFO path yet, so every wait ran to its 16M-iteration timeout
    // (~0.3 s per cell, ~176 cells per pass) and the priority-4 thread (FUN_003b1dd0, woken from the
    // vsync path once a mission is up) starved the main thread down to one tick per minute. Until
    // the readback is implemented, answer with a mid-grey pixel (neutral iris) immediately.
    void socom2_LumReadPixel(uint8_t *rdram, R5900Context *ctx, PS2Runtime *)
    {
        const uint32_t outAddr = GPR_U32(ctx, 5);
        uint8_t *out = rdram + (outAddr & PS2_RAM_MASK);
        out[0] = 0x80;
        out[1] = 0x80;
        out[2] = 0x80;
        out[3] = 0x80;
        static int logged = 0;
        if (logged++ < 3)
            std::cout << "[socom2] exposure readback FUN_003b24c0 -> stubbed grey pixel" << std::endl;
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
        if (std::getenv("PS2X_SOCOM2_NET_TRACE"))
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

    // Reporting a connected pad through scePad2 makes the game run first-time controller
    // configuration through Sony's libdbc/DBCMAN DS2 device-bus protocol (rpc 0x8000131a et al.),
    // which is not yet emulated and stalls the config lookup. Until that path is implemented, the
    // pad HLE is opt-in via PS2X_SOCOM2_PAD so the default boot stays in the (renderable) shell
    // loop. When disabled these behave like the previous ret0 stubs (no controller).
    bool socom2PadEnabled()
    {
        static const bool on = (std::getenv("PS2X_SOCOM2_PAD") != nullptr);
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
        if (std::getenv("PS2X_SOCOM2_PAD_TRACE"))
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
            report[9 + field] = g_socom2Pad.button[kSocom2PressureButton[field]] ? 0xFFu : 0x00u;
        std::memcpy(rdram + buf, report, sizeof(report));
        // PS2X_SOCOM2_PAD_TRACE=1: log the first non-neutral reports the game reads.
        static const bool s_padTrace = std::getenv("PS2X_SOCOM2_PAD_TRACE") != nullptr;
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
            value = g_socom2Pad.button[kSocom2PressureButton[id - 0x14u]] ? 0xFFu : 0u;
        else
            value = 0u;
        // PS2X_SOCOM2_PAD_TRACE=1: which ids does the game poll, and what did it get for pressed ones?
        static const bool s_padTrace = std::getenv("PS2X_SOCOM2_PAD_TRACE") != nullptr;
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
        struct Table { uint32_t begin, end; const char *name; };
        const Table tables[] = {{0x00404d10u, 0x00404f04u, "FTSCore"}, {0x006690e0u, 0x00669120u, "ZSealEtc"}};
        std::vector<GuestInvocation> invocations;
        if (!runtime->hasFunction(kInitCppRts))
        {
            std::cout << "[socom2] __initialize_cpp_rts (0x182840) has no recompiled body!" << std::endl;
        }
        else
        {
            for (const Table &t : tables)
            {
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
        if (const char *env = std::getenv("PS2X_CD_IMAGE"); env && *env)
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
        const char *env = std::getenv("PS2X_PC_SAMPLER");
        if (!env || !*env)
            return;
        const int period = std::max(1, std::atoi(env));
        std::thread([&runtime, period]() {
            for (;;)
            {
                std::this_thread::sleep_for(std::chrono::seconds(period));
                const R5900Context *c = &runtime.cpu();
                std::ostringstream o;
                o << "[pc-sampler] live pc=0x" << std::hex << c->pc << " ra=0x" << GPR_U32(c, 31)
                  << " sp=0x" << GPR_U32(c, 29) << std::dec;
                const EeKernelSnapshot snap = runtime.eeScheduler().snapshot();
                o << " running=" << snap.runningThreadId << " threads:";
                for (const auto &t : snap.threads)
                    o << " [" << t.id << " pc=0x" << std::hex << t.pc << " ra=0x" << t.ra << " sp=0x" << t.sp << std::dec << " st=" << static_cast<int>(t.status)
                      << " wait=" << static_cast<int>(t.waitReason) << "/" << t.waitId << "]";
                std::cout << o.str() << std::endl;
                // PS2X_PEEK="0xADDR[:words][,...]": dump guest words (hex + float) with each sample.
                if (const char *peek = std::getenv("PS2X_PEEK"))
                {
                    std::string spec(peek);
                    size_t pos = 0;
                    std::ostringstream po;
                    po << "[peek]";
                    while (pos < spec.size())
                    {
                        size_t end = spec.find(',', pos);
                        if (end == std::string::npos)
                            end = spec.size();
                        std::string item = spec.substr(pos, end - pos);
                        pos = end + 1;
                        uint32_t words = 1;
                        const size_t colon = item.find(':');
                        if (colon != std::string::npos)
                        {
                            words = static_cast<uint32_t>(std::strtoul(item.c_str() + colon + 1, nullptr, 0));
                            item = item.substr(0, colon);
                        }
                        const uint32_t addr = static_cast<uint32_t>(std::strtoul(item.c_str(), nullptr, 0));
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
        const char *env = std::getenv("PS2X_RDRAM_DUMP_AT");
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
        const char *env = std::getenv("PS2X_RDRAM_DUMP");
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
            const char *e = std::getenv("PS2X_CALL_TRACE_EVERY");
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
        }
    }

    template <int... Is>
    constexpr std::array<PS2Runtime::RecompiledFunction, sizeof...(Is)> makeCallTraceThunks(std::integer_sequence<int, Is...>)
    {
        return {{&callTraceThunk<Is>...}};
    }

    void installCallTrace(PS2Runtime &runtime)
    {
        const char *env = std::getenv("PS2X_CALL_TRACE");
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

    void installCrashHandler(PS2Runtime &runtime)
    {
        g_runtimeForCrash = &runtime;
#ifdef _WIN32
        AddVectoredExceptionHandler(1, crashHandler);
#endif
    }

    void applySocom2(PS2Runtime &runtime)
    {
        std::cout << "[socom2] applying SOCOM II overrides" << std::endl;
        installCrashHandler(runtime);
        startPcSampler(runtime);
        startRdramDump(runtime);
        installCallTrace(runtime);
        {
            // sanity check that the FTSCore data segment is resident: should print the boot path string
            const uint8_t *p = getConstMemPtr(runtime.memory().getRDRAM(), 0x003e5c60u);
            std::string s;
            for (int i = 0; p && i < 24 && p[i]; ++i) s.push_back(static_cast<char>(p[i]));
            std::cout << "[socom2] mem@0x3e5c60 = \"" << s << "\"" << std::endl;
        }
        configureCdImage();
        runtime.replaceFunction(0x001c59c0u, socom2_LoadGameCodeFromDisc);
        runtime.replaceFunction(0x001c5b30u, socom2_LoadGameCodeFromMemcard);
        runtime.replaceFunction(0x00181c90u, socom2_LoadOverlayFile);
        runtime.replaceFunction(0x001a6110u, ps2_stubs::socom2_SifSendCmd); // sceSifSendCmd: sreg handshake echo
        // msifrpc (libnetb transport) answered on the host; see the "msifrpc HLE" section.
        runtime.replaceFunction(0x001bcd80u, ps2_stubs::socom2_MsifInit);
        runtime.replaceFunction(0x001bd050u, ps2_stubs::socom2_MsifBind);
        runtime.replaceFunction(0x001bd320u, ps2_stubs::socom2_MsifCall);
        runtime.replaceFunction(0x001bd200u, ps2_stubs::socom2_MsifUnbind);
        // libnetb_ex ring-buffer path -> host sockets (socom2_libnetb.cpp).
        runtime.replaceFunction(0x002472c8u, socom2_libnetb::exOpen);
        runtime.replaceFunction(0x002474f8u, socom2_libnetb::exTcpRecv);
        runtime.replaceFunction(0x00247738u, socom2_libnetb::exTcpSend);
        runtime.replaceFunction(0x00247d30u, socom2_libnetb::exUdpRecv);
        runtime.replaceFunction(0x00247fe8u, socom2_libnetb::exUdpSend);
        runtime.replaceFunction(0x002479b8u, socom2_libnetb::exAvailable);
        runtime.replaceFunction(0x00247bd8u, socom2_libnetb::exConnected);
        runtime.replaceFunction(0x00248350u, socom2_libnetb::exStartAsync);
        runtime.replaceFunction(0x002483f8u, socom2_libnetb::exStartAsync);
        ps2_game_overrides::bindAddressHandler(runtime, 0x00247c98u, "ret0");   // descriptor DMA helper
        // rt_crypt: RSA block transform and SHA-1 on the host (socom2_crypto.cpp).
        runtime.replaceFunction(0x0062b948u, socom2_crypto::rsaBlock);
        runtime.replaceFunction(0x0062eec0u, socom2_crypto::sha1Hash);
        runtime.replaceFunction(0x0062a638u, socom2_crypto::rc4SetKeyHash);
        runtime.replaceFunction(0x0062a5a8u, socom2_crypto::rc4SetKey);
        runtime.replaceFunction(0x0062a720u, socom2_crypto::rc4EncryptFn);
        runtime.replaceFunction(0x0062a7c8u, socom2_crypto::rc4DecryptFn);
        // DNAS authentication object (FTSCore FUN_002cc670): the published r0001 bypass patches
        // `jr ra` at its entry; a private Horizon server needs no DNAS.
        runtime.replaceFunction(0x002cc670u, ps2_stubs::socom2_DnasTickDone);
        // _InitSys kernel-patch search (FindAddress loop over the BIOS): nothing to find here.
        ps2_game_overrides::bindAddressHandler(runtime, 0x001ac9d8u, "ret0");
    }
}

PS2_REGISTER_GAME_OVERRIDE("socom2-us", "socom2_game.elf", 0x00180008u, 0u, applySocom2)
