#pragma once
// Sprint 8 Goal 9: the launcher's pages, their layout and the one focus model mouse, keyboard and pad all drive.
//
// PURE ON PURPOSE: no raylib in this header or in focus.cpp. The rects here are the rects the pages draw --
// page_*.cpp looks its controls up by id rather than computing them again -- so a test that asserts where a
// direction lands is asserting about the layout the player sees.
#include "launcher/client_mode.h"       // Sprint 18 T5: a rail per client
#include "launcher/launcher_config.h"   // Sprint 9 P4: what forces an ADVANCED section open
#include "theme.h"

#include <cstdint>
#include <string>
#include <utility>
#include <vector>

namespace ui
{
    enum class Page
    {
        Play = 0,
        Disc,
        Video,
        Audio,
        Controller,
        Microphone,
        Online,
        Report,   // Sprint 9 Goal 8: REPORT A BUG
        About,
        Pcsx2     // Sprint 18 T5: appended, so every existing index is unchanged
    };
    constexpr int kPageCount = 10;

    // Sprint 18 T5 (R339 = R-A, R344 = R-F): the rail per client, in rail order. NATIVE: the nine pages as before.
    // PCSX2: PLAY, DISC, PCSX2, ONLINE, REPORT A BUG, ABOUT -- video, audio, the pad and the microphone are PCSX2's own.
    std::vector<Page> pagesFor(launcher::ClientMode mode);
    // The page `step` places along that client's rail from `page` (the pad's shoulder tabs), clamped at the ends; a
    // page the client has not got answers its first page.
    Page pageBeside(launcher::ClientMode mode, Page page, int step);
    // The client toggle's two cells in the top bar (chrome.h's ChromeLayout places them): "bar.client.native" and
    // "bar.client.pcsx2". The id of a mode's cell, and the mode a cell's id names (false: not a cell).
    std::string clientCellId(launcher::ClientMode mode);
    bool clientCellMode(const std::string &id, launcher::ClientMode &mode);

    Page pageAt(int index);
    int pageIndex(Page page);
    const char *pageName(Page page);    // the rail's label: "PLAY"
    // The content band's line: "PLAY -- the state of the game and ...". LATER 80: per client -- ONLINE's in the PCSX2
    // view names what that view shows (no personas list, no second instance); every other page reads the same in both.
    const char *pageTitle(Page page, launcher::ClientMode mode);
    std::string railId(Page page);        // "rail.play"
    std::string pageSlug(Page page);      // "play", "report": the rail id without "rail." -- ids and screenshot names
    std::string barLaunchId(Page page);   // "bar.launch.play" -- the bar is on every page, its node is per page

    enum class Dir
    {
        Up,
        Down,
        Left,
        Right
    };

    struct Node
    {
        std::string id;
        Rect r;
        Page page = Page::Play;
        bool rail = false;
    };

    // The bands every page is drawn into, in design units. `band` is the content panel's title strip -- the
    // page's name, and (Sprint 10) the help for whatever holds the focus; nothing a page lays out may
    // enter it, which the tests hold every page to.
    struct Frame
    {
        Rect window, header, rail, content, band, body, bar;
    };
    Frame frameFor(Rect window);
    // The bottom bar's LAUNCH: its node on every page but PLAY, and on PLAY the place its run state is drawn.
    Rect barLaunchRect(const Frame &f);

    // What the layout cannot know on its own: how many pads and capture devices the list offers, and whether
    // the server address is the player's to type (a preset owns it otherwise).
    struct LayoutInputs
    {
        int padChoices = 1;
        int micChoices = 1;
        bool customServer = true;
        // Sprint 9 P4: a page's ADVANCED section is shut by default, and its controls are then not on the
        // page at all -- not merely undrawn, so nothing can focus or activate what a player cannot see.
        bool advancedOpen = false;
        // Sprint 10 Goal 8: the CONTROLLER page's two sections under the drawn pad -- SETUP (the pad pick, the
        // dead zone) or BUTTONS (the bindings, RESTORE, the crouch row) -- and, in BUTTONS, whether
        // a dialog (a conflict's three answers, the restore confirm's two) has replaced the section's controls.
        bool padButtons = false;
        int padDialogButtons = 0;
        // Task 11: whether socom2_r0004.exe sits beside the launcher. The GAME VERSION selector's second
        // cell is DRAWN either way -- greyed, with the note -- but it is only a focusable node when the
        // build it names exists, because a control a player cannot use must not be reachable by the pad.
        uint32_t gameRevisionsInstalled = 0;
        // Sprint 16 L1b (#73): the ONLINE page's PERSONAS list -- how many records it lists (NEW PERSONA is one more,
        // last), how far it is scrolled (the first visible row), which row is selected (personaRows = NEW PERSONA,
        // the default inputs' case) and whether the masked PASSWORD field shows beside the selected row. NEW PERSONA
        // selected (personaSelected == personaRows) is what puts the creator's NAME field beside the password.
        int personaRows = 0;
        int personaScroll = 0;
        int personaSelected = 0;
        bool personaPasswordShown = true;
        // Sprint 18 T5: which client's rail and pages the graph is built from; and on the PCSX2 page, whether INSTALL
        // is running (its button is then not a node: nothing may start a second download). (T6: pcsx2HasExe, set and
        // never read, is gone -- the PLAY row and LAUNCH's reason read App's Pcsx2Status, which is where it was set from.)
        launcher::ClientMode mode = launcher::ClientMode::Native;
        bool pcsx2Installing = false;
    };

