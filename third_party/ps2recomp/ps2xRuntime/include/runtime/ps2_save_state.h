// ps2_save_state.h -- the save-state CONTAINER: a magic, a version, a chunk table and an atomic publish.
//
// Origin: adapted from the MrCoolTheCucumber/PS2Recomp fork of ran-j/PS2Recomp, commit 7978365
// ("feat(runtime): add portable save states"), files ps2xRuntime/include/runtime/ps2_save_state.h and
// ps2xRuntime/src/lib/ps2_save_state.cpp. Both trees are GPL-3.0-only, so this is a GPL-3.0 -> GPL-3.0 move
// (docs/research/41-cucumber-fork.md section 9); MrCoolTheCucumber is named on the ps2recomp row of
// THIRD_PARTY_NOTICES.md. Sprint 11 Task 8c.
//
// What was taken: the byte format (little-endian primitives, 32-byte file header, 32-byte chunk header with an
// FNV-1a payload checksum), the bounded reader, and writeFileAtomically's temp-then-rename publish. What was NOT
// taken: the fork's chunk writer, which enumerates the fork's own runtime state (its EE scheduler, its timing, its
// device registers) and does not describe ours. Full save states are Sprint 12; nothing here is wired into the
// game loop.
//
// The only chunk this file knows how to build is the simulated memory card (mc0, the host directory the kernel's
// MemoryCard stub reads and writes -- Kernel/Syscalls/Helpers/Path.h's getConfiguredMcRoot). It is the proof that
// the container carries real state, and it takes the folder as an argument so this translation unit depends on
// nothing but the standard library.
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <span>
#include <string>
#include <string_view>
#include <vector>

namespace ps2x::savestate
{
    inline constexpr uint32_t kContainerVersion = 1u;
    inline constexpr uint64_t kMaximumFileSize = 512ull * 1024ull * 1024ull;
    inline constexpr uint32_t kMaximumChunkCount = 256u;
    inline constexpr uint64_t kMaximumStringSize = 1024ull * 1024ull;

    enum class ChunkFlags : uint32_t
    {
        None = 0u,
        Required = 1u << 0u,   // a reader that does not know this chunk must refuse the state, not skip it
    };

    [[nodiscard]] constexpr uint32_t makeChunkId(char a, char b, char c, char d) noexcept
    {
        return static_cast<uint32_t>(static_cast<uint8_t>(a)) |
               (static_cast<uint32_t>(static_cast<uint8_t>(b)) << 8u) |
               (static_cast<uint32_t>(static_cast<uint8_t>(c)) << 16u) |
               (static_cast<uint32_t>(static_cast<uint8_t>(d)) << 24u);
    }

    // The four bytes of an id as text, for messages; a byte outside printable ASCII reads as '?'.
    [[nodiscard]] std::string chunkIdString(uint32_t id);

    // Little-endian, whatever the host is: a state written on one machine reads on another.
    class Writer
    {
    public:
        void u8(uint8_t value);
        void boolean(bool value);
        void u16(uint16_t value);
        void u32(uint32_t value);
        void i32(int32_t value);
        void u64(uint64_t value);
        void i64(int64_t value);
        void f32(float value);
        void f64(double value);
        void bytes(std::span<const uint8_t> value);
        void sizedBytes(std::span<const uint8_t> value);   // u64 length, then the bytes
        void string(std::string_view value);

        [[nodiscard]] const std::vector<uint8_t> &data() const noexcept;
        [[nodiscard]] std::vector<uint8_t> take();

    private:
        std::vector<uint8_t> m_data;
    };

    // Every read is bounded by the input span and returns false rather than reading past it; a length prefix is
    // checked against both its caller's maximum and what is actually left.
    class Reader
    {
    public:
        explicit Reader(std::span<const uint8_t> input) noexcept;

