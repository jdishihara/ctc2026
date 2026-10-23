// Hand-written tokenizer + Pratt parser for analyst formulas. No eval / new Function.
// Variables: x S T K (and constants pi, e). Functions: sqrt ln log exp abs min max normcdf norminv.
import { normCdf, normInv } from './normal';

type Tok = { t: 'num'; v: number } | { t: 'id'; v: string } | { t: 'op'; v: string } | { t: 'end' };

export type Node =
  | { k: 'num'; v: number }
  | { k: 'var'; name: string }
  | { k: 'neg'; a: Node }
  | { k: 'bin'; op: string; a: Node; b: Node }
  | { k: 'call'; fn: string; args: Node[] };

export const VARIABLES = ['x', 'S', 'T', 'K'] as const;
const CONSTANTS: Record<string, number> = { pi: Math.PI, e: Math.E };
const FUNCS: Record<string, { arity: [number, number]; f: (...a: number[]) => number }> = {
  sqrt: { arity: [1, 1], f: Math.sqrt },
  ln: { arity: [1, 1], f: Math.log },
  log: { arity: [1, 1], f: Math.log10 },
  exp: { arity: [1, 1], f: Math.exp },
  abs: { arity: [1, 1], f: Math.abs },
  min: { arity: [1, 16], f: Math.min },
  max: { arity: [1, 16], f: Math.max },
  normcdf: { arity: [1, 1], f: normCdf },
  norminv: { arity: [1, 1], f: normInv },
};

export class ExprError extends Error {}

function tokenize(src: string): Tok[] {
  if (src.length > 500) throw new ExprError('expression too long');
  const out: Tok[] = [];
  let i = 0;
  while (i < src.length) {
    const ch = src[i];
    if (/\s/.test(ch)) { i++; continue; }
    const num = /^(?:\d+\.?\d*|\.\d+)(?:[eE][+-]?\d+)?/.exec(src.slice(i));
    if (num) { out.push({ t: 'num', v: Number(num[0]) }); i += num[0].length; continue; }
    const id = /^[A-Za-z_][A-Za-z0-9_]*/.exec(src.slice(i));
    if (id) { out.push({ t: 'id', v: id[0] }); i += id[0].length; continue; }
    if ('+-*/^(),'.includes(ch)) { out.push({ t: 'op', v: ch }); i++; continue; }
    if (ch === '−') { out.push({ t: 'op', v: '-' }); i++; continue; }
    throw new ExprError(`unexpected character '${ch}'`);
  }
  out.push({ t: 'end' });
  return out;
}

const BP: Record<string, number> = { '+': 10, '-': 10, '*': 20, '/': 20, '^': 30 };

export function parseExpr(src: string): Node {
  const toks = tokenize(src);
  let p = 0;
  const peek = () => toks[p];
  const next = () => toks[p++];
  const expectOp = (v: string) => {
    const t = next();
    if (t.t !== 'op' || t.v !== v) throw new ExprError(`expected '${v}'`);
  };
  function nud(t: Tok): Node {
    if (t.t === 'num') return { k: 'num', v: t.v };
    if (t.t === 'op' && t.v === '-') return { k: 'neg', a: expr(25) };
    if (t.t === 'op' && t.v === '+') return expr(25);
    if (t.t === 'op' && t.v === '(') {
      const e = expr(0);
      expectOp(')');
      return e;
    }
    if (t.t === 'id') {
      const nt = peek();
      if (nt.t === 'op' && nt.v === '(') {
        const fn = t.v.toLowerCase();
        if (!Object.prototype.hasOwnProperty.call(FUNCS, fn)) throw new ExprError(`unknown function '${t.v}'`);
        next();
        const args: Node[] = [];
        const close = peek();
        if (!(close.t === 'op' && close.v === ')')) {
          for (;;) {
            args.push(expr(0));
            const s = next();
            if (s.t === 'op' && s.v === ',') continue;
            if (s.t === 'op' && s.v === ')') break;
            throw new ExprError("expected ',' or ')'");
          }
        } else next();
        const [lo, hi] = FUNCS[fn].arity;
        if (args.length < lo || args.length > hi) throw new ExprError(`${fn} takes ${lo === hi ? lo : `${lo}-${hi}`} argument(s)`);
        return { k: 'call', fn, args };
      }
      if ((VARIABLES as readonly string[]).includes(t.v)) return { k: 'var', name: t.v };
      if (Object.prototype.hasOwnProperty.call(CONSTANTS, t.v)) return { k: 'num', v: CONSTANTS[t.v] };
      throw new ExprError(`unknown identifier '${t.v}'`);
    }
    throw new ExprError('unexpected token');
  }
  function expr(rbp: number): Node {
    let left = nud(next());
    for (;;) {
      const t = peek();
      if (t.t !== 'op' || !(t.v in BP)) break;
      const bp = BP[t.v];
      if (bp <= rbp) break;
      next();
      const right = expr(t.v === '^' ? bp - 1 : bp);
      left = { k: 'bin', op: t.v, a: left, b: right };
    }
    return left;
  }
  const root = expr(0);
  if (peek().t !== 'end') throw new ExprError('unexpected trailing input');
  return root;
}

export type Vars = Partial<Record<(typeof VARIABLES)[number], number>>;

export function evalNode(n: Node, vars: Vars): number {
  switch (n.k) {
    case 'num': return n.v;
    case 'var': {
      const v = vars[n.name as keyof Vars];
      if (v == null) throw new ExprError(`variable ${n.name} has no value`);
      return v;
    }
    case 'neg': return -evalNode(n.a, vars);
    case 'bin': {
      const a = evalNode(n.a, vars);
      const b = evalNode(n.b, vars);
      switch (n.op) {
        case '+': return a + b;
        case '-': return a - b;
        case '*': return a * b;
        case '/': return a / b;
        case '^': return Math.pow(a, b);
      }
      throw new ExprError('bad operator');
    }
    case 'call': return FUNCS[n.fn].f(...n.args.map((x) => evalNode(x, vars)));
  }
}

export function compileExpr(src: string): { ok: true; run: (v: Vars) => number } | { ok: false; error: string } {
  try {
    const node = parseExpr(src);
    return { ok: true, run: (v: Vars) => evalNode(node, v) };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e.message : String(e) };
  }
}

export function evaluate(src: string, vars: Vars): number {
  return evalNode(parseExpr(src), vars);
}
