#!/usr/bin/env node
/**
 * Build JSON data files from ONGA LinkML schema for Astro site.
 *
 * ONGA has four layers:
 *   Layer 1 — Vocabularies (closed value sets): 3 core (DataType, FeatureType,
 *     Format) + 8 facet (StrandOrientation, ReadMultiplicity, FilterStatus,
 *     Normalization, Thresholding, Derivation, ReferenceBuildSex,
 *     HaplotypeResolution) = 11 hand-curated, plus 3 small structural enums
 *     (ValueType, AccessProtocol, BiospecimenClassification).
 *   Layer 2 — Track descriptor schemas (classes of slots): TrackFormat (#1,
 *     encoding), TrackInterpretation (#2, meaning), TrackProvenance (what was
 *     done to the data — processing/derivation operations), TrackGeometry (#3,
 *     shape), ReferenceGenome (the reference assembly a track is defined
 *     against, seqcol digests + build sex) = 5 total.
 *   Layer 3 — Record classes (a record about ONE file): GenomicAnnotationFile
 *     (composes the descriptors) + File and its DRS-shaped components
 *     (Checksum, AccessMethod, AccessURL, InputSource, QualityAssessment) and
 *     helpers (Term, Any).
 *   Layer 4 — Investigation classes (the research/publishing context):
 *     Experiment, Study, Analysis, Sample, Donor, Contact, Deposit, Document,
 *     FileCollection, TopLevel.
 *
 * Layer 1 vocabularies keep their hand-curated pages; Layers 2-4 classes and
 * the structural enums are rendered by the GENERIC schema browser pages under
 * /schema, driven by the schema/ JSON emitted here (buildSchemaBrowser) —
 * adding a class to src/ must produce a page with zero new hand-written Astro.
 */

import { readFileSync, writeFileSync, existsSync, mkdirSync, readdirSync } from 'fs';
import { parse } from 'yaml';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const schemaDir = join(__dirname, '../../src');
const dataDir = join(__dirname, '../src/data');
const developDir = join(dataDir, 'develop');
const mappingsDir = join(__dirname, '../../mappings');
const reportsDir = join(__dirname, '../../embeddings/outputs/reports');
const frequencyTsv = join(__dirname, '../../encode-term-use-frequency/seed_term_frequency.tsv');
const proposalsDir = join(__dirname, '../../proposals');
const curationDir = join(__dirname, '../../curation');

function readYaml(filename) {
  const path = join(schemaDir, filename);
  if (!existsSync(path)) {
    console.warn(`Warning: ${filename} not found`);
    return null;
  }
  return parse(readFileSync(path, 'utf-8'));
}

// Read an SSSOM TSV BY HEADER NAME (robust to column insertion), skipping the
// YAML-in-comments header block.
function readSssom(path) {
  if (!existsSync(path)) return [];
  const lines = readFileSync(path, 'utf-8')
    .split(/\r?\n/)
    .filter(l => l.trim() && !l.startsWith('#'));
  if (lines.length < 2) return [];
  const header = lines[0].split('\t').map(h => h.trim());
  return lines.slice(1).map(line => {
    const cells = line.split('\t');
    const row = {};
    header.forEach((h, i) => { row[h] = (cells[i] || '').trim(); });
    return row;
  });
}

// SSSOM subject_id is the term's permanent id, onga:ONGA_NNNNNNN (the `meaning:`
// of the permissible value), so every mapping is keyed by that id.
function ongaIdOf(curie) {
  const m = /^onga:(ONGA_\d{7})$/.exec(String(curie || ''));
  return m ? m[1] : null;
}

function readMappings() {
  const mappings = {};
  for (const r of readSssom(join(mappingsDir, 'edam.sssom.tsv'))) {
    if (!r.subject_id || !r.object_id) continue;
    mappings[ongaIdOf(r.subject_id)] = {
      predicate: (r.predicate_id || '').replace('skos:', '') || 'relatedMatch',
      edamId: r.object_id,
      edamLabel: r.object_label || '',
      comment: r.comment || ''
    };
  }
  return mappings;
}

// ONGA -> Sequence Ontology. NOT a SKOS mapping set: ONGA terms denote SETS of
// genomic elements and SO classes denote INDIVIDUAL element types, so membership
// rows use onga:has_element_type with an element_type_fit grade. skos:relatedMatch
// means the members are NOT instances; skos:exactMatch/closeMatch appear only for
// the two whitelisted SO classes that are themselves set-denoting. See the ADR
// "ONGA terms denote sets; SO terms denote elements".
// A term may have SEVERAL rows (a mixed set), so this is keyed ONGA id -> array.
function readSoMappings() {
  const byId = {};
  for (const r of readSssom(join(mappingsDir, 'so.sssom.tsv'))) {
    if (!r.subject_id || !r.object_id) continue;
    // Curated "no SO element type": carried by element_type_fit: not_applicable
    // on the term, not an SO class to list or link.
    if (r.object_id === 'sssom:NoTermFound') continue;
    const id = ongaIdOf(r.subject_id);
    const predicate = r.predicate_id || '';
    (byId[id] = byId[id] || []).push({
      predicate,
      // 'has_element_type' | 'exactMatch' | 'closeMatch' | 'relatedMatch'
      predicateShort: predicate.replace('skos:', '').replace('onga:', ''),
      soId: r.object_id,
      soLabel: r.object_label || '',
      fit: r.element_type_fit || '',
      subjectCategory: r.subject_category || '',
      objectCategory: r.object_category || '',
      comment: r.comment || ''
    });
  }
  return byId;
}

function soUrl(soId) {
  return `http://purl.obolibrary.org/obo/${String(soId).replace(':', '_')}`;
}

// ONGA id -> live label, over every enum in src/. see_also on a permissible
// value holds onga:ONGA_NNNNNNN CURIEs; this turns them back into names.
function termLabelsById() {
  const labels = {};
  for (const en of Object.values(loadAllModules().enums)) {
    for (const [name, data] of Object.entries(en.permissible_values || {})) {
      const id = ongaIdOf((data || {}).meaning);
      if (id) labels[id] = name;
    }
  }
  return labels;
}

function seeAlsoName(ref, labels) {
  const id = ongaIdOf(ref);
  if (!id || !labels[id]) throw new Error(`see_also ${ref} is not a live ONGA term id`);
  return labels[id];
}

function slugify(name) {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_|_$/g, '');
}

// EDAM cross-references on the value's *_mappings slots (projected from
// mappings/*.sssom.tsv). `meaning:` is the value's own ONGA id, never a
// cross-reference.
function schemaEdamMapping(data) {
  const slots = [
    ['exactMatch', data.exact_mappings],
    ['closeMatch', data.close_mappings],
    ['broadMatch', data.broad_mappings],
    ['relatedMatch', data.related_mappings],
  ];
  for (const [predicate, values] of slots) {
    const hit = (values || []).find(v => String(v).startsWith('edam:'));
    if (hit) return { predicate, edamId: hit, edamLabel: '', comment: 'From LinkML schema' };
  }
  return null;
}

// Any-prefix cross-reference declared inline in the schema (EDAM, SO, PATO, ...).
// The facet vocabularies (StrandOrientation -> SO, ReferenceBuildSex -> PATO)
// carry one of these, and rendering them as EDAM produced dead links, so they
// get their own field with a prefix-correct URL.
const CURIE_BASES = {
  edam: id => `http://edamontology.org/${id}`,
  SO: id => `http://purl.obolibrary.org/obo/SO_${id}`,
  PATO: id => `http://purl.obolibrary.org/obo/PATO_${id}`,
  UBERON: id => `http://purl.obolibrary.org/obo/UBERON_${id}`,
  CL: id => `http://purl.obolibrary.org/obo/CL_${id}`,
};

function curieUrl(curie) {
  const [prefix, local] = String(curie).split(':');
  const base = CURIE_BASES[prefix];
  return base && local ? base(local) : null;
}

function schemaCrossRef(data) {
  const slots = [
    ['exactMatch', data.exact_mappings],
    ['closeMatch', data.close_mappings],
    ['broadMatch', data.broad_mappings],
    ['relatedMatch', data.related_mappings],
  ];
  for (const [predicate, values] of slots) {
    const hit = (values || [])[0];
    if (hit) return { predicate, id: String(hit), url: curieUrl(hit) };
  }
  return null;
}

