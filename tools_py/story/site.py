"""Render the story as one self-contained page: a vertical timeline in the landing site's own look.

Spec 6.2: the site does not re-derive the timeline. This reads `docs/STORY.md` (already checked by the citation
test) and `docs/story/timeline.json`, and writes one HTML file with the CSS and the script inline and the pictures
referenced from `img/`, so the page and its images can be copied anywhere together. It fetches nothing and runs
no git; it is a build step, not a server.

The look is `../scotho/sites/s2u`'s: its teal, gold and off-white, the briefing-panel typography, its fonts
(Oswald, Exo 2, Share Tech Mono), scanlines. The timeline is a spine down the page with a node per entry and a
band per era; entries reveal as they scroll into view (not at all when the viewer prefers reduced motion), and
each has a stable anchor, `#<date>-<slug>`, which is the per-entry URL shape the spec asks the site for.

Usage:
    python -m tools_py.story.site [--story docs/STORY.md] [--timeline docs/story/timeline.json]
                                  [--out docs/story/index.html] [--img img] [--logo img/logo.webp]
                                  [--repo https://github.com/Scotho/socom-unzipped] [--full-document]
    For the site copy, under Git Bash:
        MSYS_NO_PATHCONV=1 python -m tools_py.story.site --full-document
            --out C:/projects/scotho/sites/s2u/story.html --img /story/img --logo /img/logo.webp
    Without MSYS_NO_PATHCONV=1, "/story/img" arrives as "C:/Program Files/Git/story/img" (it did, once, and the live
    page lost every picture); with it, --out must be a Windows path, since "/c/..." is not translated either.
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
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:60].rstrip("-")


def inline(text):
    out = html.escape(text, quote=False)
    out = _CODE_RE.sub(lambda m: "<code>%s</code>" % m.group(1), out)
    out = _BOLD_RE.sub(lambda m: "<strong>%s</strong>" % m.group(1), out)
    out = _ITAL_RE.sub(lambda m: "<em>%s</em>" % m.group(1), out)
    return out


def parse_document(markdown):
    doc = {"title": "", "preface": [], "eras": [], "closing": []}
    section, era, entry, para = "preface", None, None, []

    def flush():
        if not para:
            return
        text = " ".join(x.strip() for x in para).strip()
        del para[:]
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

    for raw in markdown.splitlines():
        if raw.startswith("# "):
            flush(); doc["title"] = raw[2:].strip(); continue
        if raw.startswith("## "):
            flush()
            head = raw[3:].strip()
            m = re.match(r"^(\d{4}-\d{2}-\d{2}) \.\. (\d{4}-\d{2}-\d{2}) [—-]+ (.+)$", head)
            if m:
                section, entry = "era", None
                era = {"start": m.group(1), "end": m.group(2), "title": m.group(3), "standing": "", "entries": []}
                doc["eras"].append(era)
            elif not doc["eras"]:
                section, entry = "closing", None
                doc.setdefault("foreword", {"title": head, "blocks": []})
                doc["closing"].append(doc["foreword"])
            else:
                section, entry = "closing", None
                doc["closing"].append({"title": head, "blocks": []})
            continue
        m = cite._ENTRY_RE.match(raw)
        if m and section == "era":
            flush()
            entry = {"date": m.group(1), "title": m.group(2), "blocks": []}
            era["entries"].append(entry)
            continue
        if raw.strip() == "":
            flush(); continue
        if raw.startswith("```"):
            continue
        para.append(raw)
    flush()
    return doc


MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def pretty_date(d):
    y, m, dd = d.split("-")
    return "%s %d" % (MONTHS[int(m)], int(dd))


def render_entry(e, repo, img_base, index):
    anchor = "%s-%s" % (e["date"], slug(e["title"]))
    parts = ['<li class="node" id="%s" style="--i:%d">' % (anchor, index),
             '<div class="dot" aria-hidden="true"></div>',
             '<article class="card">',
             '<header><time datetime="%s">%s<span class="yr"> %s</span></time>'
             '<h3><a href="#%s">%s</a></h3></header>' % (e["date"], pretty_date(e["date"]), e["date"][:4], anchor, inline(e["title"]))]
    body, how, but, cited, figure = [], None, None, None, None
    for b in e["blocks"]:
        if b.startswith("**") and b.endswith("**"):
            parts.append('<p class="hook">%s</p>' % inline(b[2:-2]))
        elif b.startswith("*How:*"):
            how = inline(b[len("*How:*"):].strip())
        elif b.startswith("*But:*"):
            but = inline(b[len("*But:*"):].strip())
        elif b.startswith("`Cited:`"):
            try:
                cits = cite.parse_cited(b)
            except ValueError:
                cits = []
            chips = []
            for c in cits:
                if c.kind == "commit":
                    frag = html.escape(c.fragment) if c.fragment else ""
                    chips.append('<a class="cite commit" href="%s/commit/%s"><code>%s</code>%s</a>'
                                 % (repo, c.ref, c.ref, (" " + frag) if frag else ""))
                elif c.kind in ("run", "gate", "log"):
                    chips.append('<span class="cite run" title="a run record; its witness is in docs/story/witnesses.json">%s %s</span>'
                                 % (c.kind, html.escape(c.ref)))
                else:
                    chips.append('<a class="cite path" href="%s/blob/main/%s">%s</a>' % (repo, c.ref, html.escape(c.ref)))
            cited = " ".join(chips)
        elif _IMG_RE.match(b):
            m = _IMG_RE.match(b)
            caption, path = m.group(1), m.group(2)
            figure = ('<figure><img src="%s/%s" alt="%s" loading="lazy">'
                      '<figcaption>%s</figcaption></figure>'
                      % (img_base, os.path.basename(path), html.escape(caption, quote=True), inline(caption)))
        else:
            body.append("<p>%s</p>" % inline(b))
    parts.extend(body)
    if figure:
        parts.append(figure)
    if how:
        parts.append('<p class="how"><span class="lbl">How</span>%s</p>' % how)
    if but:
        parts.append('<p class="but"><span class="lbl">But</span>%s</p>' % but)
    if cited:
        parts.append('<details class="cited"><summary><span class="lbl">Cited</span><span class="n">%d</span></summary>'
                     '<div class="chips">%s</div></details>' % (cited.count('class="cite'), cited))
    parts.append("</article></li>")
    return "\n".join(parts)


CSS = r"""
:root{--bg:#0a1216;--bg2:#06100f;--panel:rgba(10,30,36,.82);--panel2:rgba(10,38,44,.9);--line:rgba(60,120,126,.5);
--line2:rgba(60,120,126,.28);--teal:#4c8688;--teal2:#2f5c60;--glow:#7fd9e6;--lit:#ece7dc;--ink:#e9e4d8;--dim:#9fb4b8;
--dim2:#6f8f94;--gold:#d9b23a;--gold2:#f0cf5c;--mono:'Share Tech Mono','Courier New',monospace;
--head:'Oswald','Arial Narrow',sans-serif;--body:Georgia,'Times New Roman',serif;--disp:'Exo 2',sans-serif;
--spine:2px;--rail:64px;color-scheme:dark}
*{box-sizing:border-box}
html{scroll-behavior:smooth;scroll-padding-top:72px}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 var(--body);padding-inline:16px;position:relative}
body::before{content:"";position:fixed;inset:0;z-index:-2;background:
radial-gradient(ellipse at 85% -10%,rgba(40,90,100,.45),transparent 55%),
radial-gradient(ellipse at 0% 110%,rgba(30,60,70,.35),transparent 50%),
linear-gradient(180deg,var(--bg) 0%,var(--bg2) 100%)}
body::after{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;opacity:.35;
background:repeating-linear-gradient(to bottom,rgba(0,0,0,0) 0 2px,rgba(0,0,0,.28) 2px 3px)}
a{color:var(--glow)}a:focus-visible{outline:2px solid var(--gold);outline-offset:2px}
code{font:.86em var(--mono);color:var(--glow)}
.wrap{max-width:900px;margin:0 auto;padding-block:28px 96px}
/* progress bar */
#progress{position:fixed;left:0;top:0;height:3px;width:100%;z-index:10;background:rgba(0,0,0,.4);padding-top:env(safe-area-inset-top,0px)}
#progress i{display:block;height:3px;width:0;background:linear-gradient(90deg,var(--teal),var(--gold));box-shadow:0 0 8px rgba(217,178,58,.6);transition:width .1s linear}
/* header */
.top{padding-top:12px;position:relative}
.top .logo{display:block;width:min(420px,78vw);height:auto;margin:0 0 6px -10px;filter:saturate(.92) brightness(.96) drop-shadow(0 0 22px rgba(127,217,230,.28))}
.wrap::before{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;background:radial-gradient(ellipse at 50% 40%,transparent 55%,rgba(0,0,0,.45) 100%)}
/* the creator's foreword */
.foreword{margin:26px 0 0;padding:20px 22px 16px;background:linear-gradient(180deg,rgba(10,38,44,.9),rgba(10,30,36,.78));border:1px solid var(--line);position:relative}
.foreword::before{content:"";position:absolute;left:0;top:0;bottom:0;width:3px;background:linear-gradient(180deg,var(--gold),transparent)}
.foreword .brief-sub{margin-bottom:8px}
.foreword p{margin:8px 0;max-width:70ch;font-size:16.5px;line-height:1.6}
.foreword .sig{font:600 14px/1.2 var(--head);letter-spacing:1.6px;color:var(--gold);margin-top:14px}
.brief-sub{font:600 12px/1.4 var(--head);letter-spacing:2.6px;text-transform:uppercase;color:var(--gold);margin:0 0 10px}
.brief-title{font:800 clamp(34px,7vw,64px)/.98 var(--disp);font-style:italic;letter-spacing:.5px;color:var(--lit);margin:0;
text-shadow:0 0 2px rgba(127,217,230,.9),0 0 18px rgba(127,217,230,.35);text-wrap:balance}
.brief-title small{display:block;font:700 clamp(15px,2.6vw,22px)/1.2 var(--disp);font-style:italic;color:var(--glow);letter-spacing:1px;margin-top:8px;text-shadow:none}
.lede{color:var(--dim);font-style:italic;margin:20px 0 0;max-width:62ch}
.preface{margin-top:22px;display:grid;gap:12px}
.preface p{margin:0;max-width:70ch}
.preface strong{color:var(--lit);font-family:var(--head);font-weight:600;letter-spacing:.4px;font-style:normal}
/* stats strip */
.strip{display:flex;flex-wrap:wrap;gap:10px;margin:26px 0 0;padding:0;list-style:none}
.strip li{flex:1 1 130px;padding:10px 12px;background:var(--panel2);border:1px solid var(--line)}
.strip b{display:block;font:600 24px/1 var(--head);color:var(--gold2);font-variant-numeric:tabular-nums}
.strip span{font:600 11px/1.3 var(--head);letter-spacing:1.6px;text-transform:uppercase;color:var(--dim)}
/* era nav */
nav.eras{position:sticky;top:env(safe-area-inset-top,0px);z-index:5;margin:26px -16px 0;padding:8px 16px;display:flex;gap:6px;overflow-x:auto;
background:rgba(8,18,22,.88);backdrop-filter:blur(6px);border-bottom:1px solid var(--line2);scrollbar-width:none}
nav.eras::-webkit-scrollbar{display:none}
nav.eras a{flex:none;padding:6px 10px;border:1px solid var(--line2);color:var(--dim);text-decoration:none;
font:600 11px/1.2 var(--head);letter-spacing:1.4px;text-transform:uppercase;transition:color .15s,border-color .15s}
nav.eras a small{display:block;font:10px/1.2 var(--mono);letter-spacing:.3px;color:var(--dim2);text-transform:none;margin-top:2px}
nav.eras a:hover,nav.eras a.on{color:var(--lit);border-color:var(--gold)}
/* the timeline */
.tl{position:relative;margin:24px 0 0;padding:0;list-style:none}
.tl::before{content:"";position:absolute;left:calc(var(--rail)/2 - var(--spine)/2);top:0;bottom:0;width:var(--spine);
background:linear-gradient(180deg,transparent 0,var(--teal) 40px,var(--teal) calc(100% - 40px),transparent 100%);opacity:.7}
.era{position:relative;padding:38px 0 6px var(--rail);margin:0}
.era .mark{position:absolute;left:calc(var(--rail)/2 - 15px);top:44px;width:30px;height:30px;border:2px solid var(--gold);
background:var(--bg);transform:rotate(45deg);box-shadow:0 0 0 6px var(--bg),0 0 18px rgba(217,178,58,.5)}
.era .mark::after{content:"";position:absolute;inset:7px;background:var(--gold)}
.era .span{font:12px/1.2 var(--mono);letter-spacing:1.4px;color:var(--gold);display:block;margin:0 0 6px}
.era h2{font:600 clamp(22px,3.6vw,30px)/1.15 var(--head);letter-spacing:.8px;color:var(--lit);margin:0;text-wrap:balance}
.era .standing{color:var(--dim);font-style:italic;margin:10px 0 0;max-width:66ch}
.node{position:relative;padding:22px 0 0 var(--rail);margin:0}
.dot{position:absolute;left:calc(var(--rail)/2 - 7px);top:36px;width:14px;height:14px;border-radius:50%;background:var(--bg);
border:2px solid var(--teal);box-shadow:0 0 0 5px var(--bg);transition:border-color .3s,box-shadow .3s}
.node:target .dot,.node.in .dot{border-color:var(--glow);box-shadow:0 0 0 5px var(--bg),0 0 14px rgba(127,217,230,.55)}
.node.pic .dot{border-color:var(--gold)}
.card{position:relative;padding:16px 18px 14px;background:var(--panel);border:1px solid var(--line2);
transition:border-color .25s,transform .5s cubic-bezier(.2,.7,.2,1),box-shadow .25s}
.card:hover{border-color:var(--line);box-shadow:0 8px 30px rgba(0,0,0,.35)}
.node.pic .card::after{content:"";position:absolute;right:12px;top:12px;width:8px;height:8px;background:var(--gold);transform:rotate(45deg);opacity:.7}
.card::before{content:"";position:absolute;left:-9px;top:14px;border:8px solid transparent;border-right-color:var(--line2);border-left:0}
.node:target .card{border-color:var(--gold);box-shadow:0 0 0 1px rgba(217,178,58,.3)}
.card header{display:flex;gap:12px;align-items:baseline;flex-wrap:wrap}
.card time{font:12.5px/1.2 var(--mono);letter-spacing:1.2px;color:var(--gold);font-variant-numeric:tabular-nums;white-space:nowrap}
.card time .yr{color:var(--dim2)}
.card h3{font:600 20px/1.2 var(--head);letter-spacing:.4px;margin:0;color:var(--lit)}
.card h3 a{color:inherit;text-decoration:none}.card h3 a:hover{color:#fff;text-shadow:0 0 6px rgba(127,217,230,.6)}
.hook{font:700 17px/1.4 var(--disp);font-style:italic;color:#fff;margin:10px 0 8px;text-wrap:pretty}
.card p{margin:9px 0;max-width:68ch}
.card code{background:rgba(0,0,0,.35);padding:1px 4px}
.lbl{display:inline-block;font:600 10px/1 var(--head);letter-spacing:1.6px;text-transform:uppercase;padding:3px 6px;margin:0 8px 0 0;
vertical-align:2px;border:1px solid var(--line);color:var(--dim)}
.how{color:var(--dim);font-size:14.5px}.how .lbl{color:var(--teal)}
.but{border-left:2px solid var(--gold);padding-left:12px;font-size:15px}.but .lbl{color:var(--gold);border-color:rgba(217,178,58,.5)}
details.cited{margin-top:10px;font-size:12.5px;color:var(--dim2)}
details.cited summary{cursor:pointer;list-style:none;display:inline-flex;align-items:center;gap:6px;color:var(--dim)}
details.cited summary::-webkit-details-marker{display:none}
details.cited summary .n{font:11px var(--mono);color:var(--dim2)}
details.cited summary::after{content:"+";font:600 14px var(--head);color:var(--teal)}
details[open].cited summary::after{content:"\2212"}
.chips{margin-top:8px;line-height:1.9}
.cite{display:inline-block;margin:0 6px 4px 0;padding:1px 6px;border:1px solid var(--line2);text-decoration:none;color:var(--dim)}
.cite.commit code{color:var(--glow);background:none;padding:0}
.cite.commit:hover{border-color:var(--glow);color:var(--lit)}
.cite.run{font-family:var(--mono);font-size:12px;color:var(--teal)}
figure{margin:12px 0 4px;border:1px solid var(--line2);background:#000;max-width:640px}
figure img{display:block;width:100%;height:auto;filter:saturate(.95)}
figcaption{padding:8px 10px;font:12.5px/1.45 var(--head);letter-spacing:.4px;color:var(--dim)}
/* closing */
.closing{margin-top:48px;padding:18px 20px;background:var(--panel2);border:1px solid var(--line)}
.closing h2{font:600 22px/1.2 var(--head);letter-spacing:1px;color:var(--gold);margin:0 0 10px}
.closing p{max-width:70ch}
footer.foot{margin-top:40px;font:12px/1.7 var(--mono);letter-spacing:.5px;color:var(--dim2)}
footer.foot a{color:var(--teal)}
/* reveal */
/* cards are readable at rest (a thumbnail or a paused reader sees the page whole); the reveal is a small lift and
   the node lighting up, never an opacity:0 wait on an observer */
@media (prefers-reduced-motion:no-preference){
 .card{transform:translateY(14px)}
 .node.in .card,.node:target .card{transform:none;border-color:var(--line)}
}
@media (prefers-reduced-motion:reduce){html{scroll-behavior:auto}.card{transform:none}}
@media (max-width:560px){:root{--rail:34px}.card{padding:12px 12px 10px}.card header{gap:6px}.era .mark{width:22px;height:22px;left:calc(var(--rail)/2 - 11px);top:48px}
.era .mark::after{inset:5px}.dot{width:12px;height:12px;left:calc(var(--rail)/2 - 6px)}}
"""

JS = r"""
(function(){
  var bar=document.querySelector('#progress i');
  function prog(){var h=document.documentElement,max=h.scrollHeight-h.clientHeight;if(bar)bar.style.width=(max>0?(h.scrollTop/max*100):0)+'%';}
  addEventListener('scroll',prog,{passive:true});prog();
  var nodes=[].slice.call(document.querySelectorAll('.node'));
  var reduce=matchMedia('(prefers-reduced-motion: reduce)').matches;
  if(!reduce&&'IntersectionObserver' in window){
    var io=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){e.target.classList.add('in');io.unobserve(e.target);}});},{rootMargin:'0px 0px -12% 0px',threshold:0.08});
    nodes.forEach(function(n){io.observe(n);});
    if(location.hash){var t=document.querySelector(location.hash);if(t){t.classList.add('in');}}
  } else { nodes.forEach(function(n){n.classList.add('in');}); }
  var links=[].slice.call(document.querySelectorAll('nav.eras a')),eras=[].slice.call(document.querySelectorAll('.era'));
  function current(){var y=scrollY+120,on=null;eras.forEach(function(s){if(s.offsetTop<=y)on=s.id;});links.forEach(function(a){a.classList.toggle('on',a.getAttribute('href')==='#'+on);});}
  addEventListener('scroll',current,{passive:true});current();
})();
"""


def stamped(logo_url, out_path):
    """The logo URL with ?v=<sha256 prefix> of the file it names, when that file can be found beside the page.

    Cloudflare served a week-old /img/logo.webp to the live story page once, so the site busts its own assets with
    a version query; the story page does the same from the file's hash, not a date. The file is looked for as the
    page would resolve it (`<out dir>/<url>`) and, for the Vite site, under `<out dir>/public/<url>`; when neither
    exists the URL is left alone."""
    if "?" in logo_url:
        return logo_url
    rel = logo_url.lstrip("/")
    out_dir = os.path.dirname(os.path.abspath(out_path)) if out_path and out_path != os.devnull else ""
    for candidate in ([os.path.join(out_dir, rel), os.path.join(out_dir, "public", rel)] if out_dir else []):
        if os.path.isfile(candidate):
            import hashlib
            h = hashlib.sha256()
            with open(candidate, "rb") as f:
                h.update(f.read())
            return "%s?v=%s" % (logo_url, h.hexdigest()[:10])
    return logo_url


def render(doc, timeline, repo, img_base, logo):
    head_sha = timeline.get("head", "")
    entries = [e for era in doc["eras"] for e in era["entries"]]
    n_commits = sum(1 for e in timeline.get("entries", []) for c in e.get("citations", []) if c.get("kind") == "commit")
    n_pics = sum(1 for e in timeline.get("entries", []) if e.get("picture"))
    first, last = entries[0]["date"], entries[-1]["date"]
    days = (int(last[8:]) - int(first[8:])) + 1 if first[:7] == last[:7] else "18"
    title = doc["title"].replace("SOCOM Unzipped — ", "")
    fore = doc.get("foreword")
    closing = [c for c in doc["closing"] if c is not fore]
    out = ["<title>SOCOM Unzipped Story</title>",
           '<meta name="description" content="How SOCOM II became a PC game: the timeline, every claim cited.">',
           '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
           '<link href="https://fonts.googleapis.com/css2?family=Exo+2:ital,wght@1,700;1,800&family=Oswald:wght@500;600;700&family=Share+Tech+Mono&display=swap" rel="stylesheet">',
           "<style>%s</style>" % CSS,
           '<div id="progress" aria-hidden="true"><i></i></div>',
           '<div class="wrap">',
           '<header class="top">',
           '<img class="logo" src="%s" alt="SOCOM II U.S. Navy SEALs" width="640" height="280" decoding="async">' % logo,
           '<p class="brief-sub">Mission briefing &middot; operation unzipped</p>',
           '<h1 class="brief-title">%s<small>Trying to turn a PlayStation 2 game into a PC game. %s days in.</small></h1>'
           % (inline(title), days)]
    if doc["preface"]:
        out.append('<p class="lede">%s</p>' % inline(doc["preface"][0].strip("*")))
    out.append("</header>")
    out.append('<ul class="strip"><li><b>%d</b><span>entries</span></li><li><b>%d</b><span>commits cited</span></li>'
               '<li><b>%d</b><span>eras</span></li><li><b>%d</b><span>pictures</span></li><li><b>%s</b><span>first commit</span></li>'
               '<li><b>%s</b><span>latest</span></li></ul>' % (len(entries), n_commits, len(doc["eras"]), n_pics, pretty_date(first), pretty_date(last)))
    out.append('<section class="preface">')
    for p in doc["preface"][1:]:
        out.append("<p>%s</p>" % inline(p))
    out.append("</section>")
    if fore:
        out.append('<section class="foreword" id="from-the-creator"><p class="brief-sub">%s</p>' % inline(fore["title"]))
        for b in fore["blocks"]:
            if b.startswith("—") or b.startswith("--"):
                out.append('<p class="sig">%s</p>' % inline(b))
            else:
                out.append("<p>%s</p>" % inline(b))
        out.append("</section>")
    out.append('<nav class="eras" aria-label="Eras">')
    for era in doc["eras"]:
        out.append('<a href="#era-%s">%s<small>%s &ndash; %s &middot; %d</small></a>'
                   % (era["start"], inline(era["title"]), pretty_date(era["start"]), pretty_date(era["end"]), len(era["entries"])))
    out.append("</nav>")
    out.append('<ol class="tl">')
    idx = 0
    for era in doc["eras"]:
        out.append('<li class="era" id="era-%s"><div class="mark" aria-hidden="true"></div>'
                   '<span class="span">%s &ndash; %s</span><h2>%s</h2>' % (era["start"], era["start"], era["end"], inline(era["title"])))
        if era["standing"]:
            out.append('<p class="standing">%s</p>' % inline(era["standing"]))
        out.append("</li>")
        for e in era["entries"]:
            has_pic = any(_IMG_RE.match(b) for b in e["blocks"])
            html_e = render_entry(e, repo, img_base, idx)
            if has_pic:
                html_e = html_e.replace('class="node"', 'class="node pic"', 1)
            out.append(html_e)
            idx += 1
    out.append("</ol>")
    for c in closing:
        out.append('<section class="closing" id="%s"><h2>%s</h2>' % (slug(c["title"]), inline(c["title"])))
        for b in c["blocks"]:
            if b.startswith("python -m"):
                out.append("<p><code>%s</code></p>" % html.escape(b))
            else:
                out.append("<p>%s</p>" % inline(b))
        out.append("</section>")
    out.append('<footer class="foot">%d entries &middot; %d commit citations &middot; built from <code>docs/STORY.md</code> at <code>%s</code> '
               '&middot; checked by <code>tools_py/story/cite.py</code> &middot; link to a moment: <code>#&lt;date&gt;-&lt;slug&gt;</code></footer>'
               % (len(entries), n_commits, head_sha))
    out.append("</div>")
    out.append("<script>%s</script>" % JS)
    return "\n".join(out) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Render docs/STORY.md as one page.")
    ap.add_argument("--story", default=os.path.join(ROOT, "docs", "STORY.md"))
    ap.add_argument("--timeline", default=os.path.join(ROOT, "docs", "story", "timeline.json"))
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "story", "index.html"))
    ap.add_argument("--img", default="img", help="the pictures' path relative to the page")
    ap.add_argument("--logo", default="img/logo.webp", help="the site's logo, as the page will reference it")
    ap.add_argument("--repo", default="https://github.com/Scotho/socom-unzipped")
    ap.add_argument("--full-document", action="store_true",
                    help="wrap in <!doctype html><html><head>...; the default emits a fragment the Artifact tool wraps itself")
    args = ap.parse_args(argv)
    # Git Bash rewrites an argument that looks like an absolute POSIX path ("/story/img") into a Windows path
    # ("C:/Program Files/Git/story/img") before Python ever sees it. That shipped once: every picture and the logo
    # on s2u.scotho.com/story.html pointed at a path on the build machine. A URL path never carries a drive letter,
    # so one that does is refused here rather than rendered.
    for name, value in (("--img", args.img), ("--logo", args.logo)):
        if ":" in value or value.lower().startswith("c:/") or "Program Files" in value:
            sys.stderr.write("%s=%r is a filesystem path, not a URL path. Under Git Bash run with MSYS_NO_PATHCONV=1, "
                             "or write the argument as //story/img.\n" % (name, value))
            return 2
    with open(args.story, encoding="utf-8") as f:
        doc = parse_document(f.read())
    with open(args.timeline, encoding="utf-8") as f:
        timeline = json.load(f)
    page = render(doc, timeline, args.repo, args.img.rstrip("/"), stamped(args.logo, args.out))
    if args.full_document:
        head_end = page.index("<div id=\"progress\"")
        page = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1">\n' + page[:head_end] +
                '</head>\n<body>\n' + page[head_end:] + '</body>\n</html>\n')
    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(page)
    print("%s: %d bytes, %d eras, %d entries" % (args.out, len(page.encode("utf-8")), len(doc["eras"]),
                                                  sum(len(e["entries"]) for e in doc["eras"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
