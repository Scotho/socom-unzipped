// Sprint 9 Goal 1: the checks the runner makes before it opens a window, each driven through the failing
// condition on a real temporary directory, each asserting the code and the sentence.
#include "MiniTest.h"
#include "ps2x/exit_codes.h"
#include "ps2x/preflight.h"

#include <chrono>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

namespace
{
    namespace fs = std::filesystem;

    // <temp>/ps2x_preflight_<ticks>_<n>/outer/home -- two levels, so "one folder up" is ours too.
    fs::path makeHome()
    {
        static int counter = 0;
        const auto ticks = std::chrono::steady_clock::now().time_since_epoch().count();
        const fs::path root = fs::temp_directory_path() / ("ps2x_preflight_" + std::to_string(ticks) + "_" + std::to_string(counter++));
        std::error_code ec;
        fs::create_directories(root / "outer" / "home", ec);
        return root / "outer" / "home";
    }

    void removeHome(const fs::path &home)
    {
        std::error_code ec;
        fs::remove_all(home.parent_path().parent_path(), ec);
    }

    void writeBytes(const fs::path &p, const std::vector<uint8_t> &bytes)
    {
        std::ofstream out(p, std::ios::binary | std::ios::trunc);
        out.write(reinterpret_cast<const char *>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
    }

    void writeText(const fs::path &p, const std::string &text)
    {
        writeBytes(p, std::vector<uint8_t>(text.begin(), text.end()));
    }

    // A 20-sector ISO 9660 image: PVD at 16, root directory at 18, one file at 19 holding "hello".
    // `fileName` is the root-directory name of that file ("SCUS_972.75;1" for a SOCOM-shaped disc).
    std::vector<uint8_t> isoWith(const char *fileName)
    {
        std::vector<uint8_t> img(20u * 2048u, 0u);
        uint8_t *pvd = img.data() + 16u * 2048u;
        pvd[0] = 1;
        std::memcpy(pvd + 1, "CD001", 5);
        auto put32both = [](uint8_t *at, uint32_t v)
        {
            at[0] = static_cast<uint8_t>(v); at[1] = static_cast<uint8_t>(v >> 8); at[2] = static_cast<uint8_t>(v >> 16); at[3] = static_cast<uint8_t>(v >> 24);
            at[4] = static_cast<uint8_t>(v >> 24); at[5] = static_cast<uint8_t>(v >> 16); at[6] = static_cast<uint8_t>(v >> 8); at[7] = static_cast<uint8_t>(v);
        };
        auto record = [&](uint8_t *at, uint32_t extent, uint32_t size, const char *name, size_t nameLen, uint8_t flags)
        {
            const uint8_t len = static_cast<uint8_t>((33 + nameLen + 1) & ~static_cast<size_t>(1));
            at[0] = len;
            put32both(at + 2, extent);
            put32both(at + 10, size);
            at[25] = flags;
            at[32] = static_cast<uint8_t>(nameLen);
            std::memcpy(at + 33, name, nameLen);
            return len;
        };
        uint8_t *root = pvd + 156;
        root[0] = 34;
        put32both(root + 2, 18u);
        put32both(root + 10, 2048u);
        root[25] = 2;
        root[32] = 1;
        uint8_t *dir = img.data() + 18u * 2048u;
        size_t off = 0;
        off += record(dir + off, 18u, 2048u, "\0", 1, 2);
        off += record(dir + off, 18u, 2048u, "\1", 1, 2);
        off += record(dir + off, 19u, 5u, fileName, std::strlen(fileName), 0);
        std::memcpy(img.data() + 19u * 2048u, "hello", 5);
        return img;
    }

    const char *kSha256OfHello = "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824";

    std::string sentenceOf(int code)
    {
        const ExitCodes::Entry *e = ExitCodes::find(code);
        return e ? std::string(e->sentence) : std::string();
    }
}

void register_preflight_tests()
{
    MiniTest::Case("Preflight", [](TestCase &tc)
    {
        tc.Run("68: no socom2_game.elf in the folder", [](TestCase &t)
        {
            const fs::path home = makeHome();
            Preflight::Input in;
            in.elfPath = home / "socom2_game.elf";
            in.cardDir = home / "cards" / "player";
            const Preflight::Result r = Preflight::run(in);
            t.Equals(r.code, ExitCodes::kElfMissing, "the ELF is checked first");
            t.Equals(r.code, 68, "and that is 68");
            t.IsTrue(r.detail.find("socom2_game.elf") != std::string::npos, "the detail names the path it looked at");
            t.IsTrue(Preflight::logLine(r).find("[preflight] exit 68 elf-missing: " + sentenceOf(68)) == 0, "the log line carries the code, the slug and the sentence");
            removeHome(home);
        });

        tc.Run("72: the memory-card folder cannot be created or written", [](TestCase &t)
        {
            const fs::path home = makeHome();
            writeText(home / "socom2_game.elf", "elf");
            writeText(home / "cards", "a file where the cards folder should be");   // portable: no chmod on Windows
            Preflight::Input in;
            in.elfPath = home / "socom2_game.elf";
            in.cardDir = home / "cards" / "player";
            const Preflight::Result r = Preflight::run(in);
            t.Equals(r.code, 72, "a card folder that cannot exist is 72, before the disc is looked for");
            t.IsTrue(Preflight::logLine(r).find(sentenceOf(72)) != std::string::npos, "with its sentence");
            std::string why;
            t.IsTrue(Preflight::directoryWritable(home / "saves" / "deep", why), "a folder that can be created is created and is writable");
            t.IsTrue(fs::is_directory(home / "saves" / "deep"), "it exists afterwards");
            t.IsTrue(!fs::exists(home / "saves" / "deep" / ".ps2x_write_probe"), "and the probe file is gone");
            removeHome(home);
        });

        tc.Run("66: no disc beside the ELF, none one folder up, and a PS2X_CD_IMAGE that is not there", [](TestCase &t)
        {
            const fs::path home = makeHome();
            writeText(home / "socom2_game.elf", "elf");
            Preflight::Input in;
            in.elfPath = home / "socom2_game.elf";
            in.cardDir = home / "cards" / "player";
            Preflight::Result r = Preflight::run(in);
            t.Equals(r.code, 66, "nothing to mount");
            t.IsTrue(Preflight::logLine(r).find(sentenceOf(66)) != std::string::npos, "with its sentence");
            in.cdImageEnv = (home / "gone.iso").string();
            r = Preflight::run(in);
            t.Equals(r.code, 66, "PS2X_CD_IMAGE naming a missing file is the same code");
            t.IsTrue(r.detail.find("gone.iso") != std::string::npos, "and the detail names the file");
            removeHome(home);
        });

        tc.Run("findDisc mirrors configureCdImage: the environment first, then *.iso beside the ELF, then one folder up", [](TestCase &t)
        {
            const fs::path home = makeHome();
            writeText(home / "socom2_game.elf", "elf");
            t.IsTrue(Preflight::findDisc(home / "socom2_game.elf", "").empty(), "nothing yet");
            writeText(home.parent_path() / "Game.ISO", "x");
            t.Equals(Preflight::findDisc(home / "socom2_game.elf", "").filename().string(), std::string("Game.ISO"), "one folder up, any case of .iso");
            writeText(home / "near.iso", "x");
            t.Equals(Preflight::findDisc(home / "socom2_game.elf", "").filename().string(), std::string("near.iso"), "beside the ELF wins over one folder up");
            t.Equals(Preflight::findDisc(home / "socom2_game.elf", "D:/elsewhere.iso").generic_string(), std::string("D:/elsewhere.iso"), "PS2X_CD_IMAGE wins over both, exists or not");
            removeHome(home);
        });

        tc.Run("67: a disc whose SCUS_972.75 is not r0001's, and a disc with no SCUS_972.75 at all", [](TestCase &t)
        {
            const fs::path home = makeHome();
            writeText(home / "socom2_game.elf", "elf");
            writeBytes(home / "disc.iso", isoWith("SCUS_972.75;1"));
            Preflight::Input in;
            in.elfPath = home / "socom2_game.elf";
            in.cardDir = home / "cards" / "player";
            Preflight::Result r = Preflight::run(in);   // the pinned r0001 digest: "hello" is not it
            t.Equals(r.code, 67, "the executable on the disc does not hash to the pinned digest");
            t.IsTrue(Preflight::logLine(r).find(sentenceOf(67)) != std::string::npos, "with its sentence");
            writeBytes(home / "disc.iso", isoWith("SLUS_200.62;1"));
            r = Preflight::run(in);
            t.Equals(r.code, 67, "another game's disc is the same code");
            t.IsTrue(r.detail.find("SCUS_972.75") != std::string::npos, "and the detail says what was not found");
            writeText(home / "disc.iso", "not an iso at all");
            r = Preflight::run(in);
            t.Equals(r.code, 67, "a file that is not a disc image is 'not that disc', not 'not found'");
            removeHome(home);
        });

        tc.Run("0: every check passes, and a non-SOCOM ELF skips the disc", [](TestCase &t)
        {
            const fs::path home = makeHome();
            writeText(home / "socom2_game.elf", "elf");
            writeBytes(home / "disc.iso", isoWith("SCUS_972.75;1"));
            Preflight::Input in;
            in.elfPath = home / "socom2_game.elf";
            in.cardDir = home / "cards" / "player";
            in.expectedElfSha256 = kSha256OfHello;   // the synthetic disc's own digest stands in for r0001's
            Preflight::Result r = Preflight::run(in);
            t.Equals(r.code, 0, "ELF present, card folder writable, disc found, digest matches");
            t.Equals(r.disc.filename().string(), std::string("disc.iso"), "and it says which disc it checked");
            t.IsTrue(fs::is_directory(home / "cards" / "player"), "the card folder now exists");
            fs::remove(home / "disc.iso");
            in.checkDisc = false;
            r = Preflight::run(in);
            t.Equals(r.code, 0, "checkDisc=false (another game's ELF): no disc is no error");
            removeHome(home);
        });
    });
}
