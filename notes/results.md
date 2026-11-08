# Results

Every number here comes with the command that made it. The error rate is character error rate (CER): substitutions,
deletions and insertions divided by the answer key's characters, punctuation included, pooled over a page's or a zone's
lines (`scripts/score.py`). "CER" counts spaces; "no sp" leaves them out. Masks: `?` (a letter the key could not
read) matches any one character and `#` (a decorated initial) zero to two, at no cost; neither counts as a key
character. "stray" is characters a reader put on lines with no text in the key (decoration, page labels).

**The record.** Each run's scores, pass errors and choice are files in `results/<run>/`: every score row carries the
md5 of the model that read the pages, the md5 of `adjudication.csv` it was scored against and the code's commit.
Every table and per-page line below is made from those files by `scripts/tables.py`, and `make tables` fails where
they differ. Sections 1 to 3 were made with the Makefile of commit e5169a9, whose target names they quote; their
record was archived from `data/models/` and `data/read/` on 3 Nov (night) and rescored against the key of section 3
(md5 c6578d45155e72e83a3388ed3bc6b5df). Made from the counts, four figures typed earlier move by 0.1 point: 73v, 220v
and 98v, and zone D of CATMuS 1.6.0 (50 errors in 901 characters, 5.5%, not 5.6%).

## The answer key (3 Nov 2026)

- 16 pages, 4 per scribal zone, drawn with `SEED` (`scripts/pick_key.py`); 114r, a display page, replaced by 100r,
  next in zone D's drawn order.
- Two separate copies of every line: Claude's (helpers on the main model, two pages each) and GPT's
  (`scripts/key_gpt.py`). Of 349 Kraken lines, the copies differed in letters on 140 and only in word gaps on 41; each
  of these was settled by viewing the line image (`scripts/key_diff.py`, `data/kells_key/adjudication.csv`).
- Settled text: 276 lines with text, 8,325 characters, of which 4,401 on the tune pages and 3,924 on the test pages;
  40 `?` and 104 `#`.
- Words outside every Kraken line (for example "· et si" on 187r, after line 19) cannot be read by any reader and are
  not in the key.
- Each raw copy against the settled key (`python scripts/key_copies.py`): GPT's copy, made from the line images and
  the label rules only, with no Abbott, differs on 2.4% of characters (1.8% without spaces); Claude's copy, which had
  Abbott as a guide, on 1.2% (0.6%). The settling was done by Claude, so this is not an outside measure of the key's
  own error.
- Final once-over (`python scripts/key_recheck.py`, gpt-6.1-sol at high effort): of the 181 lines where the copies differed, GPT flagged 50. Viewed on the image (zoomed, and on the colour
  page where colour decides), 13 are changed (6 on the test pages) and 37 kept, each call with its reason in
  `data/kells_key/recheck/decisions.csv`. Kept: Trinity's printed caption read as text (4); dots and marks the
  conventions leave out, or no dot there (12); borderline word gaps (4); decorated initials decided by colour or by
  the word (6); letters still unclear on the image, which GPT read by the expected word (10); one line read wrongly
  (1). The 13 are in `adjudication.csv` (each line's `unsure` note gives its old text) and the key PageXML
  (`make key-xml`), and every figure here is scored against them. Before them (`python scripts/key_recheck.py --effect
  <read folder>`), the fine-tuned model's test pages were at 3.65% and the St Gall model's at 16.30%.

## The extra training pages (4 Nov 2026)

- 8 pages, the next 2 of each zone's drawn order (`data/kells_extra/sample.csv`), typed by the answer key's protocol.
  Training only: they are never read as test pages.
- Of 173 Kraken lines, the copies differed in letters on 70 and only in word gaps on 23, the key's share; each was
  settled on the line image. Letters still unclear after zooming went to GPT once as blind crops (9 stretches on 5
  pages, `data/kells_extra/tie/`).
- Settled text: 134 lines with text, 3,924 characters; 4 `?` and 39 `#`; 130 lines for training.
- Each raw copy against the settled key (`python scripts/key_copies.py --set kells_extra`): GPT's 2.6% of characters,
  Claude's 1.1%.
- Once-over (`python scripts/key_recheck.py --set kells_extra`): of the 93 lines where the copies differed, GPT
  flagged 28; viewed on the image, 3 are changed and 25 kept (`data/kells_extra/recheck/decisions.csv`). Kept:
  Trinity's printed caption and a chapter number read as text (5); dots that are decoration, or no dot there (8);
  borderline word gaps (6); letters the image shows otherwise or leaves unclear (6).
- Pilate's tailed i (121v) is typed y, as the key types the same letter on 126v (`pylatus`).
- With them in training (`make reader RUN=catmus-1.6.0-extra EXTRA=1`, from the chosen reader's St Gall model,
  `ketos -r`; `results/catmus-1.6.0-extra/`): two-fold error on the tune pages 3.79% at 35 passes (4.59% with the 8
  tune pages alone); the test pages, read once by its final model: 2.85% (112 of 3,924 characters), against 3.70%
  (145). Zones: A 1.8%, B 4.9%, C 2.4%, D 3.0%.

## Freezing has no effect (4 Nov 2026)

Kraken 7.1.1's `ketos train` takes `--freeze-backbone` but does not hand it to its trainer (`kraken/ketos/recognition.py`:
the `KrakenTrainer(...)` call has no `freeze_backbone=` argument), so no layer was ever frozen. With deterministic
training (`ketos -r`) the freeze and plain runs of `results/catmus-1.6.0-extra/` match at every pass to the digit.
Every "freezing" figure below is therefore a plain run with other run-to-run noise: the 1.5.0 choice of freezing
(4.44% against 5.06%) was noise, not an effect. Runs now train the plain setting only.

