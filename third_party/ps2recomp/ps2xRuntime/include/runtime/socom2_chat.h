// socom2_chat.h -- the chat receive path's hardening.
// Sprint 11 milestone S (r0004 spec Goal A). The fields are fixed-width; this helper guarantees the terminator the
// game's readers assume. This helper is pure so the suite can prove it without the game.
#pragma once
#include <cstdint>

namespace socom2_chat
{
    constexpr uint32_t kFanoutRecvAddr = 0x002f4ef0u;   // the callback that receives a forwarded chat line
    constexpr uint32_t kNameOff = 0x1c, kNameLen = 32;   // originator name, fixed width
    constexpr uint32_t kTypeOff = 0x3c;                  // the chat type word the callback switches on
    constexpr uint32_t kMessageOff = 0x40, kMessageLen = 64;
    constexpr uint32_t kPacketBytes = 0x80;              // the span this helper may touch

    inline int terminateFields(uint8_t *pkt)
    {
        int changed = 0;
        auto fix = [&](uint32_t off, uint32_t len) {
            for (uint32_t i = 0; i < len; ++i)
                if (pkt[off + i] == 0) return;           // terminated within its width: leave it
            pkt[off + len - 1] = 0;
            ++changed;
        };
        fix(kNameOff, kNameLen);
        fix(kMessageOff, kMessageLen);
        return changed;
    }
}
