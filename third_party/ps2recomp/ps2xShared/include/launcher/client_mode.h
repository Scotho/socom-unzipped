#pragma once
// Sprint 18 T2 (R339 = R-A): which client the launcher drives -- the native recompilation or PCSX2. A global mode,
// saved in its own file beside the launcher, so neither client's settings file ever carries the other's choice.
#include <string>

namespace launcher
{
    enum class ClientMode { Native, Pcsx2 };
    constexpr const char *kClientModeFile = "launcher.json";          // beside the launcher; {"client":"native"}
    ClientMode parseClientMode(const std::string &json);               // anything but "pcsx2" is Native
    std::string clientModeJson(ClientMode mode);                       // "{\n  \"client\": \"pcsx2\"\n}\n"
    const char *clientModeId(ClientMode mode);                         // "native" | "pcsx2"
}
