"""Tests of scripts/tables.py on a made-up run: rates come from the error and character totals, and a block that no
longer matches the record is caught. Usage: python scripts/test_tables.py"""
import csv
import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tables  # noqa: E402

FIELDS = ["scope", "name", "zone", "role", "err_sp", "n_sp", "err", "n", "cer_spaces", "cer", "key_md5"]


def write_scores(path, role, rows, key="k"):
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for scope, name, zone, err_sp, n_sp in rows:
            # cer_spaces holds a rounded rate that disagrees at one decimal: the table must not use it
            w.writerow({"scope": scope, "name": name, "zone": zone, "role": role, "err_sp": err_sp, "n_sp": n_sp,
                        "err": err_sp // 2, "n": n_sp, "cer_spaces": 0.0561, "cer": 0.0, "key_md5": key})


def main():
    with tempfile.TemporaryDirectory(dir=tables.ROOT) as tmp:
        run = Path(tmp).relative_to(tables.ROOT)
        rows = [("page", "p1", z, 50, 901) for z in "ABCD"] + [("zone", z, z, 50, 901) for z in "ABCD"]
        for role in ("tune", "test"):
            write_scores(Path(tmp) / f"stgall_{role}.csv", role, rows + [("all", "all", "", 200, 3604)])
        assert tables.make(f"key | {run}").splitlines()[2] == (
            "| tune (8) | 5.5% | 5.5% | 5.5% | 5.5% | 5.5% | 2.8% | 3,604 |")   # 50/901 is 5.549%, not 5.6%
        for setting, err in (("plain", "0.0488"), ("freeze", "0.0500")):
            (Path(tmp) / f"passes_{setting}.csv").write_text(
                f"pass,fold1_trained_err,fold2_trained_err,mean_err\n22,0,0,{err}\n36,0,0,{err}\n")
        (Path(tmp) / "chosen.json").write_text(json.dumps(
            {"setting": "plain", "settings": {"plain": {"passes": 36}, "freeze": {"passes": 22}}}))
        assert tables.two_fold(run, "plain") == "4.88% (36 passes)"         # the passes the run chose
        write_scores(Path(tmp) / "stgall_test.csv", "test", rows + [("all", "all", "", 200, 3604)], key="k2")
        try:                                                                 # tune and test scored against two keys
            tables.make(f"key | {run}")
            raise AssertionError("two versions of the key in one table passed")
        except SystemExit:
            pass
        write_scores(Path(tmp) / "stgall_test.csv", "test", rows + [("all", "all", "", 200, 3604)])
        notes = Path(tmp) / "notes.md"
        notes.write_text(f"text\n<!-- make tables: key | {run} -->\nold\n<!-- end -->\nmore\n")
        cmd = [sys.executable, str(tables.ROOT / "scripts" / "tables.py"), str(notes)]
        assert subprocess.run(cmd, capture_output=True).returncode == 1     # a stale block fails
        assert subprocess.run(cmd + ["--write"], capture_output=True).returncode == 0
        assert subprocess.run(cmd, capture_output=True).returncode == 0     # and matches once made again
        assert notes.read_text().startswith("text\n<!-- make tables:") and notes.read_text().endswith("end -->\nmore\n")
    print("tables: 7 checks pass")


if __name__ == "__main__":
    main()
