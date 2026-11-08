"""Fine-tune party's St Gall model on the Kells tune pages, inside one run's folder, as
scripts/kells_finetune.py does for Kraken: the same folds, records and choice.

party's own `val_metric` is a validation loss, not a character error (party/model.py, on_validation_epoch_end), so the
passes are chosen by character error instead. Training is built here from party's own classes (its configs, data module
and model, as party/cli/train.py builds them, with party's defaults for every setting not named below) and Lightning's
Trainer, whose checkpoint callback keeps the weights after every pass (party's command line keeps only the 10 lowest
losses). Each pass's checkpoint is converted to a weights file (Kraken 7.1.1 reads no checkpoints), which reads the
other fold's pages (`party ocr`, scripts/read_pages.py), scripts/score.py's measure is taken on them (spaces counted,
`?` and `#` as masks), pooled over the fold's characters, and both files are deleted once read.
Learning rate: constant at party's default rate, no warm-up, as Kraken's defaults (kraken/configs/base.py) are, which
its Kells fine-tuning used. party's defaults (cosine over 32 passes, 1000 warm-up steps) assume a large set: a Kells
fold gives about 4 weight updates a pass (267 lines, batches of 16, gradients accumulated over 4), so 50 passes would
end inside the warm-up. party never reads its `schedule` setting and always anneals by a cosine (party/model.py,
configure_optimizers), which past 32 passes climbs again; the cosine's floor (`cos_min_lr`) set to its starting rate
keeps the rate constant. Constant, the final model trained for the chosen number of passes takes the same path as the
folds did up to that pass.
With --freeze, party's encoder and adapter are kept fixed throughout (`--freeze-encoder`; party/model.py, setup).
Outputs: data/runs/<run>/kells/<setting>/ (fold1/, fold2/, all/, final.safetensors); the record:
results/<run>/passes_<setting>.csv. --choose, --folds-only, --final-only, --passes and --record as in kells_finetune.py.
Usage: python scripts/party_finetune.py RUN_DIR [--freeze] [--passes N] [--folds-only | --final-only | --choose]
"""
import argparse
import csv
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import party_cli  # noqa: E402,F401  (Kraken's conversion knows party's model)
from kells_finetune import CFG, PASSES, ROOT, SETTINGS, choose, choose_setting, read_passes, two_fold  # noqa: E402
from read_pages import read_cmd, unread  # noqa: E402
from score import lines_of, score_page  # noqa: E402

PARTY = str(Path(sys.executable).with_name("party"))


def compiled(lst):
    """party's compiled lines of the pages a list names (`party compile`, cut once, as for Kraken)."""
    arrow = lst.with_suffix(".party.arrow")
    if not arrow.exists():
        subprocess.run([PARTY, "compile", "-o", str(arrow), "-F", str(lst)], check=True, cwd=ROOT,
                       stdout=subprocess.DEVNULL)
    return arrow


def train(out, train_lst, eval_lst, passes, model, freeze=False):
    """One training run from model for a fixed number of passes, into out (emptied first), with a checkpoint (weights
    only) after every pass: checkpoint_<pass - 1>.ckpt, as Lightning counts passes from 0. The Trainer's arguments are
    those of party/cli/train.py for `party -d cuda:0 --precision bf16-mixed -r train -q fixed`."""
    import torch
    from lightning.pytorch import Trainer, seed_everything
    from lightning.pytorch.callbacks import ModelCheckpoint
    from party.configs import PartyRecognitionTrainingConfig, PartyRecognitionTrainingDataConfig
    from party.model import PartyRecognitionModel, PartyTextLineDataModule

    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    lrate = PartyRecognitionTrainingConfig().lrate
    settings = {"training_data": [str(compiled(train_lst))], "evaluation_data": [str(compiled(eval_lst))],
                "prompt_mode": "curves", "num_workers": 4, "precision": "bf16-mixed", "quit": "fixed",
                "epochs": passes, "lrate": lrate, "cos_min_lr": lrate, "warmup": 0, "freeze_encoder": freeze}
    print(f"party training {out}: {settings}", flush=True)
    seed_everything(CFG["SEED"], workers=True)
    torch.set_float32_matmul_precision("high")
    config = PartyRecognitionTrainingConfig(**settings)
    data = PartyTextLineDataModule(PartyRecognitionTrainingDataConfig(**settings))
    every_pass = ModelCheckpoint(dirpath=out, filename="checkpoint_{epoch:02d}", auto_insert_metric_name=False,
                                 save_top_k=-1, save_weights_only=True)
    trainer = Trainer(accelerator="gpu", devices=1, precision="bf16-mixed", deterministic="warn",
                      use_distributed_sampler=False, max_epochs=passes, val_check_interval=1.0,
                      accumulate_grad_batches=config.accumulate_grad_batches,
                      gradient_clip_val=config.gradient_clip_val, num_sanity_val_steps=0, logger=False,
                      callbacks=[every_pass], enable_progress_bar=False)
    with trainer.init_module(empty_init=True):
        net = PartyRecognitionModel.load_from_weights(str(model), config=config)
    trainer.fit(net, data)
    del trainer, net, data
    torch.cuda.empty_cache()  # the GPU is free for `party ocr`, which reads the passes next
    return out


