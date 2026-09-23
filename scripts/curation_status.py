#!/usr/bin/env python3
"""Curation status: a state and a queue score for every subject.

Reads `curation/subjects.json`, `curation/decisions.yaml`,
`curation/subject_aliases.json`, `curation/findings/*.json`, the embeddings
reports (`embeddings/outputs/reports/{internal_similarity,gap_analysis,
mapping_report}.json`), `curation/usage.json`, `proposals/upstream_requests.yaml`,
`curation/machine_definitions.yaml` (when present) and `curation/policy.yaml`
(`queue:` weights, `status:` severities). Writes `curation/status.json`:

  {_generated_by, schema_fingerprint,
   sources:  [{path, findings, stale}],          # every findings input
   subjects: {sid: {kind, container, layer, retired, state, open_findings,
                    decisions, latest, signals, score}},
   rollups:  {overall, by_kind, by_layer, by_container}  # counts by state + percent_settled
   queue:    [sid ...]}                          # open | stale | unreviewed, score desc

States: unreviewed (no decision, no open finding), open (an open finding and no
terminal decision), deferred (newest decision is `defer`), settled (terminal,
not stale), applied (settled and `status: applied`), stale (the newest terminal
decision's recorded hash differs from the current one: `applied.subject_hashes_after`
for an applied record, `subject_hashes` for a pending one).

A finding is open for a subject unless a live (non-withdrawn) terminal decision
covers the subject or cites the finding in its evidence. A `map:` suggestion is
also closed once the term has any SSSOM row (positive or `Not`) for its object.
Findings files whose `schema_fingerprint` differs from subjects.json count as
stale and contribute no findings.

  python scripts/curation_status.py           # write curation/status.json
  python scripts/curation_status.py --check   # exit 1 if it would change
"""
import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from workbench.store import load_verdicts  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CURATION = ROOT / "curation"
SUBJECTS = CURATION / "subjects.json"
DECISIONS = CURATION / "decisions.yaml"
ALIASES = CURATION / "subject_aliases.json"
FINDINGS_DIR = CURATION / "findings"
USAGE = CURATION / "usage.json"
POLICY = CURATION / "policy.yaml"
VERDICTS = CURATION / "verdicts.yaml"
MACHINE_DEFS = CURATION / "machine_definitions.yaml"
UPSTREAM = ROOT / "proposals" / "upstream_requests.yaml"
REPORTS = ROOT / "embeddings" / "outputs" / "reports"
EMBEDDING_REPORTS = ("internal_similarity.json", "gap_analysis.json", "mapping_report.json")
OUT = CURATION / "status.json"

STATES = ("unreviewed", "open", "deferred", "settled", "applied", "stale")
QUEUE_STATES = ("open", "stale", "unreviewed")
ADOPTION_ROOT = "class:GenomicAnnotationFile"
PORT_SOURCE = "https://w3id.org/fga-wg/"


def rel(p):
    return str(Path(p).relative_to(ROOT))


def load_yaml(path, default=None):
    if not Path(path).exists():
        return default
    return yaml.safe_load(Path(path).read_text()) or default


# ---------------------------------------------------------------- findings

def embedding_findings(name, data):
    """Normalized findings out of one embeddings report."""
    out = []
    if name == "internal_similarity.json":
        for p in data.get("pairs") or []:
            out.append({"id": p["id"], "source": "embeddings", "rule": "similar-terms",
                        "subjects": p["subjects"],
                        "message": f"{p['term1']} ~ {p['term2']} "
                                   f"(similarity {p['similarity']}; {p.get('machine_recommendation')})"})
    elif name == "gap_analysis.json":
        for group in (data.get("by_subset") or {}).values():
            for t in group.get("terms") or []:
                out.append({"id": t["id"], "source": "embeddings", "rule": "coverage-gap",
                            "subjects": t["subjects"],
                            "message": f"{t['onga_term']}: no ontology match "
                                       f"(best similarity {t['max_similarity']})"})
    elif name == "mapping_report.json":
        for t in data.get("terms") or []:
            for m in t.get("suggested_mappings") or []:
                out.append({"id": m["id"], "source": "embeddings", "rule": "mapping-suggestion",
                            "subjects": m["subjects"], "object": m["term_id"],
                            "message": f"{t['onga_term']} -> {m['term_id']} {m['term_name']} "
                                       f"({m['match_type']}, {m['similarity']})"})
    return out


