// Review tracks and types: the queue split by what is being reviewed, then by
// kind of work, one question each.
//
// Two tracks: Vocabulary (the terms, and the subsets and enums that group them)
// and Schema (classes, fields and modules). A queue row belongs to the track of
// its subject kind; inside it, to every type whose rules match one of its open
// findings, or to "sign-off" when it has none. Each type turns its rows into
// plain-language reasons plus ready-made answers (a verdict, its operation and
// a default rationale), so the curator answers one question at a time instead
// of picking from the full verdict list. Build-time only: use from .astro
// frontmatter (pages/develop/queue/).

import queueDoc from '../data/develop/queue.json';
import subjectsDoc from '../data/develop/subjects.json';
import suggestionsDoc from '../data/develop/mapping-suggestions.json';
import { findingsById, subject, verdictsFor } from './develop';
import { findingDecided, hasSssomRow, toCurie } from './findings';

export interface ReviewType {
  id: string;            // also picks the answers (actionsFor)
  title: string;
  question: string;      // the one question every item on the page asks
  answers: string;       // the usual answers, for the landing card
  help: string;          // one or two sentences of background
  rules: string[];       // finding rules that put a row on this page
}

export interface Track {
  id: string;
  title: string;
  blurb: string;
  kinds: string[];       // subject kinds reviewed in this track
  types: ReviewType[];
}

const SIGNOFF = {
  id: 'signoff',
  title: 'Sign-off',
  question: 'Nothing was flagged. Is this right as it is?',
  answers: 'Looks right · Needs work',
  rules: [],
};

export const TRACKS: Track[] = [
  {
    id: 'vocabulary',
    title: 'Vocabulary',
    blurb: 'The words ONGA uses to say what is in a file (peaks, signal, methylation state...), and the lists they live in.',
    kinds: ['term', 'subset', 'enum'],
    types: [
      {
        id: 'links',
        title: 'Links to other ontologies',
        question: 'Does this term match a term in another ontology (EDAM, SO, PATO, ...)?',
        answers: 'Accept a suggested link · Reject it · No match exists',
        help: 'Links let other tools understand ONGA terms. A matcher suggested candidates; some links were added earlier and never checked.',
        rules: ['mapping-suggestion', 'no-mapping-at-all', 'unmapped-high-usage', 'unreviewed-mapping', 'coverage-gap'],
      },
      {
        id: 'duplicates',
        title: 'Near-duplicates',
        question: 'Is this the same thing as another term, or two ideas glued together?',
        answers: 'Merge · Different things · Keep as one term',
        help: 'Pairs of terms that read almost the same, and compound terms that might split into parts.',
        rules: ['similar-terms', 'residual-compound', 'inline-enum'],
      },
      {
        id: 'keep-or-cut',
        title: 'Keep or cut',
        question: 'Should this term exist at all?',
        answers: 'Keep · Delete',
        help: 'Terms no ENCODE file uses, and values nothing else refers to.',
        rules: ['zero-usage-term', 'orphan-facet-value'],
      },
      {
        id: 'definitions',
        title: 'Definitions',
        question: 'Is this definition clear and complete?',
        answers: 'Definition is fine · Rewrite it',
        help: 'Term definitions that are missing, very short, or carry a TODO note.',
        rules: ['terse-description', 'enum-value-no-description', 'todo-marker'],
      },
      { ...SIGNOFF, help: 'Terms, subsets and enums with no known problems that nobody has looked at yet. Most need only a quick read.' },
    ],
  },
  {
    id: 'schema',
    title: 'Schema',
    blurb: 'The data model: record types (classes) like File, Sample and ReferenceGenome, and their fields. Mostly ported from FGA-WG.',
    kinds: ['class', 'slot', 'usage', 'module'],
    types: [
      {
        id: 'fields',
        title: 'Required and examples',
        question: 'Should this field be required, and does it show what a value looks like?',
        answers: 'Required / recommended / optional · Add examples',
        help: 'Every required field is a cost to everyone adopting the schema, and fields without examples are hard to fill in.',
        rules: ['required-policy', 'slot-no-examples'],
      },
      {
        id: 'definitions',
        title: 'Descriptions',
        question: 'Is this description clear and complete?',
        answers: 'Description is fine · Rewrite it',
        help: 'Field and class descriptions that are very short or carry a TODO note.',
        rules: ['terse-description', 'todo-marker'],
      },
      {
        id: 'links',
        title: 'Outside standards',
        question: 'Does this class line up with an outside standard (DCAT, PROV-O, Phenopackets, ...)?',
        answers: 'Remove a bad link · No match exists · add one on its page',
        help: 'Ported classes that point to no outside standard, or point to a web page instead of a term.',
        rules: ['class-no-alignment', 'mapping-target-is-doc-link'],
      },
      {
        id: 'structure',
        title: 'Shared fields',
        question: 'Does this field mean the same thing in every class that uses it?',
        answers: 'Fine as is · fix on its page',
        help: 'Fields listed by more than one class.',
        rules: ['shared-slot'],
      },
      { ...SIGNOFF, help: 'Classes, fields and modules with no known problems that nobody has looked at yet. Most need only a quick read.' },
    ],
  },
];

