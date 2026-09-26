#include "Common.h"
#include "LibC.h"
#include "ps2_log.h"

namespace ps2_stubs
{
    namespace
    {
        uint32_t sanitizeMemTransferSize(uint32_t size, const char *op)
        {
            constexpr uint32_t kMaxTransfer = PS2_RAM_SIZE;
            if (size <= kMaxTransfer)
            {
                return size;
            }

            static std::mutex s_warnMutex;
            static std::unordered_map<std::string, uint32_t> s_warnCounts;
            uint32_t warnCount = 0u;
            {
                std::lock_guard<std::mutex> lock(s_warnMutex);
                warnCount = ++s_warnCounts[op ? op : "memop"];
            }
            if (warnCount <= 16u)
            {
                std::cerr << "[" << (op ? op : "memop") << "] size clamp from 0x"
                          << std::hex << size << " to 0x" << kMaxTransfer
                          << std::dec << std::endl;
            }
            return kMaxTransfer;
        }

        uint32_t guestContiguousBytes(uint32_t guestAddr)
        {
            uint32_t offset = 0u;
            bool scratch = false;
            if (!ps2ResolveGuestPointer(guestAddr, offset, scratch))
            {
                return 0u;
            }
            if (scratch)
            {
                return (offset < PS2_SCRATCHPAD_SIZE) ? (PS2_SCRATCHPAD_SIZE - offset) : 0u;
            }
            return (offset < PS2_RAM_SIZE) ? (PS2_RAM_SIZE - offset) : 0u;
        }

        // ---- soft-float double ABI -------------------------------------------------
        //
        // SOCOM II's libm ships two families. The `*f` routines are genuine float code and
        // pass their argument in $f12 (they are full of cop1/lwc1 -- see __kernel_sinf at
        // 0x1B28F8). The unsuffixed routines are the *double soft-float* family: the
        // argument arrives as a 64-bit IEEE-754 bit pattern in $a0, the result leaves in
        // $v0, and they touch no FPU register at all. Disassembly of all five addresses
        // this file binds (cos 0x1B2C88, fabs 0x1B2DB0, floor 0x1B2DE8, sin 0x1B3000,
        // tan 0x1B3138) contains zero cop1/lwc1/swc1 instructions; fabs is literally
        //
        //     daddu v0,a0,zero ; dsra32 v0,v0,0 ; and v0,v0,0x7fffffff
        //     and a0,a0,0xffffffff ; dsll32 v0,v0,0 ; or a0,a0,v0 ; daddu v0,a0,zero
        //
        // i.e. clear the sign bit of a 64-bit pattern. A stub that reads $f12 and writes
        // $f0 therefore leaves $v0 untouched and every caller consumes whatever the
        // previous call happened to leave there.
        //
        // The helpers beneath these five (dpadd 0x1A0B58, dpdiv 0x1A0EA0, fptodp
        // 0x1A0720, dptofp 0x1A12D8, __kernel_sin/cos/tan, __ieee754_rem_pio2) are NOT
        // stubbed -- they run as recompiled guest code and already honour this ABI, so
        // the pattern in $a0 is a real double and the pattern we put in $v0 is consumed
        // as one.
        inline uint64_t softDoubleArgBits(const R5900Context *ctx, int reg)
        {
            return GPR_U64(ctx, reg);
        }

        inline double bitsToDouble(uint64_t bits)
        {
            double value;
            std::memcpy(&value, &bits, sizeof(value));
            return value;
        }

        inline uint64_t doubleToBits(double value)
        {
            uint64_t bits;
            std::memcpy(&bits, &value, sizeof(bits));
            return bits;
        }

        inline void setSoftDoubleReturn(R5900Context *ctx, uint64_t bits)
        {
            // The guest returns the whole pattern in $v0 and writes nothing else that a
            // caller may rely on, so do exactly that -- do not also poke $v1.
            SET_GPR_U64(ctx, 2, bits);
        }

        constexpr uint64_t kDoubleSignMask = 0x8000000000000000ull;
        constexpr uint64_t kDoubleExpMask = 0x7FF0000000000000ull;
        constexpr uint64_t kDoubleMantMask = 0x000FFFFFFFFFFFFFull;
        constexpr uint64_t kDoubleQuietBit = 0x0008000000000000ull;

        inline bool isDoubleNanBits(uint64_t bits)
        {
            return (bits & kDoubleExpMask) == kDoubleExpMask && (bits & kDoubleMantMask) != 0ull;
        }

    }

    void malloc(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint32_t size = getRegU32(ctx, 4); // $a0
        const uint32_t guestAddr = runtime ? runtime->guestMalloc(size) : 0u;
        setReturnU32(ctx, guestAddr);
    }

    void memalign(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint32_t alignment = getRegU32(ctx, 4); // $a0
        const uint32_t size = getRegU32(ctx, 5);      // $a1
        const uint32_t guestAddr = runtime ? runtime->guestMalloc(size, alignment) : 0u;
        setReturnU32(ctx, guestAddr);
    }

    void free(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint32_t guestAddr = getRegU32(ctx, 4); // $a0
        if (runtime && guestAddr != 0u)
        {
            runtime->guestFree(guestAddr);
        }
    }

    void calloc(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint32_t count = getRegU32(ctx, 4); // $a0
        const uint32_t size = getRegU32(ctx, 5);  // $a1
        const uint32_t guestAddr = runtime ? runtime->guestCalloc(count, size) : 0u;
        setReturnU32(ctx, guestAddr);
    }

    void realloc(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint32_t oldGuestAddr = getRegU32(ctx, 4); // $a0
        const uint32_t newSize = getRegU32(ctx, 5);      // $a1
        const uint32_t newGuestAddr = runtime ? runtime->guestRealloc(oldGuestAddr, newSize) : 0u;
        setReturnU32(ctx, newGuestAddr);
    }

    void memcpy(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint32_t destAddr = getRegU32(ctx, 4); // $a0
        uint32_t srcAddr = getRegU32(ctx, 5);  // $a1
        uint32_t size = getRegU32(ctx, 6);     // $a2
        size = sanitizeMemTransferSize(size, "memcpy");

        uint32_t copied = 0u;
        uint32_t curDst = destAddr;
        uint32_t curSrc = srcAddr;
        while (copied < size)
        {
            uint8_t *hostDest = getMemPtr(rdram, curDst);
            const uint8_t *hostSrc = getConstMemPtr(rdram, curSrc);
            if (!hostDest || !hostSrc)
            {
                break;
            }

            uint32_t chunk = size - copied;
            chunk = std::min(chunk, guestContiguousBytes(curDst));
            chunk = std::min(chunk, guestContiguousBytes(curSrc));
            if (chunk == 0u)
            {
                break;
            }

            ::memcpy(hostDest, hostSrc, chunk);
            copied += chunk;
            curDst += chunk;
            curSrc += chunk;
        }

        if (copied != 0u)
        {
            ps2TraceGuestRangeWrite(rdram, destAddr, copied, "memcpy", ctx);
        }

        // returns dest pointer ($v0 = $a0)
        ctx->r[2] = ctx->r[4];
    }

