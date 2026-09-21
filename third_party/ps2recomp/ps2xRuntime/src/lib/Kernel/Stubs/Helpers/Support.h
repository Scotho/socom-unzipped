#pragma once
// The stub helpers' declarations. Until Sprint 10 Q7 this header DEFINED everything below -- every global,
// every function -- inside an anonymous namespace, so each of the stub .cpp files (and two test files) got
// its own private copy of the CD index, the file table, the GS parameters and the log counters
// (docs/AUDIT-2026-09-17.md, "one copy per TU across 19 stub files"). The definitions now live once, in
// Support.cpp; the using-directive at the end keeps every call site as it was (the anonymous namespace
// was at global scope, so its names were unqualified everywhere). Included by Common.h after the runtime
// headers it needs.
#include <algorithm>
#include <cctype>

namespace stub_support
{
    constexpr uint32_t kCdSectorSize = 2048;
    constexpr uint32_t kCdPseudoLbnStart = 0x00100000;

    struct CdFileEntry
    {
        std::filesystem::path hostPath;
        uint32_t sizeBytes = 0;
        uint32_t baseLbn = 0;
        uint32_t sectors = 0;
    };

    extern std::unordered_map<std::string, CdFileEntry> g_cdFilesByKey;
    extern std::unordered_map<std::string, std::filesystem::path> g_cdLeafIndex;
    extern std::unordered_map<std::string, std::filesystem::path> g_cdLoosePathIndex;
    extern std::filesystem::path g_cdLeafIndexRoot;
    extern bool g_cdLeafIndexBuilt;
    extern uint32_t g_nextPseudoLbn;
    extern std::filesystem::path g_cdImageSizePath;
    extern uint64_t g_cdImageSizeBytes;
    extern bool g_cdImageSizeValid;
    extern int32_t g_lastCdError;
    extern uint32_t g_cdMode;
    extern uint32_t g_cdStreamingLbn;
    extern uint32_t g_cdStreamingEndLbn;
    extern bool g_cdInitialized;

    constexpr uint32_t kIopHeapBase = 0x04000000;
    constexpr uint32_t kIopHeapLimit = 0x04500000;
    constexpr uint32_t kIopHeapAlign = 64;
    extern uint32_t g_iopHeapNext;

    std::string toLowerAscii(std::string value);

    std::string stripIsoVersionSuffix(std::string value);

    std::string normalizePathSeparators(std::string value);

    void trimLeadingSeparators(std::string &value);

    std::string normalizeCdPathNoPrefix(std::string path);

    std::string normalizeCdLooseNumericKey(std::string value);

    std::string cdLoosePathKeyFromRelative(const std::filesystem::path &relative);

    std::string cdLoosePathKey(const std::string &ps2Path);

    std::filesystem::path getCdRootPath();

    std::filesystem::path getCdImagePath();

    bool tryGetCdImageTotalSectors(uint64_t &totalSectorsOut);

    uint32_t sectorsForBytes(uint64_t byteCount);

    std::string cdPathKey(const std::string &ps2Path);

    std::filesystem::path cdHostPath(const std::string &ps2Path);

    bool resolveCaseInsensitivePath(const std::filesystem::path &root,
                                    const std::filesystem::path &relative,
                                    std::filesystem::path &resolvedOut);

    void ensureCdLeafIndex(const std::filesystem::path &root);

    bool registerCdFile(const std::string &ps2Path, CdFileEntry &entryOut);

    bool readHostRange(const std::filesystem::path &path, uint64_t offsetBytes, uint8_t *dst, size_t byteCount);

    bool readCdSectors(uint32_t lbn, uint32_t sectors, uint8_t *dst, size_t byteCount);

    bool isResolvableCdLbn(uint32_t lbn);

    bool findRegisteredCdFileForLbn(uint32_t lbn, CdFileEntry &entryOut);

    uint32_t cdStreamingEndLbnForStart(uint32_t lbn);

    bool writeCdSearchResult(uint8_t *rdram, uint32_t fileAddr, const std::string &ps2Path, const CdFileEntry &entry);

    uint8_t toBcd(uint32_t value);

    uint32_t fromBcd(uint8_t value);