def load_findings(fingerprint, severity_of):
    """([finding], [source summary]). Each finding: id, rule, severity, subjects, message."""
    findings, sources = [], []
    for path in sorted(FINDINGS_DIR.glob("*.json")):
        data = json.loads(path.read_text())
        stale = data.get("schema_fingerprint") != fingerprint
        items = [] if stale else data.get("findings") or []
        sources.append({"path": rel(path), "findings": len(items), "stale": stale})
        findings += [{**f, "source": path.stem} for f in items]
    for name in EMBEDDING_REPORTS:
        path = REPORTS / name
        if not path.exists():
            continue
        data = json.loads(path.read_text())
        prov = data.get("provenance")
        if not prov:
            continue  # pre-provenance reports are treated as absent
        stale = prov.get("schema_fingerprint") != fingerprint
        items = [] if stale else embedding_findings(name, data)
        for f in items:
            f["severity"] = severity_of[f["rule"]]
        sources.append({"path": rel(path), "findings": len(items), "stale": stale})
        findings += items
    return findings, sources


# ---------------------------------------------------------------- signals

def effective_slots(cname, subjects):
    """Slot names a class lists or inherits (is_a + mixins, transitively)."""
    out, seen, todo = [], set(), [cname]
    while todo:
        c = todo.pop()
        if c in seen:
            continue
        seen.add(c)
        body = (subjects.get(f"class:{c}") or {}).get("payload") or {}
        out += body.get("slots") or []
        todo += ([body["is_a"]] if body.get("is_a") else []) + list(body.get("mixins") or [])
    return out


def slot_ranges(body):
    rs = [body["range"]] if body.get("range") else []
    for key in ("any_of", "exactly_one_of", "all_of", "none_of"):
        rs += [b["range"] for b in body.get(key) or [] if (b or {}).get("range")]
    return rs


def adoption_path(subjects):
    """SIDs reachable from GenomicAnnotationFile through effective slots and
    their class and enum ranges; ancestors of a reached class and the terms
    of a reached enum are reached too."""
    reach, todo = set(), [ADOPTION_ROOT]
    while todo:
        sid = todo.pop()
        if sid in reach or sid not in subjects:
            continue
        reach.add(sid)
        s = subjects[sid]
        if s["kind"] == "class":
            for slot in effective_slots(s["name"], subjects):
                todo.append(f"slot:{slot}")
            body = s["payload"]
            todo += [f"class:{c}" for c in ([body["is_a"]] if body.get("is_a") else [])
                     + list(body.get("mixins") or [])]
        elif s["kind"] == "slot":
            for r in slot_ranges(s["payload"]):
                todo += [f"class:{r}", f"enum:{r}"]
        elif s["kind"] == "enum":
            todo += s.get("members") or []
    return reach


def impact(subjects, usage):
    """{sid: 0..1}, normalized within each kind."""
    raw = {}
    slot_classes = {sid: set(s.get("used_by") or []) | set(s.get("inherited_by") or [])
                    for sid, s in subjects.items() if s["kind"] == "slot"}
    for sid, s in subjects.items():
        k = s["kind"]
        if k == "term":
            raw[sid] = (usage.get(sid) or {}).get("encode_files", 0)
        elif k == "class":
            users = set()
            for slot in s.get("referenced_by") or []:
                users |= slot_classes.get(slot, set())
            raw[sid] = len(users) + len(s.get("inherited_by") or [])
        elif k == "slot":
            raw[sid] = len(slot_classes[sid])
        elif k == "enum":
            raw[sid] = len(s.get("referenced_by") or [])
        elif k in ("subset", "module"):
            raw[sid] = len(s.get("members") or [])
        else:
            raw[sid] = 0
    top = defaultdict(int)
    for sid, v in raw.items():
        top[subjects[sid]["kind"]] = max(top[subjects[sid]["kind"]], v)
    out = {}
    for sid, v in raw.items():
        k = subjects[sid]["kind"]
        log = math.log10 if k == "term" else math.log2
        out[sid] = round(log(1 + v) / log(1 + top[k]), 4) if top[k] else 0.0
    return out


