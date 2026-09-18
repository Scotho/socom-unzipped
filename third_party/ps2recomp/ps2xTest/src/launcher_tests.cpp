// Task 8b: the launcher's logic -- the ISO 9660 lookup, SHA-256, config.json and the environment it becomes.
#include "MiniTest.h"
#include "launcher/iso9660.h"
#include "launcher/launcher_config.h"
#include "launcher/mic_devices.h"
#include "launcher/sha256.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <iostream>
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

        tc.Run("the controller pick and the dead zone round-trip and reach the environment", [](TestCase &t)
        {
            launcher::Config c;
            t.Equals(c.gamepadIndex, -1, "no pick by default: the first available pad, as before this task");
            t.IsTrue(c.padDeadZone > 0.1499 && c.padDeadZone < 0.1501, "the default dead zone is the runtime's 0.15");
            std::vector<std::string> env = launcher::environmentFor(c);
            auto has = [](const std::vector<std::string> &e, const std::string &kv) { return std::find(e.begin(), e.end(), kv) != e.end(); };
            auto hasKey = [](const std::vector<std::string> &e, const std::string &k) { return std::any_of(e.begin(), e.end(), [&](const std::string &s) { return s.rfind(k + "=", 0) == 0; }); };
            t.IsTrue(!hasKey(env, "PS2X_HOST_GAMEPAD_INDEX"), "no pick: the runtime is not told one, so it keeps its own rule");
            t.IsTrue(has(env, "PS2X_PAD_DEADZONE=0.15"), "the dead zone always ships, so what the player tuned is what the game gets");
            c.gamepadIndex = 2;
            c.padDeadZone = 0.3;
            env = launcher::environmentFor(c);
            t.IsTrue(has(env, "PS2X_HOST_GAMEPAD_INDEX=2"), "the picked slot");
            t.IsTrue(has(env, "PS2X_PAD_DEADZONE=0.3"), "the tuned dead zone");
            launcher::Config back;
            t.IsTrue(launcher::fromJson(launcher::toJson(c), back), "parses its own output");
            t.Equals(back.gamepadIndex, 2, "the pick survives the round trip");
            t.IsTrue(back.padDeadZone > 0.2999 && back.padDeadZone < 0.3001, "and so does the dead zone");
            launcher::Config partial;
            t.IsTrue(launcher::fromJson("{\"gsScale\": 1}", partial), "an older config.json parses");
            t.Equals(partial.gamepadIndex, -1, "a config written before this task keeps the old behaviour");
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
            t.IsTrue(partial.gsScale == 3 && partial.profile == "x" && partial.windowSize == "1280x896" && partial.server == "127.0.0.1", "missing keys keep their defaults");
            t.Equals(launcher::Config{}.windowSize, std::string("1280x896"), "the launcher's default is 2x");
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
            t.IsTrue(has("PS2X_WINDOW_SIZE=1280x896"), "the window size: the launcher's 2x default (the gate sets none and stays 640x448)");
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

        tc.Run("server presets: the picker's choice round-trips and an unknown one falls back to custom", [](TestCase &t)
        {
            launcher::Config c;
            t.Equals(c.serverPreset, std::string("custom"), "the default preset is custom (the old hand-typed address)");
            c.serverPreset = "unzipped";
            c.server = "192.168.2.10";
            launcher::Config back;
            t.IsTrue(launcher::fromJson(launcher::toJson(c), back), "parses its own output");
            t.Equals(back.serverPreset, std::string("unzipped"), "the preset survives the round trip");
            t.Equals(back.server, std::string("192.168.2.10"), "... and so does the custom address behind it");
            launcher::Config odd;
            t.IsTrue(launcher::fromJson("{\"serverPreset\": \"horizon-2\"}", odd), "an unknown preset parses");
            t.Equals(odd.serverPreset, std::string("custom"), "... as custom, so the player's own address still applies");
            t.IsTrue(launcher::findServerPreset("nope") == nullptr, "an unknown id has no preset");
            const launcher::ServerPreset *community = launcher::findServerPreset("community");
            t.IsTrue(community != nullptr && std::string(community->address) == "COMMUNITY_SERVER_ADDRESS_TBC", "the community preset's address is the placeholder, not a guess");
        });

        // Sprint 7 Task 4 Step 5: the assertion that goes live the moment the owner supplies the hosted address.
        // Until then it reports itself as skipped rather than failing - MiniTest has no Skip, so the reason is
        // printed and nothing is asserted (docs/HUMAN_TASKS.md: "The two server addresses for the launcher's picker").
        tc.Run("server presets: the Unzipped preset ships a real address and is the default", [](TestCase &t)
        {
            const launcher::ServerPreset *unzipped = launcher::findServerPreset("unzipped");
            t.IsTrue(unzipped != nullptr, "the Unzipped preset exists");
            if (unzipped == nullptr)
                return;
            if (std::string(unzipped->address) == "UNZIPPED_SERVER_ADDRESS_TBC")
            {
                std::cout << "[skipped: the owner has not supplied the hosted address yet (docs/HUMAN_TASKS.md)] ";
            }
            else
            {
                t.IsTrue(std::string(unzipped->address).find("TBC") == std::string::npos, "no placeholder ships");
                t.Equals(launcher::Config{}.serverPreset, std::string("unzipped"), "the default preset is ours once it is real");
            }
        });

        tc.Run("the environment: the chosen preset decides PS2X_SOCOM2_SERVER", [](TestCase &t)
        {
            auto serverOf = [](const launcher::Config &c)
            {
                for (const std::string &kv : launcher::environmentFor(c))
                    if (kv.rfind("PS2X_SOCOM2_SERVER=", 0) == 0)
                        return kv.substr(std::strlen("PS2X_SOCOM2_SERVER="));
                return std::string("<missing>");
            };
            launcher::Config c;
            c.serverPreset = "community";
            c.server = "10.0.0.5";
            t.Equals(serverOf(c), std::string("COMMUNITY_SERVER_ADDRESS_TBC"), "community wins over whatever is in the text field");
            c.serverPreset = "unzipped";
            t.Equals(serverOf(c), std::string("UNZIPPED_SERVER_ADDRESS_TBC"), "our own server, not hosted yet");
            c.serverPreset = "custom";
            t.Equals(serverOf(c), std::string("10.0.0.5"), "custom uses the typed address");
            c.server.clear();
            t.Equals(serverOf(c), std::string("127.0.0.1"), "custom with nothing typed: the loopback default");
            t.Equals(launcher::effectiveServer(c), std::string("127.0.0.1"), "effectiveServer agrees");
        });

        tc.Run("exit code 65 tells the player the GL probe fell back to the CPU renderer", [](TestCase &t)
        {
            t.Equals(launcher::exitMessage(65),
                     std::string("Your GPU or driver is missing OpenGL 3.3 with dual-source blending; the game ran on the slow CPU renderer."),
                     "65 (GsGlCaps::kExitCode) names the missing capability and what happened");
            t.IsTrue(launcher::exitMessage(0).empty(), "a clean exit says nothing");
            t.IsTrue(launcher::exitMessage(1).empty(), "a crash is the log's business, not this sentence");
        });

        tc.Run("the environment: the verified ISO reaches the runtime as PS2X_CD_IMAGE", [](TestCase &t)
        {
            launcher::Config c;
            c.isoPath = "C:/discs/socom2.iso";
            std::vector<std::string> env = launcher::environmentFor(c);
            auto has = [&](const std::string &kv) { return std::find(env.begin(), env.end(), kv) != env.end(); };
            auto hasKey = [&](const std::string &k) { return std::any_of(env.begin(), env.end(), [&](const std::string &e) { return e.rfind(k + "=", 0) == 0; }); };
            t.IsTrue(has("PS2X_CD_IMAGE=C:/discs/socom2.iso"), "the disc the launcher verified is the disc the runtime mounts");
            launcher::Config empty;
            env = launcher::environmentFor(empty);
            t.IsTrue(!hasKey("PS2X_CD_IMAGE"), "no ISO configured: the runtime keeps its own .iso search");
        });

        tc.Run("the FPS overlay is off unless the player asks for it", [](TestCase &t)
        {
            launcher::Config c;
            t.IsTrue(!c.fpsOverlay, "off by default: nothing is drawn over anyone's game unasked");
            std::vector<std::string> env = launcher::environmentFor(c);
            auto hasKey = [](const std::vector<std::string> &e, const std::string &k) { return std::any_of(e.begin(), e.end(), [&](const std::string &s) { return s.rfind(k + "=", 0) == 0; }); };
            t.IsTrue(!hasKey(env, "PS2X_FPS_OVERLAY"), "off: the knob is not set at all, rather than set to 0");
            c.fpsOverlay = true;
            env = launcher::environmentFor(c);
            t.IsTrue(std::find(env.begin(), env.end(), std::string("PS2X_FPS_OVERLAY=1")) != env.end(), "on: exactly the value the runtime tests for");
            launcher::Config back;
            t.IsTrue(launcher::fromJson(launcher::toJson(c), back), "parses its own output");
            t.IsTrue(back.fpsOverlay, "the choice survives the round trip");
        });

        tc.Run("the fourth scale, the matched display size, and the master volume reach the environment", [](TestCase &t)
        {
            launcher::Config c;
            t.Equals(c.audioVolume, 100, "full volume by default: the mixer is untouched unless the player moves it");
            std::vector<std::string> env = launcher::environmentFor(c);
            auto has = [](const std::vector<std::string> &e, const std::string &kv) { return std::find(e.begin(), e.end(), kv) != e.end(); };
            t.IsTrue(has(env, "PS2X_AUDIO_VOLUME=100"), "unity always ships, so config.json is the one source of the value");
            c.gsScale = 4;
            c.windowSize = "2560x1440";      // what "Match display" resolved to on the player's monitor
            c.audioVolume = 35;
            env = launcher::environmentFor(c);
            t.IsTrue(has(env, "PS2X_GS_SCALE=4"), "the fourth radio reaches the backend's top clamp");
            t.IsTrue(has(env, "PS2X_WINDOW_SIZE=2560x1440"), "a matched display is an ordinary <w>x<h>, not a magic word");
            t.IsTrue(has(env, "PS2X_AUDIO_VOLUME=35"), "the volume the player set");
            launcher::Config back;
            t.IsTrue(launcher::fromJson(launcher::toJson(c), back), "parses its own output");
            t.IsTrue(back.gsScale == 4 && back.windowSize == "2560x1440" && back.audioVolume == 35, "all three survive the round trip");
            launcher::Config partial;
            t.IsTrue(launcher::fromJson("{\"gsScale\": 2}", partial), "an older config.json parses");
            t.Equals(partial.audioVolume, 100, "a config written before this task is still full volume");
        });

        tc.Run("the microphone pick round-trips and only reaches the environment when there is one", [](TestCase &t)
        {
            launcher::Config c;
            t.Equals(c.micDevice, std::string(""), "no microphone by default");
            std::vector<std::string> env = launcher::environmentFor(c);
            auto hasKey = [](const std::vector<std::string> &e, const std::string &k) { return std::any_of(e.begin(), e.end(), [&](const std::string &s) { return s.rfind(k + "=", 0) == 0; }); };
            t.IsTrue(!hasKey(env, "PS2X_MIC_DEVICE"), "no pick: the runtime opens no capture device at all");
            c.micDevice = "Microphone (USB Headset)";
            env = launcher::environmentFor(c);
            t.IsTrue(std::find(env.begin(), env.end(), std::string("PS2X_MIC_DEVICE=Microphone (USB Headset)")) != env.end(), "the device name, spaces and brackets and all");
            launcher::Config back;
            t.IsTrue(launcher::fromJson(launcher::toJson(c), back), "parses its own output");
            t.Equals(back.micDevice, c.micDevice, "the device name survives the round trip");
        });

        tc.Run("micLevelDb: RMS in dB full scale, -inf for silence", [](TestCase &t)
        {
            // A full-scale sine has RMS 1/sqrt(2), i.e. -3.0103 dB, whatever its frequency or phase.
            std::vector<float> sine(1600);   // 0.1 s at 16 kHz, ten whole cycles: no partial-cycle bias
            for (size_t i = 0; i < sine.size(); ++i)
                sine[i] = std::sin(2.0f * 3.14159265358979f * 100.0f * static_cast<float>(i) / 16000.0f);
            const float full = launcher::micLevelDb(sine.data(), sine.size());
            t.IsTrue(std::fabs(full + 3.0103f) < 0.05f, "a full-scale sine reads -3.01 dB");
            std::vector<float> half = sine;
            for (float &v : half)
                v *= 0.5f;
            t.IsTrue(std::fabs(launcher::micLevelDb(half.data(), half.size()) - (full - 6.0206f)) < 0.01f, "halving the amplitude drops it exactly 6.02 dB");
            const std::vector<float> quiet(1600, 0.0f);
            const float silent = launcher::micLevelDb(quiet.data(), quiet.size());
            t.IsTrue(std::isinf(silent) && silent < 0.0f, "silence is -inf, not 0 and not a crash");
            const float none = launcher::micLevelDb(nullptr, 0);
            t.IsTrue(std::isinf(none) && none < 0.0f, "no frames is -inf too");
        });

        tc.Run("the microphone list is whatever MicDevices reports, with None first", [](TestCase &t)
        {
            struct FakeMic final : launcher::MicDevices
            {
                std::vector<std::string> list() override { return {"Microphone (USB Headset)", "Stereo Mix"}; }
                bool startMeter(const std::string &name) override { started = name; return name == "Stereo Mix"; }
                float levelDb() const override { return -12.5f; }
                void stopMeter() override { started.clear(); }
                std::string started;
            };
            FakeMic mic;
            const std::vector<std::string> labels = launcher::micLabels(mic);
            t.Equals(labels.size(), static_cast<size_t>(3), "None plus the two devices");
            t.Equals(labels[0], std::string("None"), "None is first, so 'no microphone' is a click, not an empty field");
            t.Equals(labels[1], std::string("Microphone (USB Headset)"), "the device names come through unchanged");
            t.IsTrue(!mic.startMeter("Microphone (USB Headset)"), "a device that will not open says so");
            t.IsTrue(mic.startMeter("Stereo Mix") && mic.started == "Stereo Mix", "and one that will, opens");
        });
    });
}
