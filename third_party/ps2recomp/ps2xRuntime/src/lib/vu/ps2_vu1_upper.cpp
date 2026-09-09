#include "runtime/ps2_vu1.h"
#include "ps2_vu1_detail.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <emmintrin.h>
#include <limits>

namespace
{
    int32_t vuFloatToInt(float value, float scale)
    {
        const double scaled = static_cast<double>(value) * static_cast<double>(scale);
        if (scaled >= static_cast<double>(std::numeric_limits<int32_t>::max()))
            return std::numeric_limits<int32_t>::max();
        if (scaled <= static_cast<double>(std::numeric_limits<int32_t>::min()))
            return std::numeric_limits<int32_t>::min();
        return static_cast<int32_t>(scaled);
    }

    constexpr float kFltMax = std::numeric_limits<float>::max();
    constexpr double kFltMaxD = static_cast<double>(std::numeric_limits<float>::max());
    constexpr double kFltMinD = static_cast<double>(std::numeric_limits<float>::min());
    constexpr long double kFltMaxL = static_cast<long double>(std::numeric_limits<float>::max());

    inline uint32_t bitsOf(float value)
    {
        uint32_t bits = 0u;
        std::memcpy(&bits, &value, sizeof(bits));
        return bits;
    }

    // Lane order: SSE lane 0 = x .. lane 3 = w. The VU flag registers number the lanes the other way
    // round (bit 0 = w .. bit 3 = x, laneForComponent), so movemask results go through kRev4.
    constexpr uint8_t kRev4[16] = {0x0, 0x8, 0x4, 0xC, 0x2, 0xA, 0x6, 0xE, 0x1, 0x9, 0x5, 0xD, 0x3, 0xB, 0x7, 0xF};

    // movemask bit i (lane i) -> per-lane all-ones mask.
    alignas(16) constexpr int32_t kLaneMaskTable[16][4] = {
        {0, 0, 0, 0}, {-1, 0, 0, 0}, {0, -1, 0, 0}, {-1, -1, 0, 0},
        {0, 0, -1, 0}, {-1, 0, -1, 0}, {0, -1, -1, 0}, {-1, -1, -1, 0},
        {0, 0, 0, -1}, {-1, 0, 0, -1}, {0, -1, 0, -1}, {-1, -1, 0, -1},
        {0, 0, -1, -1}, {-1, 0, -1, -1}, {0, -1, -1, -1}, {-1, -1, -1, -1}};

    inline __m128i movemaskToLanes(uint32_t mask4)
    {
        return _mm_load_si128(reinterpret_cast<const __m128i *>(kLaneMaskTable[mask4 & 0xFu]));
    }

    // dest field (bit 3 = x .. bit 0 = w) -> per-lane all-ones mask.
    inline __m128i destMask4(uint8_t dest)
    {
        return movemaskToLanes(kRev4[dest & 0xFu]);
    }

    // normalizeOperand on four lanes: denormals -> +/-0, infinities/NaNs -> +/-FLT_MAX.
    inline __m128 normalize4(__m128 value)
    {
        const __m128i bits = _mm_castps_si128(value);
        const __m128i exponent = _mm_and_si128(bits, _mm_set1_epi32(0x7F800000));
        const __m128i zeroExp = _mm_cmpeq_epi32(exponent, _mm_setzero_si128());
        const __m128i maxExp = _mm_cmpeq_epi32(exponent, _mm_set1_epi32(0x7F800000));
        const __m128i sign = _mm_and_si128(bits, _mm_set1_epi32(static_cast<int>(0x80000000u)));
        __m128i out = _mm_andnot_si128(_mm_or_si128(zeroExp, maxExp), bits);
        out = _mm_or_si128(out, _mm_and_si128(sign, zeroExp));
        out = _mm_or_si128(out, _mm_and_si128(_mm_or_si128(sign, _mm_set1_epi32(0x7F7FFFFF)), maxExp));
        return _mm_castsi128_ps(out);
    }

    inline __m128 broadcastLane(__m128 v, uint32_t lane)
    {
        switch (lane & 3u)
        {
        case 0: return _mm_shuffle_ps(v, v, _MM_SHUFFLE(0, 0, 0, 0));
        case 1: return _mm_shuffle_ps(v, v, _MM_SHUFFLE(1, 1, 1, 1));
        case 2: return _mm_shuffle_ps(v, v, _MM_SHUFFLE(2, 2, 2, 2));
        default: return _mm_shuffle_ps(v, v, _MM_SHUFFLE(3, 3, 3, 3));
        }
    }

