"""Pair Kraken's lines on each St Gall page with the page's typed lines, and write one PageXML per kept page.

1. Reading order: Kraken's lines (scripts/segment_pages.py) sorted by mean baseline height.
2. Short lines: a Kraken line whose baseline is shorter than SHORT x the page's median baseline length (interlinear and
   marginal additions), and a typed line with fewer than SHORT x the page's median number of characters (the two- to
   five-letter word ends that close many pages of John), are left out of the pairing.
3. Pairing: the remaining lines are paired in order, before any train flag is applied. A page whose totals differ is
   dropped, as is a page written in two columns (Luke's genealogy), whose lines cannot be ordered by height alone.
   Spacing test: the page is also dropped when a gap between consecutive paired lines falls outside SPACING_BAND x the
   page's median gap. St Gall's lines are ruled evenly, so a missed line beside an extra one, which leaves the totals
   equal but shifts every label in between, shows as a double and a half gap. The width test cannot see such a shift,
   since the lines are all about the same length.
4. Width test, as in voynich-letters' make_lines.py but on baseline length: a line's baseline length divided by the
   characters of its label (spaces not counted), against the page median over lines with at least WIDTH_MIN_CHARS
   characters. A line outside WIDTH_BAND is dropped; a page is dropped whole when more than PAGE_FAIL of its lines
   with at least WIDTH_MIN_CHARS characters fall outside.
Baseline length is the baseline's horizontal extent; thresholds are in config/paths.yaml.

Outputs, in data/xml/stgall/:
- <page>.xml for each kept page: PageXML (2019 schema) with every Kraken line of the page (outline and baseline). A
  paired line with train=1 that passes the width test carries its label as text; every other line has no text, so no
  reader trains on it. imageFilename is relative to the XML file.
- pairs.csv: one row per paired line of a kept page (page, line, kraken_id, label, train, width_ratio, text).
- dropped.csv: every page or line left out (page, line, side, scope, reason).
Usage: python scripts/make_xml.py [--pages 10 50 ...]
"""
import argparse
import csv
import datetime
import json
import os
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import yaml
from lxml import etree
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config" / "paths.yaml").read_text())
DATA = ROOT / CFG["data_dir"]
PAGE = "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"
XSI = "http://www.w3.org/2001/XMLSchema-instance"


def length(line):
    xs = [p[0] for p in line["baseline"]]
    return max(xs) - min(xs)


def height(line):
    return float(np.mean([p[1] for p in line["baseline"]]))


def chars(label):
    return len(label.replace(" ", ""))


def points(pts):
    return " ".join(f"{int(round(x))},{int(round(y))}" for x, y in pts)


def write_xml(path, image, lines, text):
    """PageXML of all lines (Kraken's line dicts, in reading order); text maps a line id to its label."""
    def sub(parent, tag, **attrib):
        return etree.SubElement(parent, f"{{{PAGE}}}{tag}", **attrib)
    width, height_ = Image.open(image).size
    root = etree.Element(f"{{{PAGE}}}PcGts", nsmap={None: PAGE, "xsi": XSI})
    root.set(f"{{{XSI}}}schemaLocation", f"{PAGE} {PAGE}/pagecontent.xsd")
    meta = sub(root, "Metadata")
    now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
    for tag, value in (("Creator", "kells-letters scripts/make_xml.py"), ("Created", now), ("LastChange", now)):
        sub(meta, tag).text = value
    page = sub(root, "Page", imageFilename=os.path.relpath(image, path.parent), imageWidth=str(width),
               imageHeight=str(height_))
    region = sub(page, "TextRegion", id=f"r_{path.stem}")
    sub(region, "Coords", points=f"0,0 0,{height_} {width},{height_} {width},0")
    for line in lines:
        tl = sub(region, "TextLine", id=line["id"])
        sub(tl, "Coords", points=points(line["boundary"]))
        sub(tl, "Baseline", points=points(line["baseline"]))
        if line["id"] in text:
            sub(sub(tl, "TextEquiv"), "Unicode").text = text[line["id"]]
    path.write_bytes(etree.tostring(root, xml_declaration=True, encoding="UTF-8", pretty_print=True))


