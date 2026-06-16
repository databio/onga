// @ts-check
import { defineConfig } from 'astro/config';

import tailwindcss from '@tailwindcss/vite';

// https://astro.build/config
export default defineConfig({
  // Published as a GitHub Pages project site under the databio org pages domain
  // (databio.github.io has CNAME dev.databio.org), so it serves at
  // https://dev.databio.org/onga/. The base path must match the repo name.
  site: 'https://dev.databio.org',
  base: '/onga',
  vite: {
    plugins: [tailwindcss()]
  }
});