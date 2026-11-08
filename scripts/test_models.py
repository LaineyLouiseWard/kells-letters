"""Tests of scripts/models.py on small made-up files: a download is kept only with the right md5, and a stored file
with another md5 stops the script. Downloads use file:// URLs, so no network. Usage: python scripts/test_models.py"""
import hashlib
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import models  # noqa: E402


def stops(f, *a):
    try:
        f(*a)
    except SystemExit:
        return True
    return False


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        source = tmp / "source.bin"
        source.write_bytes(b"model weights")
        right = hashlib.md5(b"model weights").hexdigest()
        cfg = {"dir": str(tmp / "store"), "models": {
            "good": {"doi": "x", "file": "m.bin", "md5": right, "url": source.as_uri()},
            "bad": {"doi": "x", "file": "m.bin", "md5": "0" * 32, "url": source.as_uri()}}}
        os.environ.pop("KELLS_MODELS", None)
        assert models.ensure("good", cfg).read_bytes() == b"model weights"     # downloaded, md5 matches
        assert models.ensure("good", cfg) == tmp / "store" / "good" / "m.bin"  # already there: tested only
        assert stops(models.ensure, "bad", cfg)                                # wrong md5: stops
        assert not list((tmp / "store" / "bad").glob("*"))                     # and keeps nothing
        (tmp / "store" / "good" / "m.bin").write_bytes(b"changed weights")
        assert stops(models.ensure, "good", cfg)                               # a stored file changed: stops
        os.environ["KELLS_MODELS"] = str(tmp / "elsewhere")
        assert models.path("good", cfg) == tmp / "elsewhere" / "good" / "m.bin"
        assert stops(models.path, "unknown", cfg)
    print("models: 7 checks pass")


if __name__ == "__main__":
    main()
