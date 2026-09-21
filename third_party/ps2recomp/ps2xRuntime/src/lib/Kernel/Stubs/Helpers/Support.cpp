// The stub helpers' one definition each (Sprint 10 Q7): see Support.h.
#include "../Common.h"

namespace stub_support
{

    std::unordered_map<std::string, CdFileEntry> g_cdFilesByKey;
    std::unordered_map<std::string, std::filesystem::path> g_cdLeafIndex;
    std::unordered_map<std::string, std::filesystem::path> g_cdLoosePathIndex;
    std::filesystem::path g_cdLeafIndexRoot;
    bool g_cdLeafIndexBuilt = false;
    uint32_t g_nextPseudoLbn = kCdPseudoLbnStart;
    std::filesystem::path g_cdImageSizePath;
    uint64_t g_cdImageSizeBytes = 0;
    bool g_cdImageSizeValid = false;
    int32_t g_lastCdError = 0;
    uint32_t g_cdMode = 0;
    uint32_t g_cdStreamingLbn = 0;
    uint32_t g_cdStreamingEndLbn = 0xFFFFFFFFu;
    bool g_cdInitialized = false;

    uint32_t g_iopHeapNext = kIopHeapBase;

    std::string toLowerAscii(std::string value)
    {
        std::transform(value.begin(), value.end(), value.begin(),
                       [](unsigned char c)
                       { return static_cast<char>(std::tolower(c)); });
        return value;
    }

    std::string stripIsoVersionSuffix(std::string value)
    {
        const std::size_t semicolon = value.find(';');
        if (semicolon == std::string::npos)
        {
            return value;
        }

        bool numericSuffix = semicolon + 1 < value.size();
        for (std::size_t i = semicolon + 1; i < value.size(); ++i)
        {
            if (!std::isdigit(static_cast<unsigned char>(value[i])))
            {
                numericSuffix = false;
                break;
            }
        }

        if (numericSuffix)
        {
            value.erase(semicolon);
        }
        return value;
    }

    std::string normalizePathSeparators(std::string value)
    {
        std::replace(value.begin(), value.end(), '\\', '/');
        return value;
    }

    void trimLeadingSeparators(std::string &value)
    {
        while (!value.empty() && (value.front() == '/' || value.front() == '\\'))
        {
            value.erase(value.begin());
        }
    }

    std::string normalizeCdPathNoPrefix(std::string path)
    {
        path = normalizePathSeparators(std::move(path));
        std::string lower = toLowerAscii(path);
        if (lower.rfind("cdrom0:", 0) == 0)
        {
            path = path.substr(7);
        }
        else if (lower.rfind("cdrom:", 0) == 0)
        {
            path = path.substr(6);
        }

        trimLeadingSeparators(path);
        while (!path.empty() && std::isspace(static_cast<unsigned char>(path.front())))
        {
            path.erase(path.begin());
        }
        while (!path.empty() && std::isspace(static_cast<unsigned char>(path.back())))
        {
            path.pop_back();
        }
        path = stripIsoVersionSuffix(std::move(path));
        return path;
    }

    std::string normalizeCdLooseNumericKey(std::string value)
    {
        value = toLowerAscii(stripIsoVersionSuffix(normalizePathSeparators(std::move(value))));
        std::string normalized;
        normalized.reserve(value.size());
        for (std::size_t i = 0; i < value.size();)
        {
            if (!std::isdigit(static_cast<unsigned char>(value[i])))
            {
                normalized.push_back(value[i]);
                ++i;
                continue;
            }

            std::size_t end = i + 1;
            while (end < value.size() && std::isdigit(static_cast<unsigned char>(value[end])))
            {
                ++end;
            }

            std::size_t firstNonZero = i;
            while (firstNonZero + 1 < end && value[firstNonZero] == '0')
            {
                ++firstNonZero;
            }

            normalized.append(value, firstNonZero, end - firstNonZero);
            i = end;
        }

        return normalized;
    }

    std::string cdLoosePathKeyFromRelative(const std::filesystem::path &relative)
    {
        const std::string normalized = normalizeCdPathNoPrefix(relative.generic_string());
        if (normalized.empty())
        {
            throw std::runtime_error("cdLoosePathKeyFromRelative: normalized path is empty");
        }

        const std::filesystem::path relPath(normalized);
        std::string parent = toLowerAscii(normalizePathSeparators(relPath.parent_path().generic_string()));
        const std::string leaf = normalizeCdLooseNumericKey(relPath.filename().string());

        if (parent.empty())
        {
            return leaf;
        }
        return parent + "/" + leaf;
    }

    std::string cdLoosePathKey(const std::string &ps2Path)
    {
        return cdLoosePathKeyFromRelative(std::filesystem::path(normalizeCdPathNoPrefix(ps2Path)));
    }

    std::filesystem::path getCdRootPath()
    {
        const PS2Runtime::IoPaths &paths = PS2Runtime::getIoPaths();
        if (!paths.cdRoot.empty())
        {
            return paths.cdRoot;
        }
        if (!paths.elfDirectory.empty())
        {
            return paths.elfDirectory;
        }

        std::error_code ec;
        const std::filesystem::path cwd = std::filesystem::current_path(ec);
        return ec ? std::filesystem::path(".") : cwd.lexically_normal();
    }

    std::filesystem::path getCdImagePath()
    {
        return PS2Runtime::getIoPaths().cdImage;
    }

    bool tryGetCdImageTotalSectors(uint64_t &totalSectorsOut)
    {
        const std::filesystem::path imagePath = getCdImagePath();
        if (imagePath.empty())
        {
            return false;
        }

        if (!g_cdImageSizeValid || g_cdImageSizePath != imagePath)
        {
            std::error_code ec;
            g_cdImageSizeBytes = static_cast<uint64_t>(std::filesystem::file_size(imagePath, ec));
            g_cdImageSizePath = imagePath;
            g_cdImageSizeValid = !ec;
        }
        if (!g_cdImageSizeValid)
        {
            return false;
        }

        totalSectorsOut = g_cdImageSizeBytes / static_cast<uint64_t>(kCdSectorSize);
        return true;
    }

    uint32_t sectorsForBytes(uint64_t byteCount)
    {
        const uint64_t sectors = (byteCount + (kCdSectorSize - 1)) / kCdSectorSize;
        return sectors > 0 ? static_cast<uint32_t>(sectors) : 1;
    }

    std::string cdPathKey(const std::string &ps2Path)
    {
        return toLowerAscii(normalizeCdPathNoPrefix(ps2Path));
    }

