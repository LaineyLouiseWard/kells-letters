"""Split the kept St Gall pages into train, val and test, by whole page, for every reader.

Pages (those with a PageXML in data/xml/stgall/) are shuffled with SEED and assigned in turn to test until it holds at
least TEST_SHARE of the lines with text, then to val until it holds VAL_SHARE; the rest train. Gate: at least
MIN_TRAIN_LINES lines with text in train; otherwise the lists are still written and the script exits with an error.

Outputs, in data/xml/stgall/: train.lst, val.lst, test.lst (PageXML paths relative to the repo root, as ketos and
party take them) and split.csv (page, split, lines with text).
Usage: python scripts/split.py
"""
import csv
import random
import sys
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config" / "paths.yaml").read_text())
DATA = ROOT / CFG["data_dir"]


def main():
    xml = DATA / CFG["xml"] / "stgall"
    lines = Counter(r["page"] for r in csv.DictReader(open(xml / "pairs.csv")) if r["text"] == "1")
    pages = sorted((p for p in lines if (xml / f"{p}.xml").exists()), key=int)
    random.Random(CFG["SEED"]).shuffle(pages)
    total = sum(lines[p] for p in pages)
    split, filled = {}, Counter()
    for p in pages:
        part = next((name for name, share in (("test", CFG["TEST_SHARE"]), ("val", CFG["VAL_SHARE"]))
                     if filled[name] < share * total), "train")
        split[p] = part
        filled[part] += lines[p]
    for part in ("train", "val", "test"):
        chosen = sorted((p for p in pages if split[p] == part), key=int)
        (xml / f"{part}.lst").write_text("".join(f"{(xml / f'{p}.xml').relative_to(ROOT)}\n" for p in chosen))
    with open(xml / "split.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["page", "split", "lines"])
        w.writerows([p, split[p], lines[p]] for p in sorted(pages, key=int))
    print(", ".join(f"{part} {sum(split[p] == part for p in pages)} pages, {filled[part]} lines"
                    for part in ("train", "val", "test")))
    if filled["train"] < CFG["MIN_TRAIN_LINES"]:
        sys.exit(f"Split gate failed: {filled['train']} training lines, fewer than {CFG['MIN_TRAIN_LINES']}")


if __name__ == "__main__":
    main()
