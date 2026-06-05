#!/usr/bin/env node
/**
 * Build JSON data files from ONGA LinkML schema for Astro site.
 *
 * ONGA has two layers:
 *   Layer 1 — Vocabularies (closed value sets): 3 core (DataType, FeatureType,
 *     Format) + 7 facet (StrandOrientation, ReadMultiplicity, FilterStatus,
 *     Normalization, Thresholding, Derivation, ReferenceBuildSex) = 10 total.
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

function readYaml(filename) {
  const path = join(schemaDir, filename);
  if (!existsSync(path)) {
    console.warn(`Warning: ${filename} not found`);
    return null;
  }
  return parse(readFileSync(path, 'utf-8'));
}

function readMappings() {
  const path = join(mappingsDir, 'edam.sssom.tsv');
  if (!existsSync(path)) return {};

  const content = readFileSync(path, 'utf-8');
  const lines = content.split('\n').filter(l => l && !l.startsWith('#'));
  const mappings = {};

  for (const line of lines.slice(1)) {
    const [subject, predicate, object, , subjectLabel, objectLabel, comment] = line.split('\t');
    if (subject && object) {
      const termId = subject.replace('onga:', '');
      mappings[termId] = {
        predicate: predicate?.replace('skos:', '') || 'relatedMatch',
        edamId: object,
        edamLabel: objectLabel || '',
        comment: comment || ''
      };
    }
  }
  return mappings;
}

function slugify(name) {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_|_$/g, '');
}

function processEnum(enumData, vocabType, edamMappings) {
  const terms = [];
  const termsByCategory = {};

  if (!enumData?.permissible_values) return { terms, termsByCategory };

  for (const [name, data] of Object.entries(enumData.permissible_values)) {
    const slug = slugify(name);
    const category = data.in_subset?.[0] || 'uncategorized';

    let edamMapping = null;
    if (data.meaning) {
      edamMapping = {
        predicate: 'exactMatch',
        edamId: data.meaning,
        edamLabel: '',
        comment: 'From LinkML schema'
      };
    } else if (edamMappings[slug] || edamMappings[name.replace(/ /g, '_')]) {
      edamMapping = edamMappings[slug] || edamMappings[name.replace(/ /g, '_')];
    }

    const term = {
      id: slug,
      name,
      slug,
      description: data.description || '',
      category,
      categorySlug: slugify(category),
      vocabType, // 'data' or 'feature'
      edamMapping,
      seeAlso: data.see_also || [],
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
  const trackFormat = readYaml('track_format.yaml');
  const trackInterpretation = readYaml('track_interpretation.yaml');
  const trackProvenance = readYaml('track_provenance.yaml');
  const trackGeometry = readYaml('track_geometry.yaml');
  const referenceGenome = readYaml('reference_genome.yaml');
  const edamMappings = readMappings();
  const delegations = readDelegations();

  // Process the vocabularies (DataType, FeatureType, Format) — all LinkML enums.
  const dataTypeEnum = fileContent?.enums?.DataType;
  const featureTypeEnum = fileContent?.enums?.FeatureType;
  const formatEnum = formatSchema?.enums?.Format;

  const dataTypes = processEnum(dataTypeEnum, 'data', edamMappings);
  const featureTypes = processEnum(featureTypeEnum, 'feature', edamMappings);
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
  const geometry = processGeometry(trackGeometry);
  // TrackFormat is a schema; its file_format slot links to the Format vocabulary.
  const format = processFormat(trackFormat, {
    format: formats.terms.length,
  });
  const interpretation = processInterpretation(trackInterpretation, {
    dataType: dataTypes.terms.length,
    featureType: featureTypes.terms.length,
    strandOrientation: strandOrientations.terms.length,
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
      geometryTerms: geometry.properties.length,
      totalCategories: categories.length,
      totalMappings: mappings.length,
      coveragePercent: Math.round((mappings.length / allTerms.length) * 100),
      // Two-layer summary for the home page. There are 3 core vocabularies
      // (DataType, FeatureType, Format) plus 7 facet vocabularies
      // (StrandOrientation, ReadMultiplicity, FilterStatus, Normalization,
      // Thresholding, Derivation, ReferenceBuildSex), so 10 vocabularies total.
      vocabularyCount: 10,
      coreVocabCount: 3,
      facetVocabCount: 7,
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

  console.log('Built 10 vocabularies (3 core + 7 facet) + 5 schemas:');
  console.log(`  Core vocabularies: ${dataTypes.terms.length} DataType, ${featureTypes.terms.length} FeatureType, ${formats.terms.length} Format`);
  console.log(`  Facet vocabularies: ${strandOrientations.terms.length} StrandOrientation, ${readMultiplicities.terms.length} ReadMultiplicity, ${filterStatuses.terms.length} FilterStatus, ${normalizations.terms.length} Normalization, ${thresholdings.terms.length} Thresholding, ${derivations.terms.length} Derivation, ${referenceBuildSexes.terms.length} ReferenceBuildSex`);
  console.log(`  Schemas: TrackFormat (${format.properties.length} props), TrackInterpretation (${interpretation.properties.length} props), TrackProvenance (${provenance.properties.length} props), TrackGeometry (${geometry.properties.length} props), ReferenceGenome (${referenceGenomeSchema.properties.length} props)`);
  console.log(`Categories: ${categories.length}, Mappings: ${mappings.length}, Scope delegations: ${delegations.length}`);

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
    zeroUsageTerms: frequency.zeroUsage,
    totalTerms: allTerms.length,
  };
  writeFileSync(join(developDir, 'summary.json'), JSON.stringify(summary, null, 2));

  console.log(`Develop: ${summary.mergeCandidates} merge candidates, ${summary.gapTerms} gaps, ${summary.mappingSuggestions} mapping suggestions`);
}

build();
