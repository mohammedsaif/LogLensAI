import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));

const DATASETS = path.resolve(HERE, "../../backend/eval/datasets");

async function uploadFile(page: Page, filePath: string) {
  await page.goto("/upload");
  await page.getByLabel("Log file", { exact: true }).setInputFiles(filePath);
  await expect(page).toHaveURL(/\/analyses\/[0-9a-f]+(\/progress)?$/);
  await expect(page.getByLabel("Five-line incident summary")).toBeVisible();
}

test.describe("critical scenario: 95% pool warning at L120 + 143 DB timeouts", () => {
  test("upload → progress → summary preserves the L120 warning and aggregates 143 timeouts", async ({ page }) => {
    await uploadFile(page, path.join(DATASETS, "pool_exhaustion_1000.log"));

    const summary = page.getByLabel("Five-line incident summary");
    await expect(summary.getByTestId("summary-line-2")).toContainText("L120");
    await expect(summary.getByTestId("summary-line-2")).toContainText("Connection pool usage reached 95%");
    await expect(summary.getByTestId("summary-line-2")).toContainText("143×");
    await expect(summary.getByTestId("summary-line-3")).toContainText(/not confirmed/i);
    await expect(page.getByText("Hypothesis").first()).toBeVisible();

    const signals = page.getByRole("list", { name: "Critical signals" });
    await expect(signals).toContainText("L120");
    await expect(signals).toContainText("Precedes 143× ERROR");

    await expect(page.getByTestId("kpi-errors")).toHaveText("161");
    await expect(page.getByTestId("kpi-total-lines")).toHaveText("1,000");
    await expect(page.getByRole("heading", { name: "Severity distribution" })).toBeVisible();
    await expect(page.getByRole("heading", { name: "Event timeline" })).toBeVisible();
  });

  test("evidence expands to the original raw line, and line links open the explorer highlighted", async ({ page }) => {
    await uploadFile(page, path.join(DATASETS, "pool_exhaustion_1000.log"));
    const evidence = page.getByRole("list", { name: "Evidence" });
    await expect(evidence.getByLabel("Original log lines").first()).toContainText(
      "2026-03-14T09:02:29.232Z WARN  [order-service] Connection pool usage reached 95%",
    );

    await page.getByRole("link", { name: "Inspect line 120" }).click();
    await expect(page).toHaveURL(/\/logs\?line=120$/);
    const row = page.getByTestId("log-row-120");
    await expect(row).toBeVisible();
    await expect(row).toHaveClass(/bg-teal-100/);
    await expect(row).toContainText("Connection pool usage reached 95%");
  });

  test("exports JSON and Markdown", async ({ page }) => {
    await uploadFile(page, path.join(DATASETS, "pool_exhaustion_1000.log"));
    const jsonLink = page.getByTestId("export-json");
    const mdLink = page.getByTestId("export-markdown");

    let jsonText: string;
    let mdText: string;
    if (!process.env.PW_CHANNEL) {
      // Bundled Chromium (CI): exercise the real browser download.
      const [jsonDl] = await Promise.all([page.waitForEvent("download"), jsonLink.click()]);
      expect(jsonDl.suggestedFilename()).toBe("pool_exhaustion_1000-incident.json");
      jsonText = fs.readFileSync((await jsonDl.path())!, "utf-8");
      const [mdDl] = await Promise.all([page.waitForEvent("download"), mdLink.click()]);
      expect(mdDl.suggestedFilename()).toBe("pool_exhaustion_1000-incident.md");
      mdText = fs.readFileSync((await mdDl.path())!, "utf-8");
    } else {
      // Branded channels (msedge) close the browser after any headless download; fetch the link targets instead.
      const jsonRes = await page.request.get((await jsonLink.getAttribute("href"))!);
      expect(jsonRes.headers()["content-disposition"]).toContain("pool_exhaustion_1000-incident.json");
      jsonText = await jsonRes.text();
      const mdRes = await page.request.get((await mdLink.getAttribute("href"))!);
      expect(mdRes.headers()["content-disposition"]).toContain("pool_exhaustion_1000-incident.md");
      mdText = await mdRes.text();
    }
    const data = JSON.parse(jsonText);
    expect(data.summary_lines).toHaveLength(5);
    expect(data.critical_signals[0].line_no).toBe(120);
    expect(mdText).toContain("## Five-line summary");
    expect(mdText).toContain("| L120 |");
  });
});

