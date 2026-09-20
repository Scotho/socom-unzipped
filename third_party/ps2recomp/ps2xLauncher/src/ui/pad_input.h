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
    };

    // `repeatAt` is the caller's stick-repeat clock, carried between frames.
    PadIntent padIntent(const PadFrame &pad, bool gameRunning, double now, double &repeatAt);
}
