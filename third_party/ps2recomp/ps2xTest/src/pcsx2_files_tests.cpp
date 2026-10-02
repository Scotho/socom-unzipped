// Sprint 18 T3: what the launcher writes for PCSX2 -- the data root, the [DEV9/Eth] keys, the ini merge (Review
// Focus 2: only our keys of our section are touched), the embedded guarded pnach, the DNS pick (Review Focus 3) and
// writeIfDifferent. The task book wrote these cases as TEST_CASE/CHECK; MiniTest has no such macros, so each is the
// same case and the same checks in MiniTest's Case/Run form, as T2's pcsx2_config_tests.cpp did. The suite is named
// so PS2X_TEST_SUITE=pcsx2_files runs it alone.
#include "MiniTest.h"
#include "launcher/pcsx2_config.h"
#include "launcher/pcsx2_files.h"

#include <filesystem>
#include <fstream>
#include <iterator>
#include <string>
#include <utility>

namespace pf = launcher::pcsx2files;
namespace fs = std::filesystem;

#ifndef PS2X_PNACH_MASTER_PATH
#error "PS2X_PNACH_MASTER_PATH: ps2xTest/CMakeLists.txt names scripts/parity/pcsx2/0F6FC6CF.pnach"
#endif

namespace
{
    std::string readFile(const fs::path &p)
    {
        std::ifstream f(p, std::ios::binary);
        return std::string((std::istreambuf_iterator<char>(f)), std::istreambuf_iterator<char>());
    }

    // The tracked bytes: git stores the master with LF endings and a Windows checkout may hold CRLF, while the
    // compiler reads a raw string's line endings as LF either way. The embed is the LF form on every host.
    std::string lf(std::string s)
    {
        std::string out;
        out.reserve(s.size());
        for (size_t i = 0; i < s.size(); ++i)
            if (!(s[i] == '\r' && i + 1 < s.size() && s[i + 1] == '\n'))
                out += s[i];
        return out;
    }
}

