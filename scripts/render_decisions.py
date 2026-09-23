#!/usr/bin/env python3
"""Render the generated blocks of DECISIONS.md.

Hand-written prose (operations #1-#20, the design principles, the notes) is
never touched. Three blocks between markers are generated:

  <!-- BEGIN GENERATED: current-state -->       counts and class lists, from
                                                curation/subjects.json
  <!-- BEGIN GENERATED: atomic-by-principle -->  the "Atomic by principle" table:
                                                the transitional rows in
                                                curation/atomic_by_principle.transitional.md
                                                plus one row per keep_atomic record
  <!-- BEGIN GENERATED: cleanup-decisions -->   every applied decision that wrote
                                                something, numbered from #21

No program reads DECISIONS.md outside the markers. The first run inserts the
marker pairs at their sections; later runs only rewrite what is between them.

  python scripts/render_decisions.py           # rewrite the blocks
  python scripts/render_decisions.py --check   # exit 1 if a block is stale
"""
import argparse
import json
import re
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent))
from workbench.mappings import HAS_ELEMENT_TYPE, NO_TERM_FOUND, load_policy, read_sssom  # noqa: E402
from workbench.store import load_verdicts, plain_records  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "DECISIONS.md"
CURATION = ROOT / "curation"
ATOMIC_ROWS = CURATION / "atomic_by_principle.transitional.md"
FIRST_NUMBER = 21
BLOCKS = ("current-state", "atomic-by-principle", "cleanup-decisions")


def begin(name):
    return f"<!-- BEGIN GENERATED: {name} (scripts/render_decisions.py; do not edit) -->"


def end(name):
    return f"<!-- END GENERATED: {name} -->"


def block_re(name):
    return re.compile(re.escape(begin(name)) + r"\n.*?" + re.escape(end(name)), re.S)


# ---------------------------------------------------------------- inputs

def load():
    reg = json.loads((CURATION / "subjects.json").read_text())["subjects"]
    aliases = json.loads((CURATION / "subject_aliases.json").read_text())
    decs = plain_records(CURATION / "decisions.yaml")
    return reg, aliases, decs


def resolve(sid, aliases):
    seen = set()
    while sid in aliases and sid not in seen:
        seen.add(sid)
        sid = aliases[sid]
    return sid


def display(sid, reg, aliases):
    s = reg.get(resolve(sid, aliases))
    if s is None:
        return f"`{sid}`"
    if s["kind"] == "term":
        return f"`{s['label']}` ({s['term_id']})"
    return f"{s['kind']} `{s['name']}`"


# ---------------------------------------------------------------- blocks

def current_state(reg):
    live = [s for s in reg.values() if not s["retired"]]
    terms = [s for s in live if s["kind"] == "term"]

    def pos(t):
        return [r for r in t["payload"].get("sssom") or [] if r.get("modifier") != "Not"]

    def edam(t):
        return any(r["object"].startswith("edam:") for r in pos(t))

    def annotated(t):
        return any(r["predicate"] == HAS_ELEMENT_TYPE or
                   (r["predicate"] == "skos:relatedMatch" and r["object"].startswith("SO:"))
                   for r in pos(t))

    def so_class(t):
        return any(r["predicate"] == HAS_ELEMENT_TYPE and r["object"] != NO_TERM_FOUND
                   for r in pos(t))

    lines = []
    content = {}
    for enum in ("DataType", "FeatureType"):
        ts = [t for t in terms if t["enum"] == enum]
        content[enum] = ts
        lines.append(f"- **{enum}:** {len(ts)} terms ({sum(map(edam, ts))} EDAM-mapped, "
                     f"{sum(map(annotated, ts))} with an `element_type` annotation)")
    both = content["DataType"] + content["FeatureType"]
    n_so = sum(map(so_class, both))
    n_ann = sum(map(annotated, both))
    subsets = sum(1 for s in live if s["kind"] == "subset")
    lines.append(f"- **Categories:** {subsets} subsets")
    lines.append(f"- **Total:** {len(both)} terms, {sum(map(edam, both))} EDAM-mapped, "
                 f"{n_ann} element-type-annotated ({n_so} with an SO class, "
                 f"{n_ann - n_so} `not_applicable`)")
    ids = sorted(t["term_id"] for t in terms)
    retired = sum(1 for s in reg.values() if s["kind"] == "term" and s["retired"])
    lines.append(f"- **Term ids:** {len(ids)} live (`{ids[0]}` … `{ids[-1]}`), "
                 f"{retired} retired; one per permissible value in every enum, as "
                 "`meaning: onga:ONGA_NNNNNNN` (ledger `curation/term_ids.tsv`)")
    rows = read_sssom(ROOT / "mappings" / "so.sssom.tsv")
    rows = [r for r in rows if (r.get("predicate_modifier") or "") != "Not"]
    policy = load_policy()
    counts = {
        "SO element-type rows": sum(1 for r in rows if r["predicate_id"] == HAS_ELEMENT_TYPE
                                    and r["object_id"] != NO_TERM_FOUND),
        "SO relatedMatch rows": sum(1 for r in rows if r["predicate_id"] == "skos:relatedMatch"),
        "SO set-to-set rows": sum(1 for r in rows if r["predicate_id"] in policy["banned_skos"]
                                  and r["object_id"] in policy["set_denoting_so"]),
        "SO sequence-attribute rows": sum(1 for r in rows if r["predicate_id"] in policy["banned_skos"]
                                          and r["object_id"] in policy["sequence_attribute_so"]),
    }
    lines += [f"- **{k}:** {v}" for k, v in counts.items()]
    names = {1: "Vocabularies (Layer 1)", 2: "Descriptor schemas (Layer 2)",
             3: "Record classes (Layer 3)", 4: "Investigation classes (Layer 4)"}
    for layer, title in names.items():
        classes = sorted(s["name"] for s in live if s["kind"] == "class" and s["layer"] == layer)
        enums = sorted(s["name"] for s in live if s["kind"] == "enum" and s["layer"] == layer)
        parts = []
        if classes:
            parts.append(f"{len(classes)} class{'es' if len(classes) != 1 else ''}: "
                         + ", ".join(classes))
        if enums:
            parts.append(f"{len(enums)} enum{'s' if len(enums) != 1 else ''}: " + ", ".join(enums))
        if parts:
            lines.append(f"- **{title}:** " + "; ".join(parts))
    kinds = {}
    for s in live:
        kinds[s["kind"]] = kinds.get(s["kind"], 0) + 1
    lines.append("- **Subjects:** " + ", ".join(f"{kinds.get(k, 0)} {k}"
                 for k in ("term", "enum", "class", "slot", "usage", "subset", "module")))
    return "\n".join(lines)


