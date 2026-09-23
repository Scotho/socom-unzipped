// The save-state container. See runtime/ps2_save_state.h for what was taken from the
// MrCoolTheCucumber/PS2Recomp fork (commit 7978365) and what was left there. Sprint 11 Task 8c.
#include "runtime/ps2_save_state.h"

#include <algorithm>
#include <bit>
#include <chrono>
#include <fstream>
#include <limits>
#include <system_error>
#include <unordered_set>

namespace ps2x::savestate
{
    namespace
    {
        constexpr std::array<uint8_t, 8> kMagic{'P', '2', 'X', 'S', 'T', 'A', 'T', 'E'};
        constexpr uint32_t kHeaderSize = 32u;         // magic(8) version(4) headerSize(4) chunks(4) flags(4) total(8)
        constexpr uint32_t kChunkHeaderSize = 32u;    // id(4) version(4) flags(4) reserved(4) size(8) checksum(8)
        constexpr uint64_t kFnvOffset = 14695981039346656037ull;
        constexpr uint64_t kFnvPrime = 1099511628211ull;
        constexpr uint32_t kKnownChunkFlags = static_cast<uint32_t>(ChunkFlags::Required);

        void setError(std::string *error, std::string_view message)
        {
            if (error)
                *error = message;
        }

        // FNV-1a over the payload: not a cryptographic claim, a torn-write and bit-rot detector.
        uint64_t checksum(std::span<const uint8_t> bytes) noexcept
        {
            uint64_t value = kFnvOffset;
            for (const uint8_t byte : bytes)
            {
                value ^= byte;
                value *= kFnvPrime;
            }
            return value;
        }

        bool checkedAdd(uint64_t &total, uint64_t amount) noexcept
        {
            if (amount > std::numeric_limits<uint64_t>::max() - total)
                return false;
            total += amount;
            return true;
        }

        std::filesystem::path temporaryPathFor(const std::filesystem::path &path)
        {
            const uint64_t nonce =
                static_cast<uint64_t>(std::chrono::steady_clock::now().time_since_epoch().count());
            std::filesystem::path temporary = path;
            temporary += ".tmp-" + std::to_string(nonce);
            return temporary;
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
        u8(static_cast<uint8_t>(value));
        u8(static_cast<uint8_t>(value >> 8u));
    }

    void Writer::u32(uint32_t value)
    {
        for (uint32_t shift = 0u; shift < 32u; shift += 8u)
            u8(static_cast<uint8_t>(value >> shift));
    }

    void Writer::i32(int32_t value)
    {
        u32(std::bit_cast<uint32_t>(value));
    }