## 1. St Gall model only

Kraken's reader fine-tuned on St Gall 51 (`data/models/kraken/best_0.9840.safetensors`; 1.57% CER on St Gall's test
pages), no Kells training.

    make read-key        # kraken -d cuda:0 -f page -i <key xml> <out> ... -x ocr -B 16 -m best_0.9840.safetensors
    make score-key       # python scripts/score.py data/read/kraken_stgall --role tune|test

<!-- make tables: key | results/2026-11-03-catmus-1.5.0 -->
| Pages | Zone A | Zone B | Zone C | Zone D | All | All, no sp | Characters |
|---|---|---|---|---|---|---|---|
| tune (8) | 17.5% | 33.8% | 17.2% | 15.5% | 21.0% | 18.5% | 4,401 |
| test (8) | 18.8% | 15.2% | 14.9% | 15.1% | 16.2% | 14.1% | 3,924 |
<!-- end -->

<!-- make tables: key-pages | results/2026-11-03-catmus-1.5.0 -->
Per page, test: 310v 20.2%, 328v 17.4% (A); 126v 15.3%, 127r 15.1% (B); 220v 15.7%, 76v 14.1% (C); 98v 15.6%, 106r 14.6%
(D). Tune: 308r 19.5%, 135v 15.2% (A); 128r 56.0%, 128v 16.4% (B); 163r 19.8%, 73v 14.6% (C); 187r 13.9%, 100r 17.1%
(D).
<!-- end -->
128r is badly faded (24 of its 480 key characters are `?`); without it the tune pages are at 16.7%.

Above the plan's 10% threshold for St Gall, so fine-tuning on Kells (step 2) is needed. Zone figures rest on 2 pages
each and are indicative.

## 2. Fine-tuned on the Kells tune pages

The St Gall model fine-tuned on the 8 tune pages (119 lines; lines holding `?` held out, `#` left out of the text).

    make kells-finetune  # python scripts/kells_finetune.py, then with --freeze
    make read-test       # kraken ... -x ocr -B 16 -m data/models/kells_freeze/final.safetensors
    make score-final     # python scripts/score.py data/read/kraken_kells --role test

