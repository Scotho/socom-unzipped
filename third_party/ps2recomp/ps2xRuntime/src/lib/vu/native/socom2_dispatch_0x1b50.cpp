// SOCOM II VU1 image d418194495c25213, entry pc 0x1b50: the command dispatcher and the handlers
// its "family A" (UI quad / 2D) command lists use.
//
// Structure, command encoding, register roles and the hand-back rules: docs/research/12-vu1-entry0-ui-path.md
// section (f). Sprint-1 contract: emit exactly the GIF packets the microcode emits and leave the
// register file and VU data memory exactly as the microcode leaves them
// (verified by `vu1_replay --verify --native`, --regs all).
//
// Sprint-2 addition: PS2X_VU1_HOST_DRAW=1 makes command 0x28 draw each assembled triangle through
// GS::submitHostTriangle instead of XGKICKing its packet (see submitHostTriangleFromPacket). The
// packet is still assembled byte for byte, so the contract above is unchanged with the knob on --
// only the kick is replaced. `vu1_replay --vram-diff` compares the two renderings pixel for pixel.
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
// vi1), so a command this file does not implement hands back at 0x1b60 -- the pc at which the
// microcode reads the next command word -- with vi1 and vi14 set as the microcode would have them.
// As of Sprint 1 all seven family-A commands are implemented, so that path is a safety net rather
// than a live one.
//
// Once a list is taken over it runs to its E bit: `budgetEnd` and `m_stopRequested` are ignored,
// because 0x1b60 is the only pc this program could legally stop at and stopping there buys
// nothing. That is only defensible while a list's work is bounded, and the counts that bound it
// (TOP+2.z vertices, TOP+2.w triangles) are guest data, not something the microcode validates -- a
// header with z = 32767 would mean ~11k template-fill iterations and up to 32767 uninterruptible
// XGKICKs. So the pre-scan checks them too, against a ceiling with plenty of margin over the
// corpus maxima (68 vertices, 44 triangles): see kMaxVertices / kMaxTriangles. A header outside
// that range hands the list back whole, exactly like a family-B one.
//
// The program also requires the interpreter's default XGKICK model, which copies the whole packet
// at kick time. Under PS2X_VU1_XGKICK_CYCLE_EXACT=1 a kick streams as m_cycle advances and a new
// kick clears whatever is still in flight; this program never advances m_cycle, so command 0x28's
// back-to-back per-triangle kicks would silently drop packets. That mode therefore hands back
// whole as well.
//
// A consequence of never advancing m_cycle: a natively-run list consumes zero VU cycles, so to
// DMAC/VIF timing VU1 appears to finish instantaneously, and the cycles/s field of [vu1-stats]
// under-reports by whatever those lists would have cost on the microcode path.
#define private public
#include "../ps2_vu1_ops.h"
#undef private

#include "runtime/gs/gs_frontend.h"

#include <atomic>
#include <cstdint>
#include <cstdlib>
#include <cstring>

