#include "launcher/launcher_config.h"

#include <cctype>
#include <cstdio>
#include <cstdlib>
#include <map>

// config.json is a flat object of strings, numbers and booleans; a hand-rolled reader/writer covers it (no
// dependency for the launcher). Unknown keys are ignored, missing keys keep their defaults.
namespace launcher
{
    namespace
    {
        std::string quote(const std::string &s)
        {
            std::string out = "\"";
            for (char c : s)
            {
                switch (c)
                {
                case '"': out += "\\\""; break;
                case '\\': out += "\\\\"; break;
                case '\n': out += "\\n"; break;
                case '\r': out += "\\r"; break;
                case '\t': out += "\\t"; break;
                default: out.push_back(c); break;
                }
            }
            out.push_back('"');
            return out;
        }

        struct Parser
        {
            const std::string &s;
            size_t i = 0;
            explicit Parser(const std::string &text) : s(text) {}

            void ws()
            {
                while (i < s.size() && std::isspace(static_cast<unsigned char>(s[i])))
                    ++i;
            }
            bool take(char c)
            {
                ws();
                if (i < s.size() && s[i] == c)
                {
                    ++i;
                    return true;
                }
                return false;
            }
            bool string(std::string &out)
            {
                ws();
                if (i >= s.size() || s[i] != '"')
                    return false;
                ++i;
                out.clear();
                while (i < s.size())
                {
                    const char c = s[i++];
                    if (c == '"')
                        return true;
                    if (c == '\\')
                    {
                        if (i >= s.size())
                            return false;
                        const char e = s[i++];
                        switch (e)
                        {
                        case '"': out.push_back('"'); break;
                        case '\\': out.push_back('\\'); break;
                        case '/': out.push_back('/'); break;
                        case 'n': out.push_back('\n'); break;
                        case 'r': out.push_back('\r'); break;
                        case 't': out.push_back('\t'); break;
                        case 'b': out.push_back('\b'); break;
                        case 'f': out.push_back('\f'); break;
                        case 'u':
                        {
                            if (i + 4 > s.size())
                                return false;
                            const unsigned code = static_cast<unsigned>(std::strtoul(s.substr(i, 4).c_str(), nullptr, 16));
                            i += 4;
                            if (code < 0x80)
                                out.push_back(static_cast<char>(code));
                            else
                                out.push_back('?');   // the config never carries these
                            break;
                        }
                        default: return false;
                        }
                    }
                    else
                        out.push_back(c);
                }
                return false;
            }
            // Skips any JSON value (used for unknown keys). Returns false on malformed input.
            bool skipValue()
            {
                ws();
                if (i >= s.size())
                    return false;
                const char c = s[i];
                if (c == '"')
                {
                    std::string tmp;
                    return string(tmp);
                }
                if (c == '{' || c == '[')
                {
                    const char close = c == '{' ? '}' : ']';
                    ++i;
                    ws();
                    if (take(close))
                        return true;
                    for (;;)
                    {
                        if (c == '{')
                        {
                            std::string key;
                            if (!string(key) || !take(':'))
                                return false;
                        }
                        if (!skipValue())
                            return false;
                        if (take(','))
                            continue;
                        return take(close);
                    }
                }
                // number, true, false, null
                const size_t start = i;
                while (i < s.size() && (std::isalnum(static_cast<unsigned char>(s[i])) || s[i] == '-' || s[i] == '+' || s[i] == '.'))
                    ++i;
                return i > start;
            }
            bool scalar(std::string &raw)
            {
                ws();
                const size_t start = i;
                while (i < s.size() && (std::isalnum(static_cast<unsigned char>(s[i])) || s[i] == '-' || s[i] == '+' || s[i] == '.'))
                    ++i;
                raw = s.substr(start, i - start);
                return !raw.empty();
            }
        };
    }

    const ServerPreset *findServerPreset(const std::string &id)
    {
        for (const ServerPreset &p : kServerPresets)
            if (id == p.id)
                return &p;
        return nullptr;
    }

    std::string effectiveServer(const Config &c)
    {
        const ServerPreset *preset = findServerPreset(c.serverPreset);
        if (preset && preset->address[0] != '\0')
            return preset->address;
        return c.server.empty() ? std::string("127.0.0.1") : c.server;
    }