    void memset(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint32_t destAddr = getRegU32(ctx, 4);       // $a0
        int value = (int)(getRegU32(ctx, 5) & 0xFF); // $a1 (char value)
        uint32_t size = getRegU32(ctx, 6);           // $a2
        size = sanitizeMemTransferSize(size, "memset");

        uint32_t written = 0u;
        uint32_t curDst = destAddr;
        while (written < size)
        {
            uint8_t *hostDest = getMemPtr(rdram, curDst);
            if (!hostDest)
            {
                break;
            }

            uint32_t chunk = size - written;
            chunk = std::min(chunk, guestContiguousBytes(curDst));
            if (chunk == 0u)
            {
                break;
            }

            ::memset(hostDest, value, chunk);
            written += chunk;
            curDst += chunk;
        }

        if (written != 0u)
        {
            ps2TraceGuestRangeWrite(rdram, destAddr, written, "memset", ctx);
        }

        // returns dest pointer ($v0 = $a0)
        ctx->r[2] = ctx->r[4];
    }

    void memclr(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint32_t destAddr = getRegU32(ctx, 4); // $a0
        uint32_t size = getRegU32(ctx, 5);     // $a1
        size = sanitizeMemTransferSize(size, "memclr");

        uint32_t written = 0u;
        uint32_t curDst = destAddr;
        while (written < size)
        {
            uint8_t *hostDest = getMemPtr(rdram, curDst);
            if (!hostDest)
            {
                break;
            }

            uint32_t chunk = size - written;
            chunk = std::min(chunk, guestContiguousBytes(curDst));
            if (chunk == 0u)
            {
                break;
            }

            ::memset(hostDest, 0, chunk);
            written += chunk;
            curDst += chunk;
        }

        if (written != 0u)
        {
            ps2TraceGuestRangeWrite(rdram, destAddr, written, "memclr", ctx);
        }

        ctx->r[2] = ctx->r[4];
    }

    void memmove(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint32_t destAddr = getRegU32(ctx, 4); // $a0
        uint32_t srcAddr = getRegU32(ctx, 5);  // $a1
        uint32_t size = getRegU32(ctx, 6);     // $a2
        size = sanitizeMemTransferSize(size, "memmove");

        uint32_t copied = 0u;
        std::vector<uint8_t> tmp;
        tmp.reserve(size);
        for (uint32_t i = 0u; i < size; ++i)
        {
            const uint8_t *src = getConstMemPtr(rdram, srcAddr + i);
            if (!src)
            {
                break;
            }
            tmp.push_back(*src);
        }

        for (uint32_t i = 0u; i < static_cast<uint32_t>(tmp.size()); ++i)
        {
            uint8_t *dst = getMemPtr(rdram, destAddr + i);
            if (!dst)
            {
                break;
            }
            *dst = tmp[i];
            ++copied;
        }

        if (copied != 0u)
        {
            ps2TraceGuestRangeWrite(rdram, destAddr, copied, "memmove", ctx);
        }

        // returns dest pointer ($v0 = $a0)
        ctx->r[2] = ctx->r[4];
    }

    void memcmp(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint32_t ptr1Addr = getRegU32(ctx, 4); // $a0
        uint32_t ptr2Addr = getRegU32(ctx, 5); // $a1
        uint32_t size = getRegU32(ctx, 6);     // $a2
        size = sanitizeMemTransferSize(size, "memcmp");
        int result = 0;

        for (uint32_t i = 0u; i < size; ++i)
        {
            const uint8_t *lhs = getConstMemPtr(rdram, ptr1Addr + i);
            const uint8_t *rhs = getConstMemPtr(rdram, ptr2Addr + i);
            if (!lhs || !rhs)
            {
                result = (!lhs && !rhs) ? 0 : (lhs ? 1 : -1);
                break;
            }
            if (*lhs != *rhs)
            {
                result = static_cast<int>(*lhs) - static_cast<int>(*rhs);
                break;
            }
        }
        setReturnS32(ctx, result);
    }

    void strcpy(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint32_t destAddr = getRegU32(ctx, 4); // $a0
        uint32_t srcAddr = getRegU32(ctx, 5);  // $a1

        char *hostDest = reinterpret_cast<char *>(getMemPtr(rdram, destAddr));
        const char *hostSrc = reinterpret_cast<const char *>(getConstMemPtr(rdram, srcAddr));

        if (hostDest && hostSrc)
        {
            ::strcpy(hostDest, hostSrc);
            ps2TraceGuestRangeWrite(rdram, destAddr, static_cast<uint32_t>(::strlen(hostSrc) + 1u), "strcpy", ctx);
        }
        else
        {
            std::cerr << "strcpy error: Invalid address provided."
                      << " Dest: 0x" << std::hex << destAddr << " (host ptr valid: " << (hostDest != nullptr) << ")"
                      << ", Src: 0x" << srcAddr << " (host ptr valid: " << (hostSrc != nullptr) << ")" << std::dec
                      << std::endl;
        }

        // returns dest pointer ($v0 = $a0)
        ctx->r[2] = ctx->r[4];
    }

    void strncpy(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint32_t destAddr = getRegU32(ctx, 4); // $a0
        uint32_t srcAddr = getRegU32(ctx, 5);  // $a1
        uint32_t size = getRegU32(ctx, 6);     // $a2

        char *hostDest = reinterpret_cast<char *>(getMemPtr(rdram, destAddr));
        const char *hostSrc = reinterpret_cast<const char *>(getConstMemPtr(rdram, srcAddr));

        if (hostDest && hostSrc)
        {
            ::strncpy(hostDest, hostSrc, size);
            ps2TraceGuestRangeWrite(rdram, destAddr, size, "strncpy", ctx);
        }
        else
        {
            std::cerr << "strncpy error: Invalid address provided."
                      << " Dest: 0x" << std::hex << destAddr << " (host ptr valid: " << (hostDest != nullptr) << ")"
                      << ", Src: 0x" << srcAddr << " (host ptr valid: " << (hostSrc != nullptr) << ")" << std::dec
                      << std::endl;
        }
        // returns dest pointer ($v0 = $a0)
        ctx->r[2] = ctx->r[4];
    }

