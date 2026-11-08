"""Write one row per physical line of St Gall 51 (Cod. Sang. 51) from the Insular Gospels TEI files: its label, whether
its last word continues on the next line, and whether it may be used in training.

Label rules:
- letters lower case, as written; æ and ę are letters of their own. The TEI writes v only in numerals, where the
  scribe wrote u (seen on pages 37 and 40), so the label writes u; there is no j;
- shortened words stay short: <abbr> letters kept, <ex> expansions dropped, overlines not written;
- Insular signs, one character each, from the <hi rend> value, not the word inside it: ÷ est, ƕ autem, ⧺ enim, ⁊ et;
- joined letters (rend "lig"), red letters (rend "rubric") and enlarged letters written as their letters;
- punctuation as written (<pc>, including /); a space between words (<w>) and for each <space>;
- corrections: the first hand's reading (<rdg type="orig">) of each <app>.
Markup the plan does not name: notes are not written; an illegible <gap> is written as one _ per character of its
smallest extent; <unclear> and <supplied> letters, margin segments (<seg type="margin">) and lection titles (<fw>) are
written; the empty markers cap29End and cap2End and two leftover "rub]" strings (both in decorated lines) are dropped.
Any other element or rend value stops the script, so nothing is silently dropped.

Lines kept out of training (train=0, with the reason): a line holding an <app> (correction), enlarged letters (rend
cap2 to cap32), letters written above or below the line (displaced-above, displaced-under), an illegible gap, unclear
or supplied letters, margin text, or no text at all. Every physical line stays in the table; nothing is removed here.
Three files give the root xml:id "VL 28", which XML forbids (an id has no spaces); the space is removed before parsing.

Output: data/stgall/lines_text.csv (page, column, line, label, continues, train, reason).
Usage: python scripts/stgall_text.py
"""
import csv
import re
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

import yaml
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config" / "paths.yaml").read_text())
DATA = ROOT / CFG["data_dir"]
TEI = "{http://www.tei-c.org/ns/1.0}"
SIGNS = {"÷": "÷", "ƕ": "ƕ", "⧺": "⧺", "et": "⁊"}
WRITTEN = {"lig", "rubric", "overline"}
DISPLACED = {"displaced-above", "displaced-under"}
CONTAINERS = {"body", "div", "ab", "abbr", "fw"}
NOT_WRITTEN = {"note", "ex", "cap29End", "cap2End"}
ARTEFACT = "rub]"
FIELDS = ["page", "column", "line", "label", "continues", "train", "reason"]


class Lines:
    """Physical lines in page order, each collecting its text and the reasons it is kept out of training."""

    def __init__(self):
        self.rows, self.page, self.column, self.inside = [], None, None, []

    def start(self, n, joined):
        if self.page is None or self.column is None:
            raise ValueError(f"line {n} before a page or column break")
        if joined:
            self.rows[-1]["continues"] = 1
        self.rows.append({"page": self.page, "column": self.column, "line": n, "text": [], "continues": 0,
                          "reasons": set(self.inside)})

    def add(self, text):
        if not self.rows:
            raise ValueError(f"text {text!r} before the first line")
        self.rows[-1]["text"].append(text)

    @contextmanager
    def within(self, reason):
        """Mark the current line, and every line begun inside the element, with reason."""
        self.rows[-1]["reasons"].add(reason)
        self.inside.append(reason)
        yield
        self.inside.pop()


def name(e):
    return e.tag.replace(TEI, "") if isinstance(e.tag, str) else None


def content(e, lines):
    """Write e's own text, then each child followed by its tail. Whitespace in the files is layout, not spacing."""
    if e.text and e.text.split():
        lines.add("".join(e.text.split()))
    for c in e:
        walk(c, lines)
        if c.tail and c.tail.split():
            lines.add("".join(c.tail.split()))


def walk(e, lines):
    t = name(e)
    if t is None or t in NOT_WRITTEN:
        return
    if t == "pb":
        lines.page, lines.column = int(e.get("n")), None
    elif t == "cb":
        lines.column = int(e.get("n"))
    elif t == "lb":
        lines.start(int(e.get("n")), e.get("break") == "no")
    elif t == "space":
        lines.add(" ")
    elif t == "pc":
        if len(e):
            raise ValueError("markup inside <pc>")
        lines.add(e.text)
    elif t == "w":
        lines.add(" ")
        content(e, lines)
        lines.add(" ")
    elif t == "app":
        orig = [r for r in e if name(r) == "rdg" and r.get("type") == "orig"]
        if len(orig) != 1:
            raise ValueError(f"<app> with {len(orig)} first-hand readings")
        with lines.within("correction"):
            content(orig[0], lines)
    elif t == "gap":
        with lines.within("illegible letters"):
            lines.add("_" * int(re.match(r"\d+", e.get("extent")).group()))
    elif t in ("unclear", "supplied"):
        with lines.within(f"{t} letters"):
            content(e, lines)
    elif t == "seg" and e.get("type") == "margin":
        with lines.within("margin text"):
            content(e, lines)
    elif t == "hi":
        rend = e.get("rend") or ""
        if rend in SIGNS:
            if any(name(c) in ("lb", "pb", "cb") for c in e.iter()):
                raise ValueError(f"line break inside the sign {rend}")
            lines.add(SIGNS[rend])
        elif re.fullmatch(r"cap\d+", rend):
            with lines.within("enlarged letters"):
                content(e, lines)
        elif rend in DISPLACED:
            with lines.within("displaced letters"):
                content(e, lines)
        elif rend in WRITTEN:
            content(e, lines)
        else:
            raise ValueError(f"unknown rend value {rend!r}")
    elif t in CONTAINERS:
        content(e, lines)
    else:
        raise ValueError(f"unknown TEI element <{t}>")


def label(parts):
    return re.sub(r" +", " ", "".join(parts).replace(ARTEFACT, "")).strip().lower().replace("v", "u")


def read(raw):
    """Rows of one TEI file (its bytes), in page order."""
    raw = raw.replace(b'xml:id="VL 28"', b'xml:id="VL28"', 1)
    lines = Lines()
    content(etree.fromstring(raw, etree.XMLParser(huge_tree=True)).find(f".//{TEI}body"), lines)
    rows = []
    for r in lines.rows:
        text = label(r["text"])
        reasons = sorted(r["reasons"]) or ([] if text else ["no text"])
        rows.append({"page": r["page"], "column": r["column"], "line": r["line"], "label": text,
                     "continues": r["continues"], "train": int(not reasons), "reason": "; ".join(reasons)})
    return rows


def main():
    tei = DATA / CFG["stgall"]["tei_out"]
    rows = [r for f in CFG["stgall"]["tei_files"] for r in read((tei / f).read_bytes())]
    seen = Counter((r["page"], r["column"]) for r in rows)
    for (page, column), n in seen.items():
        got = [r["line"] for r in rows if (r["page"], r["column"]) == (page, column)]
        if got != list(range(1, n + 1)):
            raise ValueError(f"page {page} column {column}: line numbers {got}")
    out = DATA / CFG["stgall"]["text"]
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"{len(rows)} lines on {len({r['page'] for r in rows})} pages; train=1: {sum(r['train'] for r in rows)}")
    for why, n in Counter(x for r in rows for x in r["reason"].split("; ") if x).most_common():
        print(f"  lines with {why}: {n}")
    print("characters (train=1):", "".join(sorted(set("".join(r["label"] for r in rows if r["train"])) - {" "})))


if __name__ == "__main__":
    main()
