import { readFileSync } from 'node:fs';
import { join } from 'node:path';

const root = join(__dirname, '../..');
export const MOCK_HTML = readFileSync(join(root, 'mock-exchange/public/index.html'), 'utf8');
export const MOCK_CSS = readFileSync(join(root, 'mock-exchange/public/app.css'), 'utf8');
export const MOCK_JS = readFileSync(join(root, 'mock-exchange/public/app.js'), 'utf8');

/** Put the mock page's body markup (and CSS) into the current jsdom document. */
export function loadMockMarkup(doc: Document = document): void {
  const body = /<body>([\s\S]*)<\/body>/.exec(MOCK_HTML)?.[1] ?? '';
  doc.head.innerHTML = `<style>${MOCK_CSS}</style>`;
  doc.body.innerHTML = body.replace(/<script[\s\S]*?<\/script>/g, '');
}

/** Fill the mock chain with rows like the mock app renders them. */
export function fillChain(doc: Document, rows: { K: number; c: [number, number, number, number]; p: [number, number, number, number] }[], und = 'OIL') {
  const tb = doc.querySelector('.chain tbody') as HTMLElement;
  tb.innerHTML = rows
    .map(({ K, c, p }) => {
      const cs = `${und}_0626_C${K}`;
      const ps = `${und}_0626_P${K}`;
      return `<tr><td>${c[0]}</td><td class="px" data-sym="${cs}" data-side="bid">${c[1].toFixed(2)}</td><td class="px" data-sym="${cs}" data-side="ask">${c[2].toFixed(2)}</td><td>${c[3]}</td><td class="strike">${K}</td><td>${p[0]}</td><td class="px" data-sym="${ps}" data-side="bid">${p[1].toFixed(2)}</td><td class="px" data-sym="${ps}" data-side="ask">${p[2].toFixed(2)}</td><td>${p[3]}</td></tr>`;
    })
    .join('');
}
