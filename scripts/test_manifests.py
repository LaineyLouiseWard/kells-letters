"""Tests of the download gate in scripts/manifests.py and the segmenter's pinned checksum in scripts/segment_pages.py.
An image opens only when it is a whole JPEG of the expected height; the segmenter stops on a model that is not the
pinned one. Usage: python scripts/test_manifests.py"""
import hashlib
import sys
import tempfile
from pathlib import Path

import kraken
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import manifests  # noqa: E402
import segment_pages  # noqa: E402


def main():
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        Image.new("L", (40, 30)).save(tmp / "whole.jpg")
        assert manifests.opens(tmp / "whole.jpg", 30) == 40                     # whole, right height: its width
        assert manifests.opens(tmp / "whole.jpg", 31) is None                   # wrong height
        (tmp / "cut.jpg").write_bytes((tmp / "whole.jpg").read_bytes()[:-2])   # download cut before the end
        assert manifests.opens(tmp / "cut.jpg", 30) is None
        Image.new("L", (40, 30)).save(tmp / "other.png")
        assert manifests.opens(tmp / "other.png", 30) is None                   # not a JPEG
    model = Path(kraken.__file__).parent / segment_pages.CFG["kraken"]["model"]
    assert hashlib.sha256(model.read_bytes()).hexdigest() == segment_pages.CFG["kraken"]["sha256"]
    real, sys.argv = segment_pages.CFG["kraken"]["sha256"], ["segment_pages.py", "stgall"]
    segment_pages.CFG["kraken"]["sha256"] = "0" * 64
    try:
        segment_pages.main()
        raise AssertionError("a segmenter that is not the pinned one passed")
    except SystemExit as e:
        assert "does not match the pinned checksum" in str(e.code)
    finally:
        segment_pages.CFG["kraken"]["sha256"] = real
    print("manifests and segment_pages: 6 checks pass")


if __name__ == "__main__":
    main()
