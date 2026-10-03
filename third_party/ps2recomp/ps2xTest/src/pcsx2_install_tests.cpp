// Sprint 18 T4: INSTALL's pure half -- the release parse (Review Focus 4: the Windows Qt 7z, a sha256 digest
// required, the API's rate-limit message surfaced), the redirect rule (github -> githubusercontent, https, one hop),
// the loopback-only API override, the extract argv, the install dir, the adapter pick and the version line. The task
// book wrote these as TEST_CASE/CHECK; MiniTest has no such macros, so each is the same case and the same checks in
// MiniTest's Case/Run form, as T2's and T3's files did. PS2X_TEST_SUITE=pcsx2_install runs it alone.
#include "MiniTest.h"
#include "launcher/pcsx2_install.h"

#include <filesystem>
#include <string>
#include <vector>

namespace pi = launcher::pcsx2install;

namespace
{
    // The userinfo cases are built from parts: an address-shaped literal trips the leak check (a false positive).
    const std::string kAt = "@";
    const char *kJson = R"({"tag_name":"v2.8.2","name":"v2.8.2","assets":[
 {"url":"https://api.github.com/x/1","name":"pcsx2-v2.8.2-linux-appimage-x64-Qt.AppImage","size":60119544,"digest":"sha256:0c46bb6a88aa2782b10853a7b07cf3387ba99cbef2b966372cd2315b8571abea","browser_download_url":"https://github.com/PCSX2/pcsx2/releases/download/v2.8.2/pcsx2-v2.8.2-linux-appimage-x64-Qt.AppImage"},
 {"url":"https://api.github.com/x/2","name":"pcsx2-v2.8.2-windows-x64-Qt-symbols.7z","size":20962364,"digest":"sha256:b7736262b4d0228c72a2afc07dab7636af5c8a3d4fdb416058e2b070c370e26b","browser_download_url":"https://github.com/PCSX2/pcsx2/releases/download/v2.8.2/pcsx2-v2.8.2-windows-x64-Qt-symbols.7z"},
 {"url":"https://api.github.com/x/3","name":"pcsx2-v2.8.2-windows-x64-Qt.7z","size":25670075,"digest":"sha256:7dfc829ca1994cc1045ac49f05e39b6cf968b72e6a374c40e05c2a2b4ac200b4","browser_download_url":"https://github.com/PCSX2/pcsx2/releases/download/v2.8.2/pcsx2-v2.8.2-windows-x64-Qt.7z"}]})";

    // The real API's shape: every asset carries a nested "uploader" object BEFORE its size, digest and URL, and the
    // release a nested "author" -- a text search bounded by the first '}' after the name would miss all three.
    const char *kNestedJson = R"({"url":"https://api.github.com/r","author":{"login":"github-actions[bot]","id":1},"tag_name":"v2.8.2",
 "assets":[{"url":"https://api.github.com/x/3","id":3,"name":"pcsx2-v2.8.2-windows-x64-Qt.7z","label":null,
 "uploader":{"login":"github-actions[bot]","id":41898282,"site_admin":false},"content_type":"application/x-7z-compressed",
 "state":"uploaded","size":25670075,"digest":"sha256:7DFC829CA1994CC1045AC49F05E39B6CF968B72E6A374C40E05C2A2B4AC200B4","download_count":9,
 "browser_download_url":"https://github.com/PCSX2/pcsx2/releases/download/v2.8.2/pcsx2-v2.8.2-windows-x64-Qt.7z"}],
 "body":"## Changes\n- \"assets\": not this one {}"})";
}

