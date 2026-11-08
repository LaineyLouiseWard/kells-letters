"""Base models: download any that are missing and test every file against the md5 of its Zenodo record.

Models, their records and checksums: config/models.yaml. Files: <dir>/<name>/<file>, with dir from that file unless
the KELLS_MODELS environment variable names another. A download goes to a .part file, renamed only when its md5
matches; a file whose md5 does not match stops the script, so no run starts from a changed model.
Usage: python scripts/models.py [name ...]    (every model when none is named)
       python scripts/models.py --path name   (prints where the file is, for the Makefile; tests nothing)
"""
import argparse
import hashlib
import os
import sys
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config" / "models.yaml").read_text())
HEADERS = {"User-Agent": "kells-letters research download (academic use)"}


def path(name, cfg=CFG):
    if name not in cfg["models"]:
        sys.exit(f"{name} is not in config/models.yaml: {' '.join(cfg['models'])}")
    folder = Path(os.environ.get("KELLS_MODELS") or cfg["dir"]).expanduser()
    return folder / name / cfg["models"][name]["file"]


def md5(file):
    h = hashlib.md5()
    with open(file, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch(url, target, want):
    """Download url to target through a .part file; the file is kept only if its md5 is want."""
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=120) as r, open(part, "wb") as f:
        for block in iter(lambda: r.read(1 << 20), b""):
            f.write(block)
    got = md5(part)
    if got != want:
        part.unlink()
        sys.exit(f"{url}: md5 {got}, not {want}; nothing kept")
    part.rename(target)


def ensure(name, cfg=CFG):
    entry, target = cfg["models"][name], path(name, cfg)
    if not target.exists():
        print(f"{name}: downloading {entry['url']}", flush=True)
        fetch(entry["url"], target, entry["md5"])
    got = md5(target)
    if got != entry["md5"]:
        sys.exit(f"{name}: {target} has md5 {got}, not {entry['md5']} ({entry['doi']})")
    print(f"{name}: {target} md5 matches {entry['doi']}")
    return target


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("names", nargs="*")
    ap.add_argument("--path", metavar="NAME")
    a = ap.parse_args()
    if a.path:
        print(path(a.path))
        return
    for name in a.names or CFG["models"]:
        ensure(name)


if __name__ == "__main__":
    main()
