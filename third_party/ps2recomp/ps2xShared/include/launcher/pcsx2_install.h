#pragma once

// Sprint 18 T4 (R341, the spec's R-C): INSTALL -- PCSX2 from its official GitHub release, never from us. The pure
// half: which release asset, which digest, which redirects, which argv extracts it, which adapter, what the
// version line says. The transport (win32glue::httpRequest, httpDownloadFollowing, runAndWait) is the launcher's
// glue; nothing in this header opens a socket or starts a process.

#include <cstdint>
#include <filesystem>
#include <string>
#include <vector>

namespace launcher::pcsx2install
{
    constexpr const char *kReleasesApi = "https://api.github.com/repos/PCSX2/pcsx2/releases/latest";
    constexpr const char *kReleasesApiEnv = "PS2X_LAUNCHER_PCSX2_API";   // TEST-ONLY, loopback only (patchfetch::patchBase's rule)
    constexpr const char *kAssetSuffix = "-windows-x64-Qt.7z";
    constexpr const char *kVersionMarker = "socom_unzipped_pcsx2.txt";    // the tag, written beside pcsx2-qt.exe by INSTALL
    constexpr const char *kExeName = "pcsx2-qt.exe";

    struct Release
    {
        std::string tag, assetName, url, sha256;
        uint64_t bytes = 0;
    };

    // kReleasesApi unless `envValue` (PS2X_LAUNCHER_PCSX2_API, may be null) is a loopback test server: exactly
    // http://127.0.0.1:<port> or http://localhost:<port>, optionally followed by a /path -- the rule
    // bugreport::apiBase and patchfetch::patchBase hold, with the path the release JSON's file needs. Anything else
    // is ignored, so nobody can point a player's INSTALL somewhere else with an environment variable.
    std::string releasesApi(const char *envValue);

    // The GitHub "latest release" answer, parsed as JSON (not searched as text: each asset carries a nested
    // "uploader" object). Picks the first asset whose name ends in kAssetSuffix (so never the -symbols.7z), with
    // its size, its "sha256:<64 hex>" digest and its browser_download_url (https, or plain http to a loopback test
    // server). False with one sentence in `why` on every refusal: not JSON, the API's own "message" (a rate limit),
    // no tag, no Windows asset, no sha256 digest, no size, no usable URL.
    bool parseLatestRelease(const std::string &json, Release &out, std::string &why);

    // T4 review 2, fail closed: the asset may be fetched from `assetUrl` only when it is https on exactly github.com
    // (a *.githubusercontent.com host is reached only through redirectAllowed), or a loopback http/https URL when
    // `apiUrl` -- what releasesApi answered -- is itself the loopback override. GitHub's answer never sends INSTALL
    // to loopback, nor anywhere else.
    bool assetUrlAllowed(const std::string &apiUrl, const std::string &assetUrl);

    // <launcherDir>/pcsx2
    std::filesystem::path installDir(const std::filesystem::path &launcherDir);

    // github.com or api.github.com (https) may redirect to an https host ending in ".githubusercontent.com"; nothing else.
    // One hop from github only: a githubusercontent host may not redirect again. Hosts compared lower-case, the
    // suffix anchored at a label boundary with a label before it; any userinfo ('@') or backslash is refused.
    bool redirectAllowed(const std::string &fromUrl, const std::string &toUrl);

    // {"<SystemRoot>\System32\tar.exe", "-xf", archive, "-C", dest} -- the system's bsdtar, run with an argv, no
    // shell. An empty systemRoot reads as C:\Windows.
    std::vector<std::string> extractArgv(const std::string &systemRoot, const std::filesystem::path &archive,
                                         const std::filesystem::path &dest);

    struct Adapter
    {
        std::string guid;
        std::string name;
        bool hasGateway = false;
    };
    // preferred when it is in the list; else the first with a gateway; else the first; "" when the list is empty.
    std::string pickAdapter(const std::vector<Adapter> &adapters, const std::string &preferred);

    // "PCSX2 <tag> (installed by the launcher)" / "PCSX2 (your own copy)" / "" when exe is empty.
    // `markerText` is the kVersionMarker file's contents beside the exe ("" when there is none).
    std::string versionLine(const std::string &exe, const std::string &markerText);
}