    // Two double-lane masks (lanes 0,1 and 2,3) -> one four-lane 32-bit mask.
    inline __m128i packMask(__m128d lo, __m128d hi)
    {
        return _mm_castps_si128(_mm_shuffle_ps(_mm_castpd_ps(lo), _mm_castpd_ps(hi), _MM_SHUFFLE(2, 0, 2, 0)));
    }

    struct FmacResult
    {
        __m128 value;     // lanes to store (only dest lanes meaningful)
        uint32_t mac;     // MAC register bits for the dest lanes
        uint32_t status;  // Z/S/U/O presence (bits 0..3)
        uint32_t sticky;  // product flags folded into the sticky bits (product-sum ops)
    };

    inline void finishFlags(FmacResult &out, __m128i zeroM, __m128i signM, __m128i underM, __m128i overM, __m128i destM)
    {
        const uint32_t z = kRev4[_mm_movemask_ps(_mm_castsi128_ps(_mm_and_si128(zeroM, destM)))];
        const uint32_t s = kRev4[_mm_movemask_ps(_mm_castsi128_ps(_mm_and_si128(signM, destM)))];
        const uint32_t u = kRev4[_mm_movemask_ps(_mm_castsi128_ps(_mm_and_si128(underM, destM)))];
        const uint32_t o = kRev4[_mm_movemask_ps(_mm_castsi128_ps(_mm_and_si128(overM, destM)))];
        out.mac = z | (s << 4) | (u << 8) | (o << 12);
        out.status = (z ? 1u : 0u) | (s ? 2u : 0u) | (u ? 4u : 0u) | (o ? 8u : 0u);
    }

    enum FmacKind
    {
        FmacAdd,
        FmacSub,
        FmacMul
    };

    // FMAC lanes of a single add, subtract or multiply, in chop rounding (the run() loop sets
    // FE_TOWARDZERO): the stored floats and the Z/S/U/O lane flags.
    //
    // Bit-identical to classifying the long double result (normalizeFmacExactResult over
    // calculateFmacExactResult) without computing it, because a single chop-rounded float op has
    // |r| <= |exact| < |r| + ulp(r):
    //   r == 0      : add/sub only when a == -b (the exact sum of two floats is otherwise >= 2^-149 and
    //                 representable as a denormal); mul when an operand is zero, or when the exact
    //                 product is below the denormal range (underflow, U|Z).
    //   r denormal  : 2^-149 <= |exact| < FLT_MIN, underflow (U|Z), the stored value is +/-0.
    //   |r| == FLT_MAX: the exact result is >= FLT_MAX; only here the long double decides (overflow
    //                 when its chop-rounded value exceeds FLT_MAX, exactly what the old path tested).
    //   otherwise   : FLT_MIN <= |r| <= |exact| < FLT_MAX, no flag but the sign.
    // The sign of r equals the sign of the exact result in every case (chop keeps the sign; an exact
    // zero sum is +0 unless both terms are -0, in float and long double alike).
    // |r| == FLT_MAX lanes: the chop-rounded long double result decides the overflow flag.
    template <FmacKind Kind>
    __attribute__((noinline)) uint32_t singleOverflowLanes(__m128 a, __m128 b, uint32_t atMax)
    {
        alignas(16) float av[4], bv[4];
        _mm_store_ps(av, a);
        _mm_store_ps(bv, b);
        uint32_t overLanes = 0u;
        for (uint32_t lane = 0; lane < 4u; ++lane)
        {
            if ((atMax & (1u << lane)) == 0u)
                continue;
            long double exact;
            if (Kind == FmacAdd)
                exact = static_cast<long double>(av[lane]) + static_cast<long double>(bv[lane]);
            else if (Kind == FmacSub)
                exact = static_cast<long double>(av[lane]) - static_cast<long double>(bv[lane]);
            else
                exact = static_cast<long double>(av[lane]) * static_cast<long double>(bv[lane]);
            if (std::fabs(exact) > kFltMaxL)
                overLanes |= 1u << lane;
        }
        return overLanes;
    }

    template <bool Sub>
    __attribute__((noinline)) uint32_t productSumOverflowLanes(__m128 acc, __m128 a, __m128 b, uint32_t atMax)
    {
        alignas(16) float av[4], bv[4], cv[4];
        _mm_store_ps(av, a);
        _mm_store_ps(bv, b);
        _mm_store_ps(cv, acc);
        uint32_t overLanes = 0u;
        for (uint32_t lane = 0; lane < 4u; ++lane)
        {
            if ((atMax & (1u << lane)) == 0u)
                continue;
            const long double exact = Sub
                                          ? static_cast<long double>(cv[lane]) - static_cast<long double>(av[lane]) * static_cast<long double>(bv[lane])
                                          : static_cast<long double>(cv[lane]) + static_cast<long double>(av[lane]) * static_cast<long double>(bv[lane]);
            if (std::fabs(exact) > kFltMaxL)
                overLanes |= 1u << lane;
        }
        return overLanes;
    }