    extern std::unordered_map<uint32_t, FILE *> g_file_map;
    extern uint32_t g_next_file_handle;
    extern std::mutex g_file_mutex;

    uint32_t generate_file_handle();

    FILE *get_file_ptr(uint32_t handle);
}

namespace stub_support
{
    uint32_t hostPtrToPs2Addr(uint8_t *rdram, const void *hostPtr);
}

namespace stub_support
{
    bool tryReadWordFromRdram(uint8_t *rdram, uint32_t addr, uint32_t &outWord);

    bool tryReadWordFromGuest(uint8_t *rdram, PS2Runtime *runtime, uint32_t addr, uint32_t &outWord);

    bool tryReadByteFromGuest(uint8_t *rdram, PS2Runtime *runtime, uint32_t addr, uint8_t &outByte);

    bool writeGuestBytes(uint8_t *rdram, PS2Runtime *runtime, uint32_t addr, const uint8_t *src, size_t len);

    std::string readPs2CStringBounded(uint8_t *rdram, PS2Runtime *runtime, uint32_t addr, size_t maxLen = 512);

    std::string readPs2CStringBounded(uint8_t *rdram, uint32_t addr, size_t maxLen = 512);

    std::string sanitizeForLog(const std::string &value);

    class Ps2VarArgCursor
    {
    public:
        Ps2VarArgCursor(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime, int fixedArgs)
            : m_rdram(rdram),
              m_ctx(ctx),
              m_runtime(runtime),
              m_fixedArgs(fixedArgs),
              m_stackBase(getRegU32(ctx, 29) + 0x10)
        {
            if (m_fixedArgs < 0)
            {
                m_fixedArgs = 0;
            }
            m_slotIndex = static_cast<uint32_t>(m_fixedArgs);
        }

        uint32_t nextU32()
        {
            const uint32_t value = readWordAtSlot(m_slotIndex);
            ++m_slotIndex;
            return value;
        }

        uint64_t nextU64()
        {
            // O32 ABI aligns 64-bit variadic values on even 32-bit slots.
            if ((m_slotIndex & 1u) != 0u)
            {
                ++m_slotIndex;
            }
            const uint64_t low = readWordAtSlot(m_slotIndex);
            const uint64_t high = readWordAtSlot(m_slotIndex + 1u);
            m_slotIndex += 2u;
            return low | (high << 32);
        }

    private:
        uint32_t readWordAtSlot(uint32_t slotIndex) const
        {
            if (slotIndex < 8u)
            {
                // EE calls use eight integer argument registers (a0-a3, t0-t3 / r4-r11).
                return getRegU32(m_ctx, 4 + static_cast<int>(slotIndex));
            }

            const uint32_t stackIndex = slotIndex - 8u;
            const uint32_t stackAddr = m_stackBase + stackIndex * 4u;
            uint32_t value = 0;
            (void)tryReadWordFromGuest(m_rdram, m_runtime, stackAddr, value);
            return value;
        }

        uint8_t *m_rdram;
        R5900Context *m_ctx;
        PS2Runtime *m_runtime;
        int m_fixedArgs;
        uint32_t m_stackBase;
        uint32_t m_slotIndex = 0;
    };

    class Ps2VaListCursor
    {
    public:
        Ps2VaListCursor(uint8_t *rdram, PS2Runtime *runtime, uint32_t vaListAddr)
            : m_rdram(rdram), m_runtime(runtime), m_curr(vaListAddr)
        {
        }

        uint32_t nextU32()
        {
            uint32_t value = 0;
            (void)tryReadWordFromGuest(m_rdram, m_runtime, m_curr, value);
            m_curr += 4;
            return value;
        }

        uint64_t nextU64()
        {
            m_curr = (m_curr + 7u) & ~7u;
            const uint64_t low = nextU32();
            const uint64_t high = nextU32();
            return low | (high << 32);
        }

    private:
        uint8_t *m_rdram;
        PS2Runtime *m_runtime;
        uint32_t m_curr = 0;
    };