    std::string toJson(const Config &c)
    {
        std::string out = "{\n";
        out += "  \"isoPath\": " + quote(c.isoPath) + ",\n";
        out += "  \"gsScale\": " + std::to_string(c.gsScale) + ",\n";
        out += "  \"presentFilter\": " + quote(c.presentFilter) + ",\n";
        out += "  \"windowSize\": " + quote(c.windowSize) + ",\n";
        out += std::string("  \"mouseLook\": ") + (c.mouseLook ? "true" : "false") + ",\n";
        char sens[32];
        std::snprintf(sens, sizeof(sens), "%g", c.mouseSensitivity);
        out += std::string("  \"mouseSensitivity\": ") + sens + ",\n";
        out += "  \"serverPreset\": " + quote(c.serverPreset) + ",\n";
        out += "  \"server\": " + quote(c.server) + ",\n";
        out += "  \"profile\": " + quote(c.profile) + ",\n";
        out += std::string("  \"secondInstance\": ") + (c.secondInstance ? "true" : "false") + "\n";
        out += "}\n";
        return out;
    }

    bool fromJson(const std::string &json, Config &out)
    {
        out = Config{};   // malformed input leaves the defaults
        Config c;
        Parser p(json);
        if (!p.take('{'))
            return false;
        if (!p.take('}'))
        {
            for (;;)
            {
                std::string key;
                if (!p.string(key) || !p.take(':'))
                    return false;
                if (key == "isoPath" || key == "presentFilter" || key == "windowSize" || key == "server" || key == "serverPreset" || key == "profile")
                {
                    std::string v;
                    if (!p.string(v))
                        return false;
                    if (key == "isoPath") c.isoPath = v;
                    else if (key == "presentFilter") c.presentFilter = v;
                    else if (key == "windowSize") c.windowSize = v;
                    else if (key == "server") c.server = v;
                    // a preset we do not know (an older or newer build's) falls back to the typed address
                    else if (key == "serverPreset") c.serverPreset = findServerPreset(v) ? v : std::string("custom");
                    else c.profile = v;
                }
                else if (key == "gsScale" || key == "mouseSensitivity" || key == "mouseLook" || key == "secondInstance")
                {
                    std::string raw;
                    if (!p.scalar(raw))
                        return false;
                    if (key == "gsScale") c.gsScale = std::atoi(raw.c_str());
                    else if (key == "mouseSensitivity") c.mouseSensitivity = std::atof(raw.c_str());
                    else if (key == "mouseLook") c.mouseLook = raw == "true";
                    else c.secondInstance = raw == "true";
                }
                else if (!p.skipValue())
                    return false;
                if (p.take(','))
                    continue;
                if (!p.take('}'))
                    return false;
                break;
            }
        }
        out = c;
        return true;
    }

    std::vector<std::string> environmentFor(const Config &c)
    {
        std::vector<std::string> env;
        env.push_back("PS2X_SOCOM2_PAD=1");
        // The runtime mounts the disc from PS2X_CD_IMAGE (game_overrides_socom2.cpp,
        // configureCdImage); without it the verified ISO is ignored and the runtime falls
        // back to hunting for any .iso next to the ELF.
        if (!c.isoPath.empty())
            env.push_back("PS2X_CD_IMAGE=" + c.isoPath);
        env.push_back("PS2X_GS_SCALE=" + std::to_string(c.gsScale < 1 ? 1 : c.gsScale));
        env.push_back("PS2X_PRESENT_FILTER=" + (c.presentFilter.empty() ? std::string("linear") : c.presentFilter));
        env.push_back("PS2X_WINDOW_SIZE=" + (c.windowSize.empty() ? std::string("640x448") : c.windowSize));
        env.push_back("PS2X_SOCOM2_SERVER=" + effectiveServer(c));
        const std::string profile = c.profile.empty() ? std::string("player") : c.profile;
        env.push_back("PS2X_MC_DIR=cards/" + profile + (c.secondInstance ? "_b" : ""));
        if (c.mouseLook)
        {
            env.push_back("PS2X_SOCOM2_MOUSE=1");
            char sens[32];
            std::snprintf(sens, sizeof(sens), "%g", c.mouseSensitivity);
            env.push_back(std::string("PS2X_SOCOM2_MOUSE_SENS=") + sens);
        }
        if (c.secondInstance)
        {
            env.push_back("PS2X_SOCOM2_UDP_SHIFT=2");
            env.push_back("PS2X_SOCOM2_RSA_KEY=b");
        }
        return env;
    }
}