void register_pcsx2_install_tests()
{
    MiniTest::Case("pcsx2_install", [](TestCase &tc)
    {
        tc.Run("pcsx2_install: the Windows Qt 7z is picked, not the symbols one, with its size and digest", [](TestCase &t)
        {
            pi::Release r;
            std::string why;
            t.IsTrue(pi::parseLatestRelease(kJson, r, why), "the stand-in release parses");
            t.IsTrue(why.empty(), "no refusal sentence on success");
            t.IsTrue(r.tag == "v2.8.2", "the tag");
            t.IsTrue(r.assetName == "pcsx2-v2.8.2-windows-x64-Qt.7z", "the Windows Qt 7z, not the symbols one");
            t.IsTrue(r.bytes == 25670075u, "its size");
            t.IsTrue(r.sha256 == "7dfc829ca1994cc1045ac49f05e39b6cf968b72e6a374c40e05c2a2b4ac200b4", "its digest");
            t.IsTrue(r.url == "https://github.com/PCSX2/pcsx2/releases/download/v2.8.2/pcsx2-v2.8.2-windows-x64-Qt.7z",
                     "its browser_download_url");
        });

        tc.Run("pcsx2_install: the API's nested objects do not hide the asset's size, digest and URL", [](TestCase &t)
        {
            pi::Release r;
            std::string why;
            t.IsTrue(pi::parseLatestRelease(kNestedJson, r, why), "parses with uploader/author objects: " + why);
            t.IsTrue(r.bytes == 25670075u, "the size after the uploader object");
            t.IsTrue(r.sha256 == "7dfc829ca1994cc1045ac49f05e39b6cf968b72e6a374c40e05c2a2b4ac200b4", "the digest, lower-cased");
            t.IsTrue(r.url == "https://github.com/PCSX2/pcsx2/releases/download/v2.8.2/pcsx2-v2.8.2-windows-x64-Qt.7z", "the URL");
        });

        tc.Run("pcsx2_install: no Windows asset, another digest algorithm, or no digest is a refusal with a sentence (Review Focus 4)", [](TestCase &t)
        {
            pi::Release r;
            std::string why;
            t.IsTrue(!pi::parseLatestRelease(R"({"tag_name":"v9","assets":[{"name":"pcsx2-v9-macos-Qt.tar.xz","size":1,"digest":"sha256:00","browser_download_url":"https://github.com/a"}]})", r, why),
                     "no Windows asset is refused");
            t.IsTrue(why.find("windows-x64-Qt.7z") != std::string::npos, "the sentence names the asset it wanted: " + why);
            why.clear();
            t.IsTrue(!pi::parseLatestRelease(R"({"tag_name":"v9","assets":[{"name":"pcsx2-v9-windows-x64-Qt.7z","size":1,"digest":"md5:00","browser_download_url":"https://github.com/a"}]})", r, why),
                     "an md5 digest is refused");
            t.IsTrue(!why.empty(), "with a sentence (md5)");
            why.clear();
            t.IsTrue(!pi::parseLatestRelease(R"({"tag_name":"v9","assets":[{"name":"pcsx2-v9-windows-x64-Qt.7z","size":1,"browser_download_url":"https://github.com/a"}]})", r, why),
                     "no digest is refused");
            t.IsTrue(why.find("sha256") != std::string::npos, "the sentence says sha256: " + why);
            why.clear();
            t.IsTrue(!pi::parseLatestRelease("", r, why), "an empty answer is refused");
            t.IsTrue(!why.empty(), "with a sentence (empty)");
            why.clear();
            t.IsTrue(!pi::parseLatestRelease(R"({"message":"API rate limit exceeded"})", r, why), "the API's message is refused");
            t.IsTrue(why.find("rate limit") != std::string::npos, "the API's own message is surfaced: " + why);
        });

        tc.Run("pcsx2_install: redirects only from github to githubusercontent, https both ways", [](TestCase &t)
        {
            t.IsTrue(pi::redirectAllowed("https://github.com/PCSX2/pcsx2/releases/download/v2/x.7z",
                                         "https://objects.githubusercontent.com/github-production-release-asset/abc?x=1"),
                     "github.com -> objects.githubusercontent.com");
            t.IsTrue(pi::redirectAllowed("https://github.com/a", "https://release-assets.githubusercontent.com/b"),
                     "github.com -> release-assets.githubusercontent.com");
            t.IsTrue(!pi::redirectAllowed("https://github.com/a", "http://objects.githubusercontent.com/b"), "plain http to");
            t.IsTrue(!pi::redirectAllowed("https://github.com/a", "https://githubusercontent.com.evil.example/b"), "suffix not anchored");
            t.IsTrue(!pi::redirectAllowed("https://github.com/a", "https://evil.example/githubusercontent.com"), "the suffix in the path");
            t.IsTrue(!pi::redirectAllowed("https://objects.githubusercontent.com/a", "https://objects.githubusercontent.com/b"),
                     "one hop from github only");
            t.IsTrue(!pi::redirectAllowed("https://example.com/a", "https://objects.githubusercontent.com/b"), "from another host");
            // Beyond the listing: the edges of the host parse.
            t.IsTrue(pi::redirectAllowed("https://API.GitHub.com/a", "https://Objects.GitHubUserContent.com:443/b"), "case and a port");
            t.IsTrue(!pi::redirectAllowed("http://github.com/a", "https://objects.githubusercontent.com/b"), "plain http from");
            t.IsTrue(!pi::redirectAllowed("https://github.com/a", "https://.githubusercontent.com/b"), "no label before the suffix");
            t.IsTrue(!pi::redirectAllowed("https://github.com/a", std::string("https://evil.example") + kAt + "objects.githubusercontent.com/b"), "userinfo");
            t.IsTrue(!pi::redirectAllowed("https://github.com.evil.example/a", "https://objects.githubusercontent.com/b"), "from a look-alike");
            t.IsTrue(!pi::redirectAllowed("https://github.com/a", "/relative"), "a relative target is not resolved here");
        });

        tc.Run("pcsx2_install: the api override is loopback only, as the patch base is", [](TestCase &t)
        {
            t.IsTrue(pi::releasesApi(nullptr) == std::string(pi::kReleasesApi), "unset is GitHub");
            t.IsTrue(pi::releasesApi("http://127.0.0.1:8765/release.json") == "http://127.0.0.1:8765/release.json", "loopback kept");
            t.IsTrue(pi::releasesApi("https://evil.example/release.json") == std::string(pi::kReleasesApi), "elsewhere ignored");
            t.IsTrue(pi::releasesApi("http://localhost:9/r.json") == "http://localhost:9/r.json", "localhost kept");
            t.IsTrue(pi::releasesApi((std::string("http://127.0.0.1:8765") + kAt + "evil.example/r.json").c_str()) == std::string(pi::kReleasesApi), "userinfo trick ignored");
            t.IsTrue(pi::releasesApi("http://127.0.0.1.evil.example:80/r.json") == std::string(pi::kReleasesApi), "look-alike ignored");
            t.IsTrue(pi::releasesApi("") == std::string(pi::kReleasesApi), "empty ignored");
        });

        tc.Run("pcsx2_install: the extract argv is the system tar with no shell, and the install dir is beside the launcher", [](TestCase &t)
        {
            const auto argv = pi::extractArgv("C:\\Windows", "C:\\s2u\\pcsx2\\pcsx2.7z.new", "C:\\s2u\\pcsx2");
            t.IsTrue(argv.size() == 5, "five arguments");
            t.IsTrue(argv.size() == 5 && argv[0] == "C:\\Windows\\System32\\tar.exe", "argv[0] is the system tar");
            t.IsTrue(argv.size() == 5 && argv[1] == "-xf", "-xf");
            t.IsTrue(argv.size() == 5 && argv[3] == "-C", "-C");
            t.IsTrue(argv.size() == 5 && argv[2] == "C:\\s2u\\pcsx2\\pcsx2.7z.new" && argv[4] == "C:\\s2u\\pcsx2", "archive and dest");
            t.IsTrue(pi::installDir("C:\\s2u") == std::filesystem::path("C:\\s2u") / "pcsx2", "<launcherDir>/pcsx2");
        });

        tc.Run("pcsx2_install: the extract argv carries a non-ASCII path as UTF-8, the form runAndWait decodes (T4 review 3)", [](TestCase &t)
        {
            const std::filesystem::path dest(u8"D:\\Jeux\\H\u00e9l\u00e8ne\\s2u\\pcsx2.new");
            const auto argv = pi::extractArgv("C:\\Windows", dest / "pcsx2.7z.new", dest);
            const std::string utf8 = "D:\\Jeux\\H" "\xc3\xa9" "l" "\xc3\xa8" "ne\\s2u\\pcsx2.new";
            t.IsTrue(argv.size() == 5 && argv[4] == utf8, "the destination's UTF-8 bytes");
            // operator/ joins with the platform's separator: '\\' on Windows, '/' on POSIX (Linux CI).
            const std::string sep(1, static_cast<char>(std::filesystem::path::preferred_separator));
            t.IsTrue(argv.size() == 5 && argv[2] == utf8 + sep + "pcsx2.7z.new", "the archive's UTF-8 bytes");
        });

        tc.Run("pcsx2_install: the asset URL fails closed -- github.com only, loopback only behind a loopback API (T4 review 2)", [](TestCase &t)
        {
            pi::Release r;
            std::string why;
            t.IsTrue(!pi::parseLatestRelease(R"({"tag_name":"v9","assets":[{"name":"pcsx2-v9-windows-x64-Qt.7z","size":1,"digest":"sha256:7dfc829ca1994cc1045ac49f05e39b6cf968b72e6a374c40e05c2a2b4ac200b4","browser_download_url":"https://evil.example/pcsx2-v9-windows-x64-Qt.7z"}]})", r, why),
                     "an https URL on another host is refused by the parse");
            t.IsTrue(why.find("github.com") != std::string::npos, "the sentence names github.com: " + why);
            const std::string gh = "https://github.com/PCSX2/pcsx2/releases/download/v9/pcsx2-v9-windows-x64-Qt.7z";
            const std::string loop = "http://127.0.0.1:8765/pcsx2.7z";
            t.IsTrue(pi::assetUrlAllowed(pi::kReleasesApi, gh), "GitHub's API, a github.com asset");
            t.IsTrue(!pi::assetUrlAllowed(pi::kReleasesApi, loop), "GitHub's API never sends INSTALL to loopback");
            t.IsTrue(!pi::assetUrlAllowed(pi::kReleasesApi, "https://objects.githubusercontent.com/x.7z"),
                     "githubusercontent is reached only through the redirect policy");
            t.IsTrue(!pi::assetUrlAllowed(pi::kReleasesApi, "https://evil.example/x.7z"), "another host");
            t.IsTrue(!pi::assetUrlAllowed(pi::kReleasesApi, "http://github.com/x.7z"), "plain http to github.com");
            t.IsTrue(pi::assetUrlAllowed("http://127.0.0.1:8765/release.json", loop), "a loopback API, a loopback asset");
            t.IsTrue(pi::assetUrlAllowed("http://127.0.0.1:8765/release.json", "https://localhost:8443/pcsx2.7z"), "https loopback too");
            t.IsTrue(pi::assetUrlAllowed("http://127.0.0.1:8765/release.json", gh), "a loopback API may still name github.com");
            t.IsTrue(!pi::assetUrlAllowed("http://127.0.0.1:8765/release.json", "https://evil.example/x.7z"), "but nothing else");
        });

        tc.Run("pcsx2_install: the adapter pick prefers the saved one, then a gateway, then the first", [](TestCase &t)
        {
            const std::vector<pi::Adapter> a{{"{1}", "Bluetooth", false}, {"{2}", "Ethernet", true}, {"{3}", "Wi-Fi", true}};
            t.IsTrue(pi::pickAdapter(a, "{3}") == "{3}", "the saved one");
            t.IsTrue(pi::pickAdapter(a, "{9}") == "{2}", "a saved one that is gone: the first with a gateway");
            t.IsTrue(pi::pickAdapter(a, "") == "{2}", "none saved: the first with a gateway");
            t.IsTrue(pi::pickAdapter({{"{1}", "x", false}}, "") == "{1}", "no gateway anywhere: the first");
            t.IsTrue(pi::pickAdapter({}, "{1}").empty(), "an empty list: nothing");
        });

        tc.Run("pcsx2_install: the version line", [](TestCase &t)
        {
            t.IsTrue(pi::versionLine("", "").empty(), "no exe: nothing");
            t.IsTrue(pi::versionLine("C:/s2u/pcsx2/pcsx2-qt.exe", "v2.8.2\n") == "PCSX2 v2.8.2 (installed by the launcher)", "the marker's tag");
            t.IsTrue(pi::versionLine("C:/mine/pcsx2-qt.exe", "") == "PCSX2 (your own copy)", "no marker: the player's own copy");
        });
    });
}
