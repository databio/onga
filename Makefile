SCHEMA_DIR = src
SCHEMA_NAME = onga
MAIN_SCHEMA = $(SCHEMA_DIR)/$(SCHEMA_NAME).yaml

.PHONY: all gen-owl gen-owl-core gen-owl-so gen-jsonld gen-python gen-docs gen-registry validate test test-examples test-registry clean embeddings-build embeddings-compare apply mappings

all: gen-owl gen-jsonld gen-registry

# Enforced lossless round-trip invariant: every facet-map row resolves to a live
# enum base, no compound term survives, counts match DECISIONS. Stdlib + pyyaml.
# Plus instance validation of the worked examples against the record classes.
test: test-examples
	python scripts/check_roundtrip.py

# Instance validation: a full TopLevel deposit (ENCFF323LCS), a bare
# Layer-3-only GenomicAnnotationFile, and an expected-failure counterexample
# (missing the one non-negotiable slot, reference_genome).
test-examples:
	linkml-validate -s $(MAIN_SCHEMA) -C TopLevel examples/encff323lcs_deposit.yaml
	linkml-validate -s $(MAIN_SCHEMA) -C GenomicAnnotationFile examples/genomic_annotation_standalone.yaml
	@if linkml-validate -s $(MAIN_SCHEMA) -C GenomicAnnotationFile examples/invalid_missing_reference_genome.yaml >/dev/null 2>&1; then \
		echo "ERROR: examples/invalid_missing_reference_genome.yaml validated but must FAIL"; exit 1; \
	else \
		echo "Expected failure OK: invalid_missing_reference_genome.yaml rejected"; \
	fi

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

# GA4GH Schema Registry static API (site/public/api/): manifest, service-info,
# namespaces, schemas/databio/onga/versions/<version>/ with the full JSON
# Schema bundle + per-class components, and versions/latest/ as a full copy.
# The version comes from `version:` in src/onga.yaml (single source of truth).
gen-registry:
	python scripts/gen_registry.py

# Optional: run the GA4GH Schema Registry compliance suite (read-only, from
# repos/schema-registry) against the generated tree. Needs a served tree, so it
# stays out of `make test`. Filter/CORS checks are expected to fail on a plain
# static tree (no query-parameter handling).
test-registry: gen-registry
	python scripts/serve_registry.py --root site/public/api --port 8917 --pid /tmp/onga-registry-server.pid & \
	sleep 1; \
	PYTHONPATH=../schema-registry python -m compliance http://localhost:8917; STATUS=$$?; \
	kill `cat /tmp/onga-registry-server.pid` 2>/dev/null; rm -f /tmp/onga-registry-server.pid; \
	exit $$STATUS

validate:
	linkml-lint --config $(SCHEMA_DIR)/linkml_lint_config.yaml $(MAIN_SCHEMA)

embeddings-build:
	cd embeddings && python scripts/build_embeddings.py

embeddings-compare:
	cd embeddings && python scripts/run_comparison.py

apply:
	python scripts/apply_changeset.py $(CHANGESET)

clean:
	rm -f project/owl/*.ttl project/owl/*-so-element-types.owl.ttl project/*.jsonld project/*.py
