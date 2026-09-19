// Sprint 8 Goal 9: the layout and the focus model. Pure -- no raylib, no globals, no drawing.
#include "focus.h"

#include "launcher/launcher_config.h"   // which server presets can be played at all

#include <algorithm>
#include <cmath>

namespace ui
{
    namespace
    {
        struct PageInfo
        {
            const char *name;
            const char *title;
            const char *id;
        };

        const PageInfo kPages[kPageCount] = {
            {"PLAY", "PLAY -- the state of the game and the button that starts it", "rail.play"},
            {"DISC", "DISC -- your SOCOM II image, checked file by file", "rail.disc"},
            {"VIDEO", "VIDEO -- detail, filtering and the window the game opens", "rail.video"},
            {"AUDIO", "AUDIO -- how loud the game is", "rail.audio"},
            {"CONTROLLER", "CONTROLLER -- what the game will read from your pad", "rail.controller"},
            {"MICROPHONE", "MICROPHONE -- the capture device, and proof it hears you", "rail.microphone"},
            {"ONLINE", "ONLINE -- the server, your profile, a second instance", "rail.online"},
            {"ABOUT", "ABOUT -- what this is, where it keeps things", "rail.about"},
        };

        void add(std::vector<Node> &out, Page page, const std::string &id, Rect r)
        {
            out.push_back(Node{id, r, page, false});
        }

        // A row of `n` equal cells across `r`, with a gap between them: the grid the radio rows sit on.
        Rect cell(Rect r, int index, int n, float gap = 10.0f)
        {
            const float w = (r.w - gap * static_cast<float>(n - 1)) / static_cast<float>(n);
            return Rect{r.x + (w + gap) * static_cast<float>(index), r.y, w, r.h};
        }
    }

    Page pageAt(int index)
    {
        if (index < 0)
            index = 0;
        if (index >= kPageCount)
            index = kPageCount - 1;
        return static_cast<Page>(index);
    }

    int pageIndex(Page page) { return static_cast<int>(page); }
    const char *pageName(Page page) { return kPages[pageIndex(page)].name; }
    const char *pageTitle(Page page) { return kPages[pageIndex(page)].title; }
    std::string railId(Page page) { return kPages[pageIndex(page)].id; }

    std::string barLaunchId(Page page)
    {
        std::string name = pageName(page);
        for (char &c : name)
            c = static_cast<char>(c >= 'A' && c <= 'Z' ? c + 32 : c);
        return "bar.launch." + name;
    }

    Frame frameFor(Rect window)
    {
        using namespace metrics;
        Frame f;
        f.window = window;
        f.header = Rect{0.0f, 0.0f, window.w, barH};              // the launcher's own title bar
        f.bar = Rect{0.0f, window.h - bottomH, window.w, bottomH};
        f.rail = Rect{0.0f, barH, railW, window.h - barH - bottomH};
        f.content = Rect{railW + margin, barH + 20.0f, window.w - railW - margin - margin,
                         (window.h - bottomH - 16.0f) - (barH + 20.0f)};
        f.body = Rect{f.content.x + 20.0f, f.content.y + 54.0f, f.content.w - 40.0f, f.content.h - 54.0f - 20.0f};
        return f;
    }

    std::vector<Node> railLayout(Rect window)
    {
        const Frame f = frameFor(window);
        std::vector<Node> out;
        for (int i = 0; i < kPageCount; ++i)
        {
            const Page p = pageAt(i);
            const Rect r{12.0f, f.rail.y + metrics::railTop + static_cast<float>(i) * (metrics::railRowH + metrics::railGap),
                         metrics::railW - 24.0f, metrics::railRowH};
            out.push_back(Node{railId(p), r, p, true});
        }
        return out;
    }

