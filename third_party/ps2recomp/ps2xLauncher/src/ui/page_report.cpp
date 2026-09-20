// Sprint 9 Goal 8, the REPORT A BUG page: the site's own form (sites/s2u/src/report.ts -- TITLE, WHAT HAPPENED,
// CONTACT (OPTIONAL), SEND REPORT), the log checkbox that is OFF until the player ticks it, and one line that
// says exactly what SEND would send. The page only edits App::report and raises requestSend: main.cpp's loop
// checks the form, builds the payload and runs the request off this thread.
#include "pages.h"

namespace ui
{
    namespace
    {
        // A field's label in the label column; a label with a bracketed tail puts the tail on a second line
        // ("CONTACT" / "(OPTIONAL)") so the site's wording fits the launcher's grid.
        void fieldLabel(const Ctx &ctx, Rect control, const char *label)
        {
            const std::string whole = label;
            const size_t bracket = whole.find(" (");
            const float x = control.x - metrics::labelW;
            if (bracket == std::string::npos)
            {
                text(ctx, label, Vec2{x, control.y + 11.0f}, metrics::labelSize, theme::dim, Face::Bold, 0.06f);
                return;
            }
            text(ctx, whole.substr(0, bracket).c_str(), Vec2{x, control.y + 3.0f}, metrics::labelSize, theme::dim, Face::Bold, 0.06f);
            text(ctx, whole.substr(bracket + 1).c_str(), Vec2{x, control.y + 21.0f}, metrics::captionSize - 2.0f, theme::dim, Face::Bold, 0.06f);
        }
    }

    void drawReportPage(const Ctx &ctx, App &app, const std::vector<Node> &nodes)
    {
        namespace br = launcher::bugreport;
        ReportUi &rep = app.report;
        const bool sending = rep.state == ReportUi::State::Sending;
        bool changed = false;

        const Rect title = rectOf(nodes, "report.title");
        fieldLabel(ctx, title, br::kLabelTitle);
        textField(ctx, title, rep.form.title, "report.title", changed, !sending, br::kTitleMax);

        const Rect what = rectOf(nodes, "report.description");
        fieldLabel(ctx, what, br::kLabelDescription);
        if (sending)
        {
            bool ignored = false;
            Ctx frozen = ctx;
            frozen.activeField = nullptr;
            frozen.click = false;
            frozen.activate = false;
            textArea(frozen, what, rep.form.description, "report.description", ignored, br::kDescriptionMax);
        }
        else
            textArea(ctx, what, rep.form.description, "report.description", changed, br::kDescriptionMax);
        const std::string count = std::to_string(br::utf16Length(rep.form.description)) + " / " + std::to_string(br::kDescriptionMax);
        text(ctx, count.c_str(), Vec2{what.x - metrics::labelW, what.y + 32.0f}, metrics::captionSize - 2.0f, theme::dim);

        const Rect contact = rectOf(nodes, "report.contact");
        fieldLabel(ctx, contact, br::kLabelContact);
        textField(ctx, contact, rep.form.contact, "report.contact", changed, !sending, br::kContactMax);
        caption(ctx, Vec2{contact.right() + 18.0f, contact.y + 12.0f}, "only if you want an answer");

        const Rect attach = rectOf(nodes, "report.attach");
        bool attachLog = rep.form.attachLog;
        if (toggle(ctx, attach, br::kLabelAttach, "report.attach", attachLog) && !sending)
        {
            rep.form.attachLog = attachLog;
            changed = true;
        }

        // What SEND would send, said before it is sent.
        const float previewW = app.frame.body.right() - attach.x;
        float y = attach.bottom() + 12.0f;
        const std::vector<std::string> preview = wrapText(ctx, rep.preview, previewW, metrics::captionSize - 1.0f);
        for (size_t i = 0; i < preview.size() && i < 3; ++i)
        {
            text(ctx, preview[i].c_str(), Vec2{attach.x, y}, metrics::captionSize - 1.0f, theme::caption);
            y += (metrics::captionSize - 1.0f) * 1.25f;
        }

        const Rect send = rectOf(nodes, "report.send");
        static const char *spinner[] = {"SENDING", "SENDING .", "SENDING . .", "SENDING . . ."};
        const char *label = sending ? spinner[ctx.fake ? 3 : (static_cast<int>(ctx.time * 3.0) & 3)] : br::kLabelSend;
        if (button(ctx, send, label, "report.send", !sending, true))
            rep.requestSend = true;

        // The reply, next to and under SEND: the reference large, everything else one line.
        const float rx = send.right() + 22.0f;
        const float rw = app.frame.body.right() - rx;
        switch (rep.state)
        {
        case ReportUi::State::Idle:
            caption(ctx, Vec2{rx, send.y + 13.0f}, "Nothing leaves this machine until you press it.");
            break;
        case ReportUi::State::Sending:
            caption(ctx, Vec2{rx, send.y + 13.0f}, "talking to s2u.scotho.com ...");
            break;
        case ReportUi::State::Sent:
        {
            text(ctx, rep.id.empty() ? "REPORT RECEIVED" : rep.id.c_str(), Vec2{rx, send.y - 2.0f}, 34.0f, theme::goldHi, Face::Bold, 0.06f);
            const std::string under = rep.id.empty() ? std::string("Thank you.")
                                                    : std::string("REPORT RECEIVED. Quote this reference if you talk to us") +
                                                          (rep.copied ? " -- copied to the clipboard." : ".");
            text(ctx, ellipsizeEnd(ctx, under, app.frame.body.right() - send.x, metrics::captionSize).c_str(),
                 Vec2{send.x, send.bottom() + 12.0f}, metrics::captionSize, theme::lampGreen);
            break;
        }
        case ReportUi::State::FieldError:
        case ReportUi::State::RateLimited:
        case ReportUi::State::SavedLocally:
        {
            // Under SEND, the whole width: the reply's line, then where the report went if it went to disk.
            const float full = app.frame.body.right() - send.x;
            text(ctx, ellipsizeEnd(ctx, rep.message, full, metrics::captionSize, Face::Bold).c_str(),
                 Vec2{send.x, send.bottom() + 10.0f}, metrics::captionSize, theme::warn, Face::Bold);
            if (!rep.savedPath.empty())
            {
                const std::string lead = "Saved on this machine instead: ";
                const float leadW = textWidth(ctx, lead.c_str(), metrics::captionSize);
                const std::string where = lead + ellipsizeStart(ctx, rep.savedPath, full - leadW, metrics::captionSize);
                text(ctx, where.c_str(), Vec2{send.x, send.bottom() + 32.0f}, metrics::captionSize, theme::text);
            }
            break;
        }
        }
        (void)rw;

        if (changed)
        {
            rep.changed = true;
            // Typing after a reply starts a new report: the old reply's line goes.
            if (rep.state != ReportUi::State::Sending)
            {
                rep.state = ReportUi::State::Idle;
                rep.message.clear();
                rep.savedPath.clear();
            }
        }
    }
}
