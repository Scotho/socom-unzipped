"""Score our screens against the golden set and write docs/parity/REPORT.md.

score = 100 * (1 - 0.5*mad - 0.5*block) at 320x224, where mad is the mean absolute RGB difference
(0..1) and block the fraction of 16x16 blocks whose mean colour differs by more than a threshold.
"""
import os
import re

import numpy as np
from PIL import Image

SIZE = (320, 224)


def _arr(im):
    return np.asarray(im.convert("RGB").resize(SIZE, Image.BOX), dtype=np.float32) / 255.0


def score(golden, ours, block_thresh=0.08):
    g, o = _arr(golden), _arr(ours)
    mad = float(np.abs(g - o).mean())
    gb = g.reshape(14, 16, 20, 16, 3).mean(axis=(1, 3))
    ob = o.reshape(14, 16, 20, 16, 3).mean(axis=(1, 3))
    block = float((np.abs(gb - ob).mean(axis=2) > block_thresh).mean())
    return {"score": round(max(0.0, min(100.0, 100 * (1 - 0.5 * mad - 0.5 * block))), 1),
            "mad": round(mad, 4), "block": round(block, 4)}


def side_by_side(golden, ours):
    g = golden.convert("RGB").resize(SIZE)
    o = ours.convert("RGB").resize(SIZE)
    d = np.abs(_arr(g) - _arr(o)).mean(axis=2)
    heat = Image.fromarray((np.clip(d * 4, 0, 1) * 255).astype("uint8")).convert("RGB")
    out = Image.new("RGB", (SIZE[0] * 3, SIZE[1]))
    out.paste(g, (0, 0))
    out.paste(o, (SIZE[0], 0))
    out.paste(heat, (SIZE[0] * 2, 0))
    return out


def _prev_scores(prev_md):
    if not prev_md or not os.path.exists(prev_md):
        return {}
    return {m.group(1): float(m.group(2))
            for m in re.finditer(r"^\| ([^|]+?) \| ([0-9.]+) \|", open(prev_md, encoding="utf-8").read(), re.M)}


def report(golden_dir, run_dir, out_md, prev_md=None, stamp="", align=None):
    """align: {golden_label: [ours_label or None, note]} (scripts/parity/align.json); without it the
    same label is compared on both sides."""
    prev = _prev_scores(prev_md)
    align = align or {}
    rows = []
    for f in sorted(os.listdir(golden_dir)):
        if not f.endswith(".png") or f == "final.png":
            continue
        name = f[:-4]
        ours_label, note = (align.get(name) or [name, ""])[:2]
        ours_p = os.path.join(run_dir, ours_label + ".png") if ours_label else None
        if not ours_p or not os.path.exists(ours_p):
            rows.append({"screen": name, "score": None, "note": note or "not reached"})
            continue
        g, o = Image.open(os.path.join(golden_dir, f)), Image.open(ours_p)
        s = score(g, o)
        side_by_side(g, o).save(os.path.join(run_dir, name + ".diff.png"))
        rows.append({"screen": name, **s,
                     "delta": (s["score"] - prev[name]) if name in prev else None,
                     "note": (f"ours {ours_label}; " if ours_label != name else "") + note})
    scored = [r["score"] for r in rows if r["score"] is not None]
    os.makedirs(os.path.dirname(out_md), exist_ok=True)
    with open(out_md, "w", newline="\n", encoding="utf-8") as w:
        w.write(f"# Parity report {stamp}\n\n")
        w.write(f"Golden: PCSX2 2.8.1 (`{golden_dir}`). Run: `{run_dir}`. "
                "Score = 100·(1 − 0.5·mad − 0.5·block) at 320x224; screens are the step script's "
                "capture points (`scripts/parity/launch_to_mission.txt`), same index on both sides.\n\n")
        if scored:
            w.write(f"**Mean score {sum(scored) / len(scored):.1f} over {len(scored)} screens"
                    f" ({len(rows) - len(scored)} not reached).**\n\n")
        w.write("| screen | score | delta | mad | block | note |\n|---|---|---|---|---|---|\n")
        for r in rows:
            sc = "—" if r["score"] is None else f"{r['score']}"
            dl = "" if r.get("delta") is None else f"{r['delta']:+.1f}"
            w.write(f"| {r['screen']} | {sc} | {dl} | {r.get('mad', '')} | {r.get('block', '')} | {r['note']} |\n")
    return rows