    void strlen(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint32_t strAddr = getRegU32(ctx, 4); // $a0
        const char *hostStr = reinterpret_cast<const char *>(getConstMemPtr(rdram, strAddr));
        size_t len = 0;

        if (hostStr)
        {
            len = ::strlen(hostStr);
        }
        else
        {
            std::cerr << "strlen error: Invalid address provided: 0x" << std::hex << strAddr << std::dec << std::endl;
        }
        setReturnU32(ctx, (uint32_t)len);
    }

    void strcmp(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint32_t str1Addr = getRegU32(ctx, 4); // $a0
        uint32_t str2Addr = getRegU32(ctx, 5); // $a1

        const char *hostStr1 = reinterpret_cast<const char *>(getConstMemPtr(rdram, str1Addr));
        const char *hostStr2 = reinterpret_cast<const char *>(getConstMemPtr(rdram, str2Addr));
        int result = 0;

        if (hostStr1 && hostStr2)
        {
            result = ::strcmp(hostStr1, hostStr2);
        }
        else
        {
            std::cerr << "strcmp error: Invalid address provided."
                      << " Str1: 0x" << std::hex << str1Addr << " (host ptr valid: " << (hostStr1 != nullptr) << ")"
                      << ", Str2: 0x" << str2Addr << " (host ptr valid: " << (hostStr2 != nullptr) << ")" << std::dec
                      << std::endl;
            // Return non-zero on error, consistent with memcmp error handling
            result = (hostStr1 == nullptr) - (hostStr2 == nullptr);
            if (result == 0 && hostStr1 == nullptr)
                result = 1; // Both null -> treat as different? Or 0? Let's say different.
        }
        setReturnS32(ctx, result);
    }

    void strncmp(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint32_t str1Addr = getRegU32(ctx, 4); // $a0
        uint32_t str2Addr = getRegU32(ctx, 5); // $a1
        uint32_t size = getRegU32(ctx, 6);     // $a2

        const char *hostStr1 = reinterpret_cast<const char *>(getConstMemPtr(rdram, str1Addr));
        const char *hostStr2 = reinterpret_cast<const char *>(getConstMemPtr(rdram, str2Addr));
        int result = 0;

        if (hostStr1 && hostStr2)
        {
            result = ::strncmp(hostStr1, hostStr2, size);
        }
        else
        {
            std::cerr << "strncmp error: Invalid address provided."
                      << " Str1: 0x" << std::hex << str1Addr << " (host ptr valid: " << (hostStr1 != nullptr) << ")"
                      << ", Str2: 0x" << str2Addr << " (host ptr valid: " << (hostStr2 != nullptr) << ")" << std::dec
                      << std::endl;
            result = (hostStr1 == nullptr) - (hostStr2 == nullptr);
            if (result == 0 && hostStr1 == nullptr)
                result = 1; // Both null -> different
        }
        setReturnS32(ctx, result);
    }

    void strcat(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint32_t destAddr = getRegU32(ctx, 4); // $a0
        uint32_t srcAddr = getRegU32(ctx, 5);  // $a1

        char *hostDest = reinterpret_cast<char *>(getMemPtr(rdram, destAddr));
        const char *hostSrc = reinterpret_cast<const char *>(getConstMemPtr(rdram, srcAddr));

        if (hostDest && hostSrc)
        {
            ::strcat(hostDest, hostSrc);
        }
        else
        {
            std::cerr << "strcat error: Invalid address provided."
                      << " Dest: 0x" << std::hex << destAddr << " (host ptr valid: " << (hostDest != nullptr) << ")"
                      << ", Src: 0x" << srcAddr << " (host ptr valid: " << (hostSrc != nullptr) << ")" << std::dec
                      << std::endl;
        }

        // returns dest pointer ($v0 = $a0)
        ctx->r[2] = ctx->r[4];
    }

    void strncat(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint32_t destAddr = getRegU32(ctx, 4); // $a0
        uint32_t srcAddr = getRegU32(ctx, 5);  // $a1
        uint32_t size = getRegU32(ctx, 6);     // $a2

        char *hostDest = reinterpret_cast<char *>(getMemPtr(rdram, destAddr));
        const char *hostSrc = reinterpret_cast<const char *>(getConstMemPtr(rdram, srcAddr));

        if (hostDest && hostSrc)
        {
            ::strncat(hostDest, hostSrc, size);
        }
        else
        {
            std::cerr << "strncat error: Invalid address provided."
                      << " Dest: 0x" << std::hex << destAddr << " (host ptr valid: " << (hostDest != nullptr) << ")"
                      << ", Src: 0x" << srcAddr << " (host ptr valid: " << (hostSrc != nullptr) << ")" << std::dec
                      << std::endl;
        }

        // returns dest pointer ($v0 = $a0)
        ctx->r[2] = ctx->r[4];
    }

    void strchr(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint32_t strAddr = getRegU32(ctx, 4);            // $a0
        int char_code = (int)(getRegU32(ctx, 5) & 0xFF); // $a1 (char value)

        const char *hostStr = reinterpret_cast<const char *>(getConstMemPtr(rdram, strAddr));
        char *foundPtr = nullptr;
        uint32_t resultAddr = 0;

        if (hostStr)
        {
            foundPtr = ::strchr(const_cast<char *>(hostStr), char_code);
            if (foundPtr)
            {
                resultAddr = hostPtrToPs2Addr(rdram, foundPtr);
            }
        }
        else
        {
            std::cerr << "strchr error: Invalid address provided: 0x" << std::hex << strAddr << std::dec << std::endl;
        }

        // returns PS2 address or 0 (NULL)
        setReturnU32(ctx, resultAddr);
    }

    void strrchr(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint32_t strAddr = getRegU32(ctx, 4);            // $a0
        int char_code = (int)(getRegU32(ctx, 5) & 0xFF); // $a1 (char value)

        const char *hostStr = reinterpret_cast<const char *>(getConstMemPtr(rdram, strAddr));
        char *foundPtr = nullptr;
        uint32_t resultAddr = 0;

        if (hostStr)
        {
            foundPtr = ::strrchr(const_cast<char *>(hostStr), char_code); // Use const_cast carefully
            if (foundPtr)
            {
                resultAddr = hostPtrToPs2Addr(rdram, foundPtr);
            }
        }
        else
        {
            std::cerr << "strrchr error: Invalid address provided: 0x" << std::hex << strAddr << std::dec << std::endl;
        }

        // returns PS2 address or 0 (NULL)
        setReturnU32(ctx, resultAddr);
    }

