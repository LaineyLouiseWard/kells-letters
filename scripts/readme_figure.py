"""The README's line image: one line of St Gall 51 (CC BY-NC 4.0, e-codices), cut from its page by Kraken's line outline.
Never a Kells line (Trinity's terms). The line is from a St Gall test page, chosen for its error nearest the page's
median line error (page 14: 0.8%; this line: 1 character of 62).
Usage: python scripts/readme_figure.py [PAGE_XML LINE_ID OUT]
"""
import sys
from pathlib import Path

from lxml import etree
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
NS = {"p": "http://schema.primaresearch.org/PAGE/gts/pagecontent/2019-07-15"}
PAD = 12
WIDTH = 1400


def main(xml=ROOT / "data/xml/stgall/14.xml", line_id="_b63f7db6-2f8a-46c1-b810-95abf4cc5192",
         out=ROOT / "figures/stgall_line.png"):
    xml = Path(xml)
    tree = etree.parse(str(xml))
    ns = {"p": tree.getroot().nsmap.get(None, NS["p"])}
    page = tree.find(".//p:Page", ns)
    line = tree.find(f".//p:TextLine[@id='{line_id}']/p:Coords", ns)
    pts = [tuple(map(int, xy.split(","))) for xy in line.get("points").split()]
    xs, ys = zip(*pts)
    img = Image.open(xml.parent / page.get("imageFilename"))
    crop = img.crop((min(xs) - PAD, min(ys) - PAD, max(xs) + PAD, max(ys) + PAD))
    crop = crop.resize((WIDTH, round(crop.height * WIDTH / crop.width)), Image.LANCZOS)
    Path(out).parent.mkdir(exist_ok=True)
    crop.save(out)
    print(out, crop.size)


if __name__ == "__main__":
    main(*sys.argv[1:])
