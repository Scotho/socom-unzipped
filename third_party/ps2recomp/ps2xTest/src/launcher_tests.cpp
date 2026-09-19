// Task 8b: the launcher's logic -- the ISO 9660 lookup, SHA-256, config.json and the environment it becomes.
#include "MiniTest.h"
#include "launcher/iso9660.h"
#include "launcher/launcher_config.h"
#include "launcher/launcher_layout.h"
#include "launcher/mic_devices.h"
#include "launcher/sha256.h"
// Sprint 8 Goal 9: the redesigned launcher's pure halves -- the layout and the focus model, the pad's
// geometry, the glyph family, the scale factor. None of these headers touches raylib.
#include "ui/focus.h"
#include "ui/glyphs.h"
#include "ui/pad_render.h"
#include "ui/theme.h"
#ifndef _WIN32
#include "../../ps2xLauncher/src/win32_glue.h"   // Sprint 8 Task 4: the POSIX glue, tested where it is built
#include <cerrno>
#include <chrono>
#include <csignal>
#include <fstream>
#include <sys/wait.h>
#include <thread>
#include <unistd.h>
#endif

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <filesystem>
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
            t.IsTrue(has("PS2X_SOCOM2_SERVER=3.143.65.100"), "the server: a fresh config plays on the project's hosted server (Sprint 8 Goal 12)");
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
            t.Equals(c.serverPreset, std::string("unzipped"), "the default preset is the project's hosted server, now that it is real");
            // A config.json from before the picker existed carries a typed server and no preset: it must stay the player's own.
            launcher::Config legacy;
            t.IsTrue(launcher::fromJson("{\"server\": \"192.168.2.10\"}", legacy), "a pre-picker config parses");
            t.Equals(legacy.serverPreset, std::string("custom"), "a typed server with no preset stays custom");
            t.Equals(launcher::effectiveServer(legacy), std::string("192.168.2.10"), "and its address still applies");
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
            t.Equals(serverOf(c), std::string("3.143.65.100"), "our own hosted server (Lightsail, US East)");
            t.Equals(launcher::effectiveServer(launcher::Config{}), std::string("3.143.65.100"), "a fresh config resolves to it");
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

        // Sprint 7 review finding: with Windows DPI scaling at 125-150% the 932 px window is 1165-1398 px
        // tall on a 768 or 1080 laptop panel, so the Launch row sits below the screen and nothing resizes.
        // The window opens at whatever the monitor allows and the body scrolls to reach the rest.
        tc.Run("the launcher fits a short display and scrolls its body", [](TestCase &t)
        {
            t.Equals(launcher::fitWindowHeight(932, 768, 80), 688, "a 768 px panel opens the window at 688, not 932 with the Launch row off-screen");
            t.Equals(launcher::fitWindowHeight(932, 1440, 80), 932, "a tall display still gets the full content height");
            t.Equals(launcher::scrollClamp(-10, 932, 688), 0, "scrolling up past the top stops at the top");
            t.Equals(launcher::scrollClamp(999, 932, 688), 244, "scrolling down stops with the last pixel of content visible");
            t.Equals(launcher::scrollClamp(5, 500, 688), 0, "content shorter than the window does not scroll at all");
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
            // Sprint 7 review finding F9: the two startMeter assertions that used to stand here asserted the
            // FAKE's own return value ("Stereo Mix" opens, anything else does not), which is this test file's
            // code and not the launcher's. micLabels is the launcher logic under test here.
            // Review finding F8: stopMeter() is the half main.cpp calls on Launch, so it has to be safe to call
            // at any time -- before any start, and twice in a row.
            mic.stopMeter();
            mic.stopMeter();
            t.IsTrue(mic.started.empty(), "stopMeter before any start, and twice over, is a no-op");
        });

        // Sprint 8 Task 4: the environment the game is started with. Windows built its block inline and the
        // POSIX spawn needs exactly the same rule, so the rule is one pure function shared by both glues.
        tc.Run("mergeEnvironment: ours win by key, base order kept, ours appended", [](TestCase &t)
        {
            const char *const base[] = {"A=1", "B=2", nullptr};
            const std::vector<std::string> merged = launcher::mergeEnvironment(base, {"B=3", "C=4"});
            t.Equals(merged.size(), static_cast<size_t>(3), "one A, one B, one C -- the overridden base B is gone, not duplicated");
            t.Equals(merged[0], std::string("A=1"), "a base entry nobody overrides survives unchanged");
            t.Equals(merged[1], std::string("B=3"), "ours wins B");
            t.Equals(merged[2], std::string("C=4"), "ours that the base lacks is appended, in our order");

            // A key with no '=' is not an environment entry: execve would take it, the child could not read it.
            const std::vector<std::string> skipped = launcher::mergeEnvironment(base, {"D"});
            t.Equals(skipped.size(), static_cast<size_t>(2), "a key-only entry is dropped, not spawned");
            t.Equals(skipped[0], std::string("A=1"), "the base is otherwise untouched");
            t.Equals(skipped[1], std::string("B=2"), "and B keeps its base value when nothing overrides it");

            const char *const none[] = {nullptr};
            t.Equals(launcher::mergeEnvironment(none, {"A=1"}).size(), static_cast<size_t>(1), "an empty base is just ours");
            t.Equals(launcher::mergeEnvironment(base, {}).size(), static_cast<size_t>(2), "no knobs is just the base");
        });


        // ---- Sprint 8 Goal 9: the redesigned launcher -----------------------------------------------------

        tc.Run("the scale factor: 1.0 at the design size, 2.0 at double, never below the minimum window's", [](TestCase &t)
        {
            auto close = [](float a, float b) { return std::fabs(a - b) < 0.0005f; };
            t.IsTrue(close(ui::scaleFor(1100, 700), 1.0f), "1100x700 is the design: everything is drawn 1:1");
            t.IsTrue(close(ui::scaleFor(2200, 1400), 2.0f), "twice the design is twice the scale");
            t.IsTrue(close(ui::scaleFor(1100, 1400), 1.0f), "the smaller axis decides: a tall window does not stretch");
            t.IsTrue(close(ui::scaleFor(2200, 700), 1.0f), "and neither does a wide one");
            const float minimum = ui::scaleFor(800, 520);
            t.IsTrue(close(minimum, 800.0f / 1100.0f), "the 800x520 minimum's own factor is width-bound");
            t.IsTrue(close(ui::scaleFor(640, 400), minimum), "smaller than the minimum draws the minimum, not a squashed window");
            t.IsTrue(close(ui::scaleFor(320, 200), minimum), "and however small the ask, the clamp holds");
        });

        tc.Run("the focus model: each direction lands where the layout says, and nothing is unreachable", [](TestCase &t)
        {
            const ui::Rect window{0.0f, 0.0f, 1100.0f, 700.0f};
            ui::LayoutInputs in;
            in.padChoices = 2;    // "first available" and one connected pad
            in.micChoices = 3;    // "None" and two capture devices
            in.customServer = true;
            const ui::FocusGraph g = ui::FocusGraph::build(window, in);

            // VIDEO: a row of cells, three rows down the page, and the rail to the left of all of them.
            t.Equals(g.move("rail.video", ui::Dir::Right), std::string("video.detail.0"), "the rail opens onto the page's first control");
            t.Equals(g.move("video.detail.0", ui::Dir::Right), std::string("video.detail.1"), "right walks the detail row");
            t.Equals(g.move("video.detail.1", ui::Dir::Left), std::string("video.detail.0"), "and left walks back");
            t.Equals(g.move("video.detail.0", ui::Dir::Left), std::string("rail.video"), "left off the first cell goes back to the rail");
            t.Equals(g.move("video.detail.0", ui::Dir::Down), std::string("video.filter.0"), "down from detail is the filter row under it");
            t.Equals(g.move("video.filter.0", ui::Dir::Down), std::string("video.window.0"), "and the window row under that");
            t.Equals(g.move("video.window.0", ui::Dir::Up), std::string("video.filter.0"), "up retraces it");
            t.Equals(g.move("video.window.3", ui::Dir::Down), std::string("video.fps"), "the overlay toggle is the last row");
            t.Equals(g.move("video.fps", ui::Dir::Down), std::string("bar.launch.video"), "and below the last row is the bar's LAUNCH");
            t.Equals(g.move("bar.launch.video", ui::Dir::Up), std::string("video.fps"), "which comes back up into the page");
            t.IsTrue(ui::barLaunchId(ui::Page::Play) != ui::barLaunchId(ui::Page::Video),
                     "the bar is on every page, so its node is named per page -- one id, one node, one rect");
            t.IsTrue(!hasNode(ui::layoutFor(ui::Page::Play, window, in), ui::barLaunchId(ui::Page::Play)),
                     "PLAY has its own large LAUNCH, so the bar shows the run's state there instead of a second button");
            t.IsTrue(hasNode(ui::layoutFor(ui::Page::Video, window, in), ui::barLaunchId(ui::Page::Video)),
                     "every other page keeps the bar's LAUNCH");

            // CONTROLLER: a list on the left, three knobs on the right.
            t.Equals(g.move("rail.controller", ui::Dir::Right), std::string("pad.pick.0"), "the pad list is the first control");
            t.Equals(g.move("pad.pick.0", ui::Dir::Down), std::string("pad.pick.1"), "down walks the pad list");
            t.Equals(g.move("pad.pick.0", ui::Dir::Right), std::string("pad.deadzone"), "right crosses to the knobs");
            t.Equals(g.move("pad.deadzone", ui::Dir::Left), std::string("pad.pick.0"), "and left crosses back to the list");
            t.Equals(g.move("pad.deadzone", ui::Dir::Down), std::string("pad.mouselook"), "the knobs run down the right column");
            t.Equals(g.move("pad.mouselook", ui::Dir::Down), std::string("pad.sensitivity"), "dead zone, mouse look, sensitivity");
            t.Equals(g.move("pad.sensitivity", ui::Dir::Up), std::string("pad.mouselook"), "and up retraces them");
            t.IsTrue(ui::adjustsHorizontally("pad.deadzone") && ui::adjustsHorizontally("pad.sensitivity") &&
                         ui::adjustsHorizontally("audio.volume") && !ui::adjustsHorizontally("pad.mouselook"),
                     "left/right ADJUSTS the three sliders rather than navigating away from them");

            // The rail itself walks up and down and stops at its ends.
            t.Equals(g.move("rail.play", ui::Dir::Down), std::string("rail.disc"), "the rail walks down");
            t.Equals(g.move("rail.disc", ui::Dir::Up), std::string("rail.play"), "and up");
            t.Equals(g.move("rail.play", ui::Dir::Up), std::string("rail.play"), "the top of the rail stays put");
            t.Equals(g.move("rail.about", ui::Dir::Down), std::string("rail.about"), "and so does the bottom");

            // Nothing is stranded: from its rail entry, every control on every page is reachable by moving.
            for (int i = 0; i < ui::kPageCount; ++i)
            {
                const ui::Page page = ui::pageAt(i);
                std::vector<std::string> seen = {ui::railId(page)};
                for (size_t head = 0; head < seen.size(); ++head)
                {
                    const ui::Dir dirs[4] = {ui::Dir::Up, ui::Dir::Down, ui::Dir::Left, ui::Dir::Right};
                    for (ui::Dir d : dirs)
                    {
                        const std::string to = g.move(seen[head], d);
                        if (std::find(seen.begin(), seen.end(), to) == seen.end())
                            seen.push_back(to);
                    }
                }
                for (const std::string &id : g.idsOn(page))
                    t.IsTrue(std::find(seen.begin(), seen.end(), id) != seen.end(),
                             std::string("reachable from the rail: ") + id);
            }

            // A page change keeps the rail in step, and Back returns to the page's own rail entry.
            ui::Nav nav;
            nav.goTo(g, ui::Page::Video);
            t.IsTrue(nav.page == ui::Page::Video, "goTo picks the page");
            t.Equals(nav.focus, std::string("video.detail.0"), "and focuses its first control");
            nav.back(g);
            t.Equals(nav.focus, std::string("rail.video"), "Back from a page returns focus to its rail entry");
            t.IsTrue(nav.page == ui::Page::Video, "without changing the page under it");
            nav.move(g, ui::Dir::Down);
            t.Equals(nav.focus, std::string("rail.audio"), "moving down the rail moves the rail selection");
            t.IsTrue(nav.page == ui::Page::Audio, "and the page follows it: the highlight and the pane never disagree");
            nav.move(g, ui::Dir::Right);
            t.Equals(nav.focus, std::string("audio.volume"), "right enters the page the rail landed on");

            // And every control is inside the window's bands at both sizes -- nothing hangs off the panel.
            const float minScale = ui::scaleFor(800, 520);
            const ui::Rect sizes[2] = {ui::Rect{0.0f, 0.0f, 1100.0f, 700.0f},
                                       ui::Rect{0.0f, 0.0f, ui::metrics::minW / minScale, ui::metrics::minH / minScale}};
            for (const ui::Rect &win : sizes)
            {
                const ui::Frame f = ui::frameFor(win);
                for (int i = 0; i < ui::kPageCount; ++i)
                    for (const ui::Node &n : ui::layoutFor(ui::pageAt(i), win, in))
                        t.IsTrue(n.r.inside(f.content) || n.r.inside(f.bar),
                                 std::string("inside the content pane or the bottom bar: ") + n.id);
            }
        });

        tc.Run("the pad's geometry: a DualShock silhouette, every input on it, the two sticks symmetric", [](TestCase &t)
        {
            const ui::Rect bounds{100.0f, 50.0f, 560.0f, 280.0f};
            const ui::PadGeometry g = ui::padGeometry(bounds);

            t.IsTrue(g.hull.inside(bounds) && g.header.inside(bounds), "the silhouette and the shoulder strip stay inside what was asked for");
            t.IsTrue(g.header.bottom() <= g.hull.y + 0.001f, "the strip is above the pad, not on it");
            t.IsTrue(g.body.inside(g.hull), "the body is part of the hull");
            t.IsTrue(g.plate.inside(g.body), "the centre plate is on the body");
            t.IsTrue(g.wingRadius > 0.0f && g.wing[0].x < g.wing[1].x, "two wings, left before right");
            t.IsTrue(g.dpadWell.x < g.faceWell.x, "the d-pad well is left of the face well");
            t.IsTrue(g.dpadWellRadius > 0.0f && g.faceWellRadius > 0.0f, "both wells have a size");

            auto insideCircle = [](ui::Vec2 c, float r, ui::Vec2 centre, float radius)
            {
                const float dx = c.x - centre.x, dy = c.y - centre.y;
                return std::sqrt(dx * dx + dy * dy) + r <= radius + 0.001f;
            };
            auto insideHull = [&](const ui::PadCircle &c)
            {
                return ui::Rect{c.c.x - c.r, c.c.y - c.r, c.r * 2.0f, c.r * 2.0f}.inside(g.hull);
            };
            for (int i = 0; i < 4; ++i)
            {
                t.IsTrue(insideCircle(g.dpad[i].c, g.dpad[i].r, g.wing[0], g.wingRadius), "a d-pad segment sits inside the left wing");
                t.IsTrue(insideCircle(g.dpad[i].c, g.dpad[i].r, g.dpadWell, g.dpadWellRadius), "and inside the d-pad's own well");
                t.IsTrue(insideCircle(g.face[i].c, g.face[i].r, g.wing[1], g.wingRadius), "a face button sits inside the right wing");
                t.IsTrue(insideCircle(g.face[i].c, g.face[i].r, g.faceWell, g.faceWellRadius), "and inside the face cluster's well");
                t.IsTrue(insideHull(g.dpad[i]) && insideHull(g.face[i]), "and both are on the silhouette");
            }
            for (int i = 0; i < 2; ++i)
            {
                t.IsTrue(g.center[i].c.x >= g.plate.x && g.center[i].c.x <= g.plate.right(), "select and start are on the centre plate");
                t.IsTrue(insideHull(g.stickClick[i]), "a stick cap is on the silhouette");
                t.IsTrue(ui::Rect{g.well[i].x - g.wellRadius, g.well[i].y - g.wellRadius, g.wellRadius * 2.0f, g.wellRadius * 2.0f}.inside(g.hull),
                         "and so is its whole well");
                t.IsTrue(g.shoulder[i].inside(g.header), "the shoulder bar is in the strip");
                t.IsTrue(g.trigger[i].inside(g.header), "and so is the trigger");
                t.IsTrue(g.trigger[i].bottom() <= g.shoulder[i].y + 0.001f, "the trigger is drawn above its shoulder");
            }

            // The sticks are the pair the player's thumbs rest on: they have to be a mirrored pair.
            const float centreX = g.hull.cx();
            t.IsTrue(std::fabs((centreX - g.well[0].x) - (g.well[1].x - centreX)) < 0.001f,
                     "the two sticks are symmetric about the pad's centre line");
            t.IsTrue(std::fabs(g.well[0].y - g.well[1].y) < 0.001f, "and level with each other");
            t.IsTrue(g.well[0].x > g.dpadWell.x && g.well[1].x < g.faceWell.x, "and inboard of the two wells");
            t.IsTrue(g.well[0].y > g.dpadWell.y && g.well[1].y > g.faceWell.y, "and below them, where a DualShock has them");
            t.IsTrue(std::fabs((centreX - g.wing[0].x) - (g.wing[1].x - centreX)) < 0.001f, "the wings are a mirrored pair too");
            t.IsTrue(g.handleTip[0].y > g.body.bottom() && g.handleTip[1].y > g.body.bottom(),
                     "the handles reach below the body");
            t.IsTrue(g.handleTip[0].x < g.handle[0].x && g.handleTip[1].x > g.handle[1].x,
                     "and splay outwards as they go");
            t.IsTrue(g.handleTip[0].y <= bounds.bottom() + 0.001f, "without leaving the drawing's bounds");

            // The dead zone the ring shows is the dead zone the game applies.
            t.IsTrue(std::fabs(ui::deadZoneRingRadius(0.15f, 40.0f) - 6.0f) < 0.001f, "the ring is deadZone x the well's radius");
            t.IsTrue(std::fabs(ui::deadZoneRingRadius(0.0f, 40.0f)) < 0.001f, "no dead zone, no ring");

            // The drawn stick offset is the axis the game will read, times the well's radius.
            auto close = [](float a, float b) { return std::fabs(a - b) < 0.001f; };
            const float well = 40.0f;
            ui::Vec2 off = ui::stickOffset(ui::Vec2{0.1f, 0.0f}, 0.2f, well);
            t.IsTrue(close(off.x, 0.0f) && close(off.y, 0.0f), "inside the dead zone the dot does not move at all");
            off = ui::stickOffset(ui::Vec2{0.6f, 0.0f}, 0.2f, well);
            t.IsTrue(close(off.x, 20.0f), "outside it the axis is rescaled over the travel that is left: (0.6-0.2)/0.8 = half");
            off = ui::stickOffset(ui::Vec2{-0.6f, 0.0f}, 0.2f, well);
            t.IsTrue(close(off.x, -20.0f), "and the sign is kept");
            off = ui::stickOffset(ui::Vec2{0.5f, 0.0f}, 0.0f, well);
            t.IsTrue(close(off.x, 20.0f), "with no dead zone it is simply the axis times the radius");
            off = ui::stickOffset(ui::Vec2{2.0f, 0.0f}, 0.0f, well);
            t.IsTrue(close(off.x, well), "and it never leaves the well, whatever the driver reports");
            off = ui::stickOffset(ui::Vec2{0.0f, 0.0f}, 0.15f, well);
            t.IsTrue(close(off.x, 0.0f) && close(off.y, 0.0f), "a centred stick is centred");
        });

        tc.Run("the glyph family follows the pad's name: Xbox letters, PlayStation shapes, neither otherwise", [](TestCase &t)
        {
            t.IsTrue(ui::glyphFamilyFor("Xbox Wireless Controller") == ui::GlyphFamily::Xbox, "the owner's pad");
            t.IsTrue(ui::glyphFamilyFor("XINPUT CONTROLLER (Controller)") == ui::GlyphFamily::Xbox, "XInput, in any case");
            t.IsTrue(ui::glyphFamilyFor("X-Box 360 pad") == ui::GlyphFamily::Xbox, "the hyphenated spelling");
            t.IsTrue(ui::glyphFamilyFor("Microsoft SideWinder") == ui::GlyphFamily::Xbox, "and the maker's own name");
            t.IsTrue(ui::glyphFamilyFor("Sony DualShock 4") == ui::GlyphFamily::PlayStation, "DualShock");
            t.IsTrue(ui::glyphFamilyFor("DualSense Edge") == ui::GlyphFamily::PlayStation, "DualSense");
            t.IsTrue(ui::glyphFamilyFor("PLAYSTATION(R)3 Controller") == ui::GlyphFamily::PlayStation, "PlayStation, in any case");
            t.IsTrue(ui::glyphFamilyFor("PS4 Controller") == ui::GlyphFamily::PlayStation, "ps4");
            t.IsTrue(ui::glyphFamilyFor("ps5 controller") == ui::GlyphFamily::PlayStation, "ps5");
            t.IsTrue(ui::glyphFamilyFor("Wireless Controller") == ui::GlyphFamily::PlayStation,
                     "the bare name SDL reports for a DualShock 4 -- but only when it is the whole name");
            t.IsTrue(ui::glyphFamilyFor("8BitDo Pro 2") == ui::GlyphFamily::Generic, "anything else is generic");
            t.IsTrue(ui::glyphFamilyFor("") == ui::GlyphFamily::Generic, "and so is no pad at all");
        });

        tc.Run("why LAUNCH is disabled, in the player's words", [](TestCase &t)
        {
            t.Equals(ui::launchBlockedReason(false, false, true), std::string("choose your SOCOM II disc image first"),
                     "no image chosen: the first thing to do, not an error about a file");
            t.Equals(ui::launchBlockedReason(false, false, false), std::string("that file is not SOCOM II (NTSC, r0001)"),
                     "a file that is not the game");
            t.Equals(ui::launchBlockedReason(true, true, false), std::string("the game is running"), "one game at a time");
            t.Equals(ui::launchBlockedReason(false, true, true), std::string("the game is running"),
                     "the running game comes first: it is the blocker the player just created");
            t.Equals(ui::launchBlockedReason(true, false, false), std::string(), "verified and idle: nothing in the way");
        });