    template <typename NextU32Fn, typename NextU64Fn, typename ReadStringFn>
    std::string formatPs2StringCore(uint8_t *rdram, const char *format, NextU32Fn nextU32, NextU64Fn nextU64, ReadStringFn readString)
    {
        if (!format)
        {
            return {};
        }

        std::string out;
        out.reserve(std::strlen(format) + 32);
        const char *p = format;

        while (*p)
        {
            if (*p != '%')
            {
                out.push_back(*p++);
                continue;
            }

            const char *specStart = p++;
            if (*p == '%')
            {
                out.push_back('%');
                ++p;
                continue;
            }

            int parsedWidth = -1;
            int parsedPrecision = -1;
            bool widthSpecified = false;
            bool precisionSpecified = false;
            std::string parsedFlags;

            while (*p && std::strchr("-+ #0", *p))
            {
                parsedFlags.push_back(*p);
                ++p;
            }

            if (*p == '*')
            {
                parsedWidth = static_cast<int32_t>(nextU32());
                widthSpecified = true;
                ++p;
            }
            else
            {
                if (*p && std::isdigit(static_cast<unsigned char>(*p)))
                {
                    parsedWidth = 0;
                    widthSpecified = true;
                }
                while (*p && std::isdigit(static_cast<unsigned char>(*p)))
                {
                    parsedWidth = (parsedWidth * 10) + (*p - '0');
                    ++p;
                }
            }

            if (*p == '.')
            {
                ++p;
                precisionSpecified = true;
                if (*p == '*')
                {
                    parsedPrecision = static_cast<int32_t>(nextU32());
                    ++p;
                }
                else
                {
                    parsedPrecision = 0;
                    while (*p && std::isdigit(static_cast<unsigned char>(*p)))
                    {
                        parsedPrecision = (parsedPrecision * 10) + (*p - '0');
                        ++p;
                    }
                }
            }
            if (parsedPrecision < 0)
            {
                parsedPrecision = -1;
            }

            enum class LengthMod
            {
                None,
                H,
                HH,
                L,
                LL,
                J,
                Z,
                T,
                BigL
            };

            LengthMod length = LengthMod::None;
            if (*p == 'h')
            {
                ++p;
                if (*p == 'h')
                {
                    ++p;
                    length = LengthMod::HH;
                }
                else
                {
                    length = LengthMod::H;
                }
            }
            else if (*p == 'l')
            {
                ++p;
                if (*p == 'l')
                {
                    ++p;
                    length = LengthMod::LL;
                }
                else
                {
                    length = LengthMod::L;
                }
            }
            else if (*p == 'j')
            {
                ++p;
                length = LengthMod::J;
            }
            else if (*p == 'z')
            {
                ++p;
                length = LengthMod::Z;
            }
            else if (*p == 't')
            {
                ++p;
                length = LengthMod::T;
            }
            else if (*p == 'L')
            {
                ++p;
                length = LengthMod::BigL;
            }

            if (*p == '\0')
            {
                out.append(specStart);
                break;
            }

            auto buildHostSpec = [&](char spec, const char *lengthOverride = nullptr) -> std::string
            {
                std::string specText;
                specText.reserve(32);
                specText.push_back('%');

                if (widthSpecified && parsedWidth < 0 &&
                    parsedFlags.find('-') == std::string::npos)
                {
                    specText.push_back('-');
                }

                specText.append(parsedFlags);
                if (widthSpecified)
                {
                    const int hostWidth = (parsedWidth < 0) ? -parsedWidth : parsedWidth;
                    specText.append(std::to_string(hostWidth));
                }
                if (precisionSpecified)
                {
                    specText.push_back('.');
                    specText.append(std::to_string(std::max(parsedPrecision, 0)));
                }
                if (lengthOverride != nullptr)
                {
                    specText.append(lengthOverride);
                }
                specText.push_back(spec);
                return specText;
            };

            auto appendFormatted = [&](const std::string &specText, auto value) -> bool
            {
                const int needed = std::snprintf(nullptr, 0, specText.c_str(), value);
                if (needed < 0)
                {
                    return false;
                }

                std::string chunk(static_cast<size_t>(needed), '\0');
                std::snprintf(chunk.data(), chunk.size() + 1u, specText.c_str(), value);
                out.append(chunk);
                return true;
            };

            const bool use64Integer = (length == LengthMod::LL || length == LengthMod::J);
            auto readUnsignedInteger = [&]() -> uint64_t
            {
                return use64Integer ? nextU64() : static_cast<uint64_t>(nextU32());
            };
            auto readSignedInteger = [&]() -> int64_t
            {
                if (use64Integer)
                {
                    return static_cast<int64_t>(nextU64());
                }
                return static_cast<int64_t>(static_cast<int32_t>(nextU32()));
            };

            const char spec = *p++;
            switch (spec)
            {
            case 's':
            {
                const uint32_t strAddr = nextU32();
                const char *text = "(null)";
                std::string ownedText;
                if (strAddr != 0u)
                {
                    ownedText = readString(strAddr);
                    text = ownedText.c_str();
                }
                if (!appendFormatted(buildHostSpec(spec), text))
                {
                    out.append(text);
                }
                break;
            }
            case 'c':
            {
                const int ch = static_cast<int>(nextU32() & 0xFFu);
                if (!appendFormatted(buildHostSpec(spec), ch))
                {
                    out.push_back(static_cast<char>(ch));
                }
                break;
            }
            case 'd':
            case 'i':
            {
                const long long value = static_cast<long long>(readSignedInteger());
                if (!appendFormatted(buildHostSpec(spec, "ll"), value))
                {
                    out.append(std::to_string(value));
                }
                break;
            }
            case 'u':
            case 'x':
            case 'X':
            case 'o':
            {
                const unsigned long long value = static_cast<unsigned long long>(readUnsignedInteger());
                if (!appendFormatted(buildHostSpec(spec, "ll"), value))
                {
                    std::ostringstream ss;
                    if (spec == 'o')
                    {
                        ss << std::oct << value;
                    }
                    else
                    {
                        if (spec == 'X')
                        {
                            ss.setf(std::ios::uppercase);
                        }
                        ss << std::hex << value;
                    }
                    out.append(ss.str());
                }
                break;
            }
            case 'p':
            {
                const uint32_t ptrValue = nextU32();
                if (!appendFormatted(buildHostSpec(spec), reinterpret_cast<void *>(static_cast<uintptr_t>(ptrValue))))
                {
                    std::ostringstream ss;
                    ss << "0x" << std::hex << ptrValue;
                    out.append(ss.str());
                }
                break;
            }
            case 'f':
            case 'F':
            case 'e':
            case 'E':
            case 'g':
            case 'G':
            case 'a':
            case 'A':
            {
                const uint64_t bits = nextU64();
                double value = 0.0;
                std::memcpy(&value, &bits, sizeof(value));
                if (length == LengthMod::BigL)
                {
                    if (!appendFormatted(buildHostSpec(spec, "L"), static_cast<long double>(value)))
                    {
                        out.append(std::to_string(value));
                    }
                }
                else if (!appendFormatted(buildHostSpec(spec), value))
                {
                    out.append(std::to_string(value));
                }
                break;
            }
            case 'n':
            {
                // Avoid arbitrary guest memory mutation through %n in stub formatting.
                (void)nextU32();
                break;
            }
            default:
                out.append(specStart, p - specStart);
                break;
            }
        }

        return out;
    }

