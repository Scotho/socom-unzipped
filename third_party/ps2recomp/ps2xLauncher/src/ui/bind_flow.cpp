#include "bind_flow.h"

#include <cmath>

namespace ui
{
    namespace
    {
        using namespace launcher::mapping;

        // Four across, four down: the face buttons, the shoulders and triggers, the d-pad, the centre and the sticks.
        constexpr uint8_t kCells[kBindCells] = {
            kPs2Cross, kPs2Circle, kPs2Square, kPs2Triangle,
            kPs2L1, kPs2R1, kPs2L2, kPs2R2,
            kPs2Up, kPs2Down, kPs2Left, kPs2Right,
            kPs2Select, kPs2Start, kPs2L3, kPs2R3,
        };

        // drawShapeGlyph's index for a PS2 face button, -1 for the rest.
        int ps2Face(uint8_t button)
        {
            switch (button)
            {
            case kPs2Triangle: return 0;
            case kPs2Cross: return 1;
            case kPs2Square: return 2;
            case kPs2Circle: return 3;
            default: return -1;
            }
        }

        // The same index for a host face button (by position: up, down, left, right), -1 for the rest.
        int hostFace(int host)
        {
            switch (host)
            {
            case kHostFaceUp: return 0;
            case kHostFaceDown: return 1;
            case kHostFaceLeft: return 2;
            case kHostFaceRight: return 3;
            default: return -1;
            }
        }

        std::string hostWords(GlyphFamily family, int host)
        {
            return hostLabel(family, host).text;
        }
    }

    uint8_t bindCellButton(int cell)
    {
        return cell >= 0 && cell < kBindCells ? kCells[cell] : kPs2Cross;
    }

    std::string bindCellId(int cell)
    {
        return std::string("pad.bind.") + ps2ButtonName(bindCellButton(cell));
    }

    int bindCellOf(const std::string &id)
    {
        for (int i = 0; i < kBindCells; ++i)
            if (bindCellId(i) == id)
                return i;
        return -1;
    }

    Ps2Label ps2Label(uint8_t button)
    {
        // libpad2's order: SELECT L3 R3 START UP RIGHT DOWN LEFT L2 R2 L1 R1 TRIANGLE CIRCLE CROSS SQUARE.
        static const char *byId[kPs2ButtonCount] = {
            "SELECT", "L3", "R3", "START", "UP", "RIGHT", "DOWN", "LEFT",
            "L2", "R2", "L1", "R1", "TRIANGLE", "CIRCLE", "CROSS", "SQUARE"};
        if (button == kSwitchTarget)
            return Ps2Label{"SWITCH", -1};   // Q4: the window switch's cell reads like the others
        return Ps2Label{button < kPs2ButtonCount ? byId[button] : "", ps2Face(button)};
    }

    HostLabel hostLabel(GlyphFamily family, int host)
    {
        const int face = hostFace(host);
        if (face >= 0)
        {
            // The letter the family prints on it; a PlayStation pad draws the shape instead (face >= 0), and
            // its text is the shape's word for a sentence that cannot draw.
            if (family == GlyphFamily::PlayStation)
            {
                static const char *shapes[4] = {"TRIANGLE", "CROSS", "SQUARE", "CIRCLE"};
                return HostLabel{shapes[face], face};
            }
            return HostLabel{faceLetter(family, face), -1};
        }
        switch (host)
        {
        case kHostDpadUp: return HostLabel{"D-PAD UP", -1};
        case kHostDpadRight: return HostLabel{"D-PAD RIGHT", -1};
        case kHostDpadDown: return HostLabel{"D-PAD DOWN", -1};
        case kHostDpadLeft: return HostLabel{"D-PAD LEFT", -1};
        case kHostL1: return HostLabel{family == GlyphFamily::Xbox ? "LB" : "L1", -1};
        case kHostR1: return HostLabel{family == GlyphFamily::Xbox ? "RB" : "R1", -1};
        case kHostL2: return HostLabel{family == GlyphFamily::Xbox ? "LT" : "L2", -1};
        case kHostR2: return HostLabel{family == GlyphFamily::Xbox ? "RT" : "R2", -1};
        case kHostSelect: return HostLabel{family == GlyphFamily::Xbox ? "VIEW" : (family == GlyphFamily::PlayStation ? "SHARE" : "SELECT"), -1};
        case kHostGuide: return HostLabel{family == GlyphFamily::Xbox ? "XBOX" : (family == GlyphFamily::PlayStation ? "PS" : "GUIDE"), -1};
        case kHostStart: return HostLabel{family == GlyphFamily::Xbox ? "MENU" : (family == GlyphFamily::PlayStation ? "OPTIONS" : "START"), -1};
        case kHostL3: return HostLabel{family == GlyphFamily::Xbox ? "LS CLICK" : "L3", -1};
        case kHostR3: return HostLabel{family == GlyphFamily::Xbox ? "RS CLICK" : "R3", -1};
        default: return HostLabel{"NOT BOUND", -1};
        }
    }

