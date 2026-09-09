#ifndef PS2_RUNTIME_MACROS_H
#define PS2_RUNTIME_MACROS_H
#include <cstdint>
#include <cmath>
#include <cstring>
#include <cstdio>
#include <cstdlib>
#include <chrono>
#include <bit>
#if defined(_MSC_VER)
#include <intrin.h>
#elif defined(USE_SSE2NEON)
#include "sse2neon.h"
#else
#include <immintrin.h> // For SSE/AVX intrinsics
#endif

#include "ps2_runtime.h"

static inline int32_t Ps2ExtractEpi32(__m128i v, int index)
{
    switch (index & 3)
    {
    case 0:
        return _mm_extract_epi32(v, 0);
    case 1:
        return _mm_extract_epi32(v, 1);
    case 2:
        return _mm_extract_epi32(v, 2);
    default:
        return _mm_extract_epi32(v, 3);
    }
}

static inline int64_t Ps2ExtractEpi64(__m128i v, int index)
{
    if ((index & 1) == 0)
    {
        return _mm_cvtsi128_si64(v);
    }
    else
    {
        return _mm_extract_epi64(v, 1);
    }
}

static inline uint32_t ps2_clz32(uint32_t x)
{
    return static_cast<uint32_t>(std::countl_zero(x));
}

static inline uint64_t Ps2HiLoToU64(uint64_t hi, uint64_t lo)
{
    return ((hi & 0xFFFFFFFFull) << 32) | (lo & 0xFFFFFFFFull);
}

static inline uint64_t Ps2SignExt32ToU64(uint32_t v)
{
    return (uint64_t)(int64_t)(int32_t)v;
}

// PLZCW: Count leading bits that match the sign bit, minus 1.
// For positive values: count leading zeros minus 1 (excludes sign bit).
// For negative values: count leading ones minus 1 (excludes sign bit).
// Special cases: 0x00000000 -> 31, 0xFFFFFFFF -> 31.
static inline uint32_t ps2_plzcw32(uint32_t x)
{
    if (x == 0 || x == 0xFFFFFFFF)
        return 31;
    if (x & 0x80000000u)
        x = ~x; // If sign bit set, invert to count leading ones as zeros
    return static_cast<uint32_t>(std::countl_zero(x)) - 1;
}

#define PS2_BLENDV_PS(a, b, mask) _mm_blendv_ps((a), (b), (mask))
#define PS2_MIN_EPI32(a, b) _mm_min_epi32((a), (b))
#define PS2_MAX_EPI32(a, b) _mm_max_epi32((a), (b))
#define PS2_SHUFFLE_EPI8(v, mask) _mm_shuffle_epi8((v), (mask))

#define PS2_EXTRACT_EPI32(v, i) Ps2ExtractEpi32((v), (i))
#define PS2_EXTRACT_EPI64(v, i) Ps2ExtractEpi64((v), (i))

#define PS2_EXTRACT_EPI32_0(v) Ps2ExtractEpi32((v), 0)
#define PS2_EXTRACT_EPI32_1(v) Ps2ExtractEpi32((v), 1)
#define PS2_EXTRACT_EPI32_2(v) Ps2ExtractEpi32((v), 2)
#define PS2_EXTRACT_EPI32_3(v) Ps2ExtractEpi32((v), 3)

#define PS2_EXTRACT_EPI64_0(v) Ps2ExtractEpi64((v), 0)
#define PS2_EXTRACT_EPI64_1(v) Ps2ExtractEpi64((v), 1)

// Basic MIPS arithmetic operations
#define ADD32(a, b) ((uint32_t)((a) + (b)))
#define ADD32_OV(rs, rt, result32, overflow)              \
    do                                                    \
    {                                                     \
        int32_t _a = (int32_t)(rs);                       \
        int32_t _b = (int32_t)(rt);                       \
        int32_t _r = _a + _b;                             \
        overflow = (((_a ^ _b) >= 0) && ((_a ^ _r) < 0)); \
        result32 = (uint32_t)_r;                          \
    } while (0);
#define SUB32(a, b) ((uint32_t)((a) - (b)))
#define SUB32_OV(rs, rt, result32, overflow)             \
    do                                                   \
    {                                                    \
        int32_t _a = (int32_t)(rs);                      \
        int32_t _b = (int32_t)(rt);                      \
        int32_t _r = _a - _b;                            \
        overflow = (((_a ^ _b) < 0) && ((_a ^ _r) < 0)); \
        result32 = (uint32_t)_r;                         \
    } while (0);
#define MUL32(a, b) ((uint32_t)((a) * (b)))
#define DIV32(a, b) ((uint32_t)((a) / (b)))
#define AND32(a, b) ((uint32_t)((a) & (b)))
#define OR32(a, b) ((uint32_t)((a) | (b)))
#define XOR32(a, b) ((uint32_t)((a) ^ (b)))
#define NOR32(a, b) ((uint32_t)(~((a) | (b))))
#define SLL32(a, b) ((uint32_t)((a) << (b)))
#define SRL32(a, b) ((uint32_t)((a) >> (b)))
#define SRA32(a, b) ((uint32_t)((int32_t)(a) >> (b)))
#define SLT32(a, b) ((uint32_t)((int32_t)(a) < (int32_t)(b) ? 1 : 0))
#define SLTU32(a, b) ((uint32_t)((a) < (b) ? 1 : 0))

// PS2-specific 128-bit MMI operations
#define PS2_PEXTLW(a, b) _mm_unpacklo_epi32((__m128i)(b), (__m128i)(a))
#define PS2_PEXTUW(a, b) _mm_unpackhi_epi32((__m128i)(b), (__m128i)(a))
#define PS2_PEXTLH(a, b) _mm_unpacklo_epi16((__m128i)(b), (__m128i)(a))
#define PS2_PEXTUH(a, b) _mm_unpackhi_epi16((__m128i)(b), (__m128i)(a))
#define PS2_PEXTLB(a, b) _mm_unpacklo_epi8((__m128i)(b), (__m128i)(a))
#define PS2_PEXTUB(a, b) _mm_unpackhi_epi8((__m128i)(b), (__m128i)(a))
#define PS2_PADDW(a, b) _mm_add_epi32((__m128i)(a), (__m128i)(b))
#define PS2_PSUBW(a, b) _mm_sub_epi32((__m128i)(a), (__m128i)(b))
#define PS2_PMAXW(a, b) PS2_MAX_EPI32((__m128i)(a), (__m128i)(b))
#define PS2_PMINW(a, b) PS2_MIN_EPI32((__m128i)(a), (__m128i)(b))
#define PS2_PADDH(a, b) _mm_add_epi16((__m128i)(a), (__m128i)(b))
#define PS2_PSUBH(a, b) _mm_sub_epi16((__m128i)(a), (__m128i)(b))
#define PS2_PMAXH(a, b) _mm_max_epi16((__m128i)(a), (__m128i)(b))
#define PS2_PMINH(a, b) _mm_min_epi16((__m128i)(a), (__m128i)(b))
#define PS2_PADDB(a, b) _mm_add_epi8((__m128i)(a), (__m128i)(b))
#define PS2_PSUBB(a, b) _mm_sub_epi8((__m128i)(a), (__m128i)(b))
#define PS2_PAND(a, b) _mm_and_si128((__m128i)(a), (__m128i)(b))
#define PS2_POR(a, b) _mm_or_si128((__m128i)(a), (__m128i)(b))
#define PS2_PXOR(a, b) _mm_xor_si128((__m128i)(a), (__m128i)(b))
#define PS2_PNOR(a, b) _mm_xor_si128(_mm_or_si128((__m128i)(a), (__m128i)(b)), _mm_set1_epi32(0xFFFFFFFF))

