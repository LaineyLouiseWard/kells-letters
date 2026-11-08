"""Tests of scripts/kells_finetune.py: the pass and setting choices, and the two Kraken facts it relies on.

1. Kraken keeps only the 10 best checkpoints by val_metric, highest first, named checkpoint_{epoch:02d}-{metric}, and
   with -F N above 1 it measures every N-th pass only; val_metric is its character accuracy, 1 - CER. Read from
   Kraken's installed source, so a Kraken that changes either fails here.
2. The pass error is read from the tensorboard log by the epoch logged with each val_metric, so a pass that was not
   measured is missing, not filled by the next one.
Usage: python scripts/test_kells_finetune.py
"""
import csv
import json
import sys
import tempfile
from pathlib import Path

import kraken
from torch.utils.tensorboard import SummaryWriter

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kells_finetune as kf  # noqa: E402

SOURCE = Path(kraken.__file__).parent


def test_kraken_facts():
    rec = (SOURCE / "ketos" / "recognition.py").read_text()
    for fact in ("save_top_k=10", "monitor='val_metric'", "mode='max'",
                 "filename='checkpoint_{epoch:02d}-{val_metric:.4f}'",
                 "{'check_val_every_n_epoch': int(m_config.freq)}"):
        assert fact in rec, f"kraken/ketos/recognition.py no longer has {fact}"
    vgsl = (SOURCE / "train" / "vgsl.py").read_text()
    for fact in ("accuracy = 1.0 - self.val_cer.compute()", "self.log('val_metric', accuracy"):
        assert fact in vgsl, f"kraken/train/vgsl.py no longer has {fact}"


def test_errors_by_epoch(tmp):
    out = tmp / "fold1"
    w = SummaryWriter(str(out / "logs" / "lightning_logs" / "version_0"))
    for step, epoch, metric in ((3, 0, 0.90), (11, 2, 0.95)):  # passes 1 and 3 measured, pass 2 not
        w.add_scalar("epoch", epoch, step)
        w.add_scalar("val_metric", metric, step)
    w.close()
    got = kf.errors(out)
    assert sorted(got) == [1, 3] and abs(got[1] - 0.10) < 1e-6 and abs(got[3] - 0.05) < 1e-6, got


def test_choices(tmp):
    assert kf.choose({1: 0.1, 2: 0.05, 3: 0.05, 4: 0.06}) == 2             # lowest; a tie goes to fewer passes
    for name in ("checkpoint_00-0.9000.ckpt", "checkpoint_01-0.9500.ckpt"):
        (tmp / name).touch()
    assert kf.last_checkpoint(tmp, 2).name == "checkpoint_01-0.9500.ckpt"  # pass 2 is Kraken's epoch 1
    try:
        kf.last_checkpoint(tmp, 3)
        raise AssertionError("a missing checkpoint passed")
    except SystemExit:
        pass
    run, record = tmp / "run", tmp / "record"
    for part in ("kells/plain", "kells/freeze", "stgall", "key"):
        (run / part).mkdir(parents=True)
    (run / "kells" / "plain" / "final.safetensors").write_bytes(b"plain")
    (run / "kells" / "freeze" / "final.safetensors").write_bytes(b"freeze")
    (run / "stgall" / "best.safetensors").write_bytes(b"stgall")
    (run / "key" / "key.json").write_text(json.dumps({"adjudication_md5": "k"}))
    record.mkdir()
    assert kf.two_fold({"fold1": {1: 0.1, 2: 0.2}, "fold2": {1: 0.3, 2: 0.4}}, 2) == {1: 0.2, 2: 0.30000000000000004}
    try:
        kf.two_fold({"fold1": {1: 0.1, 2: 0.2}, "fold2": {2: 0.4}}, 2)            # fold2 lacks pass 1
        raise AssertionError("a fold with a pass missing passed")
    except SystemExit:
        pass
    xml = tmp / "xml"
    xml.mkdir()
    (xml / "a.xml").write_text('<p:PcGts xmlns:p="ns"><p:TextLine id="a"><p:TextEquiv><p:Unicode>et</p:Unicode>'
                               '</p:TextEquiv></p:TextLine><p:TextLine id="b"><p:TextEquiv><p:Unicode></p:Unicode>'
                               '</p:TextEquiv></p:TextLine></p:PcGts>')
    (xml / "a.lst").write_text(f"{xml / 'a.xml'}\n")
    assert kf.lines_with_text(xml / "a.lst") == 1                          # prefixed tags count, empty lines do not
    for errs, want in (((0.046, 0.046), "plain"), ((0.050, 0.046), "freeze"),  # a tie goes to no freezing,
                       ((0.044441, 0.044439), "plain")):                      # and a tie is at 4 decimals
        for setting, err in zip(kf.SETTINGS, errs):
            with open(record / f"passes_{setting}.csv", "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["pass", "fold1_trained_err", "fold2_trained_err", "mean_err"])
                w.writerows([[1, 0.1, 0.1, 0.1], [2, err, err, err]])
        kf.choose_setting(run, record)
        assert json.load(open(record / "chosen.json"))["setting"] == want
        assert (run / "kells" / "final.safetensors").read_bytes() == want.encode()


def main():
    test_kraken_facts()
    with tempfile.TemporaryDirectory() as tmp:
        test_errors_by_epoch(Path(tmp))
    with tempfile.TemporaryDirectory() as tmp:
        test_choices(Path(tmp))
    print("kells_finetune: 3 tests pass")


if __name__ == "__main__":
    main()
