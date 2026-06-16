// Base-aware link helper.
//
// The site is served from a sub-path (https://dev.databio.org/onga/), so every
// internal link must be prefixed with import.meta.env.BASE_URL ('/onga/').
// Astro auto-prefixes its own bundled assets, but NOT author-written links, so
// wrap every internal href/src with url().
//
// External links (http(s), mailto:, protocol-relative //, in-page #anchors) and
// already-relative links are passed through untouched, so url() is safe to apply
// uniformly — including to dynamic values that might be external.

const BASE = import.meta.env.BASE_URL; // e.g. '/onga/'

export function url(path: string = '/'): string {
  if (!path.startsWith('/') || path.startsWith('//')) return path;
  return BASE.replace(/\/$/, '') + path;
}
