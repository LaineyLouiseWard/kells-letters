"""List every line where the two separate copies of the Kells answer key differ, for settling against the image.

Copies: data/kells_key/raw_claude/<folio>.txt and data/kells_key/raw_gpt/<folio>.txt, one line per Kraken line,
"NN<tab>text", numbered as in data/kells_key/lines.csv. Both raw copies stay untouched. Word gaps are compared too,
since the headline error rate counts spaces: a line whose copies differ only in gaps is unsettled like any other.
Output: data/kells_key/adjudication.csv (folio, n, claude, gpt, decision, unsure), one row per line, with decision
already filled where the copies agree letter for letter and gap for gap. Rows already settled in an earlier run are kept. A line
settled as having no text is written `<none>`.
With --set kells_extra, the same for the extra training pages in data/kells_extra/.
Usage: python scripts/key_diff.py [--set kells_extra]
"""
import csv
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config" / "paths.yaml").read_text())
KEY = ROOT / CFG["data_dir"] / "kells_key"


def copy(path):
    """Line number -> text of one raw copy."""
    out = {}
    for row in path.read_text(encoding="utf-8").splitlines():
        if row.strip():
            n, _, text = row.partition("\t")
            out[int(n)] = text.strip()
    return out


def main():
    global KEY
    if "--set" in sys.argv:
        KEY = KEY.with_name(sys.argv[sys.argv.index("--set") + 1])
    lines = list(csv.DictReader(open(KEY / "lines.csv")))
    out = KEY / "adjudication.csv"
    settled = {(r["folio"], r["n"]): r for r in csv.DictReader(open(out))} if out.exists() else {}
    rows, differ, gaps, missing = [], 0, 0, []
    for folio in dict.fromkeys(r["folio"] for r in lines):
        paths = [KEY / f"raw_{who}" / f"{folio}.txt" for who in ("claude", "gpt")]
        if not all(p.exists() for p in paths):
            missing.append(folio)
            continue
        claude, gpt = (copy(p) for p in paths)
        for r in (r for r in lines if r["folio"] == folio):
            n = int(r["n"])
            a, b = claude.get(n, ""), gpt.get(n, "")
            old = settled.get((folio, r["n"]), {})
            same = " ".join(a.split()) == " ".join(b.split())
            gap = not same and a.replace(" ", "") == b.replace(" ", "")
            differ += not same and not gap
            gaps += gap
            rows.append({"folio": folio, "n": n, "claude": a, "gpt": b,
                         "decision": old.get("decision") or (a if same else ""), "unsure": old.get("unsure", "")})
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["folio", "n", "claude", "gpt", "decision", "unsure"])
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} lines on {len({r['folio'] for r in rows})} pages; copies differ in letters on {differ}, "
          f"only in gaps on {gaps}; "
          f"unsettled {sum(1 for r in rows if not r['decision'] and (r['claude'] or r['gpt']))}")
    if missing:
        print("pages without both copies:", " ".join(missing))
        sys.exit(1)


if __name__ == "__main__":
    main()