    template <FmacKind Kind>
    inline void fmacSingle4(__m128 a, __m128 b, __m128i destM, FmacResult &out)
    {
        __m128 r;
        if (Kind == FmacAdd)
            r = _mm_add_ps(a, b);
        else if (Kind == FmacSub)
            r = _mm_sub_ps(a, b);
        else
            r = _mm_mul_ps(a, b);
        const __m128i bits = _mm_castps_si128(r);
        const __m128i signBit = _mm_set1_epi32(static_cast<int>(0x80000000u));
        const __m128i magnitude = _mm_and_si128(bits, _mm_set1_epi32(0x7FFFFFFF));
        const __m128i signM = _mm_srai_epi32(bits, 31);
        const __m128i zeroM = _mm_cmpeq_epi32(magnitude, _mm_setzero_si128());
        const __m128i denormM = _mm_andnot_si128(zeroM, _mm_cmplt_epi32(magnitude, _mm_set1_epi32(0x00800000)));
        const __m128i maxM = _mm_cmpeq_epi32(magnitude, _mm_set1_epi32(0x7F7FFFFF));
        __m128i underM = denormM;
        if (Kind == FmacMul)
        {
            const __m128i operandsNonzero = _mm_castps_si128(_mm_and_ps(_mm_cmpneq_ps(a, _mm_setzero_ps()), _mm_cmpneq_ps(b, _mm_setzero_ps())));
            underM = _mm_or_si128(underM, _mm_and_si128(zeroM, operandsNonzero));
        }
        // Denormal results store as +/-0.
        __m128i value = _mm_or_si128(_mm_andnot_si128(denormM, bits), _mm_and_si128(denormM, _mm_and_si128(bits, signBit)));
        __m128i overM = _mm_setzero_si128();
        const uint32_t atMax = static_cast<uint32_t>(_mm_movemask_ps(_mm_castsi128_ps(_mm_and_si128(maxM, destM))));
        if (__builtin_expect(atMax != 0u, 0))
            overM = movemaskToLanes(singleOverflowLanes<Kind>(a, b, atMax));
        out.value = _mm_castsi128_ps(value);
        out.sticky = 0u;
        finishFlags(out, _mm_or_si128(zeroM, denormM), signM, underM, overM, destM);
    }

