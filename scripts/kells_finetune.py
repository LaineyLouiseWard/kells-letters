"""Fine-tune Kraken's St Gall reader on the Kells tune pages, inside one run's folder.

The run folder (data/runs/<run>/, from the Makefile) holds the St Gall model (stgall/best.safetensors) and the run's
own copy of the answer key (key/, scripts/key_snapshot.py), whose fold1, fold2 and tune_train lines are cut once into
Kraken's binary format (`ketos compile`), as Kraken's training manual recommends for speed.
1. Two folds (fold1 and fold2: the first and the second tune page of each zone): train on one fold from the St Gall
   model for PASSES passes (`ketos train --load`, `--resize union`, a fixed number of passes), measured after every
   pass on the other fold's lines.
2. The number of passes with the lowest error averaged over the two folds (on a tie, the fewer passes). Both folds
   must report every pass from 1 to PASSES.
3. All 8 tune pages trained for that many passes; the model after the last pass is final.safetensors.
The measure that chooses is Kraken's own: after each pass it logs `val_metric`, its character accuracy on the
validation lines (1 - CER, spaces counted; kraken/train/vgsl.py), to the run's tensorboard log, and the error here is
1 minus it. Lines holding `?` carry no text in the training files, so they are neither trained on nor measured, and
`#` is left out of the text (scripts/key_xml.py). The reported error is scripts/score.py's instead, on the reference
text with `?` and `#` as masks. The test pages play no part here.
Kraken keeps only the 10 best checkpoints by val_metric (save_top_k=10 in kraken/ketos/recognition.py). Measured on
its own training lines, the final run's metric ties near 1.0, so the last pass's checkpoint could be dropped: the final
run is measured only after its last pass (`-F N`), so that checkpoint is the one kept.
With --freeze, every layer but the output layer is kept fixed for the first FREEZE_PASSES passes' worth of lines
(`--freeze-backbone`, which Kraken's training manual suggests for small sets, against forgetting what the model knew).
Outputs: data/runs/<run>/kells/<setting>/ (setting plain or freeze): fold1/, fold2/ and all/ (checkpoints, logs) and
final.safetensors; the record: results/<run>/passes_<setting>.csv (error per pass and fold).
--choose: the setting with the lower two-fold error becomes the run's final model, data/runs/<run>/kells/
final.safetensors, recorded in results/<run>/chosen.json. The settings are compared at 4 decimals and a tie goes to
no freezing, as kells_compare.sh did (removed after commit e5169a9); passes are chosen on the unrounded errors, as before, and the record
keeps them unrounded, so both choices can be made again from it.
--page re-cuts the lines from the page images on every pass (`-f page`), the method of the first run
(data/models/kells_page/); on 3 passes the two differ by up to 0.9 points at pass 1 and match by pass 3.
A run whose key copy holds the extra training pages (key_snapshot.py --extra) trains each fold on fold<k>_train (its
pages plus the extra pages) and the final model on tune_train (tune and extra pages); the folds are measured on tune
pages only, as before.
--choose --settings plain: choose among the named settings only (PP-OCRv6 has no freezing: --freeze-backbone is
Kraken's classic reader's option).
--passes N (at most PASSES) for test runs; --folds-only stops after the folds; --final-only trains the final model
from the setting's passes_<setting>.csv; --record names another folder for the record (test runs).
Usage: python scripts/kells_finetune.py RUN_DIR [--freeze] [--page] [--passes N] [--folds-only | --final-only]
       python scripts/kells_finetune.py RUN_DIR --choose
"""
import argparse
import csv
import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score import lines_of  # noqa: E402
from stamp import commit, md5  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config" / "paths.yaml").read_text())
PASSES = CFG["KELLS_PASSES"]
FREEZE_PASSES = CFG["FREEZE_PASSES"]
SETTINGS = ("plain", "freeze")  # in this order, so that a tie goes to no freezing
KETOS = str(Path(sys.executable).with_name("ketos"))


def lines_with_text(xml_list):
    """Lines with text in the PageXML files a list names (paths relative to the repository root)."""
    return sum(1 for p in Path(xml_list).read_text().split() for t in lines_of(ROOT / p).values() if t)


