import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api } from "@/lib/api";
import { DashboardPage } from "@/pages/DashboardPage";
import { HistoryPage } from "@/pages/HistoryPage";
import { IncidentPage } from "@/pages/IncidentPage";
import { LogExplorerPage } from "@/pages/LogExplorerPage";
import { ProgressPage, stageIndex } from "@/pages/ProgressPage";
import { SettingsPage } from "@/pages/SettingsPage";
import { UploadPage } from "@/pages/UploadPage";
import { config, detail, lines, mockFetch, renderWithProviders } from "@/test/utils";

afterEach(() => vi.unstubAllGlobals());

const listBody = { items: [detail], total: 1, limit: 20, offset: 0 };

describe("api client", () => {
  it("maps the backend error envelope to ApiError", async () => {
    mockFetch(() => ({ status: 413, body: { error: { code: "FILE_TOO_LARGE", message: "File exceeds the 10 MB limit." } } }));
    const err = await api.upload(new File(["x"], "a.log")).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 413, code: "FILE_TOO_LARGE", message: "File exceeds the 10 MB limit." });
  });

  it("reports network failures clearly", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(api.config()).rejects.toMatchObject({ code: "NETWORK_ERROR" });
  });

  it("serializes repeated severity filters and line lists", async () => {
    const fetchMock = mockFetch(() => ({ body: lines }));
    await api.lines("abc", { severity: ["ERROR", "WARN"], q: "pool", line_numbers: [1, 2], malformed_only: false });
    const url = fetchMock.mock.calls[0][0] as string;
    expect(url).toContain("severity=ERROR&severity=WARN");
    expect(url).toContain("q=pool");
    expect(url).toContain("line_numbers=1%2C2");
    expect(url).not.toContain("malformed_only");
  });
});

describe("IncidentPage", () => {
  it("renders summary, critical signals, KPIs and export links", async () => {
    mockFetch((url) => (url.endsWith(`/analyses/${detail.id}`) ? { body: detail } : url.includes("/lines") ? { body: lines } : undefined));
    renderWithProviders(<IncidentPage />, { route: `/analyses/${detail.id}`, path: "/analyses/:id" });
    expect(await screen.findByRole("heading", { level: 1 })).toHaveTextContent(detail.analysis!.incident_title);
    expect(screen.getByLabelText("Five-line incident summary")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Critical signals" })).toHaveTextContent("L120");
    expect(screen.getByText(/Mock AI mode/)).toBeInTheDocument();
    expect(screen.getByTestId("export-json")).toHaveAttribute("href", `/api/v1/analyses/${detail.id}/export?format=json`);
    expect(screen.getByTestId("export-markdown")).toHaveAttribute("href", `/api/v1/analyses/${detail.id}/export?format=markdown`);
  });

  it("shows the fallback banner when the AI failed", async () => {
    const fallback = {
      ...detail,
      ai_status: "fallback",
      analysis: { ...detail.analysis!, ai_status: "fallback", failure_reason: "AI request timed out" },
    };
    mockFetch((url) => (url.endsWith(`/analyses/${detail.id}`) ? { body: fallback } : undefined));
    renderWithProviders(<IncidentPage />, { route: `/analyses/${detail.id}`, path: "/analyses/:id" });
    expect(await screen.findByText(/AI analysis unavailable/)).toBeInTheDocument();
    expect(screen.getByText(/AI request timed out/)).toBeInTheDocument();
    expect(screen.getByText("Deterministic fallback")).toBeInTheDocument();
  });

  it("shows an error state for unknown analyses", async () => {
    mockFetch(() => undefined);
    renderWithProviders(<IncidentPage />, { route: "/analyses/nope", path: "/analyses/:id" });
    expect(await screen.findByRole("alert")).toHaveTextContent("NOT_FOUND");
  });
});

describe("ProgressPage", () => {
  it("maps stages and shows failure details", async () => {
    expect(stageIndex("ai_analysis")).toBe(6);
    expect(stageIndex("unknown")).toBe(0);
    mockFetch(() => ({
      body: { ...detail, status: "failed", stage: "failed", error_code: "PIPELINE_ERROR", error_message: "Processing failed (RuntimeError)." },
    }));
    renderWithProviders(<ProgressPage />, { route: "/analyses/x/progress", path: "/analyses/:id/progress" });
    expect(await screen.findByText("Analysis failed")).toBeInTheDocument();
    expect(screen.getByText("PIPELINE_ERROR")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to upload" })).toBeInTheDocument();
  });

  it("shows an accessible progress bar while processing", async () => {
    mockFetch(() => ({ body: { ...detail, status: "processing", stage: "aggregating", progress: 35 } }));
    renderWithProviders(<ProgressPage />, { route: "/analyses/x/progress", path: "/analyses/:id/progress" });
    const bar = await screen.findByRole("progressbar", { name: "Analysis progress" });
    await waitFor(() => expect(bar).toHaveAttribute("aria-valuenow", "35"));
  });
});

describe("DashboardPage", () => {
  it("shows the empty state with a sample call to action", async () => {
    mockFetch((url) => (url.includes("/analyses?") ? { body: { items: [], total: 0, limit: 20, offset: 0 } } : undefined));
    renderWithProviders(<DashboardPage />);
    expect(await screen.findByText("No analyses yet")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Try a sample incident/ })).toBeInTheDocument();
  });

  it("shows the latest completed analysis", async () => {
    mockFetch((url) => (url.includes("/analyses?") ? { body: listBody } : url.endsWith(`/analyses/${detail.id}`) ? { body: detail } : undefined));
    renderWithProviders(<DashboardPage />);
    expect(await screen.findByTestId("kpi-errors")).toHaveTextContent("161");
    expect(screen.getByRole("link", { name: /Open incident/ })).toHaveAttribute("href", `/analyses/${detail.id}`);
  });
});