    std::filesystem::path cdHostPath(const std::string &ps2Path)
    {
        const std::string normalized = normalizeCdPathNoPrefix(ps2Path);
        std::filesystem::path resolved = getCdRootPath();
        if (!normalized.empty())
        {
            resolved /= std::filesystem::path(normalized);
        }
        return resolved.lexically_normal();
    }

    bool resolveCaseInsensitivePath(const std::filesystem::path &root,
                                    const std::filesystem::path &relative,
                                    std::filesystem::path &resolvedOut)
    {
        std::filesystem::path current = root;
        for (const auto &component : relative)
        {
            const std::filesystem::path direct = current / component;
            std::error_code ec;
            if (std::filesystem::exists(direct, ec) && !ec)
            {
                current = direct;
                continue;
            }

            bool matched = false;
            const std::string needle = toLowerAscii(component.string());
            std::error_code iterEc;
            for (const auto &entry : std::filesystem::directory_iterator(current, iterEc))
            {
                if (iterEc)
                {
                    break;
                }

                const std::string candidate = toLowerAscii(entry.path().filename().string());
                if (candidate == needle)
                {
                    current = entry.path();
                    matched = true;
                    break;
                }
            }

            if (!matched)
            {
                return false;
            }
        }

        std::error_code fileEc;
        if (std::filesystem::is_regular_file(current, fileEc) && !fileEc)
        {
            resolvedOut = current;
            return true;
        }
        return false;
    }

    void ensureCdLeafIndex(const std::filesystem::path &root)
    {
        if (g_cdLeafIndexBuilt && g_cdLeafIndexRoot == root)
        {
            return;
        }

        g_cdLeafIndex.clear();
        g_cdLoosePathIndex.clear();
        g_cdLeafIndexRoot = root;
        g_cdLeafIndexBuilt = true;

        std::error_code ec;
        if (!std::filesystem::exists(root, ec) || ec)
        {
            return;
        }

        for (const auto &entry : std::filesystem::recursive_directory_iterator(
                 root, std::filesystem::directory_options::skip_permission_denied, ec))
        {
            if (ec)
            {
                break;
            }
            if (!entry.is_regular_file())
            {
                continue;
            }

            const std::string leaf = toLowerAscii(entry.path().filename().string());
            g_cdLeafIndex.emplace(leaf, entry.path());

            std::error_code relEc;
            const std::filesystem::path relative = std::filesystem::relative(entry.path(), root, relEc);
            if (!relEc)
            {
                const std::string looseKey = cdLoosePathKeyFromRelative(relative);
                if (!looseKey.empty())
                {
                    g_cdLoosePathIndex.emplace(looseKey, entry.path());
                }
            }
        }
    }

    bool registerCdFile(const std::string &ps2Path, CdFileEntry &entryOut)
    {
        const std::string key = cdPathKey(ps2Path);
        if (key.empty())
        {
            g_lastCdError = -1;
            return false;
        }

        auto existing = g_cdFilesByKey.find(key);
        if (existing != g_cdFilesByKey.end())
        {
            entryOut = existing->second;
            g_lastCdError = 0;
            return true;
        }

        const std::filesystem::path root = getCdRootPath();
        std::filesystem::path path = cdHostPath(ps2Path);
        std::error_code ec;
        if (!std::filesystem::exists(path, ec) || ec || !std::filesystem::is_regular_file(path, ec))
        {
            const std::filesystem::path relative(normalizeCdPathNoPrefix(ps2Path));
            std::filesystem::path resolvedCasePath;
            if (resolveCaseInsensitivePath(root, relative, resolvedCasePath))
            {
                path = resolvedCasePath;
                ec.clear();
            }
            else
            {
                ensureCdLeafIndex(root);
                const std::string leaf = toLowerAscii(relative.filename().string());
                auto it = g_cdLeafIndex.find(leaf);
                if (it != g_cdLeafIndex.end())
                {
                    path = it->second;
                    ec.clear();
                }
                else
                {
                    const std::string looseKey = cdLoosePathKey(ps2Path);
                    auto looseIt = g_cdLoosePathIndex.find(looseKey);
                    if (looseIt != g_cdLoosePathIndex.end())
                    {
                        path = looseIt->second;
                        ec.clear();
                    }
                    else
                    {
                        g_lastCdError = -1;
                        return false;
                    }
                }
            }
        }

        const uint64_t sizeBytes = std::filesystem::file_size(path, ec);
        if (ec)
        {
            g_lastCdError = -1;
            return false;
        }

        CdFileEntry entry;
        entry.hostPath = path;
        entry.sizeBytes = static_cast<uint32_t>(std::min<uint64_t>(sizeBytes, 0xFFFFFFFFu));
        entry.baseLbn = g_nextPseudoLbn;
        entry.sectors = sectorsForBytes(sizeBytes);

        g_nextPseudoLbn += entry.sectors + 1;
        g_cdFilesByKey.emplace(key, entry);
        entryOut = entry;
        g_lastCdError = 0;
        return true;
    }

    bool readHostRange(const std::filesystem::path &path, uint64_t offsetBytes, uint8_t *dst, size_t byteCount)
    {
        if (!dst)
        {
            g_lastCdError = -1;
            return false;
        }
        if (byteCount == 0)
        {
            g_lastCdError = 0;
            return true;
        }

        std::memset(dst, 0, byteCount);
        std::ifstream file(path, std::ios::binary);
        if (!file.is_open())
        {
            g_lastCdError = -1;
            return false;
        }

        file.seekg(static_cast<std::streamoff>(offsetBytes), std::ios::beg);
        if (!file.good())
        {
            g_lastCdError = -1;
            return false;
        }

        file.read(reinterpret_cast<char *>(dst), static_cast<std::streamsize>(byteCount));
        g_lastCdError = 0;
        return true;
    }

    bool readCdSectors(uint32_t lbn, uint32_t sectors, uint8_t *dst, size_t byteCount)
    {
        for (const auto &[key, entry] : g_cdFilesByKey)
        {
            const uint32_t endLbn = entry.baseLbn + entry.sectors;
            if (lbn < entry.baseLbn || lbn >= endLbn)
            {
                continue;
            }

            const uint64_t relativeLbn = static_cast<uint64_t>(lbn - entry.baseLbn);
            const uint64_t offset = relativeLbn * kCdSectorSize;
            return readHostRange(entry.hostPath, offset, dst, byteCount);
        }

        const std::filesystem::path cdImage = getCdImagePath();
        if (!cdImage.empty())
        {
            uint64_t totalSectors = 0;
            if (tryGetCdImageTotalSectors(totalSectors))
            {
                const uint64_t start = static_cast<uint64_t>(lbn);
                const uint64_t end = start + static_cast<uint64_t>(sectors);
                if (start >= totalSectors || end > totalSectors)
                {
                    g_lastCdError = -1;
                    return false;
                }
            }

            const uint64_t offset = static_cast<uint64_t>(lbn) * kCdSectorSize;
            return readHostRange(cdImage, offset, dst, byteCount);
        }

        std::cerr << "sceCdRead unresolved LBN 0x" << std::hex << lbn
                  << " sectors=" << std::dec << sectors
                  << " (no mapped file and no configured CD image)" << std::endl;
        g_lastCdError = -1;
        return false;
    }

