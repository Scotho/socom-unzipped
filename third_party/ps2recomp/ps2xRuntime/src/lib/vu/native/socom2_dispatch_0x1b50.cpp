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

    // ---- VU instruction primitives --------------------------------------------------------
    //
    // One function per microcode op, with the same template parameters the generated code uses
    // (`Dest` is the VU dest field: bit 3 = x .. bit 0 = w), so the arithmetic is the interpreter's
    // own: vu1ops::fmacArith for the FMAC pipe, Vu1Gen::itof / ftoi / minmax for the conversions.
    //
    // The one deliberate difference from the generated code is timing: the FMAC flag registers and
    // Q commit here as soon as the op runs, instead of being queued for the interpreter's pipeline
    // model. The end-of-program values are identical either way (the interpreter flushes its
    // queues in issue order at the E bit), and the only family-A handler that reads a flag register
    // mid-stream is the backface cull's `FMAND vi13, vi5` at 0x1718, which reads its FMAC's flags
    // far enough downstream that immediate commit gives the same answer (see cmdBackfaceCull).
    // Keeping the scheduler out also means this file behaves the same whether the interpreter runs
    // its fast or its cycle-exact path.

    constexpr uint8_t kX = 0x8u, kY = 0x4u, kZ = 0x2u, kW = 0x1u;
    constexpr uint8_t kXY = kX | kY, kZW = kZ | kW, kXYZ = kX | kY | kZ, kXYZW = 0xFu;

    // FMAC flags as VU1Interpreter::fastCommit lands them: MAC is the newest op's lane flags,
    // STATUS keeps its sticky half (bits 6..11) and takes its current half (bits 0..3) from it.
    void commitFmacFlags(Ctx &c, const vu1ops::FmacResult &out)
    {
        c.vu.m_state.mac = out.mac;
        const uint32_t current = out.status & 0xFu;
        c.vu.m_state.status = (c.vu.m_state.status & 0xFF0u) | current | ((current | out.sticky) << 6);
    }

    // An arithmetic upper op (ADD/SUB/MUL/MADD/MSUB and their broadcast/I/Q forms). Mirrors
    // Vu1Gen::fmac; the result lanes are returned so the caller can store them after the pair's
    // lower op has run, which is how the VU resolves an upper/lower read-write pair.
    template <vu1ops::ArithKind Kind, Vu1Gen::FmacSrc Src, uint32_t Lane, uint8_t Dest,
              uint8_t Fs, uint8_t Ft, bool Opmul = false, bool NormS = true, bool NormT = true>
    __m128 fmac(Ctx &c)
    {
        float(*vf)[4] = c.vu.m_state.vf;
        __m128 first = _mm_loadu_ps(vf[Fs]);
        if (NormS)
            first = vu1ops::normalize4(first);
        __m128 second;
        if (Opmul)
        {
            __m128 vt = _mm_loadu_ps(vf[Ft]);
            if (NormT)
                vt = vu1ops::normalize4(vt);
            second = _mm_shuffle_ps(vt, vt, _MM_SHUFFLE(3, 1, 0, 2));
            first = _mm_shuffle_ps(first, first, _MM_SHUFFLE(3, 0, 2, 1));
        }
        else if (Src == Vu1Gen::SrcVt || Src == Vu1Gen::SrcBc)
        {
            __m128 vt = _mm_loadu_ps(vf[Ft]);
            if (NormT)
                vt = vu1ops::normalize4(vt);
            second = Src == Vu1Gen::SrcVt ? vt : vu1ops::broadcastLane(vt, Lane);
        }
        else if (Src == Vu1Gen::SrcQ)
            second = _mm_set1_ps(c.vu.m_state.q);
        else
            second = _mm_set1_ps(c.vu.m_state.i);

        vu1ops::FmacResult out;
        vu1ops::fmacArith<Kind, Opmul>(first, second, _mm_loadu_ps(c.vu.m_state.acc), Dest, out);
        if (Dest != 0u)
            commitFmacFlags(c, out);
        return out.value;
    }

    // Deferred ACC write of an upper op's result (MULA/MADDA/...).
    template <uint8_t Dest>
    void writeAcc(Ctx &c, __m128 value)
    {
        if (Dest != 0u)
            vu1ops::storeLanes(c.vu.m_state.acc, value, Dest);
    }

    // ITOF<n> / FTOI<n> / MINI / MAX / ABS: the non-arithmetic uppers, which push no flags.
    template <uint32_t Shift, uint8_t Fs>
    __m128 itof(Ctx &c) { return Vu1Gen::itof<Shift, Fs>(c.vu, c.vu.m_state.vf); }

    template <uint32_t Shift, uint8_t Fs>
    __m128 ftoi(Ctx &c) { return Vu1Gen::ftoi<Shift, Fs>(c.vu, c.vu.m_state.vf); }

    template <bool IsMax, Vu1Gen::MinMaxSrc Src, uint32_t Lane, uint8_t Fs, uint8_t Ft>
    __m128 minmax(Ctx &c) { return Vu1Gen::minmax<IsMax, Src, Lane, Fs, Ft>(c.vu, c.vu.m_state.vf); }

    // Deferred register write of an upper op's result (Vu1Gen::storeVf).
    template <uint8_t Reg, uint8_t Dest>
    void writeVf(Ctx &c, __m128 value)
    {
        if (Reg != 0u && Dest != 0u)
            vu1ops::storeLanes(c.vu.m_state.vf[Reg], value, Dest);
    }

    // LQ / SQ against VU data memory, addressed in qwords like the microcode.
    template <uint8_t Vf, uint8_t Dest>
    void loadQword(Ctx &c, int32_t qword)
    {
        if (Vf == 0u)
            return;
        float tmp[4];
        std::memcpy(tmp, c.qwordBytes(qword), 16);
        VU1Interpreter::applyDest(c.vu.m_state.vf[Vf], tmp, Dest);
    }

    template <uint8_t Vf, uint8_t Dest>
    void storeQword(Ctx &c, int32_t qword)
    {
        uint32_t words[4];
        std::memcpy(words, c.vu.m_state.vf[Vf], 16);
        uint32_t *dst = reinterpret_cast<uint32_t *>(c.qwordBytes(qword));
        if (Dest == kXYZW)
        {
            std::memcpy(dst, words, 16);
            return;
        }
        for (uint32_t component = 0; component < 4u; ++component)
            if ((Dest & (0x8u >> component)) != 0u)
                dst[component] = words[component];
    }

    // ISW: one 32-bit word of a qword, from a VI register.
    template <uint8_t Dest>
    void storeIntWord(Ctx &c, int32_t qword, int32_t value)
    {
        const uint32_t word = static_cast<uint32_t>(static_cast<uint16_t>(value & 0xFFFF));
        uint32_t *dst = reinterpret_cast<uint32_t *>(c.qwordBytes(qword));
        for (uint32_t component = 0; component < 4u; ++component)
            if ((Dest & (0x8u >> component)) != 0u)
                dst[component] = word;
    }

    // DIV Q, vfs<fsf>, vft<ftf> -- the FDIV unit (Vu1Gen::div), committed immediately.
    template <uint8_t Fs, uint32_t Fsf, uint8_t Ft, uint32_t Ftf>
    void divQ(Ctx &c)
    {
        float(*vf)[4] = c.vu.m_state.vf;
        const float num = VU1Interpreter::normalizeOperand(vf[Fs][Fsf]);
        const float den = VU1Interpreter::normalizeOperand(vf[Ft][Ftf]);
        uint32_t statusDi = 0u;
        float result;
        if (den == 0.0f)
        {
            statusDi = num == 0.0f ? 0x10u : 0x20u;
            result = std::signbit(num) != std::signbit(den) ? -vu1ops::kFltMax : vu1ops::kFltMax;
        }
        else
            result = num / den;
        uint32_t ignored = 0u;
        c.vu.m_state.q = c.vu.normalizeResult(result, ignored);
        // fastCommit's FDIV half: the D/I bits land in both the current (4,5) and sticky (10,11)
        // halves of STATUS.
        c.vu.m_state.status = (c.vu.m_state.status & 0xFCFu) | statusDi | (statusDi << 6);
    }

    // LOI: the pair's lower word is a float immediate in the I register.
    void loadImmediate(Ctx &c, uint32_t bits)
    {
        float value;
        std::memcpy(&value, &bits, sizeof(value));
        c.vu.m_state.i = VU1Interpreter::normalizeOperand(value);
    }

    // 16-bit wrap of the VI ALU.
    int32_t vi16(int32_t value) { return static_cast<int32_t>(static_cast<int16_t>(value)); }

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

    // ---- command 0x68 -> 0x0b20: int -> float vertex unpack --------------------------------
    //
    // Converts the raw vertex records in place: three qwords per vertex starting at TOP+4, two
    // vertices per loop iteration ("a" and "b"). Per vertex the conversion is
    //   record[0] -> (ITOF4(.xyz) + bias.xyz, ITOF15(.w))    position, 4 fractional bits
    //   record[1] -> (ITOF12(.xy), ITOF15(.zw))              texture coordinates + extras
    //   record[2] ->  ITOF0(.xyzw)                           colour, unscaled
    // with the bias taken from TOP+3 and the vertex count from TOP+2.z.
    //
    // The microcode is software-pipelined: an iteration stores the pair the previous iteration
    // converted while converting the next one, so on exit the register file holds the conversion
    // of one pair of records past the end of the array. That is reproduced here -- those registers
    // are part of the compared end-of-program state.
    namespace unpack
    {
        // The raw record qwords in flight, and the converted quads stored back over them.
        constexpr uint8_t kBias = 27;
        constexpr uint8_t kRawA0 = 20, kRawA1 = 30, kRawA2 = 19;
        constexpr uint8_t kRawB0 = 26, kRawB1 = 18, kRawB2 = 24;
        constexpr uint8_t kOutA0 = 21, kOutA1 = 31, kOutA2 = 22;
        constexpr uint8_t kOutB0 = 25, kOutB1 = 17, kOutB2 = 23;
        constexpr uint8_t kCursor = 3;    // vi3: the record cursor, in qwords
        constexpr uint8_t kRemaining = 9; // vi9: vertices left, decremented by two per iteration
    }

    bool cmdUnpackVertices(Ctx &c)
    {
        using namespace unpack;
        __m128 up;

        c.vi(kCursor) = vi16(c.vi(1) + 4);                   // 0x0b20
        c.vi(kRemaining) = c.loadWord(c.vi(1) + 2, 2);       // 0x0b28: TOP+2.z, the vertex count
        loadQword<kBias, kXYZW>(c, c.vi(1) + 3);             // 0x0b30: TOP+3, the position bias

        // 0x0b38-0x0b88: load the first pair of records and convert them.
        loadQword<kRawA0, kXYZW>(c, c.vi(kCursor) + 0);
        loadQword<kRawA1, kXYZW>(c, c.vi(kCursor) + 1);
        loadQword<kRawA2, kXYZW>(c, c.vi(kCursor) + 2);
        loadQword<kRawB0, kXYZW>(c, c.vi(kCursor) + 3);
        loadQword<kRawB1, kXYZW>(c, c.vi(kCursor) + 4);
        up = itof<4, kRawA0>(c);
        loadQword<kRawB2, kXYZW>(c, c.vi(kCursor) + 5);
        writeVf<kOutA0, kXYZ>(c, up);
        up = itof<15, kRawA1>(c); writeVf<kOutA1, kZW>(c, up);
        up = itof<0, kRawA2>(c);  writeVf<kOutA2, kXYZW>(c, up);
        up = itof<4, kRawB0>(c);  writeVf<kOutB0, kXYZ>(c, up);
        up = itof<15, kRawB1>(c); writeVf<kOutB1, kZW>(c, up);
        up = itof<0, kRawB2>(c);  writeVf<kOutB2, kXYZW>(c, up);

        // 0x0b90-0x0bc8: bias both positions, step the cursor, and prefetch the next pair's
        // record[0]/record[1] (its record[2] is fetched inside the loop).
        up = fmac<vu1ops::ArithAdd, Vu1Gen::SrcVt, 0, kXYZ, kOutA0, kBias, false, false, true>(c);
        writeVf<kOutA0, kXYZ>(c, up);
        up = fmac<vu1ops::ArithAdd, Vu1Gen::SrcVt, 0, kXYZ, kOutB0, kBias, false, false, true>(c);
        c.vi(kCursor) = vi16(c.vi(kCursor) + 6);
        writeVf<kOutB0, kXYZ>(c, up);
        up = itof<15, kRawB0>(c); writeVf<kOutB0, kW>(c, up);
        up = itof<12, kRawB1>(c); writeVf<kOutB1, kXY>(c, up);
        up = itof<15, kRawA0>(c);
        loadQword<kRawA0, kXYZW>(c, c.vi(kCursor) + 0);
        writeVf<kOutA0, kW>(c, up);
        up = itof<12, kRawA1>(c);
        loadQword<kRawA1, kXYZW>(c, c.vi(kCursor) + 1);
        writeVf<kOutA1, kXY>(c, up);
        loadQword<kRawB0, kXYZW>(c, c.vi(kCursor) + 3);
        loadQword<kRawB1, kXYZW>(c, c.vi(kCursor) + 4);

        for (;;)
        {
            c.vi(kRemaining) = vi16(c.vi(kRemaining) - 2);   // 0x0bd0

            // 0x0bd8-0x0be0: store vertex a's first two quads while converting the next pair's.
            up = itof<4, kRawA0>(c);
            storeQword<kOutA0, kXYZW>(c, c.vi(kCursor) - 6);
            writeVf<kOutA0, kXYZ>(c, up);
            up = itof<15, kRawA1>(c);
            storeQword<kOutA1, kXYZW>(c, c.vi(kCursor) - 5);
            writeVf<kOutA1, kZW>(c, up);

            // 0x0be8 `IBLTZ vi9, 0x1b60`, with vertex a's third quad in the delay slot: an odd
            // vertex count leaves here, having stored vertex a only.
            const bool oddVertexLeft = c.vi(kRemaining) < 0;
            storeQword<kOutA2, kXYZW>(c, c.vi(kCursor) - 4);
            if (oddVertexLeft)
                return true;

            // 0x0bf8-0x0c08: vertex b's three quads, and the next pair's positions biased.
            up = itof<4, kRawB0>(c);
            storeQword<kOutB0, kXYZW>(c, c.vi(kCursor) - 3);
            writeVf<kOutB0, kXYZ>(c, up);
            up = itof<15, kRawB1>(c);
            storeQword<kOutB1, kXYZW>(c, c.vi(kCursor) - 2);
            writeVf<kOutB1, kZW>(c, up);
            up = fmac<vu1ops::ArithAdd, Vu1Gen::SrcVt, 0, kXYZ, kOutA0, kBias, false, false, true>(c);
            storeQword<kOutB2, kXYZW>(c, c.vi(kCursor) - 1);
            writeVf<kOutA0, kXYZ>(c, up);

            // 0x0c10-0x0c48: step the cursor, then fetch and convert the pair after the one now
            // in flight.
            up = fmac<vu1ops::ArithAdd, Vu1Gen::SrcVt, 0, kXYZ, kOutB0, kBias, false, false, true>(c);
            c.vi(kCursor) = vi16(c.vi(kCursor) + 6);
            writeVf<kOutB0, kXYZ>(c, up);
            up = itof<15, kRawB0>(c);
            loadQword<kRawA2, kXYZW>(c, c.vi(kCursor) - 4);
            writeVf<kOutB0, kW>(c, up);
            up = itof<12, kRawB1>(c);
            loadQword<kRawB2, kXYZW>(c, c.vi(kCursor) - 1);
            writeVf<kOutB1, kXY>(c, up);
            up = itof<15, kRawA0>(c);
            loadQword<kRawA0, kXYZW>(c, c.vi(kCursor) + 0);
            writeVf<kOutA0, kW>(c, up);
            up = itof<12, kRawA1>(c);
            loadQword<kRawA1, kXYZW>(c, c.vi(kCursor) + 1);
            writeVf<kOutA1, kXY>(c, up);
            up = itof<0, kRawA2>(c);
            loadQword<kRawB0, kXYZW>(c, c.vi(kCursor) + 3);
            writeVf<kOutA2, kXYZW>(c, up);

            // 0x0c40 `IBGTZ vi9, 0x0bd0`, delay slot 0x0c48; falling through is 0x0c50 `B 0x1b60`.
            up = itof<0, kRawB2>(c);
            const bool more = c.vi(kRemaining) > 0;
            writeVf<kOutB2, kXYZW>(c, up);
            loadQword<kRawB1, kXYZW>(c, c.vi(kCursor) + 4);
            if (!more)
                return true;
        }
    }

    // ---- command 0x08 -> 0x0df8: transform by the clip matrix + perspective divide ---------
    //
    // Per vertex: clip = M(vf1..vf4) x position, Q = 1/clip.w, and the three staging quads
    //   +0 ST     = (uv * Q, clip.w)        perspective-correct texture coordinates
    //   +1 RGBAQ  = the source colour quad, copied through untouched
    //   +2 XYZF2  = clip.xyz * Q            screen position ( .w = 254, the fog default )
    // The source records are the three-qword ones command 0x68 converted, from TOP+4; the staging
    // array starts at qword 40, three qwords per vertex, in the GIFtag's REGS order.
    //
    // The microcode runs the transform two vertices ahead of the stores, with clip positions in a
    // two-deep delay line (vf27 -> vf28 -> vf29) and Q one vertex ahead of its use, so the loop
    // never waits on the divider. That schedule is kept here: it decides which vertex's values the
    // registers hold on exit, and it is what keeps the DIV/Q pairing unambiguous.
    namespace transform
    {
        constexpr uint8_t kSrcPos = 20;     // prefetched source position (two vertices ahead)
        constexpr uint8_t kSrcTex = 30;     // prefetched source texture coordinates (.xy; .z = 1)
        constexpr uint8_t kSrcColour = 24;  // source colour quad, passed through to RGBAQ
        constexpr uint8_t kClip = 27;       // clip-space position of the newest transform
        constexpr uint8_t kClipPrev = 28;   // ... one vertex behind
        constexpr uint8_t kClipCurr = 29;   // ... two vertices behind: the one being stored
        constexpr uint8_t kInvW = 17;       // 1/clip.w, broadcast over xyz
        constexpr uint8_t kScreen = 26;     // XYZF2: clip.xyz * 1/w, with .w = 254
        constexpr uint8_t kSt = 31;         // ST: uv * 1/w, with .w = clip.w
        constexpr uint8_t kSrcCursor = 3;   // vi3, in qwords (stride 3)
        constexpr uint8_t kStageCursor = 4; // vi4, in qwords (stride 3)
        constexpr uint8_t kRemaining = 9;   // vi9
    }

    bool cmdTransformDivide(Ctx &c)
    {
        using namespace transform;
        using vu1ops::ArithAdd;
        using vu1ops::ArithMadd;
        using vu1ops::ArithMul;
        __m128 up;

        c.vi(kSrcCursor) = vi16(c.vi(1) + 4);                  // 0x0df8
        c.vi(kStageCursor) = 40;                               // 0x0e00
        c.vi(kRemaining) = c.loadWord(c.vi(1) + 2, 2);         // 0x0e08: TOP+2.z, the vertex count
        loadQword<kSrcPos, kXYZW>(c, c.vi(kSrcCursor) + 0);    // 0x0e10
        loadQword<kSrcTex, kXY>(c, c.vi(kSrcCursor) + 1);      // 0x0e18

        // 0x0e20-0x0e38: vertex 0's clip position, ACC = vf1*x + vf2*y + vf3*z, then + vf4*1.
        up = fmac<ArithMul, Vu1Gen::SrcBc, 0, kXYZW, 1, kSrcPos>(c);  writeAcc<kXYZW>(c, up);
        up = fmac<ArithMadd, Vu1Gen::SrcBc, 1, kXYZW, 2, kSrcPos>(c);
        c.vi(kSrcCursor) = vi16(c.vi(kSrcCursor) + 3);
        writeAcc<kXYZW>(c, up);
        up = fmac<ArithMadd, Vu1Gen::SrcBc, 2, kXYZW, 3, kSrcPos>(c); writeAcc<kXYZW>(c, up);
        up = fmac<ArithMadd, Vu1Gen::SrcBc, 3, kXYZW, 4, 0, false, true, false>(c);
        loadQword<kSrcPos, kXYZW>(c, c.vi(kSrcCursor));
        writeVf<kClip, kXYZW>(c, up);

        // 0x0e40-0x0e48: the two constants the loop reuses -- the texture quad's third lane is 1,
        // and the screen quad's fog lane is 254.
        up = fmac<ArithAdd, Vu1Gen::SrcBc, 3, kZ, 0, 0, false, false, false>(c);
        loadImmediate(c, 0x437e0000u); // 254.0f
        writeVf<kSrcTex, kZ>(c, up);
        up = fmac<ArithAdd, Vu1Gen::SrcI, 0, kW, 0, 0, false, false, false>(c);
        writeVf<kScreen, kW>(c, up);

        // 0x0e58-0x0e98: start vertex 0's divide, transform vertex 1, and fill the delay line.
        up = fmac<ArithAdd, Vu1Gen::SrcBc, 0, kXYZW, kClip, 0, false, false, false>(c);
        divQ<0, 3, kClip, 3>(c);
        writeVf<kClipPrev, kXYZW>(c, up);
        up = fmac<ArithMul, Vu1Gen::SrcBc, 0, kXYZW, 1, kSrcPos>(c);  writeAcc<kXYZW>(c, up);
        up = fmac<ArithMadd, Vu1Gen::SrcBc, 1, kXYZW, 2, kSrcPos>(c);
        c.vi(kSrcCursor) = vi16(c.vi(kSrcCursor) + 3);
        writeAcc<kXYZW>(c, up);
        up = fmac<ArithMadd, Vu1Gen::SrcBc, 2, kXYZW, 3, kSrcPos>(c); writeAcc<kXYZW>(c, up);
        up = fmac<ArithMadd, Vu1Gen::SrcBc, 3, kXYZW, 4, 0, false, true, false>(c);
        loadQword<kSrcPos, kXYZW>(c, c.vi(kSrcCursor));
        writeVf<kClip, kXYZW>(c, up);
        up = fmac<ArithAdd, Vu1Gen::SrcBc, 0, kXYZW, kClipPrev, 0, false, false, false>(c);
        writeVf<kClipCurr, kXYZW>(c, up);
        up = fmac<ArithAdd, Vu1Gen::SrcQ, 0, kXYZ, 0, 0, false, false, false>(c);
        writeVf<kInvW, kXYZ>(c, up);
        up = fmac<ArithAdd, Vu1Gen::SrcBc, 0, kXYZW, kClip, 0, false, false, false>(c);
        writeVf<kClipPrev, kXYZW>(c, up);

        for (;;)
        {
            // 0x0ea0: the divide for the vertex one ahead of the one being stored.
            divQ<0, 3, kClip, 3>(c);

            // 0x0ea8-0x0eb8: build this vertex's ST and XYZF2 quads and fetch its colour.
            up = fmac<ArithMul, Vu1Gen::SrcBc, 3, kW, 0, kClipCurr, false, false, false>(c);
            loadQword<kSrcColour, kXYZW>(c, c.vi(kSrcCursor) - 4);
            writeVf<kSt, kW>(c, up);
            up = fmac<ArithMul, Vu1Gen::SrcVt, 0, kXYZ, kClipCurr, kInvW, false, false, true>(c);
            c.vi(kRemaining) = vi16(c.vi(kRemaining) - 1);
            writeVf<kScreen, kXYZ>(c, up);
            up = fmac<ArithMul, Vu1Gen::SrcBc, 0, kXYZ, kSrcTex, kInvW>(c);
            c.vi(kStageCursor) = vi16(c.vi(kStageCursor) + 3);
            writeVf<kSt, kXYZ>(c, up);

            // 0x0ec0-0x0ed8: transform the vertex two ahead while the stores of this one go out.
            up = fmac<ArithMul, Vu1Gen::SrcBc, 0, kXYZW, 1, kSrcPos>(c);
            loadQword<kSrcTex, kXY>(c, c.vi(kSrcCursor) - 2);
            writeAcc<kXYZW>(c, up);
            up = fmac<ArithMadd, Vu1Gen::SrcBc, 1, kXYZW, 2, kSrcPos>(c);
            c.vi(kSrcCursor) = vi16(c.vi(kSrcCursor) + 3);
            writeAcc<kXYZW>(c, up);
            up = fmac<ArithMadd, Vu1Gen::SrcBc, 2, kXYZW, 3, kSrcPos>(c);
            storeQword<kSrcColour, kXYZW>(c, c.vi(kStageCursor) - 2); // +1 RGBAQ
            writeAcc<kXYZW>(c, up);
            up = fmac<ArithMadd, Vu1Gen::SrcBc, 3, kXYZW, 4, 0, false, true, false>(c);
            loadQword<kSrcPos, kXYZW>(c, c.vi(kSrcCursor));
            writeVf<kClip, kXYZW>(c, up);

            // 0x0ee0-0x0ef0: pick up the new Q, shift the clip delay line, store the rest.
            up = fmac<ArithAdd, Vu1Gen::SrcQ, 0, kXYZ, 0, 0, false, false, false>(c);
            storeQword<kScreen, kXYZW>(c, c.vi(kStageCursor) - 1);    // +2 XYZF2
            writeVf<kInvW, kXYZ>(c, up);

            // 0x0ee8 `IBGTZ vi9, 0x0ea0`; 0x0ef0 is its delay slot and runs on both paths.
            up = fmac<ArithAdd, Vu1Gen::SrcBc, 0, kXYZW, kClipPrev, 0, false, true, false>(c);
            const bool more = c.vi(kRemaining) > 0;
            writeVf<kClipCurr, kXYZW>(c, up);
            up = fmac<ArithAdd, Vu1Gen::SrcBc, 0, kXYZW, kClip, 0, false, true, false>(c);
            storeQword<kSt, kXYZW>(c, c.vi(kStageCursor) - 3);        // +0 ST
            writeVf<kClipPrev, kXYZW>(c, up);
            if (!more)
                return true;                                          // 0x0ef8: B 0x1b60
        }
    }

    // Runs one command. Returns false when the command is not implemented yet: the caller then
    // hands back to the microcode at 0x1b60 with vi1/vi14 already set for this command's re-read.
    bool runCommand(Ctx &c, uint32_t command)
    {
        switch (command)
        {
        case kCmdUnpack:
            return cmdUnpackVertices(c);
        case kCmdTransform:
            return cmdTransformDivide(c);
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
