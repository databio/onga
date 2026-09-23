"""The subject registry: every reviewable thing in the schema, with a permanent id.

One subject per term, enum, class, slot, slot-usage override, subset and module.
A subject id (SID) is `<kind>:<key>` and is opaque: no code may split one to
recover a part, so every record also carries `kind`, `name` and its container.

    term:<term id>                 term:ONGA_0000123
    enum:<EnumName>                enum:FeatureType
    class:<ClassName>              class:GenomicAnnotationFile
    slot:<slot_name>               slot:file_id
    usage:<ClassName>/<slot_name>  usage:GenomicAnnotationFile/file_label
    subset:<subset_name>           subset:signal_track
    module:<module_name>           module:genomic_annotation_file

A slot's SID is its global name (LinkML slot names are one namespace), so an
inherited slot has one subject however many classes reach it. `usage:` exists
only where a `slot_usage:` override is authored.

`hash` covers the authored source of truth only (`payload`), never a
projection: a term's payload holds its SSSOM rows, not the `*_mappings` slots
or `element_type` annotations projected from them.

Stdlib + pyyaml only.
"""
import hashlib
import json
import re
from urllib.parse import quote

import yaml

from . import ids
from .mappings import all_rows

ROOT = ids.ROOT
SRC = ids.SRC
KINDS = ("module", "subset", "enum", "term", "class", "slot", "usage")
TERM_KEYS = ("description", "in_subset", "aliases", "keywords", "status")
MODULE_KEYS = ("id", "name", "title", "description", "imports")
SSSOM_KEYS = (("predicate", "predicate_id"), ("object", "object_id"),
              ("modifier", "predicate_modifier"),
              ("justification", "mapping_justification"),
              ("fit", "element_type_fit"), ("comment", "comment"))


class RegistryError(Exception):
    pass


def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str)


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def slug(kind, key):
    return kind + "-" + re.sub(r"[^a-z0-9]+", "-", key.lower()).strip("-")


def load_modules():
    """{module name: parsed YAML} for every src/*.yaml except the lint config."""
    out = {}
    for path in sorted(SRC.glob("*.yaml")):
        if path.name == "linkml_lint_config.yaml":
            continue
        out[path.stem] = yaml.safe_load(open(path)) or {}
    return out


def module_layer(mod_name, data):
    layer = (data.get("annotations") or {}).get("onga_layer")
    if not isinstance(layer, int):
        raise RegistryError(f"src/{mod_name}.yaml has no integer annotations.onga_layer")
    return layer


def _term_id(pv):
    meaning = str((pv or {}).get("meaning") or "")
    return meaning.split(":", 1)[1] if ids.MEANING_RE.match(meaning) else None


def _ranges(slot_def):
    """Every range named by a slot body (range, any_of / exactly_one_of ranges)."""
    out = []
    if slot_def.get("range"):
        out.append(slot_def["range"])
    for key in ("any_of", "exactly_one_of", "all_of", "none_of"):
        for branch in slot_def.get(key) or []:
            if (branch or {}).get("range"):
                out.append(branch["range"])
    return out


