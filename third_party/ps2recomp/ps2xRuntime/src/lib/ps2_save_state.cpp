// The save-state container. runtime/ps2_save_state.h says where the byte format came from (the
// MrCoolTheCucumber/PS2Recomp fork, commit 7978365) and what this file does differently. Sprint 11 Task 8c.
#include "runtime/ps2_save_state.h"

#include <algorithm>
#include <bit>
#include <cctype>
#include <chrono>
#include <fstream>
#include <limits>
#include <set>
#include <string>
#include <system_error>
#include <unordered_set>

#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#else
#include <fcntl.h>
#include <unistd.h>
#endif

namespace ps2x::savestate
{
    namespace detail
    {
        std::atomic<uint64_t> g_fileSyncCount{0u};
        std::atomic<bool> g_failNextFileSync{false};
    }

    namespace
    {
        // ---- the format's fixed numbers -------------------------------------------------------------------
        constexpr std::array<uint8_t, 8> kMagic{'P', '2', 'X', 'S', 'T', 'A', 'T', 'E'};
        constexpr uint32_t kFileHeaderSize = 32u;    // magic(8) version(4) headerSize(4) chunks(4) flags(4) total(8)
        constexpr uint32_t kChunkHeaderSize = 32u;   // id(4) version(4) flags(4) reserved(4) size(8) digest(8)
        constexpr uint32_t kDefinedChunkFlags = static_cast<uint32_t>(ChunkFlags::Required);

        // ---- every guard answers through this one line ----------------------------------------------------
        bool fail(std::string *error, std::string_view reason)
        {
            if (error)
                error->assign(reason);
            return false;
        }

        // ---- one little-endian helper, instead of one shift loop per width ---------------------------------
        template <typename Unsigned>
        void appendLittle(std::vector<uint8_t> &out, Unsigned value)
        {
            for (size_t index = 0u; index < sizeof(Unsigned); ++index)
                out.push_back(static_cast<uint8_t>(static_cast<uint64_t>(value) >> (index * 8u)));
        }

        template <typename Unsigned>
        bool takeLittle(std::span<const uint8_t> input, size_t &offset, Unsigned &value) noexcept
        {
            if (input.size() - offset < sizeof(Unsigned))
                return false;
            uint64_t accumulated = 0u;
            for (size_t index = 0u; index < sizeof(Unsigned); ++index)
                accumulated |= static_cast<uint64_t>(input[offset + index]) << (index * 8u);
            offset += sizeof(Unsigned);
            value = static_cast<Unsigned>(accumulated);
            return true;
        }

        // FNV-1a over a chunk's payload: not a cryptographic claim, a torn-write and bit-rot detector.
        uint64_t payloadDigest(std::span<const uint8_t> bytes) noexcept
        {
            constexpr uint64_t kOffsetBasis = 14695981039346656037ull;
            constexpr uint64_t kPrime = 1099511628211ull;
            uint64_t value = kOffsetBasis;
            for (const uint8_t byte : bytes)
                value = (value ^ byte) * kPrime;
            return value;
        }

        bool addWithoutOverflow(uint64_t &total, uint64_t amount) noexcept
        {
            if (amount > std::numeric_limits<uint64_t>::max() - total)
                return false;
            total += amount;
            return true;
        }

        // ---- the two headers, as things with names ---------------------------------------------------------
        struct FileHeader
        {
            uint32_t containerVersion = kContainerVersion;
            uint32_t headerSize = kFileHeaderSize;
            uint32_t chunkCount = 0u;
            uint32_t flags = 0u;   // none defined yet
            uint64_t totalSize = 0u;
        };

        struct ChunkHeader
        {
            uint32_t id = 0u;
            uint32_t version = 0u;
            uint32_t flags = 0u;
            uint32_t reserved = 0u;   // must be zero: the format's room to grow
            uint64_t payloadSize = 0u;
            uint64_t digest = 0u;
        };

