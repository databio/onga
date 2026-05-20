SCHEMA_DIR = src
SCHEMA_NAME = onga
MAIN_SCHEMA = $(SCHEMA_DIR)/$(SCHEMA_NAME).yaml

.PHONY: all gen-owl gen-jsonld gen-python gen-docs validate clean

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
	linkml-validate --schema $(MAIN_SCHEMA) --target-class OutputType

clean:
	rm -f project/owl/*.ttl project/*.jsonld project/*.py
