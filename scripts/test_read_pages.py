"""Tests of scripts/read_pages.py's gate on made-up pages: a page whose output is missing, or lacks a line of its
input, is caught (Kraken reports success even when a page fails). Usage: python scripts/test_read_pages.py"""
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_xml  # noqa: E402
import read_pages  # noqa: E402

LINE = {"boundary": [[0, 0], [10, 0], [10, 5], [0, 5]], "baseline": [[0, 4], [10, 4]]}


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        image = tmp / "p.jpg"
        Image.new("L", (20, 20)).save(image)
        both = [{"id": lid, **LINE} for lid in "ab"]
        src, dst = tmp / "in" / "p1.xml", tmp / "out" / "p1.xml"
        src.parent.mkdir()
        dst.parent.mkdir()
        make_xml.write_xml(src, image, both, {"a": "ihs"})
        assert read_pages.unread([(src, dst)]) == ["p1"]                      # no output
        make_xml.write_xml(dst, image, both[:1], {"a": "ihs"})
        assert read_pages.unread([(src, dst)]) == ["p1"]                      # a line missing
        make_xml.write_xml(dst, image, both, {"a": "ihs", "b": "et"})
        assert read_pages.unread([(src, dst)]) == []                          # every line read
        key, model, out = tmp / "key", tmp / "m.safetensors", tmp / "read" / "final"
        key.mkdir()
        (key / "sample.csv").write_text("folio,zone,role\np1,A,test\n")
        (key / "key.json").write_text(json.dumps({"adjudication_md5": "k"}))
        shutil.copy(src, key / "p1.xml")
        model.write_bytes(b"weights")

        real = read_pages.subprocess.run

        def kraken(change=False, code=0):
            def run(cmd, **kw):                                                # stands in for Kraken: copies the
                if cmd[0] != read_pages.KRAKEN:                                # input pages to the outputs
                    return real(cmd, **kw)
                for k, arg in enumerate(cmd):
                    if arg == "-i":
                        shutil.copy(cmd[k + 1], cmd[k + 2])
                if change:
                    model.write_bytes(b"other weights")
                return read_pages.subprocess.CompletedProcess(cmd, code, stderr="")
            return run
        sys.argv = ["read_pages.py", "--model", str(model), "--key", str(key), "--role", "test", "--out", str(out)]
        try:
            read_pages.subprocess.run = kraken(code=1)
            assert stops(read_pages.main) and not out.exists()                 # the reader failed: no reading kept
            read_pages.subprocess.run = kraken(change=True)
            assert stops(read_pages.main) and not out.exists()                 # the model changed: no reading kept
            model.write_bytes(b"weights")
            read_pages.subprocess.run = kraken()
            read_pages.main()
            record = json.load(open(out / "read.json"))
            assert record["model_md5"] == hashlib.md5(b"weights").hexdigest() and record["key_md5"] == "k"
            assert not out.with_name("final.part").exists()                    # renamed whole
            assert stops(read_pages.main)                                      # read once: a second reading stops
        finally:
            read_pages.subprocess.run = real
    print("read_pages: 9 checks pass")


def stops(f):
    try:
        f()
    except SystemExit:
        return True
    return False


if __name__ == "__main__":
    main()
