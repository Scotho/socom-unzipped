"""Tile every PNG of a directory into one labelled contact sheet: python -m tools_py.parity.montage <dir> <out.png>"""
import os, sys
from PIL import Image, ImageDraw
d, out = sys.argv[1], sys.argv[2]
files = sorted(f for f in os.listdir(d) if f.endswith(".png") and not f.endswith(".diff.png"))
W, H, cols = 320, 240, 4
rows = (len(files) + cols - 1) // cols
sheet = Image.new("RGB", (cols * W, rows * (H + 16)), (30, 30, 30))
dr = ImageDraw.Draw(sheet)
for i, f in enumerate(files):
    im = Image.open(os.path.join(d, f)).convert("RGB").resize((W, H))
    x, y = (i % cols) * W, (i // cols) * (H + 16)
    sheet.paste(im, (x, y + 16)); dr.text((x + 4, y + 2), f, fill=(255, 255, 0))
sheet.save(out); print(out, len(files))
