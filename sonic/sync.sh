#!/bin/bash
# Copies what a Sonic run needs into private scratch on Sonic (~/scratch/kells-letters): the tracked files (code,
# config, the typed key and extra pages, Kraken's line outlines), St Gall 51's images and PageXML, and the page images
# of the typed Kells pages only (the key's 16 and the 8 extra; Trinity's terms: never more, never anywhere public).
# Compiled datasets are rebuilt there by make; base models are downloaded there (see setup_env.sh).
# Usage: sonic/sync.sh [HOST]   (HOST: the ssh alias, sonic on campus, sonic-home off campus; default sonic)
set -euo pipefail
HOST=${1:-sonic}
DEST=scratch/kells-letters
cd "$(dirname "$0")/.."
# only committed code is copied, and its commit goes with it for the results' stamps (scripts/stamp.py): the copy on
# Sonic has no git history
if [ -n "$(git status --porcelain --untracked-files=no)" ]; then
    echo "tracked files differ from the last commit: commit them first" >&2; exit 1
fi
ssh "$HOST" "mkdir -p $DEST/data/raw/kells $DEST/data/xml/stgall $DEST/logs"
git ls-files -z | rsync -a --from0 --files-from=- ./ "$HOST:$DEST/"
rsync -a data/raw/stgall51/ "$HOST:$DEST/data/raw/stgall51/"
rsync -a --include='*.xml' --include='*.lst' --include='*.csv' --exclude='*' data/xml/stgall/ "$HOST:$DEST/data/xml/stgall/"
rsync -a data/xml/kells_key data/xml/kells_extra "$HOST:$DEST/data/xml/"
folios=$(tail -q -n +2 data/kells_key/sample.csv data/kells_extra/sample.csv | cut -d, -f1 | tr -d '\r')
for f in $folios; do echo "data/raw/kells/$f.jpg"; done | rsync -a --files-from=- ./ "$HOST:$DEST/"
git rev-parse --short HEAD | ssh "$HOST" "cat > $DEST/.synced_commit"
echo "synced commit $(git rev-parse --short HEAD) to $HOST:$DEST ($(echo $folios | wc -w) Kells pages)"
