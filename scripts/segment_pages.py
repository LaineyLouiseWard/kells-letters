"""Find the text lines on each page with Kraken's default baseline segmenter (blla.mlmodel, pinned by its checksum).

Books: stgall (the St Gall 51 pages whose TEI has text) and kells (the Gospel text pages whose image opens), both from
the manifests. A page already segmented is skipped. Most of Kraken's time goes on tracing line outlines on the CPU, so
WORKERS Kraken processes run side by side, each loading the model once for its share of pages. Kraken reports success
even when a page fails, so pages without output are retried one at a time and any still missing are listed.
Adapted from voynich-letters' scripts/segment_pages.py (commit 3820bee).

Outputs: data/seg/<book>/<page>.json (Kraken's baselines and line outlines in page-image pixels).
Usage: python scripts/segment_pages.py stgall|kells [--pages 4 5 ...] [--workers N] [--device cpu]
"""
import argparse
import csv
import hashlib
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import kraken
import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config" / "paths.yaml").read_text())
DATA = ROOT / CFG["data_dir"]
KRAKEN = Path(sys.executable).parent / "kraken"


def images(book):
    """Page name -> image path, for the pages of the book that are segmented."""
    rows = csv.DictReader(open(DATA / CFG["manifests"] / f"{'stgall51' if book == 'stgall' else 'kells'}.csv"))
    if book == "stgall":
        return {r["page"]: DATA / CFG["stgall"]["out"] / r["image"] for r in rows if r["tei_text"] == "yes"}
    return {r["folio"]: DATA / CFG["kells"]["out"] / f"{r['folio']}.jpg" for r in rows
            if r["gospel_text"] == "1" and r["file_opens"] == "yes"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("book", choices=["stgall", "kells"])
    ap.add_argument("--pages", nargs="*")
    ap.add_argument("--workers", type=int, default=CFG["kraken"]["workers"])
    ap.add_argument("--device", default="cuda:0", help="cpu when the GPU is busy")
    args = ap.parse_args()
    model = Path(kraken.__file__).parent / CFG["kraken"]["model"]
    if hashlib.sha256(model.read_bytes()).hexdigest() != CFG["kraken"]["sha256"]:
        sys.exit(f"{model} does not match the pinned checksum")
    image_of = images(args.book)
    if args.pages:
        unknown = set(args.pages) - set(image_of)
        if unknown:
            sys.exit(f"not pages of {args.book} to segment: {sorted(unknown)}")
        image_of = {p: image_of[p] for p in args.pages}
    out = DATA / CFG["seg"] / args.book
    out.mkdir(parents=True, exist_ok=True)
    todo = [p for p in image_of if not (out / f"{p}.json").exists()]

    def run(pages):
        if pages:
            pairs = [a for p in pages for a in ("-i", str(image_of[p]), str(out / f"{p}.json"))]
            subprocess.run([str(KRAKEN), "-d", args.device, *pairs, "segment", "-bl", "-i", str(model)],
                           check=True, capture_output=True)

    with ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(run, [todo[k::args.workers] for k in range(args.workers)]))
    for p in [p for p in todo if not (out / f"{p}.json").exists()]:
        run([p])
    missing = [p for p in todo if not (out / f"{p}.json").exists()]
    print(f"{len(todo) - len(missing)} of {len(todo)} pages segmented" + (f"; failed: {missing}" if missing else ""))
    if missing:
        sys.exit(1)


if __name__ == "__main__":
    main()
