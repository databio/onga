#!/usr/bin/env python3
"""Schema linter: machine findings over every subject kind.

Reads only `curation/subjects.json`, `src/*.yaml` (for attached comments), the
mapping TSVs, `curation/usage.json`, `curation/decisions.yaml` (for
`keep_atomic`, when present) and `curation/policy.yaml` (thresholds, severity,
suggested verdict per rule). Writes `curation/findings/schema_lint.json`:

  {_generated_by, schema_fingerprint, counts: {rule: n},
   findings: [{id, rule, severity, message, subjects: [sid...], suggested_verdict}]}

A finding's id is `lint:<rule>:` + sha1 of its sorted subject SIDs (first 10
hex), so it is stable across runs and survives unrelated edits. One finding per
(rule, subject set); several hits on one subject are listed in its message.

  python scripts/schema_lint.py           # write the findings
  python scripts/schema_lint.py --check   # exit 1 if they would change
"""
import argparse
import csv
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
MAPPINGS = ROOT / "mappings"
CURATION = ROOT / "curation"
SUBJECTS = CURATION / "subjects.json"
USAGE = CURATION / "usage.json"
DECISIONS = CURATION / "decisions.yaml"
POLICY = CURATION / "policy.yaml"
OUT = CURATION / "findings" / "schema_lint.json"

CONTENT_ENUMS = ("DataType", "FeatureType")
FACET_TSV = MAPPINGS / "facet_decomposition.tsv"
FACET_NON_AXIS = {"encode_term", "output_type", "feature_type", "base_exists"}
MAPPING_KEYS = ("exact_mappings", "close_mappings", "broad_mappings",
                "narrow_mappings", "related_mappings", "mappings")
SECTIONS = ("classes", "slots", "enums", "subsets")


def _tsv(path):
    with open(path) as fh:
        return list(csv.DictReader(
            (line for line in fh if not line.startswith("#")), delimiter="\t"))


def _desc(s):
    return (s["payload"].get("description") or "").strip()


def _norm(text):
    return re.sub(r"\s+", " ", text).strip().lower()