        void putFileHeader(Writer &writer, const FileHeader &header)
        {
            writer.bytes(kMagic);
            writer.u32(header.containerVersion);
            writer.u32(header.headerSize);
            writer.u32(header.chunkCount);
            writer.u32(header.flags);
            writer.u64(header.totalSize);
        }

        bool getFileHeader(Reader &reader, FileHeader &header) noexcept
        {
            std::span<const uint8_t> magic;
            return reader.bytes(kMagic.size(), magic) &&
                   std::equal(magic.begin(), magic.end(), kMagic.begin(), kMagic.end()) &&
                   reader.u32(header.containerVersion) && reader.u32(header.headerSize) &&
                   reader.u32(header.chunkCount) && reader.u32(header.flags) && reader.u64(header.totalSize);
        }

        void putChunkHeader(Writer &writer, const ChunkHeader &header)
        {
            writer.u32(header.id);
            writer.u32(header.version);
            writer.u32(header.flags);
            writer.u32(header.reserved);
            writer.u64(header.payloadSize);
            writer.u64(header.digest);
        }

        bool getChunkHeader(Reader &reader, ChunkHeader &header) noexcept
        {
            return reader.u32(header.id) && reader.u32(header.version) && reader.u32(header.flags) &&
                   reader.u32(header.reserved) && reader.u64(header.payloadSize) && reader.u64(header.digest);
        }

        // ---- the publish -----------------------------------------------------------------------------------

        // A name no other publish of this path can pick: the clock, this process, and a counter for two
        // publishes inside one tick.
        std::filesystem::path temporaryPathFor(const std::filesystem::path &path)
        {
            static std::atomic<uint64_t> sequence{0u};
            const uint64_t tick =
                static_cast<uint64_t>(std::chrono::steady_clock::now().time_since_epoch().count());
            std::filesystem::path temporary = path;
            temporary += ".tmp-" + std::to_string(tick) + "-" +
                         std::to_string(static_cast<uint64_t>(
#ifdef _WIN32
                             ::GetCurrentProcessId()
#else
                             ::getpid()
#endif
                             )) +
                         "-" + std::to_string(sequence.fetch_add(1u, std::memory_order_relaxed));
            return temporary;
        }

        // The one thing that makes the publish survive a power cut: the bytes are on the disk before the rename
        // is asked for. `directory` flushes the containing directory instead, so the new name itself is durable;
        // Windows has no such call and does not need one.
        bool syncToDisk(const std::filesystem::path &path, bool directory) noexcept
        {
#ifdef _WIN32
            if (directory)
                return true;
            const HANDLE handle =
                ::CreateFileW(path.c_str(), GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr,
                              OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
            if (handle == INVALID_HANDLE_VALUE)
                return false;
            const BOOL flushed = ::FlushFileBuffers(handle);
            ::CloseHandle(handle);
            return flushed != FALSE;
#else
            const int descriptor = ::open(path.c_str(), directory ? O_RDONLY : O_WRONLY);
            if (descriptor < 0)
                return directory;   // a platform that will not open a directory is not a failure
            const int result = ::fsync(descriptor);
            ::close(descriptor);
            return result == 0 || directory;
#endif
        }

        // The seam the suite counts and faults. Everything else calls this, never syncToDisk.
        bool syncPublished(const std::filesystem::path &path, bool directory) noexcept
        {
            if (!directory)
            {
                detail::g_fileSyncCount.fetch_add(1u, std::memory_order_relaxed);
                if (detail::g_failNextFileSync.exchange(false, std::memory_order_relaxed))
                    return false;
            }
            return syncToDisk(path, directory);
        }

        void removeQuietly(const std::filesystem::path &path) noexcept
        {
            std::error_code ignored;
            std::filesystem::remove(path, ignored);
        }
    }