    std::string formatPs2StringWithArgs(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime, const char *format, int fixedArgs);

    std::string formatPs2StringWithVaList(uint8_t *rdram, PS2Runtime *runtime, const char *format, uint32_t vaListAddr);

    constexpr uint32_t kMaxStubWarningsPerName = 8;
    extern std::unordered_map<std::string, uint32_t> g_stubWarningCount;
    extern std::mutex g_stubWarningMutex;
    constexpr uint32_t kMaxPrintfLogs = 200;
    constexpr size_t kMaxFormattedOutputBytes = 4096;
    extern uint32_t g_printfLogCount;
    extern std::mutex g_printfLogMutex;

    constexpr std::array<uint32_t, 10> kDmaChannelBases = {
        0x10008000u, 0x10009000u, 0x1000A000u, 0x1000B000u, 0x1000B400u,
        0x1000C000u, 0x1000C400u, 0x1000C800u, 0x1000D000u, 0x1000D400u};
    extern std::mutex g_dmaStubMutex;
    extern std::unordered_map<uint32_t, uint32_t> g_dmaPendingPolls;
    extern uint32_t g_dmaStubLogCount;
    constexpr uint32_t kMaxDmaStubLogs = 64;

    bool isKnownDmaChannelBase(uint32_t value);

    uint32_t toDmaPhys(uint32_t addr);

