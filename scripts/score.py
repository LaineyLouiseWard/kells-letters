"""Character error rate of a reader's PageXML against the settled Kells answer key, per page and per zone.

CER = (substitutions + deletions + insertions) / reference characters, pooled over the lines of a page or a zone. The
reference is data/xml/kells_key/<folio>.xml (scripts/key_xml.py); lines are matched by Kraken's line id. Masks in
the reference: `?` matches any one character at no cost, `#` matches zero to two characters at no cost; neither
counts as a reference character, and both are reported. Punctuation counts. Two figures: with spaces (runs of spaces
made one, ends stripped) and without spaces. Lines with no reference text are not scored; the characters a reader
puts on them are reported.
--ref names the key folder to score against: a run's own copy (scripts/key_snapshot.py; its sample.csv gives the
roles) or, by default, data/xml/kells_key/ with data/kells_key/sample.csv.
Output: a table on screen and, with --out, one CSV row per page and zone, each stamped with what made it: the md5 of
the model that read the pages (PRED_DIR/read.json, from scripts/read_pages.py; empty for older readings), the md5 of
adjudication.csv as the key copy took it (else as it is now), and the commit of the code.
Usage: python scripts/score.py PRED_DIR [--ref KEY_DIR] [--role tune|test|all] [--folios 308r ...] [--out file.csv]
"""
import argparse
import csv
import json
import re
import sys
from pathlib import Path

import yaml
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config" / "paths.yaml").read_text())
DATA = ROOT / CFG["data_dir"]
REF = DATA / CFG["xml"] / "kells_key"
sys.path.insert(0, str(Path(__file__).resolve().parent))
from stamp import commit, md5  # noqa: E402


def distance(ref, hyp):
    """Edit distance from ref to hyp, with `?` in ref matching any one character and `#` zero to two, at no cost.
    A `?` with nothing against it costs one, as a missing letter does."""
    prev = list(range(len(hyp) + 1))
    for r in ref:
        cur = [0] * (len(hyp) + 1)
        if r == "#":
            for j in range(len(hyp) + 1):
                cur[j] = min(prev[j - k] for k in range(min(j, 2) + 1))
                if j:
                    cur[j] = min(cur[j], cur[j - 1] + 1)
        else:
            cur[0] = prev[0] + 1
            for j, h in enumerate(hyp, 1):
                cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (r != h and r != "?"))
        prev = cur
    return prev[-1]


def ref_chars(ref):
    return sum(1 for c in ref if c not in "?#")


def lines_of(path):
    """Line id -> text of the TextEquiv directly under each TextLine (empty if none)."""
    root = etree.parse(str(path)).getroot()
    out = {}
    for tl in root.iter("{*}TextLine"):
        u = tl.find("{*}TextEquiv/{*}Unicode")
        out[tl.get("id")] = (u.text or "") if u is not None else ""
    return out


def norm(s, spaces):
    s = re.sub(r"\s+", " ", s).strip()
    return s if spaces else s.replace(" ", "")


def score_page(ref, pred):
    """Totals for one page: errors and reference characters with and without spaces, masks, and stray characters."""
    t = {"lines": 0, "missing": 0, "err_sp": 0, "n_sp": 0, "err": 0, "n": 0, "q": 0, "hash": 0, "stray": 0}
    for lid, r in ref.items():
        h = pred.get(lid)
        if not r.strip():
            t["stray"] += len(norm(h or "", False))
            continue
        t["lines"] += 1
        if h is None:
            t["missing"] += 1
            h = ""
        for spaces, e, n in ((True, "err_sp", "n_sp"), (False, "err", "n")):
            a, b = norm(r, spaces), norm(h, spaces)
            t[e] += distance(a, b)
            t[n] += ref_chars(a)
        t["q"] += r.count("?")
        t["hash"] += r.count("#")
    return t


def add(a, b):
    return {k: a.get(k, 0) + b[k] for k in b}


def stamps(pred, ref):
    """What the scores were made with: the reading model's md5, the key's md5 and the code's commit."""
    read, key = Path(pred) / "read.json", Path(ref) / "key.json"
    model_md5 = json.load(open(read))["model_md5"] if read.exists() else ""
    key_md5 = (json.load(open(key))["adjudication_md5"] if key.exists()
               else md5(DATA / "kells_key" / "adjudication.csv"))
    return {"model_md5": model_md5, "key_md5": key_md5, "commit": commit()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pred")
    ap.add_argument("--ref", type=Path, default=REF)
    ap.add_argument("--role", default="all", choices=["tune", "test", "all"])
    ap.add_argument("--folios", nargs="*")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    roles = a.ref / "sample.csv" if (a.ref / "sample.csv").exists() else DATA / "kells_key" / "sample.csv"
    sample = [r for r in csv.DictReader(open(roles))
              if (a.role == "all" or r["role"] == a.role) and (not a.folios or r["folio"] in a.folios)]
    read = Path(a.pred) / "read.json"
    if read.exists():  # a reading made by read_pages.py holds every page it read: one missing is lost, not failed
        listed = set(json.load(open(read))["pages"])
        lost = [r["folio"] for r in sample
                if r["folio"] not in listed or not (Path(a.pred) / f"{r['folio']}.xml").exists()]
        if lost:
            sys.exit(f"{a.pred}: pages to score that its reading does not hold: {' '.join(lost)}")
    rows, zones, total = [], {}, {}
    for r in sample:
        pred_path = Path(a.pred) / f"{r['folio']}.xml"
        pred = lines_of(pred_path) if pred_path.exists() else {}
        t = score_page(lines_of(a.ref / f"{r['folio']}.xml"), pred)
        t["failed"] = int(not pred_path.exists())
        rows.append({"scope": "page", "name": r["folio"], "zone": r["zone"], "role": r["role"], **t})
        zones[r["zone"]] = add(zones.get(r["zone"], {}), t)
        total = add(total, t)
    rows += [{"scope": "zone", "name": z, "zone": z, "role": a.role, **t} for z, t in sorted(zones.items())]
    rows.append({"scope": "all", "name": "all", "zone": "", "role": a.role, **total})
    for row in rows:
        row["cer_spaces"] = round(row["err_sp"] / row["n_sp"], 4) if row["n_sp"] else ""
        row["cer"] = round(row["err"] / row["n"], 4) if row["n"] else ""
    print(f"{'scope':6} {'name':5} {'zone':4} {'CER':>7} {'no sp':>7} {'chars':>6} {'lines':>5} {'?':>3} {'#':>3} "
          f"{'stray':>5} {'missing':>7}")
    for row in rows:
        cs = f"{row['cer_spaces']:.2%}" if row["cer_spaces"] != "" else "-"
        c = f"{row['cer']:.2%}" if row["cer"] != "" else "-"
        print(f"{row['scope']:6} {row['name']:5} {row['zone']:4} {cs:>7} {c:>7} {row['n_sp']:>6} {row['lines']:>5} "
              f"{row['q']:>3} {row['hash']:>3} {row['stray']:>5} {row['missing']:>7}")
    if a.out:
        made = stamps(a.pred, a.ref)
        rows = [{**row, **made} for row in rows]
        a.out.parent.mkdir(parents=True, exist_ok=True)
        with open(a.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)


if __name__ == "__main__":
    main()
