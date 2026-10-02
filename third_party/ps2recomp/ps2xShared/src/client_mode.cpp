#include "launcher/client_mode.h"

#include "json_reader.h"

// Sprint 18 T2 (R339 = R-A): launcher.json, read with the same reader config.json is (json_reader.h). Anything that
// does not say exactly "pcsx2" -- no file, a malformed one, a newer build's word, a different case -- is the native
// client, which is what every launcher before this one was.
namespace launcher
{
    ClientMode parseClientMode(const std::string &json)
    {
        detail::JsonReader p(json);
        if (!p.take('{') || p.take('}'))
            return ClientMode::Native;
        ClientMode mode = ClientMode::Native;
        for (;;)
        {
            std::string key;
            if (!p.string(key) || !p.take(':'))
                return ClientMode::Native;
            if (key == "client" && p.peek() == '"')
            {
                std::string v;
                if (!p.string(v))
                    return ClientMode::Native;
                mode = v == "pcsx2" ? ClientMode::Pcsx2 : ClientMode::Native;
            }
            else if (!p.skipValue())
                return ClientMode::Native;
            if (p.take(','))
                continue;
            if (!p.take('}'))
                return ClientMode::Native;   // malformed: the default, as config.json's reader does
            return mode;
        }
    }

    std::string clientModeJson(ClientMode mode)
    {
        return std::string("{\n  \"client\": \"") + clientModeId(mode) + "\"\n}\n";
    }

    const char *clientModeId(ClientMode mode)
    {
        return mode == ClientMode::Pcsx2 ? "pcsx2" : "native";
    }
}