function processEnum(enumData, vocabType, edamMappings, soMappings = {}, labelsById = {}) {
  const terms = [];
  const termsByCategory = {};

  if (!enumData?.permissible_values) return { terms, termsByCategory };

  for (const [name, data] of Object.entries(enumData.permissible_values)) {
    const slug = slugify(name);
    const category = data.in_subset?.[0] || 'uncategorized';
    // The permanent id (ONGA_NNNNNNN), carried as `meaning: onga:ONGA_NNNNNNN`.
    const ongaId = ongaIdOf(data.meaning);
    if (!ongaId) throw new Error(`${name}: no meaning: onga:ONGA_NNNNNNN id`);

    const edamMapping = edamMappings[ongaId] || schemaEdamMapping(data);

    // The set/element layer: which SO class(es) the rows of this term instantiate.
    // `element_type` is a pipe-joined STRING of SO CURIEs (a YAML list stringifies
    // badly in gen-owl output); absent + fit 'not_applicable' means "reviewed, the
    // rows are not SO-typeable features", which is different from no annotation
    // at all ("not yet curated").
    const ann = data.annotations || {};
    const elementTypes = String(ann.element_type || '')
      .split('|').map(s => s.trim()).filter(Boolean);
    const rows = soMappings[ongaId] || [];
    const labelOf = id => (rows.find(r => r.soId === id) || {}).soLabel || '';
    const elementType = elementTypes.length
      ? {
          fit: ann.element_type_fit || '',
          classes: elementTypes.map(id => ({ id, label: labelOf(id), url: soUrl(id) })),
        }
      : null;
    const elementTypeFit = ann.element_type_fit || null;
    const soMapping = rows.map(r => ({ ...r, soUrl: soUrl(r.soId) }));
    const externalMapping = schemaCrossRef(data);

    const term = {
      id: slug,
      ongaId,
      name,
      slug,
      description: data.description || '',
      category,
      categorySlug: slugify(category),
      vocabType, // 'data' or 'feature'
      edamMapping,
      // Set/element layer (ADR: ONGA terms name SETS, SO classes name ELEMENTS).
      elementType,
      elementTypeFit,
      soMapping,
      externalMapping,
      // see_also holds onga:ONGA_NNNNNNN term ids; keywords holds free-text
      // related concepts that are not ONGA terms. The site shows both as plain
      // names, so resolve the ids to live labels and concatenate.
      seeAlso: [
        ...(data.see_also || []).map(ref => seeAlsoName(ref, labelsById)),
        ...(data.keywords || [])
      ],
      encodeSource: true
    };

    terms.push(term);

    if (!termsByCategory[category]) {
      termsByCategory[category] = [];
    }
    termsByCategory[category].push(term);
  }

  return { terms, termsByCategory };
}

// Process the TrackGeometry class + slots + rules into a flat list of
// geometry "properties". Unlike DataType/FeatureType (LinkML enums), this is a
// LinkML class whose slots are the vocabulary terms. We also derive a
// human-readable conditional rule for each slot from the class `rules`.
function processGeometry(schema) {
  const properties = [];
  const valueTypes = [];

  if (!schema?.classes?.TrackGeometry) return { properties, valueTypes };

  const cls = schema.classes.TrackGeometry;
  const slotDefs = schema.slots || {};

  // Surface the ValueType enum values (referenced by value_type / edge_weight_type).
  const valueTypeEnum = schema.enums?.ValueType;
  if (valueTypeEnum?.permissible_values) {
    for (const [name, data] of Object.entries(valueTypeEnum.permissible_values)) {
      valueTypes.push({ name, description: data.description || '' });
    }
  }

  // Build a map of slot -> human-readable rule summary derived from class rules.
  // Rules are of the form: if <precondition slot> is true, then <postcondition
  // slot(s)> are required. We attach a summary to each postcondition slot.
  const ruleSummaries = {};
  for (const rule of cls.rules || []) {
    const preSlots = Object.keys(rule.preconditions?.slot_conditions || {});
    const preLabel = preSlots.join(' and ');

    // Collect postcondition slots (directly or under all_of).
    const postSlots = [];
    const post = rule.postconditions || {};
    for (const slot of Object.keys(post.slot_conditions || {})) postSlots.push(slot);
    for (const branch of post.all_of || []) {
      for (const slot of Object.keys(branch.slot_conditions || {})) postSlots.push(slot);
    }

    for (const slot of postSlots) {
      ruleSummaries[slot] = `Required when ${preLabel} is true.`;
    }
  }

  // Classify edge-related vs feature-related for grouping in the UI.
  const isEdgeProp = (name) => name.startsWith('edge') || name.startsWith('edges');

  for (const name of cls.slots || []) {
    const def = slotDefs[name] || {};
    const slug = slugify(name);
    const group = isEdgeProp(name) ? 'edge properties' : 'feature properties';

    properties.push({
      id: slug,
      slug,
      name,
      description: def.description || '',
      range: def.range || schema.default_range || 'string',
      required: def.required === true,
      rule: ruleSummaries[name] || null,
      group,
      groupSlug: slugify(group),
    });
  }

  return { properties, valueTypes };
}

// Build a map of postcondition-slot -> human-readable rule summary from a
// class's `rules` block (shared shape with processGeometry).
function ruleSummariesFor(cls) {
  const ruleSummaries = {};
  for (const rule of cls.rules || []) {
    const preSlots = Object.keys(rule.preconditions?.slot_conditions || {});
    const preConds = rule.preconditions?.slot_conditions || {};
    const preLabel = preSlots
      .map(s => {
        const c = preConds[s];
        if (c?.equals_string !== undefined) return `${s} is ${c.equals_string}`;
        if (c?.equals_number !== undefined) return `${s} is true`;
        return s;
      })
      .join(' and ');

    const postSlots = [];
    const post = rule.postconditions || {};
    for (const slot of Object.keys(post.slot_conditions || {})) postSlots.push(slot);
    for (const branch of post.all_of || []) {
      for (const slot of Object.keys(branch.slot_conditions || {})) postSlots.push(slot);
    }
    for (const slot of postSlots) {
      ruleSummaries[slot] = `Recommended when ${preLabel}.`;
    }
  }
  return ruleSummaries;
}

// Process the TrackFormat class: its slots only. The Format vocabulary lives in
// its own file (format.yaml) and is processed via processEnum, exactly like
// DataType/FeatureType. Each slot whose range is the Format vocabulary carries
// the vocabulary's browse href + live term count (mirroring processInterpretation).
function processFormat(schema, vocabCounts) {
  const properties = [];

  if (!schema?.classes?.TrackFormat) return { properties };

  const cls = schema.classes.TrackFormat;
  const slotDefs = schema.slots || {};
  const ruleSummaries = ruleSummariesFor(cls);

  // Map a vocabulary range to the browse page + term count.
  const vocabLinks = {
    Format: { href: '/formats', count: vocabCounts.format },
  };

  for (const name of cls.slots || []) {
    const def = slotDefs[name] || {};
    const slug = slugify(name);
    const range = def.range || schema.default_range || 'string';
    const link = vocabLinks[range] || null;
    properties.push({
      id: slug,
      slug,
      name,
      description: def.description || '',
      range,
      required: def.required === true,
      rule: ruleSummaries[name] || null,
      vocabHref: link?.href || null,
      vocabCount: link?.count ?? null,
    });
  }

  return { properties };
}

// Process the TrackInterpretation class: its slots, each carrying the
// vocabulary range it draws on and that vocabulary's term count.
function processInterpretation(schema, vocabCounts) {
  const properties = [];

  if (!schema?.classes?.TrackInterpretation) return { properties };

  const cls = schema.classes.TrackInterpretation;
  const slotDefs = schema.slots || {};

  // Map a vocabulary range to the browse page + term count.
  const vocabLinks = {
    DataType: { href: '/data-types', count: vocabCounts.dataType },
    FeatureType: { href: '/feature-types', count: vocabCounts.featureType },
    StrandOrientation: { href: '/strand-orientation', count: vocabCounts.strandOrientation },
    HaplotypeResolution: { href: '/haplotype-resolution', count: vocabCounts.haplotypeResolution },
  };

  for (const name of cls.slots || []) {
    const def = slotDefs[name] || {};
    const slug = slugify(name);
    const range = def.range || schema.default_range || 'string';
    const link = vocabLinks[range] || null;
    properties.push({
      id: slug,
      slug,
      name,
      description: def.description || '',
      range,
      required: def.required === true,
      vocabHref: link?.href || null,
      vocabCount: link?.count ?? null,
    });
  }

  return { properties };
}