// PS2 VU (Vector Unit) operations.
// Like the EE FPU, the VUs have no infinities/NaNs: exponent-255 values behave as +/-FLT_MAX and
// denormals as +/-0, on inputs and results. Host SSE math is clamped the same way (PCSX2's
// "VU clamping"), or a single overflow turns into NaN and poisons everything downstream.
static inline __m128 ps2_vu_sat(__m128 v)
{
    const __m128i bits = _mm_castps_si128(v);
    const __m128i expMask = _mm_set1_epi32(0x7F800000);
    const __m128i exp = _mm_and_si128(bits, expMask);
    const __m128i infNan = _mm_cmpeq_epi32(exp, expMask);
    const __m128i denorm = _mm_cmpeq_epi32(exp, _mm_setzero_si128());
    const __m128i sign = _mm_and_si128(bits, _mm_set1_epi32(static_cast<int>(0x80000000u)));
    const __m128i maxv = _mm_or_si128(sign, _mm_set1_epi32(0x7F7FFFFF));
    __m128i r = _mm_or_si128(_mm_andnot_si128(infNan, bits), _mm_and_si128(infNan, maxv));
    r = _mm_or_si128(_mm_andnot_si128(denorm, r), _mm_and_si128(denorm, sign));
    return _mm_castsi128_ps(r);
}
// PS2X_FPU_TRAP=1 also reports VU0 macro-mode results that overflowed (a lane with exponent 255
// before clamping) and Q-register divisions by zero, with the guest pc (see ps2_fpu_trap_report).
void ps2_vu_trap_report(const char *what, __m128 v, const R5900Context *ctx);
inline __m128 ps2_vu_sat_traced(__m128 v, const R5900Context *ctx, const char *what)
{
    const __m128i bits = _mm_castps_si128(v);
    const __m128i expMask = _mm_set1_epi32(0x7F800000);
    const __m128i infNan = _mm_cmpeq_epi32(_mm_and_si128(bits, expMask), expMask);
    if (_mm_movemask_epi8(infNan) != 0)
        ps2_vu_trap_report(what, v, ctx);
    return ps2_vu_sat(v);
}
#define PS2_VADD(a, b) ps2_vu_sat_traced(_mm_add_ps(ps2_vu_sat((__m128)(a)), ps2_vu_sat((__m128)(b))), ctx, "vadd")
#define PS2_VSUB(a, b) ps2_vu_sat_traced(_mm_sub_ps(ps2_vu_sat((__m128)(a)), ps2_vu_sat((__m128)(b))), ctx, "vsub")
#define PS2_VMUL(a, b) ps2_vu_sat_traced(_mm_mul_ps(ps2_vu_sat((__m128)(a)), ps2_vu_sat((__m128)(b))), ctx, "vmul")
#define PS2_VDIV(a, b) ps2_vu_sat_traced(_mm_div_ps(ps2_vu_sat((__m128)(a)), ps2_vu_sat((__m128)(b))), ctx, "vdiv")
#define PS2_VMULQ(a, q) ps2_vu_sat_traced(_mm_mul_ps(ps2_vu_sat((__m128)(a)), _mm_set1_ps(ps2_fpu_sat(q))), ctx, "vmulq")
// Q-register ops (VDIV / VSQRT / VRSQRT): a zero divisor gives +/-FLT_MAX, the roots take |x|.
#define PS2_VDIVQ(fs, ft) ps2_fpu_div_traced((float)(fs), (float)(ft), ctx)
#define PS2_VSQRTQ(ft) ps2_fpu_sqrt_traced((float)(ft), ctx)
#define PS2_VRSQRTQ(fs, ft) ps2_fpu_div_traced((float)(fs), sqrtf(fabsf(ps2_fpu_sat((float)(ft)))), ctx)
#define PS2_VBLEND(a, b, mask) PS2_BLENDV_PS((__m128)(a), (__m128)(b), (__m128)(mask))

// VU0 macro-mode FMAC flags. Every ADD/SUB/MUL/MADD/MSUB/OPMULA/OPMSUB result (the lanes named
// in dest, x=8 y=4 z=2 w=1) rewrites the MAC flags (Z bits 0-3, S 4-7, U 8-11, O 12-15; x is
// the high bit of each nibble) and the STATUS flags (Z/S/U/O in bits 0-3, ORed into the sticky
// bits 6-9 until CTC2 clears them). Updated immediately: the EE reads them with CFC2 after the
// VNOPs the game inserts. MAX/MINI, FTOI/ITOF, MOVE/MR32 and ABS leave them alone, as on the
// hardware. The result was already saturated, so an overflow shows as +/-FLT_MAX.
static inline void ps2_vu0_fmac_flags(R5900Context *ctx, __m128 res, unsigned dest)
{
    alignas(16) uint32_t bits[4];
    _mm_store_si128(reinterpret_cast<__m128i *>(bits), _mm_castps_si128(res));
    uint32_t mac = 0u, status = 0u;
    for (unsigned c = 0; c < 4u; ++c)
    {
        const uint32_t lane = 1u << (3u - c);
        if ((dest & lane) == 0u)
            continue;
        const uint32_t b = bits[c];
        uint32_t f = 0u;
        if (((b >> 23) & 0xFFu) == 0u)
            f |= 1u; // zero (denormals were flushed to a signed zero)
        if ((b & 0x80000000u) != 0u)
            f |= 2u; // sign
        if ((b & 0x7FFFFFFFu) == 0x7F7FFFFFu)
            f |= 8u; // overflow (saturated)
        if (f & 1u)
            mac |= lane;
        if (f & 2u)
            mac |= lane << 4;
        if (f & 8u)
            mac |= lane << 12;
        status |= f;
    }
    ctx->vu0_mac_flags = mac;
    ctx->vu0_status = static_cast<uint16_t>((ctx->vu0_status & 0xFF0u) | status | (status << 6));
}

// Memory access helpers - Hybrid Fast/Slow Path
// Fast path: Direct RDRAM access (masked).
// Slow path: Full runtime->Load/Store

static inline bool Ps2FastRangeIsContiguous(uint32_t offset, uint32_t bytes)
{
    return offset <= (PS2_RAM_SIZE - bytes);
}

static inline uint8_t Ps2FastRead8(const uint8_t *rdram, uint32_t addr)
{
    return rdram[addr & PS2_RAM_MASK];
}

static inline uint16_t Ps2FastRead16(const uint8_t *rdram, uint32_t addr)
{
    const uint32_t offset = addr & PS2_RAM_MASK;
    if (!Ps2FastRangeIsContiguous(offset, sizeof(uint16_t)))
    {
        uint8_t wrapped[sizeof(uint16_t)];
        for (uint32_t i = 0; i < sizeof(uint16_t); ++i)
        {
            wrapped[i] = rdram[(offset + i) & PS2_RAM_MASK];
        }
        uint16_t value;
        std::memcpy(&value, wrapped, sizeof(value));
        return value;
    }

    uint16_t value;
    std::memcpy(&value, rdram + offset, sizeof(value));
    return value;
}