    std::vector<Node> layoutFor(Page page, Rect window, const LayoutInputs &in)
    {
        const Frame f = frameFor(window);
        const Rect b = f.body;
        std::vector<Node> out;

        switch (page)
        {
        case Page::Play:
        {
            // Four rows that say what the game is about to do, each one a jump to the page that changes it.
            for (int i = 0; i < 4; ++i)
            {
                static const char *ids[] = {"play.disc", "play.video", "play.pad", "play.server"};
                add(out, page, ids[i], Rect{b.x, b.y + static_cast<float>(i) * 66.0f, b.w, 56.0f});
            }
            const float y = b.bottom() - 64.0f;
            add(out, page, "play.launch", Rect{b.x, y, 300.0f, 64.0f});
            add(out, page, "play.diagnostics", Rect{b.x + 320.0f, y + 12.0f, 200.0f, 40.0f});
            add(out, page, "play.logs", Rect{b.x + 536.0f, y + 12.0f, 150.0f, 40.0f});
            break;
        }
        case Page::Disc:
        {
            add(out, page, "disc.path", Rect{b.x + metrics::labelW, b.y + 8.0f, b.w - metrics::labelW - 140.0f, 40.0f});
            add(out, page, "disc.browse", Rect{b.right() - 128.0f, b.y + 8.0f, 128.0f, 40.0f});
            add(out, page, "disc.verify", Rect{b.x + metrics::labelW, b.y + 150.0f, 200.0f, 40.0f});
            break;
        }
        case Page::Video:
        {
            const float rowStep = metrics::rowH + 22.0f;
            const Rect ctrl0{b.x + metrics::labelW, b.y + 6.0f, b.w - metrics::labelW, 44.0f};
            for (int i = 0; i < 4; ++i)
                add(out, page, "video.detail." + std::to_string(i), cell(ctrl0, i, 4));
            Rect ctrl1 = ctrl0;
            ctrl1.y += rowStep;
            for (int i = 0; i < 3; ++i)
                add(out, page, "video.filter." + std::to_string(i), cell(ctrl1, i, 3));
            Rect ctrl2 = ctrl0;
            ctrl2.y += rowStep * 2.0f;
            for (int i = 0; i < 4; ++i)
                add(out, page, "video.window." + std::to_string(i), cell(ctrl2, i, 4));
            add(out, page, "video.fps", Rect{ctrl0.x, ctrl0.y + rowStep * 3.0f, b.w - metrics::labelW, 40.0f});
            break;
        }
        case Page::Audio:
        {
            add(out, page, "audio.volume", Rect{b.x + metrics::labelW, b.y + 22.0f, b.w - metrics::labelW - 90.0f, 32.0f});
            break;
        }
        case Page::Controller:
        {
            const float below = b.y + 342.0f;   // under the drawn pad, its legend and the section labels
            const int pads = in.padChoices < 1 ? 1 : in.padChoices;
            for (int i = 0; i < pads; ++i)
                add(out, page, "pad.pick." + std::to_string(i), Rect{b.x, below + static_cast<float>(i) * 30.0f, 400.0f, 26.0f});
            const float rx = b.x + 440.0f;
            const float rw = b.w - 440.0f;
            add(out, page, "pad.deadzone", Rect{rx, below, rw, 28.0f});
            add(out, page, "pad.mouselook", Rect{rx, below + 44.0f, rw, 28.0f});
            add(out, page, "pad.sensitivity", Rect{rx, below + 92.0f, rw, 28.0f});
            // R139: the crouch shortcut, four cells across both columns, under the page's one line of help.
            const Rect crouch{b.x + metrics::labelW, below + 144.0f, b.w - metrics::labelW, 28.0f};
            for (int i = 0; i < 4; ++i)
                add(out, page, "pad.crouch." + std::to_string(i), cell(crouch, i, 4));
            break;
        }
        case Page::Microphone:
        {
            const int mics = in.micChoices < 1 ? 1 : in.micChoices;
            for (int i = 0; i < mics; ++i)
                add(out, page, "mic.pick." + std::to_string(i), Rect{b.x, b.y + 26.0f + static_cast<float>(i) * 32.0f, 400.0f, 28.0f});
            add(out, page, "mic.rescan", Rect{b.right() - 140.0f, b.y + 22.0f, 140.0f, 36.0f});
            break;
        }
        case Page::Online:
        {
            for (int i = 0; i < 3; ++i)
                if (launcher::presetAvailable(launcher::kServerPresets[i]))
                    add(out, page, "online.preset." + std::to_string(i), onlinePresetRow(window, i));
            const float y = b.y + 26.0f + 3.0f * 38.0f + 22.0f;
            if (in.customServer)
                add(out, page, "online.server", Rect{b.x + metrics::labelW, y, 420.0f, 40.0f});
            add(out, page, "online.profile", Rect{b.x + metrics::labelW, y + 56.0f, 300.0f, 40.0f});
            add(out, page, "online.second", Rect{b.x + metrics::labelW, y + 112.0f, 460.0f, 34.0f});
            break;
        }
        case Page::About:
        {
            add(out, page, "about.logs", Rect{b.x, b.bottom() - 48.0f, 200.0f, 40.0f});
            break;
        }
        }

        // The bottom bar's LAUNCH belongs to every page but PLAY, which has its own large one: there the bar
        // carries the run's state instead of the same button twice.
        if (page != Page::Play)
            add(out, page, barLaunchId(page), Rect{f.bar.right() - metrics::margin - 220.0f, f.bar.y + 10.0f, 220.0f, 36.0f});
        return out;
    }

    Rect onlinePresetRow(Rect window, int index)
    {
        const Frame f = frameFor(window);
        return Rect{f.body.x, f.body.y + 26.0f + static_cast<float>(index) * 38.0f, f.body.w, 32.0f};
    }

    Rect rectOf(const std::vector<Node> &nodes, const std::string &id)
    {
        for (const Node &n : nodes)
            if (n.id == id)
                return n.r;
        return Rect{};
    }

    bool hasNode(const std::vector<Node> &nodes, const std::string &id)
    {
        for (const Node &n : nodes)
            if (n.id == id)
                return true;
        return false;
    }