def atomic(reg, aliases, decs):
    lines = ATOMIC_ROWS.read_text().rstrip("\n").splitlines()
    for d in decs:
        if d.get("verdict") != "keep_atomic" or d.get("status") == "withdrawn":
            continue
        s = reg.get(resolve(d["subject"], aliases)) or {}
        reason = " ".join(str(d.get("rationale") or "").split()).replace("|", "\\|")
        lines.append(f"| `{s.get('label', d['subject'])}` | {s.get('enum', '')} | "
                     f"{reason} ({d['id']}) |")
    return "\n".join(lines)


def cleanup(reg, aliases, decs):
    verdicts = load_verdicts()
    kind_of = {sid: s["kind"] for sid, s in reg.items()}
    applied = []
    for d in decs:
        if d.get("status") != "applied":
            continue
        kind = kind_of.get(resolve(d["subject"], aliases))
        entry = verdicts.get(kind, {}).get(d["verdict"], {})
        if entry.get("writes", "none") == "none":
            continue
        applied.append((str((d.get("applied") or {}).get("on")), d["id"], d, entry))
    applied.sort(key=lambda x: (x[0], x[1]))
    lines = []
    for n, (on, dec_id, d, entry) in enumerate(applied, start=FIRST_NUMBER):
        op = {k: v for k, v in (d.get("operation") or {}).items() if k != "op"}
        op_txt = ", ".join(f"{k}: {v}" for k, v in op.items())
        rationale = " ".join(str(d.get("rationale") or "").split())
        also = d.get("also_affects") or []
        head = f"- **#{n}. {entry.get('label', d['verdict'])}: {display(d['subject'], reg, aliases)}**"
        if also:
            head += " (also " + ", ".join(display(s, reg, aliases) for s in also) + ")"
        lines.append(f"{head} ({dec_id}, applied {on}). {rationale}"
                     + (f" Operation: `{op_txt}`." if op_txt else ""))
    return "\n".join(lines)


# ---------------------------------------------------------------- markers

def insert_markers(text):
    """Wrap the three sections in marker pairs (first run only)."""
    def wrap(name, body):
        return f"{begin(name)}\n{body}\n{end(name)}"

    if begin("current-state") not in text:
        m = re.search(r"(## Current state\n\n)(- \*\*DataType:\*\*.*?\n)(- \*\*Registry API:\*\*)",
                      text, re.S)
        if not m:
            sys.exit("render_decisions: cannot find the Current state list to wrap")
        text = text[:m.start(2)] + wrap("current-state", m.group(2).rstrip("\n")) + "\n" + text[m.start(3):]
    if begin("atomic-by-principle") not in text:
        m = re.search(r"(\| Axis / terms \|.*?\n)(?=\n)", text, re.S)
        if not m:
            sys.exit("render_decisions: cannot find the Atomic by principle table to wrap")
        if not ATOMIC_ROWS.exists():
            ATOMIC_ROWS.write_text(m.group(1))
        text = text[:m.start(1)] + wrap("atomic-by-principle", m.group(1).rstrip("\n")) + "\n" + text[m.end(1):]
    if begin("cleanup-decisions") not in text:
        if "## Cleanup decisions" not in text:
            sys.exit("render_decisions: no Cleanup decisions section")
        text = text.rstrip("\n") + "\n\n" + wrap("cleanup-decisions", "") + "\n"
    return text


def render(text):
    reg, aliases, decs = load()
    bodies = {"current-state": current_state(reg),
              "atomic-by-principle": atomic(reg, aliases, decs),
              "cleanup-decisions": cleanup(reg, aliases, decs)}
    for name, body in bodies.items():
        inner = f"{body}\n" if body else ""
        text = block_re(name).sub(lambda _: f"{begin(name)}\n{inner}{end(name)}", text)
    return text


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="exit 1 if a generated block is stale")
    args = ap.parse_args()
    before = DOC.read_text()
    if args.check:
        missing = [b for b in BLOCKS if begin(b) not in before]
        if missing:
            print(f"render_decisions --check: DECISIONS.md has no {missing} block; "
                  "run `make decisions`")
            sys.exit(1)
        if render(before) != before:
            print("render_decisions --check: DECISIONS.md generated blocks are stale; "
                  "run `make decisions`")
            sys.exit(1)
        print("DECISIONS.md generated blocks OK")
        return
    after = render(insert_markers(before))
    if after != before:
        DOC.write_text(after)
    print("DECISIONS.md generated blocks rendered" + ("" if after != before else " (no change)"))


if __name__ == "__main__":
    main()