static inline uint32_t Ps2FastRead32(const uint8_t *rdram, uint32_t addr)
{
    const uint32_t offset = addr & PS2_RAM_MASK;
    if (!Ps2FastRangeIsContiguous(offset, sizeof(uint32_t)))
    {
        uint8_t wrapped[sizeof(uint32_t)];
        for (uint32_t i = 0; i < sizeof(uint32_t); ++i)
        {
            wrapped[i] = rdram[(offset + i) & PS2_RAM_MASK];
        }
        uint32_t value;
        std::memcpy(&value, wrapped, sizeof(value));
        return value;
    }

    uint32_t value;
    std::memcpy(&value, rdram + offset, sizeof(value));
    return value;
}

static inline uint64_t Ps2FastRead64(const uint8_t *rdram, uint32_t addr)
{
    const uint32_t offset = addr & PS2_RAM_MASK;
    if (!Ps2FastRangeIsContiguous(offset, sizeof(uint64_t)))
    {
        uint8_t wrapped[sizeof(uint64_t)];
        for (uint32_t i = 0; i < sizeof(uint64_t); ++i)
        {
            wrapped[i] = rdram[(offset + i) & PS2_RAM_MASK];
        }
        uint64_t value;
        std::memcpy(&value, wrapped, sizeof(value));
        return value;
    }

    uint64_t value;
    std::memcpy(&value, rdram + offset, sizeof(value));
    return value;
}

static inline __m128i Ps2FastRead128(const uint8_t *rdram, uint32_t addr)
{
    const uint32_t offset = addr & PS2_RAM_MASK;
    if (!Ps2FastRangeIsContiguous(offset, sizeof(__m128i)))
    {
        alignas(16) uint8_t wrapped[sizeof(__m128i)];
        for (uint32_t i = 0; i < sizeof(__m128i); ++i)
        {
            wrapped[i] = rdram[(offset + i) & PS2_RAM_MASK];
        }
        __m128i value;
        std::memcpy(&value, wrapped, sizeof(value));
        return value;
    }

    __m128i value;
    std::memcpy(&value, rdram + offset, sizeof(value));
    return value;
}

static inline void Ps2FastWrite8(uint8_t *rdram, uint32_t addr, uint8_t value)
{
    rdram[addr & PS2_RAM_MASK] = value;
}

static inline void Ps2FastWrite16(uint8_t *rdram, uint32_t addr, uint16_t value)
{
    const uint32_t offset = addr & PS2_RAM_MASK;
    if (!Ps2FastRangeIsContiguous(offset, sizeof(uint16_t)))
    {
        uint8_t wrapped[sizeof(uint16_t)];
        std::memcpy(wrapped, &value, sizeof(value));
        for (uint32_t i = 0; i < sizeof(uint16_t); ++i)
        {
            rdram[(offset + i) & PS2_RAM_MASK] = wrapped[i];
        }
        return;
    }
    std::memcpy(rdram + offset, &value, sizeof(value));
}

static inline void Ps2FastWrite32(uint8_t *rdram, uint32_t addr, uint32_t value)
{
    const uint32_t offset = addr & PS2_RAM_MASK;
    if (!Ps2FastRangeIsContiguous(offset, sizeof(uint32_t)))
    {
        uint8_t wrapped[sizeof(uint32_t)];
        std::memcpy(wrapped, &value, sizeof(value));
        for (uint32_t i = 0; i < sizeof(uint32_t); ++i)
        {
            rdram[(offset + i) & PS2_RAM_MASK] = wrapped[i];
        }
        return;
    }
    std::memcpy(rdram + offset, &value, sizeof(value));
}

static inline void Ps2FastWrite64(uint8_t *rdram, uint32_t addr, uint64_t value)
{
    const uint32_t offset = addr & PS2_RAM_MASK;
    if (!Ps2FastRangeIsContiguous(offset, sizeof(uint64_t)))
    {
        uint8_t wrapped[sizeof(uint64_t)];
        std::memcpy(wrapped, &value, sizeof(value));
        for (uint32_t i = 0; i < sizeof(uint64_t); ++i)
        {
            rdram[(offset + i) & PS2_RAM_MASK] = wrapped[i];
        }
        return;
    }
    std::memcpy(rdram + offset, &value, sizeof(value));
}

static inline void Ps2FastWrite128(uint8_t *rdram, uint32_t addr, __m128i value)
{
    const uint32_t offset = addr & PS2_RAM_MASK;
    if (!Ps2FastRangeIsContiguous(offset, sizeof(__m128i)))
    {
        alignas(16) uint8_t wrapped[sizeof(__m128i)];
        std::memcpy(wrapped, &value, sizeof(value));
        for (uint32_t i = 0; i < sizeof(__m128i); ++i)
        {
            rdram[(offset + i) & PS2_RAM_MASK] = wrapped[i];
        }
        return;
    }
    std::memcpy(rdram + offset, &value, sizeof(value));
}

#define FAST_READ8(addr) Ps2FastRead8(rdram, (uint32_t)(addr))
#define FAST_READ16(addr) Ps2FastRead16(rdram, (uint32_t)(addr))
#define FAST_READ32(addr) Ps2FastRead32(rdram, (uint32_t)(addr))
#define FAST_READ64(addr) Ps2FastRead64(rdram, (uint32_t)(addr))
#define FAST_READ128(addr) Ps2FastRead128(rdram, (uint32_t)(addr))

#define FAST_WRITE8(addr, val) Ps2FastWrite8(rdram, (uint32_t)(addr), (uint8_t)(val))
#define FAST_WRITE16(addr, val) Ps2FastWrite16(rdram, (uint32_t)(addr), (uint16_t)(val))
#define FAST_WRITE32(addr, val) Ps2FastWrite32(rdram, (uint32_t)(addr), (uint32_t)(val))
#define FAST_WRITE64(addr, val) Ps2FastWrite64(rdram, (uint32_t)(addr), (uint64_t)(val))
#define FAST_WRITE128(addr, val) Ps2FastWrite128(rdram, (uint32_t)(addr), (val))

#define READ8(addr) ([&]() -> uint8_t {                       \
    uint32_t _addr = (uint32_t)(addr);                        \
    return PS2Runtime::isSpecialAddress(_addr)                \
        ? runtime->Load8(rdram, ctx, _addr)                   \
        : FAST_READ8(_addr); }())

#define READ16(addr) ([&]() -> uint16_t {                     \
    uint32_t _addr = (uint32_t)(addr);                        \
    return PS2Runtime::isSpecialAddress(_addr)                \
        ? runtime->Load16(rdram, ctx, _addr)                  \
        : FAST_READ16(_addr); }())

#define READ32(addr) ([&]() -> uint32_t {                     \
    uint32_t _addr = (uint32_t)(addr);                        \
    return PS2Runtime::isSpecialAddress(_addr)                \
        ? runtime->Load32(rdram, ctx, _addr)                  \
        : FAST_READ32(_addr); }())

#define READ64(addr) ([&]() -> uint64_t {                     \
    uint32_t _addr = (uint32_t)(addr);                        \
    return PS2Runtime::isSpecialAddress(_addr)                \
        ? runtime->Load64(rdram, ctx, _addr)                  \
        : FAST_READ64(_addr); }())

#define READ128(addr) ([&]() -> __m128i {                     \
    uint32_t _addr = (uint32_t)(addr);                        \
    return PS2Runtime::isSpecialAddress(_addr)                \
        ? runtime->Load128(rdram, ctx, _addr)                 \
        : FAST_READ128(_addr); }())

