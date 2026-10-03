// Sprint 18 T5: the PCSX2 page's tooltips -- one line per control page_pcsx2.cpp draws (the owner's "little tooltip"),
// in the launcher's own voice. Pure (tips.h), so launcher_tests.cpp walks the page's focus list and holds every
// control to a line.
#include "tips.h"

#include <string>

namespace ui
{
    namespace
    {
        // The adapter the page shows now: the line names it, so the tip says what pressing it keeps.
        std::string adapterLine(const std::string &, const TipState &s)
        {
            if (s.pcsx2Adapter == nullptr || s.pcsx2Adapter->empty())
                return "Binds PCSX2's network to the adapter the launcher picks: the one with your internet connection.";
            return "Binds PCSX2's network to " + *s.pcsx2Adapter + ".";
        }

        const TipRow kRows[] = {
            {"pcsx2.select",
             "Pick a pcsx2-qt.exe you already have. The launcher writes only its network settings and the SOCOM II patch into it.",
             nullptr},
            {"pcsx2.install",
             "Downloads the latest official PCSX2 release (about 26 MB) from github.com/PCSX2/pcsx2 into this folder's pcsx2 "
             "subfolder, checks it, and unpacks it. Your BIOS and disc stay yours.",
             nullptr},
            {"pcsx2.bios.open",
             "Opens the folder PCSX2 reads its BIOS from. Copy your own PS2 BIOS dump there; the game cannot start without one.",
             nullptr},
            {"pcsx2.advanced", "The network adapter PCSX2 binds; the launcher picks the one with your internet connection.", nullptr},
            {"pcsx2.adapter", nullptr, adapterLine},
        };
    }

    TipTable pcsx2Tips()
    {
        return TipTable{kRows, sizeof(kRows) / sizeof(kRows[0])};
    }
}
