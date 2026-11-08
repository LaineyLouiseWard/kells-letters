"""How far each raw copy of the answer key lies from the settled key: character error of Claude's copy and of GPT's
copy against the decision, pooled over every line settled with text, with and without spaces (scripts/score.py's
distance and masks). GPT's copy saw only the line images and the label rules; Claude's also had Abbott 1884 as a guide.
Input: data/kells_key/adjudication.csv (--set kells_extra: data/kells_extra/). Output: four lines on standard output.
Usage: python scripts/key_copies.py [--set NAME]
"""
import csv
import sys
from pathlib import Path

import yaml

from score import distance, norm, ref_chars

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config" / "paths.yaml").read_text())
KEY = ROOT / CFG["data_dir"] / (sys.argv[2] if sys.argv[1:2] == ["--set"] else "kells_key")


def main():
    rows = [r for r in csv.DictReader(open(KEY / "adjudication.csv", encoding="utf-8"))
            if r["decision"] not in ("", "<none>")]
    for who in ("claude", "gpt"):
        for spaces in (True, False):
            errors = chars = 0
            for r in rows:
                ref = norm(r["decision"], spaces)
                errors += distance(ref, norm("" if r[who] == "<none>" else r[who], spaces))
                chars += ref_chars(ref)
            label = "with spaces" if spaces else "no spaces"
            print(f"{who} copy, {label}: {errors} of {chars} characters differ from the settled key, {errors / chars:.1%}")


if __name__ == "__main__":
    main()