#define WRITE8(addr, val)                                                            \
    do                                                                               \
    {                                                                                \
        uint32_t _addr = (addr);                                                     \
        if (PS2Runtime::isSpecialAddress(_addr))                                     \
            runtime->Store8(rdram, ctx, _addr, (val));                               \
        else                                                                         \
        {                                                                            \
            ps2TraceGuestWrite(rdram, _addr, 1u, (uint8_t)(val), 0u, "WRITE8", ctx); \
            FAST_WRITE8(_addr, (val));                                               \
        }                                                                            \
    } while (0)

#define WRITE16(addr, val)                                                             \
    do                                                                                 \
    {                                                                                  \
        uint32_t _addr = (addr);                                                       \
        if (PS2Runtime::isSpecialAddress(_addr))                                       \
            runtime->Store16(rdram, ctx, _addr, (val));                                \
        else                                                                           \
        {                                                                              \
            ps2TraceGuestWrite(rdram, _addr, 2u, (uint16_t)(val), 0u, "WRITE16", ctx); \
            FAST_WRITE16(_addr, (val));                                                \
        }                                                                              \
    } while (0)

#define WRITE32(addr, val)                                                             \
    do                                                                                 \
    {                                                                                  \
        uint32_t _addr = (addr);                                                       \
        if (PS2Runtime::isSpecialAddress(_addr))                                       \
            runtime->Store32(rdram, ctx, _addr, (val));                                \
        else                                                                           \
        {                                                                              \
            ps2TraceGuestWrite(rdram, _addr, 4u, (uint32_t)(val), 0u, "WRITE32", ctx); \
            FAST_WRITE32(_addr, (val));                                                \
        }                                                                              \
    } while (0)

#define WRITE64(addr, val)                                                             \
    do                                                                                 \
    {                                                                                  \
        uint32_t _addr = (addr);                                                       \
        if (PS2Runtime::isSpecialAddress(_addr))                                       \
            runtime->Store64(rdram, ctx, _addr, (val));                                \
        else                                                                           \
        {                                                                              \
            ps2TraceGuestWrite(rdram, _addr, 8u, (uint64_t)(val), 0u, "WRITE64", ctx); \
            FAST_WRITE64(_addr, (val));                                                \
        }                                                                              \
    } while (0)

#define WRITE128(addr, val)                                                          \
    do                                                                               \
    {                                                                                \
        uint32_t _addr = (addr);                                                     \
        __m128i _value = (val);                                                      \
        if (PS2Runtime::isSpecialAddress(_addr))                                     \
            runtime->Store128(rdram, ctx, _addr, _value);                            \
        else                                                                         \
        {                                                                            \
            const uint64_t _lo = static_cast<uint64_t>(PS2_EXTRACT_EPI64_0(_value)); \
            const uint64_t _hi = static_cast<uint64_t>(PS2_EXTRACT_EPI64_1(_value)); \
            ps2TraceGuestWrite(rdram, _addr, 16u, _lo, _hi, "WRITE128", ctx);        \
            FAST_WRITE128(_addr, _value);                                            \
        }                                                                            \
    } while (0)

// Scratchpad (0x70000000, 16 KB) fast path. The scratchpad is a "special" address, so every
// access went through runtime->Load/Store -> PS2Memory::read/write -> range checks + the DMAC
// handler drain (a mutex and two vector swaps per store). SOCOM II builds all of its GS packets in
// the scratchpad (FUN_00350950 / FUN_003b4580 / FUN_003643b0 ...), hundreds of thousands of
// stores per frame: the mission ran at 3 flips/s, and the camera spring (dt from timer T0)
// exploded. Accesses that stay inside the 16 KB touch the host buffer directly.
static inline uint8_t *Ps2SprPtr(uint32_t addr, uint32_t size)
{
    const uint32_t off = (addr & 0x7FFFFFFFu) - PS2_SCRATCHPAD_BASE;
    if (off < PS2_SCRATCHPAD_SIZE && off + size <= PS2_SCRATCHPAD_SIZE)
    {
        uint8_t *base = ps2GetScratchpadHostPtr();
        return base ? base + off : nullptr;
    }
    return nullptr;
}
#define PS2_SPR_READ(T, addr, slowExpr) ([&]() -> T {                                     \
    uint32_t _a = (uint32_t)(addr);                                                     \
    if (const uint8_t *_spr = Ps2SprPtr(_a, (uint32_t)sizeof(T)))                       \
    {                                                                                   \
        T _v;                                                                           \
        std::memcpy(&_v, _spr, sizeof(T));                                              \
        return _v;                                                                      \
    }                                                                                   \
    return slowExpr(_a); }())
#undef READ8
#undef READ16
#undef READ32
#undef READ64
#undef READ128
#define PS2_READ8_SLOW(_addr) (PS2Runtime::isSpecialAddress(_addr) ? runtime->Load8(rdram, ctx, _addr) : FAST_READ8(_addr))
#define PS2_READ16_SLOW(_addr) (PS2Runtime::isSpecialAddress(_addr) ? runtime->Load16(rdram, ctx, _addr) : FAST_READ16(_addr))
#define PS2_READ32_SLOW(_addr) (PS2Runtime::isSpecialAddress(_addr) ? runtime->Load32(rdram, ctx, _addr) : FAST_READ32(_addr))
#define PS2_READ64_SLOW(_addr) (PS2Runtime::isSpecialAddress(_addr) ? runtime->Load64(rdram, ctx, _addr) : FAST_READ64(_addr))
#define PS2_READ128_SLOW(_addr) (PS2Runtime::isSpecialAddress(_addr) ? runtime->Load128(rdram, ctx, _addr) : FAST_READ128(_addr))
#define READ8(addr) PS2_SPR_READ(uint8_t, addr, PS2_READ8_SLOW)
#define READ16(addr) PS2_SPR_READ(uint16_t, addr, PS2_READ16_SLOW)
#define READ32(addr) PS2_SPR_READ(uint32_t, addr, PS2_READ32_SLOW)
#define READ64(addr) PS2_SPR_READ(uint64_t, addr, PS2_READ64_SLOW)
#define READ128(addr) PS2_SPR_READ(__m128i, addr, PS2_READ128_SLOW)
#define PS2_SPR_WRITE(T, addr, val, slowStmt)                                           \
    do                                                                                  \
    {                                                                                   \
        uint32_t _a = (uint32_t)(addr);                                                 \
        T _v = (T)(val);                                                                \
        if (uint8_t *_spr = Ps2SprPtr(_a, (uint32_t)sizeof(T)))                         \
            std::memcpy(_spr, &_v, sizeof(T));                                          \
        else                                                                            \
            slowStmt(_a, _v);                                                           \
    } while (0)
