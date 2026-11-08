"""Make the tables of notes/results.md again from the record in results/<run>/, so no number is typed by hand.

Each generated block in the notes sits between a marker naming what made it and an end marker:
    <!-- make tables: KIND | RUN ... -->
    ...
    <!-- end -->
KIND is one of:
- key | RUN: the St Gall model alone on the tune and the test pages, per zone (stgall_tune.csv, stgall_test.csv);
- key-pages | RUN: the same per page, as one line for the test pages and one for the tune pages;
- final | RUN [| BEFORE_RUN]: the test pages before Kells training (BEFORE_RUN's St Gall model, else RUN's) and
  fine-tuned (final_test.csv);
- final-pages | RUN: the fine-tuned model per test page;
- compare | LABEL: RUN | LABEL: RUN ...: runs side by side (St Gall test CER from stgall_test.txt, two-fold errors from
  passes_<setting>.csv, the setting from chosen.json).
Every rate is computed from the error and character totals, so a figure rounded twice cannot creep in. A block whose
score files were scored against different versions of the key (their key_md5 stamps) stops the script.
--write rewrites the blocks; otherwise the script lists every block that differs from the record and exits 1.
Usage: python scripts/tables.py notes/results.md [--write]
"""
import csv
import json
import re
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BLOCK = re.compile(r"(<!-- make tables: (.*?) -->\n)(.*?)(<!-- end -->)", re.S)
ZONES = "ABCD"
SETTING = {"plain": "without freezing", "freeze": "with freezing"}
WIDTH = 120  # the notes' line length


KEYS = set()  # key_md5 stamps of the score files read for the block being made


def scores(run, name):
    """scope:name -> row of a score file, with the totals as numbers."""
    rows = {}
    for r in csv.DictReader(open(ROOT / run / name)):
        rows[f"{r['scope']}:{r['name']}"] = {**r, **{k: int(r[k]) for k in ("err_sp", "n_sp", "err", "n")}}
        KEYS.add(r.get("key_md5") or "")
    return rows


def pct(err, n, places=1):
    return f"{100 * err / n:.{places}f}%"


def zone_row(label, rows):
    z = [pct(rows[f"zone:{x}"]["err_sp"], rows[f"zone:{x}"]["n_sp"]) for x in ZONES]
    a = rows["all:all"]
    return f"| {label} | {' | '.join(z)} | {pct(a['err_sp'], a['n_sp'])} | {pct(a['err'], a['n'])} | {a['n_sp']:,} |"


HEAD = ("| Pages | Zone A | Zone B | Zone C | Zone D | All | All, no sp | Characters |\n"
        "|---|---|---|---|---|---|---|---|")


def pages(rows):
    """'310v 20.2%, 328v 17.4% (A); ...': each page in file order, grouped by zone."""
    by_zone = {}
    for r in rows.values():
        if r["scope"] == "page":
            by_zone.setdefault(r["zone"], []).append(f"{r['name']} {pct(r['err_sp'], r['n_sp'])}")
    return "; ".join(f"{', '.join(v)} ({z})" for z, v in by_zone.items())


def stgall_cer(run):
    """St Gall's test pages: Kraken's report (ketos test) of errors and characters."""
    text = (ROOT / run / "stgall_test.txt").read_text()
    n = int(re.search(r"^(\d+)\tCharacters$", text, re.M).group(1))
    err = int(re.search(r"^(\d+)\tErrors$", text, re.M).group(1))
    return pct(err, n, 2)


def two_fold(run, setting):
    """The setting's two-fold error at the passes the run chose (chosen.json)."""
    mean = {int(r["pass"]): float(r["mean_err"]) for r in csv.DictReader(open(ROOT / run / f"passes_{setting}.csv"))}
    best = json.load(open(ROOT / run / "chosen.json"))["settings"][setting]["passes"]
    return f"{100 * mean[best]:.2f}% ({best} passes)"


