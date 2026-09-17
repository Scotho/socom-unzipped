#pragma once
// ISO 9660 as far as the launcher needs it: find a file in the root directory of a disc image (the primary
// volume descriptor at sector 16, its root directory record, the directory's entries) and read it.
#include <cstddef>
#include <cstdint>
#include <functional>
#include <string>
#include <vector>

namespace iso9660
{
    // Reads `size` bytes at byte `offset` of the image into `dst`; false if the range is not readable.
    using Reader = std::function<bool(uint64_t offset, void *dst, size_t size)>;

    struct FileEntry
    {
        uint32_t extent = 0;   // first sector
        uint32_t size = 0;     // bytes
    };

    constexpr uint32_t kSectorBytes = 2048;

    // Looks `name` up in the root directory ("SCUS_972.75" matches "SCUS_972.75;1"). False when the image has no
    // primary volume descriptor, the directory is unreadable, or the name is absent.
    bool findRootFile(const Reader &read, const std::string &name, FileEntry &out);

    // The file's bytes (bounded by maxBytes).
    bool readFile(const Reader &read, const FileEntry &entry, std::vector<uint8_t> &out, size_t maxBytes = 64u << 20);

    // A Reader over a file on disk (64-bit offsets).
    Reader fileReader(const std::string &path);
}
