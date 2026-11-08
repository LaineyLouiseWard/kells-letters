"""Test scripts/stgall_text.py on five lines read by eye against their page images (3 Nov 2026), which together cover
every label rule, and on markup the rules do not name, which must stop it.

Usage: python scripts/test_stgall_text.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import stgall_text as st  # noqa: E402

# (page, column, line): (label, continues, train, reason)
CHECKED = {
    # enlarged F (cap2) written lower case; ÷ est and ƕ autem as signs; <ex> dropped (babtizaret<ex>ur</ex>,
    # p<ex>o</ex>p<ex>ulu</ex>s); the shortened holy name ihu; punctuation; the last word continues (bab-tizato)
    (139, 1, 19): ("rem · factum ÷ ƕ cum babtizaret omnis pps et ihu bab", 1, 0, "enlarged letters"),
    # the first hand's reading (summationem, not the corrector's consummationem); letters below the line; æ
    (77, 1, 22): ("omnib dieb usq ad summationem sæculi : -", 0, 0, "correction; displaced letters"),
    # ⧺ enim as a sign; joined letters (ti) written as letters; <ex> dropped (retribuet<ex>ur</ex>)
    (177, 1, 25): ("tribuere tibi retribuet ⧺ tibi in resurrectione iustorum", 0, 1, ""),
    # a <space> as written, between eis and dicentes
    (202, 1, 9): ("bant principes cum eis dicentes alios saluos", 0, 1, ""),
    # the numeral five, v in the TEI, written u as the scribe wrote it; ƕ autem; punctuation
    (37, 1, 14): ("plenos manducantium ƕ fuit numerus · u · milia uirorum", 0, 1, ""),
}
UNNAMED = [b'<w>ab<foo>c</foo></w>', b'<w><hi rend="blue">a</hi></w>']


def tei(body):
    return (b'<TEI xmlns="http://www.tei-c.org/ns/1.0"><text><body><pb n="1"/><cb n="1"/><lb n="1"/>' + body
            + b'</body></text></TEI>')


def main():
    folder = st.DATA / st.CFG["stgall"]["tei_out"]
    rows = {(r["page"], r["column"], r["line"]): r for f in st.CFG["stgall"]["tei_files"]
            for r in st.read((folder / f).read_bytes())}
    assert len(rows) == 6355, f"{len(rows)} lines, not the 6,355 <lb> of the four files"
    for key, want in CHECKED.items():
        r = rows[key]
        got = (r["label"], r["continues"], r["train"], r["reason"])
        assert got == want, f"page {key[0]} line {key[2]}: got {got}, want {want}"
    for body in UNNAMED:
        try:
            st.read(tei(body))
        except ValueError:
            continue
        raise AssertionError(f"unnamed markup passed silently: {body!r}")
    print(f"stgall_text: {len(CHECKED)} checked lines and {len(UNNAMED)} unnamed-markup cases pass")


if __name__ == "__main__":
    main()