    uint32_t normalizeQwcFromArg(uint32_t value);

    struct ParsedDmaTag
    {
        bool valid = false;
        uint32_t qwc = 0;
        uint32_t id = 0;
        uint32_t addr = 0;
    };

    ParsedDmaTag tryParseDmaTag(uint8_t *rdram, uint32_t guestAddr);

    uint32_t resolveDmaChannelBase(uint8_t *rdram, uint32_t chanArg);

    int32_t submitDmaSend(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime, bool preferNormalCount);

    int32_t submitDmaSync(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime);

}

namespace stub_support
{
    struct GsGParam
    {
        uint8_t interlace;
        uint8_t omode;
        uint8_t ffmode;
        uint8_t version;
    };

    struct GsDispEnvMem
    {
        uint64_t pmode;
        uint64_t smode2;
        uint64_t dispfb;
        uint64_t display;
        uint64_t bgcolor;
    };

    struct GsGiftagMem
    {
        uint64_t lo;
        uint64_t hi;
    };

    struct GsRegPairMem
    {
        uint64_t value;
        uint64_t reg;
    };

    struct GsDrawEnv1Mem
    {
        GsRegPairMem frame1;
        GsRegPairMem zbuf1;
        GsRegPairMem xyoffset1;
        GsRegPairMem scissor1;
        GsRegPairMem prmodecont;
        GsRegPairMem colclamp;
        GsRegPairMem dthe;
        GsRegPairMem test1;
    };

    struct GsDrawEnv2Mem
    {
        GsRegPairMem frame2;
        GsRegPairMem zbuf2;
        GsRegPairMem xyoffset2;
        GsRegPairMem scissor2;
        GsRegPairMem prmodecont;
        GsRegPairMem colclamp;
        GsRegPairMem dthe;
        GsRegPairMem test2;
    };

    struct GsClearMem
    {
        GsRegPairMem testa;
        GsRegPairMem prim;
        GsRegPairMem rgbaq;
        GsRegPairMem xyz2a;
        GsRegPairMem xyz2b;
        GsRegPairMem testb;
    };

    struct GsDBuffDcMem
    {
        GsDispEnvMem disp[2];
        GsGiftagMem giftag0;
        GsDrawEnv1Mem draw01;
        GsDrawEnv2Mem draw02;
        GsClearMem clear0;
        GsGiftagMem giftag1;
        GsDrawEnv1Mem draw11;
        GsDrawEnv2Mem draw12;
        GsClearMem clear1;
    };

    struct GsDBuffMem
    {
        GsDispEnvMem disp[2];
        GsGiftagMem giftag0;
        GsDrawEnv1Mem draw0;
        GsClearMem clear0;
        GsGiftagMem giftag1;
        GsDrawEnv1Mem draw1;
        GsClearMem clear1;
    };

    struct GsImageMem
    {
        uint16_t x;
        uint16_t y;
        uint16_t width;
        uint16_t height;
        uint16_t vram_addr;
        uint8_t vram_width;
        uint8_t psm;
    };

    static_assert(sizeof(GsImageMem) == 12, "GsImageMem size mismatch");
    static_assert(sizeof(GsDispEnvMem) == 40, "GsDispEnvMem size mismatch");
    static_assert(sizeof(GsGiftagMem) == 16, "GsGiftagMem size mismatch");
    static_assert(sizeof(GsRegPairMem) == 16, "GsRegPairMem size mismatch");
    static_assert(sizeof(GsDrawEnv1Mem) == 128, "GsDrawEnv1Mem size mismatch");
    static_assert(sizeof(GsDrawEnv2Mem) == 128, "GsDrawEnv2Mem size mismatch");
    static_assert(sizeof(GsClearMem) == 96, "GsClearMem size mismatch");
    static_assert(sizeof(GsDBuffDcMem) == 0x330, "GsDBuffDcMem size mismatch");

