SCHEMA_DIR = src
SCHEMA_NAME = onga
MAIN_SCHEMA = $(SCHEMA_DIR)/$(SCHEMA_NAME).yaml

# Everything runs in the uv environment (pyproject.toml; `uv sync` first). The
# curation tooling is curation-workbench (`cwb`, configured by workbench.yaml),
# a path dependency on a checkout at ../curation-workbench.
PY = uv run python
CWB = uv run cwb

.PHONY: subjects subjects-check all gen-owl gen-owl-core gen-owl-so gen-jsonld gen-jsonld-context gen-python gen-docs gen-registry validate test test-examples test-registry clean embeddings-build embeddings-compare apply apply-dry pending decisions mappings validate-mappings fmt fmt-check regen lint-schema usage status curate-pull

all: gen-owl gen-jsonld gen-registry

# Enforced lossless round-trip invariant: every facet-map row resolves to a live
# enum base, no compound term survives, every value
# carries its ONGA_NNNNNNN id (curation/term_ids.tsv), src/ is the projection of
# mappings/*.sssom.tsv. Plus the SSSOM validation, instance validation of the
# worked examples against the record classes, and the YAML formatting fixed point.
test: fmt-check validate-mappings subjects-check test-examples
	$(PY) scripts/check_roundtrip.py
	$(PY) scripts/usage_rollup.py --check
	$(CWB) lint --check
	$(CWB) status --check
	$(CWB) review --check
	$(PY) scripts/render_decisions.py --check

# Every src/*.yaml must be a fixed point of the shared YAML writer
# (curation_workbench.yamlio), so a programmatic edit diffs only its own change.
fmt:
	$(PY) scripts/fmt_schema.py

fmt-check:
	$(PY) scripts/fmt_schema.py --check

# Instance validation: a full TopLevel deposit (ENCFF323LCS), a bare
# Layer-3-only GenomicAnnotationFile, and an expected-failure counterexample
# (missing the one non-negotiable slot, reference_genome).
test-examples:
	uv run linkml-validate -s $(MAIN_SCHEMA) -C TopLevel examples/encff323lcs_deposit.yaml
	uv run linkml-validate -s $(MAIN_SCHEMA) -C GenomicAnnotationFile examples/genomic_annotation_standalone.yaml
	@if uv run linkml-validate -s $(MAIN_SCHEMA) -C GenomicAnnotationFile examples/invalid_missing_reference_genome.yaml >/dev/null 2>&1; then \
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
	uv run gen-owl $(MAIN_SCHEMA) > project/owl/$(SCHEMA_NAME).owl.ttl

gen-owl-so:
	mkdir -p project/owl
	$(PY) scripts/gen_so_axioms.py > project/owl/$(SCHEMA_NAME)-so-element-types.owl.ttl

# mappings/*.sssom.tsv are hand-curated and the source of truth for term-level
# mappings. Project them onto the permissible values' *_mappings slots and
# element_type annotations in src/*.yaml (generated; never hand-edit).
mappings:
	$(PY) scripts/project_mappings.py

# Validate the SSSOM files: live subject ids, live SO ids, the set/element
# predicate policy in mappings/policy.yaml, no duplicate rows.
validate-mappings:
	$(PY) scripts/validate_mappings.py

# The subject registry: curation/subjects.json (every reviewable term, enum,
# class, slot, usage, subset and module, with a hash of its authored payload)
# and curation/term_crosswalk.json (every label and legacy reference form ->
# term id). Generated and tracked; never hand-edit.
subjects:
	$(CWB) subjects

subjects-check:
	$(CWB) subjects --check

# Every generator whose output is tracked. This recipe is the inventory.
# subjects runs after mappings: a term's payload includes its SSSOM rows.
# Not `cwb regen`: usage must run between subjects and lint-schema.
regen: mappings subjects gen-registry usage lint-schema status decisions pending