def compare(runs):
    labels, paths = zip(*runs)
    def row(name, cells):
        return f"| {name} | {' | '.join(cells)} |"
    out = ["| | " + " | ".join(labels) + " |", "|---|" + "---|" * len(paths)]
    out.append(row("St Gall test pages, St Gall model", [stgall_cer(p) for p in paths]))
    for role in ("test", "tune"):
        cells = []
        for p in paths:
            a = scores(p, f"stgall_{role}.csv")["all:all"]
            cells.append(f"{pct(a['err_sp'], a['n_sp'])}" + (f" (no sp {pct(a['err'], a['n'])})" if role == "test"
                                                            else ""))
        out.append(row(f"Kells {role}, St Gall model only", cells))
    out.append(row("Two-fold error on the tune pages (Kraken's measure), without freezing",
                   [two_fold(p, "plain") for p in paths]))
    out.append(row("Two-fold error, with freezing", [two_fold(p, "freeze") for p in paths]))
    out.append(row("Setting used", [SETTING[json.load(open(ROOT / p / "chosen.json"))["setting"]] for p in paths]))
    finals = [scores(p, "final_test.csv") for p in paths]
    out.append(row("**Kells test, fine-tuned**", [f"**{pct(f['all:all']['err_sp'], f['all:all']['n_sp'], 2)}** "
                                                    f"(no sp {pct(f['all:all']['err'], f['all:all']['n'], 2)})"
                                                    for f in finals]))
    out.append(row("Zone A / B / C / D, fine-tuned", [" / ".join(pct(f[f"zone:{z}"]["err_sp"], f[f"zone:{z}"]["n_sp"])
                                                                 for z in ZONES) for f in finals]))
    return "\n".join(out)


def make(spec):
    KEYS.clear()
    made = build(spec)
    if len(KEYS) > 1:
        sys.exit(f"{spec}: scored against {len(KEYS)} versions of the key ({' '.join(sorted(KEYS))}); not comparable")
    return made


def build(spec):
    kind, *args = [s.strip() for s in spec.split("|")]
    if kind == "key":
        return "\n".join([HEAD, zone_row("tune (8)", scores(args[0], "stgall_tune.csv")),
                          zone_row("test (8)", scores(args[0], "stgall_test.csv"))])
    if kind == "key-pages":
        return textwrap.fill(f"Per page, test: {pages(scores(args[0], 'stgall_test.csv'))}. "
                             f"Tune: {pages(scores(args[0], 'stgall_tune.csv'))}.", WIDTH)
    if kind == "final":
        before = args[1] if len(args) > 1 else args[0]
        return "\n".join([HEAD, zone_row("test (8), before Kells training", scores(before, "stgall_test.csv")),
                          zone_row("test (8), fine-tuned", scores(args[0], "final_test.csv"))])
    if kind == "final-pages":
        return textwrap.fill(f"Per page, fine-tuned: {pages(scores(args[0], 'final_test.csv'))}.", WIDTH)
    if kind == "compare":
        return compare([tuple(s.strip() for s in a.split(":", 1)) for a in args])
    sys.exit(f"unknown table kind {kind!r}")


def main():
    path, write = Path(sys.argv[1]), "--write" in sys.argv
    text = path.read_text()
    stale = []

    def fill(m):
        made = make(m.group(2)) + "\n"
        if made != m.group(3):
            stale.append(m.group(2))
        return m.group(1) + made + m.group(4)
    new = BLOCK.sub(fill, text)
    blocks = len(BLOCK.findall(text))
    if write:
        path.write_text(new)
        print(f"{path}: {blocks} blocks made from results/, {len(stale)} changed")
    elif stale:
        sys.exit(f"{path}: {len(stale)} of {blocks} blocks differ from results/ (make tables WRITE=1):\n  "
                 + "\n  ".join(stale))
    else:
        print(f"{path}: all {blocks} blocks match results/")


if __name__ == "__main__":
    main()