#undef WRITE8
#undef WRITE16
#undef WRITE32
#undef WRITE64
#undef WRITE128
#define PS2_WRITE8_SLOW(_a, _v) do { if (PS2Runtime::isSpecialAddress(_a)) runtime->Store8(rdram, ctx, _a, _v); else FAST_WRITE8(_a, _v); } while (0)
#define PS2_WRITE16_SLOW(_a, _v) do { if (PS2Runtime::isSpecialAddress(_a)) runtime->Store16(rdram, ctx, _a, _v); else FAST_WRITE16(_a, _v); } while (0)
#define PS2_WRITE32_SLOW(_a, _v) do { if (PS2Runtime::isSpecialAddress(_a)) runtime->Store32(rdram, ctx, _a, _v); else FAST_WRITE32(_a, _v); } while (0)
#define PS2_WRITE64_SLOW(_a, _v) do { if (PS2Runtime::isSpecialAddress(_a)) runtime->Store64(rdram, ctx, _a, _v); else FAST_WRITE64(_a, _v); } while (0)
#define PS2_WRITE128_SLOW(_a, _v) do { if (PS2Runtime::isSpecialAddress(_a)) runtime->Store128(rdram, ctx, _a, _v); else FAST_WRITE128(_a, _v); } while (0)
#define WRITE8(addr, val) PS2_SPR_WRITE(uint8_t, addr, val, PS2_WRITE8_SLOW)
#define WRITE16(addr, val) PS2_SPR_WRITE(uint16_t, addr, val, PS2_WRITE16_SLOW)
#define WRITE32(addr, val) PS2_SPR_WRITE(uint32_t, addr, val, PS2_WRITE32_SLOW)
#define WRITE64(addr, val) PS2_SPR_WRITE(uint64_t, addr, val, PS2_WRITE64_SLOW)
#define WRITE128(addr, val) PS2_SPR_WRITE(__m128i, addr, val, PS2_WRITE128_SLOW)

// Packed Compare Greater Than (PCGT)
#define PS2_PCGTW(a, b) _mm_cmpgt_epi32((__m128i)(a), (__m128i)(b))
#define PS2_PCGTH(a, b) _mm_cmpgt_epi16((__m128i)(a), (__m128i)(b))
#define PS2_PCGTB(a, b) _mm_cmpgt_epi8((__m128i)(a), (__m128i)(b))

// Packed Add with Signed Saturation Word (PADDSW)
inline __m128i ps2_paddsw(__m128i a, __m128i b)
{

    __m128i sum = _mm_add_epi32(a, b);
    // Check for over/underflow. Clamp to either INT32_MIN/INT32_MAX.
    __m128i overflow = _mm_and_si128(_mm_xor_si128(a, sum),
                                     _mm_xor_si128(b, sum));
    // Extract input sign.
    overflow = _mm_srai_epi32(overflow, 31);
    __m128i input_sign = _mm_srai_epi32(a, 31);
    // Select saturation value based on overflow sign.
    #if defined(__SSE4_1__)
    __m128i sat = _mm_blendv_epi8(
        _mm_set1_epi32(INT32_MAX),
        _mm_set1_epi32(INT32_MIN),
        input_sign);
    return _mm_blendv_epi8(sum, sat, overflow);
    #else
    __m128i sat = _mm_or_si128(_mm_and_si128(input_sign, _mm_set1_epi32(INT32_MIN)),
                               _mm_andnot_si128(input_sign, _mm_set1_epi32(INT32_MAX)));
    return _mm_or_si128(_mm_and_si128(overflow, sat),
                        _mm_andnot_si128(overflow, sum));
    #endif
}
#define PS2_PADDSW(a, b) ps2_paddsw((__m128i)(a), (__m128i)(b))

// Packed Subtract with Signed Saturation Word (PSUBSW)
inline __m128i ps2_psubsw(__m128i a, __m128i b)
{
    __m128i diff = _mm_sub_epi32(a, b);
    // Check for over/underflow. Clamp to either INT32_MIN/INT32_MAX.
    __m128i overflow = _mm_and_si128(_mm_xor_si128(a, b),
                                     _mm_xor_si128(a, diff));
    // Extract input sign.
    overflow = _mm_srai_epi32(overflow, 31);
    __m128i input_sign = _mm_srai_epi32(a, 31);
    // Select saturation value based on overflow sign.
    #if defined(__SSE4_1__)
    __m128i sat = _mm_blendv_epi8(
        _mm_set1_epi32(INT32_MAX),
        _mm_set1_epi32(INT32_MIN),
        input_sign);
    return _mm_blendv_epi8(diff, sat, overflow);
    #else
    __m128i sat = _mm_or_si128(_mm_and_si128(input_sign, _mm_set1_epi32(INT32_MIN)),
                               _mm_andnot_si128(input_sign, _mm_set1_epi32(INT32_MAX)));
    return _mm_or_si128(_mm_and_si128(overflow, sat),
                        _mm_andnot_si128(overflow, diff));
    #endif

}
#define PS2_PSUBSW(a, b) ps2_psubsw((__m128i)(a), (__m128i)(b))

// Packed Compare Equal (PCEQ)
#define PS2_PCEQW(a, b) _mm_cmpeq_epi32((__m128i)(a), (__m128i)(b))
#define PS2_PCEQH(a, b) _mm_cmpeq_epi16((__m128i)(a), (__m128i)(b))
#define PS2_PCEQB(a, b) _mm_cmpeq_epi8((__m128i)(a), (__m128i)(b))

// Packed Absolute (PABS)
#define PS2_PABSW(a) _mm_abs_epi32((__m128i)(a))
#define PS2_PABSH(a) _mm_abs_epi16((__m128i)(a))
#define PS2_PABSB(a) _mm_abs_epi8((__m128i)(a))

// Packed Pack (PPAC) - Packs larger elements into smaller ones
inline __m128i ps2_paddu32(__m128i a, __m128i b)
{
    __m128i sum = _mm_add_epi32(a, b);
    __m128i overflow = _mm_cmpgt_epi32(_mm_xor_si128(a, _mm_set1_epi32(INT32_MIN)),
                                       _mm_xor_si128(sum, _mm_set1_epi32(INT32_MIN)));
    return _mm_or_si128(sum, overflow); // overflow lanes become all-1s
}
inline __m128i ps2_psubu32(__m128i a, __m128i b)
{
    __m128i diff = _mm_sub_epi32(a, b);
    // Underflow if a < b (unsigned). Clamp to 0.
    __m128i underflow = _mm_cmpgt_epi32(_mm_xor_si128(b, _mm_set1_epi32(INT32_MIN)),
                                        _mm_xor_si128(a, _mm_set1_epi32(INT32_MIN)));
    return _mm_andnot_si128(underflow, diff); // underflow lanes become 0
}

inline __m128i ps2_ppacw(__m128i rs, __m128i rt)
{
    // rs = [rs3 rs2 rs1 rs0], rt = [rt3 rt2 rt1 rt0]
    return _mm_castps_si128(_mm_shuffle_ps(_mm_castsi128_ps(rt), _mm_castsi128_ps(rs), _MM_SHUFFLE(2, 0, 2, 0)));
}
#define PS2_PPACW(a, b) ps2_ppacw((__m128i)(a), (__m128i)(b))

inline __m128i ps2_ppach(__m128i rs, __m128i rt)
{
    const __m128i mask = _mm_setr_epi8(
        0, 1, 4, 5, 8, 9, 12, 13,  // from rt: halfwords 0,2,4,6
        0, 1, 4, 5, 8, 9, 12, 13); // from rs: halfwords 0,2,4,6
    __m128i lo = _mm_shuffle_epi8(rt, mask);
    __m128i hi = _mm_shuffle_epi8(rs, mask);
    return _mm_unpacklo_epi64(lo, hi);
}
#define PS2_PPACH(a, b) ps2_ppach((__m128i)(a), (__m128i)(b))

inline __m128i ps2_ppacb(__m128i rs, __m128i rt)
{
    const __m128i mask = _mm_setr_epi8(
        0, 2, 4, 6, 8, 10, 12, 14,  // from rt: bytes 0,2,4,6,8,10,12,14
        0, 2, 4, 6, 8, 10, 12, 14); // from rs
    __m128i lo = _mm_shuffle_epi8(rt, mask);
    __m128i hi = _mm_shuffle_epi8(rs, mask);
    return _mm_unpacklo_epi64(lo, hi);
}
#define PS2_PPACB(a, b) ps2_ppacb((__m128i)(a), (__m128i)(b))

