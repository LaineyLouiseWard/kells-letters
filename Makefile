# One command per step, in order; run from the kells-letters conda env. Targets marked (big) are big runs: announce
# their size, time and memory and wait for Lainey's go. Every step exits with an error when its gate fails; the
# downloads and segmentation resume where they stopped, and a training step that stops starts again from its beginning.
# Steps run one at a time even under make -j: two trainings at once would share the laptop's 8 GB GPU.
.NOTPARALLEL:
# Every recipe runs the kells-letters env's own programs by their full path. A bare `python` can be another env's: in
# the shell of 3 Nov it was S2S_AI's, even with kells-letters active, and the scripts then ran with other package
# versions without complaint.
ENV := kells-letters
ifneq ($(notdir $(CONDA_PREFIX)),$(ENV))
$(error activate the $(ENV) conda env before make (conda activate $(ENV)); CONDA_PREFIX is '$(CONDA_PREFIX)')
endif
BIN := $(CONDA_PREFIX)/bin
PYTHON := $(BIN)/python
KETOS := $(BIN)/ketos
KRAKEN := $(BIN)/kraken
PARTY := $(BIN)/party
SEED = $(shell $(PYTHON) -c "import yaml; print(yaml.safe_load(open('config/paths.yaml'))['SEED'])")

# A reader run: Kraken's classic reader from one base model (config/models.yaml), with its models, readings and own
# copy of the answer key in data/runs/$(RUN)/ and its record (scores, pass errors, choice) in results/$(RUN)/. Each
# step makes a file, so `make reader` does only what is missing and never redoes a finished step: a new run needs a
# new RUN name. Test runs: STGALL_ARGS="-q fixed -N 1" and KELLS_ARGS="--passes 2", with OUT outside results/.
BASE ?= catmus-1.6.0
RUN ?= $(BASE)
R := data/runs/$(RUN)
OUT ?= results/$(RUN)
BASE_MODEL = $(shell $(PYTHON) scripts/models.py --path $(BASE))
STGALL_ARGS ?=
KELLS_ARGS ?=
# Kells settings compared. Freezing is left out: Kraken 7.1.1's `ketos train` accepts --freeze-backbone but never
# passes it to its trainer (kraken/ketos/recognition.py, the KrakenTrainer call), so a freeze run equals a plain one.
SETTINGS := plain
# EXTRA=1: the 8 extra training pages join Kells training, never its measuring (key_snapshot.py --extra).
EXTRA ?=
# party (a base model named party-*) takes the same steps with its own commands: St Gall training and test by `party
# train` and `party test` (through scripts/party_cli.py, which fixes two faults; see its docstring),
# Kells by scripts/party_finetune.py, reading by `read_pages.py --party`. party applies --freeze-encoder, so both
# settings are compared.
PARTY_RUN := $(filter party-%,$(BASE))
ifneq ($(PARTY_RUN),)
SETTINGS := plain freeze
endif
SG := $(if $(PARTY_RUN),party,kraken)
FINETUNE := scripts/$(if $(PARTY_RUN),party,kells)_finetune.py
READ_AS := $(if $(PARTY_RUN),--party)
ifneq ($(PARTY_RUN),)
STGALL_TRAIN = $(PYTHON) scripts/party_cli.py -d cuda:0 --precision bf16-mixed --workers 4 -s $(SEED) -r train -i "$(BASE_MODEL)" \
	--prompt-mode curves $(STGALL_ARGS) -o $(R)/stgall.part -t data/xml/stgall/train.party.lst \
	-e data/xml/stgall/val.party.lst
STGALL_TEST = $(PYTHON) scripts/party_cli.py -d cuda:0 --precision bf16-mixed test -i $< -e data/xml/stgall/test.party.lst
else
STGALL_TRAIN = $(KETOS) -d cuda:0 --workers 4 -s $(SEED) -r train -f binary -i "$(BASE_MODEL)" --resize new -B 16 \
	$(STGALL_ARGS) -o $(R)/stgall.part -e data/xml/stgall/val.kraken.lst data/xml/stgall/train.kraken.arrow