    // Whether an ADVANCED section MUST be open whatever the player last chose, because something inside it
    // is not at its default. A disclosure that can hide a setting which is doing something is a trap: it is
    // how a player switches a second instance on, collapses the section, and then cannot find why two games
    // start. The rule is cheap to state and cheap to keep, so it is a function and not a comment.
    bool advancedForced(const launcher::Config &c);

    // Every focusable control on `page`, in reading order, plus the bottom bar's LAUNCH (id "bar.launch").
    // Sprint 18 T6: PLAY and ONLINE under in.mode == Pcsx2 are the PCSX2 view -- PLAY's rows are playRows(Pcsx2), ONLINE
    // is the presets, r0001's cell (revisionsOffered) and ADDRESS when Custom, nothing else (no personas, no ADVANCED).
    std::vector<Node> layoutFor(Page page, Rect window, const LayoutInputs &in);

    // Sprint 18 T6: PLAY's four jump rows, id and the page each one's CHANGE goes to, in order -- one table the layout
    // and page_play.cpp both read, so a row can never jump to a page outside its client's rail (the T5 review's item 1).
    // NATIVE: DISC, VIDEO, CONTROLLER, ONLINE. PCSX2: DISC, SERVER (ONLINE), GAME VERSION (ONLINE), PCSX2.
    std::vector<std::pair<std::string, Page>> playRows(launcher::ClientMode mode);
    // Sprint 18 T6 (R343 = R-E): the game versions the GAME VERSION row offers as nodes -- natively the installed mask,
    // in PCSX2 mode r0001 alone (bit 0) whatever is installed; and the note drawn beside the greyed cells ("" when none
    // is greyed): kRevisionMissingNote natively, kPcsx2RevisionNote in PCSX2 mode. Drawn on ONLINE too since T6 -- the
    // preset row's note is "coming soon" (R-B), so the cell's reason is no longer said elsewhere on the page.
    uint32_t revisionsOffered(launcher::ClientMode mode, uint32_t installed);
    const char *revisionGreyedNote(launcher::ClientMode mode, uint32_t installed);
    // Sprint 18 T6 (the T5 review's item 3): why the client toggle will not switch now, or "" when it will. An INSTALL
    // writes the PCSX2 page's state and a running game keeps its own client's LAST RUN line (Review Focus 5), so both
    // hold the toggle; the sentence is the toggle's tip and the status line a refused press leaves.
    std::string clientSwitchRefusal(bool installing, bool running);

    // The node list THIS FRAME must draw from. `computed` is the list built at the top of the frame, from
    // the page that was current then; `page` is where the frame's input left the player. The two differ on
    // exactly the frames a page change lands on -- the pad's shoulder tabs, Escape, a rail entry clicked in
    // the middle of the draw -- and drawing the new page out of the old page's list is what put a label at
    // the window's origin for one frame (Sprint 9 P4, the owner's "weird graphical bug ... around the top
    // left"). Unchanged page: the list it was handed, so the rebuild costs a page change, not every frame.
    std::vector<Node> nodesForFrame(std::vector<Node> computed, Page page, Rect window, const LayoutInputs &in);
    // The rail's entries, one per page of that client (pagesFor), plus the client toggle's two cells in the header band
    // (rail = true, page = PLAY: chrome, never a page's control).
    std::vector<Node> railLayout(Rect window, launcher::ClientMode mode);

