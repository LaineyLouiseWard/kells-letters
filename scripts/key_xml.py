"""Write the settled Kells answer key into PageXML on Kraken's lines, and the lists for reading and fine-tuning.

Input: data/kells_key/adjudication.csv (scripts/key_diff.py, settled by hand), lines.csv and sample.csv, and Kraken's
lines in data/seg/kells/<folio>.json. Every line with text in either copy must have a decision; `<none>` is a line
with no text. The script stops if any page of sample.csv is missing or unsettled.
Outputs, in data/xml/kells_key/:
- <folio>.xml: every line, the settled text on each line that has one. The reference for scoring, and the input
  that readers read (Kraken reads its lines from it).
- train/<folio>.xml (tune pages only): as above, but a line holding `?` carries no text, so no reader trains on it,
  and `#` is left out of the text, so a decorated initial is learned as no letter, as scoring treats it.
- tune.lst and test.lst: the reference files of each role; fold1.lst and fold2.lst: train/ files of the first and
  second tune page of each zone, in sample.csv order; tune_train.lst: all 8 train/ files.
With --set kells_extra: the extra training pages (role extra in data/kells_extra/sample.csv), each written as a
reference file and a train/ file as a tune page is, into data/xml/kells_extra/, with extra.lst and extra_train.lst.
Usage: python scripts/key_xml.py [--set kells_extra]
"""
import csv
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_xml  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config" / "paths.yaml").read_text())
DATA = ROOT / CFG["data_dir"]
KEY = DATA / "kells_key"
OUT = DATA / CFG["xml"] / "kells_key"


def settled():
    """folio -> {line number: settled text}; stops on any unsettled line."""
    out, open_ = {}, []
    for r in csv.DictReader(open(KEY / "adjudication.csv")):
        d = r["decision"]
        if not d and (r["claude"] or r["gpt"]):
            open_.append(f"{r['folio']}:{r['n']}")
        out.setdefault(r["folio"], {})[int(r["n"])] = "" if d == "<none>" else d
    if open_:
        sys.exit(f"{len(open_)} lines unsettled: {' '.join(open_)}")
    return out


def main():
    global KEY, OUT
    if "--set" in sys.argv:
        name = sys.argv[sys.argv.index("--set") + 1]
        KEY, OUT = KEY.with_name(name), OUT.with_name(name)
    sample = list(csv.DictReader(open(KEY / "sample.csv")))
    text = settled()
    missing = [r["folio"] for r in sample if r["folio"] not in text]
    if missing:
        sys.exit(f"pages not in adjudication.csv: {' '.join(missing)}")
    ids = {(r["folio"], int(r["n"])): r["kraken_id"] for r in csv.DictReader(open(KEY / "lines.csv"))}
    (OUT / "train").mkdir(parents=True, exist_ok=True)
    lists = ({"extra": [], "extra_train": []} if all(r["role"] == "extra" for r in sample)
             else {"tune": [], "test": [], "fold1": [], "fold2": [], "tune_train": []})
    seen = {}
    for r in sample:
        folio = r["folio"]
        lines = sorted(json.load(open(DATA / CFG["seg"] / "kells" / f"{folio}.json"))["lines"], key=make_xml.height)
        if [ln["id"] for ln in lines] != [ids[(folio, n)] for n in range(1, len(lines) + 1)]:
            sys.exit(f"{folio}: Kraken's lines no longer match lines.csv")
        labels = {ids[(folio, n)]: t for n, t in text[folio].items() if t}
        image = DATA / CFG["kells"]["out"] / f"{folio}.jpg"
        make_xml.write_xml(OUT / f"{folio}.xml", image, lines, labels)
        lists[r["role"]].append(OUT / f"{folio}.xml")
        if r["role"] in ("tune", "extra"):
            train = {k: " ".join(t.replace("#", " ").split()) for k, t in labels.items() if "?" not in t}
            train = {k: t for k, t in train.items() if t}
            make_xml.write_xml(OUT / "train" / f"{folio}.xml", image, lines, train)
            if r["role"] == "extra":
                lists["extra_train"].append(OUT / "train" / f"{folio}.xml")
                print(f"{folio} ({r['zone']}, extra): {len(labels)} lines with text, {len(train)} for training")
                continue
            fold = "fold1" if seen.get(r["zone"]) is None else "fold2"
            seen[r["zone"]] = folio
            lists[fold].append(OUT / "train" / f"{folio}.xml")
            lists["tune_train"].append(OUT / "train" / f"{folio}.xml")
            print(f"{folio} ({r['zone']}, tune, {fold}): {len(labels)} lines with text, {len(train)} for training")
        else:
            print(f"{folio} ({r['zone']}, test): {len(labels)} lines with text")
    for name, paths in lists.items():
        (OUT / f"{name}.lst").write_text("".join(f"{p.resolve().relative_to(ROOT)}\n" for p in paths))


if __name__ == "__main__":
    main()
