#pragma once
// Sprint 9 Goal 9 (P3): the gate between the pad and the launcher.
//
// The launcher reads the pad through raylib/GLFW, which reads it whether or not the launcher's window has
// focus. So while the game was running the player's stick was walking the launcher's focus ring behind it
// (the owner, 2026-09-20: "When the game is active, both the game and the launcher receive input commands
// from the controller"). Rather than dotting `if (!app.running)` through the frame loop and hoping the next
// reader remembers, every pad reading is turned into intent HERE, and this is the one place that knows the
// game may own the pad.
//
// Pure: no raylib, no windows.h -- so the tests can hold a stick down for five seconds without a window.
#include "launcher/mapping.h"   // the host buttons' numbering, so the hold detector below owns no copy of it

namespace ui
{
    // The pad's buttons, as the launcher uses them (not raylib's numbering; main.cpp maps them).
    enum class PadNav
    {
        Left = 0,
        Right,
        Up,
        Down,
        Activate,    // cross / A
        Back,        // circle / B
        PagePrev,    // L1
        PageNext,    // R1
        Launch,      // Start
        // Sprint 10 Q4: the window switch -- the guide button by default, or whatever launcher::Config::focusToggle
        // names. The ONE button the gate reads while the game runs (see padIntent).
        Toggle,
        Count
    };

    // One frame of the pad as the launcher saw it.
    struct PadFrame
    {
        bool present = false;
        bool pressed[static_cast<int>(PadNav::Count)] = {};   // edges: pressed THIS frame
        float leftX = 0.0f;
        float leftY = 0.0f;
    };

    // What ends an edit in a text field (2026-09-22). While a field holds the keyboard the launcher's whole
    // navigation branch is skipped -- that is what "typing" means -- so every way out of a field has to be
    // named here or it does not exist. Before this the ways out were ENTER, ESCAPE and TAB: all keyboard
    // keys. A player who clicked a field and then clicked elsewhere, or who opened a field with the pad, was
    // left with a dead pad and no way back without a keyboard (the owner's playthrough, finding 1).
    //
    // `clickedAway` = this frame had a click and no editable widget took it.
    struct PadIntent;
    bool releasesField(bool keyEnter, bool keyEscape, bool keyTab, const PadIntent &pad, bool clickedAway);

    // What the launcher should do about it.
    struct PadIntent
    {
        int dx = 0;
        int dy = 0;
        bool activate = false;
        bool back = false;
        bool pagePrev = false;
        bool pageNext = false;
        bool launch = false;
        bool prompts = false;   // the pad moved the UI, so show the pad's glyphs rather than the keyboard's
        // Q4: swap the front window between the launcher and the game. Only ever true while the game runs --
        // with no game there is nothing to swap to, and the button does nothing rather than something else.
        bool toggle = false;
    };

    // `repeatAt` is the caller's stick-repeat clock, carried between frames.
    PadIntent padIntent(const PadFrame &pad, bool gameRunning, double now, double &repeatAt);

    // ---- W9 (owner, 2026-09-22): hold a pad button to remap it ------------------------------------------
    // "I'd also like to add a new remapping mechanism, hold the button to remap the button while on the
    // controller page." The gesture is HERE, behind the same gate as everything else the pad says, for the
    // same reason: a button held through a firefight must not arm anything in the launcher, and a page must
    // never reach for raylib on its own. main.cpp reads the pad and fills a HoldFrame; page_controller.cpp
    // only draws what comes back.
    //
    // What the hold means: the player holds the pad button they want to MOVE, and the flow that opens is the
    // existing BindFlow for the PS2 button that control currently drives -- so the next button they press is
    // where it moves to, and a clash is the same Conflict dialog (swap / replace / cancel) as ever. Nothing
    // about binding is reimplemented here; this only decides WHEN to call bindStart.
    constexpr double kRemapHoldSeconds = 0.75;   // see holdArms() for why this number

    // The buttons the gesture refuses, and the whole argument for the feature being usable:
    //
    //   CROSS (kHostFaceDown) is Activate and CIRCLE (kHostFaceRight) is Back. They are how the player moves
    //   around the page at all -- cross opens a cell, circle leaves for the rail -- and circle is also the
    //   bind flow's own cancel (kCancelHost, held past kCancelHoldSeconds). A hold that stole cross would
    //   turn every slightly-slow press into a remap session, and a hold that stole circle would collide with
    //   the gesture that gets you OUT of one. Neither is armed, ever.
    //
    //   L1 / R1 (the page tabs) and START (LAUNCH) are refused for a different reason: their PRESS edge has
    //   already been spent by the time a hold could build -- L1 has changed the page, START has asked for a
    //   launch -- so arming them would only ever produce a hold that silently dies. Refusing them says so.
    //
    //   The d-pad IS armed: the launcher takes one focus step from its press edge and then reads nothing more
    //   from it (only the stick repeats), so a held d-pad is otherwise dead input and the gesture is free.
    //
    // All five refused buttons are still bindable the way they always were: activate their cell on the
    // BUTTONS section. The gesture is a shortcut, not the only road.
    //
    // 750 ms, inside the 600-1000 ms the brief allows: long enough that a press-and-think on the d-pad (which
    // does move the focus) cannot reach it by accident, short enough that the progress ring does not feel
    // like a punishment. It is a constant so a test can name it rather than count frames.
    bool holdArms(int host);

    // Which host buttons are down THIS frame, indexed by launcher::mapping's host id ([0] unused).
    struct HoldFrame
    {
        bool present = false;
        bool down[launcher::mapping::kHostButtonMax + 1] = {};
    };

    // Carried between frames by the caller, like padIntent's repeat clock.
    struct HoldWatch
    {
        int host = 0;         // the button building a hold, 0 for none
        double since = 0.0;   // when it went down
        bool spent = false;   // this hold already fired; the button must come up before another can start
    };

    struct HoldIntent
    {
        int host = 0;           // the button building (0: nothing is)
        float progress = 0.0f;  // 0..1 of the way to kRemapHoldSeconds -- what the page draws
        bool fired = false;     // this frame, start the remap for `host`
    };

    // `pageArmed`: the CONTROLLER page is showing and nothing else owns the pad (no bind session open, no
    // dialog). `typing`: a text field holds the keyboard -- while it does, main's navigation branch is skipped
    // entirely and the pad's buttons are the field's way OUT (ui::releasesField), so they cannot also be a
    // gesture. Any refusal clears the watch, so a hold can never survive the condition that allowed it.
    HoldIntent padHold(HoldWatch &watch, const HoldFrame &frame, bool gameRunning, bool typing, bool pageArmed,
                       double now);
}