test("JSON lines upload and raw log search / filters", async ({ page }) => {
  await uploadFile(page, path.join(DATASETS, "pool_exhaustion_1000.jsonl"));
  await page.getByRole("link", { name: "Raw logs" }).click();
  await page.getByLabel("Search").fill("pool usage");
  await expect(page.getByText("1 line(s)")).toBeVisible();
  await expect(page.getByTestId("log-row-120")).toBeVisible();

  await page.getByRole("button", { name: "Clear filters" }).first().click();
  await page.getByRole("button", { name: "ERROR", exact: true }).click();
  await expect(page.getByText("161 line(s)")).toBeVisible();
  await page.getByLabel("Service").selectOption("api-gateway");
  await expect(page.getByText("18 line(s)")).toBeVisible();
});

test("sample generator flow from the upload page", async ({ page }) => {
  await page.goto("/upload");
  await page.getByLabel("Scenario").selectOption("memory_leak");
  await page.getByLabel("Lines").fill("800");
  await page.getByRole("button", { name: "Analyze sample" }).click();
  await expect(page.getByLabel("Five-line incident summary")).toBeVisible();
  await expect(page.getByRole("heading", { level: 1 })).toContainText(/memory/i);
  await expect(page.getByRole("list", { name: "Critical signals" })).toContainText("OOMKilled");
});

test("invalid files are rejected with readable errors", async ({ page }) => {
  await page.goto("/upload");
  // client-side extension check
  await page.getByLabel("Log file", { exact: true }).setInputFiles({ name: "malware.exe", mimeType: "application/octet-stream", buffer: Buffer.from("MZ") });
  await expect(page.getByRole("alert")).toContainText("Unsupported file type");
  // server-side binary detection
  await page.getByLabel("Log file", { exact: true }).setInputFiles({ name: "binary.log", mimeType: "text/plain", buffer: Buffer.from([0, 1, 2, 3, 0]) });
  await expect(page.getByRole("alert").filter({ hasText: "BINARY_CONTENT" })).toBeVisible();
  // server-side encoding check
  await page.getByLabel("Log file", { exact: true }).setInputFiles({ name: "latin1.log", mimeType: "text/plain", buffer: Buffer.from([0x63, 0x61, 0x66, 0xe9]) });
  await expect(page.getByRole("alert").filter({ hasText: "INVALID_ENCODING" })).toBeVisible();
});

test("prompt-injection lines are flagged and withheld", async ({ page }) => {
  await uploadFile(page, path.join(DATASETS, "prompt_injection_1000.log"));
  const signals = page.getByRole("list", { name: "Critical signals" });
  await expect(signals.getByText(/Suspected prompt-injection text/).first()).toBeVisible();
  await expect(signals).not.toContainText("Ignore previous instructions");
  await expect(page.getByLabel("Five-line incident summary")).toContainText("L120");
});

test("history lists analyses and supports delete; settings show mock mode", async ({ page }) => {
  await uploadFile(page, path.join(DATASETS, "healthy_500.log"));
  await page.getByRole("link", { name: "Incident History" }).click();
  const row = page.getByRole("row").filter({ hasText: "healthy_500.log" }).first();
  await expect(row).toBeVisible();
  page.once("dialog", (d) => d.accept());
  await row.getByRole("button", { name: /Delete analysis/ }).click();
  await expect(page.getByRole("row").filter({ hasText: "healthy_500.log" })).toHaveCount(0);

  await page.getByRole("link", { name: "Settings" }).click();
  await expect(page.getByText("Mock AI (offline, deterministic)").first()).toBeVisible();
  await expect(page.getByTestId("ai-mode-chip")).toBeVisible();
});

test("mobile layout: navigation drawer and no horizontal scroll", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await uploadFile(page, path.join(DATASETS, "mixed_formats.log"));
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  await page.getByRole("button", { name: "Open navigation" }).click();
  const drawer = page.getByRole("dialog", { name: "Navigation" });
  await drawer.getByRole("link", { name: "Upload Logs" }).click();
  await expect(page).toHaveURL(/\/upload$/);
  await expect(drawer).toHaveCount(0);
});
