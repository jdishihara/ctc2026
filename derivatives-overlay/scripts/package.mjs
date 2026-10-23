// Zips dist/ into derivatives-overlay.zip using the system zip tool (no extra dependency).
import { execFileSync } from 'node:child_process';
import { existsSync, rmSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const out = join(root, 'derivatives-overlay.zip');
if (!existsSync(join(root, 'dist/manifest.json'))) throw new Error('run npm run build first');
rmSync(out, { force: true });
execFileSync('zip', ['-r', '-q', out, '.'], { cwd: join(root, 'dist') });
console.log('wrote ' + out);
