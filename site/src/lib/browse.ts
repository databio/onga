// Build-time SID lookups for the browse pages, so each page can show the
// workbench state of what it renders. Reads the generated subject index only.

import { subjectIndex } from './develop';

const rows = Object.values(subjectIndex);

/** SID of the class or enum whose browse page is `path` (e.g. '/track-geometry'). */
export function pageSid(path: string): string | undefined {
  return rows.find((r) => r.browse === path && (r.kind === 'class' || r.kind === 'enum'))?.sid;
}

export const termSid = (ongaId: string) => `term:${ongaId}`;
export const slotSid = (name: string) => `slot:${name}`;

const norm = (s: string) => s.toLowerCase().replace(/[\s_-]+/g, '_');

/** The term row for a permissible value of `enumName`, matched by label. */
export function enumValue(enumName: string, value: string) {
  const want = norm(value);
  return rows.find((r) => r.kind === 'term' && r.container === `enum:${enumName}` && norm(r.label) === want);
}
