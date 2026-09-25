// Sprint 11 Task 8c: the save-state container (runtime/ps2_save_state.h), adapted from the
// MrCoolTheCucumber/PS2Recomp fork's commit 7978365. These cases are this project's own: they prove the byte
// format, the bounded reader and the atomic publish, and then prove the container carries real state by taking a
// simulated memory card folder -- the host directory the kernel's MemoryCard stub reads and writes -- out to a
// state file and back byte-identically.
//
// No game data is involved anywhere here: every card folder a case packs is built by the case itself, in a
// temporary directory, out of bytes it generates.
#include "MiniTest.h"
#include "runtime/ps2_save_state.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <span>
#include <string>
#include <vector>

namespace fs = std::filesystem;
using namespace ps2x::savestate;

namespace
{
    fs::path makeTempDirectory(const std::string &tag)
    {
        static std::atomic<unsigned> counter{0u};
        const auto ticks = std::chrono::steady_clock::now().time_since_epoch().count();
        const fs::path dir = fs::temp_directory_path() /
                             ("ps2x_savestate_" + tag + "_" + std::to_string(ticks) + "_" +
                              std::to_string(counter.fetch_add(1u)));
        std::error_code ec;
        fs::remove_all(dir, ec);
        fs::create_directories(dir, ec);
        return dir;
    }

    void dropTree(const fs::path &dir)
    {
        std::error_code ec;
        fs::remove_all(dir, ec);
    }

    void writeBytes(const fs::path &path, const std::vector<uint8_t> &bytes)
    {
        std::error_code ec;
        fs::create_directories(path.parent_path(), ec);
        std::ofstream stream(path, std::ios::binary | std::ios::trunc);
        if (!bytes.empty())
            stream.write(reinterpret_cast<const char *>(bytes.data()),
                         static_cast<std::streamsize>(bytes.size()));
    }

    std::vector<uint8_t> readBytes(const fs::path &path)
    {
        std::ifstream stream(path, std::ios::binary | std::ios::ate);
        if (!stream)
            return {};
        const std::streamoff end = stream.tellg();
        std::vector<uint8_t> out(end < 0 ? size_t(0) : static_cast<size_t>(end));
        stream.seekg(0, std::ios::beg);
        if (!out.empty())
            stream.read(reinterpret_cast<char *>(out.data()), static_cast<std::streamsize>(out.size()));
        return out;
    }

    // Synthetic bytes: a pattern that depends on the seed, so two different files never accidentally match.
    std::vector<uint8_t> pattern(uint32_t seed, size_t length)
    {
        std::vector<uint8_t> out(length);
        uint32_t state = seed * 2654435761u + 1u;
        for (size_t i = 0; i < length; ++i)
        {
            state = state * 1664525u + 1013904223u;
            out[i] = static_cast<uint8_t>(state >> 24u);
        }
        return out;
    }

    // A card-shaped folder built entirely by the test: nested directories, an empty directory, an empty file,
    // a file with a NUL in the middle and one larger than a cluster.
    void buildSyntheticCard(const fs::path &card)
    {
        std::error_code ec;
        fs::create_directories(card / "SAVEDIR" / "NESTED", ec);
        fs::create_directories(card / "EMPTYDIR", ec);
        writeBytes(card / "SAVEDIR" / "slot0.bin", pattern(1u, 1500));
        writeBytes(card / "SAVEDIR" / "NESTED" / "deep.bin", pattern(2u, 7));
        writeBytes(card / "SAVEDIR" / "zero.bin", std::vector<uint8_t>{});
        writeBytes(card / "header.bin", std::vector<uint8_t>{0x01, 0x00, 0x02, 0x00, 0x03});
    }

    // Every entry of a folder as (relative path, is-directory, contents), sorted: two folders compare equal only
    // when they hold the same names, the same shape and the same bytes.
    struct Entry
    {
        std::string path;
        bool directory = false;
        std::vector<uint8_t> contents;

        bool operator==(const Entry &other) const
        {
            return path == other.path && directory == other.directory && contents == other.contents;
        }
    };

    std::vector<Entry> snapshot(const fs::path &root)
    {
        std::vector<Entry> out;
        std::error_code ec;
        for (const fs::directory_entry &entry : fs::recursive_directory_iterator(root, ec))
        {
            Entry item;
            item.path = entry.path().lexically_relative(root).generic_string();
            item.directory = entry.is_directory();
            if (!item.directory)
                item.contents = readBytes(entry.path());
            out.push_back(std::move(item));
        }
        std::sort(out.begin(), out.end(), [](const Entry &a, const Entry &b) { return a.path < b.path; });
        return out;
    }

    size_t countEntries(const fs::path &dir)
    {
        size_t n = 0;
        std::error_code ec;
        for (const fs::directory_entry &entry : fs::directory_iterator(dir, ec))
        {
            (void)entry;
            ++n;
        }
        return n;
    }

    bool holdsATemporary(const fs::path &dir)
    {
        std::error_code ec;
        for (const fs::directory_entry &entry : fs::directory_iterator(dir, ec))
        {
            if (entry.path().filename().string().find(".tmp-") != std::string::npos)
                return true;
        }
        return false;
    }