// Process the TrackProvenance class: its slots, each carrying the vocabulary
// range it draws on and that vocabulary's term count. Mirrors
// processInterpretation; read_multiplicity / filter_status moved here from
// TrackInterpretation (they describe what was *done* to the data).
function processProvenance(schema, vocabCounts) {
  const properties = [];

  if (!schema?.classes?.TrackProvenance) return { properties };

  const cls = schema.classes.TrackProvenance;
  const slotDefs = schema.slots || {};

  const vocabLinks = {
    ReadMultiplicity: { href: '/read-multiplicity', count: vocabCounts.readMultiplicity },
    FilterStatus: { href: '/filter-status', count: vocabCounts.filterStatus },
    Normalization: { href: '/normalization', count: vocabCounts.normalization },
    Thresholding: { href: '/thresholding', count: vocabCounts.thresholding },
    Derivation: { href: '/derivation', count: vocabCounts.derivation },
  };

  for (const name of cls.slots || []) {
    const def = slotDefs[name] || {};
    const slug = slugify(name);
    const range = def.range || schema.default_range || 'string';
    const link = vocabLinks[range] || null;
    properties.push({
      id: slug,
      slug,
      name,
      description: def.description || '',
      range,
      required: def.required === true,
      vocabHref: link?.href || null,
      vocabCount: link?.count ?? null,
    });
  }

  return { properties };
}

// Process the ReferenceGenome class (5th schema): its slots, each carrying the
// vocabulary range it draws on and that vocabulary's term count. Mirrors
// processProvenance; the build_sex slot links to the ReferenceBuildSex facet.
function processReferenceGenome(schema, vocabCounts) {
  const properties = [];

  if (!schema?.classes?.ReferenceGenome) return { properties };

  const cls = schema.classes.ReferenceGenome;
  const slotDefs = schema.slots || {};

  const vocabLinks = {
    ReferenceBuildSex: { href: '/reference-build-sex', count: vocabCounts.referenceBuildSex },
  };

  for (const name of cls.slots || []) {
    const def = slotDefs[name] || {};
    const slug = slugify(name);
    const range = def.range || schema.default_range || 'string';
    const link = vocabLinks[range] || null;
    properties.push({
      id: slug,
      slug,
      name,
      description: def.description || '',
      range,
      required: def.required === true,
      vocabHref: link?.href || null,
      vocabCount: link?.count ?? null,
    });
  }

  return { properties };
}

// Read the scope-boundary delegations (mappings/scope_delegations.tsv): sample/
// assay axes ONGA deliberately delegates OUT of content scope to external
// ontologies (UBERON/PATO). Emitted as delegations.json for the scope feature.
function readDelegations() {
  const path = join(mappingsDir, 'scope_delegations.tsv');
  if (!existsSync(path)) {
    console.warn('Warning: scope_delegations.tsv not found, scope feature will be empty');
    return [];
  }
  const lines = readFileSync(path, 'utf-8')
    .split(/\r?\n/)
    .filter(l => l.trim() && !l.startsWith('#'));
  if (lines.length < 2) return [];
  const header = lines[0].split('\t').map(h => h.trim());
  const idx = name => header.indexOf(name);
  return lines.slice(1).map(line => {
    const c = line.split('\t').map(v => v.trim());
    const curie = c[idx('external_curie')] || '';
    const [prefix, local] = curie.split(':');
    let externalUrl = null;
    if (prefix === 'UBERON' && local) externalUrl = `http://purl.obolibrary.org/obo/UBERON_${local}`;
    else if (prefix === 'PATO' && local) externalUrl = `http://purl.obolibrary.org/obo/PATO_${local}`;
    return {
      encodeTerm: c[idx('encode_term')],
      contentEnum: c[idx('content_enum')],
      contentBase: c[idx('content_base')],
      delegatedAxis: c[idx('delegated_axis')],
      delegatedValue: c[idx('delegated_value')],
      externalCurie: curie,
      externalUrl,
      note: c[idx('note')] || '',
    };
  });
}

// Read the upstream term requests (proposals/upstream_requests.yaml): concepts
// ONGA owns that an upstream ontology (currently SO) is missing, plus the
// concepts deliberately NOT sent upstream. This is the mirror image of
// scope_delegations.tsv — that file ejects axes OUT of ONGA's scope, this one
// pushes missing terms INTO an upstream ontology. Emitted as
// develop/upstream-requests.json for the so-proposals develop page.
//
// The YAML keys both `requests` and `rejections` by target ontology CURIE
// prefix so EDAM requests can land alongside SO ones later; we flatten both
// into arrays here, stamping the ontology onto each row.
function readUpstreamRequests() {
  const empty = {
    ontologies: {},
    requests: [],
    rejections: [],
    stats: { newTerms: 0, modifications: 0, proposedLabels: 0, rejectionGroups: 0, rejectedTerms: 0 },
  };
  const path = join(proposalsDir, 'upstream_requests.yaml');
  if (!existsSync(path)) {
    console.warn('Warning: proposals/upstream_requests.yaml not found, SO proposals page will be empty');
    return empty;
  }
  const doc = parse(readFileSync(path, 'utf-8'));
  const ontologies = doc.ontologies || {};

  // Resolve an ONGA term to its browse page, using the same slug rule
  // processEnum uses so the links line up with the generated term pages.
  const ongaTerm = (t) => {
    const slug = slugify(t.term || '');
    const base = t.category === 'DataType' ? '/data-types' : '/feature-types';
    return { term: t.term, category: t.category, slug, href: `${base}/${slug}` };
  };

  const purl = (id) => {
    if (!id || typeof id !== 'string' || !id.includes(':')) return null;
    const [prefix, local] = id.split(':');
    const base = ontologies[prefix]?.purl;
    return base ? `${base}${local}` : null;
  };

  const requests = [];
  for (const [ontology, list] of Object.entries(doc.requests || {})) {
    for (const r of list || []) {
      const isMod = r.kind === 'modification';
      const additional = r.additional_terms || [];
      requests.push({
        id: r.id,
        kind: r.kind,
        status: r.status || 'proposed',
        ontology,
        ontologyName: ontologies[ontology]?.name || ontology,
        tracker: ontologies[ontology]?.tracker || null,
        // Display label: the proposed label for a new term, the existing label
        // for a modification request.
        label: isMod ? (r.target?.label || '') : (r.proposed_label || ''),
        definition: r.proposed_definition || '',
        parent: r.parent
          ? { ...r.parent, url: purl(r.parent.id) }
          : null,
        target: r.target ? { ...r.target, url: purl(r.target.id) } : null,
        requestedChange: r.requested_change || '',
        additionalTerms: additional,
        rationale: r.rationale || '',
        existingRelatedTerms: (r.existing_related_terms || []).map(t => ({ ...t, url: purl(t.id) })),
        motivatingTerms: (r.motivating_terms || []).map(ongaTerm),
        dependsOn: r.depends_on || [],
        note: r.note || '',
        // A single request can ask for several labels at once (CpG/CHG/CHH).
        labelCount: isMod ? 0 : 1 + additional.length,
      });
    }
  }

  const rejections = [];
  for (const [ontology, list] of Object.entries(doc.rejections || {})) {
    for (const r of list || []) {
      const redirect = r.redirect || {};
      rejections.push({
        id: r.id,
        disposition: r.disposition,
        status: r.status || 'rejected',
        consideredFor: ontology,
        consideredForName: ontologies[ontology]?.name || ontology,
        redirectOntology: redirect.ontology || null,
        redirectName: redirect.name || redirect.ontology || null,
        redirectHomepage: ontologies[redirect.ontology]?.homepage || null,
        reason: r.reason || '',
        precedent: r.precedent || null,
        ongaTerms: (r.onga_terms || []).map(ongaTerm),
      });
    }
  }

  const stats = {
    newTerms: requests.filter(r => r.kind === 'new_term').length,
    modifications: requests.filter(r => r.kind === 'modification').length,
    proposedLabels: requests.reduce((s, r) => s + r.labelCount, 0),
    rejectionGroups: rejections.length,
    rejectedTerms: rejections.reduce((s, r) => s + r.ongaTerms.length, 0),
  };

  return { ontologies, requests, rejections, stats };
}

