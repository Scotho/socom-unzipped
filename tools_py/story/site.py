"""Render the story as one self-contained page -- the reference rendering the landing site takes a copy of.

Spec 6.2: the site does not re-derive the timeline. This reads `docs/STORY.md` (the prose, which the citation
test has already checked) and `docs/story/timeline.json` (the data), and writes `docs/story/index.html` with
the CSS inline and the pictures referenced from `img/`, so the page and its images can be copied anywhere
together. It is a build step, not a server: it fetches nothing and runs no git.

The look follows the landing site (`../scotho/sites/s2u`): its teal, gold and off-white, its briefing-panel
typography, and its fonts (Oswald, Exo 2, Share Tech Mono) -- the story reads as a page of that site rather
than as a document dropped beside it. Every entry has a stable anchor, `#<date>-<slug>`, which is the
per-entry URL shape the spec asks the site for.

Usage:
    python -m tools_py.story.site [--story docs/STORY.md] [--timeline docs/story/timeline.json]
                                  [--out docs/story/index.html] [--repo https://github.com/Scotho/socom-unzipped]
"""
import argparse
import html
import json
import os
import re
import sys

from tools_py.story import cite

ROOT = cite.ROOT
_IMG_RE = cite._IMG_RE
_CODE_RE = re.compile(r"`([^`]+)`")
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_ITAL_RE = re.compile(r"(?<!\*)\*(?!\*)([^*]+?)\*(?!\*)")


def slug(title):
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s[:60].rstrip("-")


def inline(text):
    """The little markdown the story uses: code spans, bold, italics. Everything else is escaped."""
    out = html.escape(text, quote=False)
    out = _CODE_RE.sub(lambda m: "<code>%s</code>" % m.group(1), out)
    out = _BOLD_RE.sub(lambda m: "<strong>%s</strong>" % m.group(1), out)
    out = _ITAL_RE.sub(lambda m: "<em>%s</em>" % m.group(1), out)
    return out


def parse_document(markdown):
    """The preface paragraphs, the eras (heading, standing line, entries), and the closing sections."""
    lines = markdown.splitlines()
    doc = {"title": "", "preface": [], "eras": [], "closing": []}
    section = "preface"
    era = None
    entry = None
    para = []

    def flush_para():
        if not para:
            return
        text = " ".join(x.strip() for x in para).strip()
        para[:] = []
        if not text or text == "---":
            return
        if section == "preface":
            doc["preface"].append(text)
        elif section == "era" and entry is not None:
            entry["blocks"].append(text)
        elif section == "era" and era is not None and not era["standing"] and text.startswith("*") and text.endswith("*"):
            era["standing"] = text.strip("*")
        elif section == "closing":
            doc["closing"][-1]["blocks"].append(text)

    for raw in lines:
        if raw.startswith("# "):
            flush_para()
            doc["title"] = raw[2:].strip()
            continue
        if raw.startswith("## "):
            flush_para()
            head = raw[3:].strip()
            m = re.match(r"^(\d{4}-\d{2}-\d{2}) \.\. (\d{4}-\d{2}-\d{2}) [—-]+ (.+)$", head)
            if m:
                section = "era"
                era = {"start": m.group(1), "end": m.group(2), "title": m.group(3), "standing": "", "entries": []}
                doc["eras"].append(era)
                entry = None
            else:
                section = "closing"
                doc["closing"].append({"title": head, "blocks": []})
                entry = None
            continue
        m = cite._ENTRY_RE.match(raw)
        if m and section == "era":
            flush_para()
            entry = {"date": m.group(1), "title": m.group(2), "blocks": []}
            era["entries"].append(entry)
            continue
        if raw.strip() == "":
            flush_para()
            continue
        if raw.startswith("```"):
            continue
        para.append(raw)
    flush_para()
    return doc