    FocusGraph FocusGraph::build(Rect window, const LayoutInputs &in)
    {
        FocusGraph g;
        g.m_nodes = railLayout(window);
        for (int i = 0; i < kPageCount; ++i)
        {
            const std::vector<Node> page = layoutFor(pageAt(i), window, in);
            g.m_nodes.insert(g.m_nodes.end(), page.begin(), page.end());
        }
        return g;
    }

    const Node *FocusGraph::find(const std::string &id) const
    {
        for (const Node &n : m_nodes)
            if (n.id == id)
                return &n;
        return nullptr;
    }

    std::vector<std::string> FocusGraph::idsOn(Page page) const
    {
        std::vector<std::string> out;
        for (const Node &n : m_nodes)
            if (!n.rail && n.page == page)
                out.push_back(n.id);
        return out;
    }

    std::string FocusGraph::firstOn(Page page) const
    {
        for (const Node &n : m_nodes)
            if (!n.rail && n.page == page)
                return n.id;
        return railId(page);
    }

    std::string FocusGraph::move(const std::string &from, Dir dir) const
    {
        const Node *f = find(from);
        if (f == nullptr)
            return from;

        if (f->rail)
        {
            const int i = pageIndex(f->page);
            switch (dir)
            {
            case Dir::Up:
                return railId(pageAt(i - 1 < 0 ? 0 : i - 1));
            case Dir::Down:
                return railId(pageAt(i + 1 >= kPageCount ? kPageCount - 1 : i + 1));
            case Dir::Right:
                return firstOn(f->page);
            case Dir::Left:
                return from;
            }
            return from;
        }

        // Inside a page: the nearest node that way, preferring one whose band overlaps this control's.
        auto scan = [&](bool requireOverlap) -> std::string
        {
            std::string best;
            float bestScore = 0.0f;
            for (const Node &n : m_nodes)
            {
                if (n.rail || n.page != f->page || n.id == f->id)
                    continue;
                float primary = 0.0f, perp = 0.0f;
                bool overlap = false;
                switch (dir)
                {
                case Dir::Right:
                    primary = n.r.cx() - f->r.cx();
                    perp = std::fabs(n.r.cy() - f->r.cy());
                    overlap = n.r.bottom() > f->r.y && n.r.y < f->r.bottom();
                    break;
                case Dir::Left:
                    primary = f->r.cx() - n.r.cx();
                    perp = std::fabs(n.r.cy() - f->r.cy());
                    overlap = n.r.bottom() > f->r.y && n.r.y < f->r.bottom();
                    break;
                case Dir::Down:
                    primary = n.r.cy() - f->r.cy();
                    perp = std::fabs(n.r.cx() - f->r.cx());
                    overlap = n.r.right() > f->r.x && n.r.x < f->r.right();
                    break;
                case Dir::Up:
                    primary = f->r.cy() - n.r.cy();
                    perp = std::fabs(n.r.cx() - f->r.cx());
                    overlap = n.r.right() > f->r.x && n.r.x < f->r.right();
                    break;
                }
                if (primary <= 1.0f)
                    continue;
                if (requireOverlap && !overlap)
                    continue;
                // Distance in the direction moved dominates: the row under this control wins even when a
                // row further down happens to line up with it exactly (the VIDEO page's cells do).
                const float score = primary * 4.0f + perp;
                if (best.empty() || score < bestScore)
                {
                    best = n.id;
                    bestScore = score;
                }
            }
            return best;
        };

        std::string best = scan(true);
        if (best.empty())
            best = scan(false);
        if (!best.empty())
            return best;
        if (dir == Dir::Left)
            return railId(f->page);   // nothing further left: back out to the rail
        return from;
    }

    void Nav::goTo(const FocusGraph &g, Page p)
    {
        page = p;
        focus = g.firstOn(p);
    }

    void Nav::move(const FocusGraph &g, Dir d)
    {
        const std::string next = g.move(focus, d);
        focus = next;
        const Node *n = g.find(next);
        if (n != nullptr)
            page = n->page;   // a rail entry IS its page: the highlight and the pane never disagree
    }

    void Nav::back(const FocusGraph &g)
    {
        (void)g;
        focus = railId(page);
    }

    bool Nav::onRail() const { return focus == railId(page); }

    void FocusRing::update(const FocusGraph &g, const std::string &focusId, float dt)
    {
        const Node *n = g.find(focusId);
        if (n == nullptr)
        {
            visible = false;
            return;
        }
        // No travel, by owner's request ("takes too long to adjust and awkwardly flys with a delay"): the
        // ring is the focused control's rect, whole, on the frame the focus changed. `dt` is taken and
        // ignored on purpose, so no frame time can put a delay back without the test noticing.
        (void)dt;
        shown = n->r;
        visible = true;
    }

    std::string launchBlockedReason(bool discOk, bool running, bool isoPathEmpty)
    {
        if (running)
            return "the game is running";
        if (isoPathEmpty)
            return "choose your SOCOM II disc image first";
        if (!discOk)
            return "that file is not SOCOM II (NTSC, r0001)";
        return std::string();
    }

    bool adjustsHorizontally(const std::string &id)
    {
        return id == "audio.volume" || id == "pad.deadzone" || id == "pad.sensitivity";
    }
}