export const trackOf = (kind: string) => TRACKS.find((t) => t.kinds.includes(kind))!;

/** One ready-made answer: clicking it saves this decision. */
export interface Action {
  label: string;
  verdict: string;
  operation?: Record<string, unknown>;
  rationale: string;          // default; the row's note replaces it
  evidence?: string;          // finding id the answer responds to
  also?: string[];            // other subjects the decision touches
  tone?: 'primary' | 'neutral' | 'danger';
  input?: 'description' | 'examples';  // read the row's editor into the operation
  confirm?: string;           // ask before saving
}

/** A choice inside an item, e.g. one suggested link with accept/reject. */
export interface Choice {
  text: string;
  detail?: string;
  actions: Action[];
}

export interface Item {
  sid: string;
  kind: string;
  title: string;
  href: string;
  browse: string | null;
  container: string | null;
  containerLabel: string | null;
  description: string;
  reasons: string[];
  choices: Choice[];
  actions: Action[];
  editor?: { field: 'description' | 'examples'; value: string; placeholder: string };
  findings: string[];     // ids of this type's open findings on the subject
  hash: string;
  score: number;
}

const queue = queueDoc as any[];
const payloads = (subjectsDoc as { subjects: Record<string, any> }).subjects;

// Suggested mappings by finding id (ontology and label are not on the finding).
const suggestionById: Record<string, any> = {};
for (const t of (suggestionsDoc as any).terms || []) {
  for (const m of t.suggested_mappings || []) suggestionById[m.id] = m;
}

// SO uses the element-type predicate (set/element rule, mappings/policy.yaml);
// EDAM gets closeMatch; anything else relatedMatch.
const predicateFor = (ontology: string) =>
  ontology === 'so' ? 'onga:has_element_type' : ontology === 'edam' ? 'skos:closeMatch' : 'skos:relatedMatch';

const nameOf = (sid: string) => {
  const s = subject(sid);
  return s ? (s.kind === 'term' ? s.label : s.name) : sid;
};

/** Open findings on a queue row: not cited by a decision, and no SSSOM row already covers a suggestion. */
function openFindings(row: any): any[] {
  return (row.findings || [])
    .filter((f: any) => !findingDecided(f.id))
    .map((f: any) => ({ ...findingsById[f.id], ...f }))
    .filter((f: any) => f.rule !== 'mapping-suggestion' || !hasSssomRow(row.sid, f.object ?? ''));
}

/** The review types (within its track) a queue row belongs to. */
export function typesOf(row: any): string[] {
  const track = trackOf(row.kind);
  const rules = new Set(openFindings(row).map((f) => f.rule));
  const hits = track.types.filter((t) => t.rules.some((r) => rules.has(r))).map((t) => t.id);
  return hits.length ? hits : ['signoff'];
}

