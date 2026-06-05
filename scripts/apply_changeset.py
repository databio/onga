#!/usr/bin/env python3
"""Apply a changeset.json to file_content.yaml.

Usage:
    python scripts/apply_changeset.py changeset.json
"""

import json
import sys
from pathlib import Path

try:
    from ruamel.yaml import YAML
except ImportError:
    print("ERROR: ruamel.yaml is required. Install with: pip install ruamel.yaml")
    sys.exit(1)


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "src" / "file_content.yaml"


def find_term_in_enums(data, term_name):
    for enum_name in ("DataType", "FeatureType"):
        enum = data.get("enums", {}).get(enum_name, {})
        pv = enum.get("permissible_values", {})
        if term_name in pv:
            return enum_name, pv
    return None, None


def apply_merge(data, op):
    from_term = op["from"]
    into_term = op["into"]

    from_enum, from_pv = find_term_in_enums(data, from_term)
    into_enum, into_pv = find_term_in_enums(data, into_term)

    if not from_enum:
        print(f"  SKIP merge: '{from_term}' not found")
        return False
    if not into_enum:
        print(f"  SKIP merge: '{into_term}' not found")
        return False

    into_entry = into_pv[into_term]
    if "see_also" not in into_entry:
        into_entry["see_also"] = []
    if from_term not in into_entry["see_also"]:
        into_entry["see_also"].append(from_term)

    del from_pv[from_term]
    print(f"  MERGE '{from_term}' -> '{into_term}'")
    return True


def apply_delete(data, op):
    term = op["term"]
    enum_name, pv = find_term_in_enums(data, term)
    if not enum_name:
        print(f"  SKIP delete: '{term}' not found")
        return False
    del pv[term]
    print(f"  DELETE '{term}' from {enum_name}")
    return True


def apply_edit_description(data, op):
    term = op["term"]
    enum_name, pv = find_term_in_enums(data, term)
    if not enum_name:
        print(f"  SKIP edit_description: '{term}' not found")
        return False
    pv[term]["description"] = op["description"]
    print(f"  EDIT description of '{term}'")
    return True


def apply_adopt_mapping(data, op):
    term = op["term"]
    enum_name, pv = find_term_in_enums(data, term)
    if not enum_name:
        print(f"  SKIP adopt_mapping: '{term}' not found")
        return False
    pv[term]["meaning"] = op["meaning"]
    print(f"  MAP '{term}' -> {op['meaning']}")
    return True


def apply_add_see_also(data, op):
    term = op["term"]
    enum_name, pv = find_term_in_enums(data, term)
    if not enum_name:
        print(f"  SKIP add_see_also: '{term}' not found")
        return False
    entry = pv[term]
    if "see_also" not in entry:
        entry["see_also"] = []
    if op["see_also"] not in entry["see_also"]:
        entry["see_also"].append(op["see_also"])
    print(f"  SEE_ALSO '{term}' -> '{op['see_also']}'")
    return True


def apply_recategorize(data, op):
    term = op["term"]
    enum_name, pv = find_term_in_enums(data, term)
    if not enum_name:
        print(f"  SKIP recategorize: '{term}' not found")
        return False
    entry = pv[term]
    new_subset = op.get("to_subset")
    if "in_subset" in entry:
        entry["in_subset"] = [new_subset]
    else:
        entry["in_subset"] = [new_subset]
    print(f"  RECATEGORIZE '{term}' -> {new_subset}")
    return True


HANDLERS = {
    "merge": apply_merge,
    "delete": apply_delete,
    "edit_description": apply_edit_description,
    "adopt_mapping": apply_adopt_mapping,
    "add_see_also": apply_add_see_also,
    "recategorize": apply_recategorize,
}


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <changeset.json>")
        sys.exit(1)

    changeset_path = Path(sys.argv[1])
    if not changeset_path.exists():
        print(f"ERROR: {changeset_path} not found")
        sys.exit(1)

    changeset = json.loads(changeset_path.read_text())
    operations = changeset.get("operations", [])
    if not operations:
        print("No operations in changeset.")
        sys.exit(0)

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 120

    print(f"Loading {SCHEMA_PATH}...")
    data = yaml.load(SCHEMA_PATH)

    counts = {}
    applied = 0
    for op in operations:
        op_type = op.get("op")
        handler = HANDLERS.get(op_type)
        if not handler:
            print(f"  SKIP unknown op: {op_type}")
            continue
        if handler(data, op):
            counts[op_type] = counts.get(op_type, 0) + 1
            applied += 1

    if applied == 0:
        print("No operations applied.")
        sys.exit(0)

    print(f"\nWriting {SCHEMA_PATH}...")
    yaml.dump(data, SCHEMA_PATH)

    print(f"\nApplied {applied} operations:")
    for op_type, count in sorted(counts.items()):
        print(f"  {op_type}: {count}")


if __name__ == "__main__":
    main()
