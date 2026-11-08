"""Write the two page manifests, one row per page: the single source of every count in a report.

Each run reads whatever later steps have produced so far (Kraken's lines, the PageXML pairing and split, the answer-key
sample), so it is rerun after each step.
- data/manifests/stgall51.csv: page, image, tei_text (the TEI has text on the page), segmented, lines_kept (paired
  lines with text in the page's PageXML), split, reason.
- data/manifests/kells.csv: folio, title, download_id, file_opens, width, zone, gospel_text, segmented, lines_found,
  display_page, key_role, reason.
A file opens when it is a whole JPEG (it ends with the JPEG end marker) of the expected height (every Kells image is
3150 pixels high; their widths vary with the page). Download gate: every Kells and St Gall image opens; otherwise the
manifests are still written and the script exits with an error listing the files that do not open.

Usage: python scripts/manifests.py
"""
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config" / "paths.yaml").read_text())
DATA = ROOT / CFG["data_dir"]


def opens(path, height):
    """Image width if the file is a whole JPEG of the given height, else None."""
    try:
        with Image.open(path) as im:
            ok, width = im.format == "JPEG" and im.size[1] == height, im.size[0]
        with open(path, "rb") as f:
            f.seek(-2, 2)
            return width if ok and f.read() == b"\xff\xd9" else None
    except (OSError, ValueError):
        return None


def table(path):
    return list(csv.DictReader(open(path))) if path.exists() else []


def lines_of(book):
    """Kraken lines found per page, from data/seg/<book>/<page>.json."""
    seg = DATA / CFG["seg"] / book
    return {p.stem: len(json.load(open(p))["lines"]) for p in seg.glob("*.json")} if seg.exists() else {}


def write(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)


def stgall():
    raw = DATA / CFG["stgall"]["out"]
    canvases = json.load(open(raw / "manifest.json"))["sequences"][0]["canvases"]
    text = {r["page"] for r in table(DATA / CFG["stgall"]["text"]) if r["label"]}
    segs = lines_of("stgall")
    pairs = DATA / CFG["xml"] / "stgall"
    kept = Counter(r["page"] for r in table(pairs / "pairs.csv") if r["text"] == "1")
    split = {r["page"]: r["split"] for r in table(pairs / "split.csv")}
    page_drop = {r["page"]: r["reason"] for r in table(pairs / "dropped.csv") if r["scope"] == "page"}
    rows, broken = [], []
    for c in canvases:
        image = c["images"][0]["resource"]["service"]["@id"].rsplit("/", 1)[-1].replace(".jp2", ".jpg")
        number = image.removeprefix("csg-0051_").removesuffix(".jpg")
        page = str(int(number)) if number.isdigit() else number
        ok = opens(raw / image, int(c["height"])) is not None
        if not ok:
            broken.append(image)
        reason = ("image does not open" if not ok else "no TEI text" if page not in text
                  else "not segmented" if page not in segs else page_drop.get(page, ""))
        rows.append({"page": page, "image": image, "tei_text": "yes" if page in text else "no",
                     "segmented": "yes" if page in segs else "no",
                     "lines_kept": kept.get(page, 0) if (pairs / "pairs.csv").exists() else "",
                     "split": split.get(page, ""), "reason": reason})
    write(DATA / CFG["manifests"] / "stgall51.csv", rows)
    print(f"St Gall 51: {len(rows)} images, {sum(r['tei_text'] == 'yes' for r in rows)} with TEI text, "
          f"{len(segs)} segmented")
    return broken


def kells():
    raw = DATA / CFG["kells"]["out"]
    zones = {r["folio"]: r for r in table(ROOT / CFG["kells"]["zones"])}
    listed = table(raw / "manifest.csv")
    if set(zones) != {r["folio"] for r in listed}:
        sys.exit("config/zones.csv and the Kells listing name different folios")
    segs = lines_of("kells")
    display = {r["folio"]: r["display_page"] for r in table(DATA / CFG["xml"] / "kells" / "pages.csv")}
    role = {r["folio"]: r["role"] for r in table(DATA / "kells_key" / "sample.csv")}
    rows, broken = [], []
    for r in listed:
        folio = r["folio"]
        width = opens(raw / f"{folio}.jpg", CFG["kells"]["height"])
        if width is None:
            broken.append(folio)
        z = zones[folio]
        reason = ("file does not open" if width is None else "not Gospel text" if z["gospel_text"] != "1"
                  else "not segmented" if folio not in segs else "display page" if display.get(folio) == "yes" else "")
        rows.append({"folio": folio, "title": r["title"], "download_id": r["download_id"],
                     "file_opens": "no" if width is None else "yes", "width": width or "", "zone": z["zone"],
                     "gospel_text": z["gospel_text"], "segmented": "yes" if folio in segs else "no",
                     "lines_found": segs.get(folio, ""), "display_page": display.get(folio, ""),
                     "key_role": role.get(folio, ""), "reason": reason})
    write(DATA / CFG["manifests"] / "kells.csv", rows)
    per_zone = defaultdict(int)
    for r in rows:
        per_zone[r["zone"]] += r["gospel_text"] == "1"
    print(f"Kells: {len(rows)} folios, {len(rows) - len(broken)} open; Gospel text pages by zone: "
          + ", ".join(f"{z} {n}" for z, n in sorted(per_zone.items(), key=lambda x: -x[1])))
    return broken


def main():
    broken = stgall() + kells()
    if broken:
        sys.exit(f"Download gate failed: {len(broken)} files missing or broken: {' '.join(broken[:40])}"
                 + (" ..." if len(broken) > 40 else ""))
    print("Download gate passed: every image opens.")


if __name__ == "__main__":
    main()