    bool isResolvableCdLbn(uint32_t lbn)
    {
        for (const auto &[key, entry] : g_cdFilesByKey)
        {
            const uint32_t endLbn = entry.baseLbn + entry.sectors;
            if (lbn >= entry.baseLbn && lbn < endLbn)
            {
                return true;
            }
        }

        uint64_t totalSectors = 0;
        if (tryGetCdImageTotalSectors(totalSectors))
        {
            return static_cast<uint64_t>(lbn) < totalSectors;
        }

        return false;
    }

    bool findRegisteredCdFileForLbn(uint32_t lbn, CdFileEntry &entryOut)
    {
        for (const auto &[key, entry] : g_cdFilesByKey)
        {
            const uint32_t endLbn = entry.baseLbn + entry.sectors;
            if (lbn >= entry.baseLbn && lbn < endLbn)
            {
                entryOut = entry;
                return true;
            }
        }
        return false;
    }

    uint32_t cdStreamingEndLbnForStart(uint32_t lbn)
    {
        CdFileEntry entry{};
        if (findRegisteredCdFileForLbn(lbn, entry))
        {
            return entry.baseLbn + entry.sectors;
        }
        return 0xFFFFFFFFu;
    }

    bool writeCdSearchResult(uint8_t *rdram, uint32_t fileAddr, const std::string &ps2Path, const CdFileEntry &entry)
    {
        // sceCdlFILE layout: u32 lsn, u32 size, char name[16], u8 date[8]
        uint8_t *fileStruct = getMemPtr(rdram, fileAddr);
        if (!fileStruct)
        {
            return false;
        }

        std::array<uint8_t, 32> packed{};
        std::memcpy(packed.data() + 0, &entry.baseLbn, sizeof(entry.baseLbn));
        std::memcpy(packed.data() + 4, &entry.sizeBytes, sizeof(entry.sizeBytes));

        std::filesystem::path leafPath(normalizeCdPathNoPrefix(ps2Path));
        std::string leaf = leafPath.filename().string();
        leaf = stripIsoVersionSuffix(std::move(leaf));
        std::strncpy(reinterpret_cast<char *>(packed.data() + 8), leaf.c_str(), 15);

        std::memcpy(fileStruct, packed.data(), packed.size());
        return true;
    }

    uint8_t toBcd(uint32_t value)
    {
        const uint32_t clamped = value % 100;
        return static_cast<uint8_t>(((clamped / 10) << 4) | (clamped % 10));
    }

    uint32_t fromBcd(uint8_t value)
    {
        return static_cast<uint32_t>(((value >> 4) & 0x0F) * 10 + (value & 0x0F));
    }

    std::unordered_map<uint32_t, FILE *> g_file_map;
    uint32_t g_next_file_handle = 1; // Start file handles > 0 (0 is NULL)
    std::mutex g_file_mutex;

    uint32_t generate_file_handle()
    {
        uint32_t handle = 0;
        do
        {
            handle = g_next_file_handle++;
            if (g_next_file_handle == 0)
                g_next_file_handle = 1;
        } while (handle == 0 || g_file_map.count(handle));
        return handle;
    }

    FILE *get_file_ptr(uint32_t handle)
    {
        if (handle == 0)
            return nullptr;
        std::lock_guard<std::mutex> lock(g_file_mutex);
        auto it = g_file_map.find(handle);
        return (it != g_file_map.end()) ? it->second : nullptr;
    }

}
namespace stub_support
{
    // convert a host pointer within rdram back to a PS2 address
    uint32_t hostPtrToPs2Addr(uint8_t *rdram, const void *hostPtr)
    {
        if (!hostPtr)
            return 0; // Handle NULL pointer case

        const uint8_t *ptr_u8 = static_cast<const uint8_t *>(hostPtr);
        std::ptrdiff_t offset = ptr_u8 - rdram;

        // Check if is in rdram range
        if (offset >= 0 && static_cast<size_t>(offset) < PS2_RAM_SIZE)
        {
            return PS2_RAM_BASE + static_cast<uint32_t>(offset);
        }
        else
        {
            std::cerr << "Warning: hostPtrToPs2Addr failed - host pointer " << hostPtr << " is outside rdram range [" << static_cast<void *>(rdram) << ", " << static_cast<void *>(rdram + PS2_RAM_SIZE) << ")" << std::endl;
            return 0;
        }
    }

}
namespace stub_support
{
    bool tryReadWordFromRdram(uint8_t *rdram, uint32_t addr, uint32_t &outWord)
    {
        const uint8_t *ptr = getConstMemPtr(rdram, addr);
        if (!ptr)
        {
            return false;
        }
        std::memcpy(&outWord, ptr, sizeof(outWord));
        return true;
    }

    bool tryReadWordFromGuest(uint8_t *rdram, PS2Runtime *runtime, uint32_t addr, uint32_t &outWord)
    {
        if (tryReadWordFromRdram(rdram, addr, outWord))
        {
            return true;
        }

        if (runtime)
        {
            try
            {
                PS2Memory &mem = runtime->memory();
                outWord = static_cast<uint32_t>(mem.read8(addr + 0u)) |
                          (static_cast<uint32_t>(mem.read8(addr + 1u)) << 8u) |
                          (static_cast<uint32_t>(mem.read8(addr + 2u)) << 16u) |
                          (static_cast<uint32_t>(mem.read8(addr + 3u)) << 24u);
                return true;
            }
            catch (...)
            {
                return false;
            }
        }
        return false;
    }

    bool tryReadByteFromGuest(uint8_t *rdram, PS2Runtime *runtime, uint32_t addr, uint8_t &outByte)
    {
        const uint8_t *chPtr = getConstMemPtr(rdram, addr);
        if (chPtr)
        {
            outByte = *chPtr;
            return true;
        }

        if (runtime)
        {
            try
            {
                outByte = runtime->memory().read8(addr);
                return true;
            }
            catch (...)
            {
                return false;
            }
        }
        return false;
    }

