// Sprint 10 Q4: the launcher's menu cues out of the player's own disc (launcher/menu_sounds.h). Two halves,
// each on what it can be tested on without a disc: the render on tests/fixtures/audio/hudui_block.bin +
// hudui_vag.bin (chunks 0 and 1 of the HUDUI bank, checked in for the mixer's own tests), and the ISO read on a
// synthetic image this file builds -- the bank's FileAttributes header and its two chunks laid at the r0001
// sector, and a primary volume descriptor at 16 for the key.
#include "MiniTest.h"
#include "launcher/menu_sounds.h"

#include <algorithm>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

namespace
{
    std::vector<uint8_t> readFixture(const char *name)
    {
        const char *roots[] = {"../../../../tests/fixtures/audio/", "tests/fixtures/audio/", "../../../tests/fixtures/audio/"};
        for (const char *root : roots)
        {
            const std::string path = std::string(root) + name;
            if (FILE *fp = std::fopen(path.c_str(), "rb"))
            {
                std::vector<uint8_t> bytes;
                uint8_t buf[4096];
                size_t n;
                while ((n = std::fread(buf, 1, sizeof(buf), fp)) > 0)
                    bytes.insert(bytes.end(), buf, buf + n);
                std::fclose(fp);
                return bytes;
            }
        }
        return {};
    }

    void put32(std::vector<uint8_t> &img, size_t at, uint32_t v)
    {
        img[at] = static_cast<uint8_t>(v);
        img[at + 1] = static_cast<uint8_t>(v >> 8);
        img[at + 2] = static_cast<uint8_t>(v >> 16);
        img[at + 3] = static_cast<uint8_t>(v >> 24);
    }

    // A sparse "disc": only the sectors the reader touches exist (a map of sector -> bytes), so the image
    // need not be 2 million sectors long. Sector 16 carries a PVD with a volume name; the bank lives at
    // menusounds::kHudUiSector as the game's loader lays it: the 32-byte FileAttributes header, chunk 0 right
    // after it, chunk 1 after that.
    struct SparseImage
    {
        std::vector<std::pair<uint64_t, std::vector<uint8_t>>> spans;   // (byte offset, bytes)

        void place(uint64_t offset, const std::vector<uint8_t> &bytes) { spans.emplace_back(offset, bytes); }

        iso9660::Reader reader() const
        {
            return [this](uint64_t offset, void *dst, size_t size)
            {
                std::memset(dst, 0, size);
                bool any = false;
                for (const auto &span : spans)
                {
                    const uint64_t lo = span.first, hi = span.first + span.second.size();
                    if (offset + size <= lo || offset >= hi)
                        continue;
                    const uint64_t from = std::max(lo, offset), to = std::min(hi, offset + size);
                    std::memcpy(static_cast<uint8_t *>(dst) + (from - offset), span.second.data() + (from - lo), static_cast<size_t>(to - from));
                    any = true;
                }
                return any;
            };
        }
    };

    std::vector<uint8_t> bankFile(const std::vector<uint8_t> &block, const std::vector<uint8_t> &vag, uint32_t type = 3u)
    {
        std::vector<uint8_t> out(32u, 0u);
        put32(out, 0, type);
        put32(out, 4, 2u);
        put32(out, 8, 32u);
        put32(out, 12, static_cast<uint32_t>(block.size()));
        put32(out, 16, static_cast<uint32_t>(32u + block.size()));
        put32(out, 20, static_cast<uint32_t>(vag.size()));
        out.insert(out.end(), block.begin(), block.end());
        out.insert(out.end(), vag.begin(), vag.end());
        return out;
    }

    std::vector<uint8_t> pvd(const char *volumeName)
    {
        std::vector<uint8_t> sector(2048u, 0u);
        sector[0] = 1;
        std::memcpy(sector.data() + 1, "CD001", 5);
        std::memcpy(sector.data() + 40, volumeName, std::strlen(volumeName));
        return sector;
    }
}

