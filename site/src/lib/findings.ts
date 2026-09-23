// Build-time helpers shared by the finding pages under pages/develop/
// (merge-candidates, gaps, mapping-suggestions, lint). A finding counts as
// decided when a non-withdrawn decision cites it as evidence; a subject counts
// as decided when it has a latest decision in the subject index.

import { decisions, subject } from './develop';
import subjectsDoc from '../data/develop/subjects.json';

const live = decisions.filter((d) => d.status !== 'withdrawn');

const cited = new Set<string>();
for (const d of live) {
  for (const e of d.evidence || []) if (e.kind === 'finding' && e.id) cited.add(e.id);
}

/** True when a non-withdrawn decision cites the finding id as evidence. */
export function findingDecided(id: string): boolean {
  return cited.has(id);
}

/** True when any of the SIDs already has a decision (or is retired). */
export function subjectsDecided(sids: string[]): boolean {
  return sids.some((s) => {
    const row = subject(s);
    return !row || row.retired || !!row.latest;
  });
}

/** Normalize an ontology term id to the CURIE form used in SSSOM objects. */
export function toCurie(id: string): string {
  const m = /^https?:\/\/edamontology\.org\/(.+)$/.exec(id);
  return m ? `edam:${m[1]}` : id;
}

const subjects = (subjectsDoc as { subjects: Record<string, any> }).subjects;

/** SSSOM rows (positive and negated) on a term subject's payload. */
export function sssomRows(sid: string): any[] {
  return subjects[sid]?.payload?.sssom || [];
}

/** True when the term already has a positive or negated SSSOM row to `object`. */
export function hasSssomRow(sid: string, object: string): boolean {
  const o = toCurie(object);
  return sssomRows(sid).some((r) => r.object === o);
}