    void strstr(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint32_t haystackAddr = getRegU32(ctx, 4); // $a0
        uint32_t needleAddr = getRegU32(ctx, 5);   // $a1

        const char *hostHaystack = reinterpret_cast<const char *>(getConstMemPtr(rdram, haystackAddr));
        const char *hostNeedle = reinterpret_cast<const char *>(getConstMemPtr(rdram, needleAddr));
        char *foundPtr = nullptr;
        uint32_t resultAddr = 0;

        if (hostHaystack && hostNeedle)
        {
            foundPtr = ::strstr(const_cast<char *>(hostHaystack), hostNeedle);
            if (foundPtr)
            {
                resultAddr = hostPtrToPs2Addr(rdram, foundPtr);
            }
        }
        else
        {
            std::cerr << "strstr error: Invalid address provided."
                      << " Haystack: 0x" << std::hex << haystackAddr << " (host ptr valid: " << (hostHaystack != nullptr) << ")"
                      << ", Needle: 0x" << needleAddr << " (host ptr valid: " << (hostNeedle != nullptr) << ")" << std::dec
                      << std::endl;
        }

        // returns PS2 address or 0 (NULL)
        setReturnU32(ctx, resultAddr);
    }

    void printf(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint32_t format_addr = getRegU32(ctx, 4); // $a0
        const std::string formatOwned = readPs2CStringBounded(rdram, runtime, format_addr, 1024);
        int ret = -1;

        if (format_addr != 0)
        {
            std::string rendered = formatPs2StringWithArgs(rdram, ctx, runtime, formatOwned.c_str(), 1);
            if (rendered.size() > 2048)
            {
                rendered.resize(2048);
            }
            PS2_IF_AGRESSIVE_LOGS({
                const std::string logLine = sanitizeForLog(rendered);
                uint32_t count = 0;
                {
                    StubLogRuntimeState &stubLog = stubLogRuntimeStateFor(runtime);
                    std::lock_guard<std::mutex> lock(stubLog.printfMutex);
                    count = ++stubLog.printfLogCount;
                }
                if (count <= kMaxPrintfLogs)
                {
                    RUNTIME_LOG("PS2 printf: " << logLine);
                    RUNTIME_LOG(std::flush);
                }
                else if (count == kMaxPrintfLogs + 1)
                {
                    std::cerr << "PS2 printf logging suppressed after " << kMaxPrintfLogs << " lines" << std::endl;
                }
            });
            ret = static_cast<int>(rendered.size());
        }
        else
        {
            std::cerr << "printf error: Invalid format string address provided: 0x" << std::hex << format_addr << std::dec << std::endl;
        }

        // returns the number of characters written, or negative on error.
        setReturnS32(ctx, ret);
    }

    void sprintf(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint32_t str_addr = getRegU32(ctx, 4);     // $a0
        uint32_t format_addr = getRegU32(ctx, 5);  // $a1
        constexpr size_t kSafeSprintfBytes = 256u; // Keep guest stack temporaries from being overwritten.

        const std::string formatOwned = readPs2CStringBounded(rdram, runtime, format_addr, 1024);
        int ret = -1;

        if (format_addr != 0)
        {
            const uint32_t watchBase = ps2PathWatchPhysAddr();
            const uint32_t watchEnd = watchBase + PS2_PATH_WATCH_BYTES;
            const uint32_t dest = str_addr & PS2_RAM_MASK;
            const bool touchesWatch = dest < watchEnd && dest >= watchBase;
            static uint32_t watchSprintfLogCount = 0;
            if (touchesWatch && watchSprintfLogCount < 64u)
            {
                const uint32_t arg0 = getRegU32(ctx, 6);
                const uint32_t arg1 = getRegU32(ctx, 7);
                RUNTIME_LOG("[watch:sprintf] dest=0x" << std::hex << str_addr
                                                      << " fmt@0x" << format_addr
                                                      << " arg0=0x" << arg0
                                                      << " arg1=0x" << arg1
                                                      << " fmt=\"" << sanitizeForLog(readPs2CStringBounded(rdram, runtime, format_addr, 64)) << "\""
                                                      << " s0=\"" << sanitizeForLog(readPs2CStringBounded(rdram, runtime, arg0, 64)) << "\""
                                                      << " s1=\"" << sanitizeForLog(readPs2CStringBounded(rdram, runtime, arg1, 64)) << "\""
                                                      << std::dec << std::endl);
                ++watchSprintfLogCount;
            }

            std::string rendered = formatPs2StringWithArgs(rdram, ctx, runtime, formatOwned.c_str(), 2);
            if (rendered.size() >= kSafeSprintfBytes)
            {
                rendered.resize(kSafeSprintfBytes - 1);
            }
            const size_t writeLen = rendered.size() + 1u;
            if (writeGuestBytes(rdram, runtime, str_addr, reinterpret_cast<const uint8_t *>(rendered.c_str()), writeLen))
            {
                ps2TraceGuestRangeWrite(rdram, str_addr, static_cast<uint32_t>(writeLen), "sprintf", ctx);
                ret = static_cast<int>(rendered.size());
            }
            else
            {
                std::cerr << "sprintf error: Failed to write destination buffer at 0x"
                          << std::hex << str_addr << std::dec << std::endl;
            }
        }
        else
        {
            std::cerr << "sprintf error: Invalid format address provided."
                      << " Dest: 0x" << std::hex << str_addr
                      << ", Format: 0x" << format_addr << std::dec
                      << std::endl;
        }

        // returns the number of characters written (excluding null), or negative on error.
        setReturnS32(ctx, ret);
    }

    void snprintf(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint32_t str_addr = getRegU32(ctx, 4);    // $a0
        size_t size = getRegU32(ctx, 5);          // $a1
        uint32_t format_addr = getRegU32(ctx, 6); // $a2
        const std::string formatOwned = readPs2CStringBounded(rdram, runtime, format_addr, 1024);
        int ret = -1;

        if (format_addr != 0)
        {
            std::string rendered = formatPs2StringWithArgs(rdram, ctx, runtime, formatOwned.c_str(), 3);
            ret = static_cast<int>(rendered.size());

            if (size > 0)
            {
                const size_t copyLen = std::min<size_t>(size - 1, rendered.size());
                std::vector<uint8_t> output(copyLen + 1u, 0u);
                if (copyLen > 0u)
                {
                    std::memcpy(output.data(), rendered.data(), copyLen);
                }
                if (writeGuestBytes(rdram, runtime, str_addr, output.data(), output.size()))
                {
                    ps2TraceGuestRangeWrite(rdram, str_addr, static_cast<uint32_t>(output.size()), "snprintf", ctx);
                }
                else
                {
                    std::cerr << "snprintf error: Failed to write destination buffer at 0x"
                              << std::hex << str_addr << std::dec << std::endl;
                    ret = -1;
                }
            }
        }
        else
        {
            std::cerr << "snprintf error: Invalid address provided or size is zero."
                      << " Dest: 0x" << std::hex << str_addr
                      << ", Format: 0x" << format_addr << std::dec
                      << ", Size: " << size << std::endl;
        }

        // returns the number of characters that *would* have been written
        // if size was large enough (excluding null), or negative on error.
        setReturnS32(ctx, ret);
    }