def build():
    """(records {sid: record}, crosswalk {"labels": ..., "legacy": ...})."""
    modules = load_modules()
    layers = {m: module_layer(m, d) for m, d in modules.items()}
    classes, slots, enums, subsets = {}, {}, {}, {}
    for mod, d in modules.items():
        for kind, pool in (("classes", classes), ("slots", slots),
                           ("enums", enums), ("subsets", subsets)):
            for name, body in (d.get(kind) or {}).items():
                if name in pool:
                    raise RegistryError(f"{kind[:-1]} {name!r} is defined in both "
                                        f"{pool[name][0]} and {mod}")
                pool[name] = (mod, body or {})

    # SSSOM rows by term id.
    sssom = {}
    for fname, r in all_rows():
        sid = r.get("subject_id", "")
        tid = sid.split(":", 1)[1] if ids.MEANING_RE.match(sid) else None
        if tid is None:
            raise RegistryError(f"mappings/{fname}: subject_id {sid!r} is not a term id")
        sssom.setdefault(tid, []).append(
            {k: (r.get(col) or "") for k, col in SSSOM_KEYS})

    records = {}

    def add(kind, key, name, mod, payload, **extra):
        sid = f"{kind}:{key}"
        if sid in records:
            raise RegistryError(f"duplicate subject {sid}")
        rec = {"sid": sid, "kind": kind, "name": name,
               "module": mod, "layer": layers.get(mod) if mod else None,
               "file": f"src/{mod}.yaml" if mod else None,
               "slug": slug(kind, key), "retired": False,
               "payload": payload, "hash": sha256(canonical(payload))}
        rec.update(extra)
        records[sid] = rec
        return rec

    # Inheritance: ancestors through is_a and mixins, transitively.
    def parents(cname):
        body = classes.get(cname, (None, {}))[1]
        return ([body["is_a"]] if body.get("is_a") else []) + list(body.get("mixins") or [])

    def ancestors(cname, seen=None):
        seen = set() if seen is None else seen
        for p in parents(cname):
            if p not in seen:
                seen.add(p)
                ancestors(p, seen)
        return seen

    anc = {c: ancestors(c) for c in classes}
    descendants = {c: sorted(d for d in classes if c in anc[d]) for c in classes}

    # Modules.
    for mod, d in modules.items():
        payload = {k: d[k] for k in MODULE_KEYS if k in d}
        payload["onga_layer"] = layers[mod]
        members = sorted(
            [f"class:{c}" for c, (m, _) in classes.items() if m == mod]
            + [f"slot:{s}" for s, (m, _) in slots.items() if m == mod]
            + [f"enum:{e}" for e, (m, _) in enums.items() if m == mod]
            + [f"subset:{s}" for s, (m, _) in subsets.items() if m == mod])
        add("module", mod, mod, mod, payload, container=None, members=members)

    # Enums and terms.
    subset_members = {s: [] for s in subsets}
    labels, legacy = {}, {}
    for ename, (mod, body) in enums.items():
        member_ids = []
        for label, pv in (body.get("permissible_values") or {}).items():
            pv = pv or {}
            tid = _term_id(pv)
            if tid is None:
                raise RegistryError(f"{ename} {label!r} has no onga:ONGA_NNNNNNN meaning")
            member_ids.append(tid)
            see_also = []
            for ref in pv.get("see_also") or []:
                ref = str(ref)
                see_also.append(ref.split(":", 1)[1] if ids.MEANING_RE.match(ref) else ref)
            payload = {"label": label, "enum": ename, "see_also": see_also,
                       "sssom": sorted(sssom.get(tid, []), key=canonical)}
            payload.update({k: pv[k] for k in TERM_KEYS if k in pv})
            for s in pv.get("in_subset") or []:
                if s not in subset_members:
                    raise RegistryError(f"{ename} {label!r} is in undefined subset {s!r}")
                subset_members[s].append(tid)
            add("term", tid, tid, mod, payload, label=label, term_id=tid,
                enum=ename, container=f"enum:{ename}")
            _crosswalk(labels, legacy, tid, ename, label)
        payload = {k: v for k, v in body.items() if k != "permissible_values"}
        payload["members"] = member_ids
        add("enum", ename, ename, mod, payload, container=f"module:{mod}",
            members=[f"term:{t}" for t in member_ids],
            referenced_by=sorted(f"slot:{s}" for s, (_, b) in slots.items()
                                 if ename in _ranges(b)))

    # Retired terms (ledger only).
    live = {r["name"] for r in records.values() if r["kind"] == "term"}
    for row in ids.read_ledger():
        tid = row["id"]
        if row["status"] == "live":
            if tid not in live:
                raise RegistryError(f"ledger says {tid} is live, but no value has it")
            continue
        payload = {"label": row.get("label", ""), "enum": row.get("enum", ""),
                   "status": row["status"], "replaced_by": row.get("replaced_by", ""),
                   "decision": row.get("decision", "")}
        rec = add("term", tid, tid, None, payload, label=row.get("label", ""),
                  term_id=tid, enum=row.get("enum", ""), container=None)
        rec["retired"] = True
        if row.get("label"):
            _crosswalk(labels, legacy, tid, row.get("enum", ""), row["label"])
    for row in ids.read_ledger():
        for former in filter(None, (row.get("former_labels") or "").split("|")):
            _crosswalk(labels, legacy, row["id"], row.get("enum", ""), former)

    # Subsets.
    for sname, (mod, body) in subsets.items():
        members = sorted(subset_members[sname])
        payload = {"description": body.get("description", ""), "members": members}
        add("subset", sname, sname, mod, payload, container=f"module:{mod}",
            members=[f"term:{t}" for t in members])

    # Classes, slots, usages.
    listers = {s: [] for s in slots}
    for cname, (mod, body) in classes.items():
        for s in body.get("slots") or []:
            if s not in listers:
                raise RegistryError(f"class {cname} lists undefined slot {s!r}")
            listers[s].append(cname)
    for cname, (mod, body) in classes.items():
        add("class", cname, cname, mod, body, container=f"module:{mod}",
            inherited_by=descendants[cname],
            referenced_by=sorted(f"slot:{s}" for s, (_, b) in slots.items()
                                 if cname in _ranges(b)))
        for sname, usage in (body.get("slot_usage") or {}).items():
            add("usage", f"{cname}/{sname}", sname, mod, usage or {},
                container=f"class:{cname}", owner_class=cname)
    for sname, (mod, body) in slots.items():
        used_by = sorted(listers[sname])
        inherited = sorted(c for c in classes if c not in used_by
                           and any(a in used_by for a in anc[c]))
        add("slot", sname, sname, mod, body, container=f"module:{mod}",
            defined_in=mod, owner_class=used_by[0] if len(used_by) == 1 else None,
            used_by=used_by, inherited_by=inherited)

    slugs = {}
    for sid, rec in records.items():
        if rec["slug"] in slugs:
            raise RegistryError(f"slug {rec['slug']!r} is shared by {slugs[rec['slug']]} and {sid}")
        slugs[rec["slug"]] = sid

    order = {k: i for i, k in enumerate(KINDS)}
    records = dict(sorted(records.items(), key=lambda kv: (order[kv[1]["kind"]], kv[0])))
    return records, {"labels": dict(sorted(labels.items())),
                     "legacy": dict(sorted(legacy.items()))}


