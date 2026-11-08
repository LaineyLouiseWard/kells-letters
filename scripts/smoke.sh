#!/bin/bash
# Smoke test, a test run before any big training run: one full cycle on the first two St Gall training pages (A, B).
# Kraken's reader trains for one pass on A (validated on B) and reads B (kraken ocr); party's base model reads B
# unfine-tuned; scripts/align.py places party's letters on B with the Kraken model; the boxes are drawn in
# outputs/audit/<B>_letters_<k>.png for viewing. Outputs in data/smoke/. Run from the kells-letters env.
set -euo pipefail
cd "$(dirname "$0")/.."
[ "$(basename "${CONDA_PREFIX:-}")" = kells-letters ] || { echo "activate the kells-letters conda env first" >&2; exit 2; }
bin=$CONDA_PREFIX/bin  # the env's own programs: a bare python can be another env's
seed=$("$bin/python" -c "import yaml; print(yaml.safe_load(open('config/paths.yaml'))['SEED'])")
# Absolute paths: both readers copy the image path into their output as they were given it.
A=$(realpath "$(sed -n 1p data/xml/stgall/train.lst)")
B=$(realpath "$(sed -n 2p data/xml/stgall/train.lst)")
out=data/smoke
rm -rf "$out"
mkdir -p "$out"
echo "$B" > "$out/val.lst"
"$bin/ketos" -d cuda:0 -s "$seed" train -f page -o "$out/kraken" -N 1 -q fixed -e "$out/val.lst" "$A"
model=$(ls "$out"/kraken/best_*.safetensors | head -1)
"$bin/kraken" -d cuda:0 -f page -i "$B" "$out/kraken_read.xml" -x ocr -m "$model"
"$bin/party" -d cuda:0 --precision bf16-mixed ocr -m 10.5281/zenodo.14616980 -x -i "$B" "$out/party_read.xml"
"$bin/python" scripts/align.py -m "$model" -o "$out/aligned" --draw "$out/party_read.xml"
echo "smoke test done: view outputs/audit/party_read_letters_*.png"
