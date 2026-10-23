import { describe, expect, it } from 'vitest';
import { cloneDefaults, DEFAULT_CONFIG, validateConfig } from '../../src/core/config';

describe('runtime config', () => {
  it('defaults validate', () => {
    expect(validateConfig(DEFAULT_CONFIG).ok).toBe(true);
    expect(validateConfig(JSON.stringify(DEFAULT_CONFIG)).ok).toBe(true);
  });
  it('merges partial patches over defaults', () => {
    const v = validateConfig({ thresholds: { minEdge: 0.1 }, focus: 'OIL' });
    expect(v.ok).toBe(true);
    expect(v.config.thresholds.minEdge).toBe(0.1);
    expect(v.config.thresholds.positionLimit).toBe(300);
    expect(v.config.focus).toBe('OIL');
  });
  it('reports bad JSON, regexes and schedule rows', () => {
    expect(validateConfig('{nope').ok).toBe(false);
    const v = validateConfig({ symbolRegex: '([', schedule: [{ n: 1, date: 'x', news: '9', move: '10:00', snap: '11:00', round: 4 }], T_mode: 'nope' });
    expect(v.ok).toBe(false);
    expect(v.errors.join('\n')).toMatch(/symbolRegex/);
    expect(v.errors.join('\n')).toMatch(/schedule\[0\]\.date/);
    expect(v.errors.join('\n')).toMatch(/T_mode/);
  });
  it('cloneDefaults is a deep copy', () => {
    const a = cloneDefaults();
    a.thresholds.minEdge = 9;
    expect(DEFAULT_CONFIG.thresholds.minEdge).toBe(0.05);
  });
});