    // Product-sum lanes (acc +/- a*b). The float result keeps the old two-rounding form; the flags
    // come from the double sum: the product of two floats is exact in double, and a chop-rounded
    // double sum falls in the same class (zero / underflow / normal / overflow) as the chop-rounded
    // long double sum except when it lands exactly on FLT_MAX, where the long double decides. Every
    // product condition accumulates into the sticky flags (calculateFmacProductSticky).
    template <bool Sub>
    inline void fmacProductSum4(__m128 acc, __m128 a, __m128 b, __m128i destM, FmacResult &out)
    {
        const __m128 r = Sub ? _mm_sub_ps(acc, _mm_mul_ps(a, b)) : _mm_add_ps(acc, _mm_mul_ps(a, b));

        const __m128d aLo = _mm_cvtps_pd(a);
        const __m128d aHi = _mm_cvtps_pd(_mm_movehl_ps(a, a));
        const __m128d bLo = _mm_cvtps_pd(b);
        const __m128d bHi = _mm_cvtps_pd(_mm_movehl_ps(b, b));
        const __m128d pLo = _mm_mul_pd(aLo, bLo);
        const __m128d pHi = _mm_mul_pd(aHi, bHi);
        const __m128d accLo = _mm_cvtps_pd(acc);
        const __m128d accHi = _mm_cvtps_pd(_mm_movehl_ps(acc, acc));
        const __m128d sLo = Sub ? _mm_sub_pd(accLo, pLo) : _mm_add_pd(accLo, pLo);
        const __m128d sHi = Sub ? _mm_sub_pd(accHi, pHi) : _mm_add_pd(accHi, pHi);

        const __m128d absMask = _mm_castsi128_pd(_mm_set_epi32(0x7FFFFFFF, -1, 0x7FFFFFFF, -1));
        const __m128d fltMax = _mm_set1_pd(kFltMaxD);
        const __m128d fltMin = _mm_set1_pd(kFltMinD);
        const __m128d zero = _mm_setzero_pd();

        // Product sticky: Z / S / U / O of a*b.
        {
            const __m128d pAbsLo = _mm_and_pd(pLo, absMask);
            const __m128d pAbsHi = _mm_and_pd(pHi, absMask);
            const __m128i pZero = packMask(_mm_cmpeq_pd(pLo, zero), _mm_cmpeq_pd(pHi, zero));
            const __m128i pOver = packMask(_mm_cmpgt_pd(pAbsLo, fltMax), _mm_cmpgt_pd(pAbsHi, fltMax));
            const __m128i pUnder = _mm_andnot_si128(pZero, packMask(_mm_cmplt_pd(pAbsLo, fltMin), _mm_cmplt_pd(pAbsHi, fltMin)));
            const uint32_t pSign = static_cast<uint32_t>(_mm_movemask_pd(pLo)) | (static_cast<uint32_t>(_mm_movemask_pd(pHi)) << 2);
            const __m128i pSignM = movemaskToLanes(pSign);
            const uint32_t z = static_cast<uint32_t>(_mm_movemask_ps(_mm_castsi128_ps(_mm_and_si128(_mm_or_si128(pZero, pUnder), destM))));
            const uint32_t s = static_cast<uint32_t>(_mm_movemask_ps(_mm_castsi128_ps(_mm_and_si128(pSignM, destM))));
            const uint32_t u = static_cast<uint32_t>(_mm_movemask_ps(_mm_castsi128_ps(_mm_and_si128(pUnder, destM))));
            const uint32_t o = static_cast<uint32_t>(_mm_movemask_ps(_mm_castsi128_ps(_mm_and_si128(pOver, destM))));
            out.sticky = (z ? 1u : 0u) | (s ? 2u : 0u) | (u ? 4u : 0u) | (o ? 8u : 0u);
        }

        const __m128d sAbsLo = _mm_and_pd(sLo, absMask);
        const __m128d sAbsHi = _mm_and_pd(sHi, absMask);
        const __m128i zeroM = packMask(_mm_cmpeq_pd(sLo, zero), _mm_cmpeq_pd(sHi, zero));
        __m128i overM = packMask(_mm_cmpgt_pd(sAbsLo, fltMax), _mm_cmpgt_pd(sAbsHi, fltMax));
        const __m128i underM = _mm_andnot_si128(zeroM, packMask(_mm_cmplt_pd(sAbsLo, fltMin), _mm_cmplt_pd(sAbsHi, fltMin)));
        const __m128i atMaxM = packMask(_mm_cmpeq_pd(sAbsLo, fltMax), _mm_cmpeq_pd(sAbsHi, fltMax));
        const uint32_t signBits = static_cast<uint32_t>(_mm_movemask_pd(sLo)) | (static_cast<uint32_t>(_mm_movemask_pd(sHi)) << 2);
        const __m128i signM = movemaskToLanes(signBits);

        const uint32_t atMax = static_cast<uint32_t>(_mm_movemask_ps(_mm_castsi128_ps(_mm_and_si128(atMaxM, destM))));
        if (__builtin_expect(atMax != 0u, 0))
            overM = _mm_or_si128(overM, movemaskToLanes(productSumOverflowLanes<Sub>(acc, a, b, atMax)));

        // Stored value: +/-0 for zero and underflow, +/-FLT_MAX for overflow, else the float result.
        const __m128i signOnly = _mm_and_si128(signM, _mm_set1_epi32(static_cast<int>(0x80000000u)));
        const __m128i zeroOrUnder = _mm_or_si128(zeroM, underM);
        __m128i value = _mm_andnot_si128(_mm_or_si128(zeroOrUnder, overM), _mm_castps_si128(r));
        value = _mm_or_si128(value, _mm_and_si128(zeroOrUnder, signOnly));
        value = _mm_or_si128(value, _mm_and_si128(overM, _mm_or_si128(signOnly, _mm_set1_epi32(0x7F7FFFFF))));
        out.value = _mm_castsi128_ps(value);
        finishFlags(out, _mm_or_si128(zeroM, underM), signM, underM, overM, destM);
    }
}


