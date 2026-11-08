"""Final once-over of the settled Kells answer key: GPT looks again at every line where the two typed copies differed.

One call per page, all pages at once. Each call sends that page's disagreed line images and
config/recheck_prompt_gpt.txt filled with: for each line, the two copies (unlabelled, as typing A and B) and the
settled reading; the page's whole settled text, for context; and Abbott 1884's printed passage for the page (OCR
lines of the page's own Gospel, found by shared letter runs with the settled text, since Matthew, Mark and Luke tell
many passages in nearly the same words), as a guide to which word is meant. In Mark, Abbott gives Kells' differences
in a list after the Gospel, by page ("Ad pag. 676."), instead of under the text: the entries for the passage's pages
are added to it. GPT answers OK or FLAG
for each line and changes nothing: a flag is a candidate, settled on the image by the main chat. GPT sees no Kraken
reading. Codex on Lainey's ChatGPT plan, high effort, through ~/.claude/scripts/ask_gpt.py.
Inputs: data/kells_key/adjudication.csv, data/kells_key/lines/<folio>/NN.png, data/raw/abbott/*.txt,
config/key_prompt_gpt.txt (its rules, so both GPT calls judge by the same ones), config/recheck_prompt_gpt.txt.
Outputs in data/kells_key/recheck/: <folio>.prompt.txt (the text sent), <folio>.response.txt (GPT's answer
untouched, then the model and tokens), <folio>.tsv (folio, n, verdict, reading, note). Pages with a .tsv are skipped.
--dry-run writes the prompts and prints, for each page, how many of its letter runs Abbott's passage holds.
--effect READ_DIR: the main chat's calls (recheck/decisions.csv: folio, n, settled, gpt_reading, gpt_note, call,
final, reason) held against a reader's test pages: its character error with spaces against the key as it stands and
with the changed lines, without writing to the key.
--set kells_extra: the same once-over for the extra training pages (data/kells_extra/).
Usage: python scripts/key_recheck.py [--set kells_extra] [--dry-run] [--workers N] [folio ...] | --effect READ_DIR
"""
import argparse
import csv
import re
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import yaml

from key_abbott import EXPAND

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config" / "paths.yaml").read_text())
DATA = ROOT / CFG["data_dir"]
KEY = DATA / "kells_key"
OUT = KEY / "recheck"
ASK = Path.home() / ".claude" / "scripts" / "ask_gpt.py"
RUN = 8                    # letters in a shared run
WINDOW, REACH = 40, 80     # densest stretch of OCR lines, and how far either side of it a matching line may lie
KELLS_NOTE = re.compile(r"^\s*C\S{2,4}\s+K\s*\.?\s*[—-]")  # "CODEX K. —" in OCR spellings such as CoDKX K.
NO_TEXT = "(no text)"
HEAD = re.compile(r"(MATTHAEUM|MARCUM|LUCAM|[lI1]OHANNEM)")  # Abbott's running heads name the Gospel on each page
HEADER = re.compile(r"^\s*([0-9oOlIiSs]{3})\s*\.?\s+SECUNDUM")  # an even page's number, as the OCR reads it
NOTES = re.compile(r"Lectiones\s+Variantes")  # Mark's list of Durrow and Kells differences, up to APPENDIX.
AD_PAG = re.compile(r"^\s*Ad\s+pag\.?\s*(\S+?)\.?\s*$")
DIGITS = str.maketrans("oOlIiSs", "0011155")
# Kells' Gospel openings: Mark at 130r, Luke at 188r, John at 292r (Matthew's text before 130r).
OPENINGS = [(292, "IOHANNEM"), (188, "LUCAM"), (130, "MARCUM"), (0, "MATTHAEUM")]


def gospel(folio):
    number = int(re.match(r"\d+", folio).group())
    return next(name for start, name in OPENINGS if number >= start)


def letters(text):
    """Lower-case letters only, u for v and i for j, as Abbott's OCR is compared with the key."""
    return re.sub(r"[^a-z]", "", text.lower().replace("v", "u").replace("j", "i"))


def runs(s):
    return {s[i:i + RUN] for i in range(len(s) - RUN + 1)}


def settled_letters(text):
    t = text.lower()
    for short, full in EXPAND.items():
        t = t.replace(short, full)
    return letters(t)


