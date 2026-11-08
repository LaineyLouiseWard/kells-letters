"""Write settled readings of one page into adjudication.csv.

The decisions file has one line per settled line: "NN<tab>decision[<tab>unsure note]", `<none>` for a line with no
text. Only that page's rows change; the lines of the page still open are printed. --set kells_extra writes the extra
training pages' adjudication.csv (data/kells_extra/).
Usage: python scripts/key_settle.py [--set NAME] FOLIO decisions.tsv
"""
import argparse
import csv
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config" / "paths.yaml").read_text())
DATA = ROOT / CFG["data_dir"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="kells_key")
    ap.add_argument("folio")
    ap.add_argument("decisions", type=Path)
    a = ap.parse_args()
    settled = {}
    for row in a.decisions.read_text(encoding="utf-8").splitlines():
        if row.strip():
            parts = row.split("\t")
            settled[str(int(parts[0]))] = (parts[1], parts[2] if len(parts) > 2 else "")
    path = DATA / a.set / "adjudication.csv"
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    on_page = {r["n"] for r in rows if r["folio"] == a.folio}
    unknown = sorted(set(settled) - on_page, key=int)
    if unknown:
        raise SystemExit(f"{a.folio} has no lines {' '.join(unknown)} in {path}")
    for r in rows:
        if r["folio"] == a.folio and r["n"] in settled:
            r["decision"], r["unsure"] = settled[r["n"]]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    still = [r["n"] for r in rows if r["folio"] == a.folio and not r["decision"] and (r["claude"] or r["gpt"])]
    print(f"{a.folio}: {len(settled)} settled; still open: {' '.join(still) or 'none'}")


if __name__ == "__main__":
    main()
