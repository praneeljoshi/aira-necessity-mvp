PY ?= python3
PORT ?= 8000          # 8000 is the manual server; verify on another port (make run PORT=8001)
VENV := .venv
BIN := $(VENV)/bin

.PHONY: run test clean setup poppler cli add dist wipe

$(BIN)/activate:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -q --upgrade pip
	$(BIN)/pip install -q -r requirements.txt

setup: $(BIN)/activate poppler

poppler:              ## pdftotext keeps page breaks and indent (AND/OR nesting); install it if missing, else warn
	@command -v pdftotext >/dev/null 2>&1 && exit 0; \
	if [ "$$(uname)" = Darwin ] && command -v brew >/dev/null 2>&1; then \
	  echo "pdftotext not found: HOMEBREW_NO_AUTO_UPDATE=1 brew install poppler"; \
	  HOMEBREW_NO_AUTO_UPDATE=1 brew install poppler || true; \
	else \
	  pm=; for m in apt-get dnf; do command -v $$m >/dev/null 2>&1 && pm=$$m && break; done; \
	  if [ -z "$$pm" ]; then :; \
	  elif [ "$$(id -u)" = 0 ]; then echo "pdftotext not found: $$pm install -y poppler-utils"; \
	    $$pm install -y poppler-utils || true; \
	  elif command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then \
	    echo "pdftotext not found: sudo -n $$pm install -y poppler-utils"; sudo -n $$pm install -y poppler-utils || true; \
	  fi; \
	fi; \
	command -v pdftotext >/dev/null 2>&1 || printf '%s\n' '' \
	  '======================================================================' \
	  ' WARNING: pdftotext (poppler) is missing and could not be installed.' \
	  ' PDFs will be read with the pypdf fallback: page numbers (every line' \
	  ' lands on page 1) and indentation (which the guideline prompts read' \
	  ' as AND/OR nesting) are LOST. The app still runs, with worse results.' \
	  ' Install it, then restart:' \
	  '   macOS:  brew install poppler' \
	  '   Linux:  sudo apt-get install poppler-utils  (or: sudo dnf install poppler-utils)' \
	  '======================================================================' '' >&2

run: setup            ## one-line run: make run   (needs OPENAI_API_KEY)
	@test -n "$$OPENAI_API_KEY" || (echo "Set OPENAI_API_KEY first: export OPENAI_API_KEY=sk-..." && exit 1)
	$(BIN)/uvicorn app.main:app --host 127.0.0.1 --port $(PORT) --no-access-log

test: setup           ## evaluator + merge + matching tests, no network
	$(BIN)/python -m pytest -q

cli: setup            ## make cli CHART=path.pdf [GUIDELINE=id]
	$(BIN)/python -m app.cli $(CHART) $(GUIDELINE)

add: setup             ## make add FILE=guideline.pdf [ID=id]  -> data/guidelines/<id>/spans.json (code only)
	$(BIN)/python -m app.cli add $(FILE) $(ID)

dist:                 ## zip of the committed tree (export-ignore drops working docs); runs/charts/orders stay empty
	git archive --format=zip --prefix=aira-necessity/ -o ../aira-necessity-v1.zip HEAD
	@unzip -l ../aira-necessity-v1.zip | tail -1

wipe: setup           ## forget every checked chart (charts, orders, run logs); the guideline library stays
	$(BIN)/python -m app.cli wipe --all
	touch data/runs/.gitkeep

clean:
	rm -rf $(VENV) data/runs/* data/charts/* data/results/*