def page_number(text):
    digits = text.translate(DIGITS)
    return int(digits) if digits.isdigit() else None


def abbott_lines():
    """Abbott's OCR lines, volume by volume, each with its letters (the OCR reads the capital I of Iesus as l) and
    the Gospel named by the last running head above it: None in a volume's preface and from a list of differences
    on. Also Mark's list of differences, as page -> text of its "Ad pag." entry (an entry whose number the OCR
    garbled stays part of the one before)."""
    out, notes = [], {}
    for p in sorted((DATA / "raw" / "abbott").glob("*.txt")):
        name, listing, page = None, False, None
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            if NOTES.search(line):
                listing = True
            elif listing and line.strip() == "APPENDIX.":
                listing, page = False, None
            elif listing and (m := AD_PAG.match(line)):
                page = page_number(m.group(1)) or page
            if listing and page is not None:
                notes[page] = notes.get(page, "") + line + "\n"
            if not listing and (m := HEAD.search(line)):
                name = "IOHANNEM" if m.group(1).endswith("OHANNEM") else m.group(1)
            out.append((line, letters(line).replace("lesu", "iesu"), None if listing or page else name))
    return out, notes


def passage(page, ocr, notes, name):
    """Abbott's OCR lines for a page: every line of its Gospel sharing at least two letter runs with the page within
    REACH of the densest WINDOW of such lines, extended to the end of the next Kells note after them, then, where
    the Gospel's differences are listed apart (Mark), the list's entries for the passage's pages. Returns the text and
    the share of the page's letter runs it holds."""
    want = runs(page)
    score = [len(runs(l) & want) if g == name else 0 for _, l, g in ocr]
    best = max(range(len(ocr)), key=lambda i: sum(score[i:i + WINDOW]))
    hits = [i for i in range(max(0, best - REACH), min(len(ocr), best + WINDOW + REACH)) if score[i] >= 2]
    first, last = hits[0], hits[-1]
    for j in range(last + 1, min(len(ocr), last + REACH)):
        if ocr[j][2] != name:
            break
        if KELLS_NOTE.match(ocr[j][0]):
            last = j
            while last + 1 < len(ocr) and ocr[last + 1][0].strip():
                last += 1
            break
    block = ocr[max(0, first - 3):last + 1]
    text = "\n".join(line for line, _, _ in block)
    if notes and name == "MARCUM":
        start = next((page_number(m.group(1)) for line, _, _ in reversed(ocr[max(0, first - REACH):first + 1])
                      if (m := HEADER.match(line)) and page_number(m.group(1))), None)
        pages = [n for line, _, _ in block if (m := HEADER.match(line)) and (n := page_number(m.group(1)))]
        keys = sorted({max((k for k in notes if k <= n), default=None) for n in [start, *pages] if n} - {None})
        text += ("\n\n[In Mark, Abbott lists the differences of Codex D and Codex K (Kells) after the Gospel, by page."
                 " The entries for this passage's pages:]\n" + "".join(notes[k] for k in keys))
    held = runs(letters(text).replace("lesu", "iesu")) & want
    return text, len(held) / max(1, len(want))


def show(text):
    return text if text not in ("", "<none>") else NO_TEXT


def build(folio, rows, ocr, rules, template):
    page_rows = [r for r in rows if r["folio"] == folio]
    check = [r for r in page_rows if " ".join(r["claude"].split()) != " ".join(r["gpt"].split())]
    page = "".join(settled_letters(r["decision"]) for r in page_rows if r["decision"] not in ("", "<none>"))
    abbott, held = passage(page, *ocr, gospel(folio))
    context = "\n".join(f"{int(r['n']):02d}\t{show(r['decision'])}" for r in page_rows)
    listing = "\n".join(f"Image {k} is line {int(r['n']):02d}\n  typing A: {show(r['claude'])}\n"
                        f"  typing B: {show(r['gpt'])}\n  settled:  {show(r['decision'])}"
                        for k, r in enumerate(check, 1))
    prompt = (template.replace("{ABBOTT}", abbott).replace("{PAGE}", context).replace("{LINES}", listing)
              .replace("{RULES}", rules))
    images = [str((KEY / "lines" / folio / f"{int(r['n']):02d}.png").resolve()) for r in check]
    return check, prompt, images, held


