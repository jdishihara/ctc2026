// Exercise the actual build outputs: mock practice must never inject into Cornell.
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const builds = [
  { flag: '--dev', directory: 'dist-dev', origin: 'http://localhost:5317/*' },
  { flag: '--prod', directory: 'dist', origin: 'https://cornelltradingcompetition.org/*' },
];

for (const build of builds) {
  execFileSync(process.execPath, [join(root, 'scripts/build.mjs'), build.flag], { cwd: root, stdio: 'pipe' });
  const manifest = JSON.parse(readFileSync(join(root, build.directory, 'manifest.json'), 'utf8'));
  test(`${build.directory} injects only into its own exchange`, () => {
    assert.equal(manifest.content_scripts.length, 2);
    for (const script of manifest.content_scripts) assert.deepEqual(script.matches, [build.origin]);
    for (const resource of manifest.web_accessible_resources ?? []) assert.deepEqual(resource.matches, [build.origin]);
    assert.deepEqual(manifest.permissions, ['storage']);
    assert.deepEqual(manifest.host_permissions ?? [], []);
  });
  test(`${build.directory} describes optional order submission accurately`, () => {
    assert.match(manifest.description, /optional.*order submission/i);
    assert.doesNotMatch(manifest.description, /read.only|never submits/i);
  });
}
