// Sprint 9 Goal 1: the diagnostics zip's writer. STORE only; checked here byte by byte against the
// format (APPNOTE 4.3.7, 4.3.12, 4.3.16), and in tools_py/tests/test_diagnostics_zip.py by Python's zipfile.
#include "MiniTest.h"
#include "ps2x/zip_store.h"

#include <cstdint>
#include <string>
#include <vector>

namespace
{
    uint16_t rd16(const std::string &z, size_t at)
    {
        return static_cast<uint16_t>(static_cast<uint8_t>(z[at]) | (static_cast<uint8_t>(z[at + 1]) << 8));
    }
    uint32_t rd32(const std::string &z, size_t at)
    {
        return static_cast<uint32_t>(rd16(z, at)) | (static_cast<uint32_t>(rd16(z, at + 2)) << 16);
    }
    uint32_t crcOf(const std::string &s)
    {
        return ZipStore::crc32(reinterpret_cast<const uint8_t *>(s.data()), s.size());
    }
}

void register_zip_store_tests()
{
    MiniTest::Case("ZipStore", [](TestCase &tc)
    {
        tc.Run("crc32: the check value, the empty string, and chaining", [](TestCase &t)
        {
            t.Equals(crcOf("123456789"), 0xCBF43926u, "the CRC-32/ISO-HDLC check value");
            t.Equals(crcOf(""), 0u, "nothing hashes to 0");
            t.Equals(crcOf("hello"), 0x3610A686u, "hello");
            const std::string a = "1234", b = "56789";
            const uint32_t first = ZipStore::crc32(reinterpret_cast<const uint8_t *>(a.data()), a.size());
            t.Equals(ZipStore::crc32(reinterpret_cast<const uint8_t *>(b.data()), b.size(), first), 0xCBF43926u, "two halves chain to the whole");
        });

        tc.Run("names: forward slashes, relative, no way out of the folder", [](TestCase &t)
        {
            t.IsTrue(ZipStore::nameAllowed("config.json"), "a file");
            t.IsTrue(ZipStore::nameAllowed("log/run_20260919_084912.log"), "a file in a folder");
            t.IsFalse(ZipStore::nameAllowed(""), "empty");
            t.IsFalse(ZipStore::nameAllowed("/etc/passwd"), "absolute");
            t.IsFalse(ZipStore::nameAllowed("..\\x"), "a backslash");
            t.IsFalse(ZipStore::nameAllowed("a/../b"), "a parent segment");
            t.IsFalse(ZipStore::nameAllowed("a//b"), "an empty segment");
            t.IsFalse(ZipStore::nameAllowed("C:/x"), "a drive");
            t.IsTrue(ZipStore::build(std::vector<ZipStore::Entry>{ZipStore::Entry{"../x", "data"}}).empty(), "build refuses the whole archive rather than write a bad name");
        });

        tc.Run("the DOS date and time out of the launcher's stamp", [](TestCase &t)
        {
            uint16_t date = 1, time = 1;
            t.IsTrue(ZipStore::dosDateTime("20260919_084912", date, time), "a stamp parses");
            t.Equals(date, static_cast<uint16_t>(((2026 - 1980) << 9) | (9 << 5) | 19), "years since 1980, month, day");
            t.Equals(time, static_cast<uint16_t>((8 << 11) | (49 << 5) | (12 / 2)), "hours, minutes, two-second units");
            date = 7; time = 9;
            t.IsFalse(ZipStore::dosDateTime("2026-09-19", date, time), "anything else does not");
            t.IsFalse(ZipStore::dosDateTime("20261319_084912", date, time), "nor a thirteenth month");
            t.Equals(date, static_cast<uint16_t>(7), "and the outputs are left alone");
        });

        tc.Run("an empty archive is the 22-byte end record", [](TestCase &t)
        {
            const std::string z = ZipStore::build({});
            t.Equals(z.size(), static_cast<size_t>(22), "just the end of central directory");
            t.Equals(rd32(z, 0), 0x06054b50u, "its signature");
            t.Equals(rd16(z, 10), static_cast<uint16_t>(0), "no entries");
        });

        tc.Run("three stored entries: local headers, data, central directory, end record -- every field", [](TestCase &t)
        {
            const std::string bin("\0\1\2", 3);
            const std::vector<ZipStore::Entry> in = {{"a.txt", "hello"}, {"dir/b.bin", bin}, {"empty.txt", ""}};
            const std::string z = ZipStore::build(in, 0x5D33, 0x4626);
            // locals: (30+5+5) + (30+9+3) + (30+9+0) = 121; central: (46+5) + (46+9) + (46+9) = 161; end: 22
            t.Equals(z.size(), static_cast<size_t>(304), "the size is exactly headers + names + data");
            const size_t eocd = z.size() - 22;
            t.Equals(rd32(z, eocd), 0x06054b50u, "end record signature");
            t.Equals(rd16(z, eocd + 8), static_cast<uint16_t>(3), "entries on this disk");
            t.Equals(rd16(z, eocd + 10), static_cast<uint16_t>(3), "entries in total");
            t.Equals(rd32(z, eocd + 12), 161u, "central directory size");
            t.Equals(rd32(z, eocd + 16), 121u, "central directory offset");
            t.Equals(rd16(z, eocd + 20), static_cast<uint16_t>(0), "no comment");

            const uint32_t expectedOffset[3] = {0u, 40u, 82u};
            size_t cd = 121;
            for (size_t i = 0; i < in.size(); ++i)
            {
                const std::string &name = in[i].name;
                const std::string &data = in[i].data;
                const std::string which = "entry " + std::to_string(i) + ": ";
                t.Equals(rd32(z, cd), 0x02014b50u, which + "central signature");
                t.Equals(rd16(z, cd + 6), static_cast<uint16_t>(10), which + "version needed 1.0 (stored, no folders-as-entries)");
                t.Equals(rd16(z, cd + 8), static_cast<uint16_t>(0x0800), which + "flag bit 11: the name is UTF-8");
                t.Equals(rd16(z, cd + 10), static_cast<uint16_t>(0), which + "method 0: stored");
                t.Equals(rd16(z, cd + 12), static_cast<uint16_t>(0x4626), which + "time");
                t.Equals(rd16(z, cd + 14), static_cast<uint16_t>(0x5D33), which + "date");
                t.Equals(rd32(z, cd + 16), crcOf(data), which + "crc");
                t.Equals(rd32(z, cd + 20), static_cast<uint32_t>(data.size()), which + "compressed size == size");
                t.Equals(rd32(z, cd + 24), static_cast<uint32_t>(data.size()), which + "uncompressed size");
                t.Equals(rd16(z, cd + 28), static_cast<uint16_t>(name.size()), which + "name length");
                t.Equals(rd16(z, cd + 30), static_cast<uint16_t>(0), which + "no extra field");
                t.Equals(rd32(z, cd + 42), expectedOffset[i], which + "local header offset");
                t.Equals(z.substr(cd + 46, name.size()), name, which + "central name");

                const size_t lh = expectedOffset[i];
                t.Equals(rd32(z, lh), 0x04034b50u, which + "local signature");
                t.Equals(rd16(z, lh + 6), static_cast<uint16_t>(0x0800), which + "local flags");
                t.Equals(rd16(z, lh + 8), static_cast<uint16_t>(0), which + "local method");
                t.Equals(rd32(z, lh + 14), crcOf(data), which + "local crc (no data descriptor)");
                t.Equals(rd32(z, lh + 18), static_cast<uint32_t>(data.size()), which + "local compressed size");
                t.Equals(rd32(z, lh + 22), static_cast<uint32_t>(data.size()), which + "local size");
                t.Equals(rd16(z, lh + 26), static_cast<uint16_t>(name.size()), which + "local name length");
                t.Equals(rd16(z, lh + 28), static_cast<uint16_t>(0), which + "local extra length");
                t.Equals(z.substr(lh + 30, name.size()), name, which + "local name");
                t.Equals(z.substr(lh + 30 + name.size(), data.size()), data, which + "the bytes, as given");
                cd += 46 + name.size();
            }
            t.Equals(cd, eocd, "the central directory ends where the end record starts");
        });
    });
}
