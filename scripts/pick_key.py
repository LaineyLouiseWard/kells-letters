"""Draw the Kells answer-key pages: 4 per scribal zone (A, B, C, D), 2 to tune and 2 to test, before any model reads them.

Candidates: Gospel text pages (gospel_text = 1 in config/zones.csv) in zones A to D that are not boundary pages. Zone
blocks are runs of consecutive folios with the same zone. A boundary page is a page where a zone boundary falls (zone
"mixed": 125v, 243v), or the first or last page of a block, except next to a mixed page, since there the boundary is
fixed on the mixed page itself (so 126r, after 125v, is a candidate). The candidates are printed per zone.
Drawing: each zone's candidates are shuffled with SEED; the first two are tune pages, the next two test pages. The rest
of that order is kept as the reserve, used in order for any replacement or extra page drawn by the same rule.

Outputs: data/kells_key/sample.csv (folio, zone, role) and data/kells_key/draw_order.csv (folio, zone, rank).
Usage: python scripts/pick_key.py
"""
import csv
import random
from itertools import groupby
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config" / "paths.yaml").read_text())
DATA = ROOT / CFG["data_dir"]
ZONES = ["A", "B", "C", "D"]


def candidates(rows):
    """Folios of each zone that may be drawn, in manuscript order."""
    blocks = [list(g) for _, g in groupby(range(len(rows)), key=lambda i: rows[i]["zone"])]
    edge = set()
    for b in blocks:
        if b[0] == 0 or rows[b[0] - 1]["zone"] != "mixed":
            edge.add(b[0])
        if b[-1] == len(rows) - 1 or rows[b[-1] + 1]["zone"] != "mixed":
            edge.add(b[-1])
    return {z: [rows[i]["folio"] for i in range(len(rows))
                if rows[i]["zone"] == z and rows[i]["gospel_text"] == "1" and i not in edge] for z in ZONES}


def main():
    rows = list(csv.DictReader(open(ROOT / CFG["kells"]["zones"])))
    cand = candidates(rows)
    order, sample = [], []
    for z in ZONES:
        print(f"zone {z}: {len(cand[z])} candidates: {' '.join(cand[z])}")
        drawn = list(cand[z])
        random.Random(f"{CFG['SEED']}-{z}").shuffle(drawn)
        order += [{"folio": f, "zone": z, "rank": k + 1} for k, f in enumerate(drawn)]
        sample += [{"folio": f, "zone": z, "role": "tune" if k < 2 else "test"} for k, f in enumerate(drawn[:4])]
    out = DATA / "kells_key"
    out.mkdir(parents=True, exist_ok=True)
    for name, table in (("sample.csv", sample), ("draw_order.csv", order)):
        with open(out / name, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=table[0].keys())
            w.writeheader()
            w.writerows(table)
    for role in ("tune", "test"):
        print(f"{role}: " + " ".join(f"{r['folio']} ({r['zone']})" for r in sample if r["role"] == role))


if __name__ == "__main__":
    main()