// PS2X_VU1_FMAC_CHECK=1: recompute through the long double path (it reads the register file, so this
// runs before the write-back) and report any difference in stored value, MAC/status or sticky bits.
__attribute__((noinline)) void VU1Interpreter::checkFmac(uint32_t instr, uint8_t kindValue, bool opmul, __m128 first, __m128 second,
                                                          __m128 value, uint32_t mac, uint32_t status, uint32_t sticky)
{
    enum ArithKind : uint8_t
    {
        ArithNone,
        ArithAdd,
        ArithSub,
        ArithMadd,
        ArithMsub,
        ArithMul
    };
    const ArithKind kind = static_cast<ArithKind>(kindValue);
    const uint8_t dest = DEST(instr);
    FmacResult out;
    out.value = value;
    out.mac = mac;
    out.status = status;
    out.sticky = sticky;
    alignas(16) float fa[4], sb[4], ca[4], nv[4];
    _mm_store_ps(fa, first);
    _mm_store_ps(sb, second);
    _mm_store_ps(nv, out.value);
    for (uint32_t c = 0; c < 4u; ++c)
        ca[c] = normalizeOperand(m_state.acc[c]);
    float checkResult[4] = {0.0f, 0.0f, 0.0f, 0.0f};
    for (uint32_t c = 0; c < 4u; ++c)
    {
        switch (kind)
        {
        case ArithAdd: checkResult[c] = fa[c] + sb[c]; break;
        case ArithSub: checkResult[c] = fa[c] - sb[c]; break;
        case ArithMul: checkResult[c] = fa[c] * sb[c]; break;
        case ArithMadd: checkResult[c] = ca[c] + fa[c] * sb[c]; break;
        case ArithMsub: checkResult[c] = ca[c] - fa[c] * sb[c]; break;
        default: break;
        }
    }
    if (opmul)
        checkResult[3] = 0.0f;
    uint8_t checkFlags[4]{};
    normalizeFmacResult(checkResult, dest, checkFlags);
    const uint32_t checkSticky = calculateFmacProductSticky(dest);
    uint32_t checkMac = 0u, checkStatus = 0u;
    for (uint32_t c = 0; c < 4u; ++c)
    {
        const uint32_t lane = 1u << (3u - c);
        if ((dest & lane) == 0u)
            continue;
        if (bitsOf(checkResult[c]) != bitsOf(nv[c]))
            std::fprintf(stderr, "[vu-fmac-check] pc=0x%x instr=%08x lane %u value: fast %08x exact %08x\n",
                         m_state.pc, instr, c, bitsOf(nv[c]), bitsOf(checkResult[c]));
        const uint32_t f = checkFlags[c];
        if (f & 1u) checkMac |= lane;
        if (f & 2u) checkMac |= lane << 4;
        if (f & 4u) checkMac |= lane << 8;
        if (f & 8u) checkMac |= lane << 12;
        checkStatus |= f;
    }
    if (checkMac != out.mac || checkStatus != out.status || checkSticky != out.sticky)
        std::fprintf(stderr, "[vu-fmac-check] pc=0x%x instr=%08x flags: fast mac=%03x st=%x sticky=%x exact mac=%03x st=%x sticky=%x\n",
                     m_state.pc, instr, out.mac, out.status, out.sticky, checkMac, checkStatus, checkSticky);
}