    void puts(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint32_t strAddr = getRegU32(ctx, 4); // $a0
        const char *hostStr = reinterpret_cast<const char *>(getConstMemPtr(rdram, strAddr));
        int result = EOF;

        if (hostStr)
        {
            result = std::puts(hostStr); // std::puts adds a newline
            std::fflush(stdout);         // Ensure output appears
        }
        else
        {
            std::cerr << "puts error: Invalid address provided: 0x" << std::hex << strAddr << std::dec << std::endl;
        }

        // returns non-negative on success, EOF on error.
        setReturnS32(ctx, result >= 0 ? 0 : -1); // PS2 might expect 0/-1 rather than EOF
    }

    void fopen(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint32_t pathAddr = getRegU32(ctx, 4); // $a0
        uint32_t modeAddr = getRegU32(ctx, 5); // $a1

        const char *guestPath = reinterpret_cast<const char *>(getConstMemPtr(rdram, pathAddr));
        const char *hostMode = reinterpret_cast<const char *>(getConstMemPtr(rdram, modeAddr));
        uint32_t file_handle = 0;

        if (guestPath && hostMode)
        {
            // Issue #53 (Sprint 13 U2's class, upstream #239): the guest path goes through the same
            // translation as the fio calls -- host0:/cdrom0:/mc0: pick hostRoot/cdRoot/mcRoot, a bare
            // path is the CD's -- and so through resolvePs2PathUnderRoot's lexical walk (links resolved
            // for the memory-card root only, ruling S13-R8). A '..' above the root, a drive letter or
            // a Windows device name comes back empty and the guest gets NULL, as libc fopen reports
            // for a path it cannot open. It used to go to the host fopen verbatim, relative to the
            // process's working directory. SOCOM II binds nothing to this stub (its newlib _fopen_r
            // reaches the host through the fio calls); any image whose ELF or analyzer names a
            // function `fopen` binds here by name (ps2_call_list.h PS2_STUB_LIST).
            const std::string hostPathStr = translatePs2Path(guestPath);
            if (hostPathStr.empty())
            {
                static std::atomic<bool> warned{false};
                if (!warned.exchange(true))
                {
                    std::cerr << "ps2_stub fopen: refused '" << sanitizeForLog(guestPath)
                              << "': it does not stay under its root (logged once)" << std::endl;
                }
                setReturnU32(ctx, 0);
                return;
            }
            const char *hostPath = hostPathStr.c_str();
            RUNTIME_LOG("ps2_stub fopen: path='" << guestPath << "' -> '" << hostPath << "', mode='" << hostMode << "'");
            FILE *fp = ::fopen(hostPath, hostMode);
            if (fp)
            {
                LibCRuntimeState &files = libcRuntimeStateFor(runtime);
                std::lock_guard<std::mutex> lock(files.mutex);
                file_handle = files.allocateHandleLocked();
                files.openFiles[file_handle] = fp;
                RUNTIME_LOG("  -> handle=0x" << std::hex << file_handle << std::dec);
            }
            else
            {
                std::cerr << "ps2_stub fopen error: Failed to open '" << hostPath << "' with mode '" << hostMode << "'. Error: " << strerror(errno) << std::endl;
            }
        }
        else
        {
            std::cerr << "fopen error: Invalid address provided for path or mode."
                      << " Path: 0x" << std::hex << pathAddr << " (host ptr valid: " << (guestPath != nullptr) << ")"
                      << ", Mode: 0x" << modeAddr << " (host ptr valid: " << (hostMode != nullptr) << ")" << std::dec
                      << std::endl;
        }
        // returns a file handle (non-zero) on success, or NULL (0) on error.
        setReturnU32(ctx, file_handle);
    }

    void fclose(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint32_t file_handle = getRegU32(ctx, 4); // $a0
        int ret = EOF;                            // Default to error

        if (file_handle != 0)
        {
            LibCRuntimeState &files = libcRuntimeStateFor(runtime);
            std::lock_guard<std::mutex> lock(files.mutex);
            auto it = files.openFiles.find(file_handle);
            if (it != files.openFiles.end())
            {
                FILE *fp = it->second;
                ret = ::fclose(fp);
                files.openFiles.erase(it);
            }
            else
            {
                std::cerr << "ps2_stub fclose error: Invalid file handle 0x" << std::hex << file_handle << std::dec << std::endl;
            }
        }
        else
        {
            // Closing NULL handle in Standard C defines this as no-op
            ret = 0;
        }

        // returns 0 on success, EOF on error.
        setReturnS32(ctx, ret);
    }

    void fread(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint32_t ptrAddr = getRegU32(ctx, 4);     // $a0 (buffer)
        uint32_t size = getRegU32(ctx, 5);        // $a1 (element size)
        uint32_t count = getRegU32(ctx, 6);       // $a2 (number of elements)
        uint32_t file_handle = getRegU32(ctx, 7); // $a3 (file handle)
        size_t items_read = 0;

        uint8_t *hostPtr = getMemPtr(rdram, ptrAddr);
        FILE *fp = get_file_ptr(runtime, file_handle);

        if (hostPtr && fp && size > 0 && count > 0)
        {
            items_read = ::fread(hostPtr, size, count, fp);
        }
        else
        {
            std::cerr << "fread error: Invalid arguments."
                      << " Ptr: 0x" << std::hex << ptrAddr << " (host ptr valid: " << (hostPtr != nullptr) << ")"
                      << ", Handle: 0x" << file_handle << " (file valid: " << (fp != nullptr) << ")" << std::dec
                      << ", Size: " << size << ", Count: " << count << std::endl;
        }
        // returns the number of items successfully read.
        setReturnU32(ctx, (uint32_t)items_read);
    }

    void fwrite(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint32_t ptrAddr = getRegU32(ctx, 4);     // $a0 (buffer)
        uint32_t size = getRegU32(ctx, 5);        // $a1 (element size)
        uint32_t count = getRegU32(ctx, 6);       // $a2 (number of elements)
        uint32_t file_handle = getRegU32(ctx, 7); // $a3 (file handle)
        size_t items_written = 0;

        const uint8_t *hostPtr = getConstMemPtr(rdram, ptrAddr);
        FILE *fp = get_file_ptr(runtime, file_handle);

        if (hostPtr && fp && size > 0 && count > 0)
        {
            items_written = ::fwrite(hostPtr, size, count, fp);
        }
        else
        {
            std::cerr << "fwrite error: Invalid arguments."
                      << " Ptr: 0x" << std::hex << ptrAddr << " (host ptr valid: " << (hostPtr != nullptr) << ")"
                      << ", Handle: 0x" << file_handle << " (file valid: " << (fp != nullptr) << ")" << std::dec
                      << ", Size: " << size << ", Count: " << count << std::endl;
        }
        // returns the number of items successfully written.
        setReturnU32(ctx, (uint32_t)items_written);
    }

