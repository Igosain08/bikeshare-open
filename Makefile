.PHONY: all data features train test clean model check-model

# --- The pipeline ----------------------------------------------------------
all: data features train

data:
	python -m src.ingest

features:
	python -m src.features

train:
	python -m src.train

test:
	python -m pytest tests/ -q

clean:
	rm -f data/processed/*.parquet reports/metrics.json reports/*.png

# --- The agent model (open weights, local) ----------------------------------
# Builds `bikeshare-coder`: the base model plus a 64k context window, which
# Claude Code needs and Ollama does not give you by default. Pick a larger
# BASE if your machine has the memory (see README.md).
BASE ?= qwen3.5:9b

model:
	ollama pull $(BASE)
	# A temp file, not `-f -`: Ollama 0.40 does not read a Modelfile from stdin.
	sed "s|^FROM .*|FROM $(BASE)|" model/Modelfile > model/.Modelfile.build
	ollama create bikeshare-coder -f model/.Modelfile.build; status=$$?; rm -f model/.Modelfile.build; exit $$status

check-model:
	bash model/check.sh