/** Plain-language reason for one finding. */
function reason(f: any, sid: string): string {
  const m = f.message as string;
  switch (f.rule) {
    case 'no-mapping-at-all': return 'Not linked to any outside ontology.';
    case 'unmapped-high-usage': {
      const n = /has (\d+) ENCODE files/.exec(m)?.[1];
      return `Used by ${n ? Number(n).toLocaleString('en-US') : 'many'} ENCODE files, but not linked to any outside ontology.`;
    }
    case 'unreviewed-mapping': {
      const link = /' (\S+ \S+) has no mapping/.exec(m)?.[1];
      return `Has a link nobody has checked: ${link ?? m}.`;
    }
    case 'class-no-alignment': return 'Does not point to any outside standard.';
    case 'coverage-gap': return 'The automatic matcher found nothing similar in other ontologies.';
    case 'mapping-suggestion': return '';
    case 'terse-description': {
      const n = /is (\d+) chars/.exec(m)?.[1];
      return `Definition is very short${n ? ` (${n} characters)` : ''}.`;
    }
    case 'enum-value-no-description': return 'Has no definition.';
    case 'todo-marker': return `Has a TODO note: ${m.replace(/^.*?comment /, '')}`;
    case 'similar-terms': {
      const other = (f.subjects as string[]).find((s) => s !== sid);
      const score = /similarity ([\d.]+)/.exec(m)?.[1];
      return `Reads almost the same as "${other ? nameOf(other) : '?'}"${score ? ` (similarity ${score})` : ''}.`;
    }
    case 'zero-usage-term': return 'No ENCODE file uses this term.';
    case 'orphan-facet-value': return 'Nothing else refers to this value.';
    case 'required-policy': return 'Marked required, but it is not an identifier. Every required field is extra work for adopters.';
    case 'slot-no-examples': return 'Has no examples.';
    default: return m;
  }
}

