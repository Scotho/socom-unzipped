#include "ps2x/zip_store.h"

#include <array>

namespace ZipStore
{
    namespace
    {
        void put16(std::string &out, uint32_t v)
        {
            out.push_back(static_cast<char>(v & 0xFFu));
            out.push_back(static_cast<char>((v >> 8) & 0xFFu));
        }

        void put32(std::string &out, uint32_t v)
        {
            put16(out, v & 0xFFFFu);
            put16(out, (v >> 16) & 0xFFFFu);
        }

        bool digits(const std::string &s, size_t at, size_t count, int &value)
        {
            value = 0;
            for (size_t i = at; i < at + count; ++i)
            {
                if (s[i] < '0' || s[i] > '9')
                    return false;
                value = value * 10 + (s[i] - '0');
            }
            return true;
        }

        constexpr uint64_t kZip32Limit = 0xFFFFFFFEull;
    }

    uint32_t crc32(const uint8_t *data, size_t size, uint32_t crc)
    {
        static const std::array<uint32_t, 256> table = []
        {
            std::array<uint32_t, 256> values{};
            for (uint32_t i = 0; i < 256u; ++i)
            {
                uint32_t v = i;
                for (int bit = 0; bit < 8; ++bit)
                    v = (v & 1u) ? (0xEDB88320u ^ (v >> 1)) : (v >> 1);
                values[i] = v;
            }
            return values;
        }();
        crc = ~crc;
        for (size_t i = 0; i < size; ++i)
            crc = table[(crc ^ data[i]) & 0xFFu] ^ (crc >> 8);
        return ~crc;
    }

    bool nameAllowed(const std::string &name)
    {
        if (name.empty() || name.size() > 0xFFFFu || name.front() == '/')
            return false;
        if (name.find('\\') != std::string::npos || name.find(':') != std::string::npos)
            return false;
        size_t start = 0;
        while (start <= name.size())
        {
            size_t end = name.find('/', start);
            if (end == std::string::npos)
                end = name.size();
            const std::string segment = name.substr(start, end - start);
            if (segment.empty() || segment == "." || segment == "..")
                return false;
            start = end + 1;
        }
        return true;
    }

    bool dosDateTime(const std::string &stamp, uint16_t &date, uint16_t &time)
    {
        int y, mo, d, h, mi, s;
        if (stamp.size() != 15 || stamp[8] != '_')
            return false;
        if (!digits(stamp, 0, 4, y) || !digits(stamp, 4, 2, mo) || !digits(stamp, 6, 2, d) ||
            !digits(stamp, 9, 2, h) || !digits(stamp, 11, 2, mi) || !digits(stamp, 13, 2, s))
            return false;
        if (y < 1980 || y > 2107 || mo < 1 || mo > 12 || d < 1 || d > 31 || h > 23 || mi > 59 || s > 59)
            return false;
        date = static_cast<uint16_t>(((y - 1980) << 9) | (mo << 5) | d);
        time = static_cast<uint16_t>((h << 11) | (mi << 5) | (s / 2));
        return true;
    }

    std::string build(const std::vector<Entry> &entries, uint16_t dosDate, uint16_t dosTime)
    {
        if (entries.size() > 0xFFFEu)
            return {};
        std::string out;
        std::string central;
        for (const Entry &e : entries)
        {
            if (!nameAllowed(e.name) || e.data.size() > kZip32Limit)
                return {};
            if (static_cast<uint64_t>(out.size()) + 30u + e.name.size() + e.data.size() > kZip32Limit)
                return {};
            const uint32_t crc = crc32(reinterpret_cast<const uint8_t *>(e.data.data()), e.data.size());
            const uint32_t size = static_cast<uint32_t>(e.data.size());
            const uint32_t offset = static_cast<uint32_t>(out.size());

            put32(out, 0x04034b50u);   // local file header
            put16(out, 10);            // version needed: 1.0
            put16(out, 0x0800);        // bit 11: UTF-8 name
            put16(out, 0);             // method: stored
            put16(out, dosTime);
            put16(out, dosDate);
            put32(out, crc);
            put32(out, size);          // compressed
            put32(out, size);          // uncompressed
            put16(out, static_cast<uint32_t>(e.name.size()));
            put16(out, 0);             // extra
            out += e.name;
            out += e.data;

            put32(central, 0x02014b50u);   // central directory header
            put16(central, 20);            // made by: 2.0, MS-DOS attribute compatibility
            put16(central, 10);
            put16(central, 0x0800);
            put16(central, 0);
            put16(central, dosTime);
            put16(central, dosDate);
            put32(central, crc);
            put32(central, size);
            put32(central, size);
            put16(central, static_cast<uint32_t>(e.name.size()));
            put16(central, 0);             // extra
            put16(central, 0);             // comment
            put16(central, 0);             // disk number
            put16(central, 0);             // internal attributes
            put32(central, 0);             // external attributes
            put32(central, offset);
            central += e.name;
        }
        if (static_cast<uint64_t>(out.size()) + central.size() + 22u > kZip32Limit)
            return {};
        const uint32_t cdOffset = static_cast<uint32_t>(out.size());
        const uint32_t cdSize = static_cast<uint32_t>(central.size());
        out += central;
        put32(out, 0x06054b50u);   // end of central directory
        put16(out, 0);
        put16(out, 0);
        put16(out, static_cast<uint32_t>(entries.size()));
        put16(out, static_cast<uint32_t>(entries.size()));
        put32(out, cdSize);
        put32(out, cdOffset);
        put16(out, 0);             // comment
        return out;
    }
}