# ENCODE file/dataset counts rolled up onto live content terms through the
# facet decomposition (curation/usage.json). Runs before lint-schema, which reads it.
usage:
	$(PY) scripts/usage_rollup.py

# Machine lint findings over every subject kind (curation/findings/schema_lint.json);
# thresholds, severities and suggested verdicts live in curation/policy.yaml.
lint-schema: usage
	$(CWB) lint

# Per-subject state (unreviewed | open | deferred | settled | applied | stale),
# queue score and rollups (curation/status.json); weights in curation/policy.yaml.
# Then the queue sorted into review tracks and types (curation/review.json;
# tracks and types in curation/review_types.yaml).
status: lint-schema
	$(CWB) status
	$(CWB) review

gen-jsonld:
	mkdir -p project
	uv run gen-jsonld-context $(MAIN_SCHEMA) > project/$(SCHEMA_NAME).context.jsonld

# Alias: the generator is named gen-jsonld-context, so accept that name too.
gen-jsonld-context: gen-jsonld

gen-python:
	uv run gen-python $(MAIN_SCHEMA) > project/$(SCHEMA_NAME).py

gen-docs:
	uv run gen-doc -d docs $(MAIN_SCHEMA)

# GA4GH Schema Registry static API (site/public/api/): manifest, service-info,
# namespaces, schemas/databio/onga/versions/<version>/ with the full JSON
# Schema bundle + per-class components, and versions/latest/ as a full copy.
# The version comes from `version:` in src/onga.yaml (single source of truth).
gen-registry:
	$(PY) scripts/gen_registry.py

# Optional: run the GA4GH Schema Registry compliance suite (read-only, from
# repos/schema-registry) against the generated tree. Needs a served tree, so it
# stays out of `make test`. Filter/CORS checks are expected to fail on a plain
# static tree (no query-parameter handling).
test-registry: gen-registry
	$(PY) scripts/serve_registry.py --root site/public/api --port 8917 --pid /tmp/onga-registry-server.pid & \
	sleep 1; \
	PYTHONPATH=../schema-registry $(PY) -m compliance http://localhost:8917; STATUS=$$?; \
	kill `cat /tmp/onga-registry-server.pid` 2>/dev/null; rm -f /tmp/onga-registry-server.pid; \
	exit $$STATUS

validate:
	uv run linkml-lint --config $(SCHEMA_DIR)/linkml_lint_config.yaml $(MAIN_SCHEMA)

embeddings-build:
	cd embeddings && python scripts/build_embeddings.py

embeddings-compare:
	cd embeddings && python scripts/run_comparison.py

# Apply every pending decision already in curation/decisions.yaml to the
# schema, all or nothing (`cwb apply`: preflight, stage, write, regen, test; any
# failure restores every file), then refresh curation/pending.json. New
# decisions come from curate.databio.org through `make curate-pull`.
apply:
	$(CWB) apply
	$(MAKE) pending

# Print the diff `make apply` would make; write nothing.
apply-dry:
	$(CWB) apply --dry-run

# The staged diff and per-decision effects of the pending records
# (curation/pending.json).
pending:
	$(CWB) apply --dry-run --emit curation/pending.json >/dev/null || true

# The generated blocks of DECISIONS.md (current-state, atomic-by-principle,
# cleanup-decisions); everything outside the markers is hand-written.
decisions:
	$(PY) scripts/render_decisions.py

clean:
	rm -f project/owl/*.ttl project/owl/*-so-element-types.owl.ttl project/*.jsonld project/*.py

# Decisions are made at https://curate.databio.org (votes, curators decide).
# This fetches the approved ones (needs CURATE_API_KEY, a read-only key a
# curator makes on the site's Approved page), applies them here (edits, `make
# regen`, `make test`), and leaves the changes for you to commit. The `curate`
# GitHub Action (.github/workflows/curate.yml) runs the same command and opens
# a pull request.
curate-pull:
	$(CWB) pull onga