    // Writes `width` little-endian bytes of `value` over an already-encoded file, so a case can craft a header
    // field no encoder of ours would ever produce.
    void patchLittle(std::vector<uint8_t> &bytes, size_t offset, uint64_t value, size_t width)
    {
        for (size_t index = 0u; index < width; ++index)
            bytes[offset + index] = static_cast<uint8_t>(value >> (index * 8u));
    }

    // Where the fields the cases patch live: the file header is 32 bytes, the first chunk header follows it.
    constexpr size_t kChunkCountOffset = 16u;
    constexpr size_t kFirstChunkPayloadSizeOffset = 32u + 16u;

    Chunk makeChunk(uint32_t id, std::vector<uint8_t> payload, uint32_t version = 1u)
    {
        Chunk chunk;
        chunk.id = id;
        chunk.version = version;
        chunk.payload = std::move(payload);
        return chunk;
    }
}

void register_ps2_save_state_tests()
{
    MiniTest::Case("SaveStateContainer", [](TestCase &tc)
    {
        tc.Run("an empty document round-trips, and the file is the bare 32-byte header", [](TestCase &t)
        {
            Document document;
            std::vector<uint8_t> encoded;
            std::string error;
            t.IsTrue(encode(document, encoded, &error), "an empty document encodes: " + error);
            t.Equals(encoded.size(), size_t(32), "header only, no chunks");
            t.IsTrue(std::memcmp(encoded.data(), "P2XSTATE", 8) == 0, "the file starts with the magic");
            t.Equals(encoded[8], uint8_t(kContainerVersion), "the container version follows the magic");

            Document back;
            t.IsTrue(decode(encoded, back, &error), "and decodes: " + error);
            t.Equals(back.chunks.size(), size_t(0), "no chunks came back");
        });

        tc.Run("every primitive round-trips, and the bytes on disk are little-endian", [](TestCase &t)
        {
            Writer writer;
            writer.u8(0xA5u);
            writer.boolean(true);
            writer.boolean(false);
            writer.u16(0x1122u);
            writer.u32(0x11223344u);
            writer.i32(-2);
            writer.u64(0x1122334455667788ull);
            writer.i64(-3);
            writer.f32(0.5f);
            writer.f64(-0.25);
            writer.string("mc0:");
            const std::vector<uint8_t> blob{0xDEu, 0xADu, 0xBEu, 0xEFu};
            writer.sizedBytes(blob);
            const std::vector<uint8_t> bytes = writer.data();

            // The u32 sits after u8 + 2 booleans + u16 = 5 bytes, least significant byte first.
            t.Equals(bytes[5], uint8_t(0x44), "u32 byte 0 is the low byte");
            t.Equals(bytes[6], uint8_t(0x33), "u32 byte 1");
            t.Equals(bytes[7], uint8_t(0x22), "u32 byte 2");
            t.Equals(bytes[8], uint8_t(0x11), "u32 byte 3 is the high byte");

            Reader reader(bytes);
            uint8_t u8v = 0u;
            bool trueValue = false, falseValue = true;
            uint16_t u16v = 0u;
            uint32_t u32v = 0u;
            int32_t i32v = 0;
            uint64_t u64v = 0u;
            int64_t i64v = 0;
            float f32v = 0.0f;
            double f64v = 0.0;
            std::string text;
            std::span<const uint8_t> tail;
            t.IsTrue(reader.u8(u8v) && u8v == 0xA5u, "u8");
            t.IsTrue(reader.boolean(trueValue) && trueValue, "boolean true");
            t.IsTrue(reader.boolean(falseValue) && !falseValue, "boolean false");
            t.IsTrue(reader.u16(u16v) && u16v == 0x1122u, "u16");
            t.IsTrue(reader.u32(u32v) && u32v == 0x11223344u, "u32");
            t.IsTrue(reader.i32(i32v) && i32v == -2, "i32");
            t.IsTrue(reader.u64(u64v) && u64v == 0x1122334455667788ull, "u64");
            t.IsTrue(reader.i64(i64v) && i64v == -3, "i64");
            t.IsTrue(reader.f32(f32v) && f32v == 0.5f, "f32");
            t.IsTrue(reader.f64(f64v) && f64v == -0.25, "f64");
            t.IsTrue(reader.string(text) && text == "mc0:", "string");
            t.IsTrue(reader.sizedBytes(tail) && std::vector<uint8_t>(tail.begin(), tail.end()) == blob, "sizedBytes");
            t.IsTrue(reader.atEnd(), "nothing left over");
            t.Equals(reader.remaining(), size_t(0), "remaining() agrees");
        });

        tc.Run("the reader stops at the end of its input instead of reading past it", [](TestCase &t)
        {
            const std::vector<uint8_t> three{1u, 2u, 3u};
            Reader reader(three);
            uint32_t value = 0u;
            t.IsFalse(reader.u32(value), "a u32 does not fit in three bytes");
            Reader again(three);
            std::span<const uint8_t> got;
            t.IsFalse(again.bytes(4u, got), "four bytes do not fit either");
            t.Equals(again.offset(), size_t(0), "and the offset did not move");
            uint8_t byte = 0u;
            t.IsTrue(again.u8(byte) && byte == 1u, "the reader is still usable after a refusal");

            Reader empty(std::span<const uint8_t>{});
            t.IsTrue(empty.atEnd(), "an empty input is already at the end");
            t.IsFalse(empty.u8(byte), "and yields nothing");
        });

        tc.Run("a length prefix is bounded by the input and by the caller's maximum", [](TestCase &t)
        {
            Writer writer;
            writer.u64(1024ull * 1024ull * 1024ull);   // a length far past what follows
            writer.u8(0u);
            Reader reader(writer.data());
            std::span<const uint8_t> got;
            t.IsFalse(reader.sizedBytes(got), "a length past the end of the input is refused");

            Writer small;
            small.string("abcdefgh");
            Reader bounded(small.data());
            std::string text;
            t.IsFalse(bounded.string(text, 4u), "eight bytes are refused when the caller allows four");
            Reader allowed(small.data());
            t.IsTrue(allowed.string(text, 8u) && text == "abcdefgh", "and accepted when the caller allows eight");
        });

        tc.Run("chunks round-trip with id, version and flags, and find() locates one by id", [](TestCase &t)
        {
            Document document;
            document.chunks.push_back(makeChunk(makeChunkId('A', 'A', 'A', 'A'), pattern(7u, 64), 3u));
            document.chunks.push_back(makeChunk(makeChunkId('B', 'B', 'B', 'B'), std::vector<uint8_t>{}));
            document.chunks.back().flags = ChunkFlags::Required;

            std::vector<uint8_t> encoded;
            std::string error;
            t.IsTrue(encode(document, encoded, &error), "encodes: " + error);
            Document back;
            t.IsTrue(decode(encoded, back, &error), "decodes: " + error);
            t.Equals(back.chunks.size(), size_t(2), "both chunks came back");

            const Chunk *first = back.find(makeChunkId('A', 'A', 'A', 'A'));
            t.IsNotNull(first, "find() locates the first chunk");
            if (first)
            {
                t.Equals(first->version, uint32_t(3), "its version survived");
                t.IsTrue(first->payload == pattern(7u, 64), "its payload is byte-for-byte");
                t.IsTrue(first->flags == ChunkFlags::None, "its flags survived");
            }
            const Chunk *second = back.find(makeChunkId('B', 'B', 'B', 'B'));
            t.IsNotNull(second, "find() locates the empty chunk");
            if (second)
            {
                t.Equals(second->payload.size(), size_t(0), "an empty payload is legal");
                t.IsTrue(second->flags == ChunkFlags::Required, "the Required flag survived");
            }
            t.IsNull(back.find(makeChunkId('Z', 'Z', 'Z', 'Z')), "and returns null for an id that is not there");
            t.Equals(chunkIdString(makeChunkId('M', 'C', 'R', 'D')), std::string("MCRD"), "an id reads back as text");
        });

        tc.Run("a single flipped payload byte is caught by the chunk checksum", [](TestCase &t)
        {
            Document document;
            document.chunks.push_back(makeChunk(makeChunkId('C', 'H', 'K', 'S'), pattern(11u, 256)));
            std::vector<uint8_t> encoded;
            std::string error;
            t.IsTrue(encode(document, encoded, &error), "encodes: " + error);

            std::vector<uint8_t> corrupt = encoded;
            corrupt[encoded.size() - 5u] ^= 0x01u;   // one bit, inside the payload
            Document back;
            error.clear();
            t.IsFalse(decode(corrupt, back, &error), "the flipped byte is refused");
            t.IsTrue(error.find("checksum") != std::string::npos, "and the reason says checksum: " + error);
        });

        tc.Run("a truncated file and a padded one are both refused", [](TestCase &t)
        {
            Document document;
            document.chunks.push_back(makeChunk(makeChunkId('T', 'R', 'U', 'N'), pattern(13u, 128)));
            std::vector<uint8_t> encoded;
            std::string error;
            t.IsTrue(encode(document, encoded, &error), "encodes: " + error);

            Document back;
            std::vector<uint8_t> half(encoded.begin(), encoded.begin() + (encoded.size() / 2u));
            t.IsFalse(decode(half, back, &error), "half a file is refused");
            std::vector<uint8_t> stub(encoded.begin(), encoded.begin() + 20);
            t.IsFalse(decode(stub, back, &error), "less than a header is refused");
            std::vector<uint8_t> padded = encoded;
            padded.push_back(0u);
            t.IsFalse(decode(padded, back, &error), "a byte appended past the last chunk is refused");
        });

        tc.Run("the wrong magic and an unknown container version are each refused", [](TestCase &t)
        {
            Document document;
            document.chunks.push_back(makeChunk(makeChunkId('M', 'A', 'G', 'C'), pattern(17u, 16)));
            std::vector<uint8_t> encoded;
            std::string error;
            t.IsTrue(encode(document, encoded, &error), "encodes: " + error);

            Document back;
            std::vector<uint8_t> wrongMagic = encoded;
            wrongMagic[0] = 'Q';
            error.clear();
            t.IsFalse(decode(wrongMagic, back, &error), "a file that is not ours is refused");
            t.IsTrue(error.find("header") != std::string::npos, "and says so: " + error);

            std::vector<uint8_t> wrongVersion = encoded;
            wrongVersion[8] = static_cast<uint8_t>(kContainerVersion + 1u);
            error.clear();
            t.IsFalse(decode(wrongVersion, back, &error), "a newer container version is refused");
            t.IsTrue(error.find("version") != std::string::npos, "and says so: " + error);
        });

        tc.Run("duplicate chunk ids are refused when writing and when reading", [](TestCase &t)
        {
            Document document;
            document.chunks.push_back(makeChunk(makeChunkId('D', 'U', 'P', 'E'), pattern(19u, 8)));
            document.chunks.push_back(makeChunk(makeChunkId('D', 'U', 'P', 'E'), pattern(23u, 8)));
            std::vector<uint8_t> encoded;
            std::string error;
            t.IsFalse(encode(document, encoded, &error), "encode refuses two chunks with one id");
            t.IsTrue(error.find("duplicate") != std::string::npos, "and says duplicate: " + error);

            // A file built by something else could still hold two: the reader refuses it too. Build one by
            // encoding two distinct ids and then rewriting the second id over the first's.
            Document distinct;
            distinct.chunks.push_back(makeChunk(makeChunkId('D', 'U', 'P', 'E'), pattern(19u, 8)));
            distinct.chunks.push_back(makeChunk(makeChunkId('O', 'T', 'H', 'R'), pattern(23u, 8)));
            t.IsTrue(encode(distinct, encoded, &error), "the distinct pair encodes: " + error);
            const size_t secondHeader = 32u + 32u + 8u;   // file header, first chunk header, first payload
            std::memcpy(encoded.data() + secondHeader, encoded.data() + 32u, 4u);
            // The id is not covered by the payload checksum, so this file is otherwise well-formed.
            Document back;
            error.clear();
            t.IsFalse(decode(encoded, back, &error), "decode refuses the duplicate too");
            t.IsTrue(error.find("duplicate") != std::string::npos, "and says duplicate: " + error);
        });

        tc.Run("too many chunks, and a flag the container does not define, are refused", [](TestCase &t)
        {
            Document tooMany;
            for (uint32_t i = 0u; i <= kMaximumChunkCount; ++i)
                tooMany.chunks.push_back(makeChunk(i + 1u, std::vector<uint8_t>{}));
            std::vector<uint8_t> encoded;
            std::string error;
            t.IsFalse(encode(tooMany, encoded, &error), "one chunk past the bound is refused");
            t.Equals(tooMany.chunks.size(), size_t(kMaximumChunkCount) + 1u, "the bound is what the header says");

            Document badFlag;
            badFlag.chunks.push_back(makeChunk(makeChunkId('F', 'L', 'A', 'G'), std::vector<uint8_t>{}));
            badFlag.chunks.back().flags = static_cast<ChunkFlags>(0x80u);
            error.clear();
            t.IsFalse(encode(badFlag, encoded, &error), "an undefined flag is refused");
            t.IsTrue(error.find("flags") != std::string::npos, "and says flags: " + error);
        });

        // The encode side of the chunk bound is case 10's; this is the read side, which is the one a corrupt
        // file meets. The count is refused before `decode` reserves anything, so four billion costs nothing.
        tc.Run("a header claiming four billion chunks is refused before anything is reserved", [](TestCase &t)
        {
            Document document;
            document.chunks.push_back(makeChunk(makeChunkId('C', 'N', 'T', 'R'), pattern(53u, 24)));
            std::vector<uint8_t> encoded;
            std::string error;
            t.IsTrue(encode(document, encoded, &error), "encodes: " + error);

            // Only the count is touched: the file is the size its own header claims, so the size check passes
            // and the chunk bound is the thing that must refuse.
            patchLittle(encoded, kChunkCountOffset, 0xFFFFFFFFull, 4u);
            Document back;
            error.clear();
            t.IsFalse(decode(encoded, back, &error), "four billion chunks are refused");
            t.IsTrue(error.find("too many chunks") != std::string::npos, "and say so: " + error);
            t.Equals(back.chunks.size(), size_t(0), "nothing was built");
        });

        tc.Run("a chunk claiming to be larger than the file it sits in is refused", [](TestCase &t)
        {
            Document document;
            document.chunks.push_back(makeChunk(makeChunkId('H', 'U', 'G', 'E'), pattern(59u, 24)));
            std::vector<uint8_t> encoded;
            std::string error;
            t.IsTrue(encode(document, encoded, &error), "encodes: " + error);

            // 256 MB: under the container's own 512 MB ceiling, so the bound that has to catch it is the one
            // that asks what is actually left in the file.
            std::vector<uint8_t> overlong = encoded;
            patchLittle(overlong, kFirstChunkPayloadSizeOffset, 256ull * 1024ull * 1024ull, 8u);
            Document back;
            error.clear();
            t.IsFalse(decode(overlong, back, &error), "a payload larger than the file is refused");
            t.IsTrue(error.find("payload is truncated") != std::string::npos, "and says so: " + error);

            // And past the ceiling, which the earlier guard catches -- same refusal, no allocation either way.
            std::vector<uint8_t> absurd = encoded;
            patchLittle(absurd, kFirstChunkPayloadSizeOffset, 0xFFFFFFFFFFFFFFFFull, 8u);
            error.clear();
            t.IsFalse(decode(absurd, back, &error), "a payload of 2^64-1 is refused");
            t.IsTrue(error.find("payload is truncated") != std::string::npos, "and says so: " + error);
            t.Equals(back.chunks.size(), size_t(0), "nothing was built either time");
        });

        tc.Run("a refused file leaves the caller's document exactly as it was", [](TestCase &t)
        {
            Document held;
            held.chunks.push_back(makeChunk(makeChunkId('K', 'E', 'E', 'P'), pattern(29u, 32)));
            const std::vector<uint8_t> garbage{'n', 'o', 't', ' ', 'a', ' ', 's', 't', 'a', 't', 'e'};
            t.IsFalse(decode(garbage, held, nullptr), "garbage is refused");
            t.Equals(held.chunks.size(), size_t(1), "the document the caller passed still holds its chunk");
            t.IsTrue(held.chunks[0].payload == pattern(29u, 32), "byte-for-byte");
        });
    });

    MiniTest::Case("SaveStateMemoryCard", [](TestCase &tc)
    {
        tc.Run("a simulated card folder round-trips byte-identically through a state file", [](TestCase &t)
        {
            const fs::path root = makeTempDirectory("roundtrip");
            const fs::path card = root / "mc0";
            const fs::path restored = root / "mc0-restored";
            buildSyntheticCard(card);
            const std::vector<Entry> before = snapshot(card);
            t.Equals(before.size(), size_t(7), "the synthetic card has seven entries");

            std::string error;
            Chunk chunk;
            t.IsTrue(packMemoryCard(card, chunk, &error), "the folder packs: " + error);
            t.Equals(chunk.id, kMemoryCardChunkId, "into the MCRD chunk");
            t.Equals(chunk.version, kMemoryCardChunkVersion, "at the chunk version the header declares");
            t.IsTrue(chunk.flags == ChunkFlags::Required, "and marked Required: a reader must not skip the card");

            Document document;
            document.chunks.push_back(chunk);
            const fs::path state = root / "slot0.p2s";
            t.IsTrue(writeFileAtomically(state, document, &error), "the state file is written: " + error);

            Document back;
            t.IsTrue(readFile(state, back, &error), "and read back: " + error);
            const Chunk *found = back.find(kMemoryCardChunkId);
            t.IsNotNull(found, "the card chunk is in the file");
            if (found)
            {
                t.IsTrue(unpackMemoryCard(*found, restored, &error), "and unpacks: " + error);
                t.IsTrue(snapshot(restored) == before, "the restored folder is the card, byte for byte");
            }
            dropTree(root);
        });

        tc.Run("the same folder packs to the same bytes, parents before their contents", [](TestCase &t)
        {
            const fs::path root = makeTempDirectory("stable");
            const fs::path card = root / "mc0";
            buildSyntheticCard(card);

            std::string error;
            Chunk first, second;
            t.IsTrue(packMemoryCard(card, first, &error), "packs once: " + error);
            t.IsTrue(packMemoryCard(card, second, &error), "packs twice: " + error);
            t.IsTrue(first.payload == second.payload, "the two packings are the same bytes");

            // Sorted names put "SAVEDIR" before "SAVEDIR/NESTED" before "SAVEDIR/NESTED/deep.bin", so unpacking
            // in payload order never needs a directory that has not been made yet.
            Reader reader(first.payload);
            uint32_t count = 0u;
            std::string previous;
            t.IsTrue(reader.u32(count), "the entry count leads the payload");
            t.Equals(count, uint32_t(7), "seven entries");
            for (uint32_t i = 0u; i < count; ++i)
            {
                std::string name;
                uint8_t kind = 0u;
                t.IsTrue(reader.string(name), "entry name");
                t.IsTrue(reader.u8(kind), "entry kind");
                t.IsTrue(previous < name, "entries are in ascending order: " + previous + " < " + name);
                previous = name;
                if (kind == 1u)
                {
                    std::span<const uint8_t> contents;
                    t.IsTrue(reader.sizedBytes(contents), "file contents follow a file entry");
                }
            }
            t.IsTrue(reader.atEnd(), "the payload holds exactly its entries");
            dropTree(root);
        });

        tc.Run("a write that cannot be encoded leaves the previous state file byte-for-byte", [](TestCase &t)
        {
            const fs::path root = makeTempDirectory("intact");
            const fs::path card = root / "mc0";
            const fs::path state = root / "slot0.p2s";
            buildSyntheticCard(card);

            std::string error;
            Chunk chunk;
            t.IsTrue(packMemoryCard(card, chunk, &error), "the card packs: " + error);
            Document good;
            good.chunks.push_back(chunk);
            t.IsTrue(writeFileAtomically(state, good, &error), "the first write lands: " + error);
            const std::vector<uint8_t> published = readBytes(state);
            t.IsTrue(published.size() > 32u, "and the file has content");

            // A second write that fails at the encode step -- two chunks with one id -- must not touch the file.
            Document broken;
            broken.chunks.push_back(chunk);
            broken.chunks.push_back(chunk);
            error.clear();
            t.IsFalse(writeFileAtomically(state, broken, &error), "the bad write is refused");
            t.IsTrue(readBytes(state) == published, "the published state is byte-for-byte what it was");
            t.IsFalse(holdsATemporary(root), "and no temporary was left behind");
            t.Equals(countEntries(root), size_t(2), "the folder holds the card and the one state file");

            // And the good path replaces it completely: one file, decoding to the new document, never a mixture.
            Document second;
            second.chunks.push_back(chunk);
            second.chunks.push_back(makeChunk(makeChunkId('N', 'O', 'T', 'E'), pattern(31u, 40)));
            t.IsTrue(writeFileAtomically(state, second, &error), "the good write lands: " + error);
            t.IsFalse(holdsATemporary(root), "the temporary is gone once it is published");
            t.Equals(countEntries(root), size_t(2), "still one state file beside the card");
            Document reread;
            t.IsTrue(readFile(state, reread, &error), "and it reads: " + error);
            t.Equals(reread.chunks.size(), size_t(2), "as the new document, whole");
            dropTree(root);
        });

        tc.Run("the publish is a rename, so the destination file is never rewritten in place", [](TestCase &t)
        {
            const fs::path root = makeTempDirectory("rename");
            const fs::path card = root / "mc0";
            const fs::path state = root / "slot0.p2s";
            buildSyntheticCard(card);
            std::string error;
            Chunk chunk;
            t.IsTrue(packMemoryCard(card, chunk, &error), "the card packs: " + error);
            Document first;
            first.chunks.push_back(chunk);
            t.IsTrue(writeFileAtomically(state, first, &error), "the first state lands: " + error);
            const std::vector<uint8_t> published = readBytes(state);

            // A hard link is a second name for the very same file. If the next write goes through a temporary
            // and a rename, the link keeps pointing at the old file and still reads the old bytes; an
            // implementation that opened the destination and rewrote it would show the new ones through the link.
            const fs::path witness = root / "witness.link";
            std::error_code linkError;
            fs::create_hard_link(state, witness, linkError);
            // The link is the whole proof, so a filesystem that cannot make one fails the case rather than
            // quietly reducing it to "the destination holds new bytes".
            t.IsFalse(static_cast<bool>(linkError),
                      "a hard link could not be made in the temp folder, so this case proves nothing: " +
                          linkError.message());

            Document second;
            second.chunks.push_back(chunk);
            second.chunks.push_back(makeChunk(makeChunkId('N', 'O', 'T', 'E'), pattern(43u, 24)));
            t.IsTrue(writeFileAtomically(state, second, &error), "the second state lands: " + error);
            t.IsTrue(readBytes(state) != published, "the destination now holds the new state");
            t.IsTrue(readBytes(witness) == published, "and the old file, still named by the link, is unchanged");
            dropTree(root);
        });

        // The suite cannot cut the power, so it proves the call that would matter if it did: the temporary is
        // flushed to the disk (FlushFileBuffers on Windows, fsync elsewhere) before the rename is asked for.
        tc.Run("the temporary is flushed to the disk once per published file", [](TestCase &t)
        {
            const fs::path root = makeTempDirectory("fsync");
            const fs::path card = root / "mc0";
            buildSyntheticCard(card);
            std::string error;
            Chunk chunk;
            t.IsTrue(packMemoryCard(card, chunk, &error), "the card packs: " + error);
            Document document;
            document.chunks.push_back(chunk);

            const uint64_t before = detail::g_fileSyncCount.load();
            t.IsTrue(writeFileAtomically(root / "slot0.p2s", document, &error), "the state lands: " + error);
            t.Equals(detail::g_fileSyncCount.load() - before, uint64_t(1), "one flush for one published file");
            t.IsTrue(writeFileAtomically(root / "slot1.p2s", document, &error), "a second state lands: " + error);
            t.Equals(detail::g_fileSyncCount.load() - before, uint64_t(2), "and one more for the second");

            // A document that cannot be encoded never gets as far as a file to flush.
            Document broken;
            broken.chunks.push_back(chunk);
            broken.chunks.push_back(chunk);
            t.IsFalse(writeFileAtomically(root / "slot2.p2s", broken, &error), "the bad write is refused");
            t.Equals(detail::g_fileSyncCount.load() - before, uint64_t(2), "with nothing flushed");
            dropTree(root);
        });

        tc.Run("a flush that fails refuses the publish and leaves the previous state where it was", [](TestCase &t)
        {
            const fs::path root = makeTempDirectory("fsyncfail");
            const fs::path card = root / "mc0";
            const fs::path state = root / "slot0.p2s";
            buildSyntheticCard(card);
            std::string error;
            Chunk chunk;
            t.IsTrue(packMemoryCard(card, chunk, &error), "the card packs: " + error);
            Document first;
            first.chunks.push_back(chunk);
            t.IsTrue(writeFileAtomically(state, first, &error), "the first state lands: " + error);
            const std::vector<uint8_t> published = readBytes(state);

            // This is the interruption that matters: the temporary is written, and the publish stops between
            // the bytes and the rename, with a good state file already in place underneath.
            Document second;
            second.chunks.push_back(chunk);
            second.chunks.push_back(makeChunk(makeChunkId('N', 'O', 'T', 'E'), pattern(61u, 16)));
            detail::g_failNextFileSync.store(true);
            error.clear();
            t.IsFalse(writeFileAtomically(state, second, &error), "the publish is refused");
            t.IsTrue(error.find("flush") != std::string::npos, "and says the flush failed: " + error);
            t.IsFalse(detail::g_failNextFileSync.load(), "the injected fault was consumed, not left armed");
            t.IsTrue(readBytes(state) == published, "the previous state is byte-for-byte what it was");
            t.IsFalse(holdsATemporary(root), "and the temporary it had written is gone");
            t.Equals(countEntries(root), size_t(2), "the folder holds the card and the one state file");

            // The very next write, with no fault, lands normally.
            t.IsTrue(writeFileAtomically(state, second, &error), "the retry lands: " + error);
            Document reread;
            t.IsTrue(readFile(state, reread, &error) && reread.chunks.size() == 2u, "as the new state: " + error);
            dropTree(root);
        });

        tc.Run("a publish that cannot complete leaves the destination alone and cleans up after itself", [](TestCase &t)
        {
            const fs::path root = makeTempDirectory("publish");
            const fs::path card = root / "mc0";
            buildSyntheticCard(card);
            std::string error;
            Chunk chunk;
            t.IsTrue(packMemoryCard(card, chunk, &error), "the card packs: " + error);
            Document document;
            document.chunks.push_back(chunk);

            // The destination is a folder with something in it: the rename at the end cannot succeed.
            const fs::path blocked = root / "occupied.p2s";
            writeBytes(blocked / "inside.bin", pattern(37u, 24));
            const std::vector<Entry> before = snapshot(blocked);
            error.clear();
            t.IsFalse(writeFileAtomically(blocked, document, &error), "the publish fails");
            t.IsTrue(error.find("publish") != std::string::npos, "and says where it failed: " + error);
            t.IsTrue(snapshot(blocked) == before, "what was at the destination is untouched");
            t.IsFalse(holdsATemporary(root), "and the temporary it wrote was removed");

            t.IsFalse(writeFileAtomically(fs::path(), document, &error), "an empty path is refused outright");
            dropTree(root);
        });

        tc.Run("a state file cut in half is refused rather than half-loaded", [](TestCase &t)
        {
            const fs::path root = makeTempDirectory("halffile");
            const fs::path card = root / "mc0";
            buildSyntheticCard(card);
            std::string error;
            Chunk chunk;
            t.IsTrue(packMemoryCard(card, chunk, &error), "the card packs: " + error);
            Document document;
            document.chunks.push_back(chunk);
            const fs::path state = root / "slot0.p2s";
            t.IsTrue(writeFileAtomically(state, document, &error), "the state is written: " + error);

            // What a writer that did not go through a temporary could leave behind after a power cut.
            const std::vector<uint8_t> whole = readBytes(state);
            const fs::path torn = root / "torn.p2s";
            writeBytes(torn, std::vector<uint8_t>(whole.begin(), whole.begin() + (whole.size() / 2u)));
            Document loaded;
            error.clear();
            t.IsFalse(readFile(torn, loaded, &error), "the half file is refused");
            t.Equals(loaded.chunks.size(), size_t(0), "and nothing was loaded from it");

            t.IsFalse(readFile(root / "absent.p2s", loaded, &error), "a file that is not there is refused");
            t.IsTrue(error.find("open") != std::string::npos, "and says it could not open it: " + error);
            dropTree(root);
        });

        tc.Run("a chunk naming a path outside the card folder is refused and writes nothing", [](TestCase &t)
        {
            const fs::path root = makeTempDirectory("escape");
            const fs::path card = root / "mc0";
            std::error_code ec;
            fs::create_directories(card, ec);   // so "nothing was written inside it" is an assertion, not a void

            // The escapes, and the names Windows would turn into something other than a file: NUL opens the
            // null device, and a trailing dot or space is silently trimmed, so two names would become one.
            for (const std::string &name : {std::string("../escape.bin"), std::string("/absolute.bin"),
                                            std::string("SAVEDIR/../../escape.bin"), std::string("C:/escape.bin"),
                                            std::string(""), std::string("NUL"), std::string("con.txt"),
                                            std::string("COM1"), std::string("SAVEDIR/lpt1.bin"),
                                            std::string("trailing."), std::string("trailing ")})
            {
                Writer writer;
                writer.u32(1u);
                writer.string(name);
                writer.u8(1u);
                writer.sizedBytes(pattern(41u, 4));
                Chunk chunk;
                chunk.id = kMemoryCardChunkId;
                chunk.version = kMemoryCardChunkVersion;
                chunk.payload = writer.take();
                std::string error;
                t.IsFalse(unpackMemoryCard(chunk, card, &error), "refused: " + name);
            }
            t.IsFalse(fs::exists(root / "escape.bin"), "nothing was written beside the card folder");
            t.Equals(countEntries(card), size_t(0), "and nothing inside it either");

            // The wrong chunk id and an unknown chunk version are refused before any of that.
            Chunk wrong;
            wrong.id = makeChunkId('N', 'O', 'P', 'E');
            wrong.version = kMemoryCardChunkVersion;
            std::string error;
            t.IsFalse(unpackMemoryCard(wrong, card, &error), "another chunk is not the card");
            Chunk future;
            future.id = kMemoryCardChunkId;
            future.version = kMemoryCardChunkVersion + 1u;
            error.clear();
            t.IsFalse(unpackMemoryCard(future, card, &error), "a newer card chunk is refused");
            t.IsTrue(error.find("version") != std::string::npos, "and says version: " + error);

            // A truncated card chunk is refused whole: no half a card on disk.
            Writer partial;
            partial.u32(2u);
            partial.string("SAVEDIR");
            partial.u8(0u);
            partial.string("SAVEDIR/slot0.bin");
            partial.u8(1u);   // the file's contents never follow
            Chunk cut;
            cut.id = kMemoryCardChunkId;
            cut.version = kMemoryCardChunkVersion;
            cut.payload = partial.take();
            error.clear();
            t.IsFalse(unpackMemoryCard(cut, card, &error), "a truncated card chunk is refused");
            t.IsFalse(fs::exists(card / "SAVEDIR"), "and the directory it named was never created");

            // An entry count out of a corrupt file is bounded the same way the container's chunk count is.
            Writer absurd;
            absurd.u32(0xFFFFFFFFu);
            Chunk fourBillion;
            fourBillion.id = kMemoryCardChunkId;
            fourBillion.version = kMemoryCardChunkVersion;
            fourBillion.payload = absurd.take();
            error.clear();
            t.IsFalse(unpackMemoryCard(fourBillion, card, &error), "four billion card entries are refused");
            t.IsTrue(error.find("entry count") != std::string::npos, "and say so: " + error);
            t.Equals(countEntries(card), size_t(0), "with the card folder still empty");
            dropTree(root);
        });

        // A restore is the chunk's contents exactly. Anything the card has gained since the state was taken is
        // neither the saved card nor a card the guest's own free-space walk would agree with, so it goes.
        tc.Run("a restore is the chunk exactly: what the chunk does not name is gone afterwards", [](TestCase &t)
        {
            const fs::path root = makeTempDirectory("restore");
            const fs::path card = root / "mc0";
            buildSyntheticCard(card);
            const std::vector<Entry> saved = snapshot(card);

            std::string error;
            Chunk chunk;
            t.IsTrue(packMemoryCard(card, chunk, &error), "the card packs: " + error);

            // The card moves on: a stray file at the top, a whole stray directory, a stray inside a directory
            // the chunk does name, and a named file whose bytes have changed.
            writeBytes(card / "STRAY.bin", pattern(67u, 32));
            writeBytes(card / "STRAYDIR" / "inside.bin", pattern(71u, 16));
            writeBytes(card / "SAVEDIR" / "extra.bin", pattern(73u, 8));
            writeBytes(card / "SAVEDIR" / "slot0.bin", pattern(79u, 64));
            t.IsFalse(snapshot(card) == saved, "the card really has moved on");

            t.IsTrue(unpackMemoryCard(chunk, card, &error), "the state restores over it: " + error);
            t.IsTrue(snapshot(card) == saved, "and the card is the saved one exactly, strays and all");
            t.IsFalse(fs::exists(card / "STRAY.bin"), "the stray file is gone");
            t.IsFalse(fs::exists(card / "STRAYDIR"), "the stray directory is gone");
            t.IsFalse(fs::exists(card / "SAVEDIR" / "extra.bin"), "the stray inside a named directory is gone");
            t.IsTrue(fs::exists(card / "SAVEDIR" / "NESTED" / "deep.bin"), "and what the chunk names is still there");

            // A directory the chunk does not name but a named file lives under must survive: the clearing
            // never removes something a named entry sits inside.
            Writer writer;
            writer.u32(1u);
            writer.string("SAVEDIR/slot0.bin");
            writer.u8(1u);
            writer.sizedBytes(pattern(83u, 12));
            Chunk implied;
            implied.id = kMemoryCardChunkId;
            implied.version = kMemoryCardChunkVersion;
            implied.payload = writer.take();
            const fs::path second = root / "mc0-implied";
            t.IsTrue(unpackMemoryCard(implied, second, &error), "a chunk naming only a file restores: " + error);
            t.IsTrue(fs::is_directory(second / "SAVEDIR"), "its unnamed parent directory was kept");
            t.IsTrue(readBytes(second / "SAVEDIR" / "slot0.bin") == pattern(83u, 12), "with the file in it");
            t.Equals(countEntries(second), size_t(1), "and nothing else at the top");

            // The clearing never leaves the folder it was handed: a path that is a file, or a filesystem root,
            // is refused before anything is written or removed.
            const fs::path notAFolder = root / "a-file.bin";
            writeBytes(notAFolder, pattern(89u, 4));
            error.clear();
            t.IsFalse(unpackMemoryCard(chunk, notAFolder, &error), "a file is not a card folder");
            t.IsTrue(error.find("not a directory") != std::string::npos, "and says so: " + error);
            t.IsTrue(readBytes(notAFolder) == pattern(89u, 4), "and the file is untouched");
            t.IsFalse(unpackMemoryCard(chunk, fs::path(), &error), "an empty path is refused");
            #ifdef _WIN32
            // A drive that does not exist: a regression in usableCardRoot must not be able to write into C:\.
            t.IsFalse(unpackMemoryCard(chunk, fs::path("Q:/"), &error), "and so is a filesystem root");
#else
            t.IsFalse(unpackMemoryCard(chunk, fs::path("/"), &error), "and so is a filesystem root");
#endif
            dropTree(root);
        });

        tc.Run("a folder that is not there does not pack, and an empty one round-trips", [](TestCase &t)
        {
            const fs::path root = makeTempDirectory("empty");
            std::string error;
            Chunk chunk;
            t.IsFalse(packMemoryCard(root / "no-such-card", chunk, &error), "a missing folder is refused");

            const fs::path card = root / "mc0";
            std::error_code ec;
            fs::create_directories(card, ec);
            t.IsTrue(packMemoryCard(card, chunk, &error), "a formatted but empty card packs: " + error);
            const fs::path restored = root / "restored";
            t.IsTrue(unpackMemoryCard(chunk, restored, &error), "and unpacks: " + error);
            t.IsTrue(fs::is_directory(restored), "the folder is created even with nothing in it");
            t.Equals(countEntries(restored), size_t(0), "and stays empty");
            dropTree(root);
        });
    });
}
