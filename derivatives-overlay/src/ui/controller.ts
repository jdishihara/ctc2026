import { Validation } from '../core/config';
import { Store } from '../state/store';
import { Ticket } from '../engine/tickets';

export interface Controller {
  store: Store;
  loadNext(kind: 'edge' | 'flatten'): void;
  loadTicket(t: Ticket): void;
  downloadCapture(): void;
  saveConfig(json: string): Validation;
  resetConfig(): void;
  patchConfig(patch: Record<string, unknown>): void;
  saveUi(): void;
  copy(text: string): void;
  /** arm or disarm the auto-pilot (Config auto.submit); arming also clears a pause */
  setAutoSubmit(on: boolean): void;
  /** Alt+P */
  toggleAutoPause(): void;
}

export function ticketText(t: Ticket): string {
  return `${t.side} ${t.qty} ${t.symbol} LIMIT @ ${t.price}`;
}