void register_pcsx2_files_tests()
{
    MiniTest::Case("pcsx2_files", [](TestCase &tc)
    {
        tc.Run("pcsx2_files: the data root is beside a portable exe and under Documents otherwise", [](TestCase &t)
        {
            t.IsTrue(pf::dataRoot("C:/s2u/pcsx2", true, "X:/Documents") == fs::path("C:/s2u/pcsx2"), "portable: beside the exe");
            t.IsTrue(pf::dataRoot("C:/Program Files/PCSX2", false, "X:/Documents") == fs::path("X:/Documents/PCSX2"),
                     "installed: <documents>/PCSX2");
        });

        tc.Run("pcsx2_files: the DEV9 keys are the harness's template with the DNS filled in", [](TestCase &t)
        {
            const auto keys = pf::dev9Keys("3.143.65.100", "");
            t.IsTrue(!keys.empty() && keys.front() == std::make_pair(std::string("EthEnable"), std::string("true")),
                     "EthEnable = true comes first");
            bool sawDns1 = false, sawDevice = false;
            for (const auto &[k, v] : keys)
            {
                if (k == "DNS1") { sawDns1 = true; t.IsTrue(v == "3.143.65.100", "DNS1 is the pick"); }
                if (k == "EthDevice") sawDevice = true;
            }
            t.IsTrue(sawDns1, "DNS1 is set");
            t.IsTrue(!sawDevice, "no EthDevice when none is given");
            const auto withDevice = pf::dev9Keys("3.143.65.100", "{AAAA}");
            bool found = false;
            for (const auto &[k, v] : withDevice)
                if (k == "EthDevice") { found = true; t.IsTrue(v == "{AAAA}", "EthDevice is the given GUID"); }
            t.IsTrue(found, "EthDevice when given");
            for (const char *k : {"EthApi", "InterceptDHCP", "AutoMask", "AutoGateway", "ModeDNS1", "ModeDNS2", "DNS2"})
            {
                bool f = false;
                for (const auto &kv : keys) f = f || kv.first == k;
                t.IsTrue(f, std::string("the template's ") + k);
            }
        });

        tc.Run("pcsx2_files: merging into a player's ini touches only our keys of our section (Review Focus 2)", [](TestCase &t)
        {
            const std::string ini =
                "[UI]\r\nMainWindowGeometry = abc\r\n\r\n[DEV9/Eth]\r\nEthEnable = false\r\nEthApi = PCAP\r\nEthLogDNS = true\r\n\r\n"
                "[DEV9/Hdd]\r\nHddEnable = false\r\n";
            const std::string out = pf::mergeIniSection(ini, "DEV9/Eth", {{"EthEnable", "true"}, {"EthApi", "Sockets"}, {"DNS1", "1.2.3.4"}});
            t.IsTrue(out.find("[UI]\r\nMainWindowGeometry = abc\r\n") == 0, "the section before ours, kept");
            t.IsTrue(out.find("EthEnable = true\r\n") != std::string::npos, "EthEnable replaced, CRLF kept");
            t.IsTrue(out.find("EthEnable = false") == std::string::npos, "the old EthEnable gone");
            t.IsTrue(out.find("EthApi = Sockets\r\n") != std::string::npos, "EthApi replaced");
            t.IsTrue(out.find("EthLogDNS = true\r\n") != std::string::npos, "a key we do not own, kept");
            t.IsTrue(out.find("DNS1 = 1.2.3.4\r\n") != std::string::npos, "the missing key added, CRLF");
            t.IsTrue(out.find("DNS1 = 1.2.3.4\r\n") < out.find("[DEV9/Hdd]"), "appended inside our section");
            t.IsTrue(out.find("[DEV9/Hdd]\r\nHddEnable = false\r\n") != std::string::npos, "the section after ours, kept");
            t.IsTrue(out.find("Sockets") == out.rfind("Sockets"), "Sockets once");
        });

        tc.Run("pcsx2_files: a missing section is appended; an empty file becomes just the section; LF stays LF", [](TestCase &t)
        {
            const std::string out = pf::mergeIniSection("[UI]\nX = 1\n", "DEV9/Eth", {{"EthEnable", "true"}});
            t.IsTrue(out == "[UI]\nX = 1\n\n[DEV9/Eth]\nEthEnable = true\n", "appended after one blank line, LF");
            t.IsTrue(pf::mergeIniSection("", "DEV9/Eth", {{"EthEnable", "true"}}) == "[DEV9/Eth]\nEthEnable = true\n",
                     "an empty file is just the section");
        });

        tc.Run("pcsx2_files: the merge -- a key twice, no spaces, mixed endings, no final newline (review)", [](TestCase &t)
        {
            auto count = [](const std::string &s, const std::string &needle)
            {
                size_t n = 0;
                for (size_t at = s.find(needle); at != std::string::npos; at = s.find(needle, at + 1)) ++n;
                return n;
            };
            const std::string twice = pf::mergeIniSection("[DEV9/Eth]\nEthEnable = false\nEthApi = PCAP\nEthEnable = false\n",
                                                          "DEV9/Eth", {{"EthEnable", "true"}});
            t.IsTrue(count(twice, "EthEnable = true\n") == 2, "a key present twice: both lines replaced");
            t.IsTrue(twice.find("false") == std::string::npos, "and no false left");
            t.IsTrue(pf::mergeIniSection("[DEV9/Eth]\nEthEnable=false\n", "DEV9/Eth", {{"EthEnable", "true"}})
                         == "[DEV9/Eth]\nEthEnable = true\n", "key=value with no spaces is matched and rewritten");
            t.IsTrue(pf::mergeIniSection("[UI]\r\nX = 1\n[DEV9/Eth]\nEthEnable = false\nEthApi = PCAP\r\n", "DEV9/Eth",
                                         {{"EthEnable", "true"}, {"DNS1", "1.2.3.4"}})
                         == "[UI]\r\nX = 1\n[DEV9/Eth]\nEthEnable = true\nEthApi = PCAP\r\nDNS1 = 1.2.3.4\r\n",
                     "mixed endings: a replaced line keeps its own, an added line takes the file's (CRLF)");
            t.IsTrue(pf::mergeIniSection("[UI]\nX = 1\n\n[DEV9/Eth]\nEthEnable = false", "DEV9/Eth",
                                         {{"EthEnable", "true"}, {"DNS1", "1.2.3.4"}})
                         == "[UI]\nX = 1\n\n[DEV9/Eth]\nEthEnable = true\nDNS1 = 1.2.3.4\n",
                     "our section last with no final newline: the added key is not glued on");
        });

        tc.Run("pcsx2_files: sections and keys match case-insensitively, the name trimmed in its brackets (review)", [](TestCase &t)
        {
            const std::string lower = pf::mergeIniSection("[UI]\r\nX = 1\r\n\r\n[dev9/eth]\r\nethenable = false\r\n", "DEV9/Eth",
                                                          {{"EthEnable", "true"}});
            t.IsTrue(lower == "[UI]\r\nX = 1\r\n\r\n[dev9/eth]\r\nEthEnable = true\r\n",
                     "[dev9/eth] and ethenable are ours: replaced in place with our spelling, no second section or key");
            const std::string spaced = pf::mergeIniSection("[ DEV9/Eth ]\nEthApi = PCAP\n", "DEV9/Eth", {{"EthApi", "Sockets"}});
            t.IsTrue(spaced == "[ DEV9/Eth ]\nEthApi = Sockets\n", "[ DEV9/Eth ] is the same section");
            t.IsTrue(pf::mergeIniSection("[DEV9/Ethernet]\nEthApi = PCAP\n", "DEV9/Eth", {{"EthApi", "Sockets"}})
                         == "[DEV9/Ethernet]\nEthApi = PCAP\n\n[DEV9/Eth]\nEthApi = Sockets\n",
                     "a longer name is another section");
        });

        tc.Run("pcsx2_files: the embedded pnach is the master, byte for byte", [](TestCase &t)
        {
            const std::string master = readFile(PS2X_PNACH_MASTER_PATH);
            t.IsTrue(!master.empty(), "the master is read (PS2X_PNACH_MASTER_PATH)");
            t.IsTrue(std::string(pf::kPnachMaster) == lf(master), "the embed is the master's tracked (LF) bytes");
            t.IsTrue(std::string(pf::kPnachMaster).find('\r') == std::string::npos, "the embed is LF on every host");
            t.IsTrue(master.find("E00327BD") != std::string::npos, "the guard: never an unguarded 0x2CC670 write");
            t.IsTrue(std::string(pf::kPnachName) == "0F6FC6CF.pnach", "the pnach's name is the r0001 CRC");
            t.IsTrue(std::string(pf::kIniName) == "PCSX2.ini" && std::string(pf::kPortableMarker) == "portable.txt",
                     "the ini and the portable marker");
        });

        tc.Run("pcsx2_files: the DNS pick -- dotted stays, a name resolves, a failure names the name (Review Focus 3)", [](TestCase &t)
        {
            launcher::Pcsx2Config c;                      // unzipped -> socom.scotho.com
            auto resolver = [](const std::string &n) { return n == "socom.scotho.com" ? std::string("3.143.65.100") : std::string(); };
            t.IsTrue(pf::dnsServerFor(c, resolver).ip == "3.143.65.100", "the preset's name resolves");
            t.IsTrue(pf::dnsServerFor(c, resolver).error.empty(), "and no error");
            c.serverPreset = "custom"; c.server = "203.0.113.3";
            t.IsTrue(pf::dnsServerFor(c, resolver).ip == "203.0.113.3", "a dotted address stays");
            c.server = "nowhere.invalid";
            const pf::DnsPick p = pf::dnsServerFor(c, resolver);
            t.IsTrue(p.ip.empty(), "an unresolved name has no address");
            t.IsTrue(p.error.find("nowhere.invalid") != std::string::npos, "the error names the name");
            t.IsTrue(p.error == "cannot resolve nowhere.invalid -- check your connection", "the exact error text");
            c.server = " 203.0.113.3 ";                      // spaces: not dotted, not a name either
            t.IsTrue(!pf::dnsServerFor(c, resolver).error.empty(), "spaces are refused");
            t.IsTrue(pf::dnsServerFor(c, resolver).ip.empty(), "and give no address");
            t.IsTrue(pf::isDottedIpv4("3.143.65.100"), "dotted");
            t.IsTrue(!pf::isDottedIpv4("3.143.65."), "a missing octet");
            t.IsTrue(!pf::isDottedIpv4("300.1.1.1"), "an octet over 255");
        });

        tc.Run("pcsx2_files: writeIfDifferent writes once, keeps a .bak once, and is quiet when equal", [](TestCase &t)
        {
            const fs::path dir = fs::temp_directory_path() / "s18_wid";
            fs::remove_all(dir);
            const fs::path p = dir / "patches" / "0F6FC6CF.pnach";
            std::string err;
            t.IsTrue(pf::writeIfDifferent(p, "one", "20261001T000000Z", err), "the first write, the folders made");
            t.IsTrue(err.empty(), "no error");
            t.IsTrue(!pf::writeIfDifferent(p, "one", "20261001T000001Z", err), "equal bytes: no write");
            t.IsTrue(!fs::exists(dir / "patches" / "0F6FC6CF.pnach.bak-20261001T000001Z"), "and no .bak");
            t.IsTrue(pf::writeIfDifferent(p, "two", "20261001T000002Z", err), "different bytes: written");
            t.IsTrue(fs::exists(dir / "patches" / "0F6FC6CF.pnach.bak-20261001T000002Z"), "the old file kept as .bak");
            t.IsTrue(readFile(dir / "patches" / "0F6FC6CF.pnach.bak-20261001T000002Z") == "one", "the .bak holds the old bytes");
            t.IsTrue(readFile(p) == "two", "the file holds the new bytes");
            t.IsTrue(pf::writeIfDifferent(p, "three", "20261001T000002Z", err), "a third write with the same stamp");
            t.IsTrue(readFile(dir / "patches" / "0F6FC6CF.pnach.bak-20261001T000002Z") == "one", "a .bak is never overwritten");
            t.IsTrue(readFile(p) == "three", "the file holds the third bytes");
            fs::remove_all(dir);
        });
    });
}
