import { expect, test } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));

// Captures README screenshots. Run: npx playwright test screenshots
const OUT = path.resolve(HERE, "../../docs/screenshots");
const DATASETS = path.resolve(HERE, "../../backend/eval/datasets");

test.use({ viewport: { width: 1440, height: 900 } });

test("capture README screenshots", async ({ page }) => {
  await page.goto("/upload");
  await expect(page.getByRole("button", { name: "Analyze sample" })).toBeVisible();
  await page.screenshot({ path: path.join(OUT, "upload.png") });

  await page.getByLabel("Log file", { exact: true }).setInputFiles(path.join(DATASETS, "pool_exhaustion_1000.log"));
  await expect(page.getByLabel("Five-line incident summary")).toBeVisible();
  await page.screenshot({ path: path.join(OUT, "incident-summary.png") });

  await page.getByRole("heading", { name: "Severity distribution" }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: path.join(OUT, "incident-charts.png") });

  await page.getByRole("link", { name: "Inspect line 120" }).click();
  await expect(page.getByTestId("log-row-120")).toBeVisible();
  await page.screenshot({ path: path.join(OUT, "log-explorer.png") });
});