def render_entry(e, repo):
    anchor = "%s-%s" % (e["date"], slug(e["title"]))
    parts = ['<article class="entry" id="%s">' % anchor,
             '<header><time datetime="%s">%s</time><h3><a href="#%s">%s</a></h3></header>'
             % (e["date"], e["date"], anchor, inline(e["title"]))]
    for b in e["blocks"]:
        if b.startswith("**") and b.endswith("**"):
            parts.append('<p class="hook">%s</p>' % inline(b[2:-2]))
        elif b.startswith("*How:*"):
            parts.append('<p class="how"><span class="lbl">How</span>%s</p>' % inline(b[len("*How:*"):].strip()))
        elif b.startswith("*But:*"):
            parts.append('<p class="but"><span class="lbl">But</span>%s</p>' % inline(b[len("*But:*"):].strip()))
        elif b.startswith("`Cited:`"):
            try:
                cits = cite.parse_cited(b)
            except ValueError:
                cits = []
            chips = []
            for c in cits:
                if c.kind == "commit":
                    label = "<code>%s</code> %s" % (c.ref, html.escape(c.fragment)) if c.fragment else "<code>%s</code>" % c.ref
                    chips.append('<a class="cite commit" href="%s/commit/%s" title="%s">%s</a>'
                                 % (repo, c.ref, html.escape(c.fragment or c.ref, quote=True), label))
                elif c.kind in ("run", "gate", "log"):
                    chips.append('<span class="cite run" title="a run record; its witness is in docs/story/witnesses.json">%s %s</span>'
                                 % (c.kind if c.kind != "log" else "log", html.escape(c.ref)))
                else:
                    chips.append('<a class="cite path" href="%s/blob/main/%s">%s</a>' % (repo, c.ref, html.escape(c.ref)))
            parts.append('<p class="cited"><span class="lbl">Cited</span>%s</p>' % " ".join(chips))
        elif _IMG_RE.match(b):
            m = _IMG_RE.match(b)
            caption, path = m.group(1), m.group(2)
            rel = path.replace("docs/story/", "")
            parts.append('<figure><img src="%s" alt="%s" loading="lazy"><figcaption>%s</figcaption></figure>'
                         % (rel, html.escape(caption, quote=True), inline(caption)))
        else:
            parts.append("<p>%s</p>" % inline(b))
    parts.append("</article>")
    return "\n".join(parts)