    bool writeGuestBytes(uint8_t *rdram, PS2Runtime *runtime, uint32_t addr, const uint8_t *src, size_t len)
    {
        if (!src || len == 0)
        {
            return true;
        }

        bool allViaPtrs = true;
        for (size_t i = 0; i < len; ++i)
        {
            const uint64_t guestAddr = static_cast<uint64_t>(addr) + i;
            if (guestAddr > 0xFFFFFFFFull)
            {
                return false;
            }
            uint8_t *dst = getMemPtr(rdram, static_cast<uint32_t>(guestAddr));
            if (!dst)
            {
                allViaPtrs = false;
                break;
            }
            *dst = src[i];
        }
        if (allViaPtrs)
        {
            return true;
        }

        if (runtime)
        {
            try
            {
                PS2Memory &mem = runtime->memory();
                for (size_t i = 0; i < len; ++i)
                {
                    const uint64_t guestAddr = static_cast<uint64_t>(addr) + i;
                    if (guestAddr > 0xFFFFFFFFull)
                    {
                        return false;
                    }
                    mem.write8(static_cast<uint32_t>(guestAddr), src[i]);
                }
                return true;
            }
            catch (...)
            {
                return false;
            }
        }

        return false;
    }

    std::string readPs2CStringBounded(uint8_t *rdram, PS2Runtime *runtime, uint32_t addr, size_t maxLen)
    {
        std::string out;
        if (addr == 0 || maxLen == 0)
        {
            return out;
        }

        out.reserve(std::min<size_t>(maxLen, 128));
        for (size_t i = 0; i < maxLen; ++i)
        {
            const uint64_t guestAddr = static_cast<uint64_t>(addr) + i;
            if (guestAddr > 0xFFFFFFFFull)
            {
                break;
            }

            uint8_t chByte = 0;
            if (!tryReadByteFromGuest(rdram, runtime, static_cast<uint32_t>(guestAddr), chByte))
            {
                break;
            }

            const char ch = static_cast<char>(chByte);
            if (ch == '\0')
            {
                break;
            }
            out.push_back(ch);
        }

        return out;
    }

    std::string readPs2CStringBounded(uint8_t *rdram, uint32_t addr, size_t maxLen)
    {
        return readPs2CStringBounded(rdram, nullptr, addr, maxLen);
    }

    std::string sanitizeForLog(const std::string &value)
    {
        std::string out;
        out.reserve(value.size());
        for (unsigned char ch : value)
        {
            if (ch == '\n' || ch == '\r' || ch == '\t' || (ch >= 0x20 && ch < 0x7F))
            {
                out.push_back(static_cast<char>(ch));
            }
            else
            {
                out.push_back('.');
            }
        }
        return out;
    }

    std::string formatPs2StringWithArgs(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime, const char *format, int fixedArgs)
    {
        Ps2VarArgCursor cursor(rdram, ctx, runtime, fixedArgs);
        return formatPs2StringCore(
            rdram,
            format,
            [&cursor]()
            { return cursor.nextU32(); },
            [&cursor]()
            { return cursor.nextU64(); },
            [rdram, runtime](uint32_t addr)
            { return readPs2CStringBounded(rdram, runtime, addr); });
    }

    std::string formatPs2StringWithVaList(uint8_t *rdram, PS2Runtime *runtime, const char *format, uint32_t vaListAddr)
    {
        Ps2VaListCursor cursor(rdram, runtime, vaListAddr);
        return formatPs2StringCore(
            rdram,
            format,
            [&cursor]()
            { return cursor.nextU32(); },
            [&cursor]()
            { return cursor.nextU64(); },
            [rdram, runtime](uint32_t addr)
            { return readPs2CStringBounded(rdram, runtime, addr); });
    }

    std::unordered_map<std::string, uint32_t> g_stubWarningCount;
    std::mutex g_stubWarningMutex;
    uint32_t g_printfLogCount = 0;
    std::mutex g_printfLogMutex;

    std::mutex g_dmaStubMutex;
    std::unordered_map<uint32_t, uint32_t> g_dmaPendingPolls;
    uint32_t g_dmaStubLogCount = 0;

    bool isKnownDmaChannelBase(uint32_t value)
    {
        return std::find(kDmaChannelBases.begin(), kDmaChannelBases.end(), value) != kDmaChannelBases.end();
    }

    uint32_t toDmaPhys(uint32_t addr)
    {
        if ((addr & 0x80000000u) != 0)
        {
            uint32_t lower = addr & 0x7FFFFFFFu;
            if (lower >= PS2_SCRATCHPAD_BASE &&
                lower < PS2_SCRATCHPAD_BASE + PS2_SCRATCHPAD_SIZE)
            {
                return lower;
            }
        }
        return addr & 0x1FFFFFFFu;
    }

    uint32_t normalizeQwcFromArg(uint32_t value)
    {
        if (value == 0)
        {
            return 0;
        }
        if (value > 0xFFFFu)
        {
            return std::min<uint32_t>((value + 15u) >> 4u, 0xFFFFu);
        }
        return value & 0xFFFFu;
    }

    ParsedDmaTag tryParseDmaTag(uint8_t *rdram, uint32_t guestAddr)
    {
        ParsedDmaTag out;
        if (guestAddr == 0)
        {
            return out;
        }

        const uint8_t *ptr = getConstMemPtr(rdram, guestAddr);
        if (!ptr)
        {
            return out;
        }

        uint64_t tag = 0;
        std::memcpy(&tag, ptr, sizeof(tag));
        out.valid = true;
        out.qwc = static_cast<uint32_t>(tag & 0xFFFFu);
        out.id = static_cast<uint32_t>((tag >> 28) & 0x7u);
        out.addr = static_cast<uint32_t>((tag >> 32) & 0x7FFFFFFFu);
        return out;
    }

    uint32_t resolveDmaChannelBase(uint8_t *rdram, uint32_t chanArg)
    {
        if (isKnownDmaChannelBase(chanArg))
        {
            return chanArg;
        }
        if (chanArg < kDmaChannelBases.size())
        {
            return kDmaChannelBases[chanArg];
        }

        const uint32_t masked = chanArg & 0xFFFFFF00u;
        if (isKnownDmaChannelBase(masked))
        {
            return masked;
        }

        uint32_t candidate0 = 0;
        if (!tryReadWordFromRdram(rdram, chanArg, candidate0))
        {
            return 0;
        }
        if (isKnownDmaChannelBase(candidate0))
        {
            return candidate0;
        }

        uint32_t candidate1 = 0;
        if (!tryReadWordFromRdram(rdram, chanArg + 4u, candidate1))
        {
            return 0;
        }
        if (isKnownDmaChannelBase(candidate1))
        {
            return candidate1;
        }

        return 0;
    }