class Linter:
    def __init__(self):
        data = json.loads(SUBJECTS.read_text())
        self.fingerprint = data["schema_fingerprint"]
        self.all = list(data["subjects"].values())
        self.subjects = [s for s in self.all if not s.get("retired")]
        self.by_sid = {s["sid"]: s for s in self.subjects}
        self.of_kind = defaultdict(list)
        for s in self.subjects:
            self.of_kind[s["kind"]].append(s)
        self.term_by_label = {(s["enum"], s["label"]): s["sid"] for s in self.of_kind["term"]}
        self.module_layer = {s["name"]: s["layer"] for s in self.of_kind["module"]}
        self.class_layer = {s["name"]: s["layer"] for s in self.of_kind["class"]}
        self.enums = {s["name"] for s in self.of_kind["enum"]}
        pol = yaml.safe_load(POLICY.read_text())["lint"]
        self.pol = pol
        self.markers = [re.compile(p, re.I) for p in pol["todo_markers"]]
        self.usage = json.loads(USAGE.read_text())
        self.keep_atomic = set()
        if DECISIONS.exists():
            for d in (yaml.safe_load(DECISIONS.read_text()) or {}).get("decisions") or []:
                if d.get("verdict") == "keep_atomic" and d.get("status") != "withdrawn":
                    self.keep_atomic.add(d["subject"])
        self.findings = {}

    # -- helpers -----------------------------------------------------------
    def emit(self, rule, sids, message):
        sids = sorted(set(sids))
        missing = [s for s in sids if s not in self.by_sid]
        if missing:
            sys.exit(f"schema_lint: rule {rule} names unknown subjects {missing}")
        key = hashlib.sha1("\n".join(sids).encode()).hexdigest()[:10]
        fid = f"lint:{rule}:{key}"
        if fid in self.findings:
            self.findings[fid]["message"] += f"; {message}"
            return
        cfg = self.pol["rules"][rule]
        self.findings[fid] = {
            "id": fid, "rule": rule, "severity": cfg["severity"], "message": message,
            "subjects": sids, "suggested_verdict": cfg["suggested_verdict"],
        }

    def positive_rows(self, term):
        return [r for r in term["payload"].get("sssom") or []
                if (r.get("modifier") or "") != "Not"]

    def is_content(self, s):
        return s["kind"] == "term" and s["enum"] in CONTENT_ENUMS

    # -- slot rules --------------------------------------------------------
    def slot_rules(self):
        for s in self.of_kind["slot"]:
            p, sid, name = s["payload"], s["sid"], s["name"]
            if p.get("required") and not p.get("identifier"):
                self.emit("required-policy", [sid],
                          f"slot {name} is required but is not an identifier; "
                          "every required slot is a cost to adopters")
            if not s.get("used_by") and not s.get("inherited_by"):
                self.emit("unused-slot", [sid], f"slot {name} is listed by no class")
            if len(s.get("used_by") or []) > 1:
                self.emit("shared-slot", [sid],
                          f"slot {name} is listed by {', '.join(s['used_by'])}; "
                          "confirm the meaning is shared")
            if not p.get("examples"):
                self.emit("slot-no-examples", [sid], f"slot {name} has no examples")
            rng = p.get("range")
            if rng in self.class_layer:
                own = self.module_layer[s["module"]]
                if self.class_layer[rng] > own:
                    self.emit("layer-violation", [sid, f"class:{rng}"],
                              f"slot {name} (layer {own}) ranges on {rng} "
                              f"(layer {self.class_layer[rng]})")

    # -- mapping rules -----------------------------------------------------
    def doc_link_rule(self):
        for s in self.of_kind["class"] + self.of_kind["slot"]:
            for key in MAPPING_KEYS:
                for v in s["payload"].get(key) or []:
                    prefix = v.split(":", 1)[0] if ":" in v else ""
                    if prefix.endswith("_info") or v.endswith(".html"):
                        self.emit("mapping-target-is-doc-link", [s["sid"]],
                                  f"{s['kind']} {s['name']} {key} value {v} is a "
                                  "documentation page, not a term")

    def term_rules(self):
        facet_labels = self.facet_value_labels()
        facet_words = [w.lower() for w in self.pol["facet_words"]]
        examples = self.slot_example_values()
        decomposed = self.decomposed_facet_values()
        high = self.pol["high_usage_files"]
        for t in self.of_kind["term"]:
            sid, label = t["sid"], t["label"]
            if not _desc(t):
                self.emit("enum-value-no-description", [sid],
                          f"{t['enum']} value '{label}' has no description")
            for r in t["payload"].get("sssom") or []:
                if r.get("justification") == "semapv:UnspecifiedMatching":
                    self.emit("unreviewed-mapping", [sid],
                              f"'{label}' {r['predicate']} {r['object']} "
                              "has no mapping justification")
            if t["enum"] in facet_labels:
                if label not in decomposed and label not in examples:
                    self.emit("orphan-facet-value", [sid],
                              f"{t['enum']} value '{label}' appears in no facet "
                              "decomposition row and no slot example")
            if not self.is_content(t):
                continue
            hits = sorted({v for vals in facet_labels.values() for v in vals
                           if _word_in(v, label)} |
                          {w for w in facet_words if _word_in(w, label)})
            if hits and sid not in self.keep_atomic:
                self.emit("residual-compound", [sid],
                          f"'{label}' contains facet word(s) {', '.join(hits)} "
                          "and has no keep_atomic decision")
            positive = self.positive_rows(t)
            if not positive:
                self.emit("no-mapping-at-all", [sid], f"'{label}' has no SSSOM mapping")
            files = self.usage[sid]["encode_files"]
            if files == 0:
                self.emit("zero-usage-term", [sid], f"'{label}' has no ENCODE files")
            elif files >= high and not positive:
                self.emit("unmapped-high-usage", [sid],
                          f"'{label}' has {files} ENCODE files and no SSSOM mapping")

    def facet_value_labels(self):
        """{facet enum: {labels}} for the facet vocabularies named in policy.yaml."""
        out = {e: set() for e in self.pol["facet_enums"]}
        for t in self.of_kind["term"]:
            if t["enum"] in out:
                out[t["enum"]].add(t["label"])
        return out

    def decomposed_facet_values(self):
        vals = set()
        for r in _tsv(FACET_TSV):
            for k, v in r.items():
                if k not in FACET_NON_AXIS and v and v.strip():
                    vals.add(v.strip())
        return vals

    def slot_example_values(self):
        vals = set()
        for s in self.of_kind["slot"]:
            for ex in s["payload"].get("examples") or []:
                if isinstance(ex, dict) and ex.get("value") is not None:
                    vals.add(str(ex["value"]))
        return vals

    # -- enum, class, subset, module rules -----------------------------------
    def enum_rules(self):
        for e in self.of_kind["enum"]:
            if not e.get("referenced_by"):
                self.emit("unused-enum", [e["sid"]], f"enum {e['name']} is the range of no slot")
            mod = next(m for m in self.of_kind["module"] if m["name"] == e["module"])
            if any(c["module"] == mod["name"] for c in self.of_kind["class"]):
                self.emit("inline-enum", [e["sid"]],
                          f"enum {e['name']} is defined inside class module {mod['name']}")

    def class_rules(self):
        for c in self.of_kind["class"]:
            p = c["payload"]
            if (str(p.get("source") or "").startswith("https://w3id.org/fga-wg/")
                    and not p.get("conforms_to")
                    and not any(p.get(k) for k in MAPPING_KEYS)):
                self.emit("class-no-alignment", [c["sid"]],
                          f"ported class {c['name']} has no conforms_to and no mappings")

    def subset_rules(self):
        big = self.pol["oversized_subset"]
        for s in self.of_kind["subset"]:
            n = len(s.get("members") or [])
            if n == 1:
                self.emit("singleton-subset", [s["sid"]], f"subset {s['name']} has one member")
            elif n > big:
                self.emit("oversized-subset", [s["sid"]],
                          f"subset {s['name']} has {n} members (> {big})")

    # -- description rules -------------------------------------------------
    def description_rules(self):
        terse = self.pol["terse_description_chars"]
        seen = defaultdict(list)
        for s in self.of_kind["term"] + self.of_kind["slot"] + self.of_kind["class"]:
            d = _desc(s)
            if d and len(d) < terse:
                self.emit("terse-description", [s["sid"]],
                          f"{s['kind']} {s['name']} description is {len(d)} chars "
                          f"(< {terse})")
            if d:
                seen[_norm(d)].append(s["sid"])
        for d, sids in seen.items():
            if len(sids) > 1:
                self.emit("duplicate-description", sids,
                          f"{len(sids)} subjects share the description '{d[:60]}'")
        for s in self.of_kind["module"] + self.of_kind["enum"]:
            sentences = [x for x in re.split(r"(?<=[.!?])\s+", _norm(_desc(s))) if len(x) >= 40]
            dup = sorted({x for x in sentences if sentences.count(x) > 1})
            if dup:
                self.emit("duplicate-paragraph", [s["sid"]],
                          f"{s['kind']} {s['name']} description repeats '{dup[0][:60]}'")

    def todo_rules(self):
        for s in self.subjects:
            d = _desc(s)
            if any(m.search(d) for m in self.markers):
                self.emit("todo-marker", [s["sid"]],
                          f"{s['kind']} {s['name']} description carries a TODO/placeholder marker")
        for path in sorted(SRC.glob("*.yaml")):
            if path.name == "linkml_lint_config.yaml":
                continue
            for lineno, comment, ctx in _comments(path):
                if any(m.search(comment) for m in self.markers):
                    sid = self.context_sid(path.stem, ctx)
                    self.emit("todo-marker", [sid],
                              f"{path.name}:{lineno} comment '{comment.strip()[:80]}'")

    def context_sid(self, module, path):
        """Map a YAML key path to the innermost subject; fall back to the module."""
        cands = []
        if len(path) >= 2 and path[0] in SECTIONS:
            kind = {"classes": "class", "slots": "slot", "enums": "enum", "subsets": "subset"}[path[0]]
            cands.append(f"{kind}:{path[1]}")
            if path[0] == "enums" and len(path) >= 4 and path[2] == "permissible_values":
                cands.insert(0, self.term_by_label.get((path[1], path[3])))
            if path[0] == "classes" and len(path) >= 4 and path[2] == "slot_usage":
                cands.insert(0, f"usage:{path[1]}/{path[3]}")
        cands.append(f"module:{module}")
        return next(c for c in cands if c in self.by_sid)

    def run(self):
        self.slot_rules()
        self.doc_link_rule()
        self.term_rules()
        self.enum_rules()
        self.class_rules()
        self.subset_rules()
        self.description_rules()
        self.todo_rules()
        findings = sorted(self.findings.values(), key=lambda f: (f["rule"], f["id"]))
        counts = defaultdict(int)
        for f in findings:
            counts[f["rule"]] += 1
        return {
            "_generated_by": "scripts/schema_lint.py",
            "schema_fingerprint": self.fingerprint,
            "counts": {r: counts.get(r, 0) for r in sorted(self.pol["rules"])},
            "findings": findings,
        }


