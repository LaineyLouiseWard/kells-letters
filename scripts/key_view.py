"""Views of the answer key's line images, for typing and for settling by eye.

- zoom FOLIO N [N ...]: the named lines as halves, left over right, at full size (the image viewer shrinks anything
  over about 1,000 pixels; two lines make an image under 1,000 pixels high);
- crop FOLIO N X0 X1 SCALE: one stretch of one line, enlarged, for a hard letter;
- diff FOLIO: only the stretches where the two typed copies of an unsettled line differ, stacked and numbered, with
  the two readings printed (C Claude's copy, G GPT's), placed by their share of the line's letters.
Images go to OUT_DIR (default outputs/view/<folio>/). They are cut from Trinity's images and never released.
--set kells_extra views the extra training pages (data/kells_extra/).
Usage: python scripts/key_view.py [--set NAME] [--out OUT_DIR] zoom FOLIO N [N ...]
       python scripts/key_view.py [--set NAME] [--out OUT_DIR] crop FOLIO N X0 X1 SCALE
       python scripts/key_view.py [--set NAME] [--out OUT_DIR] diff FOLIO
"""
import argparse
import csv
from difflib import SequenceMatcher
from pathlib import Path

import yaml
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config" / "paths.yaml").read_text())
DATA = ROOT / CFG["data_dir"]
HALF, NEAR, HIGH = 210, 120, 950  # pixels either side of a difference; differences this close share a crop; sheet


def line(key, folio, n):
    return Image.open(key / "lines" / folio / f"{int(n):02d}.png").convert("RGB")


def zoom(key, folio, ns, out):
    parts = []
    for n in ns:
        im = line(key, folio, n)
        w, h = im.size
        parts += [(n, im)] if w <= 980 else [(n, im.crop((0, 0, min(w, w // 2 + 40), h))),
                                              (n, im.crop((max(0, w // 2 - 40), 0, w, h)))]
    canvas = Image.new("RGB", (max(p.size[0] for _, p in parts) + 40, sum(p.size[1] + 6 for _, p in parts)), "white")
    draw, y = ImageDraw.Draw(canvas), 0
    for n, p in parts:
        canvas.paste(p, (40, y))
        draw.text((2, y + 4), f"{int(n):02d}", fill="red")
        y += p.size[1] + 6
    path = out / f"zoom_{'_'.join(f'{int(n):02d}' for n in ns)}.png"
    canvas.save(path)
    print(path, canvas.size)


def crop(key, folio, n, x0, x1, scale, out):
    im = line(key, folio, n)
    im = im.crop((x0, 0, min(x1, im.size[0]), im.size[1]))
    im = im.resize((int(im.size[0] * scale), int(im.size[1] * scale)), Image.LANCZOS)
    path = out / f"crop_{int(n):02d}_{x0}_{x1}.png"
    im.save(path)
    print(path, im.size)


def diff(key, folio, out):
    crops = []
    for r in csv.DictReader(open(key / "adjudication.csv", encoding="utf-8")):
        if r["folio"] != folio or r["decision"] or not (r["claude"] or r["gpt"]):
            continue
        a, b = r["claude"], r["gpt"]
        im = line(key, folio, r["n"])
        spans = []
        for tag, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
            if tag == "equal":
                continue
            x = int((i1 + i2) / 2 / max(1, len(a)) * im.size[0])
            if spans and x - spans[-1][1] < NEAR:
                spans[-1][1] = x
                spans[-1][2].append((a[i1:i2], b[j1:j2]))
            else:
                spans.append([x, x, [(a[i1:i2], b[j1:j2])]])
        for x0, x1, diffs in spans:
            lo, hi = max(0, x0 - HALF), min(im.size[0], x1 + HALF)
            crops.append((r["n"], im.crop((lo, 0, hi, im.size[1])), diffs, lo))
    sheets, sheet, height = [], [], 0
    for c in crops:
        if sheet and height + c[1].size[1] + 8 > HIGH:
            sheets.append(sheet)
            sheet, height = [], 0
        sheet.append(c)
        height += c[1].size[1] + 8
    sheets += [sheet] if sheet else []
    k = 0
    for s, part in enumerate(sheets):
        canvas = Image.new("RGB", (max(c[1].size[0] for c in part) + 50, sum(c[1].size[1] + 8 for c in part)),
                           "white")
        draw, y = ImageDraw.Draw(canvas), 0
        for n, im, diffs, lo in part:
            k += 1
            canvas.paste(im, (50, y))
            draw.text((2, y + 4), f"{k}", fill="red")
            draw.text((2, y + 20), f"L{n}", fill="blue")
            print(f"{k}: line {n} (x {lo}): " + "; ".join(f"C'{c}' G'{g}'" for c, g in diffs))
            y += im.size[1] + 8
        path = out / f"diff_{s}.png"
        canvas.save(path)
        print(path, canvas.size)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="kells_key")
    ap.add_argument("--out", type=Path)
    ap.add_argument("view", choices=["zoom", "crop", "diff"])
    ap.add_argument("folio")
    ap.add_argument("args", nargs="*")
    a = ap.parse_args()
    key = DATA / a.set
    out = a.out or ROOT / "outputs" / "view" / a.folio
    out.mkdir(parents=True, exist_ok=True)
    if a.view == "zoom":
        zoom(key, a.folio, a.args, out)
    elif a.view == "crop":
        n, x0, x1, scale = a.args
        crop(key, a.folio, n, int(x0), int(x1), float(scale), out)
    else:
        diff(key, a.folio, out)


if __name__ == "__main__":
    main()