    int32_t submitDmaSend(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime, bool preferNormalCount)
    {
        if (!runtime)
        {
            return -1;
        }

        const uint32_t chanArg = getRegU32(ctx, 4);
        const uint32_t payloadArg = getRegU32(ctx, 5);
        const uint32_t countArg = getRegU32(ctx, 6);
        const uint32_t channelBase = resolveDmaChannelBase(rdram, chanArg);
        if (channelBase == 0)
        {
            return -1;
        }

        const uint32_t payloadPhys = toDmaPhys(payloadArg);
        uint32_t madr = 0;
        uint32_t qwc = 0;
        uint32_t tadr = payloadPhys;
        // CHCR bits: DIR=0, MOD=2-3, ASP=4-5, TTE=6, TIE=7, STR=8. Sony's libdma sends chains with
        // TTE=1 (the DMAtag's upper 64 bits carry VIFcodes: STBASE/STOFFSET, MPG...), which is also
        // what the game's own MFIFO sends use (0x145). This used to set TIE (0x185) instead, so the
        // tag upper halves were only delivered by an unconditional hack in the chain walker.
        uint32_t chcr = 0x00000101u; // DIR=1, STR=1 (normal mode).

        if (preferNormalCount)
        {
            qwc = normalizeQwcFromArg(countArg);
            madr = payloadPhys;
        }
        else
        {
            chcr = 0x00000145u; // MOD=1 chain, DIR=1, TTE=1, STR=1.
        }

        PS2Memory &mem = runtime->memory();
        mem.writeIORegister(channelBase + 0x20u, qwc & 0xFFFFu);
        mem.writeIORegister(channelBase + 0x10u, madr);
        mem.writeIORegister(channelBase + 0x30u, tadr);
        mem.writeIORegister(channelBase + 0x00u, chcr);
        mem.processPendingTransfers();

        std::vector<uint32_t> completedCauses = mem.consumeCompletedDmacCauses();
        if (completedCauses.empty() && (mem.readIORegister(channelBase + 0x00u) & 0x100u) == 0u)
        {
            if (channelBase == 0x10008000u)
            {
                completedCauses.push_back(0u);
            }
            else if (channelBase == 0x10009000u)
            {
                completedCauses.push_back(1u);
            }
            else if (channelBase == 0x1000A000u)
            {
                completedCauses.push_back(2u);
            }
        }

        {
            std::lock_guard<std::mutex> lock(g_dmaStubMutex);
            g_dmaPendingPolls[channelBase] = 1;
            if (g_dmaStubLogCount < kMaxDmaStubLogs)
            {
                RUNTIME_LOG("[sceDmaSend] ch=0x" << std::hex << channelBase
                          << " madr=0x" << madr
                          << " qwc=0x" << qwc
                          << " tadr=0x" << tadr
                          << " chcr=0x" << chcr << std::dec << std::endl);

                if (!preferNormalCount && (channelBase == 0x10009000u || channelBase == 0x1000A000u))
                {
                    if (const uint8_t *tagPtr = getConstMemPtr(rdram, tadr))
                    {
                        uint64_t tagLo = 0u;
                        std::memcpy(&tagLo, tagPtr, sizeof(tagLo));
                        uint32_t w2 = 0u;
                        uint32_t w3 = 0u;
                        std::memcpy(&w2, tagPtr + 8u, sizeof(w2));
                        std::memcpy(&w3, tagPtr + 12u, sizeof(w3));
                        RUNTIME_LOG("[sceDmaSend:head] ch=0x" << std::hex << channelBase
                                  << " tagQwc=0x" << static_cast<uint32_t>(tagLo & 0xFFFFu)
                                  << " id=0x" << static_cast<uint32_t>((tagLo >> 28u) & 0x7u)
                                  << " irq=0x" << static_cast<uint32_t>((tagLo >> 31u) & 0x1u)
                                  << " addr=0x" << static_cast<uint32_t>((tagLo >> 32u) & 0x7FFFFFFFu)
                                  << " w2=0x" << w2
                                  << " w3=0x" << w3
                                  << std::dec << std::endl);
                    }
                }
                ++g_dmaStubLogCount;
            }
        }

        for (const uint32_t completedCause : completedCauses)
        {
            ps2_syscalls::dispatchDmacHandlersForCause(rdram, runtime, completedCause);
        }

        return 0;
    }

    int32_t submitDmaSync(uint8_t *rdram, R5900Context *ctx, PS2Runtime *runtime)
    {
        if (!runtime)
        {
            return -1;
        }

        const uint32_t chanArg = getRegU32(ctx, 4);
        const uint32_t mode = getRegU32(ctx, 5);
        const uint32_t channelBase = resolveDmaChannelBase(rdram, chanArg);
        if (channelBase == 0)
        {
            return -1;
        }

        bool modelBusy = false;
        {
            std::lock_guard<std::mutex> lock(g_dmaStubMutex);
            auto it = g_dmaPendingPolls.find(channelBase);
            if (it != g_dmaPendingPolls.end() && it->second > 0)
            {
                modelBusy = true;
                if (mode != 0)
                {
                    --it->second;
                    if (it->second == 0)
                    {
                        g_dmaPendingPolls.erase(it);
                    }
                }
                else
                {
                    // Blocking mode: complete immediately in this runtime.
                    g_dmaPendingPolls.erase(it);
                }
            }
        }

        const uint32_t chcr = runtime->memory().readIORegister(channelBase + 0x00u);
        const bool hwBusy = (chcr & 0x100u) != 0;
        return ((modelBusy || hwBusy) && mode != 0) ? 1 : 0;
    }

}
namespace stub_support
{

    GsGParam g_gparam{1, 2, 1, 3}; // Default: interlaced NTSC, frame mode.

    uint64_t makePmode(uint32_t en1, uint32_t en2, uint32_t mmod, uint32_t amod, uint32_t slbg, uint32_t alp)
    {
        return (static_cast<uint64_t>(en1 & 1) << 0) |
               (static_cast<uint64_t>(en2 & 1) << 1) |
               (static_cast<uint64_t>(1) << 2) |
               (static_cast<uint64_t>(mmod & 1) << 5) |
               (static_cast<uint64_t>(amod & 1) << 6) |
               (static_cast<uint64_t>(slbg & 1) << 7) |
               (static_cast<uint64_t>(alp & 0xFF) << 8);
    }

