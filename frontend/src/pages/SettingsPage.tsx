import { useState } from "react";
import { ErrorState, PageSkeleton } from "@/components/StateViews";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/input";
import { useConfig } from "@/hooks/queries";
import { DEFAULT_PREFS, loadPrefs, savePrefs, type Prefs } from "@/lib/prefs";

export function SettingsPage() {
  const { data, isLoading, error, refetch } = useConfig();
  const [prefs, setPrefs] = useState<Prefs>(loadPrefs);
  const [saved, setSaved] = useState(false);

  if (isLoading) return <PageSkeleton />;
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;

  const rows: [string, string][] = data
    ? [
        ["AI mode", data.ai_mode_label],
        ["Model", data.ai_model],
        ["Evidence sent to", data.ai_external ? "External AI service (redacted)" : "Nowhere outside your network"],
        ["Prompt version", data.prompt_version],
        ["AI timeout / retries", `${data.ai_timeout_seconds}s / ${data.ai_max_retries}`],
        ["Evidence token budget", `${data.evidence_token_budget.toLocaleString()} tokens`],
        ["Max upload size", `${data.max_upload_mb} MB`],
        ["Max lines", data.max_lines.toLocaleString()],
        ["Allowed file types", data.allowed_extensions.join(", ")],
        ["Retention", data.retention_days > 0 ? `${data.retention_days} days` : "Disabled"],
        ["Redaction before AI", data.redaction_enabled ? `On${data.redact_ip_addresses ? " (incl. IP addresses)" : ""}` : "Off"],
        ["Version", `${data.version} (${data.environment})`],
      ]
    : [];

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-semibold text-navy-900">Settings</h1>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Server configuration</CardTitle>
            <CardDescription>Read-only. Set through environment variables (see .env.example).</CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="divide-y divide-slate-100 text-sm">
              {rows.map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4 py-2">
                  <dt className="text-slate-500">{k}</dt>
                  <dd className="text-right font-medium text-navy-900">{v}</dd>
                </div>
              ))}
            </dl>
            {(data?.ai_provider === "mock" || data?.ai_provider === "disabled") && (
              <Alert variant="info" className="mt-4">
                <span>
                  To use a real model, set <code className="font-mono">AI_PROVIDER</code> on the backend to{" "}
                  <code className="font-mono">anthropic</code>, <code className="font-mono">openai</code>,{" "}
                  <code className="font-mono">gemini</code> (each with its API key and model), or{" "}
                  <code className="font-mono">ollama</code> for a local model where logs never leave your machine. Mock mode
                  needs no key and sends nothing externally.
                </span>
              </Alert>
            )}
          </CardContent>
        </Card>

        <Card className="h-fit">
          <CardHeader>
            <CardTitle>Preferences</CardTitle>
            <CardDescription>Stored in this browser only.</CardDescription>
          </CardHeader>
          <CardContent>
            <form
              className="space-y-4"
              onSubmit={(e) => {
                e.preventDefault();
                savePrefs(prefs);
                setSaved(true);
              }}
            >
              <div className="space-y-1">
                <Label htmlFor="poll">Progress polling interval (ms)</Label>
                <Input
                  id="poll"
                  type="number"
                  min={250}
                  max={10000}
                  step={250}
                  value={prefs.pollIntervalMs}
                  onChange={(e) => {
                    setSaved(false);
                    setPrefs({ ...prefs, pollIntervalMs: Number(e.target.value) });
                  }}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="page-size">Raw log page size</Label>
                <Select
                  id="page-size"
                  value={prefs.explorerPageSize}
                  onChange={(e) => {
                    setSaved(false);
                    setPrefs({ ...prefs, explorerPageSize: Number(e.target.value) });
                  }}
                >
                  {[50, 100, 200, 500].map((n) => (
                    <option key={n} value={n}>
                      {n}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="flex gap-2">
                <Button type="submit">Save preferences</Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => {
                    setPrefs(DEFAULT_PREFS);
                    savePrefs(DEFAULT_PREFS);
                    setSaved(true);
                  }}
                >
                  Reset
                </Button>
              </div>
              {saved && (
                <p role="status" className="text-sm text-teal-700">
                  Preferences saved.
                </p>
              )}
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
