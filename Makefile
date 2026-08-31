SCHEMA_DIR = src
SCHEMA_NAME = onga
MAIN_SCHEMA = $(SCHEMA_DIR)/$(SCHEMA_NAME).yaml

.PHONY: all gen-owl gen-owl-core gen-owl-so gen-jsonld gen-python gen-docs validate test clean embeddings-build embeddings-compare apply mappings

all: gen-owl gen-jsonld

# Enforced lossless round-trip invariant: every facet-map row resolves to a live
# enum base, no compound term survives, counts match DECISIONS. Stdlib + pyyaml.
test:
	python scripts/check_roundtrip.py

# The core OWL carries the vocabularies and descriptor schemas. The SO axioms
# are generated separately because the ONGA->SO relation is a level shift (set ->
# element) that LinkML has no slot for: it is emitted as an owl:Restriction on
# onga:has_element_type, never as a SKOS match and never with an SO IRI as the
# subject. See the ADR "ONGA terms denote sets; SO terms denote elements".
gen-owl: gen-owl-core gen-owl-so

gen-owl-core:
	mkdir -p project/owl
	gen-owl $(MAIN_SCHEMA) > project/owl/$(SCHEMA_NAME).owl.ttl

gen-owl-so:
	mkdir -p project/owl
	python scripts/gen_so_axioms.py > project/owl/$(SCHEMA_NAME)-so-element-types.owl.ttl

# Regenerate the curated SO mapping set and re-apply the element_type
# annotations it implies to src/file_content.yaml.
mappings:
	python scripts/build_so_sssom.py
	python scripts/apply_element_type.py

gen-jsonld:
	mkdir -p project
	gen-jsonld-context $(MAIN_SCHEMA) > project/$(SCHEMA_NAME).context.jsonld

# Alias: the generator is named gen-jsonld-context, so accept that name too.
gen-jsonld-context: gen-jsonld

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
	rm -f project/owl/*.ttl project/owl/*-so-element-types.owl.ttl project/*.jsonld project/*.py