STGALL_TEST = $(KETOS) -d cuda:0 test -f binary -m $< data/xml/stgall/test.kraken.arrow
endif
# A run folder belongs to the settings it was made with (made.txt): the same RUN with another base model or other
# training options stops here, so no step reuses a model made another way.
MADE := BASE=$(BASE) STGALL_ARGS=$(strip $(STGALL_ARGS)) KELLS_ARGS=$(strip $(KELLS_ARGS))$(if $(EXTRA), EXTRA=$(EXTRA))
ifneq ($(wildcard $(R)/made.txt),)
ifneq ($(strip $(shell cat $(R)/made.txt)),$(strip $(MADE)))
$(error $(R) was made with '$(strip $(shell cat $(R)/made.txt))', not '$(MADE)': name another RUN)
endif
endif

.PHONY: download models manifests stgall-text stgall-seg stgall-xml audit split smoke kraken-compile party-compile
.PHONY: party-train kells-seg key-pick key-lines key-gpt key-diff key-xml key-snapshot stgall-train read-key score-key
.PHONY: kells-finetune read-test score-final reader tables test

download:          ## Kells, St Gall 51 and TEI files (one request per 3 s; reruns fetch only what is missing)
	$(PYTHON) scripts/download.py

models:            ## base models: download any missing, test every md5 against its Zenodo record (config/models.yaml)
	$(PYTHON) scripts/models.py

manifests:         ## one row per page for both books; download gate: every image opens
	$(PYTHON) scripts/manifests.py

stgall-text:       ## St Gall's typed lines, after the label-rule test
	$(PYTHON) scripts/test_stgall_text.py
	$(PYTHON) scripts/stgall_text.py

stgall-seg:        ## (big) Kraken lines on every St Gall page with text
	$(PYTHON) scripts/segment_pages.py stgall

stgall-xml:        ## pair Kraken's lines with the typed lines; one PageXML per kept page
	$(PYTHON) scripts/make_xml.py

audit:             ## draw 5 kept pages at random with their labels, for viewing whole
	$(PYTHON) scripts/draw_pairs.py stgall --draw 5

split:             ## train, val and test lists by page; gate: at least 4,000 training lines
	$(PYTHON) scripts/split.py

smoke:             ## test run of the whole cycle on 2 pages, before the big training runs
	scripts/smoke.sh

kraken-compile: $(foreach p,train val test,data/xml/stgall/$(p).kraken.arrow data/xml/stgall/$(p).kraken.lst)
data/xml/stgall/%.kraken.arrow: data/xml/stgall/%.lst  ## each split's lines cut out once into Kraken's binary format
	$(KETOS) --workers 8 compile -f page -o $@ -F $<
data/xml/stgall/%.kraken.lst: data/xml/stgall/%.kraken.arrow  ## a one-line list naming it, for ketos -e
	echo $< > $@

party-compile: $(foreach p,train val test,data/xml/stgall/$(p).party.lst)  ## party's own binary datasets, one per split
data/xml/stgall/%.party.arrow: data/xml/stgall/%.lst  ## (not compatible with Kraken's)
	$(PARTY) compile -o $@ -F $<
data/xml/stgall/%.party.lst: data/xml/stgall/%.party.arrow  ## a one-line list naming it, for party train -t and -e
	echo $< > $@
# compiled lines are kept: make would otherwise delete the ones it reaches only through their one-line lists
.PRECIOUS: data/xml/stgall/%.party.arrow data/xml/stgall/%.kraken.arrow

kells-seg:         ## (big) Kraken lines on every Kells Gospel text page
	$(PYTHON) scripts/segment_pages.py kells

key-pick:          ## draw the 16 answer-key pages, 4 per zone (2 tune, 2 test), with SEED
	$(PYTHON) scripts/pick_key.py

key-lines:         ## every Kraken line of the key pages as a numbered image (never released), and empty PageXML
	$(PYTHON) scripts/key_lines.py

key-gpt:           ## GPT's separate copy of the key, one call per page (Codex on Lainey's ChatGPT plan)
	$(PYTHON) scripts/key_gpt.py

key-diff:          ## lines where Claude's and GPT's copies differ, into adjudication.csv for settling by eye
	$(PYTHON) scripts/key_diff.py

key-xml: data/xml/kells_key/tune.lst  ## the settled key into PageXML, whenever adjudication.csv is newer
data/xml/kells_key/tune.lst: data/kells_key/adjudication.csv data/kells_key/lines.csv data/kells_key/sample.csv \
		scripts/key_xml.py   ## with tune, test and fold lists; stops on any unsettled line
	$(PYTHON) scripts/key_xml.py

# The steps of one reader run, in the order `make reader` takes them. The key's PageXML is
# brought up to date only before the run takes its copy; a run that has its copy never looks at the key again.
reader: $(if $(wildcard $(R)/key/key.json),,key-xml) key-snapshot stgall-train score-key score-final  ## (big)