def upstream_terms(labels):
    """Term SIDs named in upstream requests (motivating_terms, onga_terms)."""
    data = load_yaml(UPSTREAM, {})
    out = set()

    def walk(node):
        if isinstance(node, dict):
            for key in ("motivating_terms", "onga_terms"):
                for t in node.get(key) or []:
                    label = t.get("term") if isinstance(t, dict) else t
                    if label in labels:
                        out.add(f"term:{labels[label]}")
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
    walk(data)
    return out


def machine_terms(subjects):
    """Term SIDs whose description still matches curation/machine_definitions.yaml."""
    data = load_yaml(MACHINE_DEFS, {})
    out = set()
    for entry in (data.get("definitions") or []) if isinstance(data, dict) else []:
        sid = entry.get("subject")
        s = subjects.get(sid)
        if s and (s["payload"].get("description") or "").strip() == (entry.get("description") or "").strip():
            out.add(sid)
    return out


def port_subjects(subjects):
    """Classes sourced from the FGA-WG schema, plus slots and enums defined in their modules."""
    classes = {sid for sid, s in subjects.items() if s["kind"] == "class"
               and str(s["payload"].get("source") or "").startswith(PORT_SOURCE)}
    modules = {subjects[sid]["module"] for sid in classes}
    return classes | {sid for sid, s in subjects.items()
                      if s["kind"] in ("slot", "enum") and s["module"] in modules}


# ---------------------------------------------------------------- status

def resolve(sid, aliases):
    seen = set()
    while sid in aliases and sid not in seen:
        seen.add(sid)
        sid = aliases[sid]
    return sid


