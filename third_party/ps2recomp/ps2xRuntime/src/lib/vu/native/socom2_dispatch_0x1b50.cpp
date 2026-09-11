// SOCOM II VU1 image d418194495c25213, entry pc 0x1b50: the command dispatcher and the handlers
// its "family A" (UI quad / 2D) command lists use.
//
// Structure, command encoding, register roles and the hand-back rules: docs/research/12-vu1-entry0-ui-path.md
// section (f). Sprint-1 contract: emit exactly the GIF packets the microcode emits and leave the
// register file and VU data memory exactly as the microcode leaves them
// (verified by `vu1_replay --verify --native`, --regs all).
//
// What runs natively: command lists whose linear decode from data qword 340 contains only the
// family-A command words and terminates on 0x42 (END). Every other list -- family B (world
// objects: 0x02/0x0a/0x12/0x1a/0x2a/0x4c and the 0x3618 subroutine) and family C (0x64/0x30/0x32)
// -- hands back WHOLE at 0x1b50 before this file touches any state, so the generated microcode
// translation runs it exactly as before. Family B is out of scope for Sprint 1: its 0x02/0x4c pair
// keeps vi12 (the primitive counter) live across the dispatcher back-edge, so it is not safe to
// hand back in the middle of such a list (research/12 f.3).
//
// Within a family-A list the handlers are mutually independent (each re-derives its pointers from
// vi1), so a command this file does not implement yet hands back at 0x1b60 -- the pc at which the
// microcode reads the next command word -- with vi1 and vi14 set as the microcode would have them.
#define private public
#include "../ps2_vu1_ops.h"
#undef private

#include <cstdint>
#include <cstring>

namespace
{
    // ---- dispatcher pcs -------------------------------------------------------------------
    // 0x1b50: XTOP vi1 / vi14 = 0.  0x1b60: ILW.x vi5, 340(vi14) -- the command read, and the only
    // legal mid-list hand-back point.  0x1b40: the E bit, which leaves pc = 0x1b50 behind.
    constexpr uint32_t kNextCommandPc = 0x1b60u;
    constexpr uint32_t kProgramEndPc = 0x1b50u;

    // ---- command list ---------------------------------------------------------------------
    constexpr int32_t kCommandListQword = 340;
    // The longest list in the corpus is 10 commands; a list that does not terminate inside this
    // many qwords is stale data, not a list this file may run.
    constexpr uint32_t kMaxCommands = 32u;

    enum Command : uint32_t
    {
        kCmdCull = 0x06u,          // 0x1638 backface cull
        kCmdTransform = 0x08u,     // 0x0df8 transform by the clip matrix + perspective divide
        kCmdFade = 0x10u,          // 0x0f90 per-vertex distance fade (the XYZF2 fog lane)
        kCmdLight = 0x18u,         // 0x1440 lighting
        kCmdBuildPacket = 0x28u,   // 0x1780 triangle assembly -> GIF packet -> XGKICK per triangle
        kCmdEnd = 0x42u,           // 0x1b40 E bit
        kCmdTemplateFill = 0x54u,  // 0x05d8 broadcast data qword 327 into every RGBAQ slot
        kCmdUnpack = 0x68u,        // 0x0b20 int->float vertex unpack
    };

    // The command words a family-A list is allowed to contain. A list built only from these is
    // linear: none of them rewrites vi14 (only 0x4c and 0x32 do), and every one of them ends with
    // `B 0x1b60`, so the static decode below is also the executed order.
    bool isFamilyACommand(uint32_t command)
    {
        switch (command)
        {
        case kCmdCull:
        case kCmdTransform:
        case kCmdFade:
        case kCmdLight:
        case kCmdBuildPacket:
        case kCmdEnd:
        case kCmdTemplateFill:
        case kCmdUnpack:
            return true;
        default:
            return false;
        }
    }

    // Execution context: VU data memory plus the handful of accessors the handlers need.
    struct Ctx
    {
        VU1Interpreter &vu;

