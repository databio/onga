#!/usr/bin/env node
/**
 * Build JSON data files from ONGA LinkML schema for Astro site.
 *
 * ONGA has two layers:
 *   Layer 1 — Vocabularies (closed value sets): 3 core (DataType, FeatureType,
 *     Format) + 8 facet (StrandOrientation, ReadMultiplicity, FilterStatus,
 *     Normalization, Thresholding, Derivation, ReferenceBuildSex,
 *     HaplotypeResolution) = 11 total.
 *   Layer 2 — Track descriptor schemas (classes of slots): TrackFormat (#1,
 *     encoding), TrackInterpretation (#2, meaning), TrackProvenance (what was
 *     done to the data — processing/derivation operations), TrackGeometry (#3,
 *     shape), ReferenceGenome (#4, the reference assembly a track is defined
 *     against) = 5 total.
 */

import { readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs';
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

function readMappings() {
  const mappings = {};
  for (const r of readSssom(join(mappingsDir, 'edam.sssom.tsv'))) {
    if (!r.subject_id || !r.object_id) continue;
    mappings[r.subject_id.replace('onga:', '')] = {
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
// A term may have SEVERAL rows (a mixed set), so this is keyed slug -> array.
function readSoMappings() {
  const bySlug = {};
  for (const r of readSssom(join(mappingsDir, 'so.sssom.tsv'))) {
    if (!r.subject_id || !r.object_id) continue;
    const slug = slugify(r.subject_label || r.subject_id.replace('onga:', ''));
    const predicate = r.predicate_id || '';
    (bySlug[slug] = bySlug[slug] || []).push({
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
  return bySlug;
}

function soUrl(soId) {
  return `http://purl.obolibrary.org/obo/${String(soId).replace(':', '_')}`;
}

function curieToName(ref) {
  return String(ref).replace(/^onga:/, '').replace(/_/g, ' ');
}

function slugify(name) {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_|_$/g, '');
}

// EDAM cross-references declared in the schema itself. `meaning:` is BANNED on
// the content enums (it makes the value's IRI *be* the CURIE, which hijacks SO
// classes and collapses duplicate EDAM CURIEs into one OWL node -- see the ADR
// "ONGA terms denote sets; SO terms denote elements"), so DataType/FeatureType
// badges come from edam.sssom.tsv. The small facet/format vocabularies still
// declare their single EDAM CURIE inline, so read those slots here.
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
  if (String(data.meaning || '').startsWith('edam:')) {
    return { predicate: 'exactMatch', edamId: data.meaning, edamLabel: '', comment: 'From LinkML schema' };
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
  if (data.meaning) {
    return { predicate: 'exactMatch', id: String(data.meaning), url: curieUrl(data.meaning) };
  }
  return null;
}

function processEnum(enumData, vocabType, edamMappings, soMappings = {}) {
  const terms = [];
  const termsByCategory = {};

  if (!enumData?.permissible_values) return { terms, termsByCategory };

  for (const [name, data] of Object.entries(enumData.permissible_values)) {
    const slug = slugify(name);
    const category = data.in_subset?.[0] || 'uncategorized';

    const edamMapping =
      edamMappings[slug] || edamMappings[name.replace(/ /g, '_')] || schemaEdamMapping(data);

    // The set/element layer: which SO class(es) the rows of this term instantiate.
    // `element_type` is a pipe-joined STRING of SO CURIEs (a YAML list stringifies
    // badly in gen-owl output); absent + fit 'not_applicable' means "reviewed, the
    // rows are not SO-typeable features", which is different from no annotation
    // at all ("not yet curated").
    const ann = data.annotations || {};
    const elementTypes = String(ann.element_type || '')
      .split('|').map(s => s.trim()).filter(Boolean);
    const rows = soMappings[slug] || [];
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
      // see_also holds onga: CURIEs (schema-valid URIorCURIE); keywords holds
      // free-text related concepts that are not ONGA terms. The site shows both
      // as plain names, so resolve the CURIEs back and concatenate.
      seeAlso: [
        ...(data.see_also || []).map(curieToName),
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

  // Surface the DataTypes enum values (referenced by value_type / edge_weight_type).
  const dataTypesEnum = schema.enums?.DataTypes;
  if (dataTypesEnum?.permissible_values) {
    for (const [name, data] of Object.entries(dataTypesEnum.permissible_values)) {
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
        confidence: r.confidence || 'medium',
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
  const delegations = readDelegations();
  const upstream = readUpstreamRequests();

  // Process the vocabularies (DataType, FeatureType, Format) — all LinkML enums.
  const dataTypeEnum = fileContent?.enums?.DataType;
  const featureTypeEnum = fileContent?.enums?.FeatureType;
  const formatEnum = formatSchema?.enums?.Format;

  const dataTypes = processEnum(dataTypeEnum, 'data', edamMappings, soMappings);
  const featureTypes = processEnum(featureTypeEnum, 'feature', edamMappings, soMappings);
  const formats = processEnum(formatEnum, 'format', edamMappings);
  // Facet vocabularies (small, tied to interpretation): StrandOrientation,
  // ReadMultiplicity, FilterStatus.
  const strandOrientations = processEnum(strandSchema?.enums?.StrandOrientation, 'strand', edamMappings);
  const readMultiplicities = processEnum(readMultiplicitySchema?.enums?.ReadMultiplicity, 'read_multiplicity', edamMappings);
  const filterStatuses = processEnum(filterStatusSchema?.enums?.FilterStatus, 'filter_status', edamMappings);
  const normalizations = processEnum(normalizationSchema?.enums?.Normalization, 'normalization', edamMappings);
  const thresholdings = processEnum(thresholdingSchema?.enums?.Thresholding, 'thresholding', edamMappings);
  const derivations = processEnum(derivationSchema?.enums?.Derivation, 'derivation', edamMappings);
  const referenceBuildSexes = processEnum(referenceBuildSexSchema?.enums?.ReferenceBuildSex, 'reference_build_sex', edamMappings);
  const haplotypeResolutions = processEnum(haplotypeResolutionSchema?.enums?.HaplotypeResolution, 'haplotype_resolution', edamMappings);
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
      // Two-layer summary for the home page. There are 3 core vocabularies
      // (DataType, FeatureType, Format) plus 8 facet vocabularies
      // (StrandOrientation, ReadMultiplicity, FilterStatus, Normalization,
      // Thresholding, Derivation, ReferenceBuildSex, HaplotypeResolution), so
      // 11 vocabularies total.
      vocabularyCount: 11,
      coreVocabCount: 3,
      facetVocabCount: 8,
      schemaCount: 5,
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

  // Track geometry vocabulary (class with slots, plus the DataTypes enum)
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

  // Combined for backwards compat
  writeFileSync(join(dataDir, 'terms.json'), JSON.stringify(allTerms, null, 2));
  writeFileSync(join(dataDir, 'mappings.json'), JSON.stringify(mappings, null, 2));
  writeFileSync(join(dataDir, 'so-mappings.json'), JSON.stringify(soMappingList, null, 2));

  console.log('Built 11 vocabularies (3 core + 8 facet) + 5 schemas:');
  console.log(`  Core vocabularies: ${dataTypes.terms.length} DataType, ${featureTypes.terms.length} FeatureType, ${formats.terms.length} Format`);
  console.log(`  Facet vocabularies: ${strandOrientations.terms.length} StrandOrientation, ${readMultiplicities.terms.length} ReadMultiplicity, ${filterStatuses.terms.length} FilterStatus, ${normalizations.terms.length} Normalization, ${thresholdings.terms.length} Thresholding, ${derivations.terms.length} Derivation, ${referenceBuildSexes.terms.length} ReferenceBuildSex, ${haplotypeResolutions.terms.length} HaplotypeResolution`);
  console.log(`  Schemas: TrackFormat (${format.properties.length} props), TrackInterpretation (${interpretation.properties.length} props), TrackProvenance (${provenance.properties.length} props), TrackGeometry (${geometry.properties.length} props), ReferenceGenome (${referenceGenomeSchema.properties.length} props)`);
  console.log(`Categories: ${categories.length}, Mappings: ${mappings.length}, Scope delegations: ${delegations.length}`);
  console.log(`SO element-type layer: ${soMappingList.length} SSSOM rows, ${elementTypeCoverage} terms with an element type, ${elementTypeNone.length} curated not_applicable`);

  // Build develop data from embeddings reports
  mkdirSync(developDir, { recursive: true });

  function readReport(filename) {
    const path = join(reportsDir, filename);
    if (!existsSync(path)) {
      console.warn(`Warning: report ${filename} not found, using empty structure`);
      return null;
    }
    return JSON.parse(readFileSync(path, 'utf-8'));
  }

  const internalSim = readReport('internal_similarity.json');
  const gapAnalysis = readReport('gap_analysis.json');
  const mappingReport = readReport('mapping_report.json');

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

  const qualityIssuesPath = join(developDir, 'quality-issues.json');
  if (!existsSync(qualityIssuesPath)) {
    writeFileSync(qualityIssuesPath, JSON.stringify({ issues: [] }, null, 2));
  }

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
    mergeCandidates: internalSim?.total_pairs || 0,
    gapTerms: gapAnalysis?.gap_terms_count || 0,
    mappingSuggestions: mappingReport?.terms_with_matches || 0,
    qualityIssues: 0,
    soProposals: upstream.stats.newTerms + upstream.stats.modifications,
    soRejections: upstream.stats.rejectedTerms,
    zeroUsageTerms: frequency.zeroUsage,
    totalTerms: allTerms.length,
    soMappings: soMappingList.length,
    elementTypeCoverage,
  };
  writeFileSync(join(developDir, 'summary.json'), JSON.stringify(summary, null, 2));

  console.log(`Develop: ${summary.mergeCandidates} merge candidates, ${summary.gapTerms} gaps, ${summary.mappingSuggestions} mapping suggestions`);
  console.log(`Upstream requests: ${upstream.stats.newTerms} new terms (${upstream.stats.proposedLabels} labels), ${upstream.stats.modifications} modifications, ${upstream.stats.rejectionGroups} rejections covering ${upstream.stats.rejectedTerms} ONGA terms`);
}

build();
