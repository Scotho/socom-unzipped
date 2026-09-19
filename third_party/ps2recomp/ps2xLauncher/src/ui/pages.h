#pragma once
// Sprint 8 Goal 9: what the pages share -- the whole state of the launcher, and one function per page.
//
// A page never touches the process glue, the microphone or the disc: it reads App and raises a request flag,
// and main.cpp's loop is the only thing that acts on the world.
#include "focus.h"
#include "launcher/launcher_config.h"
#include "pad_render.h"
#include "widgets.h"

#include <string>
#include <vector>

namespace ui
{
    struct App
    {
        launcher::Config config;
        bool dirty = false;   // the unsaved-changes hint (saved on Launch and on close)

        // the disc check
        bool discChecked = false;
        bool discOk = false;
        std::string discMessage;

        // the game
        bool running = false;
        std::string status;     // the last thing that happened, in the bottom bar
        std::string exitLine;   // the last run's exit message, on PLAY

        // the pads
        std::vector<std::string> padLabels;   // "first available", then "[0] <name>"
        std::vector<int> padSlots;            // -1, then the slot each label means
        PadSnapshot pad;                      // the one being drawn

        // the microphone
        std::vector<std::string> micLabels;   // "None", then the devices
        bool meterOn = false;
        float micDb = 0.0f;
        bool micDbValid = false;
        std::string micStatus;

        // what ABOUT shows
        std::string configPath, logsPath, version, monitorSize;

        // what the loop must do after this frame (the pages raise these, nothing else)
        bool requestBrowse = false;
        bool requestVerify = false;
        bool requestLaunch = false;
        bool requestDiagnostics = false;
        bool requestOpenLogs = false;
        bool requestMicChanged = false;
        bool requestMicRescan = false;
        bool requestSave = false;   // the top bar's UNSAVED pill

        std::string activeField;   // the text field holding the keyboard, by node id
        Nav nav;
        Frame frame;   // the four bands of this frame's window, in design units
        const FocusGraph *graph = nullptr;   // so a row can jump to the page that owns its setting
        LayoutInputs layout;
        bool padPrompts = false;   // the last input came from a pad: the bar shows its glyphs
        bool fake = false;         // --screenshot: fixed state, no config written, no devices touched
    };

    // ---- the shared furniture of a settings page ----------------------------------------------------------
    // Every settings row has the same label column, one metrics::labelW to the left of its control: that is
    // the grid the pages line up on.
    inline void rowLabel(const Ctx &ctx, Rect control, const char *label)
    {
        text(ctx, label, Vec2{control.x - metrics::labelW, control.y + (control.h - metrics::labelSize * 1.12f) * 0.5f},
             metrics::labelSize, theme::dim, Face::Bold, 0.06f);
    }

    inline void caption(const Ctx &ctx, Vec2 at, const char *s)
    {
        text(ctx, s, at, metrics::captionSize, theme::caption);
    }

    // ---- one per page -------------------------------------------------------------------------------------
    void drawPlayPage(const Ctx &ctx, App &app, const std::vector<Node> &nodes);
    void drawDiscPage(const Ctx &ctx, App &app, const std::vector<Node> &nodes);
    void drawVideoPage(const Ctx &ctx, App &app, const std::vector<Node> &nodes);
    void drawAudioPage(const Ctx &ctx, App &app, const std::vector<Node> &nodes);
    void drawControllerPage(const Ctx &ctx, App &app, const std::vector<Node> &nodes);
    void drawMicrophonePage(const Ctx &ctx, App &app, const std::vector<Node> &nodes);
    void drawOnlinePage(const Ctx &ctx, App &app, const std::vector<Node> &nodes);
    void drawAboutPage(const Ctx &ctx, App &app, const std::vector<Node> &nodes);
}
