"""Blind second look at doubtful words of one Kells key page: GPT types the letters of word crops it sees alone.

Each crop is a stretch of one line image, given as n:x0:x1 (line number, pixel range). GPT gets only the crops and
config/tie_prompt_gpt.txt (Codex on Lainey's ChatGPT plan, high effort, through ~/.claude/scripts/ask_gpt.py): no
line text, no other copy, no guide. Crops: data/kells_key/tie/<folio>/NN.png (never released); the crop list and
GPT's untouched answer: data/kells_key/tie/<folio>.txt. The main chat then settles each word against the image; a
letter still unsure is `?`. --set kells_extra looks at the extra training pages
(data/kells_extra/).
Usage: python scripts/key_tie.py [--set NAME] folio n:x0:x1 [n:x0:x1 ...]
"""
import subprocess
import sys
from pathlib import Path

import yaml
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config" / "paths.yaml").read_text())
DATA = ROOT / CFG["data_dir"]
ASK = Path.home() / ".claude" / "scripts" / "ask_gpt.py"


def main():
    args = sys.argv[1:]
    name = "kells_key"
    if args[:1] == ["--set"]:
        name, args = args[1], args[2:]
    KEY = DATA / name
    folio, specs = args[0], args[1:]
    out = KEY / "tie" / folio
    out.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(ASK), "--effort", "high", "--no-log"]
    listing = []
    for k, spec in enumerate(specs, 1):
        n, x0, x1 = (int(v) for v in spec.split(":"))
        im = Image.open(KEY / "lines" / folio / f"{n:02d}.png").convert("L")
        im.crop((x0, 0, min(x1, im.size[0]), im.size[1])).save(out / f"{k:02d}.png")
        cmd += ["-i", str((out / f"{k:02d}.png").resolve())]
        listing.append(f"{k:02d}\tline {n}\tx {x0}-{x1}")
    prompt = (ROOT / "config" / "tie_prompt_gpt.txt").read_text()
    result = subprocess.run(cmd + [prompt], capture_output=True, text=True)
    text = "\n".join(listing) + "\n\nGPT:\n" + result.stdout + (("\n" + result.stderr) if result.returncode else "")
    (KEY / "tie" / f"{folio}.txt").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