function actionsFor(type: string, row: any, found: any[]): { choices: Choice[]; actions: Action[]; editor?: Item['editor'] } {
  const sid = row.sid;
  const payload = payloads[sid]?.payload ?? {};
  const choices: Choice[] = [];
  const actions: Action[] = [];
  let editor: Item['editor'];
  const has = (rule: string) => found.find((f) => f.rule === rule);

  if (type === 'signoff') {
    actions.push({ label: 'Looks right', verdict: 'keep', rationale: 'Reviewed; no problems found.', tone: 'primary' });
  }

  if (type === 'links') {
    for (const f of found.filter((x) => x.rule === 'mapping-suggestion')) {
      const s = suggestionById[f.id];
      if (!s) continue;
      const object = toCurie(s.term_id);
      const op = { predicate: predicateFor(s.ontology), object, object_label: s.term_name };
      // An SO link says what each feature in the set is, and needs a fit grade
      // (mappings/policy.yaml): one button per grade instead of a plain Accept.
      const accept: Action[] = s.ontology === 'so'
        ? ([['Exact fit', 'exact', 'is exactly'], ['Close enough', 'approximate', 'is the nearest SO match for'],
          ['SO term too broad', 'broad', 'is broader than']] as const).map(([label, fit, phrase], i) => ({
          label, verdict: 'adopt_mapping', operation: { ...op, element_type_fit: fit }, evidence: f.id,
          tone: i === 0 ? 'primary' as const : 'neutral' as const,
          rationale: `${s.term_name} ${phrase} the kind of feature in this set.`,
        }))
        : [{ label: 'Accept', verdict: 'adopt_mapping', operation: op, evidence: f.id, tone: 'primary',
          rationale: `Accepted suggested link to ${object} (${s.term_name}).` }];
      choices.push({
        text: `${s.term_name} (${object})`,
        detail: `${String(s.ontology).toUpperCase()} · similarity ${Number(s.similarity).toFixed(2)}${s.definition ? ` · ${s.definition}` : ''}`,
        actions: [...accept,
          { label: 'Reject', verdict: 'reject_mapping', operation: op, evidence: f.id, tone: 'danger',
            rationale: `${s.term_name} is not a match.` }],
      });
    }
    const unrev = has('unreviewed-mapping');
    const link = unrev && /' (\S+) (\S+) has no mapping/.exec(unrev.message);
    if (link) {
      const op = { predicate: link[1], object: link[2] };
      choices.push({
        text: `Existing link: ${link[1]} ${link[2]}`,
        actions: [
          { label: 'Confirm link', verdict: 'adopt_mapping', operation: op, evidence: unrev.id, tone: 'primary',
            rationale: `Checked the existing link to ${link[2]}; it is right.` },
          { label: 'Remove link', verdict: 'reject_mapping', operation: op, evidence: unrev.id, tone: 'danger',
            rationale: `The existing link to ${link[2]} is wrong.` },
        ],
      });
    }
    const doc = has('mapping-target-is-doc-link');
    const docLink = doc && /(\w+_mappings) value (\S+) is a documentation page/.exec(doc.message);
    if (docLink) {
      choices.push({
        text: `Link to a web page, not a term: ${docLink[2]}`,
        actions: [{ label: 'Remove link', verdict: 'reject_mapping', evidence: doc.id, tone: 'primary',
          operation: { predicate: docLink[1], object: docLink[2] },
          rationale: 'The link points at a documentation page, not a term.' }],
      });
    }
    actions.push({ label: 'No match exists', verdict: 'keep', tone: 'neutral',
      evidence: (has('no-mapping-at-all') ?? has('unmapped-high-usage') ?? has('coverage-gap') ?? has('class-no-alignment'))?.id,
      rationale: 'No suitable term in outside ontologies; this stays ONGA-only.' });
  }

  if (type === 'definitions') {
    const f = has('terse-description') ?? has('enum-value-no-description') ?? has('todo-marker');
    editor = { field: 'description', value: payload.description ?? '', placeholder: 'Write the definition' };
    actions.push({ label: 'Save new definition', verdict: 'edit_description', input: 'description', evidence: f?.id,
      tone: 'primary', rationale: 'Rewrote the definition.' });
    actions.push({ label: 'Definition is fine', verdict: 'keep', evidence: f?.id, tone: 'neutral',
      rationale: 'Definition is clear as it is.' });
  }

  if (type === 'duplicates' || type === 'structure') {
    for (const f of found.filter((x) => x.rule === 'similar-terms')) {
      const other = (f.subjects as string[]).find((s) => s !== sid);
      if (!other || !subject(other) || subject(other)!.retired) continue;
      choices.push({
        text: `"${nameOf(sid)}" vs "${nameOf(other)}"`,
        actions: [
          { label: `Merge into "${nameOf(other)}"`, verdict: 'merge', evidence: f.id, also: [other], tone: 'danger',
            operation: { into: other, mappings: 'move' },
            confirm: `Merge "${nameOf(sid)}" into "${nameOf(other)}"? This term goes away when applied.`,
            rationale: `Same meaning as "${nameOf(other)}".` },
          { label: 'Different things', verdict: 'keep', evidence: f.id, also: [other], tone: 'neutral',
            rationale: `Different from "${nameOf(other)}".` },
        ],
      });
    }
    const compound = has('residual-compound');
    if (compound) actions.push({ label: 'Keep as one term', verdict: 'keep_atomic', evidence: compound.id, tone: 'neutral',
      rationale: 'This is one concept, not a compound of facets.' });
    const other = has('inline-enum') ?? has('shared-slot');
    if (other) actions.push({ label: 'Fine as is', verdict: 'keep', evidence: other.id, tone: 'neutral',
      rationale: 'Reviewed; leave as is.' });
  }

  if (type === 'keep-or-cut') {
    const f = has('zero-usage-term') ?? has('orphan-facet-value');
    actions.push({ label: 'Keep', verdict: 'keep', evidence: f?.id, tone: 'primary',
      rationale: 'Worth keeping even though nothing uses it yet.' });
    actions.push({ label: 'Delete', verdict: 'delete', evidence: f?.id, tone: 'danger',
      confirm: `Delete "${nameOf(sid)}"? It goes away when applied.`, rationale: 'Unused and not needed.' });
  }

  if (type === 'fields') {
    const req = has('required-policy');
    if (req) {
      choices.push({
        text: 'Should this field be required?',
        actions: [
          { label: 'Required', verdict: 'set_cardinality', operation: { required: true }, evidence: req.id, tone: 'neutral',
            rationale: 'Records are meaningless without it; keep it required.' },
          { label: 'Recommended', verdict: 'set_cardinality', operation: { required: false, recommended: true }, evidence: req.id,
            tone: 'primary', rationale: 'Useful but not essential; make it recommended.' },
          { label: 'Optional', verdict: 'set_cardinality', operation: { required: false, recommended: false }, evidence: req.id,
            tone: 'neutral', rationale: 'Make it optional.' },
        ],
      });
    }
    const ex = has('slot-no-examples');
    if (ex) {
      editor = { field: 'examples', value: '', placeholder: 'One example value per line' };
      actions.push({ label: 'Save examples', verdict: 'set_examples', input: 'examples', evidence: ex.id, tone: 'primary',
        rationale: 'Added examples.' });
    }
    actions.push({ label: 'Fine as is', verdict: 'keep', evidence: (req ?? ex)?.id, tone: 'neutral',
      rationale: 'Field is set up right as it is.' });
  }

  // Drop answers whose verdict this kind does not have (e.g. keep_atomic on a slot).
  const allowed = new Set(verdictsFor(row.kind).map(([v]) => v));
  const ok = (a: Action) => allowed.has(a.verdict);
  return {
    choices: choices.map((c) => ({ ...c, actions: c.actions.filter(ok) })).filter((c) => c.actions.length),
    actions: actions.filter(ok),
    editor,
  };
}