    uint64_t makeDispFb(uint32_t fbp, uint32_t fbw, uint32_t psm, uint32_t dbx, uint32_t dby)
    {
        return (static_cast<uint64_t>(fbp & 0x1FF) << 0) |
               (static_cast<uint64_t>(fbw & 0x3F) << 9) |
               (static_cast<uint64_t>(psm & 0x1F) << 15) |
               (static_cast<uint64_t>(dbx & 0x7FF) << 32) |
               (static_cast<uint64_t>(dby & 0x7FF) << 43);
    }

    uint64_t makeDisplay(uint32_t dx, uint32_t dy, uint32_t magh, uint32_t magv, uint32_t dw, uint32_t dh)
    {
        return (static_cast<uint64_t>(dx & 0x0FFF) << 0) |
               (static_cast<uint64_t>(dy & 0x07FF) << 12) |
               (static_cast<uint64_t>(magh & 0x0F) << 23) |
               (static_cast<uint64_t>(magv & 0x03) << 27) |
               (static_cast<uint64_t>(dw & 0x0FFF) << 32) |
               (static_cast<uint64_t>(dh & 0x07FF) << 44);
    }

    uint64_t makeFrame(uint32_t fbp, uint32_t fbw, uint32_t psm, uint32_t fbmsk)
    {
        return (static_cast<uint64_t>(fbp & 0x1FFu) << 0) |
               (static_cast<uint64_t>(fbw & 0x3Fu) << 16) |
               (static_cast<uint64_t>(psm & 0x3Fu) << 24) |
               (static_cast<uint64_t>(fbmsk) << 32);
    }

    uint64_t makeZbuf(uint32_t zbp, uint32_t psm, bool zmsk)
    {
        return (static_cast<uint64_t>(zbp & 0x1FFu) << 0) |
               (static_cast<uint64_t>(psm & 0xFu) << 24) |
               (static_cast<uint64_t>(zmsk ? 1u : 0u) << 32);
    }

    uint64_t makeXYOffset(int32_t width, int32_t height)
    {
        const int32_t offX = 0x800 - (width >> 1);
        const int32_t offY = 0x800 - (height >> 1);
        return (static_cast<uint64_t>(static_cast<uint32_t>(offY) & 0xFFFFu) << 36) |
               (static_cast<uint64_t>(static_cast<uint32_t>(offX) & 0xFFFFu) << 4);
    }

    uint64_t makeScissor(int32_t width, int32_t height)
    {
        return (static_cast<uint64_t>(0u) << 0) |
               (static_cast<uint64_t>(static_cast<uint32_t>(width - 1) & 0x7FFu) << 16) |
               (static_cast<uint64_t>(0u) << 32) |
               (static_cast<uint64_t>(static_cast<uint32_t>(height - 1) & 0x7FFu) << 48);
    }

    uint64_t makeTest(uint32_t ztest)
    {
        if ((ztest & 0x3u) == 0u)
        {
            return 0x30000ULL;
        }
        return (static_cast<uint64_t>(ztest & 0x3u) << 17) | 0x10000ULL;
    }

    uint64_t makeGiftagAplusD(uint32_t nloop)
    {
        return (static_cast<uint64_t>(nloop & 0x7FFFu) << 0) |
               (static_cast<uint64_t>(1u) << 15) |
               (static_cast<uint64_t>(1u) << 60);
    }

    // Like makeGiftagAplusD but leaves EOP (bit 15) clear, for a chained/open
    // A+D tag whose nloop is finalized later by closePacketGifTag.
    uint64_t makeGiftagAplusDOpen(uint32_t nloop)
    {
        return (static_cast<uint64_t>(nloop & 0x7FFFu) << 0) |
               (static_cast<uint64_t>(1u) << 60);
    }

    uint32_t readStackU32(uint8_t *rdram, R5900Context *ctx, uint32_t offset)
    {
        uint32_t sp = getRegU32(ctx, 29);
        const uint8_t *ptr = getConstMemPtr(rdram, sp + offset);
        if (!ptr)
            return 0;
        uint32_t value = 0;
        std::memcpy(&value, ptr, sizeof(value));
        return value;
    }

    uint32_t bytesForPixels(uint8_t psm, uint32_t pixelCount)
    {
        const uint64_t pixels = static_cast<uint64_t>(pixelCount);
        uint64_t bytes = 0;
        switch (psm)
        {
        case 0:  // PSMCT32
        case 1:  // PSMCT24 (treat as 32)
        case 27: // PSMT8H (packed in 32-bit lanes)
        case 36: // PSMT4HL (packed in 32-bit lanes)
        case 44: // PSMT4HH (packed in 32-bit lanes)
            bytes = pixels * 4ull;
            break;
        case 2:  // PSMCT16
        case 10: // PSMCT16S
            bytes = pixels * 2ull;
            break;
        case 19: // PSMT8
            bytes = pixels;
            break;
        case 20: // PSMT4
            bytes = (pixels + 1ull) / 2ull;
            break;
        default:
            bytes = pixels * 4ull;
            break;
        }
        if (bytes > 0xFFFFFFFFull)
        {
            return 0xFFFFFFFFu;
        }
        return static_cast<uint32_t>(bytes);
    }

    GsSetDefImageArgs decodeGsSetDefImageArgs(uint8_t *rdram, R5900Context *ctx)
    {
        GsSetDefImageArgs decoded{};

        const uint32_t reg8 = getRegU32(ctx, 8);
        const uint32_t reg9 = getRegU32(ctx, 9);
        const uint32_t reg10 = getRegU32(ctx, 10);
        const uint32_t reg11 = getRegU32(ctx, 11);

        const uint32_t stack0 = readStackU32(rdram, ctx, 16);
        const uint32_t stack1 = readStackU32(rdram, ctx, 20);
        const uint32_t stack2 = readStackU32(rdram, ctx, 24);
        const uint32_t stack3 = readStackU32(rdram, ctx, 28);

        const bool looksLikeCanonicalRegs = (reg10 != 0u || reg11 != 0u);
        const bool looksLikeCanonicalStack = (stack2 != 0u || stack3 != 0u);

        if (looksLikeCanonicalRegs || looksLikeCanonicalStack)
        {
            decoded.vramAddr = getRegU32(ctx, 5);
            decoded.vramWidth = getRegU32(ctx, 6);
            decoded.psm = getRegU32(ctx, 7);

            if (looksLikeCanonicalRegs)
            {
                decoded.x = reg8;
                decoded.y = reg9;
                decoded.width = reg10;
                decoded.height = reg11;
            }
            else
            {
                decoded.x = stack0;
                decoded.y = stack1;
                decoded.width = stack2;
                decoded.height = stack3;
            }
            return decoded;
        }

        // Legacy code
        // a1=x, a2=y, a3=w, stack/reg extension for h/vram/fbw/psm.
        decoded.x = getRegU32(ctx, 5);
        decoded.y = getRegU32(ctx, 6);
        decoded.width = getRegU32(ctx, 7);
        decoded.height = stack0 != 0u ? stack0 : reg8;
        decoded.vramAddr = stack1 != 0u ? stack1 : reg9;
        decoded.vramWidth = stack2 != 0u ? stack2 : reg10;
        decoded.psm = stack3 != 0u ? stack3 : reg11;
        return decoded;
    }