    void bindStart(BindFlow &flow, uint8_t button, double now)
    {
        if (button != kSwitchTarget && rowOf(button) < 0)
            return;
        flow.state = BindFlow::State::Listening;
        flow.button = button;
        flow.host = 0;
        flow.takenBy = -1;
        flow.deadline = now + kBindWindowSeconds;
    }

    BindEvent bindStep(BindFlow &flow, Mapping &m, const BindInput &in, double now)
    {
        if (flow.state != BindFlow::State::Listening)
            return BindEvent::None;
        if (in.escape)
        {
            bindCancel(flow);
            return BindEvent::Cancelled;
        }
        if (in.releasedHost == kCancelHost && in.heldSeconds >= kCancelHoldSeconds)
        {
            bindCancel(flow);
            return BindEvent::Cancelled;
        }
        if (in.releasedHost > kHostNone && in.releasedHost <= kHostButtonMax)
        {
            if (flow.button == kSwitchTarget)
            {
                // Q4: the switch takes no row of the mapping. A host button the game reads is a conflict all
                // the same -- the game must never see the switch -- and the dialog's REPLACE frees it.
                const int taken = boundTo(m, in.releasedHost);
                if (taken >= 0)
                {
                    flow.state = BindFlow::State::Conflict;
                    flow.host = in.releasedHost;
                    flow.takenBy = taken;
                    return BindEvent::Conflict;
                }
                flow.lastHost = in.releasedHost;
                flow.lastAt = now;
                bindCancel(flow);
                return BindEvent::Bound;
            }
            const Conflict c = rebind(m, flow.button, in.releasedHost, Resolution::Ask);
            if (c.kind == Conflict::Kind::Taken)
            {
                flow.state = BindFlow::State::Conflict;
                flow.host = in.releasedHost;
                flow.takenBy = c.by;
                return BindEvent::Conflict;
            }
            flow.lastHost = in.releasedHost;
            flow.lastAt = now;
            bindCancel(flow);
            return BindEvent::Bound;
        }
        if (now >= flow.deadline)
        {
            bindCancel(flow);
            return BindEvent::TimedOut;
        }
        return BindEvent::None;
    }

    BindEvent bindResolve(BindFlow &flow, Mapping &m, Resolution resolution, double now)
    {
        if (flow.state != BindFlow::State::Conflict)
            return BindEvent::None;
        if (resolution == Resolution::Ask || (flow.button == kSwitchTarget && resolution == Resolution::Swap))
        {
            bindCancel(flow);
            return BindEvent::Cancelled;
        }
        if (flow.button == kSwitchTarget)
            rebind(m, static_cast<uint8_t>(flow.takenBy), kHostNone, Resolution::Replace);   // the game lets go of it
        else
            rebind(m, flow.button, flow.host, resolution);
        flow.lastHost = flow.host;
        flow.lastAt = now;
        bindCancel(flow);
        return BindEvent::Bound;
    }

