// Browser client for the local curation daemon (scripts/curation_server.py).
//
// The daemon runs only on a curator's machine (`make curate`) and listens on
// loopback. The published site (dev.databio.org/onga) never reaches it: probe()
// resolves to null there and every page renders read-only from the generated
// JSON under src/data/develop/. Import this only from client <script>s.
//
// Mode is decided once per page load: probe() does one cached health check with
// a 400 ms timeout, and only when the page itself is served from localhost (so
// the public site never makes a request to 127.0.0.1).

export const CURATION_API = 'http://127.0.0.1:8781';

export interface Health {
  ok: boolean;
  repo_root: string;
  git_branch: string;
  schema_fingerprint: string;
  decision_count: number;
  working_tree_dirty: boolean;
  decided_by: string;
  apply_available: boolean;
}

export interface Evidence { kind: string; id?: string; detail?: string }

/** What the browser sends; the daemon sets id, decided_by/on, status, origin, fingerprint. */
export interface DecisionDraft {
  subject: string;
  verdict: string;
  operation: Record<string, unknown> | null;
  rationale: string;
  also_affects: string[];
  evidence: Evidence[];
  subject_hashes: Record<string, string>;
  supersedes?: string | null;
}

export interface Decision extends DecisionDraft {
  id: string;
  decided_by: string;
  decided_on: string;
  schema_fingerprint: string;
  status: 'pending' | 'applied' | 'withdrawn';
  applied: { on: string | null; subject_hashes_after: Record<string, string> | null; created: string[]; retired: string[] };
  origin: { kind: string; ref: string | null };
}

export interface Store { version: number; next_id: number; decisions: Decision[]; mtime_ns: number }

/** A daemon error: `status` is the HTTP code (409 = the store or a subject changed; reload). */
export class CurationError extends Error {
  constructor(public status: number, public errors: string[], public store?: Store) {
    super(errors.join('; '));
  }
}

let probed: Promise<Health | null> | null = null;
let mtime: string | null = null;

/** The daemon's health, or null in static (read-only) mode. Cached per page load. */
export function probe(): Promise<Health | null> {
  if (probed) return probed;
  const local = ['localhost', '127.0.0.1', '[::1]'].includes(location.hostname);
  probed = !local ? Promise.resolve(null) : (async () => {
    try {
      const res = await fetch(`${CURATION_API}/api/health`, { signal: AbortSignal.timeout(400) });
      return res.ok ? ((await res.json()) as Health) : null;
    } catch {
      return null;
    }
  })();
  return probed;
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (method !== 'GET' && mtime) headers['X-Store-Mtime'] = mtime;
  const res = await fetch(`${CURATION_API}${path}`, {
    method, headers, body: body === undefined ? undefined : JSON.stringify(body),
  });
  const m = res.headers.get('X-Store-Mtime');
  if (m) mtime = m;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new CurationError(res.status, data.errors || [res.statusText], data.store);
  return data as T;
}

let storePromise: Promise<Store> | null = null;

/** The whole decision store. Cached; pass `fresh` to refetch (after a save or a 409). */
export function getDecisions(fresh = false): Promise<Store> {
  if (fresh || !storePromise) {
    storePromise = call<Store>('GET', '/api/decisions');
    storePromise.catch(() => { storePromise = null; });
  }
  return storePromise;
}

/** Create a decision, or replace pending decision `id`. Returns the stored record. */
export async function saveDecision(draft: DecisionDraft, id?: string): Promise<Decision> {
  const out = id
    ? await call<{ decision: Decision }>('PUT', `/api/decisions/${id}`, draft)
    : await call<{ decision: Decision }>('POST', '/api/decisions', draft);
  storePromise = null;
  notify(out.decision);
  return out.decision;
}

/** Withdraw a decision (status: withdrawn; the record stays in the store). */
export async function withdrawDecision(id: string): Promise<Decision> {
  const out = await call<{ decision: Decision }>('DELETE', `/api/decisions/${id}`);
  storePromise = null;
  notify(out.decision);
  return out.decision;
}

/** Set `status:` of an upstream request in proposals/upstream_requests.yaml. */
export function patchProposal(id: string, status: 'proposed' | 'filed' | 'accepted' | 'declined' | 'withdrawn') {
  return call<{ id: string; status: string }>('PATCH', `/api/proposals/${id}`, { status });
}

/**
 * Run the apply engine (all pending decisions, or `ids`), streaming its output
 * line by line to `onLine`. Resolves to the engine's exit code.
 */
export async function apply(
  opts: { dryRun?: boolean; ids?: string[]; onLine?: (line: string) => void } = {},
): Promise<number> {
  const res = await fetch(`${CURATION_API}/api/apply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ dry_run: !!opts.dryRun, ids: opts.ids }),
  });
  if (!res.ok || !res.body) {
    const data = await res.json().catch(() => ({}));
    throw new CurationError(res.status, data.errors || [res.statusText]);
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buf = '';
  let code = -1;
  for (;;) {
    const { value, done } = await reader.read();
    if (value) buf += value;
    const lines = done ? buf.split('\n') : buf.split('\n').slice(0, -1);
    buf = done ? '' : buf.slice(buf.lastIndexOf('\n') + 1);
    for (const line of lines) {
      const m = /^exit (-?\d+)$/.exec(line);
      if (m) code = Number(m[1]);
      else opts.onLine?.(line);
    }
    if (done) break;
  }
  storePromise = null;
  return code;
}

/** Fired on `document` after any save or withdraw, so other controls on the page can refresh. */
export const DECISION_EVENT = 'curation:decision';

function notify(decision: Decision) {
  document.dispatchEvent(new CustomEvent(DECISION_EVENT, { detail: decision }));
}
