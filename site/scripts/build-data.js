#!/usr/bin/env node
/**
 * Build JSON data files from ONGA LinkML schema for Astro site.
 * Handles two vocabularies: DataType (algorithmic) and FeatureType (biological)
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

function build() {
  console.log('Building ONGA site data...');

  const onga = readYaml('onga.yaml');
  const fileContent = readYaml('file_content.yaml');
  const edamMappings = readMappings();

  // Process both vocabularies
  const dataTypeEnum = fileContent?.enums?.DataType;
  const featureTypeEnum = fileContent?.enums?.FeatureType;

  const dataTypes = processEnum(dataTypeEnum, 'data', edamMappings);
  const featureTypes = processEnum(featureTypeEnum, 'feature', edamMappings);

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
      totalCategories: categories.length,
      totalMappings: mappings.length,
      coveragePercent: Math.round((mappings.length / allTerms.length) * 100)
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

  // Combined for backwards compat
  writeFileSync(join(dataDir, 'terms.json'), JSON.stringify(allTerms, null, 2));
  writeFileSync(join(dataDir, 'mappings.json'), JSON.stringify(mappings, null, 2));

  console.log(`Built: ${dataTypes.terms.length} DataTypes, ${featureTypes.terms.length} FeatureTypes`);
  console.log(`Categories: ${categories.length}, Mappings: ${mappings.length}`);

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

  const summary = {
    mergeCandidates: internalSim?.total_pairs || 0,
    gapTerms: gapAnalysis?.gap_terms_count || 0,
    mappingSuggestions: mappingReport?.terms_with_matches || 0,
    qualityIssues: 0,
    totalTerms: allTerms.length,
  };
  writeFileSync(join(developDir, 'summary.json'), JSON.stringify(summary, null, 2));

  console.log(`Develop: ${summary.mergeCandidates} merge candidates, ${summary.gapTerms} gaps, ${summary.mappingSuggestions} mapping suggestions`);
}

build();
