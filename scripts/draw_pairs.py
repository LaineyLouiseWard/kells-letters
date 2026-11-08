"""Draw the lines of PageXML pages with their text, for viewing a pairing by eye.

Each page is read with Kraken's own PageXML reader (so a drawing also shows that Kraken reads the file). Each line is
cut from the page image by the bounding box of its outline and shown with its text (or "[no text]") underneath, in
line order, LINES_PER_IMAGE lines to an image 1000 pixels wide.

Outputs: outputs/audit/<book>_<page>_<k>.png. Not for release; Kells drawings stay on this laptop.
Usage: python scripts/draw_pairs.py stgall 10 50 ...  |  python scripts/draw_pairs.py stgall --draw 5
"""
import argparse
import random
from pathlib import Path

import yaml
from kraken.lib.xml import XMLPage
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config" / "paths.yaml").read_text())
DATA = ROOT / CFG["data_dir"]
FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
WIDTH, LINES_PER_IMAGE, TEXT_H = 1000, 8, 34


def draw(book, page):
    xml = DATA / CFG["xml"] / book / f"{page}.xml"
    seg = XMLPage(xml).to_container()
    im = Image.open(seg.imagename).convert("L")
    rows = []
    for line in seg.lines:
        xs, ys = [p[0] for p in line.boundary], [p[1] for p in line.boundary]
        crop = im.crop((min(xs), min(ys), max(xs), max(ys)))
        crop = crop.resize((WIDTH, max(1, round(crop.size[1] * WIDTH / crop.size[0])))) if crop.size[0] > WIDTH else crop
        row = Image.new("L", (WIDTH, crop.size[1] + TEXT_H), 255)
        row.paste(crop, (0, 0))
        ImageDraw.Draw(row).text((4, crop.size[1] + 4), line.text or "[no text]", font=FONT, fill=0)
        rows.append(row)
    out = ROOT / "outputs" / "audit"
    out.mkdir(parents=True, exist_ok=True)
    for k in range(0, len(rows), LINES_PER_IMAGE):
        part = rows[k:k + LINES_PER_IMAGE]
        sheet = Image.new("L", (WIDTH, sum(r.size[1] + 6 for r in part)), 160)
        y = 0
        for r in part:
            sheet.paste(r, (0, y))
            y += r.size[1] + 6
        path = out / f"{book}_{page}_{k // LINES_PER_IMAGE}.png"
        sheet.save(path)
        print(path.relative_to(ROOT))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book")
    ap.add_argument("pages", nargs="*")
    ap.add_argument("--draw", type=int, help="draw this many kept pages at random with SEED instead")
    args = ap.parse_args()
    pages = args.pages
    if args.draw:
        kept = sorted(p.stem for p in (DATA / CFG["xml"] / args.book).glob("*.xml"))
        pages = random.Random(CFG["SEED"]).sample(kept, args.draw)
        print("drawn:", " ".join(pages))
    for page in pages:
        draw(args.book, page)


if __name__ == "__main__":
    main()
