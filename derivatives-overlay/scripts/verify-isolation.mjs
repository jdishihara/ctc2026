// Fails if any path outside derivatives-overlay/ differs from the git status captured before the build started.
import { execSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = join(dirname(fileURLToPath(import.meta.url)), '..');
const repoRoot = execSync('git rev-parse --show-toplevel', { cwd: here }).toString().trim();
const outside = (txt) =>
  new Set(
    txt.split('\n').map((l) => l.trimEnd()).filter(Boolean)
      .filter((l) => !l.slice(3).replace(/^"|"$/g, '').startsWith('derivatives-overlay/')),
  );
const baseline = outside(readFileSync(join(here, '.isolation-baseline.txt'), 'utf8'));
const now = outside(execSync('git status --porcelain', { cwd: repoRoot }).toString());
const added = [...now].filter((l) => !baseline.has(l));
const removed = [...baseline].filter((l) => !now.has(l));
if (added.length || removed.length) {
  console.error('Isolation check FAILED. Paths outside derivatives-overlay/ changed:');
  for (const l of added) console.error('  + ' + l);
  for (const l of removed) console.error('  - ' + l);
  process.exit(1);
}
console.log(`Isolation OK: nothing outside derivatives-overlay/ changed (${baseline.size} pre-existing entries).`);
