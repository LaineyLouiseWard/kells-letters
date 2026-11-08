"""Tests of scripts/key_snapshot.py's gate and copying on a made-up page: the key's PageXML must hold the settled text
and the training text by key_xml.py's rule, and a copied file must still find its image.
Usage: python scripts/test_key_snapshot.py"""
import os
import sys
import tempfile
from pathlib import Path

from lxml import etree
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import key_snapshot as ks  # noqa: E402
import make_xml  # noqa: E402

LINE = {"boundary": [[0, 0], [10, 0], [10, 5], [0, 5]], "baseline": [[0, 4], [10, 4]]}


def page(tmp, ref, train):
    """A one-page key: reference and train/ PageXML with the given texts on lines a, b and c."""
    image = tmp / "raw" / "p1.jpg"
    image.parent.mkdir(parents=True, exist_ok=True)
    Image.new("L", (20, 20)).save(image)
    (tmp / "xml").mkdir(exist_ok=True)
    lines = [{"id": lid, **LINE} for lid in "abc"]
    make_xml.write_xml(tmp / "xml" / "p1.xml", image, lines, {k: v for k, v in zip("abc", ref) if v})
    (tmp / "xml" / "train").mkdir(exist_ok=True)
    make_xml.write_xml(tmp / "xml" / "train" / "p1.xml", image, lines, {k: v for k, v in zip("abc", train) if v})
    return image


def rows(decisions, copies=("x", "", "y")):
    return [{"folio": "p1", "n": str(n), "claude": c, "gpt": c, "decision": d}
            for n, (d, c) in enumerate(zip(decisions, copies), 1)]


def main():
    sample = [{"folio": "p1", "zone": "A", "role": "tune"}]
    lines = [{"folio": "p1", "n": str(n), "kraken_id": lid} for n, lid in enumerate("abc", 1)]
    settled = ("#um ergo", "<none>", "hu?c")
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        image = page(tmp, ("#um ergo", "", "hu?c"), ("um ergo", "", ""))
        xml = tmp / "xml"
        assert ks.out_of_date(sample, rows(settled), lines, xml) == []                 # in step with the key
        assert ks.out_of_date(sample, rows(("#um ergo.", "<none>", "hu?c")), lines, xml) == [
            "p1:1: reference '#um ergo', settled '#um ergo.'",
            "p1:1: training text 'um ergo', by the rule 'um ergo.'"]                     # key changed since
        assert ks.out_of_date(sample, rows(("", "<none>", "hu?c")), lines, xml) == [
            "p1:1: not settled"]                                                         # a line left open
        assert ks.out_of_date(sample, rows(("#um ergo", "", "hu?c")), lines, xml) == []  # no text in either copy
        assert ks.out_of_date(sample, rows(settled), lines + [{"folio": "p1", "n": "4", "kraken_id": "d"}],
                              xml) == ["p1: its lines are not lines.csv's"]             # lines changed
        page(tmp, ("#um ergo", "", "hu?c"), ("#um ergo", "", "hu?c"))
        assert ks.out_of_date(sample, rows(settled), lines, xml) == [
            "p1:1: training text '#um ergo', by the rule 'um ergo'",                     # `#` not left out
            "p1:3: training text 'hu?c', by the rule ''"]                                # `?` line not held out
        dst = tmp / "runs" / "r" / "key" / "train" / "p1.xml"
        ks.copy_xml(xml / "train" / "p1.xml", dst)
        name = etree.parse(str(dst)).getroot().find("{*}Page").get("imageFilename")
        assert os.path.samefile(dst.parent / name, image)                               # still finds its image
        assert ks.lines_of(dst) == ks.lines_of(xml / "train" / "p1.xml")                # same text
        assert ks.train_text("#u?c") == "" and ks.train_text("#um  ergo") == "um ergo"
        pages = [{"folio": f, "zone": z, "role": r} for f, z, r in
                 (("t1", "A", "tune"), ("t2", "A", "tune"), ("t3", "B", "tune"), ("t4", "B", "tune"),
                  ("s1", "A", "test"), ("s2", "B", "test"))]
        good = {"tune": ["t1", "t2", "t3", "t4"], "test": ["s1", "s2"], "fold1": ["train/t1", "train/t3"],
                "fold2": ["train/t2", "train/t4"], "tune_train": ["train/t1", "train/t2", "train/t3", "train/t4"]}

        def lists(**change):
            for name, entries in {**good, **change}.items():
                (xml / f"{name}.lst").write_text("".join(f"/abs/{e}.xml\n" for e in entries))
            return ks.wrong_lists(pages, xml)
        assert lists() == []                                                     # as key_xml.py writes them
        assert lists(fold1=["train/t1", "s1"]) == ["fold1"]                      # a test page in training
        assert lists(fold1=["train/t1", "train/t1", "train/t3"]) == ["fold1"]    # a page twice
        assert lists(fold2=["train/t3", "train/t4"]) == ["fold2"]                # folds that overlap
        assert lists(tune_train=["t1", "train/t2", "train/t3", "train/t4"]) == ["tune_train"]  # reference text
        extra = [{"folio": "e1", "zone": "A", "role": "extra"}]
        x = ks.with_extra(ks.expected_lists(pages), extra)
        assert x["fold1_train"] == [("train", "t1"), ("train", "t3"), ("extra/train", "e1")]  # fold plus extra
        assert x["fold1"] == [("train", "t1"), ("train", "t3")]                  # measured on tune pages only
        assert x["tune_train"][-1] == ("extra/train", "e1") and ("", "e1") not in x["test"]
        page(tmp, ("#um ergo", "", "hu?c"), ("#um ergo", "", ""))
        assert ks.out_of_date([{"folio": "p1", "zone": "A", "role": "extra"}], rows(settled), lines, xml) == [
            "p1:1: training text '#um ergo', by the rule 'um ergo'"]             # an extra page's training text
    print("key_snapshot: 18 checks pass")


if __name__ == "__main__":
    main()