$(R)/made.txt:
	mkdir -p $(R) && echo '$(MADE)' > $@

key-snapshot: $(R)/key/key.json  ## the run's own copy of the key: PageXML, lists and compiled lines
$(R)/key/key.json: | $(R)/made.txt
	$(PYTHON) scripts/key_snapshot.py $(R)/key $(if $(EXTRA),--extra)

stgall-train: $(R)/stgall/best.safetensors $(OUT)/stgall_test.txt  ## (big) St Gall fine-tuning from BASE
# The compiled lines are named here, not only their one-line lists: sonic/sync.sh copies the lists but not the compiled
# lines, and make never rebuilds a missing file it reaches only through an existing list.
$(R)/stgall/best.safetensors: | $(R)/made.txt data/xml/stgall/train.$(SG).arrow data/xml/stgall/val.$(SG).arrow \
		data/xml/stgall/val.$(SG).lst $(if $(PARTY_RUN),data/xml/stgall/train.party.lst)
	$(PYTHON) scripts/models.py $(BASE)
	rm -rf $(R)/stgall.part $(R)/stgall && mkdir -p $(R)/stgall.part
	$(PYTHON) scripts/stamp.py "$(BASE_MODEL)" data/xml/stgall/train.$(SG).arrow data/xml/stgall/val.$(SG).arrow \
		> $(R)/stgall.part/inputs.txt
	$(STGALL_TRAIN)
	cp $(R)/stgall.part/best_*.safetensors $(R)/stgall.part/best.safetensors
	mv $(R)/stgall.part $(R)/stgall
$(OUT)/stgall_test.txt: $(R)/stgall/best.safetensors | data/xml/stgall/test.$(SG).arrow data/xml/stgall/test.$(SG).lst  ## St Gall's test pages, once
	mkdir -p $(OUT)
	{ cat $(R)/stgall/inputs.txt; $(PYTHON) scripts/stamp.py $< data/xml/stgall/test.$(SG).arrow; } > $@.part
	$(STGALL_TEST) >> $@.part
	mv $@.part $@

read-key: $(R)/read/stgall/read.json  ## the St Gall model reads the 16 key pages
$(R)/read/stgall/read.json: $(R)/stgall/best.safetensors $(R)/key/key.json
	$(PYTHON) scripts/read_pages.py --model $(R)/stgall/best.safetensors --key $(R)/key --role all --out $(R)/read/stgall \
		$(READ_AS)

score-key: $(OUT)/stgall_tune.csv $(OUT)/stgall_test.csv  ## its error on the tune and on the test pages, per page, zone
$(OUT)/stgall_%.csv: $(R)/read/stgall/read.json
	$(PYTHON) scripts/score.py $(R)/read/stgall --ref $(R)/key --role $* --out $@

kells-finetune: $(OUT)/chosen.json  ## the St Gall model fine-tuned on the tune pages, with and without freezing
$(R)/kells/%/final.safetensors: $(R)/stgall/best.safetensors $(R)/key/key.json  ## passes by two folds, then all 8
	$(PYTHON) $(FINETUNE) $(R) --record $(OUT) $(if $(filter freeze,$*),--freeze) $(KELLS_ARGS)
$(OUT)/chosen.json: $(foreach s,$(SETTINGS),$(R)/kells/$(s)/final.safetensors)  ## and the setting chosen
	$(PYTHON) $(FINETUNE) $(R) --record $(OUT) --choose --settings $(SETTINGS)

read-test: $(R)/read/final/read.json  ## the run's final model reads the 8 test pages, once
$(R)/read/final/read.json: $(OUT)/chosen.json
	$(PYTHON) scripts/read_pages.py --model $(R)/kells/final.safetensors --key $(R)/key --role test --out $(R)/read/final \
		$(READ_AS)

score-final: $(OUT)/final_test.csv  ## its error on the test pages, per page and zone
$(OUT)/final_test.csv: $(R)/read/final/read.json
	$(PYTHON) scripts/score.py $(R)/read/final --ref $(R)/key --role test --out $@

tables:            ## notes/results.md's tables made again from results/; fails where they differ (WRITE=1 rewrites)
	$(PYTHON) scripts/tables.py notes/results.md $(if $(WRITE),--write)

test:              ## every test of the code; each gate's test was seen to fail once with the gate broken
	for t in scripts/test_*.py; do $(PYTHON) $$t || exit 1; done