/** The rows on one review type's page, in queue order. */
export function itemsFor(trackId: string, type: string): Item[] {
  const track = TRACKS.find((t) => t.id === trackId)!;
  const def = track.types.find((t) => t.id === type)!;
  const out: Item[] = [];
  for (const row of queue) {
    if (!track.kinds.includes(row.kind) || !typesOf(row).includes(type)) continue;
    const found = openFindings(row).filter((f) => def.rules.includes(f.rule));
    const { choices, actions, editor } = actionsFor(type, row, found);
    const container = row.container ?? null;
    out.push({
      sid: row.sid,
      kind: row.kind,
      title: row.kind === 'term' ? row.label : row.name,
      href: row.href,
      browse: row.browse ?? null,
      container,
      containerLabel: container ? nameOf(container) : null,
      description: payloads[row.sid]?.payload?.description ?? '',
      // "Used by N files, not linked" already says "not linked".
      reasons: [...new Set(found
        .filter((f) => f.rule !== 'no-mapping-at-all' || !found.some((x) => x.rule === 'unmapped-high-usage'))
        .map((f) => reason(f, row.sid)).filter(Boolean))],
      choices,
      actions,
      editor,
      findings: found.map((f) => f.id),
      hash: row.hash,
      score: row.score,
    });
  }
  return out;
}

/** Item count per review type in a track. */
export function typeCounts(trackId: string): Record<string, number> {
  const track = TRACKS.find((t) => t.id === trackId)!;
  const counts: Record<string, number> = Object.fromEntries(track.types.map((t) => [t.id, 0]));
  for (const row of queue) {
    if (!track.kinds.includes(row.kind)) continue;
    for (const t of typesOf(row)) counts[t]++;
  }
  return counts;
}
