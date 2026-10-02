// Sprint 18 T4 (R341): see launcher/pcsx2_install.h.
#include "launcher/pcsx2_install.h"

#include "json_reader.h"

#include <cctype>
#include <cstdlib>
#include <cstring>

namespace launcher::pcsx2install
{
    namespace
    {
        std::string lower(std::string s)
        {
            for (char &c : s)
                c = static_cast<char>(std::tolower(static_cast<unsigned char>(c)));
            return s;
        }

        bool endsWith(const std::string &s, const std::string &suffix)
        {
            return s.size() >= suffix.size() && s.compare(s.size() - suffix.size(), suffix.size(), suffix) == 0;
        }

        std::string trim(const std::string &s)
        {
            const char *ws = " \t\r\n";
            const size_t first = s.find_first_not_of(ws);
            if (first == std::string::npos)
                return {};
            return s.substr(first, s.find_last_not_of(ws) - first + 1);
        }

        bool isLowerHex64(const std::string &s)
        {
            if (s.size() != 64)
                return false;
            for (char c : s)
                if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f')))
                    return false;
            return true;
        }

        // http://127.0.0.1:<port> or http://localhost:<port>, a port of 1-65535, then the end or a /path with no
        // userinfo, backslash or space in it.
        bool isLoopbackUrl(const std::string &v)
        {
            for (const char *prefix : {"http://127.0.0.1:", "http://localhost:"})
            {
                const size_t n = std::strlen(prefix);
                if (v.compare(0, n, prefix) != 0)
                    continue;
                size_t at = n;
                while (at < v.size() && std::isdigit(static_cast<unsigned char>(v[at])))
                    ++at;
                const std::string port = v.substr(n, at - n);
                if (port.empty() || port.size() > 5 || std::atoi(port.c_str()) <= 0 || std::atoi(port.c_str()) > 65535)
                    return false;
                if (at == v.size())
                    return true;
                if (v[at] != '/')
                    return false;
                for (size_t i = at; i < v.size(); ++i)
                {
                    const unsigned char c = static_cast<unsigned char>(v[i]);
                    if (c == '@' || c == '\\' || c <= ' ' || c >= 0x7F)
                        return false;
                }
                return true;
            }
            return false;
        }

        // The scheme and host of an absolute URL, lower-case. False for anything without "://", with userinfo or
        // a backslash in the authority, a non-numeric port, or a host outside [a-z0-9.-].
        bool schemeAndHost(const std::string &url, std::string &scheme, std::string &host)
        {
            const size_t sep = url.find("://");
            if (sep == std::string::npos || sep == 0)
                return false;
            scheme = lower(url.substr(0, sep));
            const size_t start = sep + 3;
            const size_t end = url.find_first_of("/?#", start);
            const std::string authority = url.substr(start, end == std::string::npos ? std::string::npos : end - start);
            if (authority.empty() || authority.find_first_of("@\\") != std::string::npos)
                return false;
            const size_t colon = authority.find(':');
            host = lower(authority.substr(0, colon));
            if (colon != std::string::npos)
            {
                const std::string port = authority.substr(colon + 1);
                if (port.empty() || port.size() > 5)
                    return false;
                for (char c : port)
                    if (!std::isdigit(static_cast<unsigned char>(c)))
                        return false;
            }
            if (host.empty())
                return false;
            for (char c : host)
                if (!((c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '.' || c == '-'))
                    return false;
            return true;
        }

        struct AssetFields
        {
            std::string name, digest, url;
            uint64_t size = 0;
        };

        // A string value, or null (read as ""); false on anything else.
        bool stringOrNull(detail::JsonReader &r, std::string &out)
        {
            out.clear();
            if (r.peek() == '"')
                return r.string(out);
            std::string raw;
            return r.scalar(raw) && raw == "null";
        }

        bool readAsset(detail::JsonReader &r, AssetFields &a)
        {
            if (!r.take('{'))
                return r.skipValue();   // not an object: not an asset, skipped
            if (r.take('}'))
                return true;
            for (;;)
            {
                std::string key;
                if (!r.string(key) || !r.take(':'))
                    return false;
                if (key == "name")
                {
                    if (!stringOrNull(r, a.name))
                        return false;
                }
                else if (key == "digest")
                {
                    if (!stringOrNull(r, a.digest))
                        return false;
                }
                else if (key == "browser_download_url")
                {
                    if (!stringOrNull(r, a.url))
                        return false;
                }
                else if (key == "size")
                {
                    std::string raw;
                    if (!r.scalar(raw))
                        return false;
                    char *end = nullptr;
                    const unsigned long long v = std::strtoull(raw.c_str(), &end, 10);
                    a.size = (end != nullptr && *end == '\0' && raw[0] != '-') ? static_cast<uint64_t>(v) : 0;
                }
                else if (!r.skipValue(1))
                    return false;
                if (r.take(','))
                    continue;
                return r.take('}');
            }
        }
    }

    std::string releasesApi(const char *envValue)
    {
        if (envValue == nullptr || *envValue == '\0')
            return kReleasesApi;
        const std::string v = envValue;
        return isLoopbackUrl(v) ? v : std::string(kReleasesApi);
    }