    // The ONLINE page's preset rows, by index: a row exists for every preset, but only the ones that can
    // actually be played get a focusable node (see launcher::presetAvailable).
    Rect onlinePresetRow(Rect window, int index);
    // Sprint 16 L1b (#73, R295): the ONLINE page under the server list. ADDRESS on its own row; the PERSONAS list's
    // rows at the presets' pitch, three visible, scrolling inside themselves past three, NEW PERSONA last; the masked
    // password beside the selected row, which narrows for it. Shared as onlinePresetRow is, so the drawn and the
    // focusable rects agree. A row is by its index in the whole list (records, then NEW PERSONA) and the scroll.
    constexpr int kPersonaVisibleRows = 3;
    Rect onlineAddressRow(Rect window);
    Rect onlinePersonaRow(Rect window, int index, int scroll);
    Rect onlinePersonaPassword(Rect window, int index, int scroll);
    // The persona-card plan: NEW PERSONA selected is the creator -- a strip at the row's right end (as wide as the row
    // can spare, 200 to 520) holding the new persona's NAME ("online.persona.name"), its PASSWORD
    // ("online.persona.password") and the CREATE ON CARD button ("online.persona.create"), left to right. A record
    // row keeps the one password field.
    Rect onlinePersonaCreator(Rect window, int index, int scroll);
    Rect onlinePersonaName(Rect window, int index, int scroll);
    Rect onlinePersonaNewPassword(Rect window, int index, int scroll);
    Rect onlinePersonaCreate(Rect window, int index, int scroll);
    // "online.persona.<i>" for a record, "online.persona.new" for index == records; the reverse (-1: not a row).
    std::string personaRowId(int index, int records);
    int personaIndexOf(const std::string &id, int records);
    // The scroll that shows `index` (unchanged when it already shows), clamped to the list.
    int personaScrollToShow(int index, int scroll, int total);
    // The scroll a (re)read of the ledgers leaves (main.cpp's readPersonas): the selected row in view, and with it the
    // password field beside it -- a password is never sent from a field the player cannot see.
    int personaScrollOnRead(const LayoutInputs &in, int scroll);
    // The scroll each frame leaves (main.cpp's frame loop): when the selected row changed since the last frame
    // without a reread (the 'Second instance' toggle picks another ledger's row), the scroll a read would leave;
    // otherwise clamped only, so a list scrolled by hand away from the selection stays where it is.
    int personaScrollPerFrame(const LayoutInputs &in, int selectedBefore, int scroll);
    // Up and down inside the list are the list's own moves, so a hidden row is reachable: true with `to` and the
    // `scroll` that shows it; false off either end, where the layout's geometry takes over (ADDRESS, ADVANCED).
    bool personaMove(const LayoutInputs &in, const std::string &from, Dir dir, std::string &to, int &scroll);

    // Sprint 18 T5: the PCSX2 page's rows, shared as onlinePresetRow is -- layoutFor emits the nodes from these rects
    // and page_pcsx2.cpp draws the rest (the read-only path, the greyed INSTALL while a download runs, the text rows)
    // from the same ones. The ONLINE page's pitch: 40-unit controls, ADVANCED at ONLINE's own ADVANCED y and the
    // adapter under it where ONLINE's second-instance toggle sits.
    struct Pcsx2Rows
    {
        Rect path;       // INSTANCE: the exe's path, read-only (not a node)
        Rect select;     // "pcsx2.select", 140 wide
        Rect install;    // "pcsx2.install", 140 wide; not a node while INSTALL runs
        Rect progress;   // INSTALL's meter and its sentence, under INSTANCE
        Rect version;    // VERSION, text only
        Rect bios;       // BIOS: the folder's sentence, text only
        Rect biosOpen;   // "pcsx2.bios.open", 160 wide
        Rect captions;   // the two sentences: PCSX2's own settings, and the license line
        Rect advanced;   // "pcsx2.advanced"
        Rect adapter;    // "pcsx2.adapter", only while ADVANCED is open
    };
    Pcsx2Rows pcsx2Rows(Rect window);

    // Task 11: the GAME VERSION selector's cells, by index, on the page that carries it (PLAY or ONLINE).
    // Shared the way onlinePresetRow is: layoutFor emits a node for the cells that can be chosen, and the
    // page draws the greyed one from this same rect -- so what is drawn and what can be focused cannot
    // disagree about where a cell is.
    Rect revisionCell(Rect window, Page page, int index);

    // Sprint 9 P4 (owner: "tooltips where the launcher is unclear ... 'what is a profile?' first"). The
    // help is DATA, keyed by a control's own id, and empty for the controls that explain themselves --
    // which is most of them. This is the "?" band: the two-line answer to a stranger's real question, shown in
    // the title strip for the focused control. The one-line tips are tips.h's, a different thing: they show on a
    // 0.5 s hover and, for the focused control, in the bottom bar (issue #74, the owner 2026-09-26).
    std::string helpFor(const std::string &id);
    // Every id the set answers for, so a test can hold the set to the controls that actually exist.
    std::vector<std::string> helpedIds();

    Rect rectOf(const std::vector<Node> &nodes, const std::string &id);
    bool hasNode(const std::vector<Node> &nodes, const std::string &id);

    // The rail and every page at once: the whole navigable surface of the launcher.
    class FocusGraph
    {
    public:
        // Sprint 18 T5: the rail and the pages of in.mode only (pagesFor), and the client toggle.
        static FocusGraph build(Rect window, const LayoutInputs &in);