#ifndef _WIN32
        // Sprint 8 Task 4: the POSIX glue. These two need a real /proc and a real filesystem, so they run in
        // the Linux VM and in CI, never on Windows (where win32_glue.cpp owns the interface).
        tc.Run("startGame refuses a directory with no socom2 next to the launcher", [](TestCase &t)
        {
            const std::string dir = (std::filesystem::temp_directory_path() / ("ps2x_task4_" + win32glue::stamp())).string();
            std::error_code ec;
            std::filesystem::create_directories(dir, ec);
            launcher::Config config;
            win32glue::GameProcess game;
            t.IsTrue(!win32glue::startGame(dir, config, game), "no socom2 in the folder is a false, not a spawn");
            t.IsTrue(game.error.find("socom2") != std::string::npos, "the message names socom2, so the player knows what is missing");
            std::filesystem::remove_all(dir, ec);
        });

        // F9: close() used to poll once with WNOHANG and then set pid = 0, abandoning a child that
        // was still running -- the launcher lost its only handle on the game, nothing could stop it,
        // and its status was never collected. close() must end the child and reap it.
        tc.Run("close() ends and reaps a game that is still running", [](TestCase &t)
        {
            namespace fs = std::filesystem;
            const fs::path dir = fs::temp_directory_path() / ("ps2x_f9_" + win32glue::stamp());
            std::error_code ec;
            fs::create_directories(dir, ec);

            // A stand-in for the game: it outlives the test on purpose, so an abandoned child would
            // still be alive when the assertions run.
            {
                std::ofstream script((dir / "socom2").string());
                script << "#!/bin/sh\n" << "sleep 30\n";
            }
            fs::permissions(dir / "socom2",
                            fs::perms::owner_all | fs::perms::group_read | fs::perms::group_exec,
                            fs::perm_options::replace, ec);
            { std::ofstream elf((dir / "socom2_game.elf").string()); }   // startGame only checks that it exists

            launcher::Config config;
            win32glue::GameProcess game;
            const bool started = win32glue::startGame(dir.string(), config, game);
            t.IsTrue(started, "the stand-in game must spawn (" + game.error + ")");
            if (!started)
            {
                fs::remove_all(dir, ec);
                return;
            }
            const pid_t child = static_cast<pid_t>(game.pid);
            t.IsTrue(child > 0, "and report a pid");
            t.IsTrue(game.running(), "and be running before close() is called");

            const auto start = std::chrono::steady_clock::now();
            game.close();
            const long long closeMs = std::chrono::duration_cast<std::chrono::milliseconds>(
                                          std::chrono::steady_clock::now() - start)
                                          .count();

            // Reaped by close() means there is nothing left to wait for: ECHILD, not a live pid.
            bool gone = false;
            for (int i = 0; i < 30 && !gone; ++i)
            {
                int raw = 0;
                errno = 0;
                const pid_t r = ::waitpid(child, &raw, WNOHANG);
                gone = (r < 0 && errno == ECHILD) || r == child;
                if (!gone)
                    std::this_thread::sleep_for(std::chrono::milliseconds(100));
            }
            t.IsTrue(gone, "close() must have reaped the child: waitpid has nothing left to report");
            t.IsTrue(closeMs < 3000, "and it must not have taken longer than the SIGTERM grace period");
            t.IsFalse(game.running(), "and the launcher must no longer believe a game is running");

            // Nothing of the stand-in survives: an abandoned `sleep 30` would still answer kill(0).
            t.IsTrue(::kill(child, 0) != 0 && errno == ESRCH,
                     "and the process itself must be gone, not left running without a handle");

            fs::remove_all(dir, ec);
        });

        tc.Run("exeDirectory is a directory that exists", [](TestCase &t)
        {
            const std::string dir = win32glue::exeDirectory();
            t.IsTrue(!dir.empty(), "exeDirectory answers something");
            std::error_code ec;
            t.IsTrue(std::filesystem::is_directory(dir, ec), "and it is a directory that exists (/proc/self/exe's parent, or the fallback)");
        });
#endif
    });
}
