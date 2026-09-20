// Sprint 9 Goal 1: what the launcher's SAVE DIAGNOSTICS puts in its zip -- and what it must not.
#include "MiniTest.h"
#include "launcher/diagnostics.h"
#include "launcher/launcher_config.h"
#include "ps2x/zip_store.h"

#include <algorithm>
#include <string>
#include <vector>

namespace
{
    namespace diag = launcher::diagnostics;

    const char *kConfigWithSecrets =
        "{\n"
        "  \"isoPath\": \"C:\\\\Users\\\\secretuser\\\\Games\\\\SOCOM II (USA).iso\",\n"
        "  \"gsScale\": 2,\n"
        "  \"password\": \"hunter2\",\n"
        "  \"token\": \"abc123token\",\n"
        "  \"account\": {\"name\": \"viper\", \"sessionKey\": \"deadbeefcafe\"},\n"
        "  \"serverPreset\": \"custom\",\n"
        "  \"server\": \"10.0.0.5\",\n"
        "  \"profile\": \"viper\"\n"
        "}\n";

    const char *kLog =
        "INFO: GL: OpenGL device information:\r\n"
        "INFO:     > Vendor:   NVIDIA Corporation\r\n"
        "INFO:     > Renderer: NVIDIA GeForce RTX 4070 SUPER/PCIe/SSE2\r\n"
        "INFO:     > Version:  3.3.0 NVIDIA 595.97\r\n"
        "INFO:     > GLSL:     3.30 NVIDIA via Cg compiler\r\n"
        "[socom2] CD image: C:\\Users\\secretuser\\Games\\SOCOM II (USA).iso\r\n"
        "[gs-gl] depth mapping: clip-control (GL_ZERO_TO_ONE, z exact)\r\n"
        "[gs-gl] initialised: 3.3.0 NVIDIA 595.97\r\n"
        "[audio] 989snd mix stream open (48000 Hz stereo)\r\n"
        "[crash] code=0xc0000005 host=0x7ff6a1b2c3d4 module+0x1b2c3d4 access=read at 0x10\r\n"
        "[crash] backtrace (module-relative): 1b2c3d4 1b2c000\r\n"
        "[crash] guest live pc=0x2a1b40 ra=0x2a1b00 running=3 threads: [3 pc=0x2a1b40 ra=0x2a1b00 st=1]\r\n";

    const ZipStore::Entry *find(const std::vector<ZipStore::Entry> &entries, const std::string &name)
    {
        for (const ZipStore::Entry &e : entries)
            if (e.name == name)
                return &e;
        return nullptr;
    }

    diag::Inputs inputs()
    {
        diag::Inputs in;
        in.logName = "run_20260919_084912.log";
        in.logText = kLog;
        in.configText = kConfigWithSecrets;
        in.version = "SOCOM Unzipped 871f9f8 (2026-09-19)";
        in.platform = "windows";
        in.homeDir = "C:\\Users\\secretuser";
        in.haveLastExit = true;
        in.lastExit = static_cast<int>(0xC0000005u);
        return in;
    }
}

