#include "ps2x/host_window.h"

namespace ps2x::host_window
{
    std::string title(const char *tag, const char *gameName, const std::string &elfName)
    {
        std::string out;
        if (tag != nullptr && *tag != '\0')
            out = std::string(tag) + " | ";
        if (elfName == kSocom2Elf)
            out += kSocom2Name;
        else if (gameName != nullptr && *gameName != '\0')
            out += gameName;
        else
            out += elfName;
        out += kTitleSuffix;
        return out;
    }
}
