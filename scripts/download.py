"""Download the Book of Kells and St Gall 51 page images and the Insular Gospels TEI files.

Kells: every folio listed on Trinity Digital Collections, with a manifest (folio, title, download id); the listing is
reused once saved. St Gall 51: every canvas of the e-codices IIIF manifest at full size.
A file is skipped when it is already there and opens as an image; a missing or broken file is fetched again, written
to a .part file and renamed only when complete, so the script can be stopped and rerun at any point.
At the end every Kells manifest row is opened and the result written to data/raw/kells/download_status.txt.
"""
import csv
import io
import json
import re
import time
import urllib.request
import zipfile
from pathlib import Path

import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config" / "paths.yaml").read_text())
DATA = ROOT / CFG["data_dir"]
HEADERS = {"User-Agent": "kells-letters research download (academic use)"}


def get(url):
    """Fetch a URL; on failure wait longer each time (Trinity's server answers 503 when asked too fast)."""
    req = urllib.request.Request(url, headers=HEADERS)
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return r.read()
        except Exception:
            if attempt == 5:
                raise
            time.sleep(60 * (attempt + 1))


def opens(path):
    try:
        with Image.open(path) as im:
            im.load()
        return True
    except Exception:
        return False


def fetch(url, path):
    """Download to path unless a complete image is already there."""
    if path.exists() and opens(path):
        return False
    part = path.with_suffix(path.suffix + ".part")
    part.write_bytes(get(url))
    part.rename(path)
    time.sleep(CFG["delay_seconds"])
    return True


def kells():
    out = DATA / CFG["kells"]["out"]
    out.mkdir(parents=True, exist_ok=True)
    listing = out / "manifest.csv"
    if listing.exists():
        rows = [(r["folio"], r["title"], r["download_id"]) for r in csv.DictReader(open(listing))]
    else:
        row = re.compile(
            r'<img src="/downloads/(\w+)\?file=thumbnail".*?folios/\w+">([^<]+)</a></td>\s*'
            r'<td class="attribute attribute-identifier">IE TCD MS 58, folio (\w+)</td>', re.S)
        rows, page = [], 1
        while True:
            html = get(f"{CFG['kells']['work_url']}?locale=en&page={page}").decode("utf-8", "ignore")
            found = row.findall(html)
            if not found:
                break
            rows += [(folio, title.strip(), dl) for dl, title, folio in found]
            page += 1
            time.sleep(CFG["delay_seconds"])
        with open(listing, "w", newline="") as f:
            csv.writer(f).writerows([("folio", "title", "download_id"), *rows])
    for folio, _, dl in rows:
        fetch(f"{CFG['kells']['download_url']}/{dl}", out / f"{folio}.jpg")
    bad = [folio for folio, _, _ in rows if not opens(out / f"{folio}.jpg")]
    status = f"{len(rows) - len(bad)} of {len(rows)} Kells pages present and open"
    (out / "download_status.txt").write_text(
        status + (f"\nmissing or broken: {' '.join(bad)}\n" if bad else "\nall complete\n"))
    print(status)


def stgall():
    out = DATA / CFG["stgall"]["out"]
    out.mkdir(parents=True, exist_ok=True)
    saved = out / "manifest.json"
    manifest = json.loads(saved.read_text()) if saved.exists() else json.loads(get(CFG["stgall"]["manifest_url"]))
    saved.write_text(json.dumps(manifest))
    canvases = manifest["sequences"][0]["canvases"]
    for c in canvases:
        service = c["images"][0]["resource"]["service"]["@id"]
        fetch(f"{service}/full/full/0/default.jpg", out / f"{service.rsplit('/', 1)[-1].replace('.jp2', '')}.jpg")
    print(f"St Gall 51: {len(canvases)} images")


def tei():
    out = DATA / CFG["stgall"]["tei_out"]
    out.mkdir(parents=True, exist_ok=True)
    if not list(out.rglob("*.xml")):
        zipfile.ZipFile(io.BytesIO(get(CFG["stgall"]["tei_url"]))).extractall(out)
    print(f"TEI: {len(list(out.rglob('*.xml')))} files")


if __name__ == "__main__":
    tei()
    stgall()
    kells()