CSS = """
:root{--bg:#0b1418;--bg2:#08121a;--panel:rgba(10,30,36,.78);--panel2:rgba(10,38,44,.85);--line:rgba(60,120,126,.45);
--line2:rgba(60,120,126,.3);--teal:#4c8688;--glow:#7fd9e6;--lit:#ece7dc;--ink:#f2ede3;--dim:#9fb4b8;--dim2:#6f8f94;
--gold:#d9b23a;--red:#ff6b5e;--green:#6fe08a;--mono:'Share Tech Mono','Courier New',monospace;
--head:'Oswald','Arial Narrow',sans-serif;--body:Georgia,'Times New Roman',serif;--disp:'Exo 2',sans-serif;
color-scheme:dark}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:radial-gradient(ellipse at 80% 0%,rgba(40,80,90,.35),transparent 55%),
linear-gradient(180deg,var(--bg) 0%,var(--bg2) 100%) fixed;color:var(--ink);font:16px/1.55 var(--body);padding-inline:16px}
a{color:var(--glow)}a:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
.wrap{max-width:820px;margin:0 auto;padding-block:32px 80px}
.brief-title{font:700 clamp(30px,6vw,52px)/1 var(--disp);font-style:italic;letter-spacing:1px;color:var(--lit);margin:0;
text-shadow:0 0 2px rgba(127,217,230,.9),0 0 12px rgba(127,217,230,.35);text-wrap:balance}
.brief-sub{font:600 13px/1.4 var(--head);letter-spacing:2.2px;text-transform:uppercase;color:var(--gold);margin:10px 0 0}
.lede{color:var(--dim);font-style:italic;margin:22px 0 0;max-width:62ch}
.preface p{margin:14px 0;max-width:66ch}
.preface strong{color:var(--lit);font-family:var(--head);font-weight:600;letter-spacing:.4px}
nav.eras{display:flex;flex-wrap:wrap;gap:8px;margin:28px 0 8px;padding:0;list-style:none}
nav.eras a{display:block;padding:8px 12px;background:var(--panel2);border:1px solid var(--line);color:var(--lit);
font:600 12px/1.2 var(--head);letter-spacing:1.4px;text-transform:uppercase;text-decoration:none}
nav.eras a:hover{border-color:var(--glow);color:#fff}
nav.eras small{display:block;font:11px/1.2 var(--mono);letter-spacing:.5px;color:var(--dim2);margin-top:3px;text-transform:none}
.era{margin-top:56px}
.era>header{border-bottom:1px solid var(--line);padding-bottom:10px;margin-bottom:8px}
.era h2{font:600 24px/1.15 var(--head);letter-spacing:1px;color:var(--gold);margin:0;text-wrap:balance}
.era .span{font:12px/1.2 var(--mono);letter-spacing:1px;color:var(--dim2);display:block;margin-bottom:6px}
.era .standing{color:var(--dim);font-style:italic;margin:10px 0 0;max-width:66ch}
.entry{margin-top:36px;padding:18px 20px 16px;background:var(--panel);border:1px solid var(--line2);scroll-margin-top:16px}
.entry:target{border-color:var(--gold);box-shadow:0 0 0 1px rgba(217,178,58,.35)}
.entry header{display:flex;gap:14px;align-items:baseline;flex-wrap:wrap}
.entry time{font:12px/1.2 var(--mono);letter-spacing:1.2px;color:var(--gold);font-variant-numeric:tabular-nums}
.entry h3{font:600 20px/1.2 var(--head);letter-spacing:.5px;margin:0;color:var(--lit)}
.entry h3 a{color:inherit;text-decoration:none}.entry h3 a:hover{color:#fff;text-shadow:0 0 6px rgba(127,217,230,.6)}
.hook{font:700 17px/1.4 var(--disp);font-style:italic;color:#fff;margin:12px 0 10px;text-wrap:pretty}
.entry p{margin:10px 0;max-width:68ch}
.entry code{font:13px var(--mono);color:var(--glow);background:rgba(0,0,0,.35);padding:1px 4px}
.lbl{display:inline-block;font:600 10.5px/1 var(--head);letter-spacing:1.6px;text-transform:uppercase;padding:3px 6px;
margin:0 8px 0 0;vertical-align:2px;border:1px solid var(--line);color:var(--dim)}
.how{color:var(--dim);font-size:14.5px}.how .lbl{color:var(--teal)}
.but{border-left:2px solid var(--gold);padding-left:12px;font-size:15px}.but .lbl{color:var(--gold);border-color:rgba(217,178,58,.5)}
.cited{font-size:12.5px;line-height:1.9;color:var(--dim2)}.cited .lbl{vertical-align:1px}
.cite{display:inline-block;margin:0 6px 4px 0;padding:1px 6px;border:1px solid var(--line2);text-decoration:none;color:var(--dim)}
.cite.commit code{color:var(--glow);background:none;padding:0}
.cite.commit:hover{border-color:var(--glow);color:var(--lit)}
.cite.run{font-family:var(--mono);font-size:12px;color:var(--teal)}
.cite.path{color:var(--dim)}
figure{margin:14px 0 6px;border:1px solid var(--line2);background:#000;max-width:100%}
figure img{display:block;width:100%;max-width:100%;height:auto;filter:saturate(.95)}
figcaption{padding:8px 10px;font:12.5px/1.45 var(--head);letter-spacing:.4px;color:var(--dim)}
.closing{margin-top:56px;padding-top:12px;border-top:1px solid var(--line)}
.closing h2{font:600 22px/1.2 var(--head);letter-spacing:1px;color:var(--gold);margin:0 0 10px}
.closing p{max-width:68ch}
.closing code{font:13px var(--mono);color:var(--glow)}
footer.foot{margin-top:60px;font:12px/1.6 var(--mono);letter-spacing:.6px;color:var(--dim2)}
footer.foot a{color:var(--teal)}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
@media (max-width:480px){.entry{padding:14px 12px}.entry header{gap:6px}}
"""