def pair_page(page, segs, typed):
    """(pairs, dropped) for one page: pairs are (Kraken line, typed row, width ratio or None); dropped are rows of
    dropped.csv. An empty pairs list means the page is dropped."""
    drop = []
    lines = sorted(segs, key=height)
    if any(r["column"] != "1" for r in typed):
        return [], [{"page": page, "line": "", "side": "", "scope": "page", "reason": "two columns"}]
    med_len = np.median([length(s) for s in lines])
    med_chars = np.median([chars(r["label"]) for r in typed])
    kraken = [s for s in lines if length(s) >= CFG["SHORT"] * med_len]
    text = [r for r in typed if chars(r["label"]) >= CFG["SHORT"] * med_chars]
    drop += [{"page": page, "line": s["id"], "side": "kraken", "scope": "line", "reason": "short line"}
             for s in lines if s not in kraken]
    drop += [{"page": page, "line": r["line"], "side": "text", "scope": "line", "reason": "short line"}
             for r in typed if r not in text]
    if len(kraken) != len(text):
        return [], drop + [{"page": page, "line": "", "side": "", "scope": "page",
                            "reason": f"line totals differ (Kraken {len(kraken)}, text {len(text)})"}]
    gaps = np.diff([height(s) for s in kraken])
    lo, hi = CFG["SPACING_BAND"]
    if len(gaps) and not np.all((gaps >= lo * np.median(gaps)) & (gaps <= hi * np.median(gaps))):
        return [], drop + [{"page": page, "line": "", "side": "", "scope": "page", "reason": "uneven line spacing"}]
    per = np.array([length(s) / chars(r["label"]) for s, r in zip(kraken, text)])
    counted = np.array([chars(r["label"]) >= CFG["WIDTH_MIN_CHARS"] for r in text])
    ratio = per / np.median(per[counted])
    lo, hi = CFG["WIDTH_BAND"]
    inside = (ratio >= lo) & (ratio <= hi)
    if np.mean(~inside[counted]) > CFG["PAGE_FAIL"]:
        return [], drop + [{"page": page, "line": "", "side": "", "scope": "page",
                            "reason": f"fails width test ({np.mean(~inside[counted]):.0%} of lines)"}]
    drop += [{"page": page, "line": r["line"], "side": "text", "scope": "line", "reason": "fails width test"}
             for r, ok in zip(text, inside) if not ok]
    return [(s, r, float(q)) for s, r, q in zip(kraken, text, ratio)], drop


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pages", nargs="*")
    args = ap.parse_args()
    typed = defaultdict(list)
    for r in csv.DictReader(open(DATA / CFG["stgall"]["text"])):
        if r["label"]:
            typed[r["page"]].append(r)
    image = {r["page"]: DATA / CFG["stgall"]["out"] / r["image"]
             for r in csv.DictReader(open(DATA / CFG["manifests"] / "stgall51.csv"))}
    seg = DATA / CFG["seg"] / "stgall"
    out = DATA / CFG["xml"] / "stgall"
    out.mkdir(parents=True, exist_ok=True)
    pages = sorted((p for p in typed if (seg / f"{p}.json").exists() and (not args.pages or p in args.pages)), key=int)
    rows, dropped = [], []
    for page in pages:
        segs = json.load(open(seg / f"{page}.json"))["lines"]
        pairs, drop = pair_page(page, segs, typed[page])
        dropped += drop
        (out / f"{page}.xml").unlink(missing_ok=True)
        if not pairs:
            continue
        lo, hi = CFG["WIDTH_BAND"]
        text = {s["id"]: r["label"] for s, r, q in pairs if r["train"] == "1" and lo <= q <= hi}
        write_xml(out / f"{page}.xml", image[page], sorted(segs, key=height), text)
        rows += [{"page": page, "line": r["line"], "kraken_id": s["id"], "label": r["label"], "train": r["train"],
                  "width_ratio": round(q, 3), "text": int(s["id"] in text)} for s, r, q in pairs]
    for name, table, fields in (("pairs.csv", rows, ["page", "line", "kraken_id", "label", "train", "width_ratio",
                                                     "text"]),
                                ("dropped.csv", dropped, ["page", "line", "side", "scope", "reason"])):
        with open(out / name, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            w.writerows(table)
    kept = {r["page"] for r in rows}
    print(f"{len(pages)} segmented pages: {len(kept)} kept, {len(pages) - len(kept)} dropped; "
          f"{len(rows)} paired lines, {sum(r['text'] for r in rows)} with text for training")
    for why, n in Counter(d["reason"] if d["scope"] == "line" else "page " + d["reason"].split(" (")[0]
                          for d in dropped).most_common():
        print(f"  {why}: {n}")


if __name__ == "__main__":
    main()