// Packed Interleave (PINT)
#define PS2_PINTH(a, b) _mm_unpacklo_epi16(_mm_shuffle_epi32((__m128i)(b), _MM_SHUFFLE(3, 2, 1, 0)), _mm_shuffle_epi32((__m128i)(a), _MM_SHUFFLE(3, 2, 1, 0)))
#define PS2_PINTEH(a, b) _mm_unpackhi_epi16(_mm_shuffle_epi32((__m128i)(b), _MM_SHUFFLE(3, 2, 1, 0)), _mm_shuffle_epi32((__m128i)(a), _MM_SHUFFLE(3, 2, 1, 0)))

// Packed Multiply-Add (PMADD)
#define PS2_PMADDW(a, b) _mm_add_epi32(_mm_mullo_epi32(_mm_shuffle_epi32((__m128i)(a), _MM_SHUFFLE(1, 0, 3, 2)), _mm_shuffle_epi32((__m128i)(b), _MM_SHUFFLE(1, 0, 3, 2))), _mm_mullo_epi32(_mm_shuffle_epi32((__m128i)(a), _MM_SHUFFLE(3, 2, 1, 0)), _mm_shuffle_epi32((__m128i)(b), _MM_SHUFFLE(3, 2, 1, 0))))

// Packed Variable Shifts
#define PS2_PSLLVW(a, b) _mm_custom_sllv_epi32((__m128i)(a), (__m128i)(b))
#define PS2_PSRLVW(a, b) _mm_custom_srlv_epi32((__m128i)(a), (__m128i)(b))
#define PS2_PSRAVW(a, b) _mm_custom_srav_epi32((__m128i)(a), (__m128i)(b))

inline __m128i _mm_custom_sllv_epi32(__m128i a, __m128i count)
{
    alignas(16) int32_t a_arr[4];
    alignas(16) int32_t count_arr[4];
    alignas(16) int32_t result[4];

    std::memcpy(a_arr, &a, sizeof(a));
    std::memcpy(count_arr, &count, sizeof(count));

    for (int i = 0; i < 4; i++)
    {
        result[i] = a_arr[i] << (count_arr[i] & 0x1F);
    }

    __m128i out;
    std::memcpy(&out, result, sizeof(out));
    return out;
}

inline __m128i _mm_custom_srlv_epi32(__m128i a, __m128i count)
{
    int32_t a_arr[4], count_arr[4], result[4];
    _mm_storeu_si128((__m128i *)a_arr, a);
    _mm_storeu_si128((__m128i *)count_arr, count);
    for (int i = 0; i < 4; i++)
    {
        result[i] = (uint32_t)a_arr[i] >> (count_arr[i] & 0x1F);
    }
    return _mm_loadu_si128((__m128i *)result);
}

inline __m128i _mm_custom_srav_epi32(__m128i a, __m128i count)
{
    int32_t a_arr[4], count_arr[4], result[4];
    _mm_storeu_si128((__m128i *)a_arr, a);
    _mm_storeu_si128((__m128i *)count_arr, count);
    for (int i = 0; i < 4; i++)
    {
        result[i] = a_arr[i] >> (count_arr[i] & 0x1F);
    }
    return _mm_loadu_si128((__m128i *)result);
}

// PMFHL function implementations
inline __m128i ps2_u64_to_epi64_pair(uint64_t value)
{
    return _mm_set1_epi64x(static_cast<long long>(value));
}

#define PS2_PMFHL_LW(hi, lo) _mm_unpacklo_epi64(ps2_u64_to_epi64_pair(lo), ps2_u64_to_epi64_pair(hi))
#define PS2_PMFHL_UW(hi, lo) _mm_unpackhi_epi64(ps2_u64_to_epi64_pair(lo), ps2_u64_to_epi64_pair(hi))
#define PS2_PMFHL_SLW(hi, lo) _mm_packs_epi32(ps2_u64_to_epi64_pair(lo), ps2_u64_to_epi64_pair(hi))
#define PS2_PMFHL_LH(hi, lo) _mm_shuffle_epi32(_mm_packs_epi32(ps2_u64_to_epi64_pair(lo), ps2_u64_to_epi64_pair(hi)), _MM_SHUFFLE(3, 1, 2, 0))
#define PS2_PMFHL_SH(hi, lo) _mm_shufflehi_epi16(_mm_shufflelo_epi16(_mm_packs_epi32(ps2_u64_to_epi64_pair(lo), ps2_u64_to_epi64_pair(hi)), _MM_SHUFFLE(3, 1, 2, 0)), _MM_SHUFFLE(3, 1, 2, 0))

// FPU (COP1) operations. Comparisons flush denormals first: the EE FPU treats them as zero
// (an axis-angle length of 1e-40 must take the `length == 0` guard, as on the console).
// The EE FPU is not IEEE: it has no infinities and no NaNs. Overflow saturates to +/-FLT_MAX,
// a zero (or denormal) divisor yields +/-FLT_MAX, denormals are flushed to zero and SQRT takes
// |x|. Host IEEE math then diverges silently: SOCOM II's fog setup does 255 - near * (-255 /
// (far - near)); with far == near the PS2 gets 255 (0 * -FLT_MAX = -0), IEEE gets NaN
// (0 * -inf), and the NaN spreads through the camera object.
inline float ps2_fpu_sat(float v)
{
    uint32_t bits;
    std::memcpy(&bits, &v, sizeof(bits));
    const uint32_t exp = bits & 0x7F800000u;
    if (exp == 0x7F800000u)          // inf / NaN -> +/-FLT_MAX
        bits = (bits & 0x80000000u) | 0x7F7FFFFFu;
    else if (exp == 0u)              // zero / denormal -> +/-0
        bits &= 0x80000000u;
    std::memcpy(&v, &bits, sizeof(v));
    return v;
}
inline float ps2_fpu_div(float a, float b)
{
    uint32_t bb;
    std::memcpy(&bb, &b, sizeof(bb));
    if ((bb & 0x7F800000u) == 0u)   // divisor zero/denormal: +/-FLT_MAX with the quotient's sign
    {
        uint32_t ab;
        std::memcpy(&ab, &a, sizeof(ab));
        const uint32_t sign = (ab ^ bb) & 0x80000000u;
        const uint32_t out = sign | 0x7F7FFFFFu;
        float r;
        std::memcpy(&r, &out, sizeof(r));
        return r;
    }
    return ps2_fpu_sat(ps2_fpu_sat(a) / b);
}
// PS2X_FPU_TRAP=1: print the guest pc of the first divisions by zero and square roots of a
// saturated operand (the first overflow in a divergence chain: a quantity that is zero here and
// not on the console). Cheap when off (one predictable branch on the slow paths only).
// PS2X_FPU_TRAP=<seconds>: report only after that much host time (the boot and menus have
// legitimate divisions by zero: fog with far == near, the flip's 1/0). 300 reports per kind.
inline bool ps2_fpu_trap_enabled()
{
    static const double s_after = [] { const char *e = std::getenv("PS2X_FPU_TRAP"); return e ? std::atof(e) : -1.0; }();
    if (s_after < 0.0)
        return false;
    static const auto s_epoch = std::chrono::steady_clock::now();
    return std::chrono::duration<double>(std::chrono::steady_clock::now() - s_epoch).count() >= s_after;
}
// Per-site cap (5 reports per guest pc) with the host time, so one benign site cannot exhaust
// the budget and the first occurrence of every site is visible in time order.
bool ps2_fpu_trap_site_ok(uint32_t pc);   // ps2_runtime.cpp: one shared per-site table (an inline
                                          // function's statics got duplicated per unity batch)
