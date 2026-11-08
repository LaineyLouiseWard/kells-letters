"""What a result was made with: the md5 of a file, and the git commit of the code (marked when scripts/, config/ or
the Makefile differ from it, so a result from uncommitted code shows as such).
Usage: python scripts/stamp.py FILE ...   (prints each file's md5, then the commit)
"""
import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SYNCED_COMMIT = ".synced_commit"


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def commit():
    """The code's git commit. A copy without git history (Sonic's, from sonic/sync.sh, which copies committed code only)
    gives the commit it was copied from, which sync.sh writes to SYNCED_COMMIT."""
    if not (ROOT / ".git").exists():
        return (ROOT / SYNCED_COMMIT).read_text().strip() if (ROOT / SYNCED_COMMIT).exists() else "unknown"

    def git(*a):
        return subprocess.run(["git", *a], cwd=ROOT, capture_output=True, text=True)
    head = git("rev-parse", "--short", "HEAD")
    if head.returncode:
        return "unknown"
    changed = git("status", "--porcelain", "--", "scripts", "config", "Makefile").stdout.strip()
    return head.stdout.strip() + ("+changes" if changed else "")


if __name__ == "__main__":
    for name in sys.argv[1:]:
        print(f"md5 {md5(name)} {name}")
    print(f"commit {commit()}")
