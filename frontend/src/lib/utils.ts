import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatNumber(n: number | null | undefined): string {
  return new Intl.NumberFormat("en-US").format(n ?? 0);
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

export function formatTime(iso: string | null | undefined, withDate = false): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const time = d.toISOString().slice(11, 23);
  return withDate ? `${d.toISOString().slice(0, 10)} ${time} UTC` : `${time}`;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  if (m < 60) return `${m}m ${seconds % 60}s`;
  return `${Math.floor(m / 60)}h ${m % 60}m`;
}

export const PATTERN_LABELS: Record<string, string> = {
  pool_exhaustion: "Connection pool",
  db_timeout: "DB timeout",
  auth_failure: "Auth failure",
  memory_pressure: "Memory",
  service_failure: "Service failure",
  disk_pressure: "Disk",
  rate_limit: "Rate limit",
};

export const SIGNAL_LABELS: Record<string, string> = {
  critical: "Critical",
  precursor: "Precursor",
  threshold: "Threshold breach",
  rare_high_severity: "Rare high-severity",
  pattern: "Pattern",
  prompt_injection: "Prompt injection",
};

export function lineLabel(first: number, last: number): string {
  return first === last ? `L${first}` : `L${first}–L${last}`;
}