inline double ps2_fpu_trap_time()
{
    static const auto s_epoch = std::chrono::steady_clock::now();
    return std::chrono::duration<double>(std::chrono::steady_clock::now() - s_epoch).count();
}
inline void ps2_fpu_trap_report(const char *what, float a, float b, const R5900Context *ctx)
{
    if (!ps2_fpu_trap_site_ok(ctx->pc))
        return;
    std::fprintf(stderr, "[fpu-trap] %.3fs %s a=%g b=%g pc=0x%x ra=0x%x\n", ps2_fpu_trap_time(), what, (double)a, (double)b,
                 ctx->pc, (uint32_t)_mm_cvtsi128_si32(ctx->r[31]));
}
inline float ps2_fpu_div_traced(float a, float b, const R5900Context *ctx)
{
    uint32_t bb;
    std::memcpy(&bb, &b, sizeof(bb));
    if ((bb & 0x7F800000u) == 0u && ps2_fpu_trap_enabled())
        ps2_fpu_trap_report("div-by-zero", a, b, ctx);
    return ps2_fpu_div(a, b);
}
inline float ps2_fpu_sqrt_traced(float a, const R5900Context *ctx)
{
    const float v = ps2_fpu_sat(a);
    if (std::fabs(v) >= 3.0e38f && ps2_fpu_trap_enabled())
        ps2_fpu_trap_report("sqrt-of-max", v, 0.0f, ctx);
    return ps2_fpu_sat(sqrtf(fabsf(v)));
}
#define FPU_SET_ACC(ctx, res) (ctx->f_acc = res)
#define FPU_ADD_S(a, b) ps2_fpu_sat(ps2_fpu_sat((float)(a)) + ps2_fpu_sat((float)(b)))
#define FPU_SUB_S(a, b) ps2_fpu_sat(ps2_fpu_sat((float)(a)) - ps2_fpu_sat((float)(b)))
#define FPU_MUL_S(a, b) ps2_fpu_sat(ps2_fpu_sat((float)(a)) * ps2_fpu_sat((float)(b)))
#define FPU_DIV_S(a, b) ps2_fpu_div_traced((float)(a), (float)(b), ctx)
#define FPU_SQRT_S(a) ps2_fpu_sqrt_traced((float)(a), ctx)
// EE RSQRT.S fd, fs, ft: fd = fs / sqrt(|ft|) (SQRT.S fd, ft reads ft too — the translator used fs).
#define FPU_RSQRT_S(fs, ft) ps2_fpu_div_traced((float)(fs), sqrtf(fabsf(ps2_fpu_sat((float)(ft)))), ctx)
#define FPU_ABS_S(a) fabsf((float)(a))
#define FPU_MOV_S(a) ((float)(a))
#define FPU_NEG_S(a) (-(float)(a))
#define FPU_ROUND_L_S(a) ((int64_t)roundf((float)(a)))
#define FPU_TRUNC_L_S(a) ((int64_t)(float)(a))
#define FPU_CEIL_L_S(a) ((int64_t)ceilf((float)(a)))
#define FPU_FLOOR_L_S(a) ((int64_t)floorf((float)(a)))
#define FPU_ROUND_W_S(a) ((int32_t)nearbyintf((float)(a)))
#define FPU_TRUNC_W_S(a) ((int32_t)(float)(a))
#define FPU_CEIL_W_S(a) ((int32_t)ceilf((float)(a)))
#define FPU_FLOOR_W_S(a) ((int32_t)floorf((float)(a)))
#define FPU_CVT_S_W(a) ((float)(int32_t)(a))
#define FPU_CVT_S_L(a) ((float)(int64_t)(a))
// EE cvt.w.s truncates toward zero and saturates (|x| >= 2^31 -> 0x7FFFFFFF / 0x80000000), the
// FCR31 rounding mode is not applied — the same as PCSX2's CVT_W. Rounding to nearest here made
// every float->int of the form (int)(pos / cell) land one cell off half of the time.
static inline int32_t ps2_fpu_cvt_w(float v)
{
    uint32_t bits;
    std::memcpy(&bits, &v, sizeof(bits));
    if ((bits & 0x7F800000u) <= 0x4E800000u)   // |v| < 2^31 (and not inf/NaN)
        return static_cast<int32_t>(v);
    return (bits & 0x80000000u) ? static_cast<int32_t>(0x80000000u) : 0x7FFFFFFF;
}
#define FPU_CVT_W_S(a) ps2_fpu_cvt_w((float)(a))
#define FPU_CVT_L_S(a) ((int64_t)(float)(a))
#define FPU_C_F_S(a, b) (0)
#define FPU_C_UN_S(a, b) (isnan(ps2_fpu_sat((float)(a))) || isnan(ps2_fpu_sat((float)(b))))
#define FPU_C_EQ_S(a, b) (ps2_fpu_sat((float)(a)) == ps2_fpu_sat((float)(b)))
#define FPU_C_UEQ_S(a, b) (ps2_fpu_sat((float)(a)) == ps2_fpu_sat((float)(b)) || isnan(ps2_fpu_sat((float)(a))) || isnan(ps2_fpu_sat((float)(b))))
#define FPU_C_OLT_S(a, b) (ps2_fpu_sat((float)(a)) < ps2_fpu_sat((float)(b)))
#define FPU_C_ULT_S(a, b) (ps2_fpu_sat((float)(a)) < ps2_fpu_sat((float)(b)) || isnan(ps2_fpu_sat((float)(a))) || isnan(ps2_fpu_sat((float)(b))))
#define FPU_C_OLE_S(a, b) (ps2_fpu_sat((float)(a)) <= ps2_fpu_sat((float)(b)))
#define FPU_C_ULE_S(a, b) (ps2_fpu_sat((float)(a)) <= ps2_fpu_sat((float)(b)) || isnan(ps2_fpu_sat((float)(a))) || isnan(ps2_fpu_sat((float)(b))))
#define FPU_C_SF_S(a, b) (0)
#define FPU_C_NGLE_S(a, b) (isnan(ps2_fpu_sat((float)(a))) || isnan(ps2_fpu_sat((float)(b))))
#define FPU_C_SEQ_S(a, b) (ps2_fpu_sat((float)(a)) == ps2_fpu_sat((float)(b)))
#define FPU_C_NGL_S(a, b) (ps2_fpu_sat((float)(a)) == ps2_fpu_sat((float)(b)) || isnan(ps2_fpu_sat((float)(a))) || isnan(ps2_fpu_sat((float)(b))))
#define FPU_C_LT_S(a, b) (ps2_fpu_sat((float)(a)) < ps2_fpu_sat((float)(b)))
#define FPU_C_NGE_S(a, b) (ps2_fpu_sat((float)(a)) < ps2_fpu_sat((float)(b)) || isnan(ps2_fpu_sat((float)(a))) || isnan(ps2_fpu_sat((float)(b))))
#define FPU_C_LE_S(a, b) (ps2_fpu_sat((float)(a)) <= ps2_fpu_sat((float)(b)))
#define FPU_C_NGT_S(a, b) (ps2_fpu_sat((float)(a)) <= ps2_fpu_sat((float)(b)) || isnan(ps2_fpu_sat((float)(a))) || isnan(ps2_fpu_sat((float)(b))))