// ---------------------------------------------------------------------------
// Generic schema browser (Layers 2-4 + structural enums), approach ported from
// nsheff's schema-registry-site import_linkml.py: merge all src/*.yaml modules,
// resolve each class's effective slots (is_a inheritance, mixins, slot_usage
// overrides — matters now that GenomicAnnotationFile is_a File), classify each
// slot's range, compute forward references and inverse referenced_by, and emit
// per-class/per-enum JSON the dynamic /schema Astro routes render generically.
// ---------------------------------------------------------------------------

// Layer names. A module's layer comes from its `annotations.onga_layer` (see
// loadAllModules). Layer 1 vocabularies keep hand-curated pages; classes in
// Layers 2-4 (and the structural enums) get generic pages.
const LAYER_NAMES = { 1: 'Vocabulary', 2: 'Descriptor', 3: 'Record', 4: 'Investigation' };

// Enums with hand-curated browse pages (Layer-1 vocabularies). Slot ranges
// hitting these link there; everything else enum-shaped gets a generic page.
const VOCAB_ENUM_HREFS = {
  DataType: '/data-types',
  FeatureType: '/feature-types',
  Format: '/formats',
  StrandOrientation: '/strand-orientation',
  ReadMultiplicity: '/read-multiplicity',
  FilterStatus: '/filter-status',
  Normalization: '/normalization',
  Thresholding: '/thresholding',
  Derivation: '/derivation',
  ReferenceBuildSex: '/reference-build-sex',
  HaplotypeResolution: '/haplotype-resolution',
};

// Layer-2 descriptor classes keep their richer hand-written pages; slot ranges
// hitting them link there rather than to the generic class page.
const CLASS_HREF_OVERRIDES = {
  TrackFormat: '/track-format',
  TrackInterpretation: '/track-interpretation',
  TrackProvenance: '/track-provenance',
  TrackGeometry: '/track-geometry',
  ReferenceGenome: '/reference-genome',
};

// Each module's layer is data: the schema-level `annotations: {onga_layer: N}`
// in src/<module>.yaml (0 for the root onga.yaml).
function loadAllModules() {
  const classes = {};
  const slots = {};
  const enums = {};
  const moduleLayers = {};
  const fs = readdirSync(schemaDir);
  for (const fname of fs.sort()) {
    if (!fname.endsWith('.yaml') || fname === 'linkml_lint_config.yaml') continue;
    const data = parse(readFileSync(join(schemaDir, fname), 'utf-8'));
    if (!data) continue;
    const module = fname.replace(/\.yaml$/, '');
    const layer = data.annotations?.onga_layer;
    if (!Number.isInteger(layer)) throw new Error(`${fname}: no integer annotations.onga_layer`);
    moduleLayers[module] = layer;
    for (const [name, def] of Object.entries(data.classes || {})) {
      classes[name] = { ...(def || {}), _module: module };
    }
    for (const [name, def] of Object.entries(data.slots || {})) {
      slots[name] = { ...(def || {}), _module: module };
    }
    for (const [name, def] of Object.entries(data.enums || {})) {
      enums[name] = { ...(def || {}), _module: module };
    }
  }
  return { classes, slots, enums, moduleLayers };
}

function resolveClassSlots(clsName, classes, slots, fromParent = null) {
  const cls = classes[clsName] || {};
  const result = {};
  if (cls.is_a && classes[cls.is_a]) {
    Object.assign(result, resolveClassSlots(cls.is_a, classes, slots, cls.is_a));
  }
  for (const mixin of cls.mixins || []) {
    if (classes[mixin]) Object.assign(result, resolveClassSlots(mixin, classes, slots, mixin));
  }
  for (const slotName of cls.slots || []) {
    const def = { ...(slots[slotName] || {}) };
    const usage = (cls.slot_usage || {})[slotName];
    if (usage) Object.assign(def, usage);
    result[slotName] = { ...def, _name: slotName, _inheritedFrom: fromParent };
  }
  return result;
}

// Human-readable conditional-rule summaries per postcondition slot (same shape
// as ruleSummariesFor, kept separate so the browser can list whole rules too).
function ruleList(cls) {
  const rules = [];
  for (const rule of cls.rules || []) {
    const preConds = rule.preconditions?.slot_conditions || {};
    const pre = Object.keys(preConds).map(s => {
      const c = preConds[s];
      if (c?.equals_string !== undefined) return `${s} = "${c.equals_string}"`;
      if (c?.equals_number !== undefined) return `${s} is true`;
      if (c?.value_presence !== undefined) return `${s} is present`;
      return s;
    });
    const anyOfPre = (rule.preconditions?.any_of || []).flatMap(b =>
      Object.entries(b.slot_conditions || {}).map(([s, c]) =>
        c?.equals_string !== undefined ? `${s} = "${c.equals_string}"` : s));
    const preLabel = [...pre, ...(anyOfPre.length ? [anyOfPre.join(' or ')] : [])].join(' and ');

    const post = rule.postconditions || {};
    const postSlots = [
      ...Object.keys(post.slot_conditions || {}),
      ...(post.all_of || []).flatMap(b => Object.keys(b.slot_conditions || {})),
    ];
    if (post.exactly_one_of) {
      const alts = post.exactly_one_of.flatMap(b => Object.keys(b.slot_conditions || {}));
      rules.push({ summary: `Exactly one of ${alts.join(' / ')} is required.`, slots: alts });
    }
    if (postSlots.length) {
      rules.push({ summary: `When ${preLabel}: ${postSlots.join(', ')} required.`, slots: postSlots });
    }
  }
  return rules;
}

