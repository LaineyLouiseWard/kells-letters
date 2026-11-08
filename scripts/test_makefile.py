"""Test that make runs only the kells-letters env's own programs.

1. No recipe line in the Makefile, and no line of a shell script in scripts/, calls python, ketos, kraken or party by
   bare name (a bare name runs whichever env comes first on the PATH).
2. make stops before any recipe when the active env is not kells-letters, and in it runs the env's own python.
Usage: python scripts/test_makefile.py
"""
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BARE = re.compile(r"(?:^\t[@-]*\s*|^\s*|;\s*|&&\s*|\|\|?\s*|\$\$?\(\s*|`\s*|\b(?:do|then|else|exec)\s+)"
                  r"(python3?|ketos|kraken|party|pip)\b(?![-.\w/])")


def logical_lines(text):
    """Lines with their backslash continuations joined."""
    out, buf = [], None
    for line in text.split("\n"):
        buf = line if buf is None else buf + " " + line.strip()
        if buf.endswith("\\"):
            buf = buf[:-1]
            continue
        out.append(buf)
        buf = None
    return out


def recipe_lines(text):
    """The tab-indented lines of each rule; blank and comment lines inside a rule do not end it."""
    out, in_rule = [], False
    for line in logical_lines(text):
        if line.startswith("\t"):
            if in_rule:
                out.append(line)
        elif line.strip() and not line.lstrip().startswith("#"):
            in_rule = bool(re.match(r"^[^\s#.][^=]*?:(?![=:])", line))
    return out


def bare_calls(lines):
    return [line.strip() for line in lines if BARE.search(line.split("#")[0] if not line.startswith("\t") else line)]


def shell_lines(path):
    return [line for line in logical_lines(path.read_text()) if line.strip() and not line.lstrip().startswith("#")]


def test_parser_finds_bare_calls():
    made = "x:  ## a rule\n                   ## its comment\n\tpython a.py\n\t$(PYTHON) b.py; ketos test\ny := 1\n"
    assert bare_calls(recipe_lines(made)) == ["python a.py", "$(PYTHON) b.py; ketos test"]
    assert bare_calls(["for p in a b; do kraken -i $$p", "seed=$(python -c 1)", "x data/models/kraken y"]) == [
        "for p in a b; do kraken -i $$p", "seed=$(python -c 1)"]


def test_no_bare_calls():
    found = bare_calls(recipe_lines((ROOT / "Makefile").read_text()))
    for sh in sorted((ROOT / "scripts").glob("*.sh")):
        found += [f"{sh.name}: {line.strip()}" for line in shell_lines(sh) if BARE.search(line)]
    assert not found, "bare calls:\n" + "\n".join(found)


def test_env_check():
    clean = {k: v for k, v in os.environ.items() if k not in ("MAKEFLAGS", "MAKELEVEL", "MFLAGS")}  # as if typed
    other = dict(clean, CONDA_PREFIX="/tmp/not-kells-letters")
    r = subprocess.run(["make", "-n", "models"], cwd=ROOT, env=other, capture_output=True, text=True)
    assert r.returncode != 0 and "activate the kells-letters conda env" in r.stderr, r.stderr
    own = dict(clean, CONDA_PREFIX=str(Path(sys.executable).parents[1]))
    r = subprocess.run(["make", "-n", "models"], cwd=ROOT, env=own, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.split()[0] == sys.executable, r.stdout + r.stderr


def test_run_settings():
    """A run folder made with one base model or training option set refuses another."""
    clean = {k: v for k, v in os.environ.items() if k not in ("MAKEFLAGS", "MAKELEVEL", "MFLAGS")}
    env = dict(clean, CONDA_PREFIX=str(Path(sys.executable).parents[1]))
    runs = ROOT / "data" / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=runs) as tmp:
        run = Path(tmp).name
        (Path(tmp) / "made.txt").write_text("BASE=catmus-1.5.0 STGALL_ARGS= KELLS_ARGS=\n")
        def make(*a):
            return subprocess.run(["make", "-n", "key-snapshot", f"RUN={run}", *a], cwd=ROOT, env=env,
                                  capture_output=True, text=True)
        r = make("BASE=catmus-1.6.0")
        assert r.returncode != 0 and "name another RUN" in r.stderr, r.stderr      # another base model
        r = make("BASE=catmus-1.5.0", "KELLS_ARGS=--passes 2")
        assert r.returncode != 0 and "name another RUN" in r.stderr, r.stderr      # another training option
        assert make("BASE=catmus-1.5.0").returncode == 0                           # the same settings


def main():
    tests = [test_parser_finds_bare_calls, test_no_bare_calls, test_env_check, test_run_settings]
    for t in tests:
        t()
    print(f"makefile: {len(tests)} tests pass")


if __name__ == "__main__":
    main()
