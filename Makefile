PY ?= python3
PORT ?= 8000          # 8000 is the owner's manual server; agents verify on another port (make run PORT=8001)
VENV := .venv
BIN := $(VENV)/bin

.PHONY: run test clean setup cli add dist wipe

$(BIN)/activate:
	$(PY) -m venv $(VENV)
	$(BIN)/pip install -q --upgrade pip
	$(BIN)/pip install -q -r requirements.txt

setup: $(BIN)/activate

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