        [[nodiscard]] bool u8(uint8_t &value) noexcept;
        [[nodiscard]] bool boolean(bool &value) noexcept;
        [[nodiscard]] bool u16(uint16_t &value) noexcept;
        [[nodiscard]] bool u32(uint32_t &value) noexcept;
        [[nodiscard]] bool i32(int32_t &value) noexcept;
        [[nodiscard]] bool u64(uint64_t &value) noexcept;
        [[nodiscard]] bool i64(int64_t &value) noexcept;
        [[nodiscard]] bool f32(float &value) noexcept;
        [[nodiscard]] bool f64(double &value) noexcept;
        [[nodiscard]] bool bytes(size_t size, std::span<const uint8_t> &value) noexcept;
        [[nodiscard]] bool sizedBytes(std::span<const uint8_t> &value,
                                      uint64_t maximumSize = kMaximumFileSize) noexcept;
        [[nodiscard]] bool string(std::string &value, uint64_t maximumSize = kMaximumStringSize);

        [[nodiscard]] size_t offset() const noexcept;
        [[nodiscard]] size_t remaining() const noexcept;
        [[nodiscard]] bool atEnd() const noexcept;

    private:
        std::span<const uint8_t> m_input;
        size_t m_offset = 0u;
    };

    struct Chunk
    {
        uint32_t id = 0u;
        uint32_t version = 0u;
        ChunkFlags flags = ChunkFlags::None;
        std::vector<uint8_t> payload;
    };

    struct Document
    {
        std::vector<Chunk> chunks;

        [[nodiscard]] const Chunk *find(uint32_t id) const noexcept;
        [[nodiscard]] Chunk *find(uint32_t id) noexcept;
    };

    [[nodiscard]] bool encode(const Document &document, std::vector<uint8_t> &output, std::string *error = nullptr);

    [[nodiscard]] bool decode(std::span<const uint8_t> input, Document &document, std::string *error = nullptr);

    // Writes the whole encoded document to a sibling temporary and renames it over `path`. Nothing ever opens
    // `path` for writing, so a failure at any step -- encode, create, write, rename -- leaves whatever was already
    // there byte-for-byte, and leaves no temporary behind.
    [[nodiscard]] bool writeFileAtomically(const std::filesystem::path &path, const Document &document,
                                           std::string *error = nullptr);

    [[nodiscard]] bool readFile(const std::filesystem::path &path, Document &document, std::string *error = nullptr);

    // ---- the first chunk: the simulated memory card folder -------------------------------------------------
    //
    // mc0 is a host directory (the launcher makes it beside the ELF; PS2X_MC_DIR moves it). The chunk is the
    // directory's own shape: every entry, relative to the folder, in a sorted order so the same folder always
    // packs to the same bytes.
    //
    //   u32 entryCount
    //   entryCount x { string relativePath (always '/'-separated), u8 kind (0 = directory, 1 = file),
    //                  sizedBytes contents (files only) }

    inline constexpr uint32_t kMemoryCardChunkId = makeChunkId('M', 'C', 'R', 'D');
    inline constexpr uint32_t kMemoryCardChunkVersion = 1u;
    inline constexpr uint32_t kMemoryCardMaximumEntries = 4096u;
    inline constexpr uint64_t kMemoryCardMaximumPathLength = 1024u;
    // The retail card is 8 MB (8000 x 1 KB clusters -- Kernel/Stubs/MemoryCard.cpp); twice that is room to spare
    // and still a bound a corrupt file cannot walk past.
    inline constexpr uint64_t kMemoryCardMaximumFileSize = 16ull * 1024ull * 1024ull;

    // Packs `cardDirectory` (which must exist) into a chunk. A missing folder, an entry that is neither a regular
    // file nor a directory, a symlink, or more entries than the bound allows is a failure, not a silent skip.
    [[nodiscard]] bool packMemoryCard(const std::filesystem::path &cardDirectory, Chunk &chunk,
                                      std::string *error = nullptr);

    // Recreates the packed folder under `cardDirectory`, which is created if it does not exist. Entries already
    // there are left alone unless the chunk names them; a file the chunk names is overwritten.
    [[nodiscard]] bool unpackMemoryCard(const Chunk &chunk, const std::filesystem::path &cardDirectory,
                                        std::string *error = nullptr);
}