describe("UploadPage", () => {
  it("submits a sample request with the chosen scenario", async () => {
    const fetchMock = mockFetch((url, init) => {
      if (url.endsWith("/config")) return { body: config };
      if (url.endsWith("/samples/analyze") && init?.method === "POST") return { status: 202, body: { ...detail, status: "queued" } };
      return undefined;
    });
    renderWithProviders(<UploadPage />);
    await screen.findByRole("option", { name: /Memory leak/ });
    await userEvent.selectOptions(screen.getByLabelText("Scenario"), "memory_leak");
    await userEvent.click(screen.getByRole("button", { name: /Analyze sample/ }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).endsWith("/samples/analyze"))).toBe(true));
    const call = fetchMock.mock.calls.find(([u]) => String(u).endsWith("/samples/analyze"))!;
    expect(JSON.parse(String(call[1]!.body))).toEqual({ scenario: "memory_leak", lines: 1000, format: "text" });
  });

  it("blocks out-of-range line counts", async () => {
    mockFetch((url) => (url.endsWith("/config") ? { body: config } : undefined));
    renderWithProviders(<UploadPage />);
    const input = await screen.findByLabelText("Lines");
    await userEvent.clear(input);
    await userEvent.type(input, "10");
    expect(screen.getByRole("button", { name: /Analyze sample/ })).toBeDisabled();
    expect(input).toHaveAttribute("aria-invalid", "true");
  });
});

describe("LogExplorerPage", () => {
  it("jumps to the requested line and highlights it", async () => {
    const fetchMock = mockFetch((url) => (url.includes("/lines") ? { body: lines } : url.endsWith("/analyses/x") ? { body: detail } : undefined));
    renderWithProviders(<LogExplorerPage />, { route: "/analyses/x/logs?line=120", path: "/analyses/:id/logs" });
    const row = await screen.findByTestId("log-row-120");
    expect(row.className).toContain("bg-teal-100");
    expect(String(fetchMock.mock.calls.find(([u]) => String(u).includes("/lines"))![0])).toContain("around_line=120");
  });

  it("filters by severity via toggle buttons", async () => {
    const fetchMock = mockFetch((url) => (url.includes("/lines") ? { body: lines } : url.endsWith("/analyses/x") ? { body: detail } : undefined));
    renderWithProviders(<LogExplorerPage />, { route: "/analyses/x/logs", path: "/analyses/:id/logs" });
    const toggle = await screen.findByRole("button", { name: "ERROR", pressed: false });
    await userEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-pressed", "true");
    await waitFor(() => expect(fetchMock.mock.calls.some(([u]) => String(u).includes("severity=ERROR"))).toBe(true));
  });
});

describe("HistoryPage and SettingsPage", () => {
  it("lists analyses and confirms before delete", async () => {
    const fetchMock = mockFetch((url, init) => {
      if (init?.method === "DELETE") return { status: 204, body: null };
      if (url.includes("/analyses?")) return { body: listBody };
      return undefined;
    });
    vi.stubGlobal("confirm", vi.fn(() => true));
    renderWithProviders(<HistoryPage />);
    expect(await screen.findByRole("link", { name: detail.analysis!.incident_title })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /Delete analysis/ }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, i]) => i?.method === "DELETE")).toBe(true));
  });

  it("shows server settings without secrets and saves preferences", async () => {
    mockFetch((url) => (url.endsWith("/config") ? { body: config } : undefined));
    renderWithProviders(<SettingsPage />);
    expect(await screen.findByText("Mock AI (offline, deterministic)")).toBeInTheDocument();
    expect(screen.getByText(/incident-analysis\/v1.0.0/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Save preferences" }));
    expect(screen.getByText("Preferences saved.")).toHaveAttribute("role", "status");
  });
});
