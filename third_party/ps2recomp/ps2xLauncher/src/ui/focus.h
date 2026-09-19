#pragma once
// Sprint 8 Goal 9: the launcher's pages, their layout and the one focus model mouse, keyboard and pad all drive.
//
// PURE ON PURPOSE: no raylib in this header or in focus.cpp. The rects here are the rects the pages draw --
// page_*.cpp looks its controls up by id rather than computing them again -- so a test that asserts where a
// direction lands is asserting about the layout the player sees.
#include "theme.h"

#include <string>
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
        About
    };
    constexpr int kPageCount = 8;

    Page pageAt(int index);
    int pageIndex(Page page);
    const char *pageName(Page page);    // the rail's label: "PLAY"
    const char *pageTitle(Page page);   // the content band's line: "PLAY -- everything at a glance"
    std::string railId(Page page);        // "rail.play"
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

    // The four bands every page is drawn into, in design units.
    struct Frame
    {
        Rect window, header, rail, content, body, bar;
    };
    Frame frameFor(Rect window);

    // What the layout cannot know on its own: how many pads and capture devices the list offers, and whether
    // the server address is the player's to type (a preset owns it otherwise).
    struct LayoutInputs
    {
        int padChoices = 1;
        int micChoices = 1;
        bool customServer = true;
    };

    // Every focusable control on `page`, in reading order, plus the bottom bar's LAUNCH (id "bar.launch").
    std::vector<Node> layoutFor(Page page, Rect window, const LayoutInputs &in);
    // The rail's eight entries.
    std::vector<Node> railLayout(Rect window);

    Rect rectOf(const std::vector<Node> &nodes, const std::string &id);
    bool hasNode(const std::vector<Node> &nodes, const std::string &id);

    // The rail and all eight pages at once: the whole navigable surface of the launcher.
    class FocusGraph
    {
    public:
        static FocusGraph build(Rect window, const LayoutInputs &in);

        const std::vector<Node> &nodes() const { return m_nodes; }
        const Node *find(const std::string &id) const;
        std::vector<std::string> idsOn(Page page) const;   // the page's controls, rail entry excluded
        std::string firstOn(Page page) const;

        // The id `dir` lands on, by the layout's rects: the nearest node that way on the same page (one whose
        // band overlaps for preference), the page's rail entry when there is nothing further left, and the
        // same id when there is nowhere to go. From the rail, up/down walks the rail and right enters the page.
        std::string move(const std::string &from, Dir dir) const;

    private:
        std::vector<Node> m_nodes;
    };

    // Where the player is. The rail highlight is `page`, so a move onto a rail entry changes the page with it.
    struct Nav
    {
        Page page = Page::Play;
        std::string focus;

        void goTo(const FocusGraph &g, Page p);   // the page, focused on its first control
        void move(const FocusGraph &g, Dir d);
        void back(const FocusGraph &g);           // out to this page's rail entry
        bool onRail() const;
    };

    // Why LAUNCH is disabled, in the player's words; empty when it is not. The running game comes first: it is
    // the blocker the player just created, whatever the disc field says.
    std::string launchBlockedReason(bool discOk, bool running, bool isoPathEmpty);

    // True for the controls that left/right ADJUSTS rather than navigates away from: the three sliders. The
    // bottom bar's prompts say so when one of them holds the focus.
    bool adjustsHorizontally(const std::string &id);
}