    std::string chunkIdString(uint32_t id)
    {
        std::string result(4u, ' ');
        for (uint32_t index = 0u; index < 4u; ++index)
        {
            const uint8_t value = static_cast<uint8_t>(id >> (index * 8u));
            result[index] = value >= 0x20u && value <= 0x7eu ? static_cast<char>(value) : '?';
        }
        return result;
    }

    // ---- Writer ------------------------------------------------------------------------------------------

    void Writer::u8(uint8_t value)
    {
        m_data.push_back(value);
    }

    void Writer::boolean(bool value)
    {
        u8(value ? 1u : 0u);
    }

    void Writer::u16(uint16_t value)
    {
        appendLittle(m_data, value);
    }

    void Writer::u32(uint32_t value)
    {
        appendLittle(m_data, value);
    }

    void Writer::u64(uint64_t value)
    {
        appendLittle(m_data, value);
    }

    // The signed and floating widths are their unsigned twin's bits: one conversion, no second encoder.
    void Writer::i32(int32_t value)
    {
        u32(std::bit_cast<uint32_t>(value));
    }

    void Writer::i64(int64_t value)
    {
        u64(std::bit_cast<uint64_t>(value));
    }

    void Writer::f32(float value)
    {
        u32(std::bit_cast<uint32_t>(value));
    }

    void Writer::f64(double value)
    {
        u64(std::bit_cast<uint64_t>(value));
    }

    void Writer::bytes(std::span<const uint8_t> value)
    {
        m_data.insert(m_data.end(), value.begin(), value.end());
    }

    void Writer::sizedBytes(std::span<const uint8_t> value)
    {
        u64(value.size());
        bytes(value);
    }

    void Writer::string(std::string_view value)
    {
        sizedBytes(std::span<const uint8_t>(reinterpret_cast<const uint8_t *>(value.data()), value.size()));
    }

    const std::vector<uint8_t> &Writer::data() const noexcept
    {
        return m_data;
    }

    std::vector<uint8_t> Writer::take()
    {
        return std::move(m_data);
    }

    // ---- Reader ------------------------------------------------------------------------------------------

    Reader::Reader(std::span<const uint8_t> input) noexcept
        : m_input(input)
    {
    }

    bool Reader::u8(uint8_t &value) noexcept
    {
        return takeLittle(m_input, m_offset, value);
    }

    bool Reader::u16(uint16_t &value) noexcept
    {
        return takeLittle(m_input, m_offset, value);
    }

    bool Reader::u32(uint32_t &value) noexcept
    {
        return takeLittle(m_input, m_offset, value);
    }

    bool Reader::u64(uint64_t &value) noexcept
    {
        return takeLittle(m_input, m_offset, value);
    }

    // A boolean is one byte and only ever 0 or 1: anything else is a file we do not understand.
    bool Reader::boolean(bool &value) noexcept
    {
        uint8_t encoded = 0u;
        if (!u8(encoded) || encoded > 1u)
            return false;
        value = encoded != 0u;
        return true;
    }

    bool Reader::i32(int32_t &value) noexcept
    {
        uint32_t encoded = 0u;
        if (!u32(encoded))
            return false;
        value = std::bit_cast<int32_t>(encoded);
        return true;
    }

    bool Reader::i64(int64_t &value) noexcept
    {
        uint64_t encoded = 0u;
        if (!u64(encoded))
            return false;
        value = std::bit_cast<int64_t>(encoded);
        return true;
    }

    bool Reader::f32(float &value) noexcept
    {
        uint32_t encoded = 0u;
        if (!u32(encoded))
            return false;
        value = std::bit_cast<float>(encoded);
        return true;
    }

    bool Reader::f64(double &value) noexcept
    {
        uint64_t encoded = 0u;
        if (!u64(encoded))
            return false;
        value = std::bit_cast<double>(encoded);
        return true;
    }