def parse(answer, check):
    """Line number -> (verdict, reading, note) from GPT's tab-separated answer."""
    asked = {int(r["n"]) for r in check}
    got = {}
    for row in answer.splitlines():
        m = re.match(r"^\s*(\d{1,2})[\t ]+(OK|FLAG)\b\t?([^\t]*)\t?(.*)$", row)
        if m and int(m.group(1)) in asked:
            got[int(m.group(1))] = (m.group(2), m.group(3).strip(), m.group(4).strip())
    return got


def ask(folio, check, prompt, images):
    cmd = [sys.executable, str(ASK), "--effort", "high", "--no-log"]
    for im in images:
        cmd += ["-i", im]
    result = subprocess.run(cmd + [prompt], capture_output=True, text=True)
    (OUT / f"{folio}.response.txt").write_text(result.stdout + "\n" + result.stderr)
    got = parse(result.stdout, check)
    if result.returncode or len(got) < len(check):
        return f"{folio}: GPT call failed or answered {len(got)} of {len(check)} lines; see {folio}.response.txt"
    with open(OUT / f"{folio}.tsv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["folio", "n", "verdict", "reading", "note"])
        for r in check:
            w.writerow([folio, r["n"], *got[int(r["n"])]])
    flags = Counter(v for v, _, _ in got.values())["FLAG"]
    return f"{folio}: {len(check)} lines checked, {flags} flagged"


def effect(read):
    from score import REF, add, lines_of, score_page
    ids = {(r["folio"], int(r["n"])): r["kraken_id"] for r in csv.DictReader(open(KEY / "lines.csv"))}
    changed = {}
    for d in csv.DictReader(open(OUT / "decisions.csv", encoding="utf-8")):
        if d["call"] == "change":
            changed.setdefault(d["folio"], {})[ids[(d["folio"], int(d["n"]))]] = d["final"]
    before, after = {}, {}
    for r in csv.DictReader(open(KEY / "sample.csv")):
        if r["role"] == "test":
            ref, pred = lines_of(REF / f"{r['folio']}.xml"), lines_of(Path(read) / f"{r['folio']}.xml")
            before = add(before, score_page(ref, pred))
            after = add(after, score_page({k: changed.get(r["folio"], {}).get(k, v) for k, v in ref.items()}, pred))
    lines = sum(len(v) for v in changed.values())
    print(f"{lines} lines changed; test pages: {before['err_sp']} of {before['n_sp']} characters wrong "
          f"({before['err_sp'] / before['n_sp']:.2%}) now, {after['err_sp']} of {after['n_sp']} "
          f"({after['err_sp'] / after['n_sp']:.2%}) with the changes")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--effect", metavar="READ_DIR")
    ap.add_argument("--set", default="kells_key")
    ap.add_argument("--workers", type=int, default=0, help="calls at once (default: every page at once)")
    ap.add_argument("folios", nargs="*")
    args = ap.parse_args()
    global KEY, OUT
    KEY = KEY.with_name(args.set)
    OUT = KEY / "recheck"
    if args.effect:
        return effect(args.effect)
    rows = list(csv.DictReader(open(KEY / "adjudication.csv", encoding="utf-8")))
    folios = args.folios or list(dict.fromkeys(r["folio"] for r in rows))
    rules = "\n".join(l for l in (ROOT / "config" / "key_prompt_gpt.txt").read_text().splitlines()
                      if l.startswith("- "))
    template = (ROOT / "config" / "recheck_prompt_gpt.txt").read_text()
    ocr = abbott_lines()
    OUT.mkdir(parents=True, exist_ok=True)
    jobs = []
    for folio in folios:
        check, prompt, images, held = build(folio, rows, ocr, rules, template)
        (OUT / f"{folio}.prompt.txt").write_text(prompt)
        print(f"{folio}: {len(check)} lines to check; Abbott's passage holds {held:.0%} of the page's letter runs")
        if check and not args.dry_run and not (OUT / f"{folio}.tsv").exists():
            jobs.append((folio, check, prompt, images))
    if jobs:
        with ThreadPoolExecutor(max_workers=args.workers or len(jobs)) as pool:
            for message in pool.map(lambda job: ask(*job), jobs):
                print(message)


if __name__ == "__main__":
    main()
