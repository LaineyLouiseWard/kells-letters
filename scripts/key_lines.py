"""Cut every Kraken line of the Kells answer-key pages out of the page images, numbered in reading order, for typing.

Pages: data/<set>/sample.csv (set kells_key, the answer key, unless --set names another, such as kells_extra for
extra training pages), segmented by scripts/segment_pages.py. Lines are in order of mean baseline height;
every line Kraken found is kept, including page numbers and decoration, so the typing decides what is text. Each line
is cut by the bounding box of its outline, PAD pixels taller above and below.
Outputs (never released; Kells images stay on this laptop):
- data/<set>/lines/<folio>/<NN>.png, and lines.csv (folio, n, kraken_id, x, y, width, height, baseline_length);
- data/xml/<set>/<folio>.xml: PageXML with the lines and no text yet;
- outputs/audit/<set>_<folio>_<k>.png: the lines numbered, LINES_PER_IMAGE to an image 1000 pixels wide, for viewing
  (key_<folio>_<k>.png for the answer key).
Usage: python scripts/key_lines.py [--set kells_extra]
"""
import csv
import json
import sys
from pathlib import Path

import yaml
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_xml  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config" / "paths.yaml").read_text())
DATA = ROOT / CFG["data_dir"]
FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 26)
PAD, WIDTH, LINES_PER_IMAGE = 12, 1000, 6


def main():
    name = sys.argv[sys.argv.index("--set") + 1] if "--set" in sys.argv else "kells_key"
    prefix = "key" if name == "kells_key" else name
    folios = [r["folio"] for r in csv.DictReader(open(DATA / name / "sample.csv"))]
    (DATA / CFG["xml"] / name).mkdir(parents=True, exist_ok=True)
    rows = []
    for folio in folios:
        seg = DATA / CFG["seg"] / "kells" / f"{folio}.json"
        if not seg.exists():
            sys.exit(f"{folio} is not segmented")
        lines = sorted(json.load(open(seg))["lines"], key=make_xml.height)
        image = DATA / CFG["kells"]["out"] / f"{folio}.jpg"
        im = Image.open(image).convert("L")
        make_xml.write_xml(DATA / CFG["xml"] / name / f"{folio}.xml", image, lines, {})
        out = DATA / name / "lines" / folio
        out.mkdir(parents=True, exist_ok=True)
        crops = []
        for n, line in enumerate(lines, 1):
            xs, ys = [p[0] for p in line["boundary"]], [p[1] for p in line["boundary"]]
            box = (max(0, min(xs)), max(0, min(ys) - PAD), min(im.size[0], max(xs)), min(im.size[1], max(ys) + PAD))
            crop = im.crop(box)
            crop.save(out / f"{n:02d}.png")
            crops.append((n, crop))
            rows.append({"folio": folio, "n": n, "kraken_id": line["id"], "x": box[0], "y": box[1],
                         "width": box[2] - box[0], "height": box[3] - box[1],
                         "baseline_length": round(make_xml.length(line))})
        sheets = ROOT / "outputs" / "audit"
        sheets.mkdir(parents=True, exist_ok=True)
        for k in range(0, len(crops), LINES_PER_IMAGE):
            part = []
            for n, crop in crops[k:k + LINES_PER_IMAGE]:
                scale = min(1, (WIDTH - 60) / crop.size[0])
                c = crop.resize((max(1, round(crop.size[0] * scale)), max(1, round(crop.size[1] * scale))))
                row = Image.new("L", (WIDTH, c.size[1] + 8), 255)
                row.paste(c, (60, 4))
                ImageDraw.Draw(row).text((4, 4), f"{n:02d}", font=FONT, fill=0)
                part.append(row)
            sheet = Image.new("L", (WIDTH, sum(r.size[1] + 4 for r in part)), 140)
            y = 0
            for r in part:
                sheet.paste(r, (0, y))
                y += r.size[1] + 4
            sheet.save(sheets / f"{prefix}_{folio}_{k // LINES_PER_IMAGE}.png")
        print(f"{folio}: {len(lines)} lines")
    with open(DATA / name / "lines.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)


if __name__ == "__main__":
    main()
