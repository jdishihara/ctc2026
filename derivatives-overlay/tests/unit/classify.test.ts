import { describe, expect, it } from 'vitest';
import { FrameClassifier } from '../../src/core/classify';
import { Capture } from '../../src/core/capture';

const QUOTE = '{"type":"quote","symbol":"AQUA","bid":27.25,"ask":27.32,"bid_size":38,"ask_size":19,"timestamp":"2026-10-23T13:03:20.554930"}';
const TRADE = '{"type":"trade","symbol":"AQUA","price":27.25,"quantity":12,"timestamp":"2026-10-23T13:03:13.281876","trade_id":"d2519546-6541-432c-b269-7211b1713c7c"}';
const ACK = '{"type":"subscription_ack","symbols":["AQUA"],"channels":["news","quotes","trades"],"timestamp":"2026-10-23T13:03:20.554838"}';
const STORM = '{"type":"news","message":{"type":"storm","round":2,"storm":"Arlo","time":"1800-05-13T13:41:00","age":442,"x":682.4,"y":-59.2,"vx":1.43,"vy":-0.64,"radius":141.9,"intensity":0.777,"seq":550}}';

describe('frame classifier', () => {
  it('classifies the observed frame shapes', () => {
    const c = new FrameClassifier();
    expect(c.classifyWs('in', QUOTE).key).toBe('ws:quote');
    expect(c.classifyWs('in', TRADE).key).toBe('ws:trade');
    expect(c.classifyWs('in', ACK).key).toBe('ws:subscription_ack');
    const n = c.classifyWs('in', STORM);
    expect(n.key).toBe('ws:news:storm');
    expect(n.seq).toBe(550);
    expect(n.dup).toBe(false);
  });
  it('dedupes news by seq', () => {
    const c = new FrameClassifier();
    expect(c.classifyWs('in', STORM).dup).toBe(false);
    expect(c.classifyWs('in', STORM).dup).toBe(true);
    expect(c.classifyWs('in', STORM.replace('550', '551')).dup).toBe(false);
  });
  it('headline news, unknown types and highlights', () => {
    const c = new FrameClassifier();
    const h = c.classifyWs('in', '{"type":"news","message":{"headline":"Analyst 2 sees OIL vol at 55%","seq":3}}');
    expect(h.key).toBe('ws:news:headline');
    expect(h.highlights).toContain('vol/analyst');
    const u = c.classifyWs('in', '{"type":"greeks_update","symbol":"OIL_0626_C100"}');
    expect(u.key).toBe('ws:greeks_update');
    expect(u.highlights).toContain('new-type');
    const b = c.classifyWs('in', '{"type":"orderbook","symbol":"X","bids":[[1,2]],"asks":[[2,3]]}');
    expect(b.highlights).toContain('orderbook-like');
    const ub = c.classifyWs('in', '{"type":"depth","levels":[{"p":1}]}');
    expect(ub.highlights).toEqual(expect.arrayContaining(['new-type', 'orderbook-like']));
  });
  it('malformed JSON and binary never throw', () => {
    const c = new FrameClassifier();
    expect(c.classifyWs('in', '{not json').key).toBe('ws:malformed');
    expect(c.classifyWs('in', { binary: true, size: 10 }).key).toBe('ws-in:binary');
    expect(c.classifyWs('in', 'null').key).toBe('ws:untyped');
    expect(c.classifyWs('out', '{"action":"subscribe","symbols":[]}').key).toBe('ws-out:subscribe');
  });
  it('http keys strip the query string', () => {
    const c = new FrameClassifier();
    expect(c.classifyHttp('GET', 'https://cornelltradingcompetition.org/api/v1/positions?include_zero=true').key).toBe('http:GET /api/v1/positions');
    expect(c.classifyHttp('post', '/api/v1/orders', {}, '', true).key).toBe('req:POST /api/v1/orders');
  });
});

describe('capture buffer', () => {
  it('is a ring buffer with per-kind stats and JSON export', () => {
    const cap = new Capture(3);
    for (let i = 0; i < 5; i++) cap.add({ t: 1000 + i, key: i % 2 ? 'ws:quote' : 'ws:trade', dir: 'in', raw: String(i), highlights: [] });
    expect(cap.length).toBe(3);
    expect(cap.entries().map((e) => e.raw)).toEqual(['2', '3', '4']);
    expect(cap.kinds.get('ws:trade')?.count).toBe(3);
    const j = JSON.parse(cap.toJSON({ case: 'x' }));
    expect(j.entries).toHaveLength(3);
    expect(j.meta.case).toBe('x');
    cap.clear();
    expect(cap.length).toBe(0);
  });
});