    bool Reader::bytes(size_t size, std::span<const uint8_t> &value) noexcept
    {
        if (size > remaining())
            return false;
        value = m_input.subspan(m_offset, size);
        m_offset += size;
        return true;
    }

    // Two bounds, both of them: what the caller will accept, and what the input actually holds. The second is
    // what stops a length prefix out of a corrupt file from naming half a gigabyte.
    bool Reader::sizedBytes(std::span<const uint8_t> &value, uint64_t maximumSize) noexcept
    {
        uint64_t size = 0u;
        if (!u64(size) || size > maximumSize || size > remaining())
            return false;
        return bytes(static_cast<size_t>(size), value);
    }

    bool Reader::string(std::string &value, uint64_t maximumSize)
    {
        std::span<const uint8_t> encoded;
        if (!sizedBytes(encoded, maximumSize))
            return false;
        value.assign(reinterpret_cast<const char *>(encoded.data()), encoded.size());
        return true;
    }

    size_t Reader::offset() const noexcept
    {
        return m_offset;
    }

    size_t Reader::remaining() const noexcept
    {
        return m_input.size() - m_offset;
    }

    bool Reader::atEnd() const noexcept
    {
        return m_offset == m_input.size();
    }

    // ---- Document ----------------------------------------------------------------------------------------

    const Chunk *Document::find(uint32_t id) const noexcept
    {
        const auto it = std::find_if(chunks.begin(), chunks.end(),
                                     [id](const Chunk &chunk) { return chunk.id == id; });
        return it == chunks.end() ? nullptr : &*it;
    }

    Chunk *Document::find(uint32_t id) noexcept
    {
        const auto it = std::find_if(chunks.begin(), chunks.end(),
                                     [id](const Chunk &chunk) { return chunk.id == id; });
        return it == chunks.end() ? nullptr : &*it;
    }

    // ---- encode / decode ---------------------------------------------------------------------------------

    bool encode(const Document &document, std::vector<uint8_t> &output, std::string *error)
    {
        if (document.chunks.size() > kMaximumChunkCount)
            return fail(error, "save state has too many chunks");

        // Everything the file will be is checked before a single byte is written.
        uint64_t totalSize = kFileHeaderSize;
        std::unordered_set<uint32_t> seen;
        for (const Chunk &chunk : document.chunks)
        {
            if (!seen.insert(chunk.id).second)
                return fail(error, "save state contains a duplicate chunk");
            if ((static_cast<uint32_t>(chunk.flags) & ~kDefinedChunkFlags) != 0u)
                return fail(error, "save state chunk uses unknown flags");
            if (!addWithoutOverflow(totalSize, kChunkHeaderSize) ||
                !addWithoutOverflow(totalSize, chunk.payload.size()) || totalSize > kMaximumFileSize)
                return fail(error, "save state exceeds the maximum file size");
        }

        Writer writer;
        putFileHeader(writer, FileHeader{kContainerVersion, kFileHeaderSize,
                                         static_cast<uint32_t>(document.chunks.size()), 0u, totalSize});
        for (const Chunk &chunk : document.chunks)
        {
            putChunkHeader(writer, ChunkHeader{chunk.id, chunk.version, static_cast<uint32_t>(chunk.flags), 0u,
                                               chunk.payload.size(), payloadDigest(chunk.payload)});
            writer.bytes(chunk.payload);
        }
        output = writer.take();
        return true;
    }

