"""List where a settled key page's letters disagree with Abbott 1884's text, so those words are viewed again.

Abbott (data/raw/abbott/, OCR) prints the Vulgate and Codex Usserianus passage by passage, with notes on Kells
("CoDEX K."). The page's settled letters (adjudication.csv; spaces, punctuation and masks left out, unambiguous
Insular contractions such as ihs written out) are located in Abbott by shared 12-letter runs and aligned with the two
best-matching stretches. A disagreement is reported only where the page disagrees with both, and not where `#` or
`?` stands against at most two letters. Abbott is a guide, not the answer: a reported word is viewed on the image,
and the image decides (Kells has its own spellings and slips).
Output: one line per disagreement, "folio line: key 'letters' | Abbott 'letters'", with a few letters either side.
A long stretch only Abbott has is either his notes and page headings or text the key lacks, such as words outside
every Kraken line (187r: "et si" after line 19).
Usage: python scripts/key_abbott.py [folio ...]
"""
import csv
import re
import sys
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config" / "paths.yaml").read_text())
DATA = ROOT / CFG["data_dir"]
# Contractions with one reading, as substrings of the key's letters; ds, di, do and dm stay, since they occur in words.
EXPAND = {"ihs": "iesus", "ihm": "iesum", "ihu": "iesu", "xps": "christus", "xpi": "christi", "xpo": "christo",
          "xpm": "christum", "dns": "dominus", "dni": "domini", "dno": "domino", "dnm": "dominum", "dne": "domine",
          "sps": "spiritus", "spm": "spiritum", "spu": "spiritu", "÷": "est", "ƕ": "autem", "⧺": "enim", "⁊": "et"}
K, CONTEXT = 12, 4


def abbott():
    text = " ".join(p.read_text(encoding="utf-8", errors="ignore")
                    for p in sorted((DATA / "raw" / "abbott").glob("*.txt")))
    text = re.sub(r"[^a-z]", "", text.lower().replace("v", "u").replace("j", "i"))
    return text.replace("lesu", "iesu")  # OCR reads the capital I of Iesus as l


def key_letters(lines):
    """The page's letters and, for each, its line number."""
    letters, where = [], []
    for n, t in lines:
        t = t.lower()
        for short, full in EXPAND.items():
            t = t.replace(short, full)
        for c in t:
            if c.isalpha() or c in "#?":
                letters.append(c)
                where.append(n)
    return "".join(letters), where


def windows(key, ref, top=2):
    """Start positions in ref of the top best-matching stretches, from shared K-letter runs."""
    index = {}
    for i in range(len(ref) - K):
        index.setdefault(ref[i:i + K], []).append(i)
    votes = Counter()
    for j in range(0, len(key) - K):
        for i in index.get(key[j:j + K], [])[:50]:
            votes[(i - j) // 500] += 1
    starts = []
    for b, _ in votes.most_common():
        if all(abs(b - s) > 6 for s in starts):
            starts.append(b)
        if len(starts) == top:
            break
    return [max(0, b * 500 - 300) for b in starts]


def main():
    rows = list(csv.DictReader(open(DATA / "kells_key" / "adjudication.csv", encoding="utf-8")))
    folios = sys.argv[1:] or list(dict.fromkeys(r["folio"] for r in rows))
    ref = abbott()
    for folio in folios:
        lines = [(int(r["n"]), r["decision"]) for r in rows if r["folio"] == folio
                 and r["decision"] not in ("", "<none>")]
        if not lines:
            continue
        key, where = key_letters(lines)
        bad = [set(range(len(key)))]
        aligned = []
        for s in windows(key, ref):
            seg = ref[s:s + int(len(key) * 1.6) + 600]
            sm = SequenceMatcher(None, key, seg, autojunk=False)
            ops = [op for op in sm.get_opcodes() if op[0] != "equal"]
            miss = set()
            for tag, i1, i2, j1, j2 in ops:
                k, a = key[i1:i2], seg[j1:j2]
                if any(c in k for c in "#?") and len(a) <= 2 + k.count("#") * 2:
                    continue
                miss |= set(range(i1, i2)) if i2 > i1 else {min(i1, len(key) - 1)}
            bad.append(miss)
            aligned.append((sm, seg, ops))
        if not aligned:
            print(f"{folio}: not found in Abbott")
            continue
        flagged = set.intersection(*bad[1:])
        sm, seg, ops = max(aligned, key=lambda x: sum(b.size for b in x[0].get_matching_blocks()))
        matched = sum(b.size for b in sm.get_matching_blocks())
        print(f"{folio}: {matched} of {len(key)} letters match Abbott's best stretch; disagreements with both:")
        for tag, i1, i2, j1, j2 in ops:
            span = set(range(i1, i2)) if i2 > i1 else {min(i1, len(key) - 1)}
            if not span & flagged or (i1 == i2 and i1 in (0, len(key))):
                continue  # Abbott's text before the page starts or after it ends
            n = where[min(i1, len(key) - 1)]
            a = seg[j1:j2] if j2 - j1 <= 30 else f"{seg[j1:j1 + 20]}... {j2 - j1} letters"
            print(f"  {n:02d}: key '{key[max(0, i1 - CONTEXT):i1]}[{key[i1:i2]}]{key[i2:i2 + CONTEXT]}' | "
                  f"Abbott '{seg[max(0, j1 - CONTEXT):j1]}[{a}]{seg[j2:j2 + CONTEXT]}'")


if __name__ == "__main__":
    main()
