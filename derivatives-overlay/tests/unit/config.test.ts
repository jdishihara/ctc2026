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
  it('auto-pilot defaults: confirm on, submit off; the submit cap cannot exceed the browser limit', () => {
    expect(DEFAULT_CONFIG.auto).toMatchObject({ confirm: true, converter: true, submit: false });
    expect(DEFAULT_CONFIG.auto.submitRateCap).toBeLessThan(40);
    expect(validateConfig({ auto: { submit: true } }).ok).toBe(true);
    const v = validateConfig({ auto: { submitRateCap: 50, volMin: 2, volMax: 1, confirm: 'yes' } });
    expect(v.ok).toBe(false);
    expect(v.errors.join('\n')).toMatch(/submitRateCap must not exceed/);
    expect(v.errors.join('\n')).toMatch(/volMin must be below/);
    expect(v.errors.join('\n')).toMatch(/auto\.confirm must be true or false/);
  });
  it('cloneDefaults is a deep copy', () => {
    const a = cloneDefaults();
    a.thresholds.minEdge = 9;
    expect(DEFAULT_CONFIG.thresholds.minEdge).toBe(0.05);
  });
});