    bool parseLatestRelease(const std::string &json, Release &out, std::string &why)
    {
        out = Release{};
        why.clear();
        auto refuse = [&](const std::string &sentence)
        {
            out = Release{};
            why = sentence;
            return false;
        };

        detail::JsonReader r(json);
        std::string message, tag;
        std::vector<AssetFields> assets;
        bool sawAssets = false;
        if (!r.take('{'))
            return refuse("the release answer from GitHub is not JSON (an empty or broken reply)");
        if (!r.take('}'))
        {
            for (;;)
            {
                std::string key;
                if (!r.string(key) || !r.take(':'))
                    return refuse("the release answer from GitHub is not valid JSON");
                bool ok = true;
                if (key == "message")
                    ok = r.peek() == '"' ? r.string(message) : r.skipValue(1);
                else if (key == "tag_name")
                    ok = stringOrNull(r, tag);
                else if (key == "assets")
                {
                    sawAssets = true;
                    if (!r.take('['))
                        ok = r.skipValue(1);
                    else if (!r.take(']'))
                    {
                        for (;;)
                        {
                            AssetFields a;
                            if (!readAsset(r, a))
                            {
                                ok = false;
                                break;
                            }
                            assets.push_back(a);
                            if (r.take(','))
                                continue;
                            ok = r.take(']');
                            break;
                        }
                    }
                }
                else
                    ok = r.skipValue(1);
                if (!ok)
                    return refuse("the release answer from GitHub is not valid JSON");
                if (r.take(','))
                    continue;
                if (!r.take('}'))
                    return refuse("the release answer from GitHub is not valid JSON");
                break;
            }
        }

        // An error body (a rate limit, "Not Found") carries "message" and no release: its own words are the reason.
        if (!message.empty())
            return refuse("GitHub did not give the latest PCSX2 release: " + message);
        if (tag.empty())
            return refuse("the release answer from GitHub has no tag_name, so there is no release to install");
        if (!sawAssets)
            return refuse("the PCSX2 release " + tag + " lists no assets");

        for (const AssetFields &a : assets)
        {
            if (!endsWith(a.name, kAssetSuffix))
                continue;
            const std::string prefix = "sha256:";
            const std::string digest = lower(a.digest);
            if (digest.compare(0, prefix.size(), prefix) != 0 || !isLowerHex64(digest.substr(prefix.size())))
                return refuse("no sha256 digest for " + a.name + (a.digest.empty() ? std::string() : " (GitHub gave \"" + a.digest + "\")") +
                              ": the download could not be verified, so it is refused");
            if (a.size == 0)
                return refuse(a.name + " has no size in the release answer, so the download could not be checked");
            if (a.url.rfind("https://", 0) != 0 && !isLoopbackUrl(a.url))
                return refuse(a.name + " has no https download URL in the release answer");
            out.tag = tag;
            out.assetName = a.name;
            out.url = a.url;
            out.sha256 = digest.substr(prefix.size());
            out.bytes = a.size;
            return true;
        }
        return refuse(std::string("the PCSX2 release ") + tag + " has no *" + kAssetSuffix + " asset for Windows");
    }

    std::filesystem::path installDir(const std::filesystem::path &launcherDir)
    {
        return launcherDir / "pcsx2";
    }

    bool redirectAllowed(const std::string &fromUrl, const std::string &toUrl)
    {
        std::string fromScheme, fromHost, toScheme, toHost;
        if (!schemeAndHost(fromUrl, fromScheme, fromHost) || !schemeAndHost(toUrl, toScheme, toHost))
            return false;
        if (fromScheme != "https" || toScheme != "https")
            return false;
        if (fromHost != "github.com" && fromHost != "api.github.com")
            return false;
        const std::string suffix = ".githubusercontent.com";
        if (!endsWith(toHost, suffix) || toHost.size() == suffix.size())
            return false;
        // A label before the suffix: "x.githubusercontent.com", never ".githubusercontent.com" or "a..githubusercontent.com".
        const char before = toHost[toHost.size() - suffix.size() - 1];
        return before != '.' && toHost[0] != '.';
    }

    std::vector<std::string> extractArgv(const std::string &systemRoot, const std::filesystem::path &archive,
                                         const std::filesystem::path &dest)
    {
        std::string root = systemRoot.empty() ? std::string("C:\\Windows") : systemRoot;
        while (root.size() > 1 && (root.back() == '\\' || root.back() == '/'))
            root.pop_back();
        return {root + "\\System32\\tar.exe", "-xf", archive.string(), "-C", dest.string()};
    }

    std::string pickAdapter(const std::vector<Adapter> &adapters, const std::string &preferred)
    {
        if (adapters.empty())
            return {};
        if (!preferred.empty())
            for (const Adapter &a : adapters)
                if (a.guid == preferred)
                    return a.guid;
        for (const Adapter &a : adapters)
            if (a.hasGateway)
                return a.guid;
        return adapters.front().guid;
    }

    std::string versionLine(const std::string &exe, const std::string &markerText)
    {
        if (exe.empty())
            return {};
        const std::string tag = trim(markerText.substr(0, markerText.find_first_of("\r\n")));
        if (tag.empty())
            return "PCSX2 (your own copy)";
        return "PCSX2 " + tag + " (installed by the launcher)";
    }
}
