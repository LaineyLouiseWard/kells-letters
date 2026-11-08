"""Tests of scripts/score.py on hand-made strings. Usage: python scripts/test_score.py"""
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import score  # noqa: E402
from score import distance, norm, ref_chars, score_page  # noqa: E402


def test_plain_edits():
    assert distance("dixit", "dixit") == 0
    assert distance("dixit", "dicit") == 1          # substitution
    assert distance("dixit", "dxit") == 1           # deletion
    assert distance("dixit", "dixiit") == 1         # insertion
    assert distance("", "ab") == 2 and distance("ab", "") == 2


def test_question_mark():
    assert distance("hu?c", "hunc") == 0            # any one letter
    assert distance("hu?c", "huc") == 1             # a missing letter still costs
    assert distance("hu?c", "huinc") == 1           # one letter only: the second is an insertion


def test_hash():
    assert distance("#um", "um") == 0               # initial read as nothing
    assert distance("#um", "cum") == 0              # as one letter
    assert distance("#um", "ccum") == 0             # as two
    assert distance("#um", "cccum") == 1            # a third is an insertion
    assert distance("#um ergo", "#um ergo") == 0


def test_masks_not_counted_and_spaces():
    assert ref_chars("#u?c") == 2
    assert norm(" quia  manducastis ", True) == "quia manducastis"
    assert norm("quia manducastis", False) == "quiamanducastis"
    t = score_page({"a": "#um ergo", "b": "", "c": "hu?c"}, {"a": "cumergo", "b": "xx"})
    assert (t["err_sp"], t["n_sp"]) == (1 + 4, 7 + 3)  # a missing space; c read as nothing
    assert (t["err"], t["n"]) == (0 + 4, 6 + 3)
    assert (t["q"], t["hash"], t["stray"], t["missing"]) == (1, 1, 2, 1)


def test_stamps():
    """Each score row names the model that read the pages, the key it was scored against and the commit."""
    with tempfile.TemporaryDirectory() as tmp:
        pred, ref, data = Path(tmp) / "read", Path(tmp) / "key", Path(tmp) / "data"
        for d in (pred, ref, data / "kells_key"):
            d.mkdir(parents=True)
        (data / "kells_key" / "adjudication.csv").write_text("folio,n\n")
        score.DATA, real = data, score.DATA
        try:
            s = score.stamps(pred, ref)                     # an older reading, scored against the key as it is
            assert s["model_md5"] == "" and s["key_md5"] == hashlib.md5(b"folio,n\n").hexdigest() and s["commit"]
            (pred / "read.json").write_text(json.dumps({"model_md5": "m"}))
            (ref / "key.json").write_text(json.dumps({"adjudication_md5": "k"}))
            s = score.stamps(pred, ref)                     # a run: the reading's model, the run's copy of the key
            assert (s["model_md5"], s["key_md5"]) == ("m", "k")
            (pred / "read.json").write_text(json.dumps({"model_md5": "m", "pages": ["p1"]}))
            (ref / "sample.csv").write_text("folio,zone,role\np1,A,test\n")
            (ref / "p1.xml").write_text('<PcGts><Page><TextRegion><TextLine id="a"><TextEquiv><Unicode>et'
                                        '</Unicode></TextEquiv></TextLine></TextRegion></Page></PcGts>')
            cmd = [sys.executable, str(Path(score.__file__)), str(pred), "--ref", str(ref)]
            assert subprocess.run(cmd, capture_output=True).returncode == 1   # a page of the reading is lost
            (pred / "p1.xml").write_text((ref / "p1.xml").read_text())
            assert subprocess.run(cmd, capture_output=True).returncode == 0
        finally:
            score.DATA = real


def main():
    tests = [test_plain_edits, test_question_mark, test_hash, test_masks_not_counted_and_spaces, test_stamps]
    for t in tests:
        t()
    print(f"score: {len(tests)} tests pass")


if __name__ == "__main__":
    main()