function buildSchemaBrowser() {
  const { classes, slots, enums, moduleLayers } = loadAllModules();
  const classNames = new Set(Object.keys(classes));
  const enumNames = new Set(Object.keys(enums));

  const classRecords = [];
  for (const [name, cls] of Object.entries(classes)) {
    const layer = moduleLayers[cls._module];
    if (layer < 2) continue; // Layer-1 files hold no classes, but be safe.
    const resolved = resolveClassSlots(name, classes, slots);
    const references = new Set();
    const slotRecords = Object.entries(resolved).map(([slotName, def]) => {
      const range = def.range || 'string';
      let rangeKind = 'scalar';
      let rangeHref = null;
      if (classNames.has(range)) {
        rangeKind = 'class';
        rangeHref = CLASS_HREF_OVERRIDES[range] || `/schema/class/${range}`;
        references.add(range);
      } else if (enumNames.has(range)) {
        rangeKind = 'enum';
        rangeHref = VOCAB_ENUM_HREFS[range] || `/schema/enum/${range}`;
        references.add(range);
      }
      return {
        name: slotName,
        description: def.description || '',
        range,
        rangeKind,
        rangeHref,
        required: def.required === true,
        recommended: def.recommended === true,
        multivalued: def.multivalued === true,
        identifier: def.identifier === true,
        inlined: def.inlined === true,
        inheritedFrom: def._inheritedFrom || null,
        pattern: def.pattern || null,
      };
    });
    slotRecords.sort((a, b) =>
      (b.identifier - a.identifier) || (b.required - a.required) ||
      (b.recommended - a.recommended) || a.name.localeCompare(b.name));

    classRecords.push({
      name,
      module: cls._module,
      layer,
      layerName: LAYER_NAMES[layer],
      description: cls.description || '',
      isA: cls.is_a || null,
      isAHref: cls.is_a ? (CLASS_HREF_OVERRIDES[cls.is_a] || `/schema/class/${cls.is_a}`) : null,
      href: CLASS_HREF_OVERRIDES[name] || `/schema/class/${name}`,
      // Provenance box: machine-readable lineage + external-standard alignment.
      conformsTo: cls.conforms_to || null,
      source: cls.source || null,
      seeAlso: cls.see_also || [],
      closeMappings: cls.close_mappings || [],
      exactMappings: cls.exact_mappings || [],
      rules: ruleList(cls),
      slots: slotRecords,
      references: [...references].sort(),
    });
  }

  // Inverse references
  for (const record of classRecords) {
    record.referencedBy = classRecords
      .filter(r => r.name !== record.name && r.references.includes(record.name))
      .map(r => ({ name: r.name, href: r.href }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }

  // Structural enums (everything without a hand-curated vocabulary page).
  const enumRecords = [];
  for (const [name, en] of Object.entries(enums)) {
    if (VOCAB_ENUM_HREFS[name]) continue;
    enumRecords.push({
      name,
      module: en._module,
      layer: 1,
      layerName: 'Vocabulary (structural)',
      description: en.description || '',
      source: en.source || null,
      seeAlso: en.see_also || [],
      values: Object.entries(en.permissible_values || {}).map(([v, def]) => ({
        name: v,
        description: (def || {}).description || '',
      })),
      referencedBy: classRecords
        .filter(r => r.references.includes(name))
        .map(r => ({ name: r.name, href: r.href }))
        .sort((a, b) => a.name.localeCompare(b.name)),
    });
  }

  classRecords.sort((a, b) => (a.layer - b.layer) || a.name.localeCompare(b.name));
  enumRecords.sort((a, b) => a.name.localeCompare(b.name));
  return { classes: classRecords, enums: enumRecords };
}

// ---------------------------------------------------------------------------
// Curation workbench data (site/src/data/develop/). The curation files under
// curation/ are generated by the Python tooling (make regen) and tracked, so
// the published site renders them with no daemon and no Python in CI.
//
// Emitted:
//   subjects.json, status.json, usage.json, pending.json   copies of curation/
//   verdicts.json, decisions.json, review_prompts.json     curation/*.yaml as JSON
//   lint.json          curation/findings/schema_lint.json (+ `stale`)
//   findings.json      {byId: {id: finding}}: lint + embeddings findings on live
//                      subjects, each {id, source, rule, severity, subjects,
//                      message, suggested_verdict?, object?}
//   subject-index.json {sid: compact row}: the one lookup pages and controls
//                      use (label, slug, href, browse, state, lint, prompts...)
//   queue.json         status queue joined with names, findings, latest decision
// ---------------------------------------------------------------------------

const EMBEDDING_REPORTS = ['internal_similarity.json', 'gap_analysis.json', 'mapping_report.json'];

function readCurationJson(rel) {
  const path = join(curationDir, rel);
  if (!existsSync(path)) throw new Error(`curation/${rel} is missing; run \`make regen\` in the onga repo`);
  return JSON.parse(readFileSync(path, 'utf-8'));
}

function readCurationYaml(rel) {
  const path = join(curationDir, rel);
  if (!existsSync(path)) throw new Error(`curation/${rel} is missing`);
  try {
    return parse(readFileSync(path, 'utf-8'));
  } catch (e) {
    throw new Error(`curation/${rel} is not valid YAML: ${e.message}`);
  }
}

// The decision store must be well formed: a malformed store fails the build
// rather than rendering a silently empty log.
function readDecisions() {
  const doc = readCurationYaml('decisions.yaml');
  const bad = (msg) => { throw new Error(`curation/decisions.yaml is malformed: ${msg}`); };
  if (!doc || typeof doc !== 'object' || Array.isArray(doc)) bad('top level must be a mapping');
  if (!Number.isInteger(doc.version)) bad('`version` must be an integer');
  if (!Number.isInteger(doc.next_id)) bad('`next_id` must be an integer');
  if (!Array.isArray(doc.decisions)) bad('`decisions` must be a list');
  const seen = new Set();
  for (const [i, d] of doc.decisions.entries()) {
    const where = `decisions[${i}]`;
    if (!d || typeof d !== 'object') bad(`${where} is not a mapping`);
    if (typeof d.id !== 'string' || !/^DEC-\d{4,}$/.test(d.id)) bad(`${where}.id must be DEC-NNNN`);
    if (seen.has(d.id)) bad(`duplicate id ${d.id}`);
    seen.add(d.id);
    for (const f of ['subject', 'verdict']) {
      if (typeof d[f] !== 'string' || !d[f]) bad(`${d.id}.${f} must be a non-empty string`);
    }
    if (!['pending', 'applied', 'withdrawn'].includes(d.status)) bad(`${d.id}.status must be pending | applied | withdrawn`);
  }
  return { version: doc.version, next_id: doc.next_id, decisions: doc.decisions };
}

// SID aliases (retired/renamed -> current), followed to the end of the chain.
function aliasResolver(aliases) {
  return (sid) => {
    const seen = new Set();
    while (aliases[sid] && !seen.has(sid)) { seen.add(sid); sid = aliases[sid]; }
    return sid;
  };
}

// Browse-page path (no base) for a subject, or null when it has none.
function browsePath(s) {
  if (s.retired) return null;
  const classHref = (c) => CLASS_HREF_OVERRIDES[c] || `/schema/class/${c}`;
  const enumHref = (e) => VOCAB_ENUM_HREFS[e] || `/schema/enum/${e}`;
  switch (s.kind) {
    case 'class': return classHref(s.name);
    case 'enum': return enumHref(s.name);
    case 'term':
      if (s.enum === 'DataType') return `/data-types/${slugify(s.label)}`;
      if (s.enum === 'FeatureType') return `/feature-types/${slugify(s.label)}`;
      return enumHref(s.enum);
    case 'slot': return s.owner_class ? classHref(s.owner_class) : null;
    case 'usage': return classHref(s.name.split('/')[0]);
    default: return null;
  }
}

// Does a review prompt apply to a subject? Every `when` key given must match.
function promptMatches(prompt, subject, signals) {
  const w = prompt.when || {};
  if (w.kind && !w.kind.includes(subject.kind)) return false;
  if (w.layer && !w.layer.includes(subject.layer)) return false;
  if (w.signal && !w.signal.some(k => signals?.[k])) return false;
  return true;
}

// Embeddings findings, normalized exactly as scripts/curation_status.py does
// (same ids, rules, messages), and the reports filtered to live subjects.
function joinEmbeddings(known, resolve, severityOf) {
  const reports = {};
  const findings = [];
  let dropped = 0;
  let stale = false;

  const isLive = (sid) => known.subjects[sid] && !known.subjects[sid].retired;
  // Keep a finding only if every subject it names is live (after aliases).
  const live = (sids) => {
    const out = (sids || []).map(resolve);
    if (!out.length || !out.every(isLive)) {
      dropped += 1;
      return null;
    }
    return out;
  };
  const add = (f) => findings.push({ ...f, source: 'embeddings', severity: severityOf[f.rule] });

  for (const name of EMBEDDING_REPORTS) {
    const path = join(reportsDir, name);
    if (!existsSync(path)) {
      console.warn(`Warning: report ${name} not found`);
      reports[name] = null;
      continue;
    }
    const data = JSON.parse(readFileSync(path, 'utf-8'));
    if (!data.provenance) {
      // Pre-provenance reports are treated as absent.
      stale = true;
      reports[name] = null;
      continue;
    }
    if (data.provenance.schema_fingerprint !== known.fingerprint) stale = true;

    if (name === 'internal_similarity.json') {
      const pairs = [];
      for (const p of data.pairs || []) {
        const subjects = live(p.subjects);
        if (!subjects) continue;
        pairs.push({ ...p, subjects });
        add({ id: p.id, rule: 'similar-terms', subjects,
          message: `${p.term1} ~ ${p.term2} (similarity ${p.similarity}; ${p.machine_recommendation})` });
      }
      reports[name] = { ...data, total_pairs: pairs.length, pairs };
    } else if (name === 'gap_analysis.json') {
      const bySubset = {};
      for (const [subset, group] of Object.entries(data.by_subset || {})) {
        const terms = [];
        for (const t of group.terms || []) {
          const subjects = live(t.subjects);
          if (!subjects) continue;
          terms.push({ ...t, subjects });
          add({ id: t.id, rule: 'coverage-gap', subjects,
            message: `${t.onga_term}: no ontology match (best similarity ${t.max_similarity})` });
        }
        if (terms.length) bySubset[subset] = { ...group, count: terms.length, terms };
      }
      const count = Object.values(bySubset).reduce((n, g) => n + g.terms.length, 0);
      reports[name] = { ...data, gap_terms_count: count, by_subset: bySubset };
    } else {
      const terms = [];
      for (const t of data.terms || []) {
        const subject = resolve(t.subject);
        if (!isLive(subject)) {
          dropped += (t.suggested_mappings || []).length;
          continue;
        }
        const suggested = [];
        for (const m of t.suggested_mappings || []) {
          const subjects = live(m.subjects);
          if (!subjects) continue;
          suggested.push({ ...m, subjects });
          add({ id: m.id, rule: 'mapping-suggestion', subjects, object: m.term_id,
            message: `${t.onga_term} -> ${m.term_id} ${m.term_name} (${m.match_type}, ${m.similarity})` });
        }
        terms.push({ ...t, subject, suggested_mappings: suggested });
      }
      reports[name] = {
        ...data,
        total_terms: terms.length,
        terms_with_matches: terms.filter(t => t.suggested_mappings.length).length,
        terms,
      };
    }
  }
  return { reports, findings, dropped, stale };
}

function buildDevelop() {
  mkdirSync(developDir, { recursive: true });
  const write = (name, data) => writeFileSync(join(developDir, name), JSON.stringify(data, null, 2));

  const registry = readCurationJson('subjects.json');
  if (!registry.subjects || !registry.schema_fingerprint) {
    throw new Error('curation/subjects.json has no subjects / schema_fingerprint');
  }
  const status = readCurationJson('status.json');
  const aliasDoc = readCurationJson('subject_aliases.json');
  const aliases = Object.fromEntries(Object.entries(aliasDoc).filter(([k]) => !k.startsWith('_')));
  const resolve = aliasResolver(aliases);
  const lint = readCurationJson('findings/schema_lint.json');
  const usage = readCurationJson('usage.json');
  const pending = readCurationJson('pending.json');
  const verdicts = readCurationYaml('verdicts.yaml');
  if (!verdicts?.verdicts) throw new Error('curation/verdicts.yaml has no `verdicts` map');
  const decisions = readDecisions();
  const policy = readCurationYaml('policy.yaml');
  const prompts = readCurationYaml('review_prompts.yaml');
  if (!Array.isArray(prompts?.prompts)) throw new Error('curation/review_prompts.yaml has no `prompts` list');

  const subjects = registry.subjects;
  const emb = joinEmbeddings({ subjects, fingerprint: registry.schema_fingerprint }, resolve,
    policy.status.finding_severity);

  // One finding index: lint (skipped when stale, as curation_status does) + embeddings.
  const lintStale = lint.schema_fingerprint !== registry.schema_fingerprint;
  const byId = {};
  for (const f of lintStale ? [] : lint.findings) byId[f.id] = { ...f, source: 'schema_lint' };
  for (const f of emb.findings) byId[f.id] = f;

  const decisionById = Object.fromEntries(decisions.decisions.map(d => [d.id, d]));
  const brief = (d) => d ? {
    id: d.id, verdict: d.verdict, status: d.status, decided_by: d.decided_by,
    decided_on: d.decided_on, rationale: d.rationale,
  } : null;

  const index = {};
  for (const [sid, s] of Object.entries(subjects)) {
    const st = status.subjects[sid] || {};
    const open = st.open_findings || [];
    index[sid] = {
      sid,
      kind: s.kind,
      name: s.name,
      label: s.label || s.name,
      slug: s.slug,
      layer: s.layer,
      container: s.container,
      retired: s.retired,
      hash: s.hash,
      href: `/develop/subject/${s.slug}`,
      browse: browsePath(s),
      owner_class: s.owner_class ? `class:${s.owner_class}` : null,
      state: st.state || 'unreviewed',
      score: st.score || 0,
      findings: open.length,
      lint: open.filter(id => byId[id]?.source === 'schema_lint').length,
      latest: st.latest || null,
      prompts: prompts.prompts.filter(p => promptMatches(p, s, st.signals)).map(p => p.id),
    };
  }

  const queue = status.queue.map((sid) => {
    const st = status.subjects[sid];
    return {
      ...index[sid],
      signals: st.signals,
      findings: (st.open_findings || []).filter(id => byId[id]).map((id) => {
        const f = byId[id];
        return { id, rule: f.rule, severity: f.severity, message: f.message,
          suggested_verdict: f.suggested_verdict || null };
      }),
      decisions: st.decisions,
      latest: brief(decisionById[st.latest]),
    };
  });

  write('subjects.json', registry);
  write('status.json', status);
  write('usage.json', usage);
  write('pending.json', pending);
  write('verdicts.json', verdicts);
  write('decisions.json', decisions);
  write('review_prompts.json', prompts);
  write('lint.json', { ...lint, stale: lintStale });
  write('findings.json', { byId });
  write('subject-index.json', index);
  write('queue.json', queue);

  const STATES = ['unreviewed', 'open', 'deferred', 'settled', 'applied', 'stale'];
  const rollup = (r) => ({
    percentSettled: r.percent_settled,
    total: r.total,
    states: Object.fromEntries(STATES.map(k => [k, r[k]])),
  });
  const overall = rollup(status.rollups.overall);
  const counts = {
    percentSettled: overall.percentSettled,
    totalSubjects: overall.total,
    states: overall.states,
    layers: Object.fromEntries(Object.entries(status.rollups.by_layer).map(([l, r]) => [l, rollup(r)])),
    pendingDecisions: decisions.decisions.filter(d => d.status === 'pending').length,
    appliedDecisions: decisions.decisions.filter(d => d.status === 'applied').length,
    lintIssues: lintStale ? 0 : lint.findings.length,
    staleFindings: emb.dropped,
    findingsStale: emb.stale || lintStale,
    queued: queue.length,
  };
  return { counts, reports: emb.reports };
}

function build() {
  console.log('Building ONGA site data...');

  const onga = readYaml('onga.yaml');
  const fileContent = readYaml('file_content.yaml');
  const formatSchema = readYaml('format.yaml');
  const strandSchema = readYaml('strand_orientation.yaml');
  const readMultiplicitySchema = readYaml('read_multiplicity.yaml');
  const filterStatusSchema = readYaml('filter_status.yaml');
  const normalizationSchema = readYaml('normalization.yaml');
  const thresholdingSchema = readYaml('thresholding.yaml');
  const derivationSchema = readYaml('derivation.yaml');
  const referenceBuildSexSchema = readYaml('reference_build_sex.yaml');
  const haplotypeResolutionSchema = readYaml('haplotype_resolution.yaml');
  const trackFormat = readYaml('track_format.yaml');
  const trackInterpretation = readYaml('track_interpretation.yaml');
  const trackProvenance = readYaml('track_provenance.yaml');
  const trackGeometry = readYaml('track_geometry.yaml');
  const referenceGenome = readYaml('reference_genome.yaml');
  const edamMappings = readMappings();
  const soMappings = readSoMappings();
  const labelsById = termLabelsById();
  const delegations = readDelegations();
  const upstream = readUpstreamRequests();
  const schemaBrowser = buildSchemaBrowser();

  // Process the vocabularies (DataType, FeatureType, Format) — all LinkML enums.
  const dataTypeEnum = fileContent?.enums?.DataType;
  const featureTypeEnum = fileContent?.enums?.FeatureType;
  const formatEnum = formatSchema?.enums?.Format;

  const dataTypes = processEnum(dataTypeEnum, 'data', edamMappings, soMappings, labelsById);
  const featureTypes = processEnum(featureTypeEnum, 'feature', edamMappings, soMappings, labelsById);
  const formats = processEnum(formatEnum, 'format', edamMappings, {}, labelsById);
  // Facet vocabularies (small, tied to interpretation): StrandOrientation,
  // ReadMultiplicity, FilterStatus.
  const strandOrientations = processEnum(strandSchema?.enums?.StrandOrientation, 'strand', edamMappings, {}, labelsById);
  const readMultiplicities = processEnum(readMultiplicitySchema?.enums?.ReadMultiplicity, 'read_multiplicity', edamMappings, {}, labelsById);
  const filterStatuses = processEnum(filterStatusSchema?.enums?.FilterStatus, 'filter_status', edamMappings, {}, labelsById);
  const normalizations = processEnum(normalizationSchema?.enums?.Normalization, 'normalization', edamMappings, {}, labelsById);
  const thresholdings = processEnum(thresholdingSchema?.enums?.Thresholding, 'thresholding', edamMappings, {}, labelsById);
  const derivations = processEnum(derivationSchema?.enums?.Derivation, 'derivation', edamMappings, {}, labelsById);
  const referenceBuildSexes = processEnum(referenceBuildSexSchema?.enums?.ReferenceBuildSex, 'reference_build_sex', edamMappings, {}, labelsById);
  const haplotypeResolutions = processEnum(haplotypeResolutionSchema?.enums?.HaplotypeResolution, 'haplotype_resolution', edamMappings, {}, labelsById);
  const geometry = processGeometry(trackGeometry);
  // TrackFormat is a schema; its file_format slot links to the Format vocabulary.
  const format = processFormat(trackFormat, {
    format: formats.terms.length,
  });
  const interpretation = processInterpretation(trackInterpretation, {
    dataType: dataTypes.terms.length,
    featureType: featureTypes.terms.length,
    strandOrientation: strandOrientations.terms.length,
    haplotypeResolution: haplotypeResolutions.terms.length,
  });
  // TrackProvenance: facet slots link to their facet vocabularies.
  const provenance = processProvenance(trackProvenance, {
    readMultiplicity: readMultiplicities.terms.length,
    filterStatus: filterStatuses.terms.length,
    normalization: normalizations.terms.length,
    thresholding: thresholdings.terms.length,
    derivation: derivations.terms.length,
  });
  // ReferenceGenome (5th schema): build_sex slot links to the ReferenceBuildSex facet.
  const referenceGenomeSchema = processReferenceGenome(referenceGenome, {
    referenceBuildSex: referenceBuildSexes.terms.length,
  });

  // Group geometry properties for the by-group view.
  const geometryByGroup = {};
  for (const prop of geometry.properties) {
    if (!geometryByGroup[prop.group]) geometryByGroup[prop.group] = [];
    geometryByGroup[prop.group].push(prop);
  }

  // Combine for backwards compatibility views
  const allTerms = [...dataTypes.terms, ...featureTypes.terms];

  // Build categories from subsets
  const categories = [];
  if (fileContent?.subsets) {
    for (const [id, data] of Object.entries(fileContent.subsets)) {
      categories.push({
        id,
        slug: slugify(id),
        name: id.replace(/_/g, ' '),
        description: data.description || ''
      });
    }
  }

  // Categorize categories by vocab type
  const dataCategories = new Set(dataTypes.terms.map(t => t.category));
  const featureCategories = new Set(featureTypes.terms.map(t => t.category));

  // Build mappings summary
  const mappings = allTerms
    .filter(t => t.edamMapping)
    .map(t => ({
      termId: t.id,
      termName: t.name,
      category: t.category,
      vocabType: t.vocabType,
      ...t.edamMapping
    }));

  // ONGA -> SO. One entry per SSSOM row, so a mixed set (e.g. `regulatory
  // elements`, whose rows may be enhancers, promoters, silencers or insulators)
  // contributes one row per SO class.
  const soMappingList = allTerms
    .filter(t => (t.soMapping || []).length)
    .flatMap(t => t.soMapping.map(m => ({
      termId: t.id,
      termName: t.name,
      category: t.category,
      vocabType: t.vocabType,
      ...m
    })));

  // Terms reviewed and found to have NO SO element type at all -- curated-none,
  // which is different from not-yet-curated (no annotation).
  const elementTypeNone = allTerms.filter(
    t => !t.elementType && t.elementTypeFit === 'not_applicable');
  const elementTypeCoverage = allTerms.filter(t => t.elementType).length;

  // Build vocabulary info
  const vocabularyInfo = {
    name: onga?.name || 'onga',
    title: onga?.title || 'ONGA - Ontology for Genomic Annotations',
    description: fileContent?.description || onga?.description || '',
    version: onga?.version || '0.1.0',
    license: onga?.license || '',
    createdBy: onga?.created_by || '',
    creationDate: onga?.creation_date || '',
    prefix: 'https://databio.org/onga/',
    stats: {
      totalTerms: allTerms.length,
      dataTypeTerms: dataTypes.terms.length,
      featureTypeTerms: featureTypes.terms.length,
      formatTerms: formats.terms.length,
      strandOrientationTerms: strandOrientations.terms.length,
      readMultiplicityTerms: readMultiplicities.terms.length,
      filterStatusTerms: filterStatuses.terms.length,
      normalizationTerms: normalizations.terms.length,
      thresholdingTerms: thresholdings.terms.length,
      derivationTerms: derivations.terms.length,
      referenceBuildSexTerms: referenceBuildSexes.terms.length,
      haplotypeResolutionTerms: haplotypeResolutions.terms.length,
      geometryTerms: geometry.properties.length,
      totalCategories: categories.length,
      totalMappings: mappings.length,
      coveragePercent: Math.round((mappings.length / allTerms.length) * 100),
      // Set/element layer: SSSOM rows against SO, and how many terms carry an
      // element type at all. See the ADR "ONGA terms denote sets; SO terms
      // denote elements".
      soMappings: soMappingList.length,
      elementTypeCoverage,
      elementTypeNone: elementTypeNone.length,
      elementTypePercent: Math.round((elementTypeCoverage / allTerms.length) * 100),
      // Four-layer summary for the home page. Layer 1: 3 core vocabularies
      // (DataType, FeatureType, Format) + 8 facet vocabularies
      // (StrandOrientation, ReadMultiplicity, FilterStatus, Normalization,
      // Thresholding, Derivation, ReferenceBuildSex, HaplotypeResolution)
      // + the small structural enums (ValueType, AccessProtocol,
      // BiospecimenClassification). Layer 2: the 5 descriptor schemas.
      // Layers 3/4: the record and investigation classes from the FGA-WG merge.
      vocabularyCount: 11 + schemaBrowser.enums.length,
      coreVocabCount: 3,
      facetVocabCount: 8,
      structuralVocabCount: schemaBrowser.enums.length,
      schemaCount: 5,
      recordClassCount: schemaBrowser.classes.filter(c => c.layer === 3).length,
      investigationClassCount: schemaBrowser.classes.filter(c => c.layer === 4).length,
      formatProps: format.properties.length,
      interpretationProps: interpretation.properties.length,
      provenanceProps: provenance.properties.length,
      geometryProps: geometry.properties.length,
      referenceGenomeProps: referenceGenomeSchema.properties.length,
      delegationCount: delegations.length,
    }
  };

  // Write JSON files
  writeFileSync(join(dataDir, 'vocabulary.json'), JSON.stringify(vocabularyInfo, null, 2));
  writeFileSync(join(dataDir, 'categories.json'), JSON.stringify(categories, null, 2));

  // Separate vocab files
  writeFileSync(join(dataDir, 'data-types.json'), JSON.stringify(dataTypes.terms, null, 2));
  writeFileSync(join(dataDir, 'feature-types.json'), JSON.stringify(featureTypes.terms, null, 2));
  writeFileSync(join(dataDir, 'data-types-by-category.json'), JSON.stringify(dataTypes.termsByCategory, null, 2));
  writeFileSync(join(dataDir, 'feature-types-by-category.json'), JSON.stringify(featureTypes.termsByCategory, null, 2));

  // Format vocabulary (flat list; Format terms are uncategorized).
  writeFileSync(join(dataDir, 'format.json'), JSON.stringify(formats.terms, null, 2));
  writeFileSync(join(dataDir, 'format-by-category.json'), JSON.stringify(formats.termsByCategory, null, 2));

  // Facet vocabularies (flat lists; small, tied to TrackInterpretation).
  writeFileSync(join(dataDir, 'strand-orientation.json'), JSON.stringify(strandOrientations.terms, null, 2));
  writeFileSync(join(dataDir, 'read-multiplicity.json'), JSON.stringify(readMultiplicities.terms, null, 2));
  writeFileSync(join(dataDir, 'filter-status.json'), JSON.stringify(filterStatuses.terms, null, 2));
  writeFileSync(join(dataDir, 'normalization.json'), JSON.stringify(normalizations.terms, null, 2));
  writeFileSync(join(dataDir, 'thresholding.json'), JSON.stringify(thresholdings.terms, null, 2));
  writeFileSync(join(dataDir, 'derivation.json'), JSON.stringify(derivations.terms, null, 2));
  writeFileSync(join(dataDir, 'reference-build-sex.json'), JSON.stringify(referenceBuildSexes.terms, null, 2));
  writeFileSync(join(dataDir, 'haplotype-resolution.json'), JSON.stringify(haplotypeResolutions.terms, null, 2));

  // Track geometry vocabulary (class with slots, plus the ValueType enum)
  writeFileSync(join(dataDir, 'track-geometry.json'), JSON.stringify({
    properties: geometry.properties,
    valueTypes: geometry.valueTypes,
  }, null, 2));
  writeFileSync(join(dataDir, 'track-geometry-by-group.json'), JSON.stringify(geometryByGroup, null, 2));

  // Track format schema (class slots only; file_format links to the Format vocabulary)
  writeFileSync(join(dataDir, 'track-format.json'), JSON.stringify({
    properties: format.properties,
  }, null, 2));

  // Track interpretation schema (class slots, each linked to its vocabulary)
  writeFileSync(join(dataDir, 'track-interpretation.json'), JSON.stringify({
    properties: interpretation.properties,
  }, null, 2));

  // Track provenance schema (facet slots, each linked to its facet vocabulary)
  writeFileSync(join(dataDir, 'track-provenance.json'), JSON.stringify({
    properties: provenance.properties,
  }, null, 2));

  // Reference genome schema (5th schema; build_sex slot linked to the ReferenceBuildSex facet)
  writeFileSync(join(dataDir, 'reference-genome.json'), JSON.stringify({
    properties: referenceGenomeSchema.properties,
  }, null, 2));

  // Scope-boundary delegations (axes ONGA delegates OUT to external ontologies)
  writeFileSync(join(dataDir, 'delegations.json'), JSON.stringify(delegations, null, 2));

  // Generic schema browser data (Layers 2-4 classes + structural enums); the
  // dynamic /schema Astro routes getStaticPaths() over these.
  mkdirSync(join(dataDir, 'schema'), { recursive: true });
  writeFileSync(join(dataDir, 'schema', 'classes.json'), JSON.stringify(schemaBrowser.classes, null, 2));
  writeFileSync(join(dataDir, 'schema', 'enums.json'), JSON.stringify(schemaBrowser.enums, null, 2));

  // Combined for backwards compat
  writeFileSync(join(dataDir, 'terms.json'), JSON.stringify(allTerms, null, 2));
  writeFileSync(join(dataDir, 'mappings.json'), JSON.stringify(mappings, null, 2));
  writeFileSync(join(dataDir, 'so-mappings.json'), JSON.stringify(soMappingList, null, 2));

  console.log(`Schema browser: ${schemaBrowser.classes.length} classes (${vocabularyInfo.stats.recordClassCount} record + ${vocabularyInfo.stats.investigationClassCount} investigation + 5 descriptor), ${schemaBrowser.enums.length} structural enums`);
  console.log('Built 11 hand-curated vocabularies (3 core + 8 facet) + 5 schemas:');
  console.log(`  Core vocabularies: ${dataTypes.terms.length} DataType, ${featureTypes.terms.length} FeatureType, ${formats.terms.length} Format`);
  console.log(`  Facet vocabularies: ${strandOrientations.terms.length} StrandOrientation, ${readMultiplicities.terms.length} ReadMultiplicity, ${filterStatuses.terms.length} FilterStatus, ${normalizations.terms.length} Normalization, ${thresholdings.terms.length} Thresholding, ${derivations.terms.length} Derivation, ${referenceBuildSexes.terms.length} ReferenceBuildSex, ${haplotypeResolutions.terms.length} HaplotypeResolution`);
  console.log(`  Schemas: TrackFormat (${format.properties.length} props), TrackInterpretation (${interpretation.properties.length} props), TrackProvenance (${provenance.properties.length} props), TrackGeometry (${geometry.properties.length} props), ReferenceGenome (${referenceGenomeSchema.properties.length} props)`);
  console.log(`Categories: ${categories.length}, Mappings: ${mappings.length}, Scope delegations: ${delegations.length}`);
  console.log(`SO element-type layer: ${soMappingList.length} SSSOM rows, ${elementTypeCoverage} terms with an element type, ${elementTypeNone.length} curated not_applicable`);

  const curationSummary = buildDevelop();

  // Embeddings finding pages read the raw reports, filtered to live subjects
  // (buildDevelop drops findings on unknown subjects and flags stale reports).
  const { reports } = curationSummary;
  const internalSim = reports['internal_similarity.json'];
  const gapAnalysis = reports['gap_analysis.json'];
  const mappingReport = reports['mapping_report.json'];

  writeFileSync(
    join(developDir, 'merge-candidates.json'),
    JSON.stringify(internalSim || { total_pairs: 0, pairs: [] }, null, 2)
  );
  writeFileSync(
    join(developDir, 'gaps.json'),
    JSON.stringify(gapAnalysis || { total_onga_terms: 0, gap_terms_count: 0, by_subset: {} }, null, 2)
  );
  writeFileSync(
    join(developDir, 'mapping-suggestions.json'),
    JSON.stringify(mappingReport || { total_terms: 0, terms_with_matches: 0, terms: [] }, null, 2)
  );

  // Upstream ontology requests (proposals/upstream_requests.yaml)
  writeFileSync(
    join(developDir, 'upstream-requests.json'),
    JSON.stringify(upstream, null, 2)
  );

  // ENCODE usage frequency (from encode-term-use-frequency/seed_term_frequency.tsv)
  let frequency = { generated: false, totalFiles: 0, zeroUsage: 0, terms: [] };
  if (existsSync(frequencyTsv)) {
    const lines = readFileSync(frequencyTsv, 'utf-8').split(/\r?\n/).filter(l => l.trim());
    const header = lines[0].split('\t').map(h => h.trim());
    const idx = name => header.indexOf(name);
    const terms = lines.slice(1).map(line => {
      const c = line.split('\t').map(v => v.trim());
      return {
        term: c[idx('term')],
        inEncode: (c[idx('in_encode')] || '').toLowerCase() === 'yes',
        fileCount: parseInt(c[idx('file_count')] || '0', 10),
        datasetCount: parseInt(c[idx('dataset_count')] || '0', 10),
      };
    }).sort((a, b) => b.fileCount - a.fileCount);
    frequency = {
      generated: true,
      totalFiles: terms.reduce((s, t) => s + t.fileCount, 0),
      zeroUsage: terms.filter(t => t.fileCount === 0).length,
      terms,
    };
  } else {
    console.warn('Warning: seed_term_frequency.tsv not found, frequency page will be empty');
  }
  writeFileSync(join(developDir, 'frequency.json'), JSON.stringify(frequency, null, 2));

  const summary = {
    ...curationSummary.counts,
    mergeCandidates: internalSim?.pairs?.length || 0,
    gapTerms: Object.values(gapAnalysis?.by_subset || {}).reduce((n, g) => n + (g.terms || []).length, 0),
    mappingSuggestions: (mappingReport?.terms || []).filter(t => (t.suggested_mappings || []).length).length,
    soProposals: upstream.stats.newTerms + upstream.stats.modifications,
    soRejections: upstream.stats.rejectedTerms,
    zeroUsageTerms: frequency.zeroUsage,
    totalTerms: allTerms.length,
    soMappings: soMappingList.length,
    elementTypeCoverage,
  };
  writeFileSync(join(developDir, 'summary.json'), JSON.stringify(summary, null, 2));

  console.log(`Develop: ${summary.mergeCandidates} merge candidates, ${summary.gapTerms} gaps, ${summary.mappingSuggestions} mapping suggestions`);
  console.log(`Curation: ${summary.percentSettled}% settled, ${summary.pendingDecisions} pending / ${summary.appliedDecisions} applied decisions, ${summary.lintIssues} lint findings, ${summary.staleFindings} findings on unknown subjects dropped${summary.findingsStale ? ', embeddings findings STALE' : ''}`);
  console.log(`Upstream requests: ${upstream.stats.newTerms} new terms (${upstream.stats.proposedLabels} labels), ${upstream.stats.modifications} modifications, ${upstream.stats.rejectionGroups} rejections covering ${upstream.stats.rejectedTerms} ONGA terms`);
}

build();
