"""Read answer-key pages with a Kraken or party model, once, and record what read them.

Pages: those of one role (tune, test or all) in a run's copy of the key (scripts/key_snapshot.py). Kraken reads each
page's lines from its reference PageXML (`kraken -f page ... -x ocr`, BATCH lines at a time; 1, 16 and 64 read the
tune pages' text lines alike, and 16 was fastest). The pages are read into OUT_DIR.part, renamed OUT_DIR only when the
gates pass, so a failed reading leaves nothing that can pass for one; a folder that was read is never read again (the
test pages are read once by each final model).
Gates: Kraken reports success even when a page fails, so every page's output must exist and hold every line of its
input; and the model file must be the same before and after the reading.
Outputs in OUT_DIR: <folio>.xml, and read.json (model and its md5, the key copy and its adjudication.csv md5, pages,
command, commit, seconds).
--party reads with party instead (`party ocr -l M -x`, its own line prompts from the same PageXML lines).
Usage: python scripts/read_pages.py --model M --key KEY_DIR --role tune|test|all --out OUT_DIR [--batch N] [--party]
"""
import argparse
import csv
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score import lines_of  # noqa: E402
from stamp import commit, md5  # noqa: E402

KRAKEN = str(Path(sys.executable).with_name("kraken"))
PARTY = str(Path(sys.executable).with_name("party"))
BATCH = 16


def unread(pairs):
    """Pages whose output is missing or lacks lines of the input."""
    return [src.stem for src, dst in pairs if not dst.exists() or set(lines_of(dst)) != set(lines_of(src))]


def read_cmd(model, pairs, batch=BATCH, party=False):
    """The command that reads each (input PageXML, output PageXML) pair with model."""
    if party:
        cmd = [PARTY, "-d", "cuda:0", "--precision", "bf16-mixed", "ocr", "-l", str(Path(model).absolute()), "-x",
               "-B", str(batch)]
        for src, dst in pairs:
            cmd += ["-i", str(src), str(dst)]
        return cmd
    cmd = [KRAKEN, "-d", "cuda:0", "-f", "page"]
    for src, dst in pairs:
        cmd += ["-i", str(src), str(dst)]
    return cmd + ["-x", "ocr", "-B", str(batch), "-m", str(Path(model).absolute())]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", type=Path, required=True)
    ap.add_argument("--key", type=Path, required=True)
    ap.add_argument("--role", choices=["tune", "test", "all"], required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--batch", type=int, default=BATCH)
    ap.add_argument("--party", action="store_true")
    a = ap.parse_args()
    if a.out.exists():
        sys.exit(f"{a.out} was read already; each model reads the pages once (delete the folder to read again)")
    part = a.out.with_name(a.out.name + ".part")
    shutil.rmtree(part, ignore_errors=True)  # a reading that failed before
    folios = [r["folio"] for r in csv.DictReader(open(a.key / "sample.csv")) if a.role in ("all", r["role"])]
    pairs = [((a.key / f"{f}.xml").absolute(), (part / f"{f}.xml").absolute()) for f in folios]
    part.mkdir(parents=True)
    model_md5 = md5(a.model)
    cmd = read_cmd(a.model, pairs, a.batch, a.party)
    start = time.time()
    r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    seconds = round(time.time() - start, 1)
    failed = unread(pairs)
    if r.returncode or failed:  # party ocr logs a failed page and still exits 0 (party/cli/ocr.py)
        sys.exit(f"{'party' if a.party else 'Kraken'} did not read every line of {' '.join(failed)} "
                 f"(exit {r.returncode}); its last messages:\n{r.stderr[-3000:]}")
    if md5(a.model) != model_md5:
        sys.exit(f"{a.model} changed during the reading")
    key = json.load(open(a.key / "key.json"))
    record = {"model": str(a.model), "model_md5": model_md5, "key": str(a.key),
              "key_md5": key["adjudication_md5"], "role": a.role, "pages": folios, "batch": a.batch,
              "command": " ".join(cmd), "commit": commit(), "seconds": seconds}
    (part / "read.json").write_text(json.dumps(record, indent=1) + "\n")
    part.rename(a.out)
    print(f"{a.out}: {len(folios)} pages read in {seconds} s by {a.model} (md5 {record['model_md5']})")


if __name__ == "__main__":
    main()