def checkpoint(out, k):
    """The checkpoint saved after pass k."""
    ck = out / f"checkpoint_{k - 1:02d}.ckpt"
    if not ck.exists():
        sys.exit(f"no checkpoint after pass {k} in {out}")
    return ck


def errors(out, eval_lst, passes):
    """Pass -> character error on the eval list's pages, read by that pass's checkpoint as a weights file (both deleted
    once read). The pages read and scored are the key copy's own (KEY/<folio>.xml, `?` and `#` kept as masks), not the
    training copies the list names (KEY/train/, where those lines carry no text)."""
    from kraken.models.convert import convert_models
    pages = [eval_lst.parent / Path(p).name for p in eval_lst.read_text().split()]
    errs = {}
    for k in range(1, passes + 1):
        ck, read = checkpoint(out, k), out / "read" / f"pass{k:02d}"
        weights = convert_models([str(ck)], ck.with_suffix(".safetensors"), weights_format="safetensors")
        read.mkdir(parents=True)
        pairs = [(p.absolute(), (read / p.name).absolute()) for p in pages]
        r = subprocess.run(read_cmd(weights, pairs, party=True), stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                           text=True)
        if r.returncode or unread(pairs):
            sys.exit(f"party did not read every line of {' '.join(unread(pairs))} with {ck} (exit {r.returncode}); "
                     f"its last messages:\n{r.stderr[-3000:]}")
        t = [score_page(lines_of(src), lines_of(dst)) for src, dst in pairs]
        errs[k] = sum(x["err_sp"] for x in t) / sum(x["n_sp"] for x in t)
        ck.unlink()
        Path(weights).unlink()
        print(f"{out.name} pass {k}: {errs[k]:.2%}", flush=True)
    return errs


def main():
    ap = argparse.ArgumentParser(description="party's Kells fine-tuning inside one run folder; see the docstring.")
    ap.add_argument("run", type=Path)
    ap.add_argument("--freeze", action="store_true")
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
    passes_csv = record / f"passes_{setting}.csv"
    if a.final_only:
        mean = read_passes(passes_csv)
    else:
        folds = {}
        for t, e in (("fold1", "fold2"), ("fold2", "fold1")):
            tr = f"{t}_train" if (key / f"{t}_train.lst").exists() else t  # with the extra pages
            folds[t] = errors(train(out / t, key / f"{tr}.lst", key / f"{e}.lst", a.passes, model, a.freeze),
                              key / f"{e}.lst", a.passes)
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
    final = train(out / "all", key / "tune_train.lst", key / "tune_train.lst", best, model, a.freeze)
    from kraken.models.convert import convert_models
    convert_models([str(checkpoint(final, best))], out / "final.safetensors", weights_format="safetensors")
    for ck in final.glob("checkpoint_*.ckpt"):
        ck.unlink()
    print(f"final model: {out / 'final.safetensors'}")


if __name__ == "__main__":
    main()
