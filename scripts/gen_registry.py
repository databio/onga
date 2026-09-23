#!/usr/bin/env python3
"""Generate the GA4GH Schema Registry static API for the ONGA schema.

Publishes the registry API layout (spec: repos/schema-registry) under
site/public/api/ so the Astro build ships it verbatim:

    manifest.json
    service-info/index.json                 (GA4GH Service Info 1.0)
    namespaces/index.json                   (single namespace: databio)
    schemas/databio/index.json
    schemas/databio/onga/versions/index.json
    schemas/databio/onga/versions/<version>/index.json      (full JSON Schema)
    schemas/databio/onga/versions/<version>/components/<Class>.json
    schemas/databio/onga/versions/<version>/components/index.json
    schemas/databio/onga/versions/latest/                   (full copy)

Version identity: `version:` in src/onga.yaml is the single source of truth;
this script fails loudly if it is absent. While a version is current it is
regenerated IN PLACE on every build (mutable current — correct for
developmental software) and versions/latest/ always mirrors it. Cutting a
version is a DECISIONS-logged operation that bumps `version:`; a superseded
version's directory is left committed as static history and its row in
versions/index.json flips from "current" to "superseded" (this script derives
the rows from the directories on disk).

Approach ported from nsheff's schema-registry-site build.py/registry_utils.py
(pagination envelopes, version records, component splitting); no code is
imported from and nothing is written to that repo. Stdlib + pyyaml, invoking
LinkML's gen-json-schema for the actual schema document.
"""

import json
import os
import shutil
import subprocess
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
MAIN_SCHEMA = os.path.join(ROOT, "src", "onga.yaml")
API_DIR = os.path.join(ROOT, "site", "public", "api")

SERVER = "https://dev.databio.org/onga/api"
NAMESPACE = "databio"
SCHEMA_NAME = "onga"


def make_pagination(total):
    return {
        "page": 0,
        "page_size": 100000,
        "total": total,
        "total_pages": 1,
    }


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  Wrote {os.path.relpath(path, ROOT)}")


def read_version():
    with open(MAIN_SCHEMA) as f:
        schema = yaml.safe_load(f)
    version = schema.get("version")
    if not version:
        sys.exit("ERROR: src/onga.yaml has no `version:` key — the registry "
                 "needs a version identity; refusing to generate.")
    return str(version), schema


def gen_json_schema():
    """Full JSON Schema for the merged schema, classes as $defs."""
    result = subprocess.run(
        ["gen-json-schema", "--include-range-class-descendants", MAIN_SCHEMA],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


def build():
    version, schema = read_version()
    print(f"Generating registry API for {NAMESPACE}/{SCHEMA_NAME} {version}")
    bundle = gen_json_schema()
    components = bundle.get("$defs", {})

    versions_dir = os.path.join(API_DIR, "schemas", NAMESPACE, SCHEMA_NAME, "versions")
    ver_dir = os.path.join(versions_dir, version)

    # The current version is regenerated in place: clear only its own dir (and
    # latest); superseded version dirs are committed static history.
    for stale in (ver_dir, os.path.join(versions_dir, "latest")):
        if os.path.isdir(stale):
            shutil.rmtree(stale)

    # Version bundle + per-class components
    write_json(os.path.join(ver_dir, "index.json"), bundle)
    component_records = []
    for name, component in sorted(components.items()):
        write_json(os.path.join(ver_dir, "components", f"{name}.json"), component)
        component_records.append({
            "component_name": name,
            "schema_id": component.get("$id", ""),
            "description": component.get("description", ""),
        })
    write_json(
        os.path.join(ver_dir, "components", "index.json"),
        {"pagination": make_pagination(len(component_records)),
         "results": component_records},
    )

    # latest/ is a FULL COPY of the current version (static hosting has no
    # symlinks — the registry site's own pattern).
    shutil.copytree(ver_dir, os.path.join(versions_dir, "latest"))

    # Version list: rows derived from the version directories on disk; the one
    # matching `version:` is current, every other committed dir is superseded.
    version_rows = []
    for d in sorted(os.listdir(versions_dir)):
        if d == "latest" or not os.path.isdir(os.path.join(versions_dir, d)):
            continue
        version_rows.append({
            "schema_name": SCHEMA_NAME,
            "version": d,
            "status": "current" if d == version else "superseded",
            "release_date": "",
            "contributors": ["databio"],
            "release_notes": "",
            "tags": {},
        })
    write_json(
        os.path.join(versions_dir, "index.json"),
        {"pagination": make_pagination(len(version_rows)),
         "results": version_rows},
    )

    # Schema list for the namespace
    write_json(
        os.path.join(API_DIR, "schemas", NAMESPACE, "index.json"),
        {
            "pagination": make_pagination(1),
            "results": [{
                "namespace": NAMESPACE,
                "schema_name": SCHEMA_NAME,
                "latest_released_version": version,
                "maintainers": ["databio"],
                "maturity_level": "draft",
            }],
        },
    )

    # Namespace list
    write_json(
        os.path.join(API_DIR, "namespaces", "index.json"),
        {
            "pagination": make_pagination(1),
            "results": [{
                "server": SERVER,
                "namespace_name": NAMESPACE,
                "contact_url": "https://databio.org",
            }],
        },
    )

    # Service info (GA4GH Service Info 1.0)
    write_json(
        os.path.join(API_DIR, "service-info", "index.json"),
        {
            "id": "org.databio.onga",
            "name": "ONGA Schema Registry",
            "type": {
                "group": "org.ga4gh",
                "artifact": "schema-registry",
                "version": "1.0.0",
            },
            "description": "A static GA4GH Schema Registry serving the ONGA "
                           "(Ontology for Genomic Annotations) LinkML schema "
                           "as JSON Schema.",
            "organization": {
                "name": "databio",
                "url": "https://databio.org",
            },
            "version": version,
            "environment": "production",
        },
    )

    # Manifest: every file under the api tree
    manifest_paths = []
    for root, _dirs, files in os.walk(API_DIR):
        for f in files:
            rel = os.path.relpath(os.path.join(root, f), API_DIR)
            if rel != "manifest.json":
                manifest_paths.append(rel)
    manifest_paths.sort()
    write_json(os.path.join(API_DIR, "manifest.json"), {"paths": manifest_paths})

    print(f"Registry API: {len(component_records)} components, "
          f"{len(version_rows)} version(s), current={version}")


if __name__ == "__main__":
    build()