// ps2_vu1_core.cpp: XGKICKs whose packet this build decoded (the [vu1-stats] counter). The
// generated translation increments it at its L_0x1920; so does this program's command 0x28.
extern std::atomic<uint64_t> g_xgkickDecoded;

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

    // ---- the family-A work ceiling ---------------------------------------------------------
    // Every family-A handler loops over TOP+2.z vertices or TOP+2.w triangles, both of them guest
    // data. The corpus maxima are 68 vertices and 44 triangles; these limits keep several times
    // that margin while still bounding a native run to a few thousand iterations and at most 256
    // XGKICKs, which is what makes ignoring budgetEnd and m_stopRequested defensible. A header
    // outside the range (including a negative count) hands the list back whole.
    constexpr int32_t kMaxVertices = 256;
    constexpr int32_t kMaxTriangles = 256;

    enum Command : uint32_t
    {
        kCmdCull = 0x06u,          // 0x1638 backface cull
        kCmdTransform = 0x08u,     // 0x0df8 transform by the clip matrix + perspective divide
        kCmdClippedTransform = 0x0au, // 0x0f08 family-B shim: XGKICK 423, then 0x08's kernel
        kCmdFade = 0x10u,          // 0x0f90 per-vertex distance fade (the XYZF2 fog lane)
        kCmdLight = 0x18u,         // 0x1440 lighting
        kCmdBuildPacket = 0x28u,   // 0x1780 triangle assembly -> GIF packet -> XGKICK per triangle
        kCmdEnd = 0x42u,           // 0x1b40 E bit
        kCmdTemplateFill = 0x54u,  // 0x05d8 broadcast data qword 327 into every RGBAQ slot
        kCmdClippedTemplateFill = 0x56u, // 0x0640 family-B shim: 0x54's fill on the 150 base
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
    // KEEP IN SYNC with the FMAC half of VU1Interpreter::fastCommit (ps2_vu1_core.cpp): this is a
    // deliberate copy of that bit arithmetic, not a call, because the native path commits without
    // going through the flag pipeline. The interpreter is frozen for Sprint 1, so the duplication
    // stays; if fastCommit's formula changes, this must change with it.
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

    // DIV Q, vfs<fsf>, vft<ftf> -- the FDIV unit, committed immediately instead of after the
    // seven-cycle latency. KEEP IN SYNC with Vu1Gen::div (ps2_vu1_ops.h) for the divide-by-zero
    // classification and the FLT_MAX saturation, and with the FDIV half of
    // VU1Interpreter::fastCommit for the STATUS D/I bits. Both are frozen for Sprint 1; this is a
    // deliberate copy rather than a call, because queueQ would never land without a cycle advance.
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

    // FMAND: an integer register masked with the MAC flag register.
    int32_t fmand(Ctx &c, int32_t mask)
    {
        return static_cast<int32_t>(c.vu.m_state.mac & static_cast<uint32_t>(static_cast<uint16_t>(mask)));
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

    // True when this run is one this file may take over: a command list of family-A commands only,
    // terminated by a literal 0x42 within the bound, and a header whose vertex and triangle counts
    // keep the work inside kMaxVertices / kMaxTriangles. Called before anything is written, so a
    // "no" is a clean whole-program hand-back.
    bool isFamilyARun(Ctx &c, int32_t top)
    {
        bool terminated = false;
        for (uint32_t index = 0; index < kMaxCommands && !terminated; ++index)
        {
            const uint32_t command = peekCommand(c, index);
            if (!isFamilyACommand(command))
                return false;
            terminated = command == kCmdEnd;
        }
        if (!terminated)
            return false;

        // The same two header words every family-A handler reads as its loop count.
        const int32_t vertices = c.loadWord(top + 2, 2);  // TOP+2.z
        const int32_t triangles = c.loadWord(top + 2, 3); // TOP+2.w
        return vertices >= 0 && vertices <= kMaxVertices && triangles >= 0 && triangles <= kMaxTriangles;
    }

    // The interpreter's XGKICK model, read the way ps2_vu1_core.cpp's startXgkick reads it: the
    // default copies the whole packet at kick time, PS2X_VU1_XGKICK_CYCLE_EXACT=1 streams it as
    // m_cycle advances. This program never advances m_cycle, so only the default is safe for
    // command 0x28's per-triangle kicks.
    bool xgkickIsImmediate()
    {
        static const bool immediate = std::getenv("PS2X_VU1_XGKICK_CYCLE_EXACT") == nullptr;
        return immediate;
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

    // 0x0e10 onward -- the loop proper, entered with vi3 = the source records, vi4 = the staging
    // base and vi9 = the vertex count already set. Command 0x08 sets them to TOP+4 / 40 / TOP+2.z;
    // command 0x0a (family B, 0x0f08) sets them to the clipped polygon / 150 / the clipped vertex
    // count and branches straight here. One kernel, two bases (research/13 4.5).
    bool transformDivideLoop(Ctx &c)
    {
        using namespace transform;
        using vu1ops::ArithAdd;
        using vu1ops::ArithMadd;
        using vu1ops::ArithMul;
        __m128 up;

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

    bool cmdTransformDivide(Ctx &c)
    {
        using namespace transform;
        c.vi(kSrcCursor) = vi16(c.vi(1) + 4);                  // 0x0df8
        c.vi(kStageCursor) = 40;                               // 0x0e00
        c.vi(kRemaining) = c.loadWord(c.vi(1) + 2, 2);         // 0x0e08: TOP+2.z, the vertex count
        return transformDivideLoop(c);
    }

    // ---- command 0x0a -> 0x0f08: flush tag, then 0x08's kernel on the clipped polygon --------
    //
    // Four instructions plus an XGKICK (research/13 4.5): kick the NLOOP=0/EOP=1 terminator tag at
    // data qword 423, then point 0x08's loop at the polygon the clipper left (vi8) and the
    // family-B staging array at 150, with the clipped vertex count (vi10) as the loop count.
    bool cmdClippedTransform(Ctx &c)
    {
        using namespace transform;

        c.vi(4) = 423;                                         // 0x0f08
        // 0x0f10: XGKICK vi4. Same model as command 0x28's kick -- the whole packet is copied at
        // kick time, which the entry check guarantees.
        g_xgkickDecoded.fetch_add(1, std::memory_order_relaxed);
        c.vu.startXgkick(static_cast<uint32_t>(static_cast<uint16_t>(c.vi(4))));
        c.vi(kSrcCursor) = vi16(c.vi(8));                      // 0x0f20: vi3 = vi8
        c.vi(kStageCursor) = 150;                              // 0x0f28
        c.vi(kRemaining) = vi16(c.vi(10));                     // 0x0f38: the B 0xe10 delay slot
        return transformDivideLoop(c);                         // 0x0f30
    }

    // ---- command 0x10 -> 0x0f90: per-vertex distance fade ----------------------------------
    //
    // Writes one lane and one lane only: the F (fog) field of each vertex's XYZF2 staging quad.
    // Per vertex, with the reference point at data qword 28 and the per-axis scale at qword 29:
    //   fog   = clamp((ST.w * scale.w) + reference.w, 0, 255)      ST.w is the clip w
    //   fade  = clamp(dot((position - reference).xyz * scale.xyz, (1,1,1)), 0, 1)
    //   XYZF2.w = fog * fade
    // Two vertices per iteration ("a" and "b"); an odd vertex count leaves after storing a only.
    //
    // The two loads of the XYZF2 quads themselves (vf24/vf25) are dead -- nothing reads them, the
    // fog lane is written with a masked SQ.w -- but they are kept because the register file they
    // leave behind is compared.
    namespace fade
    {
        constexpr uint8_t kRef = 17;   // data qword 28: reference point, .w = the fog offset
        constexpr uint8_t kScale = 18; // data qword 29: per-axis scale, .w = the fog scale
        constexpr uint8_t kPosA = 20, kPosB = 21;     // source positions (TOP+4 + 3k)
        constexpr uint8_t kStA = 30, kStB = 31;       // staging +0 (ST); only .w, the clip w, is used
        constexpr uint8_t kDeadA = 24, kDeadB = 25;   // staging +2 loaded and never read
        constexpr uint8_t kDeltaA = 22, kDeltaB = 23; // position - reference
        constexpr uint8_t kDistA = 26, kDistB = 27;   // scaled delta, then its .w = x + y + z
        constexpr uint8_t kFogA = 14, kFogB = 15;     // the fog value being built, in .w
        constexpr uint8_t kFadeA = 28, kFadeB = 29;   // the clamped distance factor, in .w
        constexpr uint8_t kSrcCursor = 3;             // vi3, stride 6 (two vertices)
        constexpr uint8_t kStageCursor = 4;           // vi4, stride 6
        constexpr uint8_t kRemaining = 9;             // vi9
    }

    bool cmdDistanceFade(Ctx &c)
    {
        using namespace fade;
        using vu1ops::ArithAdd;
        using vu1ops::ArithMadd;
        using vu1ops::ArithMul;
        using vu1ops::ArithSub;
        __m128 up;

        c.vi(kRemaining) = c.loadWord(c.vi(1) + 2, 2);           // 0x0f90: TOP+2.z, the vertex count
        c.vi(kSrcCursor) = vi16(c.vi(1) + 4);                    // 0x0f98
        c.vi(kStageCursor) = 40;                                 // 0x0fa0
        loadQword<kRef, kXYZW>(c, 28);                           // 0x0fa8
        loadQword<kScale, kXYZW>(c, 29);                         // 0x0fb0

        // 0x0fb8-0x1000: the first pair's inputs, and the two fog values started from the clip w
        // the transform left in the ST quads.
        loadQword<kPosA, kXYZW>(c, c.vi(kSrcCursor) + 0);
        loadQword<kPosB, kXYZW>(c, c.vi(kSrcCursor) + 3);
        loadQword<kDeadA, kXYZW>(c, c.vi(kStageCursor) + 2);
        loadQword<kDeadB, kXYZW>(c, c.vi(kStageCursor) + 5);
        loadQword<kStA, kXYZW>(c, c.vi(kStageCursor) + 0);
        loadQword<kStB, kXYZW>(c, c.vi(kStageCursor) + 3);
        up = fmac<ArithSub, Vu1Gen::SrcVt, 0, kXYZ, kPosA, kRef>(c);  writeVf<kDeltaA, kXYZ>(c, up);
        up = fmac<ArithSub, Vu1Gen::SrcVt, 0, kXYZ, kPosB, kRef>(c);  writeVf<kDeltaB, kXYZ>(c, up);
        up = fmac<ArithMul, Vu1Gen::SrcBc, 3, kW, kStA, kScale>(c);   writeVf<kFogA, kW>(c, up);
        up = fmac<ArithMul, Vu1Gen::SrcBc, 3, kW, kStB, kScale>(c);   writeVf<kFogB, kW>(c, up);

        for (;;)
        {
            // 0x1008-0x1020: scale the deltas, finish the fog bases, prefetch the next positions.
            up = fmac<ArithMul, Vu1Gen::SrcVt, 0, kXYZ, kDeltaA, kScale, false, false, true>(c);
            c.vi(kSrcCursor) = vi16(c.vi(kSrcCursor) + 6);
            writeVf<kDistA, kXYZ>(c, up);
            up = fmac<ArithMul, Vu1Gen::SrcVt, 0, kXYZ, kDeltaB, kScale, false, false, true>(c);
            c.vi(kStageCursor) = vi16(c.vi(kStageCursor) + 6);
            writeVf<kDistB, kXYZ>(c, up);
            up = fmac<ArithAdd, Vu1Gen::SrcBc, 3, kW, kFogA, kRef, false, false, true>(c);
            loadQword<kPosA, kXYZW>(c, c.vi(kSrcCursor) + 0);
            writeVf<kFogA, kW>(c, up);
            up = fmac<ArithAdd, Vu1Gen::SrcBc, 3, kW, kFogB, kRef, false, false, true>(c);
            loadQword<kPosB, kXYZW>(c, c.vi(kSrcCursor) + 3);
            writeVf<kFogB, kW>(c, up);

            // 0x1028-0x1038: vertex a's distance = x + y + z of the scaled delta, in .w.
            up = fmac<ArithMul, Vu1Gen::SrcBc, 0, kW, 0, kDistA, false, false, false>(c);
            writeAcc<kW>(c, up);
            up = fmac<ArithMadd, Vu1Gen::SrcBc, 1, kW, 0, kDistA, false, false, false>(c);
            writeAcc<kW>(c, up);
            up = fmac<ArithMadd, Vu1Gen::SrcBc, 2, kW, 0, kDistA, false, false, false>(c);
            writeVf<kDistA, kW>(c, up);
            loadImmediate(c, 0x437f0000u); // 255.0f

            // 0x1040-0x1060: clamp both fog values to 255, then vertex b's distance.
            up = minmax<false, Vu1Gen::MmI, 0, kFogA, 0>(c);
            loadQword<kDeadA, kXYZW>(c, c.vi(kStageCursor) + 2);
            writeVf<kFogA, kW>(c, up);
            up = minmax<false, Vu1Gen::MmI, 0, kFogB, 0>(c);
            loadQword<kDeadB, kXYZW>(c, c.vi(kStageCursor) + 5);
            writeVf<kFogB, kW>(c, up);
            up = fmac<ArithMul, Vu1Gen::SrcBc, 0, kW, 0, kDistB, false, false, false>(c);
            loadQword<kStA, kXYZW>(c, c.vi(kStageCursor) + 0);
            writeAcc<kW>(c, up);
            up = fmac<ArithMadd, Vu1Gen::SrcBc, 1, kW, 0, kDistB, false, false, false>(c);
            loadQword<kStB, kXYZW>(c, c.vi(kStageCursor) + 3);
            writeAcc<kW>(c, up);
            up = fmac<ArithMadd, Vu1Gen::SrcBc, 2, kW, 0, kDistB, false, false, false>(c);
            writeVf<kDistB, kW>(c, up);
            loadImmediate(c, 0x3f800000u); // 1.0f

            // 0x1068-0x1090: clamp the distances to [0,1] and the fog values to >= 0.
            up = minmax<false, Vu1Gen::MmI, 0, kDistA, 0>(c);          writeVf<kDistA, kW>(c, up);
            up = minmax<true, Vu1Gen::MmBc, 0, kFogA, 0>(c);           writeVf<kFogA, kW>(c, up);
            up = minmax<true, Vu1Gen::MmBc, 0, kFogB, 0>(c);           writeVf<kFogB, kW>(c, up);
            up = minmax<false, Vu1Gen::MmI, 0, kDistB, 0>(c);          writeVf<kDistB, kW>(c, up);
            up = minmax<true, Vu1Gen::MmBc, 0, kDistA, 0>(c);          writeVf<kFadeA, kW>(c, up);
            up = minmax<true, Vu1Gen::MmBc, 0, kDistB, 0>(c);          writeVf<kFadeB, kW>(c, up);

            // 0x1098-0x10b0: start the next pair's deltas, then fog *= fade.
            up = fmac<ArithSub, Vu1Gen::SrcVt, 0, kXYZ, kPosA, kRef>(c);  writeVf<kDeltaA, kXYZ>(c, up);
            up = fmac<ArithSub, Vu1Gen::SrcVt, 0, kXYZ, kPosB, kRef>(c);
            c.vi(kRemaining) = vi16(c.vi(kRemaining) - 2);
            writeVf<kDeltaB, kXYZ>(c, up);
            up = fmac<ArithMul, Vu1Gen::SrcBc, 3, kW, kFogA, kFadeA, false, false, false>(c);
            writeVf<kFogA, kW>(c, up);
            up = fmac<ArithMul, Vu1Gen::SrcBc, 3, kW, kFogB, kFadeB, false, false, false>(c);
            writeVf<kFogB, kW>(c, up);

            // 0x10c8-0x10d0: vertex a's fog lane; an odd vertex count leaves here.
            storeQword<kFogA, kW>(c, c.vi(kStageCursor) - 4);
            if (c.vi(kRemaining) < 0)
                return true;

            // 0x10e0-0x10f0: vertex b's fog lane, then the next pair's fog bases (0x10f0 is the
            // branch's delay slot and runs on both paths).
            storeQword<kFogB, kW>(c, c.vi(kStageCursor) - 1);
            up = fmac<ArithMul, Vu1Gen::SrcBc, 3, kW, kStA, kScale>(c);
            const bool more = c.vi(kRemaining) > 0;
            writeVf<kFogA, kW>(c, up);
            up = fmac<ArithMul, Vu1Gen::SrcBc, 3, kW, kStB, kScale>(c);
            writeVf<kFogB, kW>(c, up);
            if (!more)
                return true;                                           // 0x10f8: B 0x1b60
        }
    }

    // ---- command 0x54 -> 0x05d8: template fill ---------------------------------------------
    //
    // Broadcasts data qword 327 (the list's RGBAQ template, which entry 0 copied from TOP+12) into
    // the +1 slot of every vertex's staging triple, three vertices per iteration from base 40. The
    // loop overshoots to the next multiple of three -- for 68 vertices it writes the slot of
    // vertices 68 and 69 as well, i.e. up to qword 245 -- which is reproduced here because the
    // extra qwords are part of the compared data memory.
    namespace fill
    {
        constexpr uint8_t kTemplate = 28;
        constexpr uint8_t kStageCursor = 4; // vi4, three vertices (9 qwords) per iteration
        constexpr uint8_t kRemaining = 9;   // vi9
    }

    // 0x05e8 onward -- the loop proper, entered with vi4 = the staging base and vi9 = the vertex
    // count already set. Command 0x54 sets them to 40 / TOP+2.z; command 0x56 (family B, 0x0640)
    // to 150 / vi10, the clipped vertex count (research/13 4.5).
    bool templateFillLoop(Ctx &c)
    {
        using namespace fill;

        loadQword<kTemplate, kXYZW>(c, 327);                     // 0x05e8

        for (;;)
        {
            c.vi(kRemaining) = vi16(c.vi(kRemaining) - 3);       // 0x0600
            storeQword<kTemplate, kXYZW>(c, c.vi(kStageCursor) + 1);
            storeQword<kTemplate, kXYZW>(c, c.vi(kStageCursor) + 4);
            storeQword<kTemplate, kXYZW>(c, c.vi(kStageCursor) + 7);
            // 0x0620 `IBGTZ vi9, 0x0600`, with the cursor step in its delay slot.
            const bool more = c.vi(kRemaining) > 0;
            c.vi(kStageCursor) = vi16(c.vi(kStageCursor) + 9);
            if (!more)
                return true;                                     // 0x0630: B 0x1b60
        }
    }

    bool cmdTemplateFill(Ctx &c)
    {
        using namespace fill;
        c.vi(kStageCursor) = 40;                                 // 0x05d8
        c.vi(kRemaining) = c.loadWord(c.vi(1) + 2, 2);           // 0x05e0: TOP+2.z
        return templateFillLoop(c);
    }

    // ---- command 0x56 -> 0x0640: 0x54's fill over the family-B staging array ----------------
    //
    // Three instructions (research/13 4.5). The loop still overshoots to the next multiple of
    // three, which on the 150 base lands inside the array's headroom (150 + 3*12 = 186).
    bool cmdClippedTemplateFill(Ctx &c)
    {
        using namespace fill;
        c.vi(kStageCursor) = 150;                                // 0x0640
        c.vi(kRemaining) = vi16(c.vi(10));                       // 0x0650: the B 0x5e8 delay slot
        return templateFillLoop(c);                              // 0x0648
    }

    // ---- command 0x18 -> 0x1440: lighting --------------------------------------------------
    //
    // Modulates every vertex's RGBAQ staging quad by a lit colour. The per-list light parameters
    // are data qword 27; the matrices are the two entry 0 leaves live in the register file: the
    // normal/light matrix in vf5-vf7 and the colour block in vf9-vf12.
    //
    // Once per command:
    //   light[0..2] = vf9/vf10/vf11 * params.y,  light[3] = vf12 * params.z
    // then per vertex, from the record's qwords 0 and 1 (position and texture quads):
    //   normal  = max(vf5 * record0.w + vf6 * record1.z + vf7 * record1.w, 0) on xyz
    //   lit     = light[0]*normal.x + light[1]*normal.y + light[2]*normal.z + light[3] (xyz),
    //             with the w lane taken from the staging RGBAQ quad instead
    //   staging +1 = record2 * lit
    // Two vertices per iteration, and the loop runs the next pair's normals before storing this
    // pair's colours.
    namespace lighting
    {
        constexpr uint8_t kParams = 31;                 // data qword 27
        constexpr uint8_t kLight0 = 13, kLight1 = 14, kLight2 = 15, kLight3 = 16;
        constexpr uint8_t kPosA = 20, kTexA = 21;       // source record qwords 0 and 1, vertex a
        constexpr uint8_t kPosB = 22, kTexB = 23;       // ... vertex b
        constexpr uint8_t kNormalA = 29, kNormalB = 30; // clamped to >= 0 on xyz
        constexpr uint8_t kRgbaA = 17, kRgbaB = 28;     // the staging +1 quads being modulated
        constexpr uint8_t kSrcColourA = 18, kSrcColourB = 19; // the record's qword 2
        constexpr uint8_t kLitA = 24, kLitB = 25;
        constexpr uint8_t kOutA = 26, kOutB = 27;
        constexpr uint8_t kSrcCursor = 3; // vi3, stride 6
        constexpr uint8_t kStageCursor = 4; // vi4, stride 6
        constexpr uint8_t kRemaining = 9; // vi9
    }

    bool cmdLighting(Ctx &c)
    {
        using namespace lighting;
        using vu1ops::ArithMadd;
        using vu1ops::ArithMul;
        __m128 up;

        loadQword<kParams, kXYZW>(c, 27);                        // 0x1440
        c.vi(kSrcCursor) = vi16(c.vi(1) + 4);                    // 0x1448
        c.vi(kStageCursor) = 40;                                 // 0x1450
        c.vi(kRemaining) = c.loadWord(c.vi(1) + 2, 2);           // 0x1458: TOP+2.z

        // 0x1460-0x1478: scale the colour block into this list's light matrix, and load the first
        // pair of source records.
        up = fmac<ArithMul, Vu1Gen::SrcBc, 1, kXYZW, 9, kParams>(c);
        loadQword<kPosA, kXYZW>(c, c.vi(kSrcCursor) + 0);
        writeVf<kLight0, kXYZW>(c, up);
        up = fmac<ArithMul, Vu1Gen::SrcBc, 1, kXYZW, 10, kParams>(c);
        loadQword<kTexA, kXYZW>(c, c.vi(kSrcCursor) + 1);
        writeVf<kLight1, kXYZW>(c, up);
        up = fmac<ArithMul, Vu1Gen::SrcBc, 1, kXYZW, 11, kParams>(c);
        loadQword<kPosB, kXYZW>(c, c.vi(kSrcCursor) + 3);
        writeVf<kLight2, kXYZW>(c, up);
        up = fmac<ArithMul, Vu1Gen::SrcBc, 2, kXYZW, 12, kParams>(c);
        loadQword<kTexB, kXYZW>(c, c.vi(kSrcCursor) + 4);
        writeVf<kLight3, kXYZW>(c, up);

        // 0x1480-0x14c8: the first pair's normals, clamped to >= 0.
        up = fmac<ArithMul, Vu1Gen::SrcBc, 3, kXYZW, 5, kPosA>(c);   writeAcc<kXYZW>(c, up);
        up = fmac<ArithMadd, Vu1Gen::SrcBc, 2, kXYZW, 6, kTexA>(c);  writeAcc<kXYZW>(c, up);
        up = fmac<ArithMadd, Vu1Gen::SrcBc, 3, kXYZW, 7, kTexA>(c);  writeVf<kNormalA, kXYZW>(c, up);
        up = fmac<ArithMul, Vu1Gen::SrcBc, 3, kXYZW, 5, kPosB>(c);   writeAcc<kXYZW>(c, up);
        up = fmac<ArithMadd, Vu1Gen::SrcBc, 2, kXYZW, 6, kTexB>(c);  writeAcc<kXYZW>(c, up);
        up = fmac<ArithMadd, Vu1Gen::SrcBc, 3, kXYZW, 7, kTexB>(c);  writeVf<kNormalB, kXYZW>(c, up);
        c.vi(kSrcCursor) = vi16(c.vi(kSrcCursor) + 6);
        c.vi(kStageCursor) = vi16(c.vi(kStageCursor) + 6);
        up = minmax<true, Vu1Gen::MmBc, 0, kNormalA, 0>(c);          writeVf<kNormalA, kXYZ>(c, up);
        up = minmax<true, Vu1Gen::MmBc, 0, kNormalB, 0>(c);          writeVf<kNormalB, kXYZ>(c, up);

        for (;;)
        {
            // 0x14d0-0x1510: vertex a -- light the normal, keep the staging quad's own w, and
            // modulate the record's colour by the result.
            loadQword<kRgbaA, kXYZW>(c, c.vi(kStageCursor) - 5);
            loadQword<kRgbaB, kXYZW>(c, c.vi(kStageCursor) - 2);
            up = fmac<ArithMul, Vu1Gen::SrcBc, 0, kXYZW, kLight0, kNormalA, false, true, false>(c);
            c.vi(kRemaining) = vi16(c.vi(kRemaining) - 2);
            writeAcc<kXYZW>(c, up);
            up = fmac<ArithMadd, Vu1Gen::SrcBc, 1, kXYZW, kLight1, kNormalA, false, true, false>(c);
            loadQword<kSrcColourA, kXYZW>(c, c.vi(kSrcCursor) - 4);
            writeAcc<kXYZW>(c, up);
            up = fmac<ArithMadd, Vu1Gen::SrcBc, 2, kXYZW, kLight2, kNormalA, false, true, false>(c);
            loadQword<kSrcColourB, kXYZW>(c, c.vi(kSrcCursor) - 1);
            writeAcc<kXYZW>(c, up);
            up = fmac<ArithMadd, Vu1Gen::SrcBc, 3, kXYZ, kLight3, 0, false, true, false>(c);
            loadQword<kPosA, kXYZW>(c, c.vi(kSrcCursor) + 0);
            writeAcc<kXYZ>(c, up);
            up = fmac<ArithMul, Vu1Gen::SrcBc, 0, kW, 0, 0, false, false, false>(c);
            loadQword<kTexA, kXYZW>(c, c.vi(kSrcCursor) + 1);
            writeAcc<kW>(c, up);
            up = fmac<ArithMadd, Vu1Gen::SrcBc, 3, kXYZW, kRgbaA, 0, false, true, false>(c);
            loadQword<kPosB, kXYZW>(c, c.vi(kSrcCursor) + 3);
            writeVf<kLitA, kXYZW>(c, up);
            up = fmac<ArithMul, Vu1Gen::SrcVt, 0, kXYZW, kSrcColourA, kLitA, false, true, false>(c);
            loadQword<kTexB, kXYZW>(c, c.vi(kSrcCursor) + 4);
            writeVf<kOutA, kXYZW>(c, up);

            // 0x1518-0x1548: vertex b, the same way.
            up = fmac<ArithMul, Vu1Gen::SrcBc, 0, kXYZW, kLight0, kNormalB, false, true, false>(c);
            writeAcc<kXYZW>(c, up);
            up = fmac<ArithMadd, Vu1Gen::SrcBc, 1, kXYZW, kLight1, kNormalB, false, true, false>(c);
            writeAcc<kXYZW>(c, up);
            up = fmac<ArithMadd, Vu1Gen::SrcBc, 2, kXYZW, kLight2, kNormalB, false, true, false>(c);
            c.vi(kSrcCursor) = vi16(c.vi(kSrcCursor) + 6);
            writeAcc<kXYZW>(c, up);
            up = fmac<ArithMadd, Vu1Gen::SrcBc, 3, kXYZ, kLight3, 0, false, true, false>(c);
            c.vi(kStageCursor) = vi16(c.vi(kStageCursor) + 6);
            writeAcc<kXYZ>(c, up);
            up = fmac<ArithMul, Vu1Gen::SrcBc, 0, kW, 0, 0, false, false, false>(c);
            writeAcc<kW>(c, up);
            up = fmac<ArithMadd, Vu1Gen::SrcBc, 3, kXYZW, kRgbaB, 0, false, true, false>(c);
            writeVf<kLitB, kXYZW>(c, up);
            up = fmac<ArithMul, Vu1Gen::SrcVt, 0, kXYZW, kSrcColourB, kLitB, false, true, false>(c);
            writeVf<kOutB, kXYZW>(c, up);

            // 0x1550-0x1578: the next pair's normals, before this pair's colours are stored.
            up = fmac<ArithMul, Vu1Gen::SrcBc, 3, kXYZW, 5, kPosA>(c);   writeAcc<kXYZW>(c, up);
            up = fmac<ArithMadd, Vu1Gen::SrcBc, 2, kXYZW, 6, kTexA>(c);  writeAcc<kXYZW>(c, up);
            up = fmac<ArithMadd, Vu1Gen::SrcBc, 3, kXYZW, 7, kTexA>(c);  writeVf<kNormalA, kXYZW>(c, up);
            up = fmac<ArithMul, Vu1Gen::SrcBc, 3, kXYZW, 5, kPosB>(c);   writeAcc<kXYZW>(c, up);
            up = fmac<ArithMadd, Vu1Gen::SrcBc, 2, kXYZW, 6, kTexB>(c);  writeAcc<kXYZW>(c, up);
            up = fmac<ArithMadd, Vu1Gen::SrcBc, 3, kXYZW, 7, kTexB>(c);  writeVf<kNormalB, kXYZW>(c, up);

            // 0x1580-0x1598: store both colours and clamp the new normals (0x1598 is the branch's
            // delay slot and runs on both paths).
            storeQword<kOutA, kXYZW>(c, c.vi(kStageCursor) - 11);
            storeQword<kOutB, kXYZW>(c, c.vi(kStageCursor) - 8);
            up = minmax<true, Vu1Gen::MmBc, 0, kNormalA, 0>(c);
            const bool more = c.vi(kRemaining) > 0;
            writeVf<kNormalA, kXYZ>(c, up);
            up = minmax<true, Vu1Gen::MmBc, 0, kNormalB, 0>(c);
            writeVf<kNormalB, kXYZ>(c, up);
            if (!more)
                return true;                                            // 0x15a0: B 0x1b60
        }
    }

    // ---- command 0x28 -> 0x1780: triangle assembly, GIF packet, XGKICK ---------------------
    //
    // Walks the triangle index list at TOP + TOP+2.x and emits one ten-qword GIF packet per
    // surviving triangle: the list's GIFtag from TOP+1 with NLOOP patched to 3 and EOP set,
    // followed by three vertices of (ST, RGBAQ, XYZF2) taken from the staging array. RGBAQ goes
    // through MADD by the rounding bias at data qword 38 (whose .w comes from the RGBAQ template
    // at 327) and FTOI0; XYZF2 through FTOI4; ST is copied as is.
    //
    // Two gates per triangle, both from the index qword's w word: bit 0 (set by the backface cull)
    // and bit 1, the latter OR-ed with data qword 39.w so a list can force everything through.
    //
    // The two packet buffers at 290 and 300 ping-pong -- their bases live in data qword 329.x/.y
    // and are swapped per triangle and written back at the end -- so the GS can still be reading
    // one while the next is being built. One XGKICK per triangle.
    namespace packet
    {
        constexpr uint8_t kBias = 20;      // data qword 38; .w replaced from qword 327
        constexpr uint8_t kGifTag = 19;    // the GIFtag template from TOP+1 (vf19 before the loop)
        constexpr uint8_t kSt0 = 17, kSt1 = 26, kSt2 = 29;
        constexpr uint8_t kRgba0 = 18, kRgba1 = 27, kRgba2 = 30;
        constexpr uint8_t kXyz0 = 19, kXyz1 = 28, kXyz2 = 31; // vf19 again, once the tag is stored
        constexpr uint8_t kIndexCursor = 4;  // vi4, two qwords per triangle
        constexpr uint8_t kTriangles = 13;   // vi13
        constexpr uint8_t kPacket = 2;       // vi2: the buffer being built and kicked
        constexpr uint8_t kOtherPacket = 8;  // vi8: the one the GS may still be reading
        constexpr uint8_t kVertex0 = 5, kVertex1 = 6, kVertex2 = 7; // staging qword offsets
        constexpr uint8_t kFlags = 12, kGate = 3, kForce = 9, kScratch = 11;
    }

    // ---- PS2X_VU1_HOST_DRAW=1: draw the assembled triangle instead of kicking it ------------
    //
    // The packet is still built qword for qword -- every data-memory write, the ping-pong swap and
    // vi2/vi8 happen exactly as before, so the goldens stay green with the knob on -- but instead
    // of XGKICKing it, the ten qwords are decoded the way GS::writeRegisterPacked decodes them and
    // handed to GS::submitHostTriangle. The one thing the hook does NOT take from the packet is
    // the screen position: it gets the floats the microcode held before FTOI4, so the host
    // rasteriser keeps the fraction the GIF path has to truncate to 1/16 of a pixel.
    //
    // Anything the hook cannot reproduce one for one -- a tag that is not this list's PACKED
    // (ST, RGBAQ, XYZF2) x 3 template with PRE set, a primitive that is not a triangle, a vertex
    // with the ADC bit set (which suppresses the draw), or no GS at all -- falls back to the real
    // XGKICK, so the knob can only ever change how a triangle is drawn, never whether it is.
    bool hostDrawEnabled()
    {
        static const bool enabled = []() {
            const char *value = std::getenv("PS2X_VU1_HOST_DRAW");
            return value != nullptr && std::atoi(value) != 0;
        }();
        return enabled;
    }

    // The GIFtag's PRIM field (bits 47-57), decoded exactly like gs_frontend.cpp's
    // decodePrimRegister -- the same bits the GIF path feeds to the PRIM register through PRE.
    GSPrimReg primFromGifTag(uint64_t tagLo)
    {
        const uint64_t value = (tagLo >> 47) & 0x7FFu;
        GSPrimReg prim{};
        prim.type = static_cast<GSPrimType>(value & 0x7u);
        prim.iip = ((value >> 3) & 1u) != 0u;
        prim.tme = ((value >> 4) & 1u) != 0u;
        prim.fge = ((value >> 5) & 1u) != 0u;
        prim.abe = ((value >> 6) & 1u) != 0u;
        prim.aa1 = ((value >> 7) & 1u) != 0u;
        prim.fst = ((value >> 8) & 1u) != 0u;
        prim.ctxt = ((value >> 9) & 1u) != 0u;
        prim.fix = ((value >> 10) & 1u) != 0u;
        return prim;
    }

    float loadPacketFloat(const uint8_t *p)
    {
        float value;
        std::memcpy(&value, p, sizeof(value));
        return value;
    }

    uint32_t loadPacketWord(const uint8_t *p)
    {
        uint32_t value;
        std::memcpy(&value, p, sizeof(value));
        return value;
    }

    uint64_t loadPacketDword(const uint8_t *p)
    {
        uint64_t value;
        std::memcpy(&value, p, sizeof(value));
        return value;
    }

    // Returns false when the packet is not the shape the hook can reproduce; the caller then kicks.
    bool submitHostTriangleFromPacket(Ctx &c, int32_t packetQword, const float screenXY[3][2])
    {
        GS *gs = c.vu.activeGs();
        if (gs == nullptr)
            return false;

        const uint8_t *tagBytes = c.qwordBytes(packetQword);
        const uint64_t tagLo = loadPacketDword(tagBytes);
        const uint64_t tagHi = loadPacketDword(tagBytes + 8);
        if ((tagLo & 0x7FFFu) != 3u ||          // NLOOP: three vertices
            ((tagLo >> 46) & 1u) == 0u ||       // PRE: the tag carries the PRIM field
            ((tagLo >> 58) & 3u) != 0u ||       // FLG: PACKED
            ((tagLo >> 60) & 0xFu) != 3u ||     // NREG
            (tagHi & 0xFFFu) != 0x412u)         // REGS: ST, RGBAQ, XYZF2
            return false;

        const GSPrimReg prim = primFromGifTag(tagLo);
        if (prim.type != GS_PRIM_TRIANGLE)
            return false;

        GSVertex vertices[3];
        for (int i = 0; i < 3; ++i)
        {
            const uint8_t *st = c.qwordBytes(packetQword + 1 + i * 3);
            const uint8_t *rgbaq = c.qwordBytes(packetQword + 2 + i * 3);
            const uint8_t *xyzf = c.qwordBytes(packetQword + 3 + i * 3);
            GSVertex &v = vertices[i];

            // PACKED ST (0x02): S = lo[0:32], T = lo[32:64], Q = hi[0:32]; a zero Q reads as 1.0.
            v.s = loadPacketFloat(st);
            v.t = loadPacketFloat(st + 4);
            v.q = loadPacketFloat(st + 8);
            if (v.q == 0.0f)
                v.q = 1.0f;

            // PACKED RGBAQ (0x01): the low byte of each of the four words.
            v.r = rgbaq[0];
            v.g = rgbaq[4];
            v.b = rgbaq[8];
            v.a = rgbaq[12];

            // PACKED XYZF2 (0x04): Z = hi[4:28], F = hi[36:44], ADC = hi[47]. FTOI4 put X/Y/Z/F
            // in 1/16 units, which is why the GS reads Z and F four bits up.
            const uint32_t zWord = loadPacketWord(xyzf + 8);
            const uint32_t fWord = loadPacketWord(xyzf + 12);
            if (((fWord >> 15) & 1u) != 0u)
                return false;
            v.z = static_cast<double>((zWord >> 4) & 0xFFFFFFu);
            v.fog = static_cast<uint8_t>((fWord >> 4) & 0xFFu);

            // X/Y in XYOFFSET space: the packet words are (uint16)(xy * 16) and the GIF path reads
            // them back as word / 16, so these floats are the same coordinate without the truncation.
            v.x = screenXY[i][0];
            v.y = screenXY[i][1];
        }

        // The tag's PRE bit writes PRIM before the vertices; do the same so the GS register state
        // a host-drawn triangle leaves behind is the state a kicked packet would have left.
        gs->writeRegister(GS_REG_PRIM, (tagLo >> 47) & 0x7FFu);
        gs->submitHostTriangle(prim, vertices[0], vertices[1], vertices[2]);
        return true;
    }

    bool cmdBuildPacket(Ctx &c)
    {
        using namespace packet;
        using vu1ops::ArithAdd;
        using vu1ops::ArithMadd;
        using vu1ops::ArithSub;
        __m128 up;

        // Read once per run (hostDrawEnabled caches the env), and only meaningful while a GS is
        // attached -- activeGs() is valid for the length of this execute()/resume() call.
        const bool hostDraw = hostDrawEnabled() && c.vu.activeGs() != nullptr;

        loadQword<kBias, kXYZW>(c, 38);                          // 0x1780
        loadQword<kGifTag, kXYZW>(c, c.vi(1) + 1);               // 0x1788: TOP+1

        // 0x1790-0x1798: ACC holds the fixed-point rounding term the RGBAQ MADDs add; it is set
        // once and never rewritten inside this command.
        up = fmac<ArithAdd, Vu1Gen::SrcBc, 3, kXYZ, 0, kBias, false, false, true>(c);
        c.vi(kIndexCursor) = c.loadWord(c.vi(1) + 2, 0);         // TOP+2.x
        writeAcc<kXYZ>(c, up);
        up = fmac<ArithSub, Vu1Gen::SrcBc, 3, kW, 0, 0, false, false, false>(c);
        c.vi(kScratch) = 32767;
        writeAcc<kW>(c, up);
        c.vi(kScratch) = vi16(c.vi(kScratch) + 4);               // 0x17a0: 0x8003 = EOP | NLOOP 3
        c.vi(kIndexCursor) = vi16(c.vi(kIndexCursor) + c.vi(1)); // 0x17a8

        // 0x17b0-0x17c8: both packet buffers get the tag, with NLOOP patched to three vertices.
        storeQword<kGifTag, kXYZW>(c, 290);
        storeQword<kGifTag, kXYZW>(c, 300);
        storeIntWord<kX>(c, 290, c.vi(kScratch));
        storeIntWord<kX>(c, 300, c.vi(kScratch));

        c.vi(kTriangles) = c.loadWord(c.vi(1) + 2, 3);           // 0x17d0: TOP+2.w
        loadQword<kBias, kW>(c, 327);                            // 0x17d8
        c.vi(kPacket) = c.loadWord(329, 0);                      // 0x17e0: 300
        c.vi(kOtherPacket) = c.loadWord(329, 1);                 // 0x17e8: 290

        for (;;)
        {
            // 0x17f0-0x1828: the triangle's three vertex offsets and its visibility gate.
            c.vi(kFlags) = c.loadWord(c.vi(kIndexCursor), 3);
            c.vi(kScratch) = 1;
            c.vi(kVertex0) = c.loadWord(c.vi(kIndexCursor), 0);
            c.vi(kVertex1) = c.loadWord(c.vi(kIndexCursor), 1);
            c.vi(kGate) = c.vi(kFlags) & c.vi(kScratch);
            c.vi(kForce) = c.loadWord(39, 3);
            const bool visible = static_cast<int16_t>(c.vi(kGate)) != 0;
            c.vi(kVertex2) = c.loadWord(c.vi(kIndexCursor), 2); // 0x1828, the branch's delay slot

            bool emit = false;
            if (visible)
            {
                // 0x1830-0x1860: the second gate, then the first RGBAQ load in the delay slot.
                c.vi(kScratch) = 2;
                c.vi(kGate) = c.vi(kFlags) & c.vi(kScratch);
                c.vi(kGate) = c.vi(kGate) | c.vi(kForce);
                emit = static_cast<int16_t>(c.vi(kGate)) != 0;
                loadQword<kRgba0, kXYZW>(c, c.vi(kVertex0) + 41);
            }

            if (emit)
            {
                // 0x1868-0x1890: the other two RGBAQ quads and the three XYZF2 quads, with the
                // rounding bias folded in.
                loadQword<kRgba1, kXYZW>(c, c.vi(kVertex1) + 41);
                loadQword<kRgba2, kXYZW>(c, c.vi(kVertex2) + 41);
                loadQword<kXyz0, kXYZW>(c, c.vi(kVertex0) + 42);
                up = fmac<ArithMadd, Vu1Gen::SrcVt, 0, kXYZW, kRgba0, kBias>(c);
                loadQword<kXyz1, kXYZW>(c, c.vi(kVertex1) + 42);
                writeVf<kRgba0, kXYZW>(c, up);
                up = fmac<ArithMadd, Vu1Gen::SrcVt, 0, kXYZW, kRgba1, kBias>(c);
                loadQword<kXyz2, kXYZW>(c, c.vi(kVertex2) + 42);
                writeVf<kRgba1, kXYZW>(c, up);
                up = fmac<ArithMadd, Vu1Gen::SrcVt, 0, kXYZW, kRgba2, kBias>(c);
                loadQword<kSt0, kXYZW>(c, c.vi(kVertex0) + 40);
                writeVf<kRgba2, kXYZW>(c, up);

                // The three XYZF2 quads are loaded and not yet converted: this is the last point
                // at which the screen position is still the float the perspective divide produced.
                // PS2X_VU1_HOST_DRAW hands those floats to the GS instead of the FTOI4 words.
                float screenXY[3][2] = {};
                if (hostDraw)
                {
                    const float(*vf)[4] = c.vu.m_state.vf;
                    screenXY[0][0] = vf[kXyz0][0];
                    screenXY[0][1] = vf[kXyz0][1];
                    screenXY[1][0] = vf[kXyz1][0];
                    screenXY[1][1] = vf[kXyz1][1];
                    screenXY[2][0] = vf[kXyz2][0];
                    screenXY[2][1] = vf[kXyz2][1];
                }

                // 0x1898-0x18c0: to fixed point (XYZF2 with 4 fractional bits, RGBAQ with none),
                // while the ST quads load and the two packet buffers swap roles.
                up = ftoi<4, kXyz0>(c);
                loadQword<kSt1, kXYZW>(c, c.vi(kVertex1) + 40);
                writeVf<kXyz0, kXYZW>(c, up);
                up = ftoi<0, kRgba0>(c);
                loadQword<kSt2, kXYZW>(c, c.vi(kVertex2) + 40);
                writeVf<kRgba0, kXYZW>(c, up);
                up = ftoi<4, kXyz1>(c);
                c.vi(kScratch) = vi16(c.vi(kPacket));
                writeVf<kXyz1, kXYZW>(c, up);
                up = ftoi<0, kRgba1>(c);
                c.vi(kPacket) = vi16(c.vi(kOtherPacket));
                writeVf<kRgba1, kXYZW>(c, up);
                up = ftoi<4, kXyz2>(c);
                c.vi(kOtherPacket) = vi16(c.vi(kScratch));
                writeVf<kXyz2, kXYZW>(c, up);
                up = ftoi<0, kRgba2>(c);
                storeQword<kSt0, kXYZW>(c, c.vi(kPacket) + 1);
                writeVf<kRgba2, kXYZW>(c, up);

                // 0x18c8-0x1900: the nine register qwords, in the tag's REGS order per vertex.
                storeQword<kSt1, kXYZW>(c, c.vi(kPacket) + 4);
                storeQword<kSt2, kXYZW>(c, c.vi(kPacket) + 7);
                storeQword<kRgba0, kXYZW>(c, c.vi(kPacket) + 2);
                storeQword<kRgba1, kXYZW>(c, c.vi(kPacket) + 5);
                storeQword<kRgba2, kXYZW>(c, c.vi(kPacket) + 8);
                storeQword<kXyz0, kXYZW>(c, c.vi(kPacket) + 3);
                storeQword<kXyz1, kXYZW>(c, c.vi(kPacket) + 6);
                storeQword<kXyz2, kXYZW>(c, c.vi(kPacket) + 9);

                // 0x1920: XGKICK vi2. The interpreter's default model copies the whole packet at
                // kick time, so this is a complete GIF submission (the entry check refuses the
                // cycle-exact model, under which back-to-back kicks would drop packets). With
                // PS2X_VU1_HOST_DRAW=1 the packet is drawn through the host hook instead; the
                // counter counts the triangle either way so [vu1-stats] stays comparable.
                g_xgkickDecoded.fetch_add(1, std::memory_order_relaxed);
                if (!hostDraw || !submitHostTriangleFromPacket(c, c.vi(kPacket), screenXY))
                    c.vu.startXgkick(static_cast<uint32_t>(static_cast<uint16_t>(c.vi(kPacket))));
            }

            // 0x1930-0x1940: next triangle.
            c.vi(kTriangles) = vi16(c.vi(kTriangles) - 1);
            c.vi(kIndexCursor) = vi16(c.vi(kIndexCursor) + 2);
            if (!(static_cast<int16_t>(c.vi(kTriangles)) > 0))
                break;
        }

        // 0x1950-0x1960: hand the swapped buffer bases back to data qword 329.
        storeIntWord<kX>(c, 329, c.vi(kPacket));
        storeIntWord<kY>(c, 329, c.vi(kOtherPacket));
        return true;                                             // 0x1958: B 0x1b60
    }

    // ---- command 0x06 -> 0x1638: backface cull ---------------------------------------------
    //
    // Sets bit 0 of every triangle's flag word -- the gate command 0x28 reads -- from the sign of
    // dot(eye - vertex, normal). The eye position is data qword 30 (research/07's cull eye); the
    // index list is the same two-qword-per-triangle one 0x28 walks, with the reference vertex
    // index in .x of qword 0 and the normal, in 15-bit fixed point, in qword 1.
    //
    // The sign test is the microcode's own: `FMAND vi13, vi5` with vi5 = 16 reads the S flag of
    // the w lane of the MAC register, i.e. the sign of the dot product that the MADDz.w four pairs
    // earlier produced. Four pairs is exactly the FMAC latency, so the interpreter has that entry
    // committed at the FMAND and no other FMAC is in flight -- this file's immediate flag commit
    // reads the same value.
    namespace cull
    {
        constexpr uint8_t kEye = 26;     // data qword 30
        constexpr uint8_t kNormal = 29;  // the triangle normal (ITOF15 of the index qword +1)
        constexpr uint8_t kVertex = 28;  // the reference vertex's position
        constexpr uint8_t kToEye = 27;   // eye - vertex
        constexpr uint8_t kDot = 30;     // the product, then its .w = x + y + z
        constexpr uint8_t kRecordBase = 3;  // vi3 = TOP+4
        constexpr uint8_t kIndexCursor = 4; // vi4, two qwords per triangle
        constexpr uint8_t kRemaining = 9;   // vi9
        constexpr uint8_t kMacSignW = 5;    // vi5 = 16: the MAC bit for the w lane's sign
        constexpr uint8_t kScratch = 8, kVertexPtr = 11, kFlags = 12, kSign = 13;
    }

    bool cmdBackfaceCull(Ctx &c)
    {
        using namespace cull;
        using vu1ops::ArithMadd;
        using vu1ops::ArithMul;
        using vu1ops::ArithSub;
        __m128 up;

        c.vi(kIndexCursor) = c.loadWord(c.vi(1) + 2, 0);         // 0x1638: TOP+2.x
        c.vi(kRemaining) = c.loadWord(c.vi(1) + 2, 3);           // 0x1640: TOP+2.w
        loadQword<kEye, kXYZW>(c, 30);                           // 0x1648
        c.vi(kRecordBase) = vi16(c.vi(1) + 4);                   // 0x1650
        c.vi(kIndexCursor) = vi16(c.vi(kIndexCursor) + c.vi(1)); // 0x1658

        // 0x1660-0x16a8: the first triangle's normal and reference vertex.
        c.vi(kScratch) = c.loadWord(c.vi(kIndexCursor), 0);
        loadQword<kNormal, kXYZW>(c, c.vi(kIndexCursor) + 1);
        c.vi(kMacSignW) = 16;
        c.vi(kVertexPtr) = vi16(c.vi(kRecordBase) + c.vi(kScratch));
        up = itof<15, kNormal>(c);
        loadQword<kVertex, kXYZW>(c, c.vi(kVertexPtr));
        writeVf<kNormal, kXYZW>(c, up);
        up = fmac<ArithSub, Vu1Gen::SrcVt, 0, kXYZW, kEye, kVertex>(c);
        writeVf<kToEye, kXYZW>(c, up);

        for (;;)
        {
            // 0x16c8-0x16f8: dot(eye - vertex, normal) in .w, while the next triangle's normal and
            // reference vertex are fetched.
            up = fmac<ArithMul, Vu1Gen::SrcVt, 0, kXYZW, kToEye, kNormal, false, false, false>(c);
            c.vi(kScratch) = c.loadWord(c.vi(kIndexCursor) + 2, 0);
            writeVf<kDot, kXYZW>(c, up);
            loadQword<kNormal, kXYZW>(c, c.vi(kIndexCursor) + 3);
            c.vi(kFlags) = c.loadWord(c.vi(kIndexCursor), 3);
            up = fmac<ArithMul, Vu1Gen::SrcBc, 0, kW, 0, kDot, false, false, false>(c);
            c.vi(kVertexPtr) = vi16(c.vi(kRecordBase) + c.vi(kScratch));
            writeAcc<kW>(c, up);
            up = fmac<ArithMadd, Vu1Gen::SrcBc, 1, kW, 0, kDot, false, false, false>(c);
            loadQword<kVertex, kXYZW>(c, c.vi(kVertexPtr));
            writeAcc<kW>(c, up);
            up = fmac<ArithMadd, Vu1Gen::SrcBc, 2, kW, 0, kDot, false, false, false>(c);
            c.vi(kScratch) = 32766;
            writeVf<kDot, kW>(c, up);

            // 0x1700-0x1738: clear the visibility bit, set it again unless the dot came out
            // negative, and write the flag word back.
            c.vi(kFlags) = c.vi(kFlags) & c.vi(kScratch);
            up = itof<15, kNormal>(c);
            c.vi(kScratch) = 1;
            writeVf<kNormal, kXYZW>(c, up);
            c.vi(kSign) = fmand(c, c.vi(kMacSignW));
            if (!(static_cast<int16_t>(c.vi(kSign)) > 0))
                c.vi(kFlags) = c.vi(kFlags) | c.vi(kScratch);
            storeIntWord<kW>(c, c.vi(kIndexCursor), c.vi(kFlags));

            // 0x1740-0x1750: the next triangle's eye vector, then loop.
            up = fmac<ArithSub, Vu1Gen::SrcVt, 0, kXYZW, kEye, kVertex>(c);
            c.vi(kRemaining) = vi16(c.vi(kRemaining) - 1);
            writeVf<kToEye, kXYZW>(c, up);
            c.vi(kIndexCursor) = vi16(c.vi(kIndexCursor) + 2);
            if (!(static_cast<int16_t>(c.vi(kRemaining)) > 0))
                return true;                                     // 0x1760: B 0x1b60
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
        case kCmdCull:
            return cmdBackfaceCull(c);
        case kCmdTransform:
            return cmdTransformDivide(c);
        case kCmdClippedTransform:
            return cmdClippedTransform(c);
        case kCmdFade:
            return cmdDistanceFade(c);
        case kCmdTemplateFill:
            return cmdTemplateFill(c);
        case kCmdClippedTemplateFill:
            return cmdClippedTemplateFill(c);
        case kCmdLight:
            return cmdLighting(c);
        case kCmdBuildPacket:
            return cmdBuildPacket(c);
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
    // 0x1b50's XTOP result: the VIF double-buffered input base. Needed by the pre-scan (the header
    // counts live at TOP+2) before it is committed to vi1.
    const int32_t top = static_cast<int32_t>(vu.m_state.top & 0x3FFu);
    if (!vu.m_activeVuData || vu.m_activeVuDataSize < 16u * 1024u || !xgkickIsImmediate() ||
        !isFamilyARun(c, top))
        return false; // whole-program hand-back: pc is still 0x1b50 and nothing has been touched

    // 0x1b50: vi1 is the base every handler derives its pointers from.
    // 0x1b58: the command index starts at 0.
    c.vi(1) = top;
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
