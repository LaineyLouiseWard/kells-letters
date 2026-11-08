"""GPT's copy of the Kells answer key: one call per page, with that page's line images and only the label rules.

Pages: data/<set>/sample.csv (set kells_key unless --set names another, such as kells_extra for extra training pages,
typed the same way). Each call sends data/<set>/lines/<folio>/NN.png (all of the page's Kraken lines, in order) with
config/key_prompt_gpt.txt through ~/.claude/scripts/ask_gpt.py (Codex on Lainey's ChatGPT plan). GPT sees no other
copy, no guide text and no project context. Its answer is saved untouched as raw_gpt/<folio>.response.txt; the
"NN<tab>text" lines read from it are written to raw_gpt/<folio>.txt for scripts/key_diff.py. Pages already done are
skipped.
Usage: python scripts/key_gpt.py [--set kells_extra] [folio ...]
"""
import csv
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config" / "paths.yaml").read_text())
KEY = ROOT / CFG["data_dir"] / "kells_key"
ASK = Path.home() / ".claude" / "scripts" / "ask_gpt.py"


def main():
    global KEY
    args = sys.argv[1:]
    if "--set" in args:
        k = args.index("--set")
        KEY, args = KEY.with_name(args[k + 1]), args[:k] + args[k + 2:]
    folios = args or [r["folio"] for r in csv.DictReader(open(KEY / "sample.csv"))]
    prompt = (ROOT / "config" / "key_prompt_gpt.txt").read_text()
    out = KEY / "raw_gpt"
    out.mkdir(parents=True, exist_ok=True)
    for folio in folios:
        if (out / f"{folio}.txt").exists():
            continue
        images = sorted((KEY / "lines" / folio).glob("*.png"))
        cmd = [sys.executable, str(ASK), "--effort", "high", "--no-log"]
        for im in images:
            cmd += ["-i", str(im.resolve())]
        result = subprocess.run(cmd + [prompt], capture_output=True, text=True)
        (out / f"{folio}.response.txt").write_text(result.stdout + ("\n" + result.stderr if result.returncode else ""))
        lines = {int(m.group(1)): m.group(2).strip()
                 for m in re.finditer(r"^\s*(\d{1,2})[\t ]+(.*)$|^\s*(\d{1,2})\s*$", result.stdout, re.M) if m.group(1)}
        if result.returncode or len(lines) < len(images) // 2:
            print(f"{folio}: GPT call failed or answered {len(lines)} of {len(images)} lines; see {folio}.response.txt")
            continue
        (out / f"{folio}.txt").write_text("".join(f"{n:02d}\t{lines.get(n, '')}\n" for n in range(1, len(images) + 1)))
        print(f"{folio}: {len(lines)} of {len(images)} lines typed")


if __name__ == "__main__":
    main()