def build():
    reg = json.loads(SUBJECTS.read_text())
    fingerprint, subjects = reg["schema_fingerprint"], reg["subjects"]
    policy = load_yaml(POLICY)
    w, spol = policy["queue"], policy["status"]
    points = spol["severity_points"]
    terminal = {(k, v): e["terminal"] for k, vs in load_verdicts(VERDICTS).items()
                for v, e in vs.items()}
    aliases = json.loads(ALIASES.read_text()) if ALIASES.exists() else {}
    aliases = {k: v for k, v in aliases.items() if not k.startswith("_")}
    xwalk = json.loads((CURATION / "term_crosswalk.json").read_text())["labels"]
    usage = json.loads(USAGE.read_text()) if USAGE.exists() else {}

    findings, sources = load_findings(fingerprint, spol["finding_severity"])

    # Decisions per subject, oldest first.
    decs = (load_yaml(DECISIONS, {}) or {}).get("decisions") or []
    by_subject = defaultdict(list)
    for d in decs:
        if d.get("status") == "withdrawn":
            continue
        for sid in [d["subject"], *(d.get("also_affects") or [])]:
            by_subject[resolve(sid, aliases)].append(d)
    cited = defaultdict(set)   # finding id -> subjects covered by a citing terminal decision

    def is_terminal(d, sid):
        kind = (subjects.get(resolve(d["subject"], aliases)) or subjects.get(sid) or {}).get("kind")
        return terminal.get((kind, d["verdict"]), d["verdict"] != "defer")

    for sid, ds in by_subject.items():
        for d in ds:
            if is_terminal(d, sid):
                for ev in d.get("evidence") or []:
                    if ev.get("id"):
                        cited[ev["id"]].add(sid)

    findings_of = defaultdict(list)
    for f in findings:
        for sid in f["subjects"]:
            findings_of[resolve(sid, aliases)].append(f)

    reach = adoption_path(subjects)
    imp = impact(subjects, usage)
    upstream = upstream_terms(xwalk)
    machine = machine_terms(subjects)
    port = port_subjects(subjects)

    out = {}
    for sid, s in subjects.items():
        ds = by_subject.get(sid, [])
        terms_ = [d for d in ds if is_terminal(d, sid)]
        latest = ds[-1] if ds else None
        last_t = terms_[-1] if terms_ else None
        stale = False
        if last_t is not None:
            if last_t.get("status") == "applied":
                recorded = ((last_t.get("applied") or {}).get("subject_hashes_after") or {})
            else:
                recorded = last_t.get("subject_hashes") or {}
            h = recorded.get(sid)
            if h is None:  # recorded under an alias
                h = next((v for k, v in recorded.items() if resolve(k, aliases) == sid), None)
            stale = h is not None and h != s["hash"]
        sssom_objects = {r.get("object") for r in s["payload"].get("sssom") or []} \
            if s["kind"] == "term" else set()
        open_f = []
        for f in findings_of.get(sid, []):
            if last_t is not None and not stale:
                continue
            if sid in cited.get(f["id"], ()):
                continue
            if f.get("object") and f["object"] in sssom_objects:
                continue
            open_f.append(f)
        if latest is not None and latest["verdict"] == "defer":
            state = "deferred"
        elif stale:
            state = "stale"
        elif last_t is not None:
            state = "applied" if last_t.get("status") == "applied" else "settled"
        elif open_f:
            state = "open"
        else:
            state = "unreviewed"
        signals = {
            "findings": min(10, sum(points[f["severity"]] for f in open_f)),
            "impact": imp.get(sid, 0.0),
            "adoption": int(sid in reach),
            "required": int(s["kind"] == "slot" and bool(s["payload"].get("required"))),
            "port": int(sid in port and last_t is None),
            "upstream": int(sid in upstream),
            "stale": int(stale),
            "machine": int(sid in machine),
        }
        score = round(sum(w[k] * v for k, v in signals.items()), 4)
        out[sid] = {
            "kind": s["kind"], "container": s.get("container"), "layer": s.get("layer"),
            "retired": bool(s.get("retired")), "state": state,
            "open_findings": sorted({f["id"] for f in open_f}),
            "decisions": [d["id"] for d in ds],
            "latest": latest["id"] if latest else None,
            "signals": signals, "score": score,
        }

    live = {sid: r for sid, r in out.items() if not r["retired"]}

    def rollup(rows):
        c = {st: 0 for st in STATES}
        for r in rows:
            c[r["state"]] += 1
        total = sum(c.values())
        done = c["settled"] + c["applied"]
        return {**c, "total": total,
                "percent_settled": round(100 * done / total, 1) if total else 0.0}

    groups = {"by_kind": defaultdict(list), "by_layer": defaultdict(list),
              "by_container": defaultdict(list)}
    for r in live.values():
        groups["by_kind"][r["kind"]].append(r)
        groups["by_layer"][str(r["layer"])].append(r)
        if r["container"]:
            groups["by_container"][r["container"]].append(r)
    rollups = {"overall": rollup(live.values())}
    for name, g in groups.items():
        rollups[name] = {k: rollup(v) for k, v in sorted(g.items())}

    queue = sorted((sid for sid, r in live.items() if r["state"] in QUEUE_STATES),
                   key=lambda sid: (-live[sid]["score"], sid))
    return {
        "_generated_by": "scripts/curation_status.py (make status); do not edit",
        "schema_fingerprint": fingerprint,
        "weights": w,
        "sources": sources,
        "subjects": out,
        "rollups": rollups,
        "queue": queue,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if curation/status.json would change")
    args = ap.parse_args()
    data = build()
    text = json.dumps(data, indent=1, ensure_ascii=False, default=str) + "\n"
    o = data["rollups"]["overall"]
    summary = (f"status: {o['total']} subjects, " + " ".join(f"{s}={o[s]}" for s in STATES)
               + f", {o['percent_settled']}% settled, queue {len(data['queue'])}")
    if args.check:
        if not OUT.exists() or OUT.read_text() != text:
            print(f"curation_status --check: {rel(OUT)} is stale; run `make status`")
            sys.exit(1)
        print(f"{summary} (up to date)")
        return
    OUT.write_text(text)
    print(summary)


if __name__ == "__main__":
    main()