        int32_t &vi(uint32_t r) { return vu.m_state.vi[r]; }
        float *vf(uint32_t r) { return vu.m_state.vf[r]; }
        // VU1 data memory is 16 KB and every access wraps inside it, exactly like the microcode's
        // address arithmetic (Vu1Gen::dataAddress).
        uint8_t *qwordBytes(int32_t qword) { return vu.m_activeVuData + Vu1Gen::dataAddress(qword); }
        // ILW <comp>: the low 16 bits of one word of a qword, sign-extended into a VI register.
        int32_t loadWord(int32_t qword, uint32_t component)
        {
            uint32_t value = 0u;
            std::memcpy(&value, qwordBytes(qword) + component * 4u, 4u);
            return static_cast<int32_t>(static_cast<int16_t>(value & 0xFFFFu));
        }
    };

    // The command word the dispatcher would read for list index `index` (ILW.x: the low 16 bits of
    // the x word), read without disturbing any register.
    uint32_t peekCommand(Ctx &c, uint32_t index)
    {
        uint32_t value = 0u;
        std::memcpy(&value, c.qwordBytes(kCommandListQword + static_cast<int32_t>(index)), 4u);
        return value & 0xFFFFu;
    }

    // True when the resident command list is one this file may run: family-A commands only, and a
    // literal 0x42 terminator within the bound. Called before anything is written, so a "no" is a
    // clean whole-program hand-back.
    bool isFamilyAList(Ctx &c)
    {
        for (uint32_t index = 0; index < kMaxCommands; ++index)
        {
            const uint32_t command = peekCommand(c, index);
            if (!isFamilyACommand(command))
                return false;
            if (command == kCmdEnd)
                return true;
        }
        return false;
    }

    // Runs one command. Returns false when the command is not implemented yet: the caller then
    // hands back to the microcode at 0x1b60 with vi1/vi14 already set for this command's re-read.
    bool runCommand(Ctx & /*c*/, uint32_t command)
    {
        switch (command)
        {
        default:
            return false;
        }
    }
}

// Registered for (image d418194495c25213, entry pc 0x1b50). Returns true when the program ended
// (the interpreter then runs its own end epilogue), false to hand back at vu.m_state.pc.
bool vu1native_socom2_dispatch(VU1Interpreter &vu, uint64_t /*budgetEnd*/)
{
    Ctx c{vu};
    if (!vu.m_activeVuData || vu.m_activeVuDataSize < 16u * 1024u || !isFamilyAList(c))
        return false; // whole-program hand-back: pc is still 0x1b50 and nothing has been touched

    // 0x1b50: XTOP vi1 -- the VIF double-buffered input base every handler derives its pointers
    // from. 0x1b58: the command index starts at 0.
    c.vi(1) = static_cast<int32_t>(vu.m_state.top & 0x3FFu);
    c.vi(14) = 0;

    for (;;)
    {
        // 0x1b60-0x1b90: read the command word, form the jump-table address, jump.
        //   vi5 = data[340 + vi14].x (low 16)   vi4 = 884 (= 0x1ba0 / 8, the jump table)
        //   vi14 += 1                           vi3 = vi5 + vi4 -> JR
        // The jump-table slot is a `B <handler>` pair, so handler pc = 0x1ba0 + 8 * command.
        const int32_t index = c.vi(14);
        const uint32_t command = static_cast<uint32_t>(c.loadWord(kCommandListQword + index, 0)) & 0xFFFFu;

        // The dispatcher's own register writes, in microcode order and before the handler runs.
        c.vi(5) = static_cast<int32_t>(static_cast<int16_t>(command));
        c.vi(4) = 884;
        c.vi(14) = static_cast<int32_t>(static_cast<int16_t>(index + 1));
        c.vi(3) = static_cast<int32_t>(static_cast<int16_t>(c.vi(5) + c.vi(4)));

        if (command == kCmdEnd)
        {
            // 0x1b40's E bit: one more pair, then the program ends leaving pc = 0x1b50.
            vu.m_viBranchBackupValid = false;
            vu.m_state.pc = kProgramEndPc;
            return true;
        }

        if (!runCommand(c, command))
        {
            // Not implemented: give the microcode the command back. vi14 has to name this command
            // again, because 0x1b60 re-reads and 0x1b70 re-increments it; vi3/vi4/vi5 are written
            // by 0x1b60-0x1b80 before any use, so their value here does not matter.
            c.vi(14) = index;
            vu.m_viBranchBackupValid = false;
            vu.m_state.pc = kNextCommandPc;
            return false;
        }
    }
}