    void fprintf(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint32_t file_handle = getRegU32(ctx, 4); // $a0
        uint32_t format_addr = getRegU32(ctx, 5); // $a1
        FILE *fp = get_file_ptr(runtime, file_handle);
        const std::string formatOwned = readPs2CStringBounded(rdram, runtime, format_addr, 1024);
        int ret = -1;

        if (fp && format_addr != 0)
        {
            std::string rendered = formatPs2StringWithArgs(rdram, ctx, runtime, formatOwned.c_str(), 2);
            ret = std::fprintf(fp, "%s", rendered.c_str());
        }
        else
        {
            std::cerr << "fprintf error: Invalid file handle or format address."
                      << " Handle: 0x" << std::hex << file_handle << " (file valid: " << (fp != nullptr) << ")"
                      << ", Format: 0x" << format_addr << std::dec
                      << std::endl;
        }

        // returns the number of characters written, or negative on error.
        setReturnS32(ctx, ret);
    }

    void fseek(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint32_t file_handle = getRegU32(ctx, 4); // $a0
        long offset = (long)getRegU32(ctx, 5);    // $a1 (Note: might need 64-bit for large files?)
        int whence = (int)getRegU32(ctx, 6);      // $a2 (SEEK_SET, SEEK_CUR, SEEK_END)
        int ret = -1;                             // Default error

        FILE *fp = get_file_ptr(runtime, file_handle);

        if (fp)
        {
            // Ensure whence is valid (0, 1, 2)
            if (whence >= 0 && whence <= 2)
            {
                ret = ::fseek(fp, offset, whence);
            }
            else
            {
                std::cerr << "fseek error: Invalid whence value: " << whence << std::endl;
            }
        }
        else
        {
            std::cerr << "fseek error: Invalid file handle 0x" << std::hex << file_handle << std::dec << std::endl;
        }

        // returns 0 on success, non-zero on error.
        setReturnS32(ctx, ret);
    }

    void ftell(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint32_t file_handle = getRegU32(ctx, 4); // $a0
        long ret = -1L;

        FILE *fp = get_file_ptr(runtime, file_handle);

        if (fp)
        {
            ret = ::ftell(fp);
        }
        else
        {
            std::cerr << "ftell error: Invalid file handle 0x" << std::hex << file_handle << std::dec << std::endl;
        }

        // returns the current position, or -1L on error.
        if (ret > 0xFFFFFFFFL || ret < 0)
        {
            setReturnS32(ctx, -1);
        }
        else
        {
            setReturnU32(ctx, (uint32_t)ret);
        }
    }

    void fflush(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint32_t file_handle = getRegU32(ctx, 4); // $a0
        int ret = EOF;                            // Default error

        // If handle is 0 fflush flushes *all* output streams.
        if (file_handle == 0)
        {
            ret = ::fflush(NULL);
        }
        else
        {
            FILE *fp = get_file_ptr(runtime, file_handle);
            if (fp)
            {
                ret = ::fflush(fp);
            }
            else
            {
                std::cerr << "fflush error: Invalid file handle 0x" << std::hex << file_handle << std::dec << std::endl;
            }
        }
        // returns 0 on success, EOF on error.
        setReturnS32(ctx, ret);
    }

    // WARNING: the $f12/$f0 maths stubs below (sqrt, atan, atan2, pow, exp, log, log10,
    // ceil) are NOT bound by recomp/socom2.toml -- those addresses run as recompiled guest
    // code. Before binding any of them, disassemble the target and check which family it
    // is: SOCOM II's unsuffixed libm routines are double soft-float and pass in $a0/$v0
    // (see the note in the anonymous namespace above), and a $f12/$f0 stub on one of those
    // silently hands every caller a stale $v0. Only the `*f` routines use the FPU.
    void sqrt(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        float arg = ctx->f[12];
        ctx->f[0] = ::sqrtf(arg);
    }

    // sin @ 0x1B3000 -- double sin(double): 64-bit pattern in $a0, result in $v0.
    void sin(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint64_t bits = softDoubleArgBits(ctx, 4); // $a0
        setSoftDoubleReturn(ctx, doubleToBits(std::sin(bitsToDouble(bits))));
    }

    void __kernel_sinf(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const float x = ctx->f[12];
        const float y = ctx->f[13];
        const int32_t iy = static_cast<int32_t>(getRegU32(ctx, 4));
        ctx->f[0] = ::sinf(x + (iy != 0 ? y : 0.0f));
    }

    // cos @ 0x1B2C88 -- double cos(double): 64-bit pattern in $a0, result in $v0.
    void cos(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint64_t bits = softDoubleArgBits(ctx, 4); // $a0
        setSoftDoubleReturn(ctx, doubleToBits(std::cos(bitsToDouble(bits))));
    }

    void __kernel_cosf(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const float x = ctx->f[12];
        const float y = ctx->f[13];
        ctx->f[0] = ::cosf(x + y);
    }

    void __ieee754_rem_pio2f(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const float x = ctx->f[12];
        constexpr float kPi = 3.14159265358979323846f;
        constexpr float kHalfPi = kPi * 0.5f;
        constexpr float kInvHalfPi = 2.0f / kPi;
        const int32_t n = static_cast<int32_t>(std::nearbyintf(x * kInvHalfPi));
        const float y0 = x - (static_cast<float>(n) * kHalfPi);
        const float y1 = 0.0f;

        const uint32_t yOutAddr = getRegU32(ctx, 4);
        if (float *yOut0 = reinterpret_cast<float *>(getMemPtr(rdram, yOutAddr)); yOut0)
        {
            *yOut0 = y0;
        }
        if (float *yOut1 = reinterpret_cast<float *>(getMemPtr(rdram, yOutAddr + 4)); yOut1)
        {
            *yOut1 = y1;
        }

        setReturnS32(ctx, n);
    }

    // tan @ 0x1B3138 -- double tan(double): 64-bit pattern in $a0, result in $v0.
    void tan(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint64_t bits = softDoubleArgBits(ctx, 4); // $a0
        setSoftDoubleReturn(ctx, doubleToBits(std::tan(bitsToDouble(bits))));
    }

    void atan2(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        float y = ctx->f[12];
        float x = ctx->f[14];
        ctx->f[0] = ::atan2f(y, x);
    }

