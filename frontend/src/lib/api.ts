// Typed API client. All requests go through `request`, which maps the backend error envelope to ApiError.
import type {
  AnalysisDetail,
  AnalysisList,
  AnalysisStatusOut,
  AppConfig,
  LinesPage,
  LinesQuery,
  SampleRequest,
} from "./types";

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: Record<string, unknown> = {},
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, init);
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", "Cannot reach the LogLens API. Is the backend running?");
  }
  if (!response.ok) {
    let code = "HTTP_ERROR";
    let message = `Request failed (${response.status})`;
    let details: Record<string, unknown> = {};
    try {
      const body = await response.json();
      if (body?.error) {
        code = body.error.code ?? code;
        message = body.error.message ?? message;
        details = body.error.details ?? {};
      }
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, code, message, details);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

function query(params: Record<string, string | number | boolean | string[] | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === "" || value === false) continue;
    if (Array.isArray(value)) value.forEach((v) => search.append(key, v));
    else search.set(key, String(value));
  }
  const s = search.toString();
  return s ? `?${s}` : "";
}

export const api = {
  config: () => request<AppConfig>("/api/v1/config"),
  upload: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return request<AnalysisStatusOut>("/api/v1/analyses", { method: "POST", body: form });
  },
  analyzeSample: (body: SampleRequest) =>
    request<AnalysisStatusOut>("/api/v1/samples/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  sampleDownloadUrl: (body: SampleRequest) =>
    `${BASE}/api/v1/samples/download${query({ scenario: body.scenario, lines: body.lines, format: body.format })}`,
  list: (limit = 20, offset = 0) => request<AnalysisList>(`/api/v1/analyses${query({ limit, offset })}`),
  status: (id: string) => request<AnalysisStatusOut>(`/api/v1/analyses/${encodeURIComponent(id)}/status`),
  get: (id: string) => request<AnalysisDetail>(`/api/v1/analyses/${encodeURIComponent(id)}`),
  remove: (id: string) => request<void>(`/api/v1/analyses/${encodeURIComponent(id)}`, { method: "DELETE" }),
  lines: (id: string, q: LinesQuery) =>
    request<LinesPage>(
      `/api/v1/analyses/${encodeURIComponent(id)}/lines${query({
        q: q.q,
        severity: q.severity,
        service: q.service,
        malformed_only: q.malformed_only,
        line_numbers: q.line_numbers?.join(","),
        around_line: q.around_line,
        page: q.page,
        page_size: q.page_size,
      })}`,
    ),
  exportUrl: (id: string, format: "json" | "markdown") =>
    `${BASE}/api/v1/analyses/${encodeURIComponent(id)}/export?format=${format}`,
};
