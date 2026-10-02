// Sprint 18 T2 (R339 = R-A, R340 = R-B, R343 = R-E): the launcher's client mode (launcher.json) and the PCSX2
// client's own settings (config.pcsx2.json) -- two clients, two files, no key shared. The task book wrote these
// cases as TEST_CASE/CHECK; MiniTest has no such macros, so each is the same case and the same checks in
// MiniTest's Case/Run form. The suite is named so PS2X_TEST_SUITE=pcsx2_config runs it alone.
#include "MiniTest.h"
#include "launcher/client_mode.h"
#include "launcher/launcher_config.h"
#include "launcher/pcsx2_config.h"

#include <string>

void register_pcsx2_config_tests()
{
    MiniTest::Case("pcsx2_config", [](TestCase &tc)
    {
        tc.Run("client_mode: the default, the two ids, and a round trip", [](TestCase &t)
        {
            t.IsTrue(launcher::parseClientMode("") == launcher::ClientMode::Native, "empty is Native");
            t.IsTrue(launcher::parseClientMode("{\"client\": \"pcsx2\"}") == launcher::ClientMode::Pcsx2, "pcsx2 is Pcsx2");
            t.IsTrue(launcher::parseClientMode("{\"client\": \"PCSX2\"}") == launcher::ClientMode::Native, "ids are exact");
            t.IsTrue(launcher::parseClientMode("not json at all") == launcher::ClientMode::Native, "not JSON is Native");
            t.IsTrue(launcher::parseClientMode(launcher::clientModeJson(launcher::ClientMode::Pcsx2)) == launcher::ClientMode::Pcsx2,
                     "the written file reads back");
            t.IsTrue(std::string(launcher::clientModeId(launcher::ClientMode::Native)) == "native", "the native id");
        });

        tc.Run("pcsx2_config: defaults, a round trip, and no key of config.json's", [](TestCase &t)
        {
            launcher::Pcsx2Config c;
            t.IsTrue(c.gameRevision == "r0001", "the default revision");
            t.IsTrue(c.serverPreset == "unzipped", "the default preset");
            c.isoPath = "D:\\games\\socom2.iso"; c.pcsx2Exe = "C:\\s2u\\pcsx2\\pcsx2-qt.exe"; c.serverPreset = "custom";
            c.server = "203.0.113.10"; c.ethDevice = "{95852BA5-54B5-4A50-A84D-8ED1B927EDD9}";
            const std::string json = launcher::pcsx2ToJson(c);
            launcher::Pcsx2Config back;
            t.IsTrue(launcher::pcsx2FromJson(json, back), "the written file parses");
            t.IsTrue(back == c, "and reads back equal");
            // Review Focus 1 / R-A: the native client's keys mean nothing here and never leak in.
            t.IsTrue(json.find("gsScale") == std::string::npos, "no gsScale");
            t.IsTrue(json.find("loginPassword") == std::string::npos, "no loginPassword");
            t.IsTrue(json.find("mappings") == std::string::npos, "no mappings");
        });

        tc.Run("pcsx2_config: unknown keys ignored, missing keys keep defaults, malformed is the defaults", [](TestCase &t)
        {
            launcher::Pcsx2Config c;
            t.IsTrue(launcher::pcsx2FromJson("{\"isoPath\": \"x.iso\", \"futureKey\": 7, \"gsScale\": 3}", c), "unknown keys parse");
            t.IsTrue(c.isoPath == "x.iso", "the known key is read");
            t.IsTrue(c.serverPreset == "unzipped", "a missing key keeps its default");
            launcher::Pcsx2Config bad; bad.isoPath = "keep?";
            t.IsTrue(!launcher::pcsx2FromJson("{\"isoPath\": ", bad), "malformed is false");
            t.IsTrue(bad == launcher::Pcsx2Config{}, "and leaves the defaults");
        });

        tc.Run("pcsx2_config: the revision and the preset are normalised as the native config's are", [](TestCase &t)
        {
            launcher::Pcsx2Config c;
            t.IsTrue(launcher::pcsx2FromJson("{\"gameRevision\": \"r9999\", \"serverPreset\": \"unzipped-ip\"}", c), "parses");
            t.IsTrue(c.gameRevision == "r0001", "an unknown revision is r0001");
            t.IsTrue(c.serverPreset == "unzipped", "kRetiredPresets heals it, as fromJson does");
            t.IsTrue(launcher::pcsx2FromJson("{\"serverPreset\": \"community\"}", c), "parses");
            t.IsTrue(c.serverPreset == "unzipped", "R-B: not playable -> the playable fallback, as fromJson does");
        });

        tc.Run("pcsx2_config: the effective server is the preset's address or the typed one", [](TestCase &t)
        {
            launcher::Pcsx2Config c;
            t.IsTrue(launcher::pcsx2EffectiveServer(c) == "socom.scotho.com", "the default preset's address");
            c.serverPreset = "custom"; c.server = "203.0.113.7";
            t.IsTrue(launcher::pcsx2EffectiveServer(c) == "203.0.113.7", "Custom's typed address");
            c.server = "";
            t.IsTrue(launcher::pcsx2EffectiveServer(c) == "127.0.0.1", "nothing typed is loopback");
        });

        tc.Run("launcher_config: the coming-soon note exists and is not the revision note", [](TestCase &t)
        {
            t.IsTrue(std::string(launcher::kPresetComingSoonNote) == "coming soon", "the note's text");
            t.IsTrue(std::string(launcher::kPresetComingSoonNote) != std::string(launcher::kRevisionMissingNote),
                     "not the revision cell's note");
        });
    });
}