    void pow(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        float base = ctx->f[12];
        float exp = ctx->f[14];
        ctx->f[0] = ::powf(base, exp);
    }

    void exp(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        float arg = ctx->f[12];
        ctx->f[0] = ::expf(arg);
    }

    void log(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        float arg = ctx->f[12];
        ctx->f[0] = ::logf(arg);
    }

    void log10(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        float arg = ctx->f[12];
        ctx->f[0] = ::log10f(arg);
    }

    void ceil(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        float arg = ctx->f[12];
        ctx->f[0] = ::ceilf(arg);
    }

    // floor @ 0x1B2DE8 -- double floor(double): 64-bit pattern in $a0, result in $v0.
    // std::floor is IEEE-754 roundToIntegralTowardNegative, which is exactly what newlib's
    // bit-twiddling version computes for every finite and infinite input, signed zero
    // included. The one place the two could part company is a NaN argument: the guest
    // falls through to `return x + x` (dpadd 0x1A0B58), i.e. it quietens a signalling NaN
    // and returns a quiet one unchanged. Reproduce that rather than deferring to the host.
    void floor(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint64_t bits = softDoubleArgBits(ctx, 4); // $a0
        if (isDoubleNanBits(bits))
        {
            setSoftDoubleReturn(ctx, bits | kDoubleQuietBit);
            return;
        }
        setSoftDoubleReturn(ctx, doubleToBits(std::floor(bitsToDouble(bits))));
    }

    // fabs @ 0x1B2DB0 -- double fabs(double): 64-bit pattern in $a0, result in $v0.
    // Done on the bit pattern, exactly as the guest does it, so that NaN payloads, signed
    // zero and infinities come back bit-identical instead of going through a host double.
    void fabs(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint64_t bits = softDoubleArgBits(ctx, 4); // $a0
        setSoftDoubleReturn(ctx, bits & ~kDoubleSignMask);
    }
    void abs(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const int32_t value = static_cast<int32_t>(getRegU32(ctx, 4));
        if (value == std::numeric_limits<int32_t>::min())
        {
            setReturnS32(ctx, std::numeric_limits<int32_t>::max());
            return;
        }
        setReturnS32(ctx, value < 0 ? -value : value);
    }

    void atan(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        float in = ctx ? ctx->f[12] : 0.0f;
        if (in == 0.0f)
        {
            uint32_t raw = getRegU32(ctx, 4);
            std::memcpy(&in, &raw, sizeof(in));
        }
        const float out = std::atan(in);
        if (ctx)
        {
            ctx->f[0] = out;
        }

        uint32_t outRaw = 0u;
        std::memcpy(&outRaw, &out, sizeof(outRaw));
        setReturnU32(ctx, outRaw);
    }

    void memchr(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint32_t srcAddr = getRegU32(ctx, 4);
        const uint8_t needle = static_cast<uint8_t>(getRegU32(ctx, 5) & 0xFFu);
        const uint32_t size = getRegU32(ctx, 6);

        for (uint32_t i = 0; i < size; ++i)
        {
            const uint8_t *src = getConstMemPtr(rdram, srcAddr + i);
            if (!src)
            {
                break;
            }
            if (*src == needle)
            {
                setReturnU32(ctx, srcAddr + i);
                return;
            }
        }

        setReturnU32(ctx, 0u);
    }

    // --- newlib rand()/srand() --------------------------------------------------------------
    //
    // These replace the guest's own newlib routines, so they must be the SAME generator over the
    // SAME state, not "some randomness".  The guest pair is
    //
    //   srand(u):  _rand_next = (unsigned)u;
    //   rand():    _rand_next = _rand_next * 6364136223846793005ULL + 1;
    //              return (int)((_rand_next >> 32) & 0x7fffffff);      // newlib RAND_MAX, 31 bits
    //
    // Two things this has to get right that the previous implementation did not:
    //
    // 1. WIDTH.  It used to be `std::rand() & 0x7FFF`.  RAND_MAX is 0x7FFF on llvm-mingw (verified
    //    on this toolchain), so that mask was a no-op and the stub returned 15 bits where newlib
    //    promises 31.  SOCOM II turns a draw into a 0..1 float with `(float)rand() * 4.656613e-10`
    //    (2^-31) at 249 call sites, so every random value in the game was pinned to the bottom
    //    1/65536 of its range -- e.g. CSealCtrl+0x5c, `4.0 + 3.0*r`, could not exceed 4.0000458
    //    against the console's 6.3338 (docs/research/17-ground-height.md section 6).  Widening by
    //    shifting a 15-bit host draw left by 16 would be a different wrong answer (zeroed low
    //    bits, 32768 distinct values); the generator itself is reproduced instead.
    //
    // 2. STATE.  srand() is NOT stubbed in recomp/socom2.toml -- it runs recompiled and writes
    //    `_rand_next` in guest memory -- and SOCOM II calls `srand(<RTC-derived>); srand(rand());`
    //    at boot.  A stub with private state would ignore that seeding entirely (which is exactly
    //    what happened: our RDRAM images show _rand_next frozen at 41, the host CRT's first draw,
    //    written back by the guest's own srand(rand())).  So the state is read from and written to
    //    the guest's `struct _reent._rand_next`, reached through the game's _impure_ptr; the two
    //    addresses are game-specific and are registered by the game override (setLibcRandState).
    //    With no registration the stub keeps an internal state seeded the way newlib's static
    //    initialiser is, so the generic runtime still behaves.
    namespace
    {
        // The cursor, its mutex and the two registered addresses live in
        // Helpers/LibCRuntimeState.h now, owned by the runtime (Task 8b, review F2).

        // Bounds-checked guest->host translation for a small fixed-size access.
        //
        // getMemPtr() cannot be used for this: it *masks* rather than rejects (ps2_memory.h, `phys
        // &= PS2_RAM_MASK` plus a `phys = 0` fall-through), so an address in 0x40000000-0x7FFFFFFF
        // resolves to offset 0 and an address in the last 7 bytes of the 32 MB buffer would let an
        // 8-byte access run off the end. _rand_next is reached through a pointer read out of guest
        // memory, so a corrupt _impure_ptr must fail the lookup, not silently write somewhere else.
        uint8_t *guestFixedSlot(uint8_t *rdram, uint32_t addr, uint32_t bytes)
        {
            if (rdram == nullptr)
            {
                return nullptr;
            }
            uint32_t phys = addr;
            if ((addr >= 0x20000000u && addr < 0x40000000u) ||
                (addr >= 0x80000000u && addr < 0xC0000000u))
            {
                phys = addr & 0x1FFFFFFFu;   // KSEG0/KSEG1 and the uncached mirror
            }
            else if (addr >= 0x20000000u)
            {
                return nullptr;              // scratchpad, MMIO or unmapped: struct _reent is in RDRAM
            }
            if (phys > PS2_RAM_SIZE - bytes)
            {
                return nullptr;
            }
            return rdram + phys;
        }