    // libgraph's sceGsLoadImage (6 quadwords) and sceGsStoreImage (7 quadwords) packets, exactly as the SCE
    // library lays them out in guest memory -- a game may inspect or patch them and DMA them itself. SOCOM II's
    // auto-exposure thread reads the store packet's source PSM at byte 0x23 and its TRXREG at 0x40/0x44, patches
    // TRXPOS at 0x30 and sends the seven quadwords through VIF1 (research/31 section 13). Until 2026-09-16 the
    // HLE wrote a private 12-byte GsImageMem there instead, and that thread computed a zero-sized transfer.
    //
    //   sceGsLoadImage:  giftag(NLOOP=4 A+D) | BITBLTBUF | TRXPOS | TRXREG | TRXDIR=0 | giftag(IMAGE, NLOOP=qwc)
    //   sceGsStoreImage: vif1 codes (NOP NOP FLUSHA DIRECT 6) | giftag(NLOOP=5 A+D) | BITBLTBUF | TRXPOS | TRXREG |
    //                    FINISH | TRXDIR=1
    void writeGsQword(uint8_t *ptr, uint64_t lo, uint64_t hi)
    {
        std::memcpy(ptr, &lo, 8);
        std::memcpy(ptr + 8, &hi, 8);
    }

    uint64_t gsImageQwc(const GsImageMem &img)
    {
        const uint32_t rowBytes = bytesForPixels(img.psm, static_cast<uint32_t>(img.width));
        const uint32_t total = rowBytes * static_cast<uint32_t>(img.height);
        return (total + 15u) / 16u;
    }

    bool writeGsLoadImagePacket(uint8_t *rdram, uint32_t addr, const GsImageMem &img)
    {
        uint8_t *ptr = getMemPtr(rdram, addr);
        if (!ptr)
            return false;
        const uint64_t bitbltbuf = (static_cast<uint64_t>(img.vram_addr & 0x3FFFu) << 32) |
                                   (static_cast<uint64_t>(img.vram_width & 0x3Fu) << 48) |
                                   (static_cast<uint64_t>(img.psm & 0x3Fu) << 56);
        const uint64_t trxpos = (static_cast<uint64_t>(img.x & 0x7FFu) << 32) | (static_cast<uint64_t>(img.y & 0x7FFu) << 48);
        const uint64_t trxreg = static_cast<uint64_t>(img.width & 0xFFFu) | (static_cast<uint64_t>(img.height & 0xFFFu) << 32);
        writeGsQword(ptr + 0, 4ull | (1ull << 15) | (1ull << 60), 0xEull);
        writeGsQword(ptr + 16, bitbltbuf, 0x50ull);
        writeGsQword(ptr + 32, trxpos, 0x51ull);
        writeGsQword(ptr + 48, trxreg, 0x52ull);
        writeGsQword(ptr + 64, 0ull, 0x53ull);
        writeGsQword(ptr + 80, (gsImageQwc(img) & 0x7FFFull) | (1ull << 15) | (2ull << 58), 0ull);
        return true;
    }

    bool writeGsStoreImagePacket(uint8_t *rdram, uint32_t addr, const GsImageMem &img)
    {
        uint8_t *ptr = getMemPtr(rdram, addr);
        if (!ptr)
            return false;
        const uint64_t bitbltbuf = static_cast<uint64_t>(img.vram_addr & 0x3FFFu) |
                                   (static_cast<uint64_t>(img.vram_width & 0x3Fu) << 16) |
                                   (static_cast<uint64_t>(img.psm & 0x3Fu) << 24);
        const uint64_t trxpos = static_cast<uint64_t>(img.x & 0x7FFu) | (static_cast<uint64_t>(img.y & 0x7FFu) << 16);
        const uint64_t trxreg = static_cast<uint64_t>(img.width & 0xFFFu) | (static_cast<uint64_t>(img.height & 0xFFFu) << 32);
        // VIF1: NOP, NOP, FLUSHA, DIRECT 6 (the six GIF quadwords that follow)
        writeGsQword(ptr + 0, 0x0000000000000000ull, (0x50000006ull << 32) | 0x13000000ull);
        writeGsQword(ptr + 16, 5ull | (1ull << 15) | (1ull << 60), 0xEull);
        writeGsQword(ptr + 32, bitbltbuf, 0x50ull);
        writeGsQword(ptr + 48, trxpos, 0x51ull);
        writeGsQword(ptr + 64, trxreg, 0x52ull);
        writeGsQword(ptr + 80, 0ull, 0x61ull);
        writeGsQword(ptr + 96, 1ull, 0x53ull);
        return true;
    }

    // Parse either packet back: the A+D entries name BITBLTBUF / TRXPOS / TRXREG / TRXDIR, and TRXDIR says
    // which half of BITBLTBUF and TRXPOS (destination for host->local, source for local->host) is the image.
    bool readGsImage(uint8_t *rdram, uint32_t addr, GsImageMem &out)
    {
        const uint8_t *ptr = getConstMemPtr(rdram, addr);
        if (!ptr)
            return false;
        uint64_t bitbltbuf = 0, trxpos = 0, trxreg = 0, trxdir = 3;
        bool sawBuf = false, sawReg = false, sawDir = false;
        for (int q = 0; q < 7; ++q)
        {
            uint64_t lo = 0, hi = 0;
            std::memcpy(&lo, ptr + q * 16, 8);
            std::memcpy(&hi, ptr + q * 16 + 8, 8);
            switch (hi & 0xFFu)
            {
            case 0x50: bitbltbuf = lo; sawBuf = true; break;
            case 0x51: trxpos = lo; break;
            case 0x52: trxreg = lo; sawReg = true; break;
            case 0x53: trxdir = lo & 3u; sawDir = true; break;
            default: break;
            }
        }
        if (!sawBuf || !sawReg || !sawDir)
            return false;
        const bool toHost = trxdir == 1u;
        const uint64_t buf = toHost ? bitbltbuf : (bitbltbuf >> 32);
        const uint64_t pos = toHost ? trxpos : (trxpos >> 32);
        out.vram_addr = static_cast<uint16_t>(buf & 0x3FFFu);
        out.vram_width = static_cast<uint8_t>((buf >> 16) & 0x3Fu);
        out.psm = static_cast<uint8_t>((buf >> 24) & 0x3Fu);
        out.x = static_cast<uint16_t>(pos & 0x7FFu);
        out.y = static_cast<uint16_t>((pos >> 16) & 0x7FFu);
        out.width = static_cast<uint16_t>(trxreg & 0xFFFu);
        out.height = static_cast<uint16_t>((trxreg >> 32) & 0xFFFu);
        return true;
    }