    bool decode(std::span<const uint8_t> input, Document &document, std::string *error)
    {
        if (input.size() < kFileHeaderSize)
            return fail(error, "save state header is truncated");
        if (input.size() > kMaximumFileSize)
            return fail(error, "save state exceeds the maximum file size");

        Reader reader(input);
        FileHeader header;
        if (!getFileHeader(reader, header))
            return fail(error, "save state header is invalid");
        if (header.containerVersion != kContainerVersion)
            return fail(error, "unsupported save state container version");
        // totalSize is the header's own claim about the file; a truncated or padded file disagrees with it.
        if (header.headerSize != kFileHeaderSize || header.flags != 0u || header.totalSize != input.size())
            return fail(error, "save state header fields are inconsistent");
        // Bounded here, before the reserve below: a header claiming four billion chunks must cost nothing.
        if (header.chunkCount > kMaximumChunkCount)
            return fail(error, "save state has too many chunks");

        Document decoded;
        decoded.chunks.reserve(header.chunkCount);
        std::unordered_set<uint32_t> seen;
        for (uint32_t index = 0u; index < header.chunkCount; ++index)
        {
            ChunkHeader chunkHeader;
            if (!getChunkHeader(reader, chunkHeader))
                return fail(error, "save state chunk header is truncated");
            if (chunkHeader.reserved != 0u || (chunkHeader.flags & ~kDefinedChunkFlags) != 0u)
                return fail(error, "save state chunk header is invalid");
            if (!seen.insert(chunkHeader.id).second)
                return fail(error, "save state contains a duplicate chunk");

            std::span<const uint8_t> payload;
            if (chunkHeader.payloadSize > kMaximumFileSize ||
                !reader.bytes(static_cast<size_t>(chunkHeader.payloadSize), payload))
                return fail(error, "save state chunk payload is truncated");
            if (payloadDigest(payload) != chunkHeader.digest)
                return fail(error, "save state chunk checksum mismatch");

            decoded.chunks.push_back(Chunk{
                .id = chunkHeader.id,
                .version = chunkHeader.version,
                .flags = static_cast<ChunkFlags>(chunkHeader.flags),
                .payload = std::vector<uint8_t>(payload.begin(), payload.end()),
            });
        }

        if (!reader.atEnd())
            return fail(error, "save state contains trailing bytes");
        document = std::move(decoded);   // the caller's document is replaced only once everything held
        return true;
    }

    // ---- the files ---------------------------------------------------------------------------------------

    bool writeFileAtomically(const std::filesystem::path &path, const Document &document, std::string *error)
    {
        if (path.empty())
            return fail(error, "save state path is empty");

        // Encode first: a document that cannot be encoded never touches the filesystem at all.
        std::vector<uint8_t> encoded;
        if (!encode(document, encoded, error))
            return false;

        const std::filesystem::path temporary = temporaryPathFor(path);
        {
            std::ofstream stream(temporary, std::ios::binary | std::ios::trunc);
            if (!stream)
                return fail(error, "could not create temporary save state file");
            stream.write(reinterpret_cast<const char *>(encoded.data()),
                         static_cast<std::streamsize>(encoded.size()));
            stream.flush();
            if (!stream)
            {
                stream.close();
                removeQuietly(temporary);
                return fail(error, "could not write temporary save state file");
            }
        }

        // The stream's flush only reached the operating system. This reaches the disk.
        if (!syncPublished(temporary, false))
        {
            removeQuietly(temporary);
            return fail(error, "could not flush the temporary save state file to the disk");
        }

        std::error_code renameError;
        std::filesystem::rename(temporary, path, renameError);
        if (renameError)
        {
            removeQuietly(temporary);
            return fail(error, "could not publish save state file: " + renameError.message());
        }

        // And this makes the new name itself durable, where the platform has such a call.
        (void)syncPublished(path.parent_path().empty() ? std::filesystem::path(".") : path.parent_path(), true);
        return true;
    }

    bool readFile(const std::filesystem::path &path, Document &document, std::string *error)
    {
        std::ifstream stream(path, std::ios::binary | std::ios::ate);
        if (!stream)
            return fail(error, "could not open save state file");

        const std::streamoff end = stream.tellg();
        if (end < 0 || static_cast<uint64_t>(end) > kMaximumFileSize)
            return fail(error, "save state file size is invalid");

        std::vector<uint8_t> encoded(static_cast<size_t>(end));
        stream.seekg(0, std::ios::beg);
        if (!encoded.empty())
            stream.read(reinterpret_cast<char *>(encoded.data()), static_cast<std::streamsize>(encoded.size()));
        if (!stream)
            return fail(error, "could not read save state file");
        return decode(encoded, document, error);
    }