        // Host pointer to the guest's _rand_next, or nullptr when it cannot be resolved.
        uint8_t *guestRandNextSlot(LibCRuntimeState &libc, uint8_t *rdram)
        {
            if (libc.impurePtrAddr == 0u)
            {
                return nullptr;
            }
            const uint8_t *impurePtr = guestFixedSlot(rdram, libc.impurePtrAddr, sizeof(uint32_t));
            if (impurePtr == nullptr)
            {
                return nullptr;
            }
            uint32_t reentAddr = 0u;
            std::memcpy(&reentAddr, impurePtr, sizeof(reentAddr));
            if (reentAddr == 0u || reentAddr > 0xFFFFFFFFu - libc.randNextOffset)
            {
                return nullptr;
            }
            return guestFixedSlot(rdram, reentAddr + libc.randNextOffset, sizeof(uint64_t));
        }

        uint64_t loadRandNext(LibCRuntimeState &libc, uint8_t *slot)
        {
            if (slot == nullptr)
            {
                return libc.randNextFallback;
            }
            uint64_t state = 0u;
            std::memcpy(&state, slot, sizeof(state));
            return state;
        }

        void storeRandNext(LibCRuntimeState &libc, uint8_t *slot, uint64_t value)
        {
            if (slot == nullptr)
            {
                libc.randNextFallback = value;
                return;
            }
            std::memcpy(slot, &value, sizeof(value));
        }
    }

    void setLibcRandState(PS2Runtime *runtime, uint32_t impurePtrAddr, uint32_t randNextOffset)
    {
        LibCRuntimeState &state = libcRuntimeStateFor(runtime);
        std::lock_guard<std::mutex> lock(state.randMutex);
        state.impurePtrAddr = impurePtrAddr;
        state.randNextOffset = randNextOffset;
    }

    void rand(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        LibCRuntimeState &libc = libcRuntimeStateFor(runtime);
        std::lock_guard<std::mutex> lock(libc.randMutex);
        uint8_t *slot = guestRandNextSlot(libc, rdram);
        const uint64_t state = loadRandNext(libc, slot) * 6364136223846793005ULL + 1ULL;
        storeRandNext(libc, slot, state);
        setReturnS32(ctx, static_cast<int32_t>((state >> 32) & 0x7FFFFFFFu));
    }

    void srand(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        // newlib stores the unsigned 32-bit argument zero-extended and returns void.
        LibCRuntimeState &libc = libcRuntimeStateFor(runtime);
        std::lock_guard<std::mutex> lock(libc.randMutex);
        storeRandNext(libc, guestRandNextSlot(libc, rdram), static_cast<uint64_t>(getRegU32(ctx, 4)));
    }

    void strcasecmp(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const uint32_t lhsAddr = getRegU32(ctx, 4);
        const uint32_t rhsAddr = getRegU32(ctx, 5);
        const std::string lhs = readPs2CStringBounded(rdram, runtime, lhsAddr, 1024);
        const std::string rhs = readPs2CStringBounded(rdram, runtime, rhsAddr, 1024);

        const size_t n = std::min(lhs.size(), rhs.size());
        for (size_t i = 0; i < n; ++i)
        {
            const int a = std::tolower(static_cast<unsigned char>(lhs[i]));
            const int b = std::tolower(static_cast<unsigned char>(rhs[i]));
            if (a != b)
            {
                setReturnS32(ctx, a - b);
                return;
            }
        }

        setReturnS32(ctx, static_cast<int32_t>(lhs.size()) - static_cast<int32_t>(rhs.size()));
    }

    void vfprintf(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint32_t file_handle = getRegU32(ctx, 4);  // $a0
        uint32_t format_addr = getRegU32(ctx, 5);  // $a1
        uint32_t va_list_addr = getRegU32(ctx, 6); // $a2
        FILE *fp = get_file_ptr(runtime, file_handle);
        const std::string formatOwned = readPs2CStringBounded(rdram, runtime, format_addr, 1024);
        int ret = -1;

        if (fp && format_addr != 0)
        {
            std::string rendered = formatPs2StringWithVaList(rdram, runtime, formatOwned.c_str(), va_list_addr);
            ret = std::fprintf(fp, "%s", rendered.c_str());
        }
        else
        {
            std::cerr << "vfprintf error: Invalid file handle or format address."
                      << " Handle: 0x" << std::hex << file_handle << " (file valid: " << (fp != nullptr) << ")"
                      << ", Format: 0x" << format_addr << std::dec
                      << std::endl;
        }

        setReturnS32(ctx, ret);
    }

    void vsprintf(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        uint32_t str_addr = getRegU32(ctx, 4);      // $a0
        uint32_t format_addr = getRegU32(ctx, 5);   // $a1
        uint32_t va_list_addr = getRegU32(ctx, 6);  // $a2
        constexpr size_t kSafeVsprintfBytes = 256u; // Keep guest stack temporaries from being overwritten.
        const std::string formatOwned = readPs2CStringBounded(rdram, runtime, format_addr, 1024);
        int ret = -1;

        if (format_addr != 0)
        {
            std::string rendered = formatPs2StringWithVaList(rdram, runtime, formatOwned.c_str(), va_list_addr);
            if (rendered.size() >= kSafeVsprintfBytes)
            {
                rendered.resize(kSafeVsprintfBytes - 1);
            }
            if (writeGuestBytes(rdram, runtime, str_addr, reinterpret_cast<const uint8_t *>(rendered.c_str()), rendered.size() + 1u))
            {
                ret = static_cast<int>(rendered.size());
            }
            else
            {
                std::cerr << "vsprintf error: Failed to write destination buffer at 0x"
                          << std::hex << str_addr << std::dec << std::endl;
            }
        }
        else
        {
            std::cerr << "vsprintf error: Invalid address provided."
                      << " Dest: 0x" << std::hex << str_addr
                      << ", Format: 0x" << format_addr << std::dec
                      << std::endl;
        }

        setReturnS32(ctx, ret);
    }

    void __divdi3(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        const int64_t num = GPR_S64(ctx, 4);
        const int64_t den = GPR_S64(ctx, 5);
        if (den == 0)
        {
            setReturnU64(ctx, 0u);
            return;
        }
        if (num == std::numeric_limits<int64_t>::min() && den == -1)
        {
            setReturnU64(ctx, static_cast<uint64_t>(num));
            return;
        }
        setReturnU64(ctx, static_cast<uint64_t>(num / den));
    }

}