    int bindCountdown(const BindFlow &flow, double now)
    {
        if (flow.state != BindFlow::State::Listening)
            return 0;
        const double left = flow.deadline - now;
        if (left <= 0.0)
            return 0;
        return static_cast<int>(std::ceil(left));
    }

    void restoreAsk(BindFlow &flow)
    {
        flow.state = BindFlow::State::ConfirmRestore;
        flow.host = 0;
        flow.takenBy = -1;
    }

    void restoreAnswer(BindFlow &flow, Mapping &m, bool yes)
    {
        if (flow.state != BindFlow::State::ConfirmRestore)
            return;
        if (yes)
            restoreDefaults(m);
        bindCancel(flow);
    }

    void bindCancel(BindFlow &flow)
    {
        flow.state = BindFlow::State::Idle;
        flow.host = 0;
        flow.takenBy = -1;
        flow.deadline = 0.0;
    }

    int dialogButtonCount(BindFlow::State state)
    {
        switch (state)
        {
        case BindFlow::State::Conflict: return 3;
        case BindFlow::State::ConfirmRestore: return 2;
        default: return 0;
        }
    }

    const char *dialogButtonLabel(BindFlow::State state, int index)
    {
        if (state == BindFlow::State::Conflict)
        {
            static const char *labels[3] = {"SWAP", "REPLACE", "CANCEL"};
            return index >= 0 && index < 3 ? labels[index] : "";
        }
        if (state == BindFlow::State::ConfirmRestore)
        {
            static const char *labels[2] = {"RESTORE", "CANCEL"};
            return index >= 0 && index < 2 ? labels[index] : "";
        }
        return "";
    }

    std::string dialogFocusId(BindFlow::State state)
    {
        if (state == BindFlow::State::Conflict)
            return "pad.dialog.0";   // SWAP
        if (state == BindFlow::State::ConfirmRestore)
            return "pad.dialog.1";   // CANCEL: a double press cannot wipe a layout
        return std::string();
    }

    int dialogButtonCount(const BindFlow &flow)
    {
        if (flow.state == BindFlow::State::Conflict && flow.button == kSwitchTarget)
            return 2;
        return dialogButtonCount(flow.state);
    }

    const char *dialogButtonLabel(const BindFlow &flow, int index)
    {
        if (flow.state == BindFlow::State::Conflict && flow.button == kSwitchTarget)
        {
            static const char *labels[2] = {"REPLACE", "CANCEL"};
            return index >= 0 && index < 2 ? labels[index] : "";
        }
        return dialogButtonLabel(flow.state, index);
    }

    std::string dialogFocusId(const BindFlow &flow)
    {
        if (flow.state == BindFlow::State::Conflict && flow.button == kSwitchTarget)
            return "pad.dialog.1";   // CANCEL: REPLACE takes a button away from the game
        return dialogFocusId(flow.state);
    }

    std::string dialogSentence(const BindFlow &flow, GlyphFamily family)
    {
        if (flow.state == BindFlow::State::Conflict && flow.button == kSwitchTarget)
        {
            const std::string theirs = flow.takenBy >= 0 ? ps2Label(static_cast<uint8_t>(flow.takenBy)).text : "";
            return hostWords(family, flow.host) + " is already " + theirs +
                   ", and the game must not read the window switch. Replace it (" + theirs + " loses its button), or cancel?";
        }
        if (flow.state == BindFlow::State::Conflict)
        {
            const std::string mine = ps2Label(flow.button).text;
            const std::string theirs = flow.takenBy >= 0 ? ps2Label(static_cast<uint8_t>(flow.takenBy)).text : "";
            return hostWords(family, flow.host) + " is already " + theirs + ". Swap it with " + mine +
                   "'s button, replace it (" + theirs + " loses its button), or cancel?";
        }
        if (flow.state == BindFlow::State::ConfirmRestore)
            return "Every button back to the defaults for this profile?";
        return std::string();
    }
}