def render(doc, timeline, repo):
    head_sha = timeline.get("head", "")
    n_entries = sum(len(e["entries"]) for e in doc["eras"])
    n_commits = sum(1 for e in timeline.get("entries", []) for c in e.get("citations", []) if c.get("kind") == "commit")
    out = ["<title>SOCOM Unzipped Story</title>",
           '<meta name="description" content="The project\'s timeline, first commit to the present, every claim cited.">',
           '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
           '<link href="https://fonts.googleapis.com/css2?family=Exo+2:ital,wght@1,700;1,800&family=Oswald:wght@500;600;700&family=Share+Tech+Mono&display=swap" rel="stylesheet">',
           "<style>%s</style>" % CSS,
           '<div class="wrap">',
           '<header class="top"><p class="brief-sub">Mission briefing &middot; the story so far</p>',
           '<h1 class="brief-title">%s</h1>' % inline(doc["title"].replace("SOCOM Unzipped — ", "")),
           ]
    if doc["preface"]:
        out.append('<p class="lede">%s</p>' % inline(doc["preface"][0].strip("*")))
    out.append("</header>")
    out.append('<section class="preface">')
    for p in doc["preface"][1:]:
        out.append("<p>%s</p>" % inline(p))
    out.append("</section>")
    out.append('<nav class="eras" aria-label="Eras">')
    for era in doc["eras"]:
        out.append('<a href="#era-%s"><span>%s</span><small>%s .. %s &middot; %d entries</small></a>'
                   % (era["start"], inline(era["title"]), era["start"][5:], era["end"][5:], len(era["entries"])))
    out.append("</nav>")
    for era in doc["eras"]:
        out.append('<section class="era" id="era-%s"><header><span class="span">%s .. %s</span><h2>%s</h2>'
                   % (era["start"], era["start"], era["end"], inline(era["title"])))
        if era["standing"]:
            out.append('<p class="standing">%s</p>' % inline(era["standing"]))
        out.append("</header>")
        for e in era["entries"]:
            out.append(render_entry(e, repo))
        out.append("</section>")
    for c in doc["closing"]:
        out.append('<section class="closing" id="%s"><h2>%s</h2>' % (slug(c["title"]), inline(c["title"])))
        for b in c["blocks"]:
            if b.startswith("python -m"):
                out.append("<p><code>%s</code></p>" % html.escape(b))
            else:
                out.append("<p>%s</p>" % inline(b))
        out.append("</section>")
    out.append('<footer class="foot">%d entries &middot; %d commit citations &middot; built from <code>docs/STORY.md</code> at <code>%s</code> '
               '&middot; checked by <code>tools_py/story/cite.py</code> &middot; per-entry links: <code>#&lt;date&gt;-&lt;slug&gt;</code></footer>'
               % (n_entries, n_commits, head_sha))
    out.append("</div>")
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Render docs/STORY.md as one page.")
    ap.add_argument("--story", default=os.path.join(ROOT, "docs", "STORY.md"))
    ap.add_argument("--timeline", default=os.path.join(ROOT, "docs", "story", "timeline.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "story", "index.html"))
    ap.add_argument("--repo", default="https://github.com/Scotho/socom-unzipped")
    args = ap.parse_args(argv)
    with open(args.story, encoding="utf-8") as f:
        doc = parse_document(f.read())
    with open(args.timeline, encoding="utf-8") as f:
        timeline = json.load(f)
    page = render(doc, timeline, args.repo)
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    print("%s: %d bytes, %d eras, %d entries" % (args.out, len(page.encode("utf-8")), len(doc["eras"]),
                                                  sum(len(e["entries"]) for e in doc["eras"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
