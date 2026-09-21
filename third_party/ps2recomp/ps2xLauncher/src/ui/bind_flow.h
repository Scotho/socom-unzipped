#pragma once
// Sprint 10 Goal 8 (R174, part 2): the CONTROLLER page's BUTTONS section, the pure half -- which PS2 button each
// cell shows, what the connected pad calls each of its own buttons, and the press-the-button-to-bind flow as a
// state machine the tests can drive frame by frame with no window.
//
// The flow. A cell is activated: the page LISTENS for kBindWindowSeconds, counting down. The next host button
// RELEASED binds -- released, not pressed, so the one button that also means "cancel" can be told apart: the right
// face button (B / Circle, by position) held for kCancelHoldSeconds or longer cancels, a tap of it binds it like any
// other. Escape cancels at once. The countdown running out cancels. When the released button already drives another
// PS2 button the flow stops at CONFLICT and the page asks: swap, replace or cancel (launcher/mapping.h's rebind does
// the moving). "Restore defaults" is its own two-step: a confirm whose focus lands on CANCEL, so the button cannot be
// hit by accident and a double press cannot wipe a layout.
//
// Pure: no raylib. main.cpp turns the pad's raw buttons into a BindInput; page_controller.cpp draws the state.
#include "glyphs.h"
#include "launcher/mapping.h"

#include <cstdint>
#include <string>

namespace ui
{
    // The sixteen cells, four across and four down, in the order a player reads them: the face buttons, the
    // shoulders and triggers, the d-pad, then the centre and the stick clicks.
    constexpr int kBindCells = 16;
    uint8_t bindCellButton(int cell);          // the PS2 button in cell 0..15
    std::string bindCellId(int cell);          // "pad.bind.<ps2 name>"
    int bindCellOf(const std::string &id);     // the cell an id names, or -1

    // What the game calls its button, for the cell's left side: a shape glyph for the four face buttons (index as
    // drawShapeGlyph: 0 triangle, 1 cross, 2 square, 3 circle; -1 for the rest) and a short word otherwise.
    struct Ps2Label
    {
        const char *text;
        int face;
    };
    Ps2Label ps2Label(uint8_t button);

    // What the pad in the player's hands calls its own button -- the family's letters and words (Y, LB, LT,
    // VIEW, MENU on an Xbox pad; the shapes, drawn, on a PlayStation one), never the game's. kHostNone reads
    // "NOT BOUND". `face` as above: when >= 0 a PlayStation family draws the shape instead of the text.
    struct HostLabel
    {
        const char *text;
        int face;
    };
    HostLabel hostLabel(GlyphFamily family, int host);

    constexpr double kBindWindowSeconds = 5.0;
    constexpr double kCancelHoldSeconds = 0.5;
    constexpr int kCancelHost = launcher::mapping::kHostFaceRight;   // B / Circle, by position

    struct BindFlow
    {
        enum class State
        {
            Idle,
            Listening,       // `button` waits for a host button; `deadline` is when it stops waiting
            Conflict,        // `host` was released but drives `takenBy`: the page asks
            ConfirmRestore   // RESTORE DEFAULTS was pressed once
        };
        State state = State::Idle;
        uint8_t button = 0;
        int host = 0;
        int takenBy = -1;
        double deadline = 0.0;
        // The last binding made, for the drawing's highlight: which host button, and when.
        int lastHost = 0;
        double lastAt = -1.0;
    };

    // One frame of raw input while listening.
    struct BindInput
    {
        int releasedHost = 0;        // the host button released this frame (0: none)
        double heldSeconds = 0.0;    // how long it had been down
        bool escape = false;
    };

    enum class BindEvent
    {
        None,
        Bound,       // the mapping changed
        Conflict,    // the flow is at Conflict; nothing moved yet
        Cancelled,
        TimedOut
    };

    void bindStart(BindFlow &flow, uint8_t button, double now);
    // Listening only (anything else answers None): the frame's input against the clock.
    BindEvent bindStep(BindFlow &flow, launcher::mapping::Mapping &m, const BindInput &in, double now);
    // Conflict only: Swap or Replace moves the binding; Ask is the cancel and moves nothing. Back to Idle either way.
    BindEvent bindResolve(BindFlow &flow, launcher::mapping::Mapping &m, launcher::mapping::Resolution resolution, double now);
    // Whole seconds left while listening (at least 1 until the deadline passes), 0 otherwise.
    int bindCountdown(const BindFlow &flow, double now);
    // The restore two-step.
    void restoreAsk(BindFlow &flow);
    void restoreAnswer(BindFlow &flow, launcher::mapping::Mapping &m, bool yes);
    void bindCancel(BindFlow &flow);   // whatever the state, back to Idle with nothing moved

    // The dialog's buttons, as the layout lays them out and the page labels them, and where the focus lands
    // when the dialog opens: SWAP for a conflict (the thing the player most likely wants), CANCEL for the
    // restore (the thing they must not get by accident).
    int dialogButtonCount(BindFlow::State state);           // 3 for Conflict, 2 for ConfirmRestore, 0 otherwise
    const char *dialogButtonLabel(BindFlow::State state, int index);
    std::string dialogFocusId(BindFlow::State state);        // "pad.dialog.<n>", "" when no dialog is open
    // The dialog's one sentence: "LB is already L1." / "Every button back to the defaults?"
    std::string dialogSentence(const BindFlow &flow, GlyphFamily family);
}
