SCHEMA_DIR = src
SCHEMA_NAME = onga
MAIN_SCHEMA = $(SCHEMA_DIR)/$(SCHEMA_NAME).yaml

.PHONY: all gen-owl gen-jsonld gen-python gen-docs validate clean embeddings-build embeddings-compare apply

all: gen-owl gen-jsonld

gen-owl:
	gen-owl $(MAIN_SCHEMA) > project/owl/$(SCHEMA_NAME).owl.ttl

gen-jsonld:
	gen-jsonld-context $(MAIN_SCHEMA) > project/$(SCHEMA_NAME).context.jsonld

gen-python:
	gen-python $(MAIN_SCHEMA) > project/$(SCHEMA_NAME).py

gen-docs:
	gen-doc -d docs $(MAIN_SCHEMA)

validate:
	linkml-lint $(MAIN_SCHEMA)

embeddings-build:
	cd embeddings && python scripts/build_embeddings.py

embeddings-compare:
	cd embeddings && python scripts/run_comparison.py

apply:
	python scripts/apply_changeset.py $(CHANGESET)

clean:
	rm -f project/owl/*.ttl project/*.jsonld project/*.py
