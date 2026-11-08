"""Tests of scripts/make_xml.py's pairing gates on a made-up page of ten evenly ruled lines, with the thresholds of
config/paths.yaml: line totals, the spacing test (a missed line beside an extra one), the width test for a line and for
a page, two columns, and short lines. Usage: python scripts/test_make_xml.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_xml as mx  # noqa: E402


def seg(i, y, x0=100, x1=1100):
    return {"id": f"l{i}", "baseline": [[x0, y], [x1, y]]}


def typed(n, chars=40, column="1"):
    return [{"line": str(k), "label": "a" * chars, "column": column, "train": "1"} for k in range(1, n + 1)]


def reasons(drop, scope):
    return [d["reason"] for d in drop if d["scope"] == scope]


def main():
    lines = [seg(i, 100 * i) for i in range(1, 11)]
    pairs, drop = mx.pair_page("p", lines, typed(10))
    assert len(pairs) == 10 and not drop                                            # a good page pairs whole
    pairs, drop = mx.pair_page("p", lines, typed(9))
    assert not pairs and reasons(drop, "page") == ["line totals differ (Kraken 10, text 9)"]
    shifted = [s for s in lines if s["id"] != "l5"] + [seg(11, 750)]              # missed line 5, extra at 750
    pairs, drop = mx.pair_page("p", shifted, typed(10))
    assert not pairs and reasons(drop, "page") == ["uneven line spacing"]          # totals equal, labels shifted
    one_wide = typed(10)
    one_wide[3]["label"] = "a" * 80                                                 # twice the page's width per letter
    pairs, drop = mx.pair_page("p", lines, one_wide)
    assert len(pairs) == 10 and reasons(drop, "line") == ["fails width test"]       # 1 in 10: the line goes
    two_wide = typed(10)
    two_wide[3]["label"] = two_wide[6]["label"] = "a" * 80
    pairs, drop = mx.pair_page("p", lines, two_wide)
    assert not pairs and reasons(drop, "page") == ["fails width test (20% of lines)"]  # over PAGE_FAIL: the page
    pairs, drop = mx.pair_page("p", lines, typed(9) + typed(1, column="2"))
    assert not pairs and reasons(drop, "page") == ["two columns"]
    margin = lines + [seg(12, 1050, 100, 250)]                                      # a short line in the margin
    pairs, drop = mx.pair_page("p", margin, typed(10) + typed(1, chars=3))          # and a word end alone
    assert len(pairs) == 10 and sorted(d["side"] for d in drop) == ["kraken", "text"]
    print("make_xml: 7 checks pass")


if __name__ == "__main__":
    main()
