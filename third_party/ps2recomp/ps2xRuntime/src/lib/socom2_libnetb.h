// SOCOM II libnetb (SCE-RT network layer) HLE: answers the msifrpc service 0x80001201 and
// replaces the libnetb_ex ring-buffer path on the EE with direct host socket calls.
// Contract: docs/research/10-libnetb-rpc.md.
//
// Environment knobs answered here (one rule: unset or empty = default; "0"/"false"/"off" = off):
//   PS2X_SOCOM2_NET_TRACE        any value  enable the netcode trace (counters + peer hex)
//   PS2X_SOCOM2_NET_TRACE_PEERS  <n>        how many datagrams to hex-dump per direction (default 16)
//   PS2X_SOCOM2_NET_TRACE_ALL    default off  hex-dump EVERY datagram, not just ports < 10000
//   PS2X_SOCOM2_UDP_SHIFT        <n>        shift this instance's peer UDP ports by n
//   PS2X_SOCOM2_NET_STATS        default ON   sceInetInterfaceControl code 0x200 returns a real RX
//                                            byte count. Setting it to 0 restores the old constant
//                                            and REPRODUCES the online movement defect: the guest's
//                                            "ms since network activity" never resets, the
//                                            multiplayer movement scale decays to 0 and the local
//                                            player cannot move (docs/research/18 section 3.12).
//                                            Kept as an opt-out so the fix can be A/B'd on one
//                                            binary without a rebuild.
#pragma once
#include <cstdint>

struct R5900Context;
class PS2Runtime;

namespace socom2_libnetb
{
    // sceSifMCallRpc payload for service 0x80001201: dispatch by function number, fill recv.
    void call(uint8_t *rdram, uint32_t fno, uint32_t send, uint32_t sendSize, uint32_t recv, uint32_t recvSize);

    // Test only: forget the cached PS2X_SOCOM2_NET_STATS so the next call() re-reads the environment.
    void testResetKnobs();

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
