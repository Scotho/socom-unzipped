#include "pad_input.h"

#include <cmath>

namespace ui
{
    namespace
    {
        constexpr float kStickThreshold = 0.55f;   // past this, a stick counts as pushed
        constexpr double kRepeatFirst = 0.32;      // a held stick waits this long before it walks
        constexpr double kRepeatThen = 0.13;       // ... and then steps at this rate

        bool edge(const PadFrame &pad, PadNav which)
        {
            return pad.pressed[static_cast<int>(which)];
        }
    }

    PadIntent padIntent(const PadFrame &pad, bool gameRunning, double now, double &repeatAt)
    {
        // The gate. While the game runs the pad is the game's, and the launcher reads NOTHING from it --
        // not the buttons, and not the repeat clock either: a stick held through a firefight must not bank
        // steps and spend them the frame the game exits. Sprint 10 Q4 opens it one button wide: the window
        // switch (the guide by default), which the game does not read (mapping.h binds no PS2 button to it
        // unless the player does, and the CONTROLLER page refuses that without asking). The runtime reads the
        // pad whether or not its window is in front (ps2xRuntime has no IsWindowFocused), so the launcher must
        // NOT take the rest of the pad back when it is brought forward: that would be the P3 defect again.
        if (!pad.present)
        {
            repeatAt = 0.0;
            return PadIntent{};
        }
        if (gameRunning)
        {
            repeatAt = 0.0;
            PadIntent out;
            out.toggle = edge(pad, PadNav::Toggle);
            return out;
        }

        PadIntent out;
        if (edge(pad, PadNav::Left))
            out.dx -= 1;
        if (edge(pad, PadNav::Right))
            out.dx += 1;
        if (edge(pad, PadNav::Up))
            out.dy -= 1;
        if (edge(pad, PadNav::Down))
            out.dy += 1;

        // The left stick, with a repeat so a held stick walks rather than sprints.
        const bool pushed = std::fabs(pad.leftX) > kStickThreshold || std::fabs(pad.leftY) > kStickThreshold;
        if (!pushed)
        {
            repeatAt = 0.0;
        }
        else if (now >= repeatAt)
        {
            repeatAt = now + (repeatAt == 0.0 ? kRepeatFirst : kRepeatThen);
            if (std::fabs(pad.leftX) > std::fabs(pad.leftY))
                out.dx += pad.leftX < 0.0f ? -1 : 1;
            else
                out.dy += pad.leftY < 0.0f ? -1 : 1;
        }

        out.activate = edge(pad, PadNav::Activate);
        out.back = edge(pad, PadNav::Back);
        out.pagePrev = edge(pad, PadNav::PagePrev);
        out.pageNext = edge(pad, PadNav::PageNext);
        out.launch = edge(pad, PadNav::Launch);

        // The pad touched the UI, so the prompts should speak its glyphs rather than the keyboard's.
        // (A key pressed in the same frame still overrides this; that half stays with the caller.)
        out.prompts = out.dx != 0 || out.dy != 0 || out.activate || out.back;
        return out;
    }
}
