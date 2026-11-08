"""Place every letter of a page's text on the page image: Kraken's forced alignment of each line's text with the output
of a Kraken recognition model (kraken.tasks.ForcedAlignmentTaskModel), whichever reader produced the text.

Input: PageXML pages whose lines carry text (a reader's output or a typed page) and a Kraken recognition model.
Outputs, in the output folder:
- <page>.xml: the page with one Glyph per letter (its outline and confidence), written by Kraken's PageXML serializer;
- letters.csv: page, line (the line's id), index, char, confidence, and the letter's box x, y, width, height in page
  pixels (the bounding box of its outline). Spaces are not letters and get no row.
A line Kraken cannot align (its output is shorter than twice the text) gets no letters; it is printed.
--draw also writes outputs/audit/<page>_letters_<k>.png: each line with its letter boxes and the text under it.
Usage: python scripts/align.py -m model.safetensors -o outdir [--draw] page.xml ...
"""
import argparse
import csv
from pathlib import Path

from kraken.configs import RecognitionInferenceConfig
from kraken.lib.xml import XMLPage
from kraken.serialization import serialize
from kraken.tasks import ForcedAlignmentTaskModel
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
FONT = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
WIDTH, LINES_PER_IMAGE = 1000, 8


def box(cut):
    xs, ys = [p[0] for p in cut], [p[1] for p in cut]
    return min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys)


def draw(page, im, lines, letters):
    """Line crops with their letter boxes, LINES_PER_IMAGE to an image WIDTH pixels wide."""
    rows = []
    for line in lines:
        xs, ys = [p[0] for p in line.boundary], [p[1] for p in line.boundary]
        x0, y0 = min(xs), min(ys)
        crop = im.crop((x0, y0, max(xs), max(ys))).convert("RGB")
        d = ImageDraw.Draw(crop)
        for r in letters:
            if r["line"] == line.id:
                d.rectangle((r["x"] - x0, r["y"] - y0, r["x"] - x0 + r["width"], r["y"] - y0 + r["height"]),
                            outline=(220, 0, 0), width=2)
        scale = min(1, WIDTH / crop.size[0])
        crop = crop.resize((round(crop.size[0] * scale), max(1, round(crop.size[1] * scale))))
        row = Image.new("RGB", (WIDTH, crop.size[1] + 34), "white")
        row.paste(crop, (0, 0))
        ImageDraw.Draw(row).text((4, crop.size[1] + 4), line.prediction or "[not aligned]", font=FONT, fill="black")
        rows.append(row)
    out = ROOT / "outputs" / "audit"
    out.mkdir(parents=True, exist_ok=True)
    for k in range(0, len(rows), LINES_PER_IMAGE):
        part = rows[k:k + LINES_PER_IMAGE]
        sheet = Image.new("RGB", (WIDTH, sum(r.size[1] + 6 for r in part)), (160, 160, 160))
        y = 0
        for r in part:
            sheet.paste(r, (0, y))
            y += r.size[1] + 6
        sheet.save(out / f"{page}_letters_{k // LINES_PER_IMAGE}.png")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-m", "--model", required=True)
    ap.add_argument("-o", "--out", type=Path, required=True)
    ap.add_argument("--draw", action="store_true")
    ap.add_argument("pages", nargs="+", type=Path)
    args = ap.parse_args()
    model = ForcedAlignmentTaskModel.load_model(args.model)
    recognize = model.net.predict

    def log_probabilities(*a, **kw):
        # Kraken 7.1.1's recognizer puts softmax probabilities in record.logits and its alignment applies log_softmax
        # to them again, which flattens every frame to about 1/34 (all letters squeezed into the line's start, every
        # confidence 0.028). Log probabilities pass through log_softmax unchanged.
        for rec in recognize(*a, **kw):
            rec.logits = rec.logits.clamp_min(1e-12).log()
            yield rec

    model.net.predict = log_probabilities
    args.out.mkdir(parents=True, exist_ok=True)
    letters = []
    for xml in args.pages:
        seg = XMLPage(xml).to_container()
        keep = [i for i, ln in enumerate(seg.lines) if ln.text]
        new = {old: k for k, old in enumerate(keep)}
        seg.line_orders = [[new[i] for i in order if i in new] for order in seg.line_orders]
        seg.lines = [seg.lines[i] for i in keep]
        im = Image.open(seg.imagename)
        aligned = model.predict(im, seg, RecognitionInferenceConfig())
        page = []
        for rec in aligned.lines:
            # Kraken 7.1.1's alignment stores a line's text as a list of letters, which its own PageXML writer
            # cannot take; the letters are joined into the string the record is documented to hold.
            if isinstance(rec._prediction, list):
                rec._prediction = "".join(rec._prediction)
            if not rec.prediction:
                print(f"{xml.stem}: line {rec.id} not aligned")
            for i, (char, cut, conf) in enumerate(zip(rec.prediction, rec.cuts, rec.confidences)):
                if char != " ":
                    x, y, w, h = box(cut)
                    page.append({"page": xml.stem, "line": rec.id, "index": i, "char": char,
                                 "confidence": round(float(conf), 4), "x": x, "y": y, "width": w, "height": h})
        (args.out / xml.name).write_text(serialize(aligned, image_size=im.size, template="pagexml"))
        if args.draw:
            draw(xml.stem, im, aligned.lines, page)
        letters += page
    with open(args.out / "letters.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["page", "line", "index", "char", "confidence", "x", "y", "width", "height"])
        w.writeheader()
        w.writerows(letters)
    print(f"{len(letters)} letters placed on {len(args.pages)} pages")


if __name__ == "__main__":
    main()
