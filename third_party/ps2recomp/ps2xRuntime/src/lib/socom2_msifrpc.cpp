// SOCOM II's msifrpc HLE: the libnetb EE library's multi-SIF RPC transport, answered on the host.
// Moved out of game_overrides_socom2.cpp by Sprint 13 Task C8 (audit F8) so ps2x_tests drives a bind, a call
// and an unbind through the real handlers (socom2_msifrpc_tests.cpp). Runner-only: applySocom2 binds the four
// entry points with replaceFunction (game_overrides_socom2.cpp).
#include "socom2_msifrpc.h"
#include "socom2_libnetb.h"
#include "ps2_runtime.h"
#include "ps2_runtime_macros.h"
#include "runtime/ps2_memory.h"
#include "ps2x/knobs.h"

#include <cstdint>
#include <cstring>
#include <iostream>

namespace ps2_stubs
{
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
    namespace
    {
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
        // rpcFromGuest returns to ra with v0 = 0, or parks this guest thread for a VBlank when a recv would wait
        // (#34, Sprint 13 V7).
        void socom2LibnetbCall(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
        {
            static const bool s_netTrace = ps2x::knob("PS2X_SOCOM2_NET_TRACE") != nullptr;   // was a getenv on every libnetb RPC
            if (s_netTrace)
                std::cout << "[socom2/msifrpc] libnetb fno=0x" << std::hex << GPR_U32(ctx, 5) << std::dec << " send=" << GPR_U32(ctx, 8)
                          << " recv=" << GPR_U32(ctx, 10) << std::endl;
            socom2_libnetb::rpcFromGuest(rdram, ctx, runtime);
        }
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

    void socom2_MsifCall(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint32_t client = GPR_U32(ctx, 4);
        const uint32_t fno = GPR_U32(ctx, 5);
        const uint32_t mode = GPR_U32(ctx, 6);
        // send, sendSize, recv, recvSize (a3, t0..t2) are read by socom2_libnetb::rpcFromGuest.
        int32_t result = -1;
        if (mode == 0u)
        {
            const uint32_t sid = rd32(rdram, client + 4u * 4u);
            if (sid == kLibnetbSid)
            {
                socom2LibnetbCall(rdram, ctx, runtime);   // sets v0 and pc itself (and may park: #34)
                return;
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
}