    // ---- the simulated memory card chunk -----------------------------------------------------------------

    namespace
    {
        struct CardEntry
        {
            std::string relativePath;   // always '/'-separated, never empty, never absolute
            bool directory = false;
        };

        // A path out of a state file is untrusted. Only plain, forward-slash-separated, relative names with no
        // empty, '.' or '..' component, no drive letter, and no Windows device name are allowed to become a
        // host path -- `cardDirectory / "NUL"` opens the null device, and a write that silently goes nowhere is
        // not a clean refusal.
        bool reservedOnWindows(std::string_view component)
        {
            static const std::set<std::string> kDeviceNames{"aux",  "com1", "com2", "com3", "com4", "com5",
                                                            "com6", "com7", "com8", "com9", "con",  "lpt1",
                                                            "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7",
                                                            "lpt8", "lpt9", "nul",  "prn"};
            const size_t dot = component.find('.');
            std::string stem(dot == std::string_view::npos ? component : component.substr(0u, dot));
            std::transform(stem.begin(), stem.end(), stem.begin(),
                           [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
            return kDeviceNames.count(stem) != 0u;
        }

        bool safeRelativePath(std::string_view value)
        {
            if (value.empty() || value.size() > kMemoryCardMaximumPathLength)
                return false;
            if (value.front() == '/' || value.back() == '/')
                return false;
            if (value.find('\\') != std::string_view::npos || value.find(':') != std::string_view::npos)
                return false;
            size_t start = 0u;
            for (;;)
            {
                const size_t slash = value.find('/', start);
                const std::string_view component =
                    value.substr(start, slash == std::string_view::npos ? std::string_view::npos : slash - start);
                if (component.empty() || component == "." || component == "..")
                    return false;
                if (component.back() == '.' || component.back() == ' ')
                    return false;   // Windows silently trims these, so two names would become one
                if (reservedOnWindows(component))
                    return false;
                if (slash == std::string_view::npos)
                    return true;
                start = slash + 1u;
            }
        }

        bool readWholeFile(const std::filesystem::path &path, std::vector<uint8_t> &out, std::string *error)
        {
            std::ifstream stream(path, std::ios::binary | std::ios::ate);
            if (!stream)
                return fail(error, "could not open memory card file " + path.generic_string());
            const std::streamoff end = stream.tellg();
            if (end < 0 || static_cast<uint64_t>(end) > kMemoryCardMaximumFileSize)
                return fail(error, "memory card file is too large: " + path.generic_string());
            out.assign(static_cast<size_t>(end), 0u);
            stream.seekg(0, std::ios::beg);
            if (!out.empty())
                stream.read(reinterpret_cast<char *>(out.data()), static_cast<std::streamsize>(out.size()));
            if (!stream)
                return fail(error, "could not read memory card file " + path.generic_string());
            return true;
        }

        // Every entry under `root`, relative and '/'-separated, without ever throwing: the iterator is advanced
        // by hand so a directory that loses permission mid-walk is an error_code, not an exception out of a
        // function whose contract is a bool.
        bool walkFolder(const std::filesystem::path &root, std::vector<CardEntry> &entries, std::string *error)
        {
            std::error_code ec;
            std::filesystem::recursive_directory_iterator it(root, std::filesystem::directory_options::none, ec);
            if (ec)
                return fail(error, "could not walk the memory card folder: " + ec.message());
            const std::filesystem::recursive_directory_iterator end;
            while (it != end)
            {
                const std::filesystem::path current = it->path();
                const bool link = it->is_symlink(ec);
                if (ec)
                    return fail(error, "could not read " + current.generic_string() + ": " + ec.message());
                if (link)
                    return fail(error, "memory card folder contains a link: " + current.generic_string());

                const bool directory = it->is_directory(ec);
                if (ec)
                    return fail(error, "could not read " + current.generic_string() + ": " + ec.message());
                const bool regular = it->is_regular_file(ec);
                if (ec)
                    return fail(error, "could not read " + current.generic_string() + ": " + ec.message());
                if (!directory && !regular)
                    return fail(error, "memory card folder contains a special file: " + current.generic_string());

                const std::string relative = current.lexically_relative(root).generic_string();
                if (!safeRelativePath(relative))
                    return fail(error, "memory card entry has an unusable name: " + relative);
                entries.push_back(CardEntry{relative, directory});
                if (entries.size() > kMemoryCardMaximumEntries)
                    return fail(error, "memory card folder has too many entries");

                it.increment(ec);
                if (ec)
                    return fail(error, "could not walk the memory card folder: " + ec.message());
            }
            return true;
        }

        // A directory we may remove from: something that is a directory already, or nothing yet -- never a file,
        // never a filesystem root, never empty. This is the whole of the "never delete outside the target" rule.
        bool usableCardRoot(const std::filesystem::path &cardDirectory, std::string *error)
        {
            if (cardDirectory.empty())
                return fail(error, "memory card folder path is empty");
            const std::filesystem::path normal = cardDirectory.lexically_normal();
            if (normal.parent_path() == normal || !normal.has_relative_path())
                return fail(error, "memory card folder may not be a filesystem root");

            std::error_code ec;
            const std::filesystem::file_status status = std::filesystem::status(cardDirectory, ec);
            if (ec && status.type() != std::filesystem::file_type::not_found)
                return fail(error, "could not inspect the memory card folder: " + ec.message());
            if (status.type() != std::filesystem::file_type::not_found &&
                status.type() != std::filesystem::file_type::directory)
                return fail(error, "the memory card path is not a directory");
            return true;
        }

        // Removes what the chunk did not name, deepest entry first, and never anything a named entry lives
        // under. Only reached once the whole chunk has decoded and every named entry is on the disk.
        bool removeUnnamed(const std::filesystem::path &root, const std::set<std::string> &named,
                           std::string *error)
        {
            std::vector<CardEntry> present;
            if (!walkFolder(root, present, error))
                return false;

            std::vector<std::string> doomed;
            for (const CardEntry &entry : present)
            {
                if (named.count(entry.relativePath) != 0u)
                    continue;
                // A directory the chunk did not name may still be the parent of one it did.
                const std::string prefix = entry.relativePath + "/";
                const auto below = named.lower_bound(prefix);
                if (below != named.end() && below->compare(0u, prefix.size(), prefix) == 0)
                    continue;
                doomed.push_back(entry.relativePath);
            }
            // Deepest first, so a directory is empty by the time its own turn comes.
            std::sort(doomed.begin(), doomed.end(),
                      [](const std::string &a, const std::string &b) { return a.size() > b.size(); });
            for (const std::string &relative : doomed)
            {
                std::error_code ec;
                std::filesystem::remove(root / relative, ec);
                if (ec)
                    return fail(error, "could not remove " + relative + ": " + ec.message());
            }
            return true;
        }
    }

    bool packMemoryCard(const std::filesystem::path &cardDirectory, Chunk &chunk, std::string *error)
    {
        std::error_code ec;
        if (!std::filesystem::is_directory(cardDirectory, ec) || ec)
            return fail(error, "memory card folder does not exist");

        std::vector<CardEntry> entries;
        if (!walkFolder(cardDirectory, entries, error))
            return false;

        // Sorted, so the same folder always packs to the same bytes whatever order the host walked it in -- and
        // so a parent directory is always written before anything inside it.
        std::sort(entries.begin(), entries.end(),
                  [](const CardEntry &a, const CardEntry &b) { return a.relativePath < b.relativePath; });

        Writer writer;
        writer.u32(static_cast<uint32_t>(entries.size()));
        for (const CardEntry &entry : entries)
        {
            writer.string(entry.relativePath);
            writer.u8(entry.directory ? 0u : 1u);
            if (entry.directory)
                continue;
            std::vector<uint8_t> contents;
            if (!readWholeFile(cardDirectory / entry.relativePath, contents, error))
                return false;
            writer.sizedBytes(contents);
        }

        chunk.id = kMemoryCardChunkId;
        chunk.version = kMemoryCardChunkVersion;
        chunk.flags = ChunkFlags::Required;
        chunk.payload = writer.take();
        return true;
    }

    bool unpackMemoryCard(const Chunk &chunk, const std::filesystem::path &cardDirectory, std::string *error)
    {
        if (chunk.id != kMemoryCardChunkId)
            return fail(error, "chunk " + chunkIdString(chunk.id) + " is not the memory card chunk");
        if (chunk.version != kMemoryCardChunkVersion)
            return fail(error, "unsupported memory card chunk version");
        if (!usableCardRoot(cardDirectory, error))
            return false;

        Reader reader(chunk.payload);
        uint32_t entryCount = 0u;
        if (!reader.u32(entryCount) || entryCount > kMemoryCardMaximumEntries)
            return fail(error, "memory card chunk entry count is invalid");

        // Decode the whole chunk before touching the filesystem: a chunk that turns out to be truncated must not
        // have left half a card on disk, and must not have removed anything either.
        std::vector<CardEntry> entries;
        std::vector<std::vector<uint8_t>> contents;
        entries.reserve(entryCount);
        contents.reserve(entryCount);
        for (uint32_t index = 0u; index < entryCount; ++index)
        {
            std::string relative;
            uint8_t kind = 0u;
            if (!reader.string(relative, kMemoryCardMaximumPathLength) || !reader.u8(kind) || kind > 1u)
                return fail(error, "memory card chunk entry is truncated");
            if (!safeRelativePath(relative))
                return fail(error, "memory card chunk names an unusable path: " + relative);
            std::vector<uint8_t> payload;
            if (kind == 1u)
            {
                std::span<const uint8_t> bytes;
                if (!reader.sizedBytes(bytes, kMemoryCardMaximumFileSize))
                    return fail(error, "memory card chunk file contents are truncated");
                payload.assign(bytes.begin(), bytes.end());
            }
            entries.push_back(CardEntry{relative, kind == 0u});
            contents.push_back(std::move(payload));
        }
        if (!reader.atEnd())
            return fail(error, "memory card chunk has trailing bytes");

        std::error_code ec;
        std::filesystem::create_directories(cardDirectory, ec);
        if (!std::filesystem::is_directory(cardDirectory, ec))
            return fail(error, "could not create the memory card folder");

        std::set<std::string> named;
        for (size_t index = 0u; index < entries.size(); ++index)
        {
            const std::filesystem::path target = cardDirectory / entries[index].relativePath;
            named.insert(entries[index].relativePath);
            if (entries[index].directory)
            {
                std::filesystem::create_directories(target, ec);
                if (!std::filesystem::is_directory(target, ec))
                    return fail(error, "could not create " + target.generic_string());
                continue;
            }
            std::filesystem::create_directories(target.parent_path(), ec);
            std::ofstream stream(target, std::ios::binary | std::ios::trunc);
            if (!stream)
                return fail(error, "could not create " + target.generic_string());
            if (!contents[index].empty())
                stream.write(reinterpret_cast<const char *>(contents[index].data()),
                             static_cast<std::streamsize>(contents[index].size()));
            stream.flush();
            if (!stream)
                return fail(error, "could not write " + target.generic_string());
        }

        // A restore is the chunk exactly: whatever the card has gained since goes.
        return removeUnnamed(cardDirectory, named, error);
    }
}
