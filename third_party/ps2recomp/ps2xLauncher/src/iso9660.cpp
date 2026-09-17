#include "launcher/iso9660.h"

#include <cstdio>
#include <cstring>
#include <memory>

// ISO 9660 (ECMA-119), the little the launcher needs: the primary volume descriptor at sector 16 ("CD001" after
// the type byte), its root directory record at offset 156 (extent and size as both-endian 32-bit words at 2 and
// 10), and the directory's records (length at 0, extent at 2, size at 10, name length at 32, name at 33; a zero
// length means the rest of the sector is padding). Names carry ";1"; the caller asks by the bare name.
namespace iso9660
{
    namespace
    {
        uint32_t le32(const uint8_t *p)
        {
            return static_cast<uint32_t>(p[0]) | (static_cast<uint32_t>(p[1]) << 8) | (static_cast<uint32_t>(p[2]) << 16) | (static_cast<uint32_t>(p[3]) << 24);
        }

        bool sameName(const uint8_t *name, size_t len, const std::string &wanted)
        {
            // the version suffix ";1" and a trailing '.' do not count
            size_t n = len;
            for (size_t i = 0; i < len; ++i)
                if (name[i] == ';')
                {
                    n = i;
                    break;
                }
            if (n > 0 && name[n - 1] == '.')
                --n;
            if (n != wanted.size())
                return false;
            for (size_t i = 0; i < n; ++i)
            {
                const char a = static_cast<char>(name[i]);
                const char b = wanted[i];
                const char la = (a >= 'a' && a <= 'z') ? static_cast<char>(a - 32) : a;
                const char lb = (b >= 'a' && b <= 'z') ? static_cast<char>(b - 32) : b;
                if (la != lb)
                    return false;
            }
            return true;
        }
    }

    bool findRootFile(const Reader &read, const std::string &name, FileEntry &out)
    {
        if (!read)
            return false;
        uint8_t pvd[kSectorBytes];
        if (!read(16ull * kSectorBytes, pvd, sizeof(pvd)))
            return false;
        if (pvd[0] != 1 || std::memcmp(pvd + 1, "CD001", 5) != 0)
            return false;
        const uint8_t *root = pvd + 156;
        const uint32_t dirExtent = le32(root + 2);
        const uint32_t dirSize = le32(root + 10);
        if (dirSize == 0 || dirSize > (4u << 20))
            return false;
        std::vector<uint8_t> dir(dirSize);
        if (!read(static_cast<uint64_t>(dirExtent) * kSectorBytes, dir.data(), dir.size()))
            return false;
        size_t pos = 0;
        while (pos + 33 <= dir.size())
        {
            const uint8_t len = dir[pos];
            if (len == 0)
            {
                pos = (pos / kSectorBytes + 1) * kSectorBytes;   // the rest of this sector is padding
                continue;
            }
            if (pos + len > dir.size() || len < 33)
                return false;
            const uint8_t nameLen = dir[pos + 32];
            if (33u + nameLen > len)
                return false;
            const bool isDir = (dir[pos + 25] & 0x02) != 0;
            if (!isDir && sameName(dir.data() + pos + 33, nameLen, name))
            {
                out.extent = le32(dir.data() + pos + 2);
                out.size = le32(dir.data() + pos + 10);
                return true;
            }
            pos += len;
        }
        return false;
    }

    bool readFile(const Reader &read, const FileEntry &entry, std::vector<uint8_t> &out, size_t maxBytes)
    {
        if (!read || entry.size > maxBytes)
            return false;
        out.resize(entry.size);
        if (entry.size == 0)
            return true;
        return read(static_cast<uint64_t>(entry.extent) * kSectorBytes, out.data(), out.size());
    }

    Reader fileReader(const std::string &path)
    {
        FILE *fp = std::fopen(path.c_str(), "rb");
        if (!fp)
            return {};
        std::shared_ptr<FILE> file(fp, [](FILE *f) { if (f) std::fclose(f); });
        return [file](uint64_t offset, void *dst, size_t size)
        {
#ifdef _WIN32
            if (_fseeki64(file.get(), static_cast<long long>(offset), SEEK_SET) != 0)
                return false;
#else
            if (fseeko(file.get(), static_cast<off_t>(offset), SEEK_SET) != 0)
                return false;
#endif
            return std::fread(dst, 1, size, file.get()) == size;
        };
    }
}