// QFSRV: Quadword Funnel Shift Right Variable
// Concatenates rs || rt (256 bits) and right-shifts by SA bits, taking lower 128 bits.
inline __m128i ps2_qfsrv(__m128i rs, __m128i rt, uint32_t sa)
{
    if (sa == 0)
        return rt;
    if (sa >= 128)
    {
        if (sa >= 256)
            return _mm_setzero_si128();
        uint32_t shift = sa - 128;
        if (shift == 0)
            return rs;
        // Shift rs right by (sa-128) bits
        uint32_t byteShift = shift / 8;
        uint32_t bitShift = shift % 8;
        // Byte shift rs right
        alignas(16) uint8_t buf[16] = {};
        alignas(16) uint8_t src[16];
        _mm_store_si128((__m128i *)src, rs);
        for (uint32_t i = 0; i + byteShift < 16; i++)
            buf[i] = src[i + byteShift];
        __m128i result = _mm_load_si128((__m128i *)buf);
        if (bitShift > 0)
            result = _mm_or_si128(_mm_srli_epi64(result, bitShift),
                                  _mm_slli_epi64(_mm_bsrli_si128(result, 8), 64 - bitShift));
        return result;
    }
    // sa is 1..127: result = (rs || rt) >> sa, lower 128 bits
    uint32_t byteShift = sa / 8;
    uint32_t bitShift = sa % 8;
    alignas(16) uint8_t combined[32];
    _mm_store_si128((__m128i *)(combined), rt);      // low 128 bits
    _mm_store_si128((__m128i *)(combined + 16), rs); // high 128 bits
    // Shift right by byteShift bytes
    alignas(16) uint8_t shifted[16];
    for (uint32_t i = 0; i < 16; i++)
        shifted[i] = (i + byteShift < 32) ? combined[i + byteShift] : 0;
    __m128i result = _mm_load_si128((__m128i *)shifted);
    if (bitShift > 0)
    {
        uint8_t extra = (byteShift + 16 < 32) ? combined[byteShift + 16] : 0;
        __m128i hi_byte = _mm_insert_epi8(_mm_setzero_si128(), extra, 15);
        alignas(16) uint8_t src32[32];
        for (uint32_t i = 0; i < 32; i++)
            src32[i] = combined[i];
        uint64_t lo0, lo1, hi0, hi1;
        std::memcpy(&lo0, src32, 8);
        std::memcpy(&lo1, src32 + 8, 8);
        std::memcpy(&hi0, src32 + 16, 8);
        std::memcpy(&hi1, src32 + 24, 8);
        // 256-bit right shift by sa bits
        uint64_t r0, r1;
        if (sa < 64)
        {
            r0 = (lo0 >> sa) | (lo1 << (64 - sa));
            r1 = (lo1 >> sa) | (hi0 << (64 - sa));
        }
        else if (sa < 128)
        {
            uint32_t s = sa - 64;
            if (s == 0)
            {
                r0 = lo1;
                r1 = hi0;
            }
            else
            {
                r0 = (lo1 >> s) | (hi0 << (64 - s));
                r1 = (hi0 >> s) | (hi1 << (64 - s));
            }
        }
        else
        {
            r0 = 0;
            r1 = 0; // handled above
        }
        result = _mm_set_epi64x((long long)r1, (long long)r0);
    }
    return result;
}
#define PS2_QFSRV(rs, rt, sa) ps2_qfsrv((__m128i)(rs), (__m128i)(rt), (uint32_t)(sa))
#define PS2_PCPYLD(rs, rt) _mm_unpacklo_epi64(rt, rs)
#define PS2_PEXEH(rs) _mm_shufflelo_epi16(_mm_shufflehi_epi16(rs, _MM_SHUFFLE(2, 3, 0, 1)), _MM_SHUFFLE(2, 3, 0, 1))
#define PS2_PEXEW(rs) _mm_shuffle_epi32(rs, _MM_SHUFFLE(2, 3, 0, 1))
#define PS2_PROT3W(rs) _mm_shuffle_epi32(rs, _MM_SHUFFLE(0, 3, 2, 1))

// Additional VU0 operations
#define PS2_VSQRT(x) sqrtf(x)
#define PS2_VRSQRT(x) (1.0f / sqrtf(x))

#define GPR_U32(ctx_ptr, reg_idx) ((reg_idx == 0) ? 0U : static_cast<uint32_t>(PS2_EXTRACT_EPI32_0(ctx_ptr->r[reg_idx])))
#define GPR_S32(ctx_ptr, reg_idx) ((reg_idx == 0) ? 0 : PS2_EXTRACT_EPI32_0(ctx_ptr->r[reg_idx]))
#define GPR_U64(ctx_ptr, reg_idx) ((reg_idx == 0) ? 0ULL : static_cast<uint64_t>(PS2_EXTRACT_EPI64_0(ctx_ptr->r[reg_idx])))
#define GPR_S64(ctx_ptr, reg_idx) ((reg_idx == 0) ? 0LL : PS2_EXTRACT_EPI64_0(ctx_ptr->r[reg_idx]))
#define GPR_VEC(ctx_ptr, reg_idx) ((reg_idx == 0) ? _mm_setzero_si128() : ctx_ptr->r[reg_idx])

static inline void Ps2SetGprLow64(R5900Context *ctx, int reg, __m128i new_low)
{
    if (reg != 0)
    {
        ctx->r[reg] = _mm_castpd_si128(_mm_move_sd(_mm_castsi128_pd(ctx->r[reg]), _mm_castsi128_pd(new_low)));
    }
}

#define SET_GPR_U32(ctx_ptr, reg_idx, val)                                \
    do                                                                    \
    {                                                                     \
        if ((reg_idx) != 0)                                               \
        {                                                                 \
            __m128i _newVal = _mm_cvtsi64_si128((int64_t)(int32_t)(val)); \
                                                                          \
            Ps2SetGprLow64(ctx_ptr, reg_idx, _newVal);                    \
        }                                                                 \
    } while (0)

#define SET_GPR_S32(ctx_ptr, reg_idx, val)                                \
    do                                                                    \
    {                                                                     \
        if ((reg_idx) != 0)                                               \
        {                                                                 \
            __m128i _newVal = _mm_cvtsi64_si128((int64_t)(int32_t)(val)); \
            Ps2SetGprLow64(ctx_ptr, reg_idx, _newVal);                    \
        }                                                                 \
    } while (0)

#define SET_GPR_U64(ctx_ptr, reg_idx, val)                       \
    do                                                           \
    {                                                            \
        if ((reg_idx) != 0)                                      \
        {                                                        \
            __m128i _newVal = _mm_cvtsi64_si128((int64_t)(val)); \
            Ps2SetGprLow64(ctx_ptr, reg_idx, _newVal);           \
        }                                                        \
    } while (0)

#define SET_GPR_S64(ctx_ptr, reg_idx, val) SET_GPR_U64(ctx_ptr, reg_idx, val)

#define SET_GPR_VEC(ctx_ptr, reg_idx, val) \
    do                                     \
    {                                      \
        if (reg_idx != 0)                  \
            ctx_ptr->r[reg_idx] = (val);   \
    } while (0)

#endif // PS2_RUNTIME_MACROS_H
