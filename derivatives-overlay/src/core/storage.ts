// chrome.storage.local with fallbacks (localStorage, then memory). Every call is wrapped; failures are silent.

const mem = new Map<string, unknown>();

function chromeLocal(): chrome.storage.LocalStorageArea | null {
  try {
    return typeof chrome !== 'undefined' && chrome?.storage?.local ? chrome.storage.local : null;
  } catch {
    return null;
  }
}

export async function load<T>(key: string, fallback: T): Promise<T> {
  try {
    const area = chromeLocal();
    if (area) {
      const r = await area.get(key);
      return (r?.[key] as T) ?? fallback;
    }
  } catch {
    /* fall through */
  }
  try {
    const s = globalThis.localStorage?.getItem('derivOverlay:' + key);
    if (s != null) return JSON.parse(s) as T;
  } catch {
    /* fall through */
  }
  return (mem.get(key) as T) ?? fallback;
}

export async function save(key: string, value: unknown): Promise<void> {
  mem.set(key, value);
  try {
    const area = chromeLocal();
    if (area) {
      await area.set({ [key]: value });
      return;
    }
  } catch {
    /* fall through */
  }
  try {
    globalThis.localStorage?.setItem('derivOverlay:' + key, JSON.stringify(value));
  } catch {
    /* ignore */
  }
}

export async function remove(key: string): Promise<void> {
  mem.delete(key);
  try {
    await chromeLocal()?.remove(key);
  } catch {
    /* ignore */
  }
  try {
    globalThis.localStorage?.removeItem('derivOverlay:' + key);
  } catch {
    /* ignore */
  }
}