    constexpr uint32_t kGsParamScratchOffset = 0x100;
    extern GsGParam g_gparam;

    uint64_t makePmode(uint32_t en1, uint32_t en2, uint32_t mmod, uint32_t amod, uint32_t slbg, uint32_t alp);

    uint64_t makeDispFb(uint32_t fbp, uint32_t fbw, uint32_t psm, uint32_t dbx, uint32_t dby);

    uint64_t makeDisplay(uint32_t dx, uint32_t dy, uint32_t magh, uint32_t magv, uint32_t dw, uint32_t dh);

    uint64_t makeFrame(uint32_t fbp, uint32_t fbw, uint32_t psm, uint32_t fbmsk);

    uint64_t makeZbuf(uint32_t zbp, uint32_t psm, bool zmsk);

    uint64_t makeXYOffset(int32_t width, int32_t height);

    uint64_t makeScissor(int32_t width, int32_t height);

    uint64_t makeTest(uint32_t ztest);

    uint64_t makeGiftagAplusD(uint32_t nloop);

    uint64_t makeGiftagAplusDOpen(uint32_t nloop);

    uint32_t readStackU32(uint8_t *rdram, R5900Context *ctx, uint32_t offset);

    uint32_t bytesForPixels(uint8_t psm, uint32_t pixelCount);

    struct GsSetDefImageArgs
    {
        uint32_t x = 0;
        uint32_t y = 0;
        uint32_t width = 0;
        uint32_t height = 0;
        uint32_t vramAddr = 0;
        uint32_t vramWidth = 0;
        uint32_t psm = 0;
    };

    GsSetDefImageArgs decodeGsSetDefImageArgs(uint8_t *rdram, R5900Context *ctx);

    void writeGsQword(uint8_t *ptr, uint64_t lo, uint64_t hi);

    uint64_t gsImageQwc(const GsImageMem &img);

    bool writeGsLoadImagePacket(uint8_t *rdram, uint32_t addr, const GsImageMem &img);

    bool writeGsStoreImagePacket(uint8_t *rdram, uint32_t addr, const GsImageMem &img);

    bool readGsImage(uint8_t *rdram, uint32_t addr, GsImageMem &out);

    bool writeGsDispEnv(uint8_t *rdram, uint32_t addr, uint64_t display, uint64_t dispfb);

    bool readGsDispEnv(uint8_t *rdram, uint32_t addr, GsDispEnvMem &out);

    bool readGsDBuffDc(uint8_t *rdram, uint32_t addr, GsDBuffDcMem &out);

    bool readGsDBuff(uint8_t* rdram, uint32_t addr, GsDBuffMem& out);

    bool writeGsDBuffDc(uint8_t *rdram, uint32_t addr, const GsDBuffDcMem &db);

    bool writeGsDBuff(uint8_t* rdram, uint32_t addr, const GsDBuffMem& db);

    bool readGsRegPairs(uint8_t *rdram, uint32_t addr, GsRegPairMem *pairs, size_t pairCount);

    void applyGsDispEnv(PS2Runtime *runtime, const GsDispEnvMem &env);

    void applyGsRegPairs(PS2Runtime *runtime, const GsRegPairMem *pairs, size_t pairCount);

    void seedGsDrawEnv1(GsDrawEnv1Mem &env,
                               int32_t width,
                               int32_t height,
                               uint32_t fbp,
                               uint32_t fbw,
                               uint32_t psm,
                               uint32_t zbp,
                               uint32_t zpsm,
                               uint32_t ztest,
                               bool dthe);

    void seedGsDrawEnv2(GsDrawEnv2Mem &env,
                               int32_t width,
                               int32_t height,
                               uint32_t fbp,
                               uint32_t fbw,
                               uint32_t psm,
                               uint32_t zbp,
                               uint32_t zpsm,
                               uint32_t ztest,
                               bool dthe);

    uint32_t writeGsGParamToScratch(PS2Runtime *runtime);
}

using namespace stub_support;
