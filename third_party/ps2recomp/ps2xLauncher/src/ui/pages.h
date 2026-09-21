#pragma once
// Sprint 8 Goal 9: what the pages share -- the whole state of the launcher, and one function per page.
//
// A page never touches the process glue, the microphone or the disc: it reads App and raises a request flag,
// and main.cpp's loop is the only thing that acts on the world.
#include "bind_flow.h"
#include "focus.h"
#include "launcher/bug_report.h"
#include "launcher/launcher_config.h"
#include "pad_render.h"
#include "widgets.h"

#include <string>
#include <vector>

namespace ui
{
    // Sprint 9 Goal 8: the REPORT A BUG page's state. The page edits `form` and raises `requestSend`; the loop
    // owns everything else (the check, the payload, the worker thread, the reply).
    struct ReportUi
    {
        launcher::bugreport::Form form;   // attachLog is OFF by default
        enum class State
        {
            Idle,
            Sending,        // the request is on its worker thread; SEND is disabled
            Sent,           // `id` is the reference
            FieldError,     // `message` says what to fix; the focus went to the field
            RateLimited,    // `message` says when to retry
            SavedLocally    // could not send: `savedPath` is where the report was written
        };
        State state = State::Idle;
        std::string message;
        std::string id;
        std::string savedPath;
        bool copied = false;      // the reference is on the clipboard
        std::string preview;      // what SEND would send, rebuilt by the loop when `changed`
        bool changed = true;
        bool requestSend = false;
    };

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

        // Sprint 9 Goal 8: the hosted server's status line on ONLINE ("" = unreachable: nothing is drawn),
        // and the REPORT A BUG page
        std::string serverStatus;
        ReportUi report;

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
        // Sprint 10 Q4: the AUDIO page's toggle moved; main.cpp (re)loads or drops the cues. The status line under
        // it is the loop's word on where the cues stand ("from your disc", "no disc set: silent", "off").
        bool requestMenuSounds = false;
        std::string menuSoundsStatus;

        std::string activeField;   // the text field holding the keyboard, by node id
        Nav nav;
        Frame frame;   // the bands of this frame's window, in design units
        LayoutInputs layout;
        bool padPrompts = false;   // the last input came from a pad: the bar shows its glyphs
        bool fake = false;         // --screenshot: fixed state, no config written, no devices touched
        // Sprint 9 P4: whether the player has opened a page's ADVANCED section this session. Deliberately
        // NOT in Config: which drawers you left open is not a setting, and a launcher that reopens them for
        // a stranger would defeat the point. `advancedForced` can override it -- see focus.h.
        bool advancedOpen = false;
        // Sprint 10 Goal 8: the CONTROLLER page's section (0 SETUP, 1 BUTTONS -- not a setting either) and the
        // bind flow. The page asks for a session with `requestBind` (the PS2 button, or -1) and main.cpp starts
        // it, because only the loop knows which host buttons are down at that moment.
        int padSection = 0;
        BindFlow bind;
        int requestBind = -1;
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

    // Sprint 9 P4 (owner: "move 'Second instance on this machine (for testing)' into an advanced section").
    // The head of one: a caret, the word, and a rule to the edge of the body. Returns true on the frame it
    // was acted on. `forced` means something inside is not at its default -- it is then drawn open, marked
    // "in use", and refuses to close, because a disclosure that can hide a live setting is a trap.
    inline bool advancedHeader(const Ctx &ctx, Rect r, const std::string &id, bool open, bool forced)
    {
        if (!drawable(r))
            return false;
        const bool live = hovered(ctx, r) || focused(ctx, id);
        const Rgba ink = forced ? theme::gold : (live ? theme::text : theme::dim);
        const float cx = r.x + 7.0f;
        const float cy = r.cy();
        // Wound the way fillQuad documents for this backend -- top-left, then the lower point, then the
        // top-right. The other order draws nothing at all: the first pass of this caret was invisible.
        if (open)   // pointing down: the section below is showing
            fillTriangle(ctx, Vec2{cx - 5.0f, cy - 2.5f}, Vec2{cx, cy + 3.5f}, Vec2{cx + 5.0f, cy - 2.5f}, ink);
        else        // pointing right: there is more this way
            fillTriangle(ctx, Vec2{cx - 2.5f, cy - 5.0f}, Vec2{cx - 2.5f, cy + 5.0f}, Vec2{cx + 3.5f, cy}, ink);

        const float wordX = r.x + 20.0f;
        text(ctx, "ADVANCED", Vec2{wordX, r.y + (r.h - metrics::labelSize * 1.12f) * 0.5f}, metrics::labelSize, ink,
             Face::Bold, 0.12f);
        float ruleRight = r.right();
        if (forced)
        {
            const char *note = "in use";
            const float noteW = textWidth(ctx, note, metrics::captionSize - 1.0f);
            textRightIn(ctx, note, r, metrics::captionSize - 1.0f, theme::gold);
            ruleRight -= noteW + 14.0f;
        }
        const float ruleX = wordX + textWidth(ctx, "ADVANCED", metrics::labelSize, Face::Bold, 0.12f) + 14.0f;
        if (ruleRight > ruleX)
            fillRect(ctx, Rect{ruleX, cy, ruleRight - ruleX, 1.0f}, theme::alpha(theme::line, live ? 220 : 130));

        // A forced-open section still takes the focus (it is a landmark on the page); it just will not shut.
        return hit(ctx, r, id) && !forced;
    }

    // ---- one per page -------------------------------------------------------------------------------------
    void drawPlayPage(const Ctx &ctx, App &app, const std::vector<Node> &nodes);
    void drawDiscPage(const Ctx &ctx, App &app, const std::vector<Node> &nodes);
    void drawVideoPage(const Ctx &ctx, App &app, const std::vector<Node> &nodes);
    void drawAudioPage(const Ctx &ctx, App &app, const std::vector<Node> &nodes);
    void drawControllerPage(const Ctx &ctx, App &app, const std::vector<Node> &nodes);
    void drawMicrophonePage(const Ctx &ctx, App &app, const std::vector<Node> &nodes);
    void drawOnlinePage(const Ctx &ctx, App &app, const std::vector<Node> &nodes);
    void drawReportPage(const Ctx &ctx, App &app, const std::vector<Node> &nodes);
    void drawAboutPage(const Ctx &ctx, App &app, const std::vector<Node> &nodes);
}