// ============================================================================
// Upper instructions (FMAC pipeline)
// ============================================================================
void VU1Interpreter::execUpper(uint32_t instr)
{
    m_currentUpperInstruction = instr;
    const uint8_t dest = DEST(instr);
    const uint8_t ft = FT(instr);
    const uint8_t fs = FS(instr);
    const uint8_t fd = FD(instr);
    const uint8_t op = instr & 0x3F;

    // PS2X_VU1_FMAC_CHECK=1: cross-check the SIMD lane classifier against the long double path.
    static const bool s_check = std::getenv("PS2X_VU1_FMAC_CHECK") != nullptr;

    const __m128 vsRaw = _mm_loadu_ps(m_state.vf[fs]);
    const __m128 vtRaw = _mm_loadu_ps(m_state.vf[ft]);
    const __m128 vs = normalize4(vsRaw);
    const __m128 vt = normalize4(vtRaw);

    enum ArithKind : uint8_t
    {
        ArithNone,
        ArithAdd,
        ArithSub,
        ArithMadd,
        ArithMsub,
        ArithMul
    };
    ArithKind kind = ArithNone;
    __m128 second = _mm_setzero_ps();
    bool toAcc = false;
    bool opmul = false; // OPMULA / OPMSUB cross-product lane wiring

    // Non-arithmetic ops use scalar code on normalized lanes (copied out only on those paths).
    alignas(16) float vsA[4];
    alignas(16) float vtA[4];
    const auto scalarOperands = [&]()
    {
        _mm_store_ps(vsA, vs);
        _mm_store_ps(vtA, vt);
    };
    float *vd = m_state.vf[fd];
    float result[4] = {0.0f, 0.0f, 0.0f, 0.0f};

    if (op <= 0x2Fu)
    {
        switch (op)
        {
        case 0x00: case 0x01: case 0x02: case 0x03: kind = ArithAdd; second = broadcastLane(vt, op); break;   // ADDbc
        case 0x04: case 0x05: case 0x06: case 0x07: kind = ArithSub; second = broadcastLane(vt, op); break;   // SUBbc
        case 0x08: case 0x09: case 0x0A: case 0x0B: kind = ArithMadd; second = broadcastLane(vt, op); break;  // MADDbc
        case 0x0C: case 0x0D: case 0x0E: case 0x0F: kind = ArithMsub; second = broadcastLane(vt, op); break;  // MSUBbc
        case 0x10: case 0x11: case 0x12: case 0x13: // MAXbc
        {
            scalarOperands();
            const float bc = vtA[op & 3];
            for (int c = 0; c < 4; c++)
                result[c] = (vsA[c] > bc) ? vsA[c] : bc;
            applyDest(vd, result, dest);
            return;
        }
        case 0x14: case 0x15: case 0x16: case 0x17: // MINIbc
        {
            scalarOperands();
            const float bc = vtA[op & 3];
            for (int c = 0; c < 4; c++)
                result[c] = (vsA[c] < bc) ? vsA[c] : bc;
            applyDest(vd, result, dest);
            return;
        }
        case 0x18: case 0x19: case 0x1A: case 0x1B: kind = ArithMul; second = broadcastLane(vt, op); break;   // MULbc
        case 0x1C: kind = ArithMul; second = _mm_set1_ps(normalizeOperand(m_state.q)); break;                 // MULq
        case 0x1D: // MAXi
        {
            scalarOperands();
            const float i = normalizeOperand(m_state.i);
            for (int c = 0; c < 4; c++)
                result[c] = (vsA[c] > i) ? vsA[c] : i;
            applyDest(vd, result, dest);
            return;
        }
        case 0x1E: kind = ArithMul; second = _mm_set1_ps(normalizeOperand(m_state.i)); break;                 // MULi
        case 0x1F: // MINIi
        {
            scalarOperands();
            const float i = normalizeOperand(m_state.i);
            for (int c = 0; c < 4; c++)
                result[c] = (vsA[c] < i) ? vsA[c] : i;
            applyDest(vd, result, dest);
            return;
        }
        case 0x20: kind = ArithAdd; second = _mm_set1_ps(normalizeOperand(m_state.q)); break;   // ADDq
        case 0x21: kind = ArithMadd; second = _mm_set1_ps(normalizeOperand(m_state.q)); break;  // MADDq
        case 0x22: kind = ArithAdd; second = _mm_set1_ps(normalizeOperand(m_state.i)); break;   // ADDi
        case 0x23: kind = ArithMadd; second = _mm_set1_ps(normalizeOperand(m_state.i)); break;  // MADDi
        case 0x24: kind = ArithSub; second = _mm_set1_ps(normalizeOperand(m_state.q)); break;   // SUBq
        case 0x25: kind = ArithMsub; second = _mm_set1_ps(normalizeOperand(m_state.q)); break;  // MSUBq
        case 0x26: kind = ArithSub; second = _mm_set1_ps(normalizeOperand(m_state.i)); break;   // SUBi
        case 0x27: kind = ArithMsub; second = _mm_set1_ps(normalizeOperand(m_state.i)); break;  // MSUBi
        case 0x28: kind = ArithAdd; second = vt; break;   // ADD
        case 0x29: kind = ArithMadd; second = vt; break;  // MADD
        case 0x2A: kind = ArithMul; second = vt; break;   // MUL
        case 0x2B: // MAX
            scalarOperands();
            for (int c = 0; c < 4; c++)
                result[c] = (vsA[c] > vtA[c]) ? vsA[c] : vtA[c];
            applyDest(vd, result, dest);
            return;
        case 0x2C: kind = ArithSub; second = vt; break;   // SUB
        case 0x2D: kind = ArithMsub; second = vt; break;  // MSUB
        case 0x2E: kind = ArithMsub; opmul = true; break; // OPMSUB
        case 0x2F: // MINI
            scalarOperands();
            for (int c = 0; c < 4; c++)
                result[c] = (vsA[c] < vtA[c]) ? vsA[c] : vtA[c];
            applyDest(vd, result, dest);
            return;
        default:
            break;
        }
    }
    else if (op >= 0x3Cu)
    {
        // Upper special group (low op 0x3C..0x3F). Like lower1 special, the real selector is not just
        // bits 5:0: op = (instr & 0x3) | ((instr >> 4) & 0x7C). Several of these use FT as the
        // destination, not FD.
        const uint8_t specialOp = static_cast<uint8_t>((instr & 0x3u) | ((instr >> 4) & 0x7Cu));
        float *vtDest = m_state.vf[ft];
        toAcc = true;
        switch (specialOp)
        {
        case 0x00: case 0x01: case 0x02: case 0x03: kind = ArithAdd; second = broadcastLane(vt, specialOp); break;   // ADDAbc
        case 0x04: case 0x05: case 0x06: case 0x07: kind = ArithSub; second = broadcastLane(vt, specialOp); break;   // SUBAbc
        case 0x08: case 0x09: case 0x0A: case 0x0B: kind = ArithMadd; second = broadcastLane(vt, specialOp); break;  // MADDAbc
        case 0x0C: case 0x0D: case 0x0E: case 0x0F: kind = ArithMsub; second = broadcastLane(vt, specialOp); break;  // MSUBAbc
        case 0x10: // ITOF0
            for (int c = 0; c < 4; c++)
            {
                int32_t iv;
                std::memcpy(&iv, &m_state.vf[fs][c], 4);
                result[c] = static_cast<float>(iv);
            }
            applyDest(vtDest, result, dest);
            return;
        case 0x11: // ITOF4
            for (int c = 0; c < 4; c++)
            {
                int32_t iv;
                std::memcpy(&iv, &m_state.vf[fs][c], 4);
                result[c] = static_cast<float>(iv) / 16.0f;
            }
            applyDest(vtDest, result, dest);
            return;
        case 0x12: // ITOF12
            for (int c = 0; c < 4; c++)
            {
                int32_t iv;
                std::memcpy(&iv, &m_state.vf[fs][c], 4);
                result[c] = static_cast<float>(iv) / 4096.0f;
            }
            applyDest(vtDest, result, dest);
            return;
        case 0x13: // ITOF15
            for (int c = 0; c < 4; c++)
            {
                int32_t iv;
                std::memcpy(&iv, &m_state.vf[fs][c], 4);
                result[c] = static_cast<float>(iv) / 32768.0f;
            }
            applyDest(vtDest, result, dest);
            return;
        case 0x14: // FTOI0
            scalarOperands();
            for (int c = 0; c < 4; c++)
            {
                int32_t iv = vuFloatToInt(vsA[c], 1.0f);
                std::memcpy(&result[c], &iv, 4);
            }
            applyDest(vtDest, result, dest);
            return;
        case 0x15: // FTOI4
            scalarOperands();
            for (int c = 0; c < 4; c++)
            {
                int32_t iv = vuFloatToInt(vsA[c], 16.0f);
                std::memcpy(&result[c], &iv, 4);
            }
            applyDest(vtDest, result, dest);
            return;
        case 0x16: // FTOI12
            scalarOperands();
            for (int c = 0; c < 4; c++)
            {
                int32_t iv = vuFloatToInt(vsA[c], 4096.0f);
                std::memcpy(&result[c], &iv, 4);
            }
            applyDest(vtDest, result, dest);
            return;
        case 0x17: // FTOI15
            scalarOperands();
            for (int c = 0; c < 4; c++)
            {
                int32_t iv = vuFloatToInt(vsA[c], 32768.0f);
                std::memcpy(&result[c], &iv, 4);
            }
            applyDest(vtDest, result, dest);
            return;
        case 0x18: case 0x19: case 0x1A: case 0x1B: kind = ArithMul; second = broadcastLane(vt, specialOp); break;   // MULAbc
        case 0x1C: kind = ArithMul; second = _mm_set1_ps(normalizeOperand(m_state.q)); break;                        // MULAq
        case 0x1D: // ABS
            scalarOperands();
            for (int c = 0; c < 4; c++)
                result[c] = std::fabs(vsA[c]);
            applyDest(vtDest, result, dest);
            return;
        case 0x1E: kind = ArithMul; second = _mm_set1_ps(normalizeOperand(m_state.i)); break;                        // MULAi
        case 0x1F: // CLIP
        {
            uint32_t wBits = 0u;
            std::memcpy(&wBits, &m_state.vf[ft][3], sizeof(wBits));
            const int32_t limit = (wBits & 0x7F800000u) != 0u ? static_cast<int32_t>(wBits & 0x7FFFFFFFu) : 0x007FFFFF;

            const auto exceedsClipPlane = [limit](float value, uint32_t signMask)
            {
                uint32_t bits = 0u;
                std::memcpy(&bits, &value, sizeof(bits));
                bits ^= signMask;
                int32_t orderedBits = 0;
                std::memcpy(&orderedBits, &bits, sizeof(orderedBits));
                return orderedBits > limit;
            };

            uint32_t flags = 0u;
            if (exceedsClipPlane(m_state.vf[fs][0], 0x00000000u))
                flags |= 0x01u;
            if (exceedsClipPlane(m_state.vf[fs][0], 0x80000000u))
                flags |= 0x02u;
            if (exceedsClipPlane(m_state.vf[fs][1], 0x00000000u))
                flags |= 0x04u;
            if (exceedsClipPlane(m_state.vf[fs][1], 0x80000000u))
                flags |= 0x08u;
            if (exceedsClipPlane(m_state.vf[fs][2], 0x00000000u))
                flags |= 0x10u;
            if (exceedsClipPlane(m_state.vf[fs][2], 0x80000000u))
                flags |= 0x20u;
            queueClip(flags);
            return;
        }
        case 0x20: kind = ArithAdd; second = _mm_set1_ps(normalizeOperand(m_state.q)); break;   // ADDAq
        case 0x21: kind = ArithMadd; second = _mm_set1_ps(normalizeOperand(m_state.q)); break;  // MADDAq
        case 0x22: kind = ArithAdd; second = _mm_set1_ps(normalizeOperand(m_state.i)); break;   // ADDAi
        case 0x23: kind = ArithMadd; second = _mm_set1_ps(normalizeOperand(m_state.i)); break;  // MADDAi
        case 0x24: kind = ArithSub; second = _mm_set1_ps(normalizeOperand(m_state.q)); break;   // SUBAq
        case 0x25: kind = ArithMsub; second = _mm_set1_ps(normalizeOperand(m_state.q)); break;  // MSUBAq
        case 0x26: kind = ArithSub; second = _mm_set1_ps(normalizeOperand(m_state.i)); break;   // SUBAi
        case 0x27: kind = ArithMsub; second = _mm_set1_ps(normalizeOperand(m_state.i)); break;  // MSUBAi
        case 0x28: kind = ArithAdd; second = vt; break;   // ADDA
        case 0x29: kind = ArithMadd; second = vt; break;  // MADDA
        case 0x2A: kind = ArithMul; second = vt; break;   // MULA
        case 0x2C: kind = ArithSub; second = vt; break;   // SUBA
        case 0x2D: kind = ArithMsub; second = vt; break;  // MSUBA
        case 0x2E: kind = ArithMul; opmul = true; break; // OPMULA
        case 0x2F:
        case 0x30: // NOP
            return;
        default:
            reportReservedInstruction(true, instr);
            return;
        }
    }

    if (kind == ArithNone)
    {
        reportReservedInstruction(true, instr);
        return;
    }

    __m128 first = vs;
    if (opmul)
    {
        // OPMULA: acc = vs.yzx * vt.zxy ; OPMSUB: acc - vs.yzx * vt.zxy ; the w lane is an exact zero
        // (its product still feeds the OPMSUB sticky flags, like the old path).
        first = _mm_shuffle_ps(vs, vs, _MM_SHUFFLE(3, 0, 2, 1));
        second = _mm_shuffle_ps(vt, vt, _MM_SHUFFLE(3, 1, 0, 2));
    }
    const __m128i destM = destMask4(dest);
    FmacResult out;
    switch (kind)
    {
    case ArithAdd:
        fmacSingle4<FmacAdd>(first, second, destM, out);
        break;
    case ArithSub:
        fmacSingle4<FmacSub>(first, second, destM, out);
        break;
    case ArithMul:
        fmacSingle4<FmacMul>(first, second, destM, out);
        break;
    case ArithMadd:
        fmacProductSum4<false>(normalize4(_mm_loadu_ps(m_state.acc)), first, second, destM, out);
        break;
    case ArithMsub:
        fmacProductSum4<true>(normalize4(_mm_loadu_ps(m_state.acc)), first, second, destM, out);
        break;
    default:
        break;
    }
    if (opmul && (dest & 0x1u) != 0u)
    {
        // w lane: exact zero (Z flag only, +0 stored).
        out.mac = (out.mac & ~0x1111u) | 0x0001u;
        const uint32_t xyzMac = out.mac & 0xEEEEu;
        out.status = 1u | (((xyzMac >> 4) & 0xFu) ? 2u : 0u) | (((xyzMac >> 8) & 0xFu) ? 4u : 0u) | (((xyzMac >> 12) & 0xFu) ? 8u : 0u);
        out.value = _mm_castsi128_ps(_mm_and_si128(_mm_castps_si128(out.value), _mm_set_epi32(0, -1, -1, -1)));
    }

    if (__builtin_expect(s_check, 0))
        checkFmac(instr, static_cast<uint8_t>(kind), opmul, first, second, out.value, out.mac, out.status, out.sticky);

    if (dest != 0u)
        pushFmacFlags(out.mac, out.status, out.sticky);
    float *target = toAcc ? m_state.acc : vd;
    const __m128i old = _mm_castps_si128(_mm_loadu_ps(target));
    const __m128i merged = _mm_or_si128(_mm_andnot_si128(destM, old), _mm_and_si128(destM, _mm_castps_si128(out.value)));
    _mm_storeu_ps(target, _mm_castsi128_ps(merged));
}
