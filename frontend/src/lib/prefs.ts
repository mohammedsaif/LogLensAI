// Client-side preferences persisted in localStorage (per browser). Reads/writes never throw.
export interface Prefs {
  pollIntervalMs: number;
  explorerPageSize: number;
  compactTables: boolean;
}

export const DEFAULT_PREFS: Prefs = { pollIntervalMs: 1000, explorerPageSize: 100, compactTables: false };
const KEY = "loglens.prefs.v1";

export function loadPrefs(): Prefs {
  try {
    const raw = localStorage.getItem(KEY);
    return raw ? { ...DEFAULT_PREFS, ...JSON.parse(raw) } : DEFAULT_PREFS;
  } catch {
    return DEFAULT_PREFS;
  }
}

export function savePrefs(prefs: Prefs): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(prefs));
  } catch {
    /* storage unavailable (private mode) */
  }
}