def train(out, train_lst, eval_lst, passes, model, fmt="binary", freeze_lines=0, last_only=False):
    """One training run from model for a fixed number of passes, into out (emptied first)."""
    shutil.rmtree(out, ignore_errors=True)
    (out / "logs").mkdir(parents=True)
    opts = ["-F", str(passes)] if last_only else []
    opts += ["--freeze-backbone", str(freeze_lines)] if freeze_lines else []
    cmd = [KETOS, "-d", "cuda:0", "--workers", "4", "-s", str(CFG["SEED"]), "-r", "train", *opts, "-f", fmt,
           "-i", str(model), "--resize", "union", "-B", "16", "-q", "fixed", "-N", str(passes),
           "-o", str(out), "--logger", "tensorboard", "--log-dir", str(out / "logs"),
           "-t", str(train_lst), "-e", str(eval_lst)]
    print(" ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=ROOT, stdout=subprocess.DEVNULL)
    return out


def errors(out):
    """Pass (1-based) -> 1 - val_metric, Kraken's character error on the validation lines after that pass, from the
    run's tensorboard log (each val_metric is matched to the epoch logged at the same step; Kraken counts from 0)."""
    runs = sorted((out / "logs").rglob("events.out.tfevents.*"), key=lambda p: p.stat().st_mtime)
    ea = EventAccumulator(str(runs[-1].parent))
    ea.Reload()
    epoch = {e.step: int(e.value) for e in ea.Scalars("epoch")}
    return {epoch[v.step] + 1: 1 - v.value for v in ea.Scalars("val_metric")}


def two_fold(folds, passes):
    """Pass -> error averaged over the two folds; both folds must report every pass from 1 to passes."""
    want = list(range(1, passes + 1))
    for fold, errs in folds.items():
        if sorted(errs) != want:
            sys.exit(f"{fold} reported passes {sorted(errs)}, not 1 to {passes}")
    return {k: (folds["fold1"][k] + folds["fold2"][k]) / 2 for k in want}


def choose(mean):
    """The pass with the lowest error; on a tie, the fewer passes."""
    return min(mean, key=lambda k: (mean[k], k))


def last_checkpoint(out, passes):
    """The checkpoint saved after pass `passes`: Kraken names it checkpoint_{epoch:02d}-{val_metric:.4f}.ckpt."""
    found = [p for p in out.glob("checkpoint_*.ckpt") if p.name.startswith(f"checkpoint_{passes - 1:02d}-")]
    if len(found) != 1:
        sys.exit(f"the checkpoint after pass {passes} was not kept in {out}")
    return found[0]


def read_passes(path):
    return {int(r["pass"]): float(r["mean_err"]) for r in csv.DictReader(open(path))}


def choose_setting(run, record, settings=SETTINGS):
    """The setting with the lower two-fold error becomes the run's final model."""
    best = {}
    for s in settings:
        mean = read_passes(record / f"passes_{s}.csv")
        best[s] = {"passes": choose(mean), "two_fold_error": mean[choose(mean)]}
    setting = min(settings, key=lambda s: round(best[s]["two_fold_error"], 4))
    final = run / "kells" / "final.safetensors"
    shutil.copyfile(run / "kells" / setting / "final.safetensors", final)
    chosen = {"setting": setting, "settings": best, "model_md5": md5(final),
              "stgall_model_md5": md5(run / "stgall" / "best.safetensors"),
              "key_md5": json.load(open(run / "key" / "key.json"))["adjudication_md5"], "commit": commit()}
    (record / "chosen.json").write_text(json.dumps(chosen, indent=1) + "\n")
    told = ", ".join(f"{s} {b['two_fold_error']:.2%} at pass {b['passes']}" for s, b in best.items())
    print(f"chosen: {setting} ({told})")


def main():
    ap = argparse.ArgumentParser(description="Kells fine-tuning inside one run folder; see the docstring.")
    ap.add_argument("run", type=Path)
    ap.add_argument("--freeze", action="store_true")
    ap.add_argument("--page", action="store_true")
    ap.add_argument("--passes", type=int, default=PASSES)
    ap.add_argument("--record", type=Path)
    only = ap.add_mutually_exclusive_group()
    only.add_argument("--folds-only", action="store_true")
    only.add_argument("--final-only", action="store_true")
    only.add_argument("--choose", action="store_true")
    ap.add_argument("--settings", nargs="+", choices=SETTINGS, default=list(SETTINGS))
    a = ap.parse_args()
    if not 1 <= a.passes <= PASSES:
        sys.exit(f"--passes {a.passes}: the plan allows 1 to {PASSES}")
    run = a.run if a.run.is_absolute() else ROOT / a.run
    record = a.record or ROOT / CFG["results"] / run.name
    record.mkdir(parents=True, exist_ok=True)
    if a.choose:
        return choose_setting(run, record, [s for s in SETTINGS if s in a.settings])
    setting = "freeze" if a.freeze else "plain"
    out, key, model = run / "kells" / setting, run / "key", run / "stgall" / "best.safetensors"
    fmt = "page" if a.page else "binary"

    def data(name):
        return key / (f"{name}.lst" if a.page else f"{name}.arrow.lst")

    def freeze_lines(name):
        return FREEZE_PASSES * lines_with_text(key / f"{name}.lst") if a.freeze else 0

    passes_csv = record / f"passes_{setting}.csv"
    if a.final_only:
        mean = read_passes(passes_csv)
    else:
        folds = {}
        for t, e in (("fold1", "fold2"), ("fold2", "fold1")):
            tr = f"{t}_train" if (key / f"{t}_train.lst").exists() else t  # with the extra pages (key_snapshot --extra)
            folds[t] = errors(train(out / t, data(tr), data(e), a.passes, model, fmt, freeze_lines(tr)))
        # unrounded, so the choice is made again exactly from the record (passes 22 and 36 of the 3 Nov 1.5.0 run with
        # freezing tie at 4 decimals; the unrounded errors chose 36)
        mean = two_fold(folds, a.passes)
        with open(passes_csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["pass", "fold1_trained_err", "fold2_trained_err", "mean_err"])
            for k in mean:
                w.writerow([k, folds["fold1"][k], folds["fold2"][k], mean[k]])
    best = choose(mean)
    print(f"{setting}: passes chosen {best} (two-fold error {mean[best]:.2%})")
    if a.folds_only:
        return
    train(out / "all", data("tune_train"), data("tune_train"), best, model, fmt, freeze_lines("tune_train"),
          last_only=True)
    from kraken.models.convert import convert_models
    convert_models([str(last_checkpoint(out / "all", best))], out / "final.safetensors", weights_format="safetensors")
    print(f"final model: {out / 'final.safetensors'}")


if __name__ == "__main__":
    main()
