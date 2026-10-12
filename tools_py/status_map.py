"""The README's status map: Sony SDK libraries and PS2 hardware, drawn from docs/status/status.toml.

Run: python -m tools_py.status_map            regenerate docs/status/map.svg and docs/status/detail.md
     python -m tools_py.status_map --check    write nothing; exit 1 if either file is stale

The idea and the look come from KIexster/god-of-war-recomp's "Current status" map (docs/estado/, GPL-3.0); this
code is our own. Panel 1 is one cell per function of the libraries statically linked into SCUS_972.75 (r0001),
counted from the function map ps2_recomp compiles (recomp/socom2_ghidra.csv plus recomp/extra_functions.txt) and
grouped by the address ranges the data file gives each library -- the linker lays a library out contiguously, and
the boundaries come from the named functions in recomp/socom2_names.csv. Panel 2 is the PS2's hardware, one
rectangle per component, sized by its weight. Every status is a judgement read from docs/KNOWN.md (which wins on
any disagreement) and is written, with its reason, in the data file; this module only counts and draws.

The percentages count "ok" only: functions for panel 1, weights for panel 2. Output is deterministic (no dates,
no dict-order dependence) so `--check` can compare bytes. Standard library only (tomllib: Python 3.11+).
"""
import argparse
import csv
import math
import os
import re
import sys
import tomllib
from html import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = "docs/status/status.toml"
OUT_SVG = "docs/status/map.svg"
OUT_MD = "docs/status/detail.md"

STATUSES = ("ok", "partial", "pending")
LABEL = {"ok": "Working", "partial": "Partial", "pending": "Pending"}

# ----------------------------------------------------------------------------------------------------------------
# Data
# ----------------------------------------------------------------------------------------------------------------