    bool writeGsDispEnv(uint8_t *rdram, uint32_t addr, uint64_t display, uint64_t dispfb)
    {
        uint8_t *ptr = getMemPtr(rdram, addr);
        if (!ptr)
            return false;
        GsDispEnvMem env{};
        std::memcpy(&env, ptr, sizeof(env));
        env.dispfb = dispfb;
        env.display = display;
        std::memcpy(ptr, &env, sizeof(env));
        return true;
    }

    bool readGsDispEnv(uint8_t *rdram, uint32_t addr, GsDispEnvMem &out)
    {
        const uint8_t *ptr = getConstMemPtr(rdram, addr);
        if (!ptr)
            return false;
        std::memcpy(&out, ptr, sizeof(out));
        return true;
    }

    bool readGsDBuffDc(uint8_t *rdram, uint32_t addr, GsDBuffDcMem &out)
    {
        const uint8_t *ptr = getConstMemPtr(rdram, addr);
        if (!ptr)
            return false;
        std::memcpy(&out, ptr, sizeof(out));
        return true;
    }

    bool readGsDBuff(uint8_t* rdram, uint32_t addr, GsDBuffMem& out)
    {
        const uint8_t* ptr = getConstMemPtr(rdram, addr);
        if (!ptr)
            return false;
        std::memcpy(&out, ptr, sizeof(out));
        return true;
    }

    bool writeGsDBuffDc(uint8_t *rdram, uint32_t addr, const GsDBuffDcMem &db)
    {
        uint8_t *ptr = getMemPtr(rdram, addr);
        if (!ptr)
            return false;
        std::memcpy(ptr, &db, sizeof(db));
        return true;
    }

    bool writeGsDBuff(uint8_t* rdram, uint32_t addr, const GsDBuffMem& db)
    {
        uint8_t* ptr = getMemPtr(rdram, addr);
        if (!ptr)
            return false;
        std::memcpy(ptr, &db, sizeof(db));
        return true;
    }

    bool readGsRegPairs(uint8_t *rdram, uint32_t addr, GsRegPairMem *pairs, size_t pairCount)
    {
        if (!pairs || pairCount == 0u)
            return false;
        const uint8_t *ptr = getConstMemPtr(rdram, addr);
        if (!ptr)
            return false;
        std::memcpy(pairs, ptr, pairCount * sizeof(GsRegPairMem));
        return true;
    }

    void applyGsDispEnv(PS2Runtime *runtime, const GsDispEnvMem &env)
    {
        if (!runtime || !runtime->syncCoreSubsystems())
            return;
        auto &regs = runtime->memory().gs();
        regs.pmode = env.pmode;
        regs.smode2 = env.smode2;
        regs.dispfb1 = env.dispfb;
        regs.display1 = env.display;
        regs.dispfb2 = env.dispfb;
        regs.display2 = env.display;
        regs.bgcolor = env.bgcolor;
    }

    void applyGsRegPairs(PS2Runtime *runtime, const GsRegPairMem *pairs, size_t pairCount)
    {
        if (!runtime || !pairs || !runtime->syncCoreSubsystems())
            return;
        for (size_t i = 0; i < pairCount; ++i)
        {
            runtime->gs().writeRegister(static_cast<uint8_t>(pairs[i].reg & 0xFFu), pairs[i].value);
        }
    }

    void seedGsDrawEnv1(GsDrawEnv1Mem &env,
                               int32_t width,
                               int32_t height,
                               uint32_t fbp,
                               uint32_t fbw,
                               uint32_t psm,
                               uint32_t zbp,
                               uint32_t zpsm,
                               uint32_t ztest,
                               bool dthe)
    {
        env.frame1 = {makeFrame(fbp, fbw, psm, 0u), GS_REG_FRAME_1};
        env.zbuf1 = {makeZbuf(zbp, zpsm, (ztest & 0x3u) == 0u), GS_REG_ZBUF_1};
        env.xyoffset1 = {makeXYOffset(width, height), GS_REG_XYOFFSET_1};
        env.scissor1 = {makeScissor(width, height), GS_REG_SCISSOR_1};
        env.prmodecont = {1u, GS_REG_PRMODECONT};
        env.colclamp = {1u, GS_REG_COLCLAMP};
        env.dthe = {dthe ? 1u : 0u, GS_REG_DTHE};
        env.test1 = {makeTest(ztest), GS_REG_TEST_1};
    }

    void seedGsDrawEnv2(GsDrawEnv2Mem &env,
                               int32_t width,
                               int32_t height,
                               uint32_t fbp,
                               uint32_t fbw,
                               uint32_t psm,
                               uint32_t zbp,
                               uint32_t zpsm,
                               uint32_t ztest,
                               bool dthe)
    {
        env.frame2 = {makeFrame(fbp, fbw, psm, 0u), GS_REG_FRAME_2};
        env.zbuf2 = {makeZbuf(zbp, zpsm, (ztest & 0x3u) == 0u), GS_REG_ZBUF_2};
        env.xyoffset2 = {makeXYOffset(width, height), GS_REG_XYOFFSET_2};
        env.scissor2 = {makeScissor(width, height), GS_REG_SCISSOR_2};
        env.prmodecont = {1u, GS_REG_PRMODECONT};
        env.colclamp = {1u, GS_REG_COLCLAMP};
        env.dthe = {dthe ? 1u : 0u, GS_REG_DTHE};
        env.test2 = {makeTest(ztest), GS_REG_TEST_2};
    }

    uint32_t writeGsGParamToScratch(PS2Runtime *runtime)
    {
        if (!runtime)
            return 0;
        uint8_t *scratch = runtime->memory().getScratchpad();
        if (!scratch)
            return 0;
        std::memcpy(scratch + kGsParamScratchOffset, &g_gparam, sizeof(g_gparam));
        return PS2_SCRATCHPAD_BASE + kGsParamScratchOffset;
    }

}
