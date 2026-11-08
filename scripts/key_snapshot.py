"""Take a run's own copy of the Kells answer key at its start, so a key edited during the run cannot reach it.

Into OUT_DIR (data/runs/<run>/key/, from the Makefile) it writes:
- <folio>.xml: the reference PageXML of each page of data/kells_key/sample.csv (from data/xml/kells_key/, written by
  scripts/key_xml.py), and train/<folio>.xml for the tune pages, each with its image path rewritten for the new folder;
- sample.csv, and tune.lst, test.lst, fold1.lst, fold2.lst and tune_train.lst: key_xml.py's lists, pointing at the
  copies by paths relative to the repository root, so the copy also works on Sonic;
- <list>.arrow and <list>.arrow.lst for fold1, fold2 and tune_train: their lines cut once into Kraken's binary format
  (`ketos compile`), which fine-tuning reads;
- key.json: the md5 of adjudication.csv, lines.csv and sample.csv as read, of the reference text, and the commit.
Gates, on the copies, so what is tested is what the run keeps: every reference line holds exactly its settled text in
the adjudication.csv that was read (matched through lines.csv's line ids), and every train/ line the training text
(`#` left out, a line holding `?` empty); otherwise data/xml/kells_key/ is out of date and the script stops (run make
key-xml). Each list names exactly the pages its role in sample.csv gives (fold1 the first and fold2 the second tune
page of each zone, as key_xml.py draws them), so no test page can reach training. After compiling, each binary dataset
holds as many lines as its list has lines with text. A folder that already holds key.json is kept as it is.
--extra adds the extra training pages (data/kells_extra/, written by key_xml.py --set kells_extra) under extra/, under
the same gates: each fold trains on its own pages plus every extra page (fold1_train, fold2_train, also compiled) and
is still measured on the other fold's tune pages alone (fold1, fold2); tune_train holds the tune and the extra pages.
Usage: python scripts/key_snapshot.py OUT_DIR [--extra]   (OUT_DIR relative to the repository root)
"""
import csv
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pyarrow.ipc
import yaml
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score import lines_of  # noqa: E402
from stamp import commit  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CFG = yaml.safe_load((ROOT / "config" / "paths.yaml").read_text())
DATA = ROOT / CFG["data_dir"]
KEY = DATA / "kells_key"
XML = DATA / CFG["xml"] / "kells_key"
EXTRA = DATA / "kells_extra"
EXTRA_XML = DATA / CFG["xml"] / "kells_extra"
LISTS = ("tune", "test", "fold1", "fold2", "tune_train")
COMPILED = ("fold1", "fold2", "tune_train")
KETOS = str(Path(sys.executable).with_name("ketos"))


def read(path):
    """A file's bytes and their md5, so the file that is tested is the file that is recorded."""
    data = path.read_bytes()
    return data, hashlib.md5(data).hexdigest()


def rows(data):
    return list(csv.DictReader(io.StringIO(data.decode("utf-8"))))


def train_text(text):
    """The training text of a settled line, by scripts/key_xml.py's rule."""
    return "" if "?" in text else " ".join(text.replace("#", " ").split())


def out_of_date(sample, adjudication, lines, xml=XML):
    """Lines of the key's PageXML whose text is not the settled text, as 'folio:n: why'."""
    settled = {(r["folio"], int(r["n"])): r for r in adjudication}
    bad = []
    for page in sample:
        folio = page["folio"]
        ids = {int(r["n"]): r["kraken_id"] for r in lines if r["folio"] == folio}
        ref = lines_of(xml / f"{folio}.xml")
        train = lines_of(xml / "train" / f"{folio}.xml") if page["role"] in ("tune", "extra") else None
        if set(ref) != set(ids.values()) or (train is not None and set(train) != set(ids.values())):
            bad.append(f"{folio}: its lines are not lines.csv's")
            continue
        for n, lid in sorted(ids.items()):
            r = settled.get((folio, n))
            if r is None or (not r["decision"] and (r["claude"] or r["gpt"])):
                bad.append(f"{folio}:{n}: not settled")
                continue
            want = "" if r["decision"] == "<none>" else r["decision"]
            if ref[lid] != want:
                bad.append(f"{folio}:{n}: reference {ref[lid]!r}, settled {want!r}")
            if train is not None and train[lid] != train_text(want):
                bad.append(f"{folio}:{n}: training text {train[lid]!r}, by the rule {train_text(want)!r}")
    return bad