        const std::vector<Node> &nodes() const { return m_nodes; }
        const Node *find(const std::string &id) const;
        std::vector<std::string> idsOn(Page page) const;   // the page's controls, rail entry excluded
        std::string firstOn(Page page) const;

        // The id `dir` lands on, by the layout's rects: the nearest node that way on the same page (one whose
        // band overlaps for preference), the page's rail entry when there is nothing further left, and the
        // same id when there is nowhere to go. From the rail, up/down walks the rail and right enters the page.
        // Sprint 18 T5: up from the rail's first entry is the toggle's cell for the current mode; left and right cross
        // between the two cells; down from either is the rail's first entry.
        std::string move(const std::string &from, Dir dir) const;

    private:
        std::vector<Node> m_nodes;
        launcher::ClientMode m_mode = launcher::ClientMode::Native;
    };

    // Where the player is. The rail highlight is `page`, so a move onto a rail entry changes the page with it.
    //
    // Sprint 10 (owner, 2026-09-20: "text from a selected tab displays inline around the top left before
    // snapping to the right location"). A page may only change in the frame's INPUT phase -- never inside
    // the draw. The frame's node list is built for the page the input phase left behind, and a draw that
    // switched the page part-way through (a rail click in drawRail, a PLAY row's CHANGE) then drew the new
    // page from the old page's list: every rectOf missed, every caption placed from a missed rect landed at
    // the origin, and the owner saw the new page's words at the top left for one frame. P4's nodesForFrame
    // covered the input phase and widgets.cpp's drawable() guard covered the Rect primitives, but plain
    // text() takes a point, and a point computed from an empty rect is a point. So the draw does not change
    // the page at all: it asks, with `request`, and the next frame's input phase applies the ask with
    // `applyRequest` before anything is laid out. One frame later than before, which is under 17 ms.
    struct Nav
    {
        Page page = Page::Play;
        std::string focus;
        int requested = -1;   // a page index, or -1: the page a draw asked for, applied next input phase

        void goTo(const FocusGraph &g, Page p);   // the page, focused on its first control (input phase only)
        void move(const FocusGraph &g, Dir d);
        void back(const FocusGraph &g);           // out to this page's rail entry
        bool onRail() const;

        void request(Page p);                     // from inside a draw: the page, next frame
        // The input phase: goTo the request, if there is one. Sprint 18 T6: a page with no rail entry in `g` (not in
        // pagesFor(mode): VIDEO from the PCSX2 view, PCSX2 from the native one) is dropped, the page unchanged, false --
        // no request can leave the rail's pages and strand the pad.
        bool applyRequest(const FocusGraph &g);
    };

    // Where the gold focus ring is drawn, frame by frame. Pure, so a test asserts on the very rect the
    // renderer strokes -- including the frame a page change lands on.
    //
    // There is NO travel: the ring is at the focused control's rect on the very frame the focus changes,
    // inside a page and across a page change alike (owner, Sprint 8: "takes too long to adjust and awkwardly
    // flys with a delay, remove that animation").
    struct FocusRing
    {
        Rect shown{};          // the rect to stroke this frame
        bool visible = false;  // false when the focus names nothing in the graph

        // `dt` is this frame's time in seconds; it is ignored, and the test says so.
        void update(const FocusGraph &g, const std::string &focusId, float dt);
    };

    // The disc check's sentences (main.cpp's checkDisc). The DISC page shows one; LAUNCH's blocked reason says the
    // same one, so a state has one sentence wherever it is read (Sprint 13 V8, stranger audit row 10: a moved ISO
    // was "cannot open the file" on DISC and "that file is not SOCOM II" under LAUNCH). The verified line names
    // the revision and is built where it is known.
    inline constexpr const char *kDiscNotChosen = "choose your SOCOM II disc image first";
    inline constexpr const char *kDiscNotChecked = "not checked yet";
    inline constexpr const char *kDiscCannotOpen = "cannot open the file";
    inline constexpr const char *kDiscNoElf = "not a SOCOM II disc image (no SCUS_972.75)";
    inline constexpr const char *kDiscCannotReadElf = "cannot read SCUS_972.75";
    inline constexpr const char *kDiscWrongRevision = "not SOCOM II NTSC r0001 (SCUS_972.75 differs)";

    // Why LAUNCH is disabled, in the player's words; empty when it is not. The running game comes first: it is
    // the blocker the player just created, whatever the disc field says. A disc that failed its check is blocked
    // with `discMessage`, the DISC page's sentence for that state.
    std::string launchBlockedReason(bool discOk, bool running, bool isoPathEmpty, const std::string &discMessage);

    // True for the controls that left/right ADJUSTS rather than navigates away from: the three sliders. The
    // bottom bar's prompts say so when one of them holds the focus.
    bool adjustsHorizontally(const std::string &id);
}
