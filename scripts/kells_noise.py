"""Run-to-run noise of Kells fine-tuning: the same short fold run (fold1 trained, fold2 measured) repeated with the same
seed, without and with Kraken's deterministic mode (`ketos -r`), and the largest gap between repeats at any pass.

Inputs: a run folder's copy of the key (data/runs/<run>/key/) and a St Gall model (--model, by default the run's
stgall/best.safetensors). Short runs only (a test run). Output: one line per repeat (seconds, seconds a pass after
the first measure, error per pass) and the largest gap; with --out, the same as CSV.
Usage: python scripts/kells_noise.py RUN_DIR [--model M] [--passes 10] [--repeats 2] [--out file.csv]
"""
import argparse
import csv
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kells_finetune as kf  # noqa: E402


def once(out, key, model, passes, deterministic):
    (out / "logs").mkdir(parents=True)
    cmd = [kf.KETOS, "-d", "cuda:0", "--workers", "4", "-s", str(kf.CFG["SEED"]), *(["-r"] if deterministic else []),
           "train", "-f", "binary", "-i", str(model), "--resize", "union", "-B", "16", "-q", "fixed",
           "-N", str(passes), "-o", str(out), "--logger", "tensorboard", "--log-dir", str(out / "logs"),
           "-t", str(key / "fold1.arrow.lst"), "-e", str(key / "fold2.arrow.lst")]
    start = time.time()
    subprocess.run(cmd, check=True, cwd=kf.ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    seconds = time.time() - start
    ea = EventAccumulator(str(next((out / "logs").rglob("events.out.tfevents.*")).parent))
    ea.Reload()
    wall = [e.wall_time for e in ea.Scalars("val_metric")]
    return seconds, (wall[-1] - wall[0]) / max(1, len(wall) - 1), kf.errors(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run", type=Path)
    ap.add_argument("--model", type=Path)
    ap.add_argument("--passes", type=int, default=10)
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    run = a.run if a.run.is_absolute() else kf.ROOT / a.run
    model = a.model or run / "stgall" / "best.safetensors"
    rows = []
    with tempfile.TemporaryDirectory(dir=run) as tmp:
        for deterministic in (False, True):
            errs = []
            for k in range(a.repeats):
                seconds, per_pass, err = once(Path(tmp) / f"{int(deterministic)}_{k}", run / "key", model, a.passes,
                                              deterministic)
                errs.append(err)
                rows.append([int(deterministic), k + 1, round(seconds, 1), round(per_pass, 2),
                             *(round(err[p], 4) for p in sorted(err))])
                print(f"deterministic {deterministic}, repeat {k + 1}: {seconds:.1f} s, {per_pass:.2f} s a pass; "
                      + " ".join(f"{err[p]:.4f}" for p in sorted(err)), flush=True)
            gap = max(max(e[p] for e in errs) - min(e[p] for e in errs) for p in errs[0])
            print(f"deterministic {deterministic}: largest gap between repeats {100 * gap:.2f} points")
    if a.out:
        with open(a.out, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["deterministic", "repeat", "seconds", "seconds_a_pass",
                        *(f"pass{p}" for p in range(1, a.passes + 1))])
            w.writerows(rows)


if __name__ == "__main__":
    main()