    void Writer::u64(uint64_t value)
    {
        for (uint32_t shift = 0u; shift < 64u; shift += 8u)
            u8(static_cast<uint8_t>(value >> shift));
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

    Reader::Reader(std::span<const uint8_t> input) noexcept
        : m_input(input)
    {
    }

    bool Reader::u8(uint8_t &value) noexcept
    {
        if (m_offset == m_input.size())
            return false;
        value = m_input[m_offset++];
        return true;
    }

    bool Reader::boolean(bool &value) noexcept
    {
        uint8_t encoded = 0u;
        if (!u8(encoded) || encoded > 1u)
            return false;
        value = encoded != 0u;
        return true;
    }

    bool Reader::u16(uint16_t &value) noexcept
    {
        uint8_t low = 0u;
        uint8_t high = 0u;
        if (!u8(low) || !u8(high))
            return false;
        value = static_cast<uint16_t>(static_cast<uint16_t>(low) | (static_cast<uint16_t>(high) << 8u));
        return true;
    }

    bool Reader::u32(uint32_t &value) noexcept
    {
        value = 0u;
        for (uint32_t shift = 0u; shift < 32u; shift += 8u)
        {
            uint8_t byte = 0u;
            if (!u8(byte))
                return false;
            value |= static_cast<uint32_t>(byte) << shift;
        }
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

    bool Reader::u64(uint64_t &value) noexcept
    {
        value = 0u;
        for (uint32_t shift = 0u; shift < 64u; shift += 8u)
        {
            uint8_t byte = 0u;
            if (!u8(byte))
                return false;
            value |= static_cast<uint64_t>(byte) << shift;
        }
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

    bool encode(const Document &document, std::vector<uint8_t> &output, std::string *error)
    {
        if (document.chunks.size() > kMaximumChunkCount)
        {
            setError(error, "save state has too many chunks");
            return false;
        }

        uint64_t totalSize = kHeaderSize;
        std::unordered_set<uint32_t> ids;
        for (const Chunk &chunk : document.chunks)
        {
            if (!ids.insert(chunk.id).second)
            {
                setError(error, "save state contains a duplicate chunk");
                return false;
            }
            if ((static_cast<uint32_t>(chunk.flags) & ~kKnownChunkFlags) != 0u)
            {
                setError(error, "save state chunk uses unknown flags");
                return false;
            }
            if (!checkedAdd(totalSize, kChunkHeaderSize) || !checkedAdd(totalSize, chunk.payload.size()) ||
                totalSize > kMaximumFileSize)
            {
                setError(error, "save state exceeds the maximum file size");
                return false;
            }
        }

        Writer writer;
        writer.bytes(kMagic);
        writer.u32(kContainerVersion);
        writer.u32(kHeaderSize);
        writer.u32(static_cast<uint32_t>(document.chunks.size()));
        writer.u32(0u);   // file flags, none defined yet
        writer.u64(totalSize);

        for (const Chunk &chunk : document.chunks)
        {
            writer.u32(chunk.id);
            writer.u32(chunk.version);
            writer.u32(static_cast<uint32_t>(chunk.flags));
            writer.u32(0u);   // reserved
            writer.u64(chunk.payload.size());
            writer.u64(checksum(chunk.payload));
            writer.bytes(chunk.payload);
        }

        output = writer.take();
        return true;
    }

    bool decode(std::span<const uint8_t> input, Document &document, std::string *error)
    {
        if (input.size() < kHeaderSize)
        {
            setError(error, "save state header is truncated");
            return false;
        }
        if (input.size() > kMaximumFileSize)
        {
            setError(error, "save state exceeds the maximum file size");
            return false;
        }

        Reader reader(input);
        std::span<const uint8_t> magic;
        uint32_t containerVersion = 0u;
        uint32_t headerSize = 0u;
        uint32_t chunkCount = 0u;
        uint32_t flags = 0u;
        uint64_t totalSize = 0u;
        if (!reader.bytes(kMagic.size(), magic) || !std::equal(magic.begin(), magic.end(), kMagic.begin()) ||
            !reader.u32(containerVersion) || !reader.u32(headerSize) || !reader.u32(chunkCount) ||
            !reader.u32(flags) || !reader.u64(totalSize))
        {
            setError(error, "save state header is invalid");
            return false;
        }
        if (containerVersion != kContainerVersion)
        {
            setError(error, "unsupported save state container version");
            return false;
        }
        // totalSize is the header's own claim about the file; a truncated or padded file disagrees with it.
        if (headerSize != kHeaderSize || flags != 0u || totalSize != input.size())
        {
            setError(error, "save state header fields are inconsistent");
            return false;
        }
        if (chunkCount > kMaximumChunkCount)
        {
            setError(error, "save state has too many chunks");
            return false;
        }

        Document decoded;
        decoded.chunks.reserve(chunkCount);
        std::unordered_set<uint32_t> ids;
        for (uint32_t index = 0u; index < chunkCount; ++index)
        {
            uint32_t id = 0u;
            uint32_t version = 0u;
            uint32_t encodedFlags = 0u;
            uint32_t reserved = 0u;
            uint64_t payloadSize = 0u;
            uint64_t encodedChecksum = 0u;
            if (!reader.u32(id) || !reader.u32(version) || !reader.u32(encodedFlags) || !reader.u32(reserved) ||
                !reader.u64(payloadSize) || !reader.u64(encodedChecksum))
            {
                setError(error, "save state chunk header is truncated");
                return false;
            }
            if (reserved != 0u || (encodedFlags & ~kKnownChunkFlags) != 0u)
            {
                setError(error, "save state chunk header is invalid");
                return false;
            }
            if (!ids.insert(id).second)
            {
                setError(error, "save state contains a duplicate chunk");
                return false;
            }

            std::span<const uint8_t> payload;
            if (payloadSize > kMaximumFileSize || !reader.bytes(static_cast<size_t>(payloadSize), payload))
            {
                setError(error, "save state chunk payload is truncated");
                return false;
            }
            if (checksum(payload) != encodedChecksum)
            {
                setError(error, "save state chunk checksum mismatch");
                return false;
            }

            decoded.chunks.push_back(Chunk{
                .id = id,
                .version = version,
                .flags = static_cast<ChunkFlags>(encodedFlags),
                .payload = std::vector<uint8_t>(payload.begin(), payload.end()),
            });
        }

        if (!reader.atEnd())
        {
            setError(error, "save state contains trailing bytes");
            return false;
        }
        document = std::move(decoded);
        return true;
    }

    bool writeFileAtomically(const std::filesystem::path &path, const Document &document, std::string *error)
    {
        if (path.empty())
        {
            setError(error, "save state path is empty");
            return false;
        }

        // Encode first: a document that cannot be encoded never touches the filesystem at all.
        std::vector<uint8_t> encoded;
        if (!encode(document, encoded, error))
            return false;

        const std::filesystem::path temporary = temporaryPathFor(path);
        {
            std::ofstream stream(temporary, std::ios::binary | std::ios::trunc);
            if (!stream)
            {
                setError(error, "could not create temporary save state file");
                return false;
            }
            stream.write(reinterpret_cast<const char *>(encoded.data()),
                         static_cast<std::streamsize>(encoded.size()));
            stream.flush();
            if (!stream)
            {
                stream.close();
                std::error_code ignored;
                std::filesystem::remove(temporary, ignored);
                setError(error, "could not write temporary save state file");
                return false;
            }
        }

        std::error_code renameError;
        std::filesystem::rename(temporary, path, renameError);
        if (renameError)
        {
            std::error_code ignored;
            std::filesystem::remove(temporary, ignored);
            setError(error, "could not publish save state file: " + renameError.message());
            return false;
        }
        return true;
    }

    bool readFile(const std::filesystem::path &path, Document &document, std::string *error)
    {
        std::ifstream stream(path, std::ios::binary | std::ios::ate);
        if (!stream)
        {
            setError(error, "could not open save state file");
            return false;
        }

        const std::streampos end = stream.tellg();
        if (end < 0 || static_cast<uint64_t>(end) > kMaximumFileSize)
        {
            setError(error, "save state file size is invalid");
            return false;
        }

        std::vector<uint8_t> encoded(static_cast<size_t>(end));
        stream.seekg(0, std::ios::beg);
        if (!encoded.empty())
        {
            stream.read(reinterpret_cast<char *>(encoded.data()), static_cast<std::streamsize>(encoded.size()));
        }
        if (!stream)
        {
            setError(error, "could not read save state file");
            return false;
        }
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

        // The generic form of a relative path: what the container stores, whatever the host's separator is.
        std::string genericRelative(const std::filesystem::path &root, const std::filesystem::path &entry)
        {
            return entry.lexically_relative(root).generic_string();
        }

        // A path out of a state file is untrusted. Only plain, forward-slash-separated, relative names with no
        // empty, '.' or '..' component and no drive letter are allowed to become a host path.
        bool safeRelativePath(const std::string &value)
        {
            if (value.empty() || value.size() > kMemoryCardMaximumPathLength)
                return false;
            if (value.front() == '/' || value.back() == '/')
                return false;
            if (value.find('\\') != std::string::npos || value.find(':') != std::string::npos)
                return false;
            size_t start = 0u;
            while (start <= value.size())
            {
                const size_t slash = value.find('/', start);
                const std::string component =
                    value.substr(start, slash == std::string::npos ? std::string::npos : slash - start);
                if (component.empty() || component == "." || component == "..")
                    return false;
                if (slash == std::string::npos)
                    break;
                start = slash + 1u;
            }
            return true;
        }

        bool readWholeFile(const std::filesystem::path &path, std::vector<uint8_t> &out, std::string *error)
        {
            std::ifstream stream(path, std::ios::binary | std::ios::ate);
            if (!stream)
            {
                setError(error, "could not open memory card file " + path.generic_string());
                return false;
            }
            const std::streampos end = stream.tellg();
            if (end < 0 || static_cast<uint64_t>(end) > kMemoryCardMaximumFileSize)
            {
                setError(error, "memory card file is too large: " + path.generic_string());
                return false;
            }
            out.assign(static_cast<size_t>(end), 0u);
            stream.seekg(0, std::ios::beg);
            if (!out.empty())
                stream.read(reinterpret_cast<char *>(out.data()), static_cast<std::streamsize>(out.size()));
            if (!stream)
            {
                setError(error, "could not read memory card file " + path.generic_string());
                return false;
            }
            return true;
        }
    }

    bool packMemoryCard(const std::filesystem::path &cardDirectory, Chunk &chunk, std::string *error)
    {
        std::error_code ec;
        if (!std::filesystem::is_directory(cardDirectory, ec) || ec)
        {
            setError(error, "memory card folder does not exist");
            return false;
        }

        std::vector<CardEntry> entries;
        std::filesystem::recursive_directory_iterator it(
            cardDirectory, std::filesystem::directory_options::none, ec);
        if (ec)
        {
            setError(error, "could not walk the memory card folder");
            return false;
        }
        for (const std::filesystem::directory_entry &entry : it)
        {
            if (entry.is_symlink())
            {
                setError(error, "memory card folder contains a link: " + entry.path().generic_string());
                return false;
            }
            const bool directory = entry.is_directory();
            if (!directory && !entry.is_regular_file())
            {
                setError(error, "memory card folder contains a special file: " + entry.path().generic_string());
                return false;
            }
            const std::string relative = genericRelative(cardDirectory, entry.path());
            if (!safeRelativePath(relative))
            {
                setError(error, "memory card entry has an unusable name: " + relative);
                return false;
            }
            entries.push_back(CardEntry{relative, directory});
            if (entries.size() > kMemoryCardMaximumEntries)
            {
                setError(error, "memory card folder has too many entries");
                return false;
            }
        }

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
        {
            setError(error, "chunk " + chunkIdString(chunk.id) + " is not the memory card chunk");
            return false;
        }
        if (chunk.version != kMemoryCardChunkVersion)
        {
            setError(error, "unsupported memory card chunk version");
            return false;
        }

        Reader reader(chunk.payload);
        uint32_t entryCount = 0u;
        if (!reader.u32(entryCount) || entryCount > kMemoryCardMaximumEntries)
        {
            setError(error, "memory card chunk entry count is invalid");
            return false;
        }

        // Decode the whole chunk before touching the filesystem: a chunk that turns out to be truncated must not
        // have left half a card on disk.
        std::vector<CardEntry> entries;
        std::vector<std::vector<uint8_t>> contents;
        entries.reserve(entryCount);
        contents.reserve(entryCount);
        for (uint32_t index = 0u; index < entryCount; ++index)
        {
            std::string relative;
            uint8_t kind = 0u;
            if (!reader.string(relative, kMemoryCardMaximumPathLength) || !reader.u8(kind) || kind > 1u)
            {
                setError(error, "memory card chunk entry is truncated");
                return false;
            }
            if (!safeRelativePath(relative))
            {
                setError(error, "memory card chunk names an unusable path: " + relative);
                return false;
            }
            std::vector<uint8_t> payload;
            if (kind == 1u)
            {
                std::span<const uint8_t> bytes;
                if (!reader.sizedBytes(bytes, kMemoryCardMaximumFileSize))
                {
                    setError(error, "memory card chunk file contents are truncated");
                    return false;
                }
                payload.assign(bytes.begin(), bytes.end());
            }
            entries.push_back(CardEntry{relative, kind == 0u});
            contents.push_back(std::move(payload));
        }
        if (!reader.atEnd())
        {
            setError(error, "memory card chunk has trailing bytes");
            return false;
        }

        std::error_code ec;
        std::filesystem::create_directories(cardDirectory, ec);
        if (ec && !std::filesystem::is_directory(cardDirectory))
        {
            setError(error, "could not create the memory card folder");
            return false;
        }

        for (size_t index = 0u; index < entries.size(); ++index)
        {
            const std::filesystem::path target = cardDirectory / entries[index].relativePath;
            if (entries[index].directory)
            {
                std::filesystem::create_directories(target, ec);
                if (ec && !std::filesystem::is_directory(target))
                {
                    setError(error, "could not create " + target.generic_string());
                    return false;
                }
                continue;
            }
            std::filesystem::create_directories(target.parent_path(), ec);
            std::ofstream stream(target, std::ios::binary | std::ios::trunc);
            if (!stream)
            {
                setError(error, "could not create " + target.generic_string());
                return false;
            }
            if (!contents[index].empty())
            {
                stream.write(reinterpret_cast<const char *>(contents[index].data()),
                             static_cast<std::streamsize>(contents[index].size()));
            }
            stream.flush();
            if (!stream)
            {
                setError(error, "could not write " + target.generic_string());
                return false;
            }
        }
        return true;
    }
}