def _word_in(word, label):
    return re.search(r"(?<![\w-])" + re.escape(word.lower()) + r"(?![\w-])", label.lower()) is not None


_KEY = re.compile(r"""^( *)(?:- +)?(['"]?)([^'"#:][^#]*?)\2:(?:\s|$)""")


def _comments(path):
    """Yield (lineno, comment text, key path of the element it is attached to).

    A comment attaches to the element of the line just above it; a comment
    preceded by a blank line (a free-standing block) attaches to the next
    element below it. Full-line and trailing comments are both scanned.
    """
    lines = path.read_text().splitlines()
    ctx, stack = [None] * len(lines), []
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(stripped)
        while stack and stack[-1][0] >= indent:
            stack.pop()
        m = _KEY.match(line)
        if m and not stripped.startswith("-"):
            stack.append((indent, m.group(3).strip()))
            ctx[i] = [k for _, k in stack]
        else:
            ctx[i] = [k for _, k in stack]
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            comment = stripped
        elif "#" in line and ctx[i] is not None and re.search(r"\s#\s", line):
            yield i + 1, line[line.index(" #") + 2:], ctx[i]
            continue
        else:
            continue
        above = next((j for j in range(i - 1, -1, -1)
                      if lines[j].strip() and not lines[j].lstrip().startswith("#")), None)
        blank_before = i > 0 and not lines[i - 1].strip()
        if above is not None and not blank_before:
            yield i + 1, comment, ctx[above]
            continue
        below = next((ctx[j] for j in range(i + 1, len(lines))
                      if ctx[j] and len(ctx[j]) >= 2), [])
        yield i + 1, comment, below


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if curation/findings/schema_lint.json would change")
    args = ap.parse_args()
    data = Linter().run()
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    summary = "schema lint: " + " ".join(f"{r}={n}" for r, n in data["counts"].items() if n) \
        + f" total={len(data['findings'])}"
    if args.check:
        if not OUT.exists() or OUT.read_text() != text:
            print(f"schema_lint --check: {OUT.relative_to(ROOT)} is stale; run `make lint-schema`")
            sys.exit(1)
        print(f"{summary} (up to date)")
        return
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(text)
    print(summary)


if __name__ == "__main__":
    main()
