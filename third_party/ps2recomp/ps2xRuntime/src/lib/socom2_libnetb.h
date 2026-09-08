// SOCOM II libnetb (SCE-RT network layer) HLE: answers the msifrpc service 0x80001201 and
// replaces the libnetb_ex ring-buffer path on the EE with direct host socket calls.
// Contract: docs/research/10-libnetb-rpc.md.
#pragma once
#include <cstdint>

struct R5900Context;
class PS2Runtime;

namespace socom2_libnetb
{
    // sceSifMCallRpc payload for service 0x80001201: dispatch by function number, fill recv.
    void call(uint8_t *rdram, uint32_t fno, uint32_t send, uint32_t sendSize, uint32_t recv, uint32_t recvSize);

    // EE function replacements (libnetb_ex path used by the SCE-RT platform layer).
    void exOpen(uint8_t *rdram, R5900Context *ctx, PS2Runtime *);        // FUN_002472c8
    void exTcpRecv(uint8_t *rdram, R5900Context *ctx, PS2Runtime *);     // FUN_002474f8
    void exTcpSend(uint8_t *rdram, R5900Context *ctx, PS2Runtime *);     // FUN_00247738
    void exUdpRecv(uint8_t *rdram, R5900Context *ctx, PS2Runtime *);     // FUN_00247d30
    void exUdpSend(uint8_t *rdram, R5900Context *ctx, PS2Runtime *);     // FUN_00247fe8
    void exAvailable(uint8_t *rdram, R5900Context *ctx, PS2Runtime *);   // FUN_002479b8
    void exConnected(uint8_t *rdram, R5900Context *ctx, PS2Runtime *);   // FUN_00247bd8
    void exStartAsync(uint8_t *rdram, R5900Context *ctx, PS2Runtime *);  // FUN_00248350 / FUN_002483f8
}
