import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi } from "vitest";
import fixture from "./fixtures/analysis.json";
import type { AnalysisDetail, AppConfig, LinesPage } from "@/lib/types";

export const detail = fixture.detail as unknown as AnalysisDetail;
export const lines = fixture.lines as unknown as LinesPage;
export const config = fixture.config as unknown as AppConfig;

export function renderWithProviders(ui: React.ReactElement, { route = "/", path = "*" }: { route?: string; path?: string } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[route]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path={path} element={ui} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

type Handler = (url: string, init?: RequestInit) => { status?: number; body: unknown } | undefined;

/** Stubs global fetch with a URL router. Unknown URLs return 404 with the error envelope. */
export function mockFetch(handler: Handler) {
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString();
    const res = handler(url, init) ?? { status: 404, body: { error: { code: "NOT_FOUND", message: "Not found" } } };
    return new Response(res.status === 204 ? null : JSON.stringify(res.body), {
      status: res.status ?? 200,
      headers: { "Content-Type": "application/json" },
    });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}