def load(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


def _status(value, where):
    if value not in STATUSES:
        raise ValueError("%s: unknown status %r (use %s)" % (where, value, ", ".join(STATUSES)))
    return value


def function_starts(root, data):
    """Every function start ps2_recomp compiles: the map's Start column plus the forced entries, once each."""
    fn = data["functions"]
    starts = set()
    with open(os.path.join(root, fn["map"]), newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            starts.add(int(row["Start"], 16))
    extra = fn.get("extra")
    if extra:
        with open(os.path.join(root, extra), encoding="utf-8") as f:
            for line in f:
                m = re.match(r"\s*0[xX]([0-9a-fA-F]+)", line)
                if m:
                    starts.add(int(m.group(1), 16))
    return sorted(starts)


def library_rows(data, starts):
    """[{name, count, status, note, ranges, first}] in the data file's order; refuses overlaps and empty rows."""
    spans = []
    rows = []
    for lib in data.get("library", []):
        name = lib["name"]
        status = _status(lib["status"], "library %s" % name)
        ranges = [(int(a), int(b)) for a, b in lib["ranges"]]
        for a, b in ranges:
            if not a < b:
                raise ValueError("library %s: empty range 0x%X..0x%X" % (name, a, b))
            spans.append((a, b, name))
        count = sum(1 for s in starts for a, b in ranges if a <= s < b)
        if count == 0:
            raise ValueError("library %s: no function starts in its ranges" % name)
        rows.append({"name": name, "short": lib.get("short", name), "count": count, "status": status,
                     "note": lib.get("note", "").strip(),
                     "ranges": ranges, "first": min(a for a, _ in ranges)})
    spans.sort()
    for (a1, b1, n1), (a2, b2, n2) in zip(spans, spans[1:]):
        if a2 < b1:
            raise ValueError("libraries %s and %s overlap at 0x%X" % (n1, n2, a2))
    return rows


def hardware_rows(data):
    """[{name, components: [{short, name, status, weight, note}]}] in the data file's order."""
    groups = []
    for g in data.get("hardware", []):
        comps = []
        for c in g.get("component", []):
            weight = c.get("weight", 1)
            if not (isinstance(weight, (int, float)) and weight > 0):
                raise ValueError("component %s: weight must be a positive number, not %r" % (c["short"], weight))
            comps.append({"short": c["short"], "name": c.get("name", c["short"]),
                          "status": _status(c["status"], "component %s" % c["short"]),
                          "weight": weight, "note": c.get("note", "").strip()})
        if not comps:
            raise ValueError("hardware group %s: no components" % g["group"])
        groups.append({"name": g["group"], "components": comps})
    return groups


def feature_rows(data):
    """[{label, percent, categories, note}]: each badge is the plain mean of the category scores it names."""
    scores = {c["name"]: float(c["percent"]) for c in data.get("category", [])}
    rows = []
    for f in data.get("feature", []):
        names = list(f["categories"])
        unknown = [n for n in names if n not in scores]
        if not names or unknown:
            raise ValueError("feature %s: unknown or no categories %r" % (f["label"], unknown))
        rows.append({"label": f["label"], "percent": sum(scores[n] for n in names) / len(names),
                     "categories": names, "note": f.get("note", "").strip()})
    return rows


def percent(pairs):
    """(percent ok, ok weight, total weight) over (weight, status) pairs."""
    total = sum(w for w, _ in pairs)
    ok = sum(w for w, s in pairs if s == "ok")
    return (100.0 * ok / total if total else 0.0), ok, total


def fmt_pct(p):
    return "%.1f%%" % p


def _lib_pairs(libs):
    return [(r["count"], r["status"]) for r in libs]


def _hw_pairs(hw):
    return [(c["weight"], c["status"]) for g in hw for c in g["components"]]


# ----------------------------------------------------------------------------------------------------------------
# Layout: a squarified treemap (Bruls, Huizing and van Wijk, 2000) and an even grid inside each library
# ----------------------------------------------------------------------------------------------------------------


def _worst(row, side):
    s = sum(row)
    return max(max(side * side * a / (s * s), (s * s) / (side * side * a)) for a in row)


def squarify(values, x, y, w, h):
    """Rectangles (x, y, w, h) for `values`, in order, tiling the box; best when values run large to small."""
    total = float(sum(values))
    if not values or total <= 0:
        return [(x, y, 0.0, 0.0) for _ in values]
    areas = [v * w * h / total for v in values]
    out = []
    i = 0
    while i < len(areas):
        side = min(w, h)
        row = [areas[i]]
        j = i + 1
        while j < len(areas) and _worst(row + [areas[j]], side) <= _worst(row, side):
            row.append(areas[j])
            j += 1
        s = sum(row)
        if w >= h:                      # lay the row as a column on the left
            cw = s / h if h else 0.0
            yy = y
            for a in row:
                ch = a / cw if cw else 0.0
                out.append((x, yy, cw, ch))
                yy += ch
            x, w = x + cw, w - cw
        else:                           # lay the row along the top
            rh = s / w if w else 0.0
            xx = x
            for a in row:
                rw = a / rh if rh else 0.0
                out.append((xx, y, rw, rh))
                xx += rw
            y, h = y + rh, h - rh
        i = j
    return out


def grid(n, w, h):
    """(columns, rows) for n equal cells in w x h, as square as possible with few empty slots."""
    best, best_cost = (1, n), math.inf
    for cols in range(1, n + 1):
        rows = math.ceil(n / cols)
        cw, ch = w / cols, h / rows
        cost = max(cw / ch, ch / cw) + 0.05 * (cols * rows - n)
        if cost < best_cost:
            best, best_cost = (cols, rows), cost
    return best


# ----------------------------------------------------------------------------------------------------------------
# SVG
# ----------------------------------------------------------------------------------------------------------------

WIDTH = 960
MARGIN = 20
GUTTER = 20
MAP_H = 320
GROUP_GAP = 3.0
CELL_GAP = 1.0
FONT = "font-family=\"-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif\""

STYLE = """
  .bg { fill: #0d1117; } .edge { stroke: #30363d; } .panel { fill: #161b22; }
  .t1 { fill: #e6edf3; } .t2 { fill: #9198a1; } .dark { fill: #0d1117; }
  .ok { fill: #2ea043; } .partial { fill: #d29922; } .pending { fill: #484f58; }
  .hatch { stroke: #6e4b00; } .chip { fill: #0d1117; fill-opacity: .82; } .key { fill: #30363d; }
  .pct { fill: #1f6feb; } .pct-t { fill: #ffffff; }
  .lib-edge { fill: none; stroke: #c9d1d9; stroke-opacity: .55; stroke-width: 1.2; }
"""
TEXT_ON = {"ok": "t1", "partial": "dark", "pending": "t1"}


def _n(v):
    s = "%.1f" % v
    return s[:-2] if s.endswith(".0") else s


def _tw(text, size):
    """Estimated text width: good enough to decide whether a label fits."""
    return len(text) * size * 0.56


def _rect(cls, x, y, w, h, extra=""):
    return '<rect class="%s" x="%s" y="%s" width="%s" height="%s"%s/>' % (cls, _n(x), _n(y), _n(w), _n(h), extra)


def _cell(status, x, y, w, h, tip=None):
    body = "><title>%s</title></rect>" % escape(tip) if tip else "/>"
    out = ['<rect class="%s" x="%s" y="%s" width="%s" height="%s"%s' % (status, _n(x), _n(y), _n(w), _n(h), body)]
    if status == "partial":
        out.append(_rect("", x, y, w, h, ' fill="url(#hatch)" pointer-events="none"').replace('class="" ', ""))
    return out


def _badge(x, y, key, value):
    """A percentage badge. Neutral blue on purpose: a number is not a status, so it must not borrow the legend's
    green/amber/grey (a 41% badge in amber would read as "Partial")."""
    size, h, pad = 12, 22, 8
    wk, wv = _tw(key, size) + 2 * pad, _tw(value, size) + 2 * pad
    return [
        _rect("key", x, y, wk + wv, h, ' rx="3"'),
        _rect("pct", x + wk, y, wv, h, ' rx="3"'),
        _rect("pct", x + wk, y, 4, h),
        '<text class="t1" x="%s" y="%s" font-size="%d" text-anchor="middle">%s</text>'
        % (_n(x + wk / 2), _n(y + 15), size, escape(key)),
        '<text class="%s" x="%s" y="%s" font-size="%d" font-weight="600" text-anchor="middle">%s</text>'
        % ("pct-t", _n(x + wk + wv / 2), _n(y + 15), size, escape(value)),
    ], wk + wv


def _chip(label, x, y, w, h, size=11):
    cw = _tw(label, size) + 8
    if cw > w or h < size + 6:
        return []
    return [_rect("chip", x + 1, y + 1, cw, size + 5, ' rx="2" pointer-events="none"'),
            '<text class="t1" x="%s" y="%s" font-size="%d" pointer-events="none">%s</text>'
            % (_n(x + 5), _n(y + size + 1), size, escape(label))]


def _libraries_panel(libs, x, y, w, h):
    """(svg parts, the names too small to carry a label -- the caller lists those under the map)."""
    out = [_rect("panel", x, y, w, h)]
    chips = []
    edges = []
    unlabelled = []
    order = sorted(libs, key=lambda r: (-r["count"], r["first"]))
    for lib, (gx, gy, gw, gh) in zip(order, squarify([r["count"] for r in order], x, y, w, h)):
        gx, gy, gw, gh = gx + GROUP_GAP / 2, gy + GROUP_GAP / 2, gw - GROUP_GAP, gh - GROUP_GAP
        if gw <= 0 or gh <= 0:
            continue
        cols, rows = grid(lib["count"], gw, gh)
        cw, ch = gw / cols, gh / rows
        tip = "%s: %d functions -- %s. %s" % (lib["name"], lib["count"], LABEL[lib["status"]], lib["note"])
        out.append("<g><title>%s</title>" % escape(tip))
        for k in range(lib["count"]):
            cx, cy = gx + (k % cols) * cw, gy + (k // cols) * ch
            out += _cell(lib["status"], cx + CELL_GAP / 2, cy + CELL_GAP / 2,
                         max(cw - CELL_GAP, 0.5), max(ch - CELL_GAP, 0.5))
        out.append("</g>")
        # Each library gets its own outline, so an unlabelled block cannot read as part of a labelled neighbour.
        edges.append(_rect("lib-edge", gx, gy, gw, gh, ' rx="1" pointer-events="none"'))
        chip =_chip(lib["short"], gx, gy, gw, gh) or _chip(lib["short"], gx, gy, gw, gh, 9)
        chips += chip
        if not chip:
            unlabelled.append(lib["short"])
    return out + edges + chips, unlabelled


def _hardware_panel(hw, x, y, w, h):
    out = [_rect("panel", x, y, w, h)]
    chips = []
    order = sorted(hw, key=lambda g: -sum(c["weight"] for c in g["components"]))
    totals = [sum(c["weight"] for c in g["components"]) for g in order]
    for g, (gx, gy, gw, gh) in zip(order, squarify(totals, x, y, w, h)):
        gx, gy, gw, gh = gx + GROUP_GAP / 2, gy + GROUP_GAP / 2, gw - GROUP_GAP, gh - GROUP_GAP
        top = 18                                   # room for the group's own label above its components
        comps = sorted(g["components"], key=lambda c: (STATUSES.index(c["status"]), -c["weight"]))
        rects = squarify([c["weight"] for c in comps], gx, gy + top, gw, gh - top)
        chips += _chip(g["name"], gx, gy, gw, top + 4)
        for c, (cx, cy, cw, ch) in zip(comps, rects):
            rx, ry = cx + CELL_GAP, cy + CELL_GAP
            rw, rh = max(cw - 2 * CELL_GAP, 0.5), max(ch - 2 * CELL_GAP, 0.5)
            out += _cell(c["status"], rx, ry, rw, rh, "%s -- %s: %s" % (c["name"], LABEL[c["status"]], c["note"]))
            size = next((s for s in (12, 10) if _tw(c["short"], s) + 8 <= rw and rh >= s + 6), None)
            turn = ""
            if size is None:
                size = next((s for s in (12, 10) if _tw(c["short"], s) + 8 <= rh and rw >= s + 6), None)
                turn = size is not None
            if size:
                tx, ty = rx + rw / 2, ry + rh / 2
                rot = ' transform="rotate(-90 %s %s)"' % (_n(tx), _n(ty)) if turn else ""
                out.append('<text class="%s" x="%s" y="%s" font-size="%d" text-anchor="middle"%s '
                           'pointer-events="none">%s</text>'
                           % (TEXT_ON[c["status"]], _n(tx), _n(ty + size * 0.35), size, rot, escape(c["short"])))
    return out + chips


def render_svg(data, libs, hw):
    meta = data.get("meta", {})
    title = meta.get("title", "Status")
    p_lib, ok_lib, tot_lib = percent(_lib_pairs(libs))
    p_hw, _, _ = percent(_hw_pairs(hw))
    features = feature_rows(data)
    footnotes = meta.get("footnote", [])

    y_badges = 58
    y_titles = y_badges + 50
    y_map = y_titles + 10
    y_legend = y_map + MAP_H + 26
    height = y_legend + 14 + 16 * len(footnotes) + 8
    panel_w = (WIDTH - 2 * MARGIN - GUTTER) / 2

    o = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" %s role="img" '
         'aria-labelledby="status-title">' % (WIDTH, height, WIDTH, height, FONT),
         '<title id="status-title">%s: Sony SDK libraries %s, PS2 hardware %s</title>'
         % (escape(title), fmt_pct(p_lib), fmt_pct(p_hw)),
         "<style>%s</style>" % STYLE,
         '<defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" '
         'patternTransform="rotate(45)"><line class="hatch" x1="0" y1="0" x2="0" y2="6" stroke-width="1.6" '
         'stroke-opacity=".6"/></pattern></defs>',
         _rect("bg", 0, 0, WIDTH, height, ' rx="8"'),
         '<text class="t1" x="%d" y="36" font-size="22" font-weight="600">%s</text>' % (MARGIN, escape(title)),
         '<line class="edge" x1="%d" y1="46" x2="%d" y2="46" stroke-width="1"/>' % (MARGIN, WIDTH - MARGIN)]

    x = MARGIN
    for key, p in (("Sony SDK libraries*", p_lib), ("PS2 hardware", p_hw)):
        parts, bw = _badge(x, y_badges, key, fmt_pct(p))
        o += parts
        x += bw + 10
    if features:
        x += 14
        o.append('<line class="edge" x1="%s" y1="%d" x2="%s" y2="%d" stroke-width="1"/>'
                 % (_n(x - 12), y_badges, _n(x - 12), y_badges + 22))
        for f in features:
            parts, bw = _badge(x, y_badges, f["label"] + "\u2020", "%.0f%%" % f["percent"])
            o += parts
            x += bw + 10

    lib_parts, unlabelled = _libraries_panel(libs, MARGIN, y_map, panel_w, MAP_H)
    hw_x = MARGIN + panel_w + GUTTER
    for px, head, parts in (
            (MARGIN, "Sony SDK libraries*: %s (%d/%d functions)" % (fmt_pct(p_lib), ok_lib, tot_lib), lib_parts),
            (hw_x, "PS2 hardware: %s (by weight)" % fmt_pct(p_hw), _hardware_panel(hw, hw_x, y_map, panel_w, MAP_H))):
        o.append('<text class="t1" x="%s" y="%d" font-size="14" font-weight="600">%s</text>'
                 % (_n(px), y_titles, escape(head)))
        o += parts

    x = MARGIN
    for s in STATUSES:
        o.append(_rect(s, x, y_legend - 10, 12, 12, ' rx="2"'))
        if s == "partial":
            o.append(_rect("", x, y_legend - 10, 12, 12, ' rx="2" fill="url(#hatch)"').replace('class="" ', ""))
        o.append('<text class="t2" x="%d" y="%d" font-size="12">%s</text>' % (x + 17, y_legend, LABEL[s]))
        x += 17 + int(_tw(LABEL[s], 12)) + 20
    if unlabelled:
        o.append('<text class="t2" x="%d" y="%d" font-size="11">Too small to label: %s (in the table)</text>'
                 % (x + 10, y_legend, escape(", ".join(unlabelled))))
    for k, line in enumerate(footnotes):
        o.append('<text class="t2" x="%d" y="%d" font-size="11">%s</text>'
                 % (MARGIN, y_legend + 20 + 16 * k, escape(line)))
    o.append("</svg>")
    return "\n".join(o) + "\n"


# ----------------------------------------------------------------------------------------------------------------
# The table (the same facts as text: searchable, and readable without the picture)
# ----------------------------------------------------------------------------------------------------------------


def _md(text):
    return text.replace("|", "\\|").replace("\n", " ")


def render_detail(data, libs, hw):
    p_lib, ok_lib, tot_lib = percent(_lib_pairs(libs))
    p_hw, _, _ = percent(_hw_pairs(hw))
    meta = data.get("meta", {})
    o = ["# The status map, in detail", "",
         "![The status map](map.svg)", "",
         "Generated by `python -m tools_py.status_map` from `docs/status/status.toml`; do not edit by hand (edit the",
         "data file and regenerate; `--check` fails while this file or `map.svg` is stale). Statuses are read from",
         "`docs/KNOWN.md`, which wins on any disagreement. *Working* counts towards the percentages; *Partial* and",
         "*Pending* do not.", ""]
    if meta.get("intro"):
        o += [meta["intro"].strip(), ""]
    o += ["## Sony SDK libraries: %s (%d of %d functions)" % (fmt_pct(p_lib), ok_lib, tot_lib), "",
          "| Library | Functions | Status | Address ranges | Note |", "|---|---:|---|---|---|"]
    for r in sorted(libs, key=lambda r: r["first"]):
        spans = ", ".join("`0x%06X-0x%06X`" % (a, b) for a, b in r["ranges"])
        o.append("| `%s` | %d | %s | %s | %s |" % (r["name"], r["count"], LABEL[r["status"]], spans, _md(r["note"])))
    o.append("| **Total** | **%d** | %d working | | |" % (tot_lib, ok_lib))
    o += ["", "## PS2 hardware: %s (by weight)" % fmt_pct(p_hw), "",
          "| Group | Component | What | Weight | Status | Note |", "|---|---|---|---:|---|---|"]
    for g in hw:
        for c in g["components"]:
            o.append("| %s | %s | %s | %s | %s | %s |" % (g["name"], c["short"], _md(c["name"]), c["weight"],
                                                       LABEL[c["status"]], _md(c["note"])))
    features = feature_rows(data)
    if features:
        counted = {}
        for f in features:
            for n in f["categories"]:
                counted.setdefault(n, []).append(f["label"])
        o += ["", "## Feature completion", ""]
        if meta.get("feature_intro"):
            o += [meta["feature_intro"].strip(), ""]
        for f in features:
            k = len(f["categories"])
            o.append("- **%s: %.0f%%** -- the plain mean of %d category score%s below (%.2f before rounding)%s"
                     % (f["label"], f["percent"], k, "" if k == 1 else "s", f["percent"],
                        ". %s" % _md(f["note"]) if f["note"] else "."))
        o += ["", "| Category | % | Counted in | Note |", "|---|---:|---|---|"]
        for c in data.get("category", []):
            o.append("| %s | %s | %s | %s |" % (_md(c["name"]), c["percent"],
                                               ", ".join(counted.get(c["name"], [])) or "--",
                                               _md(c.get("note", "").strip())))
    if meta.get("footnote"):
        notes = [re.sub(r"^\*", r"\*", line) for line in meta["footnote"]]
        o += [""] + ["%s  " % line for line in notes[:-1]] + [notes[-1]]
    return "\n".join(o) + "\n"


# ----------------------------------------------------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------------------------------------------------


def outputs(root=ROOT):
    """{repo-relative path: expected content} for the two generated files."""
    data = load(os.path.join(root, DATA))
    libs = library_rows(data, function_starts(root, data))
    hw = hardware_rows(data)
    return {OUT_SVG: render_svg(data, libs, hw), OUT_MD: render_detail(data, libs, hw)}


def _current(path, text):
    if not os.path.isfile(path):
        return False
    with open(path, encoding="utf-8") as f:          # universal newlines: a CRLF checkout is not stale
        return f.read() == text


def main(argv=None, root=None):
    root = root or ROOT
    ap = argparse.ArgumentParser(prog="python -m tools_py.status_map", description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="write nothing; exit 1 if a generated file is stale")
    args = ap.parse_args(argv)
    want = outputs(root)
    stale = [rel for rel, text in sorted(want.items()) if not _current(os.path.join(root, rel), text)]
    if args.check:
        for rel in stale:
            print("stale: %s" % rel)
        if stale:
            print("run: python -m tools_py.status_map")
        return 1 if stale else 0
    for rel in stale:
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(want[rel])
        print("wrote: %s" % rel)
    if not stale:
        print("unchanged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
