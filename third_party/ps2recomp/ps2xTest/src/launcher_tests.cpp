// Task 8b: the launcher's logic -- the ISO 9660 lookup, SHA-256, config.json and the environment it becomes.
#include "MiniTest.h"
#include "launcher/iso9660.h"
#include "launcher/launcher_config.h"
#include "launcher/launcher_layout.h"
#include "launcher/mic_devices.h"
#include "launcher/sha256.h"
// Sprint 8 Goal 9: the redesigned launcher's pure halves -- the layout and the focus model, the pad's
// geometry, the glyph family, the scale factor. None of these headers touches raylib.
#include "ui/chrome.h"
#include "ui/focus.h"
#include "ui/glyphs.h"
#include "ui/pad_input.h"
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

        // Owner request 2026-09-19, R139: the crouch shortcut.
        tc.Run("the crouch shortcut: the stick click by default (owner 2026-09-20), off is silent, tolerant of junk, round-trips, reaches the environment", [](TestCase &t)
        {
            auto has = [](const std::vector<std::string> &e, const std::string &kv) { return std::find(e.begin(), e.end(), kv) != e.end(); };
            auto hasKey = [](const std::vector<std::string> &e, const std::string &k) { return std::any_of(e.begin(), e.end(), [&](const std::string &s) { return s.rfind(k + "=", 0) == 0; }); };

            launcher::Config c;
            t.Equals(c.crouchShortcut, std::string("l3"), "the left stick click by default: without it a pad cannot crouch at all (owner 2026-09-20)");
            t.IsTrue(has(launcher::environmentFor(c), "PS2X_PAD_CROUCH_SHORTCUT=l3"), "and the default reaches the game");
            launcher::Config offConfig;
            offConfig.crouchShortcut = "off";
            const std::vector<std::string> before = launcher::environmentFor(offConfig);
            t.IsTrue(!hasKey(before, "PS2X_PAD_CROUCH_SHORTCUT"), "off sends nothing: the game's environment is what it was before the option");

            const char *values[3] = {"l3", "touchpad", "l2"};
            for (const char *v : values)
            {
                c.crouchShortcut = v;
                const std::vector<std::string> env = launcher::environmentFor(c);
                t.IsTrue(has(env, std::string("PS2X_PAD_CROUCH_SHORTCUT=") + v), std::string("reaches the environment: ") + v);
                t.Equals(env.size(), before.size() + 1, "and is the only thing it adds");
                launcher::Config back;
                t.IsTrue(launcher::fromJson(launcher::toJson(c), back), "parses its own output");
                t.Equals(back.crouchShortcut, std::string(v), std::string("survives the round trip: ") + v);
            }

            t.Equals(launcher::normalizeCrouchShortcut("l3"), std::string("l3"), "a known value is itself");
            t.Equals(launcher::normalizeCrouchShortcut("R3"), std::string("off"), "an unknown value is off");
            t.Equals(launcher::normalizeCrouchShortcut(""), std::string("off"), "and so is an empty one");
            launcher::Config junk;
            junk.crouchShortcut = "l3";
            t.IsTrue(launcher::fromJson("{\"crouchShortcut\": \"banana\"}", junk), "a config with a value from nowhere still parses");
            t.Equals(junk.crouchShortcut, std::string("off"), "and the value is off, not kept and not guessed");
            junk.crouchShortcut = "banana";   // set in memory by a bug, not by the file
            t.IsTrue(!hasKey(launcher::environmentFor(junk), "PS2X_PAD_CROUCH_SHORTCUT"), "junk never reaches the game either");
            launcher::Config partial;
            t.IsTrue(launcher::fromJson("{\"gsScale\": 1}", partial), "an older config.json parses");
            t.Equals(partial.crouchShortcut, std::string("l3"), "a config written before the option gets the default, like a new one");

            // The words on the page: a label per cell, and the one line that states the trade (R139).
            for (int i = 0; i < launcher::kCrouchShortcutCount; ++i)
            {
                t.IsTrue(std::strlen(launcher::crouchShortcutLabel(launcher::kCrouchShortcuts[i])) > 0, "every value has a label");
                t.IsTrue(std::strlen(launcher::crouchShortcutHint(launcher::kCrouchShortcuts[i])) > 0, "and a hint");
                t.IsTrue(std::strlen(launcher::crouchShortcutHint(launcher::kCrouchShortcuts[i])) <= 104, "that fits one caption line");
            }
            t.IsTrue(std::string(launcher::crouchShortcutHint("l3")).find("fire mode") != std::string::npos ||
                         std::string(launcher::crouchShortcutHint("l3")).find("Fire mode") != std::string::npos,
                     "l3 says what it costs: fire mode leaves the pad");
            t.IsTrue(std::string(launcher::crouchShortcutHint("l3")).find("2") != std::string::npos, "and where it went: the keyboard's 2");
            t.IsTrue(std::string(launcher::crouchShortcutHint("l2")).find("weapon") != std::string::npos, "l2 says what it costs: the second weapon swap");
            t.IsTrue(std::string(launcher::crouchShortcutHint("touchpad")).find("othing") != std::string::npos, "touchpad says it costs nothing");
        });

        tc.Run("the profile names a directory, so it cannot leave cards/: separators, dots and junk are refused", [](TestCase &t)
        {
            // PS2X_MC_DIR is built as "cards/" + profile (launcher_config.cpp) and the runner resolves a relative
            // value under its own home (bare_run.cpp). The profile is free text in a config.json a player may well
            // have been sent by someone else, so "../.." there would put the game's memory-card writes anywhere the
            // player can write. It is a name, not a path: it stays one.
            t.Equals(launcher::normalizeProfile("craig"), std::string("craig"), "an ordinary name is itself");
            t.Equals(launcher::normalizeProfile("Craig 2_b-a.1"), std::string("Craig 2_b-a.1"), "letters, digits, space, _ - . are kept");
            t.Equals(launcher::normalizeProfile(""), std::string("player"), "an empty profile is the default");
            t.Equals(launcher::normalizeProfile(".."), std::string("player"), "so is the parent directory");
            t.Equals(launcher::normalizeProfile("."), std::string("player"), "and the current one");
            t.Equals(launcher::normalizeProfile("../../Windows"), std::string("player"), "a climb out is refused whole, not patched up");
            t.Equals(launcher::normalizeProfile("a/b"), std::string("player"), "a separator is refused");
            t.Equals(launcher::normalizeProfile("a\\b"), std::string("player"), "the other separator too");
            t.Equals(launcher::normalizeProfile("C:evil"), std::string("player"), "and a drive letter");
            t.Equals(launcher::normalizeProfile(std::string(300, 'x')).size(), static_cast<size_t>(64), "a very long name is cut to 64");

            launcher::Config c;
            c.profile = "../../../Users/Public";
            const std::vector<std::string> env = launcher::environmentFor(c);
            auto has = [&env](const std::string &kv) {
                return std::find(env.begin(), env.end(), kv) != env.end();
            };
            t.IsTrue(has("PS2X_MC_DIR=cards/player"), "the environment carries the safe name, never the climb");

            launcher::Config loaded;
            t.IsTrue(launcher::fromJson("{\"profile\": \"../../../etc\"}", loaded), "such a config still parses");
            t.Equals(loaded.profile, std::string("player"), "and what it loaded is already safe");
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
            // Fourth pass: a preset still carrying a placeholder is not playable, so it does not win the
            // field -- it resolves to the project's own server rather than sending the game a placeholder.
            t.Equals(serverOf(c), std::string("3.143.65.100"), "an unavailable preset resolves to the one that exists");
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
            t.Equals(launcher::exitMessage(0), std::string("The last run exited normally."), "a clean exit says so");
            t.IsTrue(launcher::exitMessage(1).find("SAVE DIAGNOSTICS") != std::string::npos, "an unnamed failure points at the diagnostics (Sprint 9 Goal 1: no ending is silent)");
        });

        tc.Run("LAST RUN: the code's sentence, a crash by its native status, a stranger by number, a notice appended", [](TestCase &t)
        {
            t.Equals(launcher::lastRunLine(0, ""), std::string("The last run exited normally."), "a clean run");
            t.Equals(launcher::lastRunLine(67, ""),
                     std::string("That disc image is not SOCOM II NTSC r0001 (SCUS-97275). This build plays only that disc."), "67");
            t.Equals(launcher::lastRunLine(static_cast<int>(0xC0000005u), ""),
                     std::string("The game crashed. Press SAVE DIAGNOSTICS and send the zip; it holds the crash record."), "Windows' access violation");
            t.Equals(launcher::lastRunLine(139, ""), launcher::lastRunLine(static_cast<int>(0xC0000005u), ""), "and Linux's SIGSEGV read the same");
            t.Equals(launcher::lastRunLine(42, ""), std::string("The game closed with code 42. Press SAVE DIAGNOSTICS to collect the log."), "never 'the game exited'");
            const std::string log = "INFO: AUDIO: Failed to initialize playback device\n[notice] no-audio-device: No audio device was found; the game ran without sound.\n";
            t.Equals(launcher::lastRunLine(0, log),
                     std::string("The last run exited normally. No audio device was found; the game ran without sound."),
                     "audio absent is not an exit: it rides on whatever the exit was");
        });

        tc.Run("the selftest lists every exit code with its sentence", [](TestCase &t)
        {
            const std::vector<std::string> lines = launcher::selftestExitLines();
            t.Equals(static_cast<int>(lines.size()), 11, "one line per code in the table");
            auto has = [&](const std::string &l) { return std::find(lines.begin(), lines.end(), l) != lines.end(); };
            t.IsTrue(has("exit   0 ok: The last run exited normally."), "0");
            t.IsTrue(has("exit  65 no-usable-gl: Your GPU or driver is missing OpenGL 3.3 with dual-source blending; the game ran on the slow CPU renderer."), "65");
            t.IsTrue(has("exit  72 card-dir-unwritable: The memory-card folder cannot be written. Move the game out of a protected folder and try again."), "72");
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
            // R139: the crouch shortcut is a row of four cells under both columns, the last thing on the page.
            t.Equals(g.move("pad.pick.1", ui::Dir::Down), std::string("pad.crouch.0"), "below the pad list is the crouch row's first cell");
            t.Equals(g.move("pad.crouch.0", ui::Dir::Right), std::string("pad.crouch.1"), "right walks the row");
            t.Equals(g.move("pad.crouch.1", ui::Dir::Right), std::string("pad.crouch.2"), "off, stick click, touchpad");
            t.Equals(g.move("pad.crouch.2", ui::Dir::Right), std::string("pad.crouch.3"), "and L2");
            t.Equals(g.move("pad.crouch.3", ui::Dir::Left), std::string("pad.crouch.2"), "left walks back");
            t.Equals(g.move("pad.sensitivity", ui::Dir::Down).rfind("pad.crouch.", 0), static_cast<size_t>(0), "below the knobs is the crouch row too");
            t.Equals(g.move("pad.crouch.0", ui::Dir::Up).rfind("pad.pick.", 0), static_cast<size_t>(0), "up from its left end is the pad list");
            t.Equals(g.move("pad.crouch.3", ui::Dir::Up), std::string("pad.sensitivity"), "up from its right end is the last knob");
            t.Equals(g.move("pad.crouch.0", ui::Dir::Down), std::string("bar.launch.controller"), "and below it is the bar's LAUNCH");
            t.IsTrue(!ui::adjustsHorizontally("pad.crouch.0"), "cells navigate; they are not a slider");
            {
                const ui::Node *sens = g.find("pad.sensitivity");
                const ui::Node *crouch = g.find("pad.crouch.0");
                t.IsTrue(sens != nullptr && crouch != nullptr && crouch->r.y >= sens->r.bottom() + 8.0f,
                         "the row clears the knobs above it");
            }
            t.IsTrue(ui::adjustsHorizontally("pad.deadzone") && ui::adjustsHorizontally("pad.sensitivity") &&
                         ui::adjustsHorizontally("audio.volume") && !ui::adjustsHorizontally("pad.mouselook"),
                     "left/right ADJUSTS the three sliders rather than navigating away from them");

            // The rail itself walks up and down and stops at its ends.
            t.Equals(g.move("rail.play", ui::Dir::Down), std::string("rail.disc"), "the rail walks down");
            t.Equals(g.move("rail.disc", ui::Dir::Up), std::string("rail.play"), "and up");
            t.Equals(g.move("rail.play", ui::Dir::Up), std::string("rail.play"), "the top of the rail stays put");
            t.Equals(g.move("rail.about", ui::Dir::Down), std::string("rail.about"), "and so does the bottom");

            // Sprint 9 Goal 8: REPORT A BUG sits after ONLINE and before ABOUT, and is a column of the site's
            // own fields -- TITLE, WHAT HAPPENED, CONTACT (OPTIONAL), the log checkbox, SEND REPORT.
            t.Equals(ui::kPageCount, 9, "nine pages");
            t.Equals(std::string(ui::pageName(ui::Page::Report)), std::string("REPORT A BUG"), "the rail's label");
            t.Equals(ui::pageSlug(ui::Page::Report), std::string("report"), "the page's short name: screenshots and ids");
            t.Equals(ui::pageSlug(ui::Page::Play), std::string("play"), "as every other page's already was");
            t.Equals(g.move("rail.online", ui::Dir::Down), std::string("rail.report"), "below ONLINE");
            t.Equals(g.move("rail.report", ui::Dir::Down), std::string("rail.about"), "above ABOUT");
            t.Equals(g.move("rail.report", ui::Dir::Right), std::string("report.title"), "the rail opens onto TITLE");
            t.Equals(g.move("report.title", ui::Dir::Down), std::string("report.description"), "then WHAT HAPPENED");
            t.Equals(g.move("report.description", ui::Dir::Down), std::string("report.contact"), "then CONTACT");
            t.Equals(g.move("report.contact", ui::Dir::Down), std::string("report.attach"), "then the log checkbox");
            t.Equals(g.move("report.attach", ui::Dir::Down), std::string("report.send"), "then SEND REPORT");
            t.Equals(g.move("report.send", ui::Dir::Up), std::string("report.attach"), "and back up");
            t.Equals(g.move("report.send", ui::Dir::Down), std::string("bar.launch.report"), "the bar's LAUNCH is under it");
            t.Equals(g.move("report.title", ui::Dir::Left), std::string("rail.report"), "left goes back to the rail");
            t.IsTrue(!ui::adjustsHorizontally("report.description"), "a text field is not a slider");
            {
                const ui::Node *what = g.find("report.description");
                const ui::Node *title = g.find("report.title");
                t.IsTrue(what != nullptr && title != nullptr && what->r.h >= title->r.h * 2.5f,
                         "WHAT HAPPENED has room for several lines");
            }

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

        // Sprint 8, owner feedback: "the yellow circle ... takes too long to adjust and awkwardly flys with a
        // delay". There is no travel left to see: the ring is at the focused control's rect on the very frame
        // the focus changes, inside a page and across a page change alike, whatever the frame time was.
        tc.Run("the focus ring does not travel: it is on the focused control's rect the frame focus changes", [](TestCase &t)
        {
            const ui::Rect window{0.0f, 0.0f, 1100.0f, 700.0f};
            ui::LayoutInputs in;
            in.padChoices = 2;
            in.micChoices = 3;
            in.customServer = true;
            const ui::FocusGraph g = ui::FocusGraph::build(window, in);
            auto same = [](ui::Rect a, ui::Rect b)
            {
                return std::fabs(a.x - b.x) < 0.001f && std::fabs(a.y - b.y) < 0.001f &&
                       std::fabs(a.w - b.w) < 0.001f && std::fabs(a.h - b.h) < 0.001f;
            };
            const float tinyDt = 0.001f;   // one millisecond: a fast frame must not hold the ring back

            ui::Nav nav;
            nav.goTo(g, ui::Page::Video);
            ui::FocusRing ring;
            ring.update(g, nav.focus, tinyDt);
            t.IsTrue(ring.visible, "the ring is drawn wherever the focus is");
            t.IsTrue(same(ring.shown, g.find(nav.focus)->r), "the first frame is already on the focused control");

            // A move inside the page: one update, one millisecond, and the ring is there.
            nav.move(g, ui::Dir::Down);
            t.IsTrue(same(g.find(nav.focus)->r, ui::rectOf(ui::layoutFor(ui::Page::Video, window, in), nav.focus)),
                     "the rect the ring aims at is the rect the page draws");
            ring.update(g, nav.focus, tinyDt);
            t.IsTrue(same(ring.shown, g.find(nav.focus)->r),
                     "a move inside a page puts the ring on the new control at once, with no interpolation");

            // A page change: onto the new page's control, never a stale rect, never collapsed at the origin.
            const ui::Rect before = ring.shown;
            nav.goTo(g, ui::Page::Online);
            ring.update(g, nav.focus, tinyDt);
            t.IsTrue(same(ring.shown, g.find(nav.focus)->r),
                     "a page change puts the ring straight onto the new page's focused control");
            t.IsFalse(same(ring.shown, before), "not on the rect it held on the page before");
            t.IsTrue(ring.shown.w > 1.0f && ring.shown.h > 1.0f, "and never collapsed at 0,0 for a frame");

            // The rail is a page change too: back out of a page and the ring is on the rail entry immediately.
            nav.back(g);
            ring.update(g, nav.focus, tinyDt);
            t.IsTrue(same(ring.shown, g.find("rail.online")->r), "Back lands the ring on the rail entry the same frame");

            // Whatever the frame time was, the whole move happens: a zero-length frame moves it all the way.
            ui::FocusRing fresh;
            fresh.update(g, "rail.play", 0.0f);
            fresh.update(g, "play.launch", 0.0f);
            t.IsTrue(same(fresh.shown, g.find("play.launch")->r),
                     "a zero-length frame still moves the ring the whole way: nothing is eased");

            // And a focus id the graph does not know draws nothing, rather than a stale rect.
            ui::FocusRing unknown;
            unknown.update(g, "nothing.at.all", tinyDt);
            t.IsFalse(unknown.visible, "an id the graph does not know draws no ring at all");
        });

        tc.Run("the pad's outline: one symmetric closed path, every input on it, the sticks a mirrored pair", [](TestCase &t)
        {
            const ui::Rect bounds{100.0f, 50.0f, 540.0f, 262.0f};
            const ui::PadGeometry g = ui::padGeometry(bounds);

            t.IsTrue(g.outlineCount > 300, "the curve is flattened finely enough to read as a curve");
            t.IsTrue(g.hull.inside(bounds) && g.header.inside(bounds), "the silhouette and the shoulder strip stay inside what was asked for");
            t.IsTrue(g.header.bottom() <= g.hull.y + 0.001f, "the strip is above the pad, not on it");
            t.IsTrue(std::fabs(g.width / g.height - 1.55f) < 0.02f, "a DualShock is about 1.55:1");

            // Symmetric about the centre line, to within half a pixel.
            float worst = 0.0f;
            for (int i = 0; i < g.outlineCount; ++i)
            {
                const ui::Vec2 p = g.outline[i];
                const ui::Vec2 mirrored{2.0f * g.centre.x - p.x, p.y};
                float best = 1e9f;
                for (int j = 0; j < g.outlineCount; ++j)
                {
                    const float dx = g.outline[j].x - mirrored.x;
                    const float dy = g.outline[j].y - mirrored.y;
                    const float d = std::sqrt(dx * dx + dy * dy);
                    if (d < best)
                        best = d;
                }
                if (best > worst)
                    worst = best;
            }
            t.IsTrue(worst < 0.5f, "every point on the outline has its mirror image on the other half");

            // A simple polygon: no segment crosses another (adjacent ones share an endpoint).
            auto crosses = [](ui::Vec2 a, ui::Vec2 b, ui::Vec2 c, ui::Vec2 d)
            {
                auto side = [](ui::Vec2 p, ui::Vec2 q, ui::Vec2 r)
                {
                    const float v = (q.x - p.x) * (r.y - p.y) - (q.y - p.y) * (r.x - p.x);
                    return v > 1e-4f ? 1 : (v < -1e-4f ? -1 : 0);
                };
                return side(a, b, c) * side(a, b, d) < 0 && side(c, d, a) * side(c, d, b) < 0;
            };
            bool selfIntersects = false;
            for (int i = 0; i < g.outlineCount && !selfIntersects; ++i)
            {
                const ui::Vec2 a = g.outline[i];
                const ui::Vec2 b = g.outline[(i + 1) % g.outlineCount];
                for (int j = i + 2; j < g.outlineCount; ++j)
                {
                    if (i == 0 && j == g.outlineCount - 1)
                        continue;
                    if (crosses(a, b, g.outline[j], g.outline[(j + 1) % g.outlineCount]))
                    {
                        selfIntersects = true;
                        break;
                    }
                }
            }
            t.IsFalse(selfIntersects, "the outline is a simple closed path: it never crosses itself");

            // Every interactive element is ON the pad: its whole hit circle inside the polygon.
            auto circleInside = [&](const ui::PadCircle &c, const char *what)
            {
                bool ok = ui::padContains(g, c.c);
                for (int k = 0; k < 16 && ok; ++k)
                {
                    const float a = static_cast<float>(k) * 3.14159265f / 8.0f;
                    ok = ui::padContains(g, ui::Vec2{c.c.x + std::cos(a) * c.r, c.c.y + std::sin(a) * c.r});
                }
                t.IsTrue(ok, std::string("on the pad's outline: ") + what);
            };
            for (int i = 0; i < 4; ++i)
            {
                circleInside(g.dpad[i], "a d-pad segment");
                circleInside(g.face[i], "a face button");
            }
            for (int i = 0; i < 2; ++i)
            {
                circleInside(g.center[i], "select or start");
                circleInside(g.stickClick[i], "a stick cap");
                circleInside(ui::PadCircle{ui::PadElement::LeftStickClick, g.well[i], g.wellRadius}, "a whole stick well");
                t.IsTrue(g.shoulder[i].inside(g.header), "the shoulder bar is in the strip");
                t.IsTrue(g.trigger[i].inside(g.header), "and so is the trigger");
                t.IsTrue(g.trigger[i].bottom() <= g.shoulder[i].y + 0.001f, "the trigger is drawn above its shoulder");
            }
            t.IsTrue(ui::padContains(g, ui::Vec2{g.plate.x, g.plate.y}) && ui::padContains(g, ui::Vec2{g.plate.right(), g.plate.bottom()}),
                     "the centre plate is on the pad");
            t.IsFalse(ui::padContains(g, ui::Vec2{g.hull.x + 1.0f, g.hull.bottom() - 1.0f}),
                      "and the corner between a handle and the hull's box is NOT on the pad -- the outline is the shape, not the box");

            // The wells are where a DualShock has them, and the sticks are a mirrored pair.
            t.IsTrue(g.dpadWell.x < g.faceWell.x, "the d-pad well is left of the face well");
            t.IsTrue(std::fabs((g.centre.x - g.well[0].x) - (g.well[1].x - g.centre.x)) < 0.001f,
                     "the two sticks are symmetric about the pad's centre line");
            t.IsTrue(std::fabs(g.well[0].y - g.well[1].y) < 0.001f, "and level with each other");
            t.IsTrue(g.well[0].x > g.dpadWell.x && g.well[1].x < g.faceWell.x, "and inboard of the two wells");
            t.IsTrue(g.well[0].y > g.dpadWell.y && g.well[1].y > g.faceWell.y, "and below them");

            t.IsTrue(std::fabs(ui::deadZoneRingRadius(0.15f, 40.0f) - 6.0f) < 0.001f, "the ring is deadZone x the well's radius");
            t.IsTrue(std::fabs(ui::deadZoneRingRadius(0.0f, 40.0f)) < 0.001f, "no dead zone, no ring");

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
        });

        tc.Run("the theme's contrast: every text colour clears 4.5:1 on the surface it is drawn on", [](TestCase &t)
        {
            using namespace ui::theme;
            auto pair = [&t](ui::Rgba ink, ui::Rgba on, const char *what)
            {
                const float ratio = ui::contrastRatio(ink, on);
                t.IsTrue(ratio >= 4.5f, std::string(what) + " must clear 4.5:1");
            };
            t.IsTrue(std::fabs(ui::contrastRatio(ui::Rgba{0, 0, 0, 255}, ui::Rgba{255, 255, 255, 255}) - 21.0f) < 0.01f,
                     "black on white is 21:1 -- the ratio itself is right");
            t.IsTrue(std::fabs(ui::contrastRatio(panel, panel) - 1.0f) < 0.001f, "a colour on itself is 1:1");

            pair(text, ground, "body text on the ground");
            pair(text, panel, "body text on a panel");
            pair(text, panelHi, "body text on a raised panel");
            pair(caption, ground, "captions on the ground");
            pair(caption, panel, "captions on a panel");
            pair(caption, panelHi, "captions on a raised panel");
            pair(dim, ground, "secondary text on the ground");
            pair(dim, panel, "secondary text on a panel");
            pair(gold, panel, "the accent on a panel");
            pair(goldHi, panel, "the bright accent on a panel");
            pair(goldHi, panelHi, "the bright accent on a raised panel");
            pair(ground, gold, "dark ink on a gold button");
            pair(ground, goldHi, "dark ink on a hovered gold button");
            pair(lampGreen, panel, "the ready lamp on a panel");
            pair(badInk, panel, "an error on a panel");
            pair(text, blueDeep, "the LAUNCH label on the bottom of its gradient");
            pair(text, blueFill, "the LAUNCH label on the top of its gradient");
        });

        tc.Run("the custom title bar's hit test: the buttons, the drag region, the resize edges", [](TestCase &t)
        {
            const int w = 1100, h = 700;
            const ui::ChromeLayout l = ui::chromeLayout(1100.0f);
            auto at = [&](float x, float y, float scale = 1.0f, bool maximized = false)
            {
                return ui::chromeHitTest(static_cast<int>(x), static_cast<int>(y), static_cast<int>(w * scale),
                                         static_cast<int>(h * scale), scale, maximized);
            };

            t.IsTrue(at(l.close.cx(), l.close.cy()) == ui::ChromeHit::Close, "the close button");
            t.IsTrue(at(l.maximize.cx(), l.maximize.cy()) == ui::ChromeHit::Maximize, "the maximise button");
            t.IsTrue(at(l.minimize.cx(), l.minimize.cy()) == ui::ChromeHit::Minimize, "the minimise button");
            t.IsTrue(at(l.pill.cx(), l.pill.cy()) == ui::ChromeHit::UnsavedPill, "the unsaved pill");
            t.IsTrue(at(l.caption.cx(), l.caption.cy()) == ui::ChromeHit::Caption, "the drag region between the mark and the status");
            t.IsTrue(at(l.mark.cx(), l.mark.cy()) == ui::ChromeHit::Client, "the mark is not draggable");
            t.IsTrue(at(l.status.cx(), l.status.cy()) == ui::ChromeHit::Client, "and neither is the status block");
            t.IsTrue(at(l.caption.cx(), l.bar.bottom() + 40.0f) == ui::ChromeHit::Client, "below the bar is the page");

            // The same boxes at 1.5x: the bar scales with everything else.
            t.IsTrue(at(l.close.cx() * 1.5f, l.close.cy() * 1.5f, 1.5f) == ui::ChromeHit::Close, "the close button at 1.5x");
            t.IsTrue(at(l.minimize.cx() * 1.5f, l.minimize.cy() * 1.5f, 1.5f) == ui::ChromeHit::Minimize, "the minimise button at 1.5x");
            t.IsTrue(at(l.caption.cx() * 1.5f, l.caption.cy() * 1.5f, 1.5f) == ui::ChromeHit::Caption, "the drag region at 1.5x");
            t.IsTrue(at(l.close.cx(), l.close.cy(), 1.5f) != ui::ChromeHit::Close,
                     "and a 1x position is NOT the close button once the window is scaled");

            // The resize frame.
            t.IsTrue(at(1.0f, 300.0f) == ui::ChromeHit::Left, "the left edge resizes");
            t.IsTrue(at(w - 1.0f, 300.0f) == ui::ChromeHit::Right, "so does the right");
            t.IsTrue(at(400.0f, 1.0f) == ui::ChromeHit::Top, "so does the top, above the bar");
            t.IsTrue(at(400.0f, h - 1.0f) == ui::ChromeHit::Bottom, "and the bottom");
            t.IsTrue(at(1.0f, 1.0f) == ui::ChromeHit::TopLeft, "the corners are corners");
            t.IsTrue(at(w - 1.0f, 1.0f) == ui::ChromeHit::TopRight, "top right");
            t.IsTrue(at(1.0f, h - 1.0f) == ui::ChromeHit::BottomLeft, "bottom left");
            t.IsTrue(at(w - 1.0f, h - 1.0f) == ui::ChromeHit::BottomRight, "bottom right");
            t.IsTrue(at(400.0f, 8.0f) == ui::ChromeHit::Caption, "past the 6 px border the bar takes over");

            // A maximised window has no resize frame at all.
            t.IsTrue(at(1.0f, 300.0f, 1.0f, true) == ui::ChromeHit::Client, "maximised: no left edge");
            t.IsTrue(at(400.0f, 1.0f, 1.0f, true) == ui::ChromeHit::Caption, "maximised: the top row is still the drag region");
            t.IsTrue(at(w - 1.0f, h - 1.0f, 1.0f, true) == ui::ChromeHit::Client, "maximised: no corner");

            // The buttons win over the top resize border, except in its top two pixels.
            t.IsTrue(at(l.close.cx(), 4.0f) == ui::ChromeHit::Close, "the close button wins inside its box");
            t.IsTrue(at(l.close.cx(), 1.0f) == ui::ChromeHit::Top, "but the top two pixels still resize");
            t.IsTrue(at(l.minimize.cx(), 1.0f) == ui::ChromeHit::Top, "away from the corner, that is the top edge too");
            t.IsTrue(at(1099.0f, 1.0f) == ui::ChromeHit::TopRight, "and the very corner is the corner grab");
        });

        // Sprint 8, owner feedback: the READY label "sits too far right", and the PLAY tab is "in a weird
        // spot". Both are placed from widths measured with the real font, so the arithmetic is asserted here.
        tc.Run("the top bar: the tab group is centred in the free width, the state word one padding from the buttons", [](TestCase &t)
        {
            auto close = [](float a, float b, float tol) { return std::fabs(a - b) <= tol; };
            // What the bar's font actually draws, in design units: the mark's two words, "READY", "PLAY".
            const float markRight = 16.0f + 86.0f + 10.0f + 74.0f;
            const float statusW = 46.0f;
            const float tabW = 34.0f;

            const float widths[2] = {1100.0f, ui::metrics::minW / ui::scaleFor(800, 520)};
            for (float barW : widths)
            {
                const ui::ChromeLayout l = ui::chromeLayout(barW);
                ui::TopBarText m;
                m.markRight = markRight;
                m.statusW = statusW;
                m.tabW.push_back(tabW);
                const ui::TopBarPlaces p = ui::topBarPlaces(l, m);

                // The state word: right-aligned against the window buttons, one padding away, measured.
                t.IsTrue(close(p.status.right(), l.minimize.x - ui::chrome::pad, 0.001f),
                         "the state word's right edge is exactly one padding left of the caption buttons");
                t.IsTrue(close(p.status.w, statusW, 0.001f), "its box is the width the font measured, not a fixed guess");
                t.IsTrue(close(p.status.y, 0.0f, 0.001f) && close(p.status.h, ui::metrics::barH, 0.001f),
                         "and it is the full height of the bar, so the word sits on its centre line");
                t.IsTrue(close(p.lamp.y, l.bar.cy(), 0.001f), "the lamp is on the bar's centre line");
                t.IsTrue(close(p.lamp.x, p.status.x - ui::chrome::lampGap, 0.001f), "and one gap to the left of the word");

                // The tab group: centred in what is free between the mark and the state cluster.
                const float freeL = markRight + ui::chrome::pad;
                const float freeR = p.lamp.x - ui::chrome::lampR - ui::chrome::pad;
                t.IsTrue(p.tabsCentred, "there is room at this width, so the group is centred");
                t.IsTrue(close(p.tabs.cx(), std::clamp(l.bar.cx(), freeL + p.tabs.w * 0.5f, freeR - p.tabs.w * 0.5f), 1.0f),
                         "the tab group is on the BAR's middle (the window's), pushed aside only as far as the mark or the cluster requires");
                t.IsTrue(p.tabs.x >= freeL - 0.001f, "it never runs into the wordmark");
                t.IsTrue(p.tabs.right() <= freeR + 0.001f, "nor into the state cluster");
                t.IsTrue(close(p.tabs.w, tabW, 0.001f) && p.tab.size() == 1u, "one tab, its own measured width");
                t.IsTrue(close(p.tab[0].x, p.tabs.x, 0.001f) && close(p.tab[0].w, tabW, 0.001f),
                         "and the group is the tab itself when there is only one");
            }

            // With unsaved changes the pill is in the bar, so the state word clears it by the same padding
            // and the two never overlap.
            {
                const ui::ChromeLayout l = ui::chromeLayout(1100.0f);
                ui::TopBarText m;
                m.markRight = markRight;
                m.statusW = statusW;
                m.showPill = true;
                m.tabW.push_back(tabW);
                const ui::TopBarPlaces p = ui::topBarPlaces(l, m);
                t.IsTrue(close(p.status.right(), l.pill.x - ui::chrome::pad, 0.001f),
                         "the UNSAVED pill takes the slot by the buttons, and the state word clears it by one padding");
                t.IsTrue(p.status.right() <= l.pill.x + 0.001f, "the word and the pill never overlap");
                t.IsTrue(p.tabs.right() <= p.lamp.x - ui::chrome::lampR - ui::chrome::pad + 0.001f,
                         "and the tab group still clears the cluster that just grew");
            }

            // Several tabs: laid out in order, one gap apart, the group still centred.
            {
                const ui::ChromeLayout l = ui::chromeLayout(1100.0f);
                ui::TopBarText m;
                m.markRight = markRight;
                m.statusW = statusW;
                m.tabW = {34.0f, 30.0f, 40.0f};
                const ui::TopBarPlaces p = ui::topBarPlaces(l, m);
                t.IsTrue(p.tab.size() == 3u, "a tab box for every label");
                t.IsTrue(close(p.tabs.w, 34.0f + 30.0f + 40.0f + 2.0f * ui::chrome::tabGap, 0.001f),
                         "the group is the labels plus the gaps between them");
                t.IsTrue(close(p.tab[1].x, p.tab[0].right() + ui::chrome::tabGap, 0.001f), "the second follows the first");
                t.IsTrue(close(p.tab[2].x, p.tab[1].right() + ui::chrome::tabGap, 0.001f), "and the third the second");
                t.IsTrue(close(p.tabs.x, p.tab[0].x, 0.001f) && close(p.tabs.right(), p.tab[2].right(), 0.001f),
                         "the group's box is exactly what the tabs span");
                const float freeL = markRight + ui::chrome::pad;
                const float freeR = p.lamp.x - ui::chrome::lampR - ui::chrome::pad;
                t.IsTrue(close(p.tabs.cx(), std::clamp(l.bar.cx(), freeL + p.tabs.w * 0.5f, freeR - p.tabs.w * 0.5f), 1.0f), "and it is on the bar's middle unless the mark or the cluster pushes it");
            }

            // No room: the group falls back to sitting after the wordmark rather than sliding under it.
            {
                const ui::ChromeLayout l = ui::chromeLayout(1100.0f);
                ui::TopBarText m;
                m.markRight = markRight;
                m.statusW = statusW;
                m.tabW.push_back(900.0f);
                const ui::TopBarPlaces p = ui::topBarPlaces(l, m);
                t.IsFalse(p.tabsCentred, "a group too wide for the free width is not pretending to be centred");
                t.IsTrue(close(p.tabs.x, markRight + ui::chrome::pad, 0.001f),
                         "it is left-aligned one padding after the wordmark instead");
            }
        });

        // Sprint 9 P4 (owner, 2026-09-20): "changing between menus causes a weird graphical bug that's
        // visible for a moment somewhere around the top left of the page." The frame's node list is built
        // from the page that was current at the top of the frame (main.cpp:1010), and the page changes
        // AFTER that -- during input (main.cpp:1149-1173) or inside the draw itself, when a rail entry is
        // clicked (main.cpp:517). On that one frame the NEW page's controls are looked up in the OLD page's
        // list; rectOf answers Rect{}, the origin with no size; and textCenteredIn duly puts a label at
        // (0,0), which is the top left of the window, for exactly one frame. Two defences, both pure: the
        // frame draws from the page's own list, and a rect that is not drawable places no ink anywhere.
        tc.Run("a page change does not leave the frame drawing from the previous page's node list", [](TestCase &t)
        {
            const ui::Rect window{0.0f, 0.0f, 1100.0f, 700.0f};
            ui::LayoutInputs in;
            const std::vector<ui::Node> onPlay = ui::layoutFor(ui::Page::Play, window, in);

            // What the defect did: the bar asks for the NEW page's LAUNCH in the OLD page's list.
            t.IsFalse(ui::hasNode(onPlay, ui::barLaunchId(ui::Page::Online)),
                      "the PLAY page's list does not hold the ONLINE page's bar LAUNCH -- this is the lookup that failed");
            t.IsFalse(ui::drawable(ui::rectOf(onPlay, ui::barLaunchId(ui::Page::Online))),
                      "and what it answers is not a rect anything may draw from");

            // The fix: the frame's list is the list of the page the input left behind.
            const std::vector<ui::Node> forFrame = ui::nodesForFrame(onPlay, ui::Page::Online, window, in);
            t.IsTrue(!forFrame.empty(), "the frame has a list to draw from");
            bool allOnline = true;
            for (const ui::Node &n : forFrame)
                allOnline = allOnline && n.page == ui::Page::Online;
            t.IsTrue(allOnline, "every node in it belongs to the page being drawn");
            const ui::Rect launch = ui::rectOf(forFrame, ui::barLaunchId(ui::Page::Online));
            t.IsTrue(ui::drawable(launch), "the bar's LAUNCH is found, with a rect of its own");
            t.IsTrue(launch.x > 0.0f && launch.y > 0.0f, "and it is on the bar, not at the window's origin");

            // A frame whose page did not change gets the list it already had, unchanged: the rebuild costs
            // a page change, not every frame.
            const std::vector<ui::Node> same = ui::nodesForFrame(onPlay, ui::Page::Play, window, in);
            t.IsTrue(same.size() == onPlay.size() && !same.empty() && same.front().id == onPlay.front().id,
                     "a frame whose page did not change draws from the same list");
        });

        tc.Run("an unknown id answers a rect nothing may draw from, and the origin is not a rect", [](TestCase &t)
        {
            const ui::Rect window{0.0f, 0.0f, 1100.0f, 700.0f};
            ui::LayoutInputs in;
            const std::vector<ui::Node> nodes = ui::layoutFor(ui::Page::Online, window, in);

            t.IsFalse(ui::drawable(ui::Rect{}), "a default Rect -- the origin, zero by zero -- is not drawable");
            t.IsFalse(ui::drawable(ui::Rect{10.0f, 10.0f, 0.0f, 40.0f}), "nor is one with no width");
            t.IsFalse(ui::drawable(ui::Rect{10.0f, 10.0f, 40.0f, 0.0f}), "nor one with no height");
            t.IsFalse(ui::drawable(ui::Rect{10.0f, 10.0f, -40.0f, 40.0f}), "nor one turned inside out");
            t.IsTrue(ui::drawable(ui::Rect{10.0f, 10.0f, 40.0f, 40.0f}), "a real rect is");

            t.IsFalse(ui::drawable(ui::rectOf(nodes, "online.no.such.control")),
                      "an id the list does not hold answers a rect nothing may draw from");
            t.IsTrue(ui::drawable(ui::rectOf(nodes, "online.profile")), "an id it does hold answers a real one");
        });

        // Sprint 9 P4, from the owner's screenshot: "the UNZIPPED part after SOCOM II is lower than the
        // SOCOM II text", and "the running text is not aligned with the yellow circle, it appears higher".
        // Both are the same mistake -- a word placed by its LINE BOX rather than by the ink a reader sees.
        // text()'s y is the top of the line box, so two different sizes drawn at the same y do NOT share a
        // baseline; and an all-caps word centred in a bar-height box sits high of centre, because the
        // font's ascent above the capitals and its descender space below it are not equal. The arithmetic
        // therefore lives with the bar's other measured placements, and this test asserts the very numbers
        // the bar draws, which is the spec's bar for this item ("asserted in the top-bar tests, not eyeballed").
        tc.Run("the top bar: UNZIPPED shares SOCOM II's baseline, and the state word's ink is centred on its lamp", [](TestCase &t)
        {
            auto close = [](float a, float b, float tol) { return std::fabs(a - b) <= tol; };
            const ui::ChromeLayout l = ui::chromeLayout(1100.0f);
            ui::TopBarText m;
            m.markRight = 16.0f + 86.0f + 10.0f + 74.0f;
            m.statusW = 46.0f;
            m.tabW.push_back(34.0f);
            // Deliberately asymmetric ink, and nothing here is zero or equal: a face whose capitals begin
            // 3.1 units below the line box's top and stand 10.4 tall at size 15, 2.7/9.0 at 13, 2.9/9.7 at
            // 14. An implementation that ignores the measurements cannot pass this by accident.
            m.markY = 10.0f;
            m.markCapTop = 3.1f;
            m.markCapH = 10.4f;
            m.markSubCapTop = 2.7f;
            m.markSubCapH = 9.0f;
            m.statusCapTop = 2.9f;
            m.statusCapH = 9.7f;
            const ui::TopBarPlaces p = ui::topBarPlaces(l, m);

            const float markBaseline = m.markY + m.markCapTop + m.markCapH;
            t.IsTrue(close(p.markSubY + m.markSubCapTop + m.markSubCapH, markBaseline, 0.001f),
                     "UNZIPPED is drawn at the y that puts its baseline on SOCOM II's");
            t.IsFalse(close(p.markSubY, m.markY, 0.001f),
                      "which is not the same y as SOCOM II's -- equal tops at two sizes is the defect the owner saw");

            t.IsTrue(close(p.statusY + m.statusCapTop + m.statusCapH * 0.5f, p.lamp.y, 0.001f),
                     "the state word's capitals are centred on the lamp's centre, not its line box on the bar's");
            t.IsTrue(p.statusY > 0.0f && p.statusY + m.statusCapTop + m.statusCapH < l.bar.h,
                     "and the word's ink is still inside the bar");
        });

        // Sprint 9 P4 (owner, 2026-09-20): "move 'Second instance on this machine (for testing)' into an
        // advanced section". There was no advanced anything in the launcher, so this makes one: a labelled
        // disclosure at the foot of a page, shut by default, holding the settings a stranger should not
        // meet on their first run. The rule that keeps a disclosure honest is that it never hides a setting
        // that is DOING something -- a section holding a non-default value opens itself and cannot be shut,
        // so nobody turns on a second instance, collapses the section and then wonders why two games start.
        tc.Run("ONLINE's ADVANCED section is shut by default, and the second instance lives inside it", [](TestCase &t)
        {
            const ui::Rect window{0.0f, 0.0f, 1100.0f, 700.0f};
            ui::LayoutInputs in;
            in.advancedOpen = false;

            const std::vector<ui::Node> shut = ui::layoutFor(ui::Page::Online, window, in);
            t.IsTrue(ui::hasNode(shut, "online.advanced"), "the disclosure itself is always there to be focused");
            t.IsFalse(ui::hasNode(shut, "online.second"),
                      "and while it is shut the second-instance toggle is not a control on the page at all");

            in.advancedOpen = true;
            const std::vector<ui::Node> open = ui::layoutFor(ui::Page::Online, window, in);
            t.IsTrue(ui::hasNode(open, "online.second"), "opened, the toggle is back");
            const ui::Rect disclosure = ui::rectOf(open, "online.advanced");
            const ui::Rect second = ui::rectOf(open, "online.second");
            t.IsTrue(ui::drawable(disclosure) && ui::drawable(second), "both are real rects");
            t.IsTrue(second.y > disclosure.y, "the toggle sits below the disclosure that reveals it");
            t.IsTrue(second.y > ui::rectOf(open, "online.profile").y,
                     "and the whole section is below the settings a stranger does need");

            // The focus order: ADVANCED is the last thing on the page before the bottom bar's LAUNCH, so
            // walking down the page never lands in it on the way to something ordinary.
            const ui::FocusGraph g = ui::FocusGraph::build(window, in);
            const std::vector<std::string> ids = g.idsOn(ui::Page::Online);
            t.IsTrue(!ids.empty(), "the page has controls");
            size_t advancedAt = ids.size(), profileAt = ids.size();
            for (size_t i = 0; i < ids.size(); ++i)
            {
                if (ids[i] == "online.advanced") advancedAt = i;
                if (ids[i] == "online.profile") profileAt = i;
            }
            t.IsTrue(advancedAt < ids.size() && profileAt < ids.size(), "both are in the graph");
            t.IsTrue(advancedAt > profileAt, "ADVANCED comes after the ordinary settings, not before them");
        });

        tc.Run("an ADVANCED section holding a non-default setting opens itself and cannot be shut", [](TestCase &t)
        {
            launcher::Config c;
            t.IsFalse(c.secondInstance, "a fresh config does not run a second instance");
            t.IsFalse(ui::advancedForced(c), "so nothing forces the section open");

            c.secondInstance = true;
            t.IsTrue(ui::advancedForced(c),
                     "a second instance switched on forces it open -- a disclosure must never hide a setting that is doing something");

            // And the layout agrees: forced open, the toggle is present whatever the player last chose.
            const ui::Rect window{0.0f, 0.0f, 1100.0f, 700.0f};
            ui::LayoutInputs in;
            in.advancedOpen = ui::advancedForced(c);   // the player's collapse does not get a vote here
            t.IsTrue(ui::hasNode(ui::layoutFor(ui::Page::Online, window, in), "online.second"),
                     "the toggle a player switched on is always on the page they switched it on");
        });

        // Sprint 9 P4 (owner, 2026-09-20): "tooltips where the launcher is unclear, 'what is a profile?'
        // first". The help is DATA, keyed by the control's own id, so the test can hold it to two rules a
        // tooltip set always breaks eventually: help that explains nothing, and help attached to a control
        // that no longer exists.
        tc.Run("the launcher's help is keyed by control id, and every id it answers for is a real control", [](TestCase &t)
        {
            t.IsTrue(ui::helpFor("no.such.control").empty(), "an id with no help answers nothing, not a placeholder");
            t.IsTrue(ui::helpFor("").empty(), "and neither does an empty id");

            // The owner's first ask, by name: a profile is the card directory AND the persona.
            const std::string profile = ui::helpFor("online.profile");
            t.IsFalse(profile.empty(), "'what is a profile?' is answered");
            t.IsTrue(profile.find("cards/") != std::string::npos, "it says where the profile puts the memory card");
            t.IsTrue(profile.find("persona") != std::string::npos, "and that it is the name the server sees");

            // Nothing drifts: every id with help is a control the focus graph actually holds. A renamed or
            // deleted control would otherwise leave help that can never be shown, and nobody would notice.
            const ui::Rect window{0.0f, 0.0f, 1100.0f, 700.0f};
            ui::LayoutInputs in;
            in.advancedOpen = true;   // the ADVANCED sections' controls count too
            const ui::FocusGraph g = ui::FocusGraph::build(window, in);
            const std::vector<std::string> helped = ui::helpedIds();
            t.IsTrue(helped.size() >= 3u, "there is a help set to check");
            for (const std::string &id : helped)
            {
                const bool real = g.find(id) != nullptr;
                t.IsTrue(real, ("help is attached to a control that exists: " + id).c_str());
                t.IsFalse(ui::helpFor(id).empty(), ("and it is not empty: " + id).c_str());
                // A sentence, not a restatement of the label: short help that just repeats the control is
                // noise, and this is the cheapest bar that catches it.
                t.IsTrue(ui::helpFor(id).size() >= 25u, ("help says something: " + id).c_str());
            }
        });

        // Sprint 8 Goal 9, fourth pass: a preset whose address is still a placeholder must never reach the
        // game. The community server runs r0004, which this client cannot play yet.
        tc.Run("an unavailable server preset cannot be played, and a config that names one heals itself", [](TestCase &t)
        {
            const launcher::ServerPreset *community = launcher::findServerPreset("community");
            const launcher::ServerPreset *unzipped = launcher::findServerPreset("unzipped");
            const launcher::ServerPreset *custom = launcher::findServerPreset("custom");
            t.IsTrue(community != nullptr && unzipped != nullptr && custom != nullptr, "the three presets are there");
            t.IsFalse(launcher::presetAvailable(*community), "community is not playable: its address is still a placeholder");
            t.IsTrue(launcher::presetAvailable(*unzipped), "the project's own server is");
            t.IsTrue(launcher::presetAvailable(*custom), "and so is an address the player types");

            launcher::Config c;
            c.serverPreset = "community";
            c.server = "192.168.2.10";
            t.Equals(launcher::effectiveServer(c), std::string("3.143.65.100"),
                     "a config still naming community plays on the project's server, not on a placeholder");
            const std::vector<std::string> env = launcher::environmentFor(c);
            for (const std::string &kv : env)
                t.IsTrue(kv.find("_TBC") == std::string::npos, "no placeholder ever reaches the game's environment");

            // Every preset id, including one that is not ours at all.
            for (const char *id : {"community", "unzipped", "custom", "nonsense"})
            {
                launcher::Config each;
                each.serverPreset = id;
                for (const std::string &kv : launcher::environmentFor(each))
                    t.IsTrue(kv.find("_TBC") == std::string::npos, std::string("no placeholder for preset ") + id);
            }

            launcher::Config loaded;
            t.IsTrue(launcher::fromJson("{\"serverPreset\": \"community\"}", loaded), "a saved community config parses");
            t.Equals(loaded.serverPreset, std::string("unzipped"),
                     "and is healed on load: the owner's saved choice moves to the server that exists");
            launcher::Config kept;
            t.IsTrue(launcher::fromJson("{\"serverPreset\": \"custom\", \"server\": \"192.168.2.10\"}", kept), "a custom config parses");
            t.Equals(kept.serverPreset, std::string("custom"), "and a playable preset is left alone");
            t.Equals(launcher::effectiveServer(kept), std::string("192.168.2.10"), "with the address the player typed");
        });

        tc.Run("the ONLINE page does not offer the preset that cannot be played", [](TestCase &t)
        {
            const ui::Rect window{0.0f, 0.0f, 1100.0f, 700.0f};
            ui::LayoutInputs in;
            in.padChoices = 2;
            in.micChoices = 3;
            in.customServer = false;
            const std::vector<ui::Node> nodes = ui::layoutFor(ui::Page::Online, window, in);
            t.IsFalse(ui::hasNode(nodes, "online.preset.0"), "community has no focusable row: it cannot be chosen");
            t.IsTrue(ui::hasNode(nodes, "online.preset.1"), "the project's server has one");
            t.IsTrue(ui::hasNode(nodes, "online.preset.2"), "and so does Custom");
            // The row is still drawn, in its own place, so the page can say why it is unavailable.
            const ui::Rect disabled = ui::onlinePresetRow(window, 0);
            const ui::Rect enabled = ui::rectOf(nodes, "online.preset.1");
            t.IsTrue(disabled.y < enabled.y && std::fabs(disabled.x - enabled.x) < 0.001f,
                     "and it is drawn above the others, on the same grid");

            // Nothing on the page is stranded by the gap in the list.
            const ui::FocusGraph g = ui::FocusGraph::build(window, in);
            std::vector<std::string> seen = {ui::railId(ui::Page::Online)};
            for (size_t head = 0; head < seen.size(); ++head)
                for (ui::Dir d : {ui::Dir::Up, ui::Dir::Down, ui::Dir::Left, ui::Dir::Right})
                {
                    const std::string to = g.move(seen[head], d);
                    if (std::find(seen.begin(), seen.end(), to) == seen.end())
                        seen.push_back(to);
                }
            for (const std::string &id : g.idsOn(ui::Page::Online))
                t.IsTrue(std::find(seen.begin(), seen.end(), id) != seen.end(),
                         std::string("still reachable from the rail: ") + id);
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


        // Sprint 9 Goal 9 (P3), the owner's defect, 2026-09-20: "When the game is active, both the game
        // and the launcher receive input commands from the controller." The launcher reads the pad through
        // raylib/GLFW, which reads it whether or not the window has focus -- so a stick push walked the
        // launcher's focus ring while the player was aiming with it. The gate is `ui::padIntent`: every pad
        // reading in the frame loop goes through it, and while the game runs it answers with nothing.
        tc.Run("the pad drives the launcher only while no game is running", [](TestCase &t)
        {
            ui::PadFrame pad;
            pad.present = true;
            pad.pressed[static_cast<int>(ui::PadNav::Right)] = true;

            double repeatAt = 0.0;
            const ui::PadIntent idle = ui::padIntent(pad, /*gameRunning=*/false, /*now=*/1.0, repeatAt);
            t.Equals(idle.dx, 1, "with no game running, a d-pad right is one step right");
            t.IsTrue(idle.prompts, "and a pad that moved the focus asks for the pad's prompts");

            double repeatAtRunning = 0.0;
            const ui::PadIntent running = ui::padIntent(pad, /*gameRunning=*/true, /*now=*/1.0, repeatAtRunning);
            t.Equals(running.dx, 0, "while the game runs the same press moves nothing");
            t.Equals(running.dy, 0, "and nothing vertically either");
            t.IsFalse(running.activate, "it does not activate");
            t.IsFalse(running.back, "it does not go back");
            t.IsFalse(running.launch, "and Start does not ask for a second launch");
            t.IsFalse(running.prompts, "a pad the launcher did not read cannot change the prompts");
        });

        // The same gate, for the half that is easy to get wrong: a HELD stick. The repeat clock must not
        // run while the game has the pad, or the frame the game exits would deliver the burst it banked.
        tc.Run("a stick held through a whole game session delivers nothing, and no burst when it ends", [](TestCase &t)
        {
            ui::PadFrame pad;
            pad.present = true;
            pad.leftX = -1.0f;   // hard left, well past the 0.55 threshold

            double repeatAt = 0.0;
            for (double now = 0.0; now < 5.0; now += 0.1)
            {
                const ui::PadIntent held = ui::padIntent(pad, /*gameRunning=*/true, now, repeatAt);
                t.Equals(held.dx, 0, "a stick held while the game runs never steps the launcher's focus");
            }
            t.Equals(repeatAt, 0.0, "and the repeat clock never started, so nothing is owed");

            const ui::PadIntent after = ui::padIntent(pad, /*gameRunning=*/false, /*now=*/5.0, repeatAt);
            t.Equals(after.dx, -1, "the frame the game ends, the still-held stick is one step, not a burst");
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
