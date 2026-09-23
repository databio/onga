// Build-time accessors for the curation workbench data in src/data/develop/
// (written by scripts/build-data.js from curation/). Use from .astro
// frontmatter. Every href returned here is a site path; wrap it in url().

import index from '../data/develop/subject-index.json';
import findings from '../data/develop/findings.json';
import decisionsDoc from '../data/develop/decisions.json';
import verdictsDoc from '../data/develop/verdicts.json';
import promptsDoc from '../data/develop/review_prompts.json';

export type State = 'unreviewed' | 'open' | 'deferred' | 'settled' | 'applied' | 'stale';

export interface SubjectRow {
  sid: string;
  kind: string;
  name: string;
  label: string;
  slug: string;
  layer: number;
  container: string | null;
  retired: boolean;
  hash: string;
  href: string;            // /develop/subject/<slug>
  browse: string | null;   // browse page, or null (subsets, modules, retired)
  owner_class: string | null;
  state: State;
  score: number;
  findings: number;        // open findings (all sources)
  lint: number;            // open schema-lint findings
  latest: string | null;   // DEC id of the newest non-withdrawn decision
  prompts: string[];       // review prompt ids that apply
}

export interface Finding {
  id: string;
  source: string;          // schema_lint | embeddings
  rule: string;
  severity: 'error' | 'warn' | 'info';
  subjects: string[];
  message: string;
  suggested_verdict?: string;
  object?: string;
}

export interface Prompt {
  id: string;
  title: string;
  text: string;
  source: string;
  when: { kind?: string[]; layer?: number[]; signal?: string[] };
  decide_on?: 'owner_class';
  suggested_verdict?: string;
  suggested_operation?: Record<string, unknown>;
}

export interface FieldSchema {
  required?: Record<string, string>;
  optional?: Record<string, string>;
  one_of?: string[][];
}

export interface Verdict {
  label: string;
  terminal: boolean;
  writes: string;
  seed_only?: boolean;
  operation?: FieldSchema;
}

export const subjectIndex = index as Record<string, SubjectRow>;
export const findingsById = (findings as { byId: Record<string, Finding> }).byId;
export const decisions = (decisionsDoc as { decisions: any[] }).decisions;
export const verdicts = (verdictsDoc as { verdicts: Record<string, Record<string, Verdict>> }).verdicts;
export const prompts = (promptsDoc as { prompts: Prompt[] }).prompts;

/** The compact row for a SID, or undefined. */
export function subject(sid: string): SubjectRow | undefined {
  return subjectIndex[sid];
}

const findingsBySubject: Record<string, Finding[]> = {};
for (const f of Object.values(findingsById)) {
  for (const sid of f.subjects) (findingsBySubject[sid] ||= []).push(f);
}

/** Every current finding naming the SID (lint + embeddings). */
export function findingsFor(sid: string): Finding[] {
  return findingsBySubject[sid] || [];
}

/** Every decision naming the SID as subject or also_affects, or that created it, oldest first. */
export function decisionsFor(sid: string): any[] {
  return decisions.filter((d) => d.subject === sid || (d.also_affects || []).includes(sid)
    || (d.applied?.created || []).includes(sid));
}

/** Review prompts that apply to the SID, with `$subject` filled into suggested operations. */
export function promptsFor(sid: string): Prompt[] {
  const row = subjectIndex[sid];
  if (!row) return [];
  return prompts
    .filter((p) => row.prompts.includes(p.id))
    .map((p) => p.suggested_operation
      ? { ...p, suggested_operation: Object.fromEntries(Object.entries(p.suggested_operation)
          .map(([k, v]) => [k, v === '$subject' ? sid : v])) }
      : p);
}

/** Verdicts a curator may record for a kind (seed-only ones excluded). */
export function verdictsFor(kind: string): [string, Verdict][] {
  return Object.entries(verdicts[kind] || {}).filter(([, v]) => !v.seed_only);
}
