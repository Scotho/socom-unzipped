// Task 8b: the launcher's logic -- the ISO 9660 lookup, SHA-256, config.json and the environment it becomes.
#include "MiniTest.h"
#include "launcher/iso9660.h"
#include "launcher/launcher_config.h"
#include "launcher/sha256.h"

#include <algorithm>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

namespace
{
    // A 20-sector image: PVD at 16, root directory at 18 with ".", ".." and SCUS_972.75;1 -> sector 19, 5 bytes.
    std::vector<uint8_t> syntheticImage(bool withPvd = true)
    {
        std::vector<uint8_t> img(20u * 2048u, 0u);
        uint8_t *pvd = img.data() + 16u * 2048u;
        pvd[0] = 1;
        if (withPvd)
            std::memcpy(pvd + 1, "CD001", 5);
        auto put32both = [](uint8_t *at, uint32_t v)
        {
            at[0] = static_cast<uint8_t>(v); at[1] = static_cast<uint8_t>(v >> 8); at[2] = static_cast<uint8_t>(v >> 16); at[3] = static_cast<uint8_t>(v >> 24);
            at[4] = static_cast<uint8_t>(v >> 24); at[5] = static_cast<uint8_t>(v >> 16); at[6] = static_cast<uint8_t>(v >> 8); at[7] = static_cast<uint8_t>(v);
        };
        auto record = [&](uint8_t *at, uint32_t extent, uint32_t size, const char *name)
        {
            const size_t nameLen = std::strlen(name);
            const uint8_t len = static_cast<uint8_t>((33 + nameLen + 1) & ~1u);
            at[0] = len;
            put32both(at + 2, extent);
            put32both(at + 10, size);
            at[25] = 0;   // flags: a file
            at[32] = static_cast<uint8_t>(nameLen);
            std::memcpy(at + 33, name, nameLen);
            return len;
        };
        // the root directory record inside the PVD (34 bytes at 156): extent 18, size 2048
        uint8_t *root = pvd + 156;
        root[0] = 34;
        put32both(root + 2, 18u);
        put32both(root + 10, 2048u);
        root[25] = 2;
        root[32] = 1;
        root[33] = 0;
        uint8_t *dir = img.data() + 18u * 2048u;
        size_t off = 0;
        off += record(dir + off, 18u, 2048u, "\0");
        off += record(dir + off, 18u, 2048u, "\1");
        off += record(dir + off, 19u, 5u, "SCUS_972.75;1");
        off += record(dir + off, 19u, 3u, "SYSTEM.CNF;1");
        std::memcpy(img.data() + 19u * 2048u, "hello", 5);
        return img;
    }

    iso9660::Reader memoryReader(const std::vector<uint8_t> &img)
    {
        return [&img](uint64_t offset, void *dst, size_t size)
        {
            if (offset + size > img.size())
                return false;
            std::memcpy(dst, img.data() + offset, size);
            return true;
        };
    }
}