- **Choices, all on the tune pages.** Two folds (the first and the second tune page of each zone): train on one, measure
  every pass on the other with Kraken's own character error, for 50 passes. Without freezing, the lowest two-fold error
  was 5.06% at pass 32; keeping every layer but the output layer fixed for the first 10 passes' worth of lines
  (`--freeze-backbone`, from Kraken's training manual for small sets) gave 4.44% at pass 34, so that setting was used.
  From pass 5 on, the two-fold error stays between 5.1% and 6.3% without freezing and 4.4% and 6.0% with it, so the
  chosen pass is the lowest point of a flat curve
  (`data/models/kells*/passes.csv`). The final model: all 8 tune pages, frozen as above, 34 passes.
- **The test pages, read once** by that final model:

<!-- make tables: final | results/2026-11-03-catmus-1.5.0-page | results/2026-11-03-catmus-1.5.0 -->
| Pages | Zone A | Zone B | Zone C | Zone D | All | All, no sp | Characters |
|---|---|---|---|---|---|---|---|
| test (8), before Kells training | 18.8% | 15.2% | 14.9% | 15.1% | 16.2% | 14.1% | 3,924 |
| test (8), fine-tuned | 2.7% | 5.3% | 2.9% | 4.2% | 3.6% | 3.2% | 3,924 |
<!-- end -->

<!-- make tables: final-pages | results/2026-11-03-catmus-1.5.0-page -->
Per page, fine-tuned: 310v 1.8%, 328v 3.6% (A); 126v 6.4%, 127r 3.9% (B); 220v 2.2%, 76v 3.6% (C); 98v 4.5%, 106r 3.9%
(D).
<!-- end -->
The model was trained on the tune pages as they stood before the once-over's 7 tune-page changes.
Masked: 11 `?` and 45 `#`; 38 characters read on lines with no text in the key (decoration and page
labels), not counted. Zone figures rest on 2 pages each and are indicative.

The fine-tuned model is under the plan's 10% threshold, so step 14.3 (more training pages) is not needed.

## 3. Two starting models side by side: CATMuS Medieval 1.5.0 and 1.6.0 (3 Nov, night)

Same steps for both: St Gall fine-tuning (`make kraken-train`, `make kraken16-train`), then Kells fine-tuning from
lines cut once (`ketos compile`), with and without freezing, two folds, the setting with the lower two-fold error read
on the test pages once (`bash scripts/kells_compare.sh`). Every Kells figure below is scored against the key as it
stood at 22:11 on 3 Nov (`adjudication.csv` md5 c6578d45155e72e83a3388ed3bc6b5df; test pages 3,924 characters, tune
4,401), after another chat's small edits; sections 1 and 2 were first scored against the key before them, and their
tables above are rescored against this one. One point of error on the test pages is about 39 characters.

<!-- make tables: compare | CATMuS 1.5.0: results/2026-11-03-catmus-1.5.0 | CATMuS 1.6.0: results/2026-11-03-catmus-1.6.0 -->
| | CATMuS 1.5.0 | CATMuS 1.6.0 |
|---|---|---|
| St Gall test pages, St Gall model | 1.57% | 1.28% |
| Kells test, St Gall model only | 16.2% (no sp 14.1%) | 14.7% (no sp 11.6%) |
| Kells tune, St Gall model only | 21.0% | 19.8% |
| Two-fold error on the tune pages (Kraken's measure), without freezing | 4.59% (20 passes) | 4.59% (32 passes) |
| Two-fold error, with freezing | 4.88% (36 passes) | 4.61% (15 passes) |
| Setting used | without freezing | without freezing |
| **Kells test, fine-tuned** | **3.82%** (no sp 3.29%) | **3.70%** (no sp 3.14%) |
| Zone A / B / C / D, fine-tuned | 2.8% / 5.4% / 2.8% / 5.0% | 2.5% / 4.5% / 2.8% / 5.5% |
<!-- end -->

- **Choice: CATMuS 1.6.0.** The two tie on the tune pages (4.59% each), and Lainey's rule is the newer model when the
  two are close (3 Nov). On the test pages they differ by 0.12 points, about 5 characters.
- The first 1.5.0 run (section 2: lines re-cut from the page images on every pass, freezing chosen), rescored against
  the same key: 3.62%. The three fine-tuned results lie within 0.2 points of each other.
- Caveat: the key edit at 22:11 fell during the 1.6.0 Kells runs, so some of its fold runs trained on the key before
  the edit and some after (the tune pages changed by 6 characters). The chosen reader is to be rerun start to finish:
  `make reader` (base model catmus-1.6.0), with its record in `results/catmus-1.6.0/`.
- **Run-to-run noise** (`python scripts/kells_noise.py`; `results/noise-2026-11-03/`). The same 10-pass fold run
  (fold 1 trained, fold 2 measured, same seed) repeated four times without Kraken's deterministic mode gave pass errors
  up to 0.46 points apart (pass 7: 4.72% to 5.18%); four runs with it (`ketos -r`) matched to every digit, at about 3%
  more time (2.48 against 2.40 s a pass, on an otherwise idle laptop). Training now runs with `-r`; the results
  above were made without it, so a rerun can differ from them within that noise. Gaps under about half a point between two runs,
  such as CATMuS 1.5.0 against 1.6.0 (a tie on the tune pages, 0.12 points on the test pages), are within that noise.
- What decided and what is reported differ in measure. Passes and freezing are chosen by Kraken's own character error
  on the fold's training text (`#` left out, lines holding `?` held out); the reported figures are `scripts/score.py`'s
  on the reference text, where `?` and `#` are masks. Both count spaces, and only the tune pages decide.