void register_menu_sounds_tests()
{
    MiniTest::Case("MenuSounds", [](TestCase &tc)
    {
        // The cue table is the bank's own names, and each cue renders to a short, audible, one-shot sound.
        tc.Run("the four cues render from the HUDUI fixtures through the game's own mixer: short, loud, and ending", [](TestCase &t)
        {
            using namespace launcher::menusounds;
            Bank bank;
            bank.block = readFixture("hudui_block.bin");
            bank.vag = readFixture("hudui_vag.bin");
            t.Equals(bank.block.size(), static_cast<size_t>(3472u), "fixture hudui_block.bin is present");
            t.Equals(bank.vag.size(), static_cast<size_t>(60928u), "fixture hudui_vag.bin is present");
            if (bank.block.empty() || bank.vag.empty())
                return;
            t.Equals(cueSound(Cue::Move), 3, ".SLIDE moves the focus");
            t.Equals(cueSound(Cue::Select), 8, ".METAL is the click the game plays on a HUD select");
            t.Equals(cueSound(Cue::Back), 1, ".BACK");
            t.Equals(cueSound(Cue::Refuse), 4, ".NEG refuses");
            for (int i = 0; i < static_cast<int>(Cue::Count); ++i)
            {
                const Cue cue = static_cast<Cue>(i);
                std::vector<int16_t> pcm;
                std::string why;
                t.IsTrue(renderCue(bank, cueSound(cue), pcm, why), std::string("renders: ") + cueFile(cue) + " " + why);
                const size_t frames = pcm.size() / 2u;
                // .BACK is 1344 samples at the bank's pitch -- under 40 ms -- so the floor is 10 ms, not a tenth of a second.
                t.IsTrue(frames >= 480u && frames < 3u * 48000u, std::string(cueFile(cue)) + " is between 10 ms and 3 s: " + std::to_string(frames) + " frames");
                int peak = 0;
                for (const int16_t s : pcm)
                    peak = std::max(peak, s < 0 ? -s : static_cast<int>(s));
                // The first run (2026-09-21) measured the four peaks at 1383 (.BACK, the quietest: vol 83 x tone 100)
                // to over 4000; and .NEG ends where its sample ends, not on a fade, so no "ends quiet" bar here.
                t.IsTrue(peak > 800, std::string(cueFile(cue)) + " has signal (peak " + std::to_string(peak) + ")");
            }
            std::vector<int16_t> none;
            std::string why;
            t.IsFalse(renderCue(bank, 99, none, why), "a sound the bank does not have renders nothing: " + why);
        });

        tc.Run("wavBytes is a 48 kHz stereo 16-bit RIFF with the sizes right", [](TestCase &t)
        {
            using namespace launcher::menusounds;
            const std::vector<int16_t> pcm = {1, -1, 2, -2, 3, -3};
            const std::vector<uint8_t> wav = wavBytes(pcm);
            t.Equals(wav.size(), static_cast<size_t>(44u + 12u), "44 bytes of header, then the samples");
            t.IsTrue(std::memcmp(wav.data(), "RIFF", 4) == 0 && std::memcmp(wav.data() + 8, "WAVEfmt ", 8) == 0, "RIFF/WAVE/fmt");
            t.Equals(static_cast<int>(wav[22]), 2, "two channels");
            t.Equals(static_cast<int>(wav[24] | (wav[25] << 8) | (wav[26] << 16)), 48000, "48 kHz");
            t.Equals(static_cast<int>(wav[34]), 16, "16 bits");
            t.Equals(static_cast<int>(wav[40]), 12, "the data chunk is the samples' bytes");
            t.Equals(static_cast<int>(wav[44]), 1, "and the first sample is there, little-endian");
            t.Equals(static_cast<int>(wav[46]), 0xFF, "-1 low byte");
        });

        tc.Run("readBank finds HUDUI at the r0001 sector of a synthetic image, and refuses anything else there", [](TestCase &t)
        {
            using namespace launcher::menusounds;
            const std::vector<uint8_t> block = readFixture("hudui_block.bin");
            const std::vector<uint8_t> vag = readFixture("hudui_vag.bin");
            if (block.empty() || vag.empty())
            {
                t.IsTrue(false, "the HUDUI fixtures are present");
                return;
            }
            SparseImage img;
            img.place(16u * 2048u, pvd("SOCOM2"));
            img.place(static_cast<uint64_t>(kHudUiSector) * 2048u, bankFile(block, vag));
            Bank bank;
            std::string why;
            t.IsTrue(readBank(img.reader(), kHudUiSector, bank, why), "the bank is read: " + why);
            t.Equals(bank.block.size(), block.size(), "chunk 0 whole");
            t.Equals(bank.vag.size(), vag.size(), "chunk 1 whole");
            t.IsTrue(bank.vag == vag, "and byte for byte");

            // Nothing there (a different disc): refused, with a reason.
            SparseImage empty;
            empty.place(16u * 2048u, pvd("OTHER"));
            t.IsFalse(readBank(empty.reader(), kHudUiSector, bank, why), "an image with no bank at the sector is refused");
            t.IsFalse(why.empty(), "with a reason: " + why);
            // A bank with another name: refused too -- the cues would be the wrong sounds.
            std::vector<uint8_t> renamed = block;
            const uint32_t names = static_cast<uint32_t>(renamed[0x38]) | (renamed[0x39] << 8);
            std::memcpy(renamed.data() + names, "OTHER\0\0\0", 8);
            SparseImage other;
            other.place(static_cast<uint64_t>(kHudUiSector) * 2048u, bankFile(renamed, vag));
            t.IsFalse(readBank(other.reader(), kHudUiSector, bank, why), "a bank that is not HUDUI is refused");
            t.IsTrue(why.find("OTHER") != std::string::npos, "and named: " + why);
            // A reader that cannot reach the sector.
            t.IsFalse(readBank(iso9660::Reader(), kHudUiSector, bank, why), "no reader, no bank");
        });

        tc.Run("the cache is keyed by the image's own bytes, lives under the home's cache/, and is built whole from the image", [](TestCase &t)
        {
            using namespace launcher::menusounds;
            const std::vector<uint8_t> block = readFixture("hudui_block.bin");
            const std::vector<uint8_t> vag = readFixture("hudui_vag.bin");
            if (block.empty() || vag.empty())
                return;
            SparseImage a, b;
            a.place(16u * 2048u, pvd("SOCOM2"));
            a.place(static_cast<uint64_t>(kHudUiSector) * 2048u, bankFile(block, vag));
            b.place(16u * 2048u, pvd("SOCOM2 COPY"));
            b.place(static_cast<uint64_t>(kHudUiSector) * 2048u, bankFile(block, vag));
            const std::string keyA = isoKey(a.reader()), keyB = isoKey(b.reader());
            t.Equals(keyA.size(), static_cast<size_t>(16u), "sixteen hex digits");
            t.IsTrue(keyA != keyB, "two images with different volume descriptors have different keys");
            t.Equals(isoKey(a.reader()), keyA, "and the key is stable");
            t.IsTrue(isoKey(iso9660::Reader()).empty(), "no image, no key");

            const std::filesystem::path home = std::filesystem::temp_directory_path() / "ps2x_menu_sounds_home";
            std::error_code ec;
            std::filesystem::remove_all(home, ec);
            const std::string dir = cacheDir(home.string(), keyA);
            t.IsTrue(dir.find("cache") != std::string::npos && dir.find("menu_sounds") != std::string::npos && dir.find(keyA) != std::string::npos,
                     "the directory names the cache and the key: " + dir);
            t.IsFalse(cacheComplete(dir), "nothing cached yet");
            std::string why;
            t.IsTrue(buildCache(a.reader(), dir, why), "the cache builds from the image: " + why);
            t.IsTrue(cacheComplete(dir), "and is complete: all four files");
            for (int i = 0; i < static_cast<int>(Cue::Count); ++i)
            {
                const std::filesystem::path file = std::filesystem::path(dir) / cueFile(static_cast<Cue>(i));
                t.IsTrue(std::filesystem::file_size(file, ec) > 44u + 1920u, std::string("a real file: ") + cueFile(static_cast<Cue>(i)));
            }
            // A file missing: not complete, so the launcher rebuilds rather than plays three of four.
            std::filesystem::remove(std::filesystem::path(dir) / cueFile(Cue::Back), ec);
            t.IsFalse(cacheComplete(dir), "a missing cue makes the set incomplete");
            // No bank in the image: nothing is written and the reason says so.
            SparseImage none;
            none.place(16u * 2048u, pvd("X"));
            const std::string dirNone = cacheDir(home.string(), "0000000000000000");
            t.IsFalse(buildCache(none.reader(), dirNone, why), "no bank, no cache: " + why);
            t.IsFalse(cacheComplete(dirNone), "and nothing is there to play");
            std::filesystem::remove_all(home, ec);
        });
    });
}