def _crosswalk(labels, legacy, tid, enum, label):
    """Record every reference form a label ever had, pointing at its term id."""
    if labels.get(label, tid) != tid:
        raise RegistryError(f"label {label!r} maps to both {labels[label]} and {tid}")
    labels[label] = tid
    under = label.replace(" ", "_")
    forms = [f"onga:{under}", f"{ids.ONGA_BASE}{under}"]
    if enum:
        forms.append(f"{ids.ONGA_BASE}{enum}#{quote(label)}")
    for form in forms:
        if legacy.get(form, tid) != tid:
            raise RegistryError(f"legacy form {form!r} maps to both {legacy[form]} and {tid}")
        legacy[form] = tid


def counts(records):
    out = {k: 0 for k in KINDS}
    retired = 0
    for rec in records.values():
        if rec["retired"]:
            retired += 1
        else:
            out[rec["kind"]] += 1
    out = {k: out[k] for k in ("term", "enum", "class", "slot", "usage", "subset", "module")}
    out["total"] = sum(out.values())
    if retired:
        out["retired_term"] = retired
    return out


def live_counts():
    """The same counts, taken straight from the YAML (the assertion's other side)."""
    modules = load_modules()
    n = {"term": 0, "enum": 0, "class": 0, "slot": 0, "usage": 0, "subset": 0,
         "module": len(modules)}
    for d in modules.values():
        n["enum"] += len(d.get("enums") or {})
        n["term"] += sum(len((e or {}).get("permissible_values") or {})
                         for e in (d.get("enums") or {}).values())
        n["class"] += len(d.get("classes") or {})
        n["usage"] += sum(len((c or {}).get("slot_usage") or {})
                          for c in (d.get("classes") or {}).values())
        n["slot"] += len(d.get("slots") or {})
        n["subset"] += len(d.get("subsets") or {})
    n["total"] = sum(n.values())
    return n


def fingerprint(records):
    lines = sorted(f"{sid}:{rec['hash']}" for sid, rec in records.items())
    return sha256("\n".join(lines))
