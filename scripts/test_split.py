"""Tests of scripts/split.py on made-up pages: test and val get at least their shares of the lines, whole pages only,
and the gate stops the script when train holds too few lines. Usage: python scripts/test_split.py"""
import csv
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import split  # noqa: E402


def make(tmp, pages, lines_each):
    xml = tmp / split.CFG["xml"] / "stgall"
    xml.mkdir(parents=True, exist_ok=True)
    with open(xml / "pairs.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["page", "line", "kraken_id", "label", "train", "width_ratio", "text"])
        for p in range(1, pages + 1):
            (xml / f"{p}.xml").touch()
            w.writerows([[p, k, f"{p}_{k}", "a", 1, 1.0, 1] for k in range(1, lines_each + 1)])
    return xml


def run(tmp, min_train):
    split.DATA, split.CFG = tmp, {**split.CFG, "MIN_TRAIN_LINES": min_train}
    try:
        split.main()
    except SystemExit:
        return None
    return {r["page"]: r["split"] for r in csv.DictReader(open(tmp / split.CFG["xml"] / "stgall" / "split.csv"))}


def main():
    real = split.DATA, split.CFG
    try:
        with tempfile.TemporaryDirectory(dir=split.ROOT / "data") as tmp:
            tmp = Path(tmp)
            make(tmp, 40, 10)                                       # 400 lines on 40 pages
            parts = run(tmp, 300)
            assert parts is not None and len(parts) == 40
            counts = {s: sum(v == s for v in parts.values()) * 10 for s in ("train", "val", "test")}
            assert counts["test"] >= 0.10 * 400 and counts["val"] >= 0.05 * 400    # shares met by whole pages
            assert run(tmp, 400) is None                              # under the gate: stops
    finally:
        split.DATA, split.CFG = real
    print("split: 3 checks pass")


if __name__ == "__main__":
    main()
