#include "launcher/launcher_config.h"
#include "ps2x/exit_codes.h"

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

    bool presetAvailable(const ServerPreset &preset)
    {
        if (preset.address[0] == '\0')
            return true;   // Custom: the player types the address
        return std::string(preset.address).find("_TBC") == std::string::npos;
    }

    namespace
    {
        // The preset a config falls back to when the one it names cannot be played.
        const ServerPreset &playableFallback()
        {
            for (const ServerPreset &p : kServerPresets)
                if (p.address[0] != '\0' && presetAvailable(p))
                    return p;
            return kServerPresets[0];
        }
    }

    std::string effectiveServer(const Config &c)
    {
        const ServerPreset *preset = findServerPreset(c.serverPreset);
        // A preset whose server does not exist yet must never reach the game: a config that still names one
        // (the owner's did) plays on the project's own server instead of on a placeholder string.
        if (preset && !presetAvailable(*preset))
            preset = &playableFallback();
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
        out += std::string("  \"fpsOverlay\": ") + (c.fpsOverlay ? "true" : "false") + ",\n";
        out += "  \"audioVolume\": " + std::to_string(c.audioVolume) + ",\n";
        out += std::string("  \"mouseLook\": ") + (c.mouseLook ? "true" : "false") + ",\n";
        char sens[32];
        std::snprintf(sens, sizeof(sens), "%g", c.mouseSensitivity);
        out += std::string("  \"mouseSensitivity\": ") + sens + ",\n";
        out += "  \"gamepadIndex\": " + std::to_string(c.gamepadIndex) + ",\n";
        char dz[32];
        std::snprintf(dz, sizeof(dz), "%g", c.padDeadZone);
        out += std::string("  \"padDeadZone\": ") + dz + ",\n";
        out += "  \"micDevice\": " + quote(c.micDevice) + ",\n";
        out += "  \"serverPreset\": " + quote(c.serverPreset) + ",\n";
        out += "  \"server\": " + quote(c.server) + ",\n";
        out += "  \"profile\": " + quote(c.profile) + ",\n";
        out += std::string("  \"secondInstance\": ") + (c.secondInstance ? "true" : "false") + "\n";
        out += "}\n";
        return out;
    }

    std::string monitorSizeOrEmpty(int width, int height)
    {
        if (width <= 0 || height <= 0)
            return std::string();   // raylib has no monitor yet: store nothing rather than "0x0"
        return std::to_string(width) + "x" + std::to_string(height);
    }

    namespace
    {
        // "<w>x<h>" with a zero (or negative, or unreadable) dimension is not a window size, whoever wrote it:
        // an older build's "Match display", a hand-edited config.json. Anything that is not of that shape at all
        // ("fullscreen") is left to the runtime's own parser.
        bool isUsableWindowSize(const std::string &value)
        {
            const size_t x = value.find_first_of("xX");
            if (x == std::string::npos)
                return true;
            const std::string w = value.substr(0, x);
            const std::string h = value.substr(x + 1);
            if (w.empty() || h.empty())
                return true;
            return std::atoi(w.c_str()) > 0 && std::atoi(h.c_str()) > 0;
        }
    }

    bool fromJson(const std::string &json, Config &out)
    {
        out = Config{};   // malformed input leaves the defaults
        Config c;
        bool sawServer = false, sawPreset = false;   // a pre-picker config: a typed server and no preset
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
                if (key == "isoPath" || key == "presentFilter" || key == "windowSize" || key == "server" || key == "serverPreset" || key == "profile" || key == "micDevice")
                {
                    std::string v;
                    if (!p.string(v))
                        return false;
                    if (key == "isoPath") c.isoPath = v;
                    else if (key == "presentFilter") c.presentFilter = v;
                    // Review finding F5: a stored 0x0 (or any zero dimension) keeps the default instead.
                    else if (key == "windowSize") { if (isUsableWindowSize(v)) c.windowSize = v; }
                    else if (key == "server") { c.server = v; sawServer = true; }
                    // a preset we do not know (an older or newer build's) falls back to the typed address
                    else if (key == "serverPreset")
                    {
                        // An unknown id means an older or hand-edited file: keep the typed address. A KNOWN
                        // but unplayable one heals to the server that exists, so the picker opens on it.
                        const ServerPreset *saved = findServerPreset(v);
                        c.serverPreset = saved == nullptr ? std::string("custom")
                                                          : (presetAvailable(*saved) ? v : std::string(playableFallback().id));
                        sawPreset = true;
                    }
                    else if (key == "micDevice") c.micDevice = v;
                    else c.profile = v;
                }
                else if (key == "gsScale" || key == "mouseSensitivity" || key == "mouseLook" || key == "secondInstance" || key == "gamepadIndex" || key == "padDeadZone" || key == "fpsOverlay" || key == "audioVolume")
                {
                    std::string raw;
                    if (!p.scalar(raw))
                        return false;
                    if (key == "gsScale") c.gsScale = std::atoi(raw.c_str());
                    else if (key == "mouseSensitivity") c.mouseSensitivity = std::atof(raw.c_str());
                    else if (key == "mouseLook") c.mouseLook = raw == "true";
                    else if (key == "fpsOverlay") c.fpsOverlay = raw == "true";
                    else if (key == "audioVolume") c.audioVolume = std::atoi(raw.c_str());
                    else if (key == "gamepadIndex") c.gamepadIndex = std::atoi(raw.c_str());
                    else if (key == "padDeadZone") c.padDeadZone = std::atof(raw.c_str());
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
        // Sprint 8 Goal 12: the default preset became the hosted server. A config written before the picker existed
        // carries the player's own address and no preset; it stays theirs instead of silently moving to ours.
        if (sawServer && !sawPreset)
            c.serverPreset = "custom";
        out = c;
        return true;
    }

    std::string exitMessage(int exitCode)
    {
        // Sprint 9 Goal 1: the sentence lives in the one table the runner also reads (ps2x/exit_codes.h).
        return ExitCodes::describe(exitCode);
    }

    std::vector<std::string> mergeEnvironment(const char *const *base, const std::vector<std::string> &ours)
    {
        // Ours, minus anything that is not a KEY=VALUE pair: execve would carry a bare "D" into the child's
        // environ, where nothing can read it back.
        std::vector<std::string> mine;
        mine.reserve(ours.size());
        for (const std::string &o : ours)
            if (o.find('=') != std::string::npos)
                mine.push_back(o);

        std::vector<std::string> merged;
        for (const char *const *p = base; p != nullptr && *p != nullptr; ++p)
        {
            const std::string s(*p);
            const size_t eq = s.find('=');
            const std::string key = eq == std::string::npos ? s : s.substr(0, eq);
            // Windows hands out "=C:=C:\path" per-drive cwd entries; an empty key is not a variable either.
            if (key.empty() || key[0] == '=')
                continue;
            bool overridden = false;
            for (const std::string &o : mine)
                if (o.rfind(key + "=", 0) == 0)
                    overridden = true;
            if (!overridden)
                merged.push_back(s);
        }
        for (const std::string &o : mine)
            merged.push_back(o);
        return merged;
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
        const int volume = c.audioVolume < 0 ? 0 : (c.audioVolume > 100 ? 100 : c.audioVolume);
        env.push_back("PS2X_AUDIO_VOLUME=" + std::to_string(volume));
        const bool sizeUsable = !c.windowSize.empty() && isUsableWindowSize(c.windowSize);
        env.push_back("PS2X_WINDOW_SIZE=" + (sizeUsable ? c.windowSize : Config{}.windowSize));
        if (c.fpsOverlay)
            env.push_back("PS2X_FPS_OVERLAY=1");
        env.push_back("PS2X_SOCOM2_SERVER=" + effectiveServer(c));
        const std::string profile = c.profile.empty() ? std::string("player") : c.profile;
        env.push_back("PS2X_MC_DIR=cards/" + profile + (c.secondInstance ? "_b" : ""));
        // Sprint 7 Task 8: the pad the player picked (only when they picked one -- unset means the runtime's
        // own "first available" rule), and the dead zone, always, so what they tuned is what the game gets.
        if (c.gamepadIndex >= 0)
            env.push_back("PS2X_HOST_GAMEPAD_INDEX=" + std::to_string(c.gamepadIndex));
        char dz[32];
        std::snprintf(dz, sizeof(dz), "%g", c.padDeadZone < 0.0 ? 0.0 : (c.padDeadZone > 0.5 ? 0.5 : c.padDeadZone));
        env.push_back(std::string("PS2X_PAD_DEADZONE=") + dz);
        // Sprint 7 Task 9: only when the player picked one -- unset means the runtime opens no capture device.
        if (!c.micDevice.empty())
            env.push_back("PS2X_MIC_DEVICE=" + c.micDevice);
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
