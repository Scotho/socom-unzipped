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
}
