// Builds dist/ (Cornell only) or dist-dev/ (localhost mock only).
import { build } from 'esbuild';
import { readFileSync, writeFileSync, mkdirSync, rmSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const dev = process.argv.includes('--dev');
const outdir = join(root, dev ? 'dist-dev' : 'dist');
const MOCK_ORIGIN = 'http://localhost:5317/*';

rmSync(outdir, { recursive: true, force: true });
mkdirSync(outdir, { recursive: true });

const common = {
  bundle: true,
  format: 'iife',
  target: 'chrome110',
  minify: !dev,
  sourcemap: dev ? 'inline' : false,
  legalComments: 'none',
  jsx: 'automatic',
  jsxImportSource: 'preact',
  loader: { '.css': 'text' },
  define: { __DEV__: JSON.stringify(dev) },
  logLevel: 'warning',
};

await build({ ...common, entryPoints: [join(root, 'src/main-world/hooks.ts')], outfile: join(outdir, 'main.js') });
await build({ ...common, entryPoints: [join(root, 'src/content/index.ts')], outfile: join(outdir, 'overlay.js') });

const manifest = JSON.parse(readFileSync(join(root, 'manifest.base.json'), 'utf8'));
if (dev) {
  manifest.name += ' (dev)';
  for (const cs of manifest.content_scripts) cs.matches = [MOCK_ORIGIN];
  for (const resource of manifest.web_accessible_resources ?? []) resource.matches = [MOCK_ORIGIN];
}
writeFileSync(join(outdir, 'manifest.json'), JSON.stringify(manifest, null, 2));

// Safety: the bundles must never contain dynamic code evaluation.
for (const f of ['main.js', 'overlay.js']) {
  const src = readFileSync(join(outdir, f), 'utf8');
  if (/(^|[^.\w$])eval\s*\(|new\s+Function\s*\(/.test(src)) throw new Error(`${f} contains eval/new Function`);
  if (!dev && src.includes('localhost:5317')) throw new Error(`${f} references the mock origin in a prod build`);
}
console.log(`built ${outdir}`);