def expected_lists(sample):
    """List name -> the (folder, folio) pairs it must hold: '' for a reference file, 'train' for a training file."""
    want = {name: [] for name in LISTS}
    seen = set()
    for r in sample:
        if r["role"] == "test":
            want["test"].append(("", r["folio"]))
        elif r["role"] == "tune":
            want["tune"].append(("", r["folio"]))
            want["tune_train"].append(("train", r["folio"]))
            want["fold2" if r["zone"] in seen else "fold1"].append(("train", r["folio"]))
            seen.add(r["zone"])
    return want


def with_extra(want, extra_sample):
    """The lists with the extra training pages added to training only: the folds are still measured on tune pages."""
    extra = [("extra/train", r["folio"]) for r in extra_sample]
    return {**want, "fold1_train": want["fold1"] + extra, "fold2_train": want["fold2"] + extra,
            "tune_train": want["tune_train"] + extra}


def wrong_lists(sample, xml=XML):
    """Lists of key_xml.py that do not hold exactly the pages their role gives."""
    bad = []
    for name, want in expected_lists(sample).items():
        listed = [Path(p) for p in (xml / f"{name}.lst").read_text().split()]
        got = [("train" if p.parent.name == "train" else "", p.stem) for p in listed]
        if sorted(got) != sorted(want) or len(set(got)) != len(got):
            bad.append(name)
    return bad


def copy_xml(src, dst):
    """Copy a PageXML file, its image path made relative to the new folder."""
    tree = etree.parse(str(src))
    page = tree.getroot().find("{*}Page")
    image = os.path.normpath(os.path.join(src.parent, page.get("imageFilename")))
    page.set("imageFilename", os.path.relpath(image, dst.parent))
    dst.parent.mkdir(parents=True, exist_ok=True)
    tree.write(str(dst), xml_declaration=True, encoding="UTF-8", pretty_print=True)


def text_md5(folder, folios):
    """md5 of the reference text (folio, line id, text), whatever else the files hold."""
    h = hashlib.md5()
    for folio in folios:
        for lid, text in sorted(lines_of(folder / f"{folio}.xml").items()):
            h.update(f"{folio}\t{lid}\t{text}\n".encode("utf-8"))
    return h.hexdigest()