void register_launcher_tests()
{
    MiniTest::Case("Launcher", [](TestCase &tc)
    {
        tc.Run("sha256: the FIPS vectors", [](TestCase &t)
        {
            t.Equals(sha256::hex(reinterpret_cast<const uint8_t *>("abc"), 3), std::string("ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"), "abc");
            t.Equals(sha256::hex(reinterpret_cast<const uint8_t *>(""), 0), std::string("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"), "empty");
            const char *two = "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq";
            t.Equals(sha256::hex(reinterpret_cast<const uint8_t *>(two), std::strlen(two)), std::string("248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1"), "two blocks");
            std::vector<uint8_t> million(1000000u, static_cast<uint8_t>('a'));
            t.Equals(sha256::hex(million.data(), million.size()), std::string("cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0"), "a million a's");
        });

        tc.Run("iso9660: the root directory lookup finds SCUS_972.75 (with its ;1), rejects the rest", [](TestCase &t)
        {
            const std::vector<uint8_t> img = syntheticImage();
            iso9660::FileEntry e;
            t.IsTrue(iso9660::findRootFile(memoryReader(img), "SCUS_972.75", e), "found");
            t.Equals(e.extent, 19u, "extent");
            t.Equals(e.size, 5u, "size");
            std::vector<uint8_t> bytes;
            t.IsTrue(iso9660::readFile(memoryReader(img), e, bytes) && bytes.size() == 5u && std::memcmp(bytes.data(), "hello", 5) == 0, "read");
            t.IsTrue(iso9660::findRootFile(memoryReader(img), "SYSTEM.CNF", e) && e.size == 3u, "another root file");
            t.IsTrue(!iso9660::findRootFile(memoryReader(img), "NOPE.BIN", e), "an absent name");
            const std::vector<uint8_t> noPvd = syntheticImage(false);
            t.IsTrue(!iso9660::findRootFile(memoryReader(noPvd), "SCUS_972.75", e), "no CD001: not an ISO");
            std::vector<uint8_t> shortImg(img.begin(), img.begin() + 17u * 2048u);
            t.IsTrue(!iso9660::findRootFile(memoryReader(shortImg), "SCUS_972.75", e), "a truncated image is refused, not read past its end");
            t.IsTrue(!iso9660::fileReader("no_such_file_here.iso"), "a missing file gives no reader");
        });

        tc.Run("the real disc's SCUS_972.75 hashes to the pinned r0001 digest (skipped without the ISO)", [](TestCase &t)
        {
            const char *candidates[] = {"../../../../game/SOCOM II - U.S. Navy SEALs (USA).iso", "game/SOCOM II - U.S. Navy SEALs (USA).iso"};
            iso9660::Reader read;
            for (const char *c : candidates)
            {
                read = iso9660::fileReader(c);
                if (read)
                    break;
            }
            if (!read)
                return;   // no disc on this machine
            iso9660::FileEntry e;
            t.IsTrue(iso9660::findRootFile(read, launcher::kSocom2ElfName, e), "SCUS_972.75 is in the root directory");
            t.Equals(e.size, 874792u, "its size");
            std::vector<uint8_t> bytes;
            t.IsTrue(iso9660::readFile(read, e, bytes), "read");
            t.Equals(sha256::hex(bytes.data(), bytes.size()), std::string(launcher::kSocom2R0001ElfSha256), "the r0001 digest");
        });

        tc.Run("config.json round-trips, tolerates unknown keys, and defaults on a malformed file", [](TestCase &t)
        {
            launcher::Config c;
            c.isoPath = "D:\\games\\socom2.iso";
            c.gsScale = 2;
            c.presentFilter = "integer";
            c.windowSize = "1280x896";
            c.mouseLook = true;
            c.mouseSensitivity = 1.5;
            c.server = "192.168.2.10";
            c.profile = "craig";
            c.secondInstance = true;
            const std::string json = launcher::toJson(c);
            t.IsTrue(json.find("\"isoPath\"") != std::string::npos && json.find("D:\\\\games\\\\socom2.iso") != std::string::npos, "the path is escaped");
            launcher::Config back;
            t.IsTrue(launcher::fromJson(json, back), "parses its own output");
            t.IsTrue(back.isoPath == c.isoPath && back.gsScale == 2 && back.presentFilter == "integer" && back.windowSize == "1280x896" && back.mouseLook && back.mouseSensitivity == 1.5 && back.server == c.server && back.profile == "craig" && back.secondInstance, "every field survives");
            launcher::Config partial;
            t.IsTrue(launcher::fromJson("{\"gsScale\": 3, \"future\": [1,2,3], \"profile\": \"x\"}", partial), "unknown keys are ignored");
            t.IsTrue(partial.gsScale == 3 && partial.profile == "x" && partial.windowSize == "640x448" && partial.server == "127.0.0.1", "missing keys keep their defaults");
            launcher::Config broken;
            broken.gsScale = 2;
            t.IsTrue(!launcher::fromJson("{\"gsScale\": ", broken), "malformed JSON is refused");
            t.Equals(broken.gsScale, 1, "... and the config is the defaults");
        });

        tc.Run("the environment: the knobs the runtime reads, the pad always, the second instance's shift and key", [](TestCase &t)
        {
            launcher::Config c;
            std::vector<std::string> env = launcher::environmentFor(c);
            auto has = [&](const std::string &kv) { return std::find(env.begin(), env.end(), kv) != env.end(); };
            auto hasKey = [&](const std::string &k) { return std::any_of(env.begin(), env.end(), [&](const std::string &e) { return e.rfind(k + "=", 0) == 0; }); };
            t.IsTrue(has("PS2X_SOCOM2_PAD=1"), "the SOCOM input path is always on");
            t.IsTrue(has("PS2X_GS_SCALE=1"), "native scale");
            t.IsTrue(has("PS2X_PRESENT_FILTER=linear"), "the filter");
            t.IsTrue(has("PS2X_WINDOW_SIZE=640x448"), "the window size");
            t.IsTrue(has("PS2X_SOCOM2_SERVER=127.0.0.1"), "the server");
            t.IsTrue(has("PS2X_MC_DIR=cards/player"), "the profile's card directory");
            t.IsTrue(!hasKey("PS2X_SOCOM2_MOUSE") && !hasKey("PS2X_SOCOM2_MOUSE_SENS"), "mouse look off: no mouse knobs");
            t.IsTrue(!hasKey("PS2X_SOCOM2_UDP_SHIFT") && !hasKey("PS2X_SOCOM2_RSA_KEY"), "first instance: no shift, no second key");
            c.gsScale = 2;
            c.mouseLook = true;
            c.mouseSensitivity = 0.75;
            c.secondInstance = true;
            c.profile = "craig";
            c.windowSize = "fullscreen";
            env = launcher::environmentFor(c);
            t.IsTrue(has("PS2X_GS_SCALE=2") && has("PS2X_SOCOM2_MOUSE=1") && has("PS2X_SOCOM2_MOUSE_SENS=0.75") && has("PS2X_WINDOW_SIZE=fullscreen"), "scale, mouse, sensitivity, fullscreen");
            t.IsTrue(has("PS2X_SOCOM2_UDP_SHIFT=2") && has("PS2X_SOCOM2_RSA_KEY=b") && has("PS2X_MC_DIR=cards/craig_b"), "the second instance: shift 2, key b, its own cards");
        });
    });
}
