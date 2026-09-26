// Sprint 13 Task C3 (audit F10): the rt_net config init, done on the host, with the peer UDP port already
// shifted when it returns.
//
// PS2X_SOCOM2_UDP_SHIFT exists for a second instance on one host: socom2_libnetb shifts the host bind, and the
// guest has to publish the same shifted port in its DME client record, which it takes from the config object
// the rt_net config init (r0001 FUN_00620648, r0004 0x00627f38) fills. research/18 has the whole story.
//
// THE TRAP THIS CLOSES. The first wrap called the original and rewrote the port field afterwards. The original
// calls two routines (memset, then a one-load getter) before it stores anything, and each call is a dispatch
// where the EE scheduler may take a checkpoint: the recompiled call chain unwinds, the wrap's "afterwards" runs
// at once -- before the store at 0x620680, with the field still the heap's old bytes (a checkpoint at the memset's
// dispatch comes before the memset runs) or the memset's zero, so the wrap saw "not 3658" and did nothing -- and the
// guest resumes inside the original later, never passing through the wrap again, and stores 3658. The shift was
// then lost with no line saying so. The on-screen keyboard's wrap met the same trap and settled the rule:
// nothing a wrap needs may be done after the original (socom2_osk_prefill.h, research/38).
//
// So the runtime no longer calls the original at all. The routine is 24 instructions with no branch the host
// cannot take itself: zero the 0x1c-byte object, store 1 at +0, the getter's word at +4, the base port at +0xc,
// return 0 (or 0x17 for a null object). configure() does exactly that, with the shifted port, and the override
// hands control back to the caller only after it has -- the write is inside the call, before the return. The
// getter is `lui v0,hi; jr ra; lw v0,lo(v0)`: one global, read here directly.
//
// Both revisions have the same instruction stream but for the getter's `jal` (r0001 0x0064f5f8 reading
// 0x00656340, r0004 0x0064db60 reading 0x00654e78; read out of both ELFs on 2026-09-25). The install checks the
// body word for word against kBody before it takes the routine over, and decodes the getter out of the image
// rather than out of a table, so neither revision's column grows and an image whose body differs keeps the
// original untouched and says so.
#pragma once

#include <cstddef>
#include <cstdint>
#include <cstring>

namespace socom2_rtnet
{
    constexpr uint32_t kBasePort = 3658u;             // the game's fixed peer UDP port (0xE4A)
    constexpr uint32_t kConfigBytes = 0x1Cu;          // the memset's length
    constexpr uint32_t kNullObjectResult = 0x17u;     // v0 when a0 is null
    constexpr std::size_t kBodyWords = 24u;
    constexpr std::size_t kGetterCallWord = 9u;       // the `jal <getter>` (entry + 0x24)

    // r0001 0x00620648..0x006206a8. Word 9 is the getter's jal, compared on its opcode only.
    inline constexpr uint32_t kBody[kBodyWords] = {
        0x27bdfff0u,   // addiu sp, sp, -0x10
        0x24020017u,   // addiu v0, zero, 0x17
        0xffb00000u,   // sd    s0, 0(sp)
        0x0080802du,   // daddu s0, a0, zero
        0x1200000fu,   // beqz  s0, +0xf (the null-object exit)
        0xffbf0008u,   // sd    ra, 8(sp)
        0x0000282du,   // daddu a1, zero, zero
        0x0c06566eu,   // jal   0x001959b8 (memset, in the loader: the same in every pressing)
        0x2406001cu,   // addiu a2, zero, 0x1c
        0x0c193d7eu,   // jal   <getter>   (r0001 0x0064f5f8)
        0x00000000u,   // nop
        0x24030001u,   // addiu v1, zero, 1
        0x24040e4au,   // addiu a0, zero, 0xe4a  (3658 -- the word the published pnach rewrites)
        0xae030000u,   // sw    v1, 0x0(s0)
        0xae04000cu,   // sw    a0, 0xc(s0)
        0xae000018u,   // sw    zero, 0x18(s0)
        0xae000008u,   // sw    zero, 0x8(s0)
        0xae000014u,   // sw    zero, 0x14(s0)
        0xae020004u,   // sw    v0, 0x4(s0)
        0x0000102du,   // daddu v0, zero, zero
        0xdfb00000u,   // ld    s0, 0(sp)
        0xdfbf0008u,   // ld    ra, 8(sp)
        0x03e00008u,   // jr    ra
        0x27bd0010u,   // addiu sp, sp, 0x10
    };

    // True when `words` (kBodyWords of them, read at the routine's address) is the routine configure() does.
    inline bool bodyMatches(const uint32_t *words)
    {
        if (words == nullptr)
            return false;
        for (std::size_t i = 0; i < kBodyWords; ++i)
        {
            if (i == kGetterCallWord)
            {
                if ((words[i] >> 26) != 3u)   // any jal
                    return false;
                continue;
            }
            if (words[i] != kBody[i])
                return false;
        }
        return true;
    }

    // The target of a `jal` at `pc`.
    inline uint32_t jalTarget(uint32_t insn, uint32_t pc)
    {
        return ((pc + 4u) & 0xF0000000u) | ((insn & 0x03FFFFFFu) << 2);
    }

    // The global the getter returns: `lui v0,hi; jr ra; lw v0,lo(v0)`. False for any other shape.
    inline bool getterGlobal(const uint32_t *getter, uint32_t &global)
    {
        if (getter == nullptr)
            return false;
        if ((getter[0] & 0xFFFF0000u) != 0x3C020000u || getter[1] != 0x03E00008u || (getter[2] & 0xFFFF0000u) != 0x8C420000u)
            return false;
        const int32_t lo = static_cast<int16_t>(getter[2] & 0xFFFFu);
        global = ((getter[0] & 0xFFFFu) << 16) + static_cast<uint32_t>(lo);
        return true;
    }

    inline uint32_t shiftedPort(int32_t shift)
    {
        return static_cast<uint32_t>(static_cast<int32_t>(kBasePort) + shift);
    }

    // The routine's whole effect on the object, with the port already shifted: the object's image is final when
    // this returns, and nothing is left to do after it. `object` is kConfigBytes of guest memory.
    inline void configure(uint8_t *object, uint32_t getterValue, uint32_t port)
    {
        std::memset(object, 0, kConfigBytes);          // memset(obj, 0, 0x1c)
        const uint32_t one = 1u;
        std::memcpy(object + 0x0, &one, 4);            // +0x0  1
        std::memcpy(object + 0x4, &getterValue, 4);    // +0x4  the getter's word
        std::memcpy(object + 0xC, &port, 4);           // +0xc  the base peer port (+0x8, +0x14, +0x18 stay 0)
    }
}