void register_diagnostics_tests()
{
    MiniTest::Case("Diagnostics", [](TestCase &tc)
    {
        tc.Run("the bundle contains no credential and no home directory, whatever config.json and the log held", [](TestCase &t)
        {
            const std::vector<ZipStore::Entry> entries = diag::entries(inputs());
            const std::string zip = ZipStore::build(entries);
            t.IsTrue(!zip.empty(), "the entries make an archive");
            for (const char *secret : {"hunter2", "abc123token", "deadbeefcafe", "password", "sessionKey", "secretuser"})
            {
                t.IsTrue(zip.find(secret) == std::string::npos, std::string("the archive's bytes do not contain ") + secret);
                for (const ZipStore::Entry &e : entries)
                    t.IsTrue(e.data.find(secret) == std::string::npos, e.name + " does not contain " + secret);
            }
        });

        tc.Run("config.json: only the schema's keys, the ISO by file name only, the rest as the player set it", [](TestCase &t)
        {
            const std::string json = diag::sanitizedConfigJson(kConfigWithSecrets);
            launcher::Config c;
            t.IsTrue(launcher::fromJson(json, c), "what comes out is a config.json the launcher can read");
            t.Equals(c.isoPath, std::string("SOCOM II (USA).iso"), "the ISO's folder is gone, its name stays (it says which dump)");
            t.Equals(c.gsScale, 2, "settings survive");
            t.Equals(c.server, std::string("10.0.0.5"), "the custom server stays: an online report is useless without it (R134)");
            t.Equals(c.profile, std::string("viper"), "the profile stays: it names the card folder");
            t.Equals(json, launcher::toJson(c), "and it is exactly toJson of that: nothing else can be in it");
            launcher::Config forward;
            forward.isoPath = "/home/secretuser/discs/socom2.iso";
            t.IsTrue(diag::sanitizedConfigJson(launcher::toJson(forward)).find("secretuser") == std::string::npos, "forward slashes too");
            const std::string bad = diag::sanitizedConfigJson("{ \"password\": \"hunter2\", ");
            t.IsTrue(bad.find("hunter2") == std::string::npos, "a malformed config is never copied through");
            t.IsTrue(bad.find("\"error\"") != std::string::npos, "it is replaced by a note that says so");
        });

        tc.Run("scrub: the home directory becomes ~ in either slash style, and a short one is left alone", [](TestCase &t)
        {
            t.Equals(diag::scrub("at C:\\Users\\bob\\x and C:/Users/bob/y", "C:\\Users\\bob"), std::string("at ~\\x and ~/y"), "both styles");
            t.Equals(diag::scrub("/home/bob/socom2.iso", "/home/bob"), std::string("~/socom2.iso"), "POSIX");
            t.Equals(diag::scrub("/a/b", "/"), std::string("/a/b"), "a root is not a home");
            t.Equals(diag::scrub("text", ""), std::string("text"), "nor is nothing");
        });

        tc.Run("gl_caps.txt: raylib's device lines and the backend's own, CRs dropped", [](TestCase &t)
        {
            const std::string caps = diag::glCapsLines(kLog);
            t.Equals(caps, std::string("INFO:     > Vendor:   NVIDIA Corporation\n"
                                       "INFO:     > Renderer: NVIDIA GeForce RTX 4070 SUPER/PCIe/SSE2\n"
                                       "INFO:     > Version:  3.3.0 NVIDIA 595.97\n"
                                       "INFO:     > GLSL:     3.30 NVIDIA via Cg compiler\n"
                                       "[gs-gl] depth mapping: clip-control (GL_ZERO_TO_ONE, z exact)\n"
                                       "[gs-gl] initialised: 3.3.0 NVIDIA 595.97\n"), "the six lines, in the log's order");
            t.Equals(diag::glCapsLines("[audio] only\n"), std::string("no GL line in this log\n"), "a run that died before the window says so");
            t.IsTrue(diag::glCapsLines("[gs-gl] switching to the CPU rasterizer: OpenGL 3.3\n").find("switching") != std::string::npos, "the fallback line is a caps line");
        });

        tc.Run("crash.txt: there when the log has a record, absent when it has none", [](TestCase &t)
        {
            const std::vector<ZipStore::Entry> crashed = diag::entries(inputs());
            const ZipStore::Entry *record = find(crashed, "crash.txt");
            t.IsNotNull(record, "a log with [crash] lines yields crash.txt");
            if (record)
            {
                t.IsTrue(record->data.find("[crash] code=0xc0000005") == 0, "it starts with the handler's first line");
                t.IsTrue(record->data.find("[audio]") == std::string::npos, "and holds nothing else");
            }
            diag::Inputs clean = inputs();
            clean.logText = "[gs-gl] initialised: 3.3.0\n[audio] ok\n";
            t.IsNull(find(diag::entries(clean), "crash.txt"), "no record, no file");
            t.Equals(diag::crashRecord("[terminate] unhandled exception\n[main] fatal exception: x\n[oom] exit 71\n[preflight] exit 66 disc-not-found: s (d)\n[gs-gl] FATAL render target\n[pc] x\n"),
                     std::string("[terminate] unhandled exception\n[main] fatal exception: x\n[oom] exit 71\n[preflight] exit 66 disc-not-found: s (d)\n[gs-gl] FATAL render target\n"),
                     "every way this process announces its own death");
        });

        tc.Run("the entries: their names, the log under log/, versions.txt with the last exit explained", [](TestCase &t)
        {
            const std::vector<ZipStore::Entry> entries = diag::entries(inputs());
            for (const char *name : {"log/run_20260919_084912.log", "config.json", "gl_caps.txt", "crash.txt", "versions.txt"})
                t.IsNotNull(find(entries, name), std::string("has ") + name);
            t.Equals(static_cast<int>(entries.size()), 5, "and nothing else");
            const ZipStore::Entry *versions = find(entries, "versions.txt");
            if (versions)
            {
                t.IsTrue(versions->data.find("launcher: SOCOM Unzipped 871f9f8 (2026-09-19)\n") != std::string::npos, "the launcher's version.txt");
                t.IsTrue(versions->data.find("platform: windows\n") != std::string::npos, "the platform");
                t.IsTrue(versions->data.find("last exit: -1073741819 -> 70 crashed: The game crashed.") != std::string::npos, "the raw status, the code and the sentence");
            }
            diag::Inputs bare;
            bare.platform = "linux";
            const std::vector<ZipStore::Entry> least = diag::entries(bare);
            t.Equals(static_cast<int>(least.size()), 2, "no log and no config: gl_caps.txt and versions.txt still");
            const ZipStore::Entry *v = find(least, "versions.txt");
            t.IsTrue(v && v->data.find("launcher: development build\n") != std::string::npos, "no version.txt reads as the About page reads it");
            t.IsTrue(v && v->data.find("last exit: no run in this launcher session\n") != std::string::npos, "and no run says so");
            diag::Inputs odd = inputs();
            odd.logName = "..\\..\\evil.log";
            t.IsNotNull(find(diag::entries(odd), "log/run.log"), "a log name the zip would refuse is stored as log/run.log");
        });

        tc.Run("a long log keeps its head and its tail and says what it dropped", [](TestCase &t)
        {
            std::string log(1000, 'h');
            log += std::string(5000, 'm');
            log += std::string(2000, 't');
            const std::string clipped = diag::clipLog(log, 1000, 2000);
            t.IsTrue(clipped.rfind(std::string(1000, 'h'), 0) == 0, "the head: the boot lines");
            t.IsTrue(clipped.size() >= 2000 && clipped.compare(clipped.size() - 2000, 2000, std::string(2000, 't')) == 0, "the tail: the ending");
            t.IsTrue(clipped.find("[diagnostics] 5000 bytes omitted here") != std::string::npos, "and the gap is named");
            t.IsTrue(std::count(clipped.begin(), clipped.end(), 'm') < 10, "the middle is gone (the only m left is the marker's)");
            t.Equals(diag::clipLog("short", 1000, 2000), std::string("short"), "a log that fits is left alone");
        });
    });
}
