#include "launcher/pcsx2_config.h"
#include "launcher/launcher_config.h"   // normalizeGameRevision, normalizeServerPreset, effectiveServer

#include "json_reader.h"

// Sprint 18 T2 (R339 = R-A): config.pcsx2.json <-> Pcsx2Config. The same shape as config.json's reader and writer
// (launcher_config.cpp): a flat object of strings, unknown keys ignored, missing keys kept at their defaults, a
// malformed file read as the defaults. Six keys, none of them config.json's meaning.
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
    }

    std::string pcsx2ToJson(const Pcsx2Config &c)
    {
        std::string out = "{\n";
        out += "  \"isoPath\": " + quote(c.isoPath) + ",\n";
        out += "  \"pcsx2Exe\": " + quote(c.pcsx2Exe) + ",\n";
        out += "  \"gameRevision\": " + quote(normalizeGameRevision(c.gameRevision)) + ",\n";
        out += "  \"serverPreset\": " + quote(c.serverPreset) + ",\n";
        out += "  \"server\": " + quote(c.server) + ",\n";
        out += "  \"ethDevice\": " + quote(c.ethDevice) + "\n";
        out += "}\n";
        return out;
    }

    bool pcsx2FromJson(const std::string &json, Pcsx2Config &out)
    {
        out = Pcsx2Config{};   // malformed input leaves the defaults
        Pcsx2Config c;
        detail::JsonReader p(json);
        if (!p.take('{'))
            return false;
        if (!p.take('}'))
        {
            for (;;)
            {
                std::string key;
                if (!p.string(key) || !p.take(':'))
                    return false;
                if (key == "isoPath" || key == "pcsx2Exe" || key == "gameRevision" || key == "serverPreset" || key == "server" || key == "ethDevice")
                {
                    std::string v;
                    if (!p.string(v))
                        return false;
                    if (key == "isoPath") c.isoPath = v;
                    else if (key == "pcsx2Exe") c.pcsx2Exe = v;
                    // Normalised on the way in, as config.json's are: a newer build's id or a hand-edited one must
                    // not leave the selector with a version it cannot draw, nor the picker on a server that is not.
                    else if (key == "gameRevision") c.gameRevision = normalizeGameRevision(v);
                    else if (key == "serverPreset") c.serverPreset = normalizeServerPreset(v);
                    else if (key == "server") c.server = v;
                    else c.ethDevice = v;
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

    std::string pcsx2EffectiveServer(const Pcsx2Config &c)
    {
        // The native rule, asked of a scratch Config holding only these two values (nothing is kept or copied
        // between the two files): the preset's address; an unplayable preset's playable fallback; else the typed
        // address, or 127.0.0.1 when nothing is typed.
        Config scratch;
        scratch.serverPreset = c.serverPreset;
        scratch.server = c.server;
        return effectiveServer(scratch);
    }
}