def main():
    out, extra = Path(sys.argv[1]), sys.argv[2:] == ["--extra"]
    out = out if out.is_absolute() else ROOT / out
    final = out.relative_to(ROOT)  # before anything is written: ketos reads the lists from the repository root
    if (out / "key.json").exists():
        print(f"{out / 'key.json'} exists: the run keeps its copy of the key")
        return
    adjudication, adjudication_md5 = read(KEY / "adjudication.csv")
    lines, lines_md5 = read(KEY / "lines.csv")
    sample_bytes, sample_md5 = read(KEY / "sample.csv")
    sample = rows(sample_bytes)
    wrong = wrong_lists(sample)
    if wrong:
        sys.exit(f"data/xml/kells_key/ lists that do not hold the pages of their role in sample.csv: {' '.join(wrong)}")
    if extra:
        extra_adj, extra_adj_md5 = read(EXTRA / "adjudication.csv")
        extra_lines, extra_lines_md5 = read(EXTRA / "lines.csv")
        extra_bytes, extra_sample_md5 = read(EXTRA / "sample.csv")
        extra_sample = rows(extra_bytes)
        key_pages = {r["folio"] for r in sample}
        if {r["role"] for r in extra_sample} != {"extra"} or key_pages & {r["folio"] for r in extra_sample}:
            sys.exit("data/kells_extra/sample.csv: every page must have role extra and none may be a key page")
    part = out.with_name(out.name + ".part")
    shutil.rmtree(part, ignore_errors=True)
    folios = {r["folio"]: r["role"] for r in sample}
    for folio, role in folios.items():
        copy_xml(XML / f"{folio}.xml", part / f"{folio}.xml")
        if role == "tune":
            copy_xml(XML / "train" / f"{folio}.xml", part / "train" / f"{folio}.xml")
    (part / "sample.csv").write_bytes(sample_bytes)
    bad = out_of_date(sample, rows(adjudication), rows(lines), part)
    if extra:
        for r in extra_sample:
            copy_xml(EXTRA_XML / f"{r['folio']}.xml", part / "extra" / f"{r['folio']}.xml")
            copy_xml(EXTRA_XML / "train" / f"{r['folio']}.xml", part / "extra" / "train" / f"{r['folio']}.xml")
        (part / "extra" / "sample.csv").write_bytes(extra_bytes)
        bad += [f"extra {b}" for b in out_of_date(extra_sample, rows(extra_adj), rows(extra_lines), part / "extra")]
    if bad:
        shutil.rmtree(part)
        sys.exit(f"data/xml/kells_key/ (or kells_extra/) does not hold the settled key ({len(bad)} lines; run make "
                 f"key-xml, or key_xml.py --set kells_extra):\n  " + "\n  ".join(bad[:20]))
    lists = with_extra(expected_lists(sample), extra_sample) if extra else expected_lists(sample)
    for name, want in lists.items():
        (part / f"{name}.lst").write_text("".join(f"{final / sub / folio}.xml\n" for sub, folio in want))
    # ketos reads the lists' paths from the repository root, so the files must sit at their final paths while it
    # compiles: the folder is renamed first, and key.json, written last, marks the copy complete.
    if out.exists():
        shutil.rmtree(out)
    part.rename(out)
    start = time.time()
    for name in COMPILED + (("fold1_train", "fold2_train") if extra else ()):
        arrow = final / f"{name}.arrow"
        subprocess.run([KETOS, "--workers", str(CFG["kraken"]["workers"]), "compile", "-f", "page", "-o", str(arrow),
                        "-F", str(final / f"{name}.lst")], check=True, cwd=ROOT, stdout=subprocess.DEVNULL)
        compiled = pyarrow.ipc.open_file(pyarrow.memory_map(str(ROOT / arrow))).read_all().num_rows
        wanted = sum(1 for p in (out / f"{name}.lst").read_text().split() for t in lines_of(ROOT / p).values() if t)
        if compiled != wanted:
            sys.exit(f"{arrow}: {compiled} lines compiled, {wanted} lines with text in {name}.lst")
        (out / f"{name}.arrow.lst").write_text(f"{arrow}\n")
    record = {"adjudication_md5": adjudication_md5, "lines_md5": lines_md5, "sample_md5": sample_md5,
              "reference_text_md5": text_md5(out, folios), "pages": folios, "commit": commit(),
              **({"extra_adjudication_md5": extra_adj_md5, "extra_lines_md5": extra_lines_md5,
                  "extra_sample_md5": extra_sample_md5, "extra_pages": [r["folio"] for r in extra_sample]}
                 if extra else {}),
              "taken": time.strftime("%Y-%m-%d %H:%M:%S %z")}
    (out / "key.json").write_text(json.dumps(record, indent=1) + "\n")
    pages = f"{len(folios)} pages" + (f" and {len(extra_sample)} extra pages" if extra else "")
    print(f"{final}: {pages} copied, {len(COMPILED) + 2 * extra} lists compiled in {time.time() - start:.0f} s; "
          f"adjudication.csv md5 {adjudication_md5}")


if __name__ == "__main__":
    main()
