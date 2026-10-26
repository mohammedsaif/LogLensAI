import { useMutation } from "@tanstack/react-query";
import { Download, FlaskConical, Loader2 } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Dropzone } from "@/components/Dropzone";
import { ErrorState } from "@/components/StateViews";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useConfig } from "@/hooks/queries";
import { api } from "@/lib/api";
import type { SampleRequest } from "@/lib/types";

const SCENARIO_LABELS: Record<string, string> = {
  pool_exhaustion: "Connection pool exhaustion → DB timeouts",
  auth_attack: "Credential-stuffing attack",
  memory_leak: "Memory leak → OOM kill",
  healthy: "Healthy baseline (no incident)",
  prompt_injection: "Prompt-injection probe",
};

export function UploadPage() {
  const navigate = useNavigate();
  const config = useConfig();
  const [sample, setSample] = useState<SampleRequest>({ scenario: "pool_exhaustion", lines: 1000, format: "text" });

  const upload = useMutation({
    mutationFn: api.upload,
    onSuccess: (s) => navigate(`/analyses/${s.id}/progress`),
  });
  const analyzeSample = useMutation({
    mutationFn: api.analyzeSample,
    onSuccess: (s) => navigate(`/analyses/${s.id}/progress`),
  });
  const busy = upload.isPending || analyzeSample.isPending;
  const linesValid = sample.lines >= 50 && sample.lines <= 50000;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-navy-900">Upload logs</h1>
        <p className="mt-1 text-sm text-slate-500">
          LogLens parses, groups and scores every line deterministically, then sends only a small redacted evidence pack to the AI.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_22rem]">
        <Card>
          <CardHeader>
            <CardTitle>Log file</CardTitle>
            <CardDescription>Plain text (.log, .txt) or JSON lines (.jsonl), UTF-8.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {config.isLoading ? (
              <Skeleton className="h-48" />
            ) : (
              <Dropzone
                accept={config.data?.allowed_extensions ?? [".log", ".txt", ".jsonl"]}
                maxBytes={(config.data?.max_upload_mb ?? 10) * 1024 * 1024}
                disabled={busy}
                onFile={(f) => upload.mutate(f)}
              />
            )}
            {upload.isPending && (
              <p className="flex items-center gap-2 text-sm text-slate-600" role="status">
                <Loader2 className="size-4 animate-spin" aria-hidden /> Uploading…
              </p>
            )}
            {upload.error && <ErrorState error={upload.error} />}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <FlaskConical className="size-4 text-teal-600" aria-hidden /> Synthetic sample
            </CardTitle>
            <CardDescription>Generate fictional logs to try LogLens without real data.</CardDescription>
          </CardHeader>
          <CardContent>
            <form
              className="space-y-3"
              onSubmit={(e) => {
                e.preventDefault();
                if (linesValid) analyzeSample.mutate(sample);
              }}
            >
              <div className="space-y-1">
                <Label htmlFor="scenario">Scenario</Label>
                <Select id="scenario" value={sample.scenario} onChange={(e) => setSample({ ...sample, scenario: e.target.value })}>
                  {(config.data?.scenarios ?? [{ id: "pool_exhaustion", description: "" }]).map((s) => (
                    <option key={s.id} value={s.id}>
                      {SCENARIO_LABELS[s.id] ?? s.id}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label htmlFor="lines">Lines</Label>
                  <Input
                    id="lines"
                    type="number"
                    min={50}
                    max={50000}
                    value={sample.lines}
                    aria-invalid={!linesValid}
                    aria-describedby="lines-help"
                    onChange={(e) => setSample({ ...sample, lines: Number(e.target.value) })}
                  />
                </div>
                <div className="space-y-1">
                  <Label htmlFor="format">Format</Label>
                  <Select id="format" value={sample.format} onChange={(e) => setSample({ ...sample, format: e.target.value as "text" | "jsonl" })}>
                    <option value="text">Text</option>
                    <option value="jsonl">JSON lines</option>
                  </Select>
                </div>
              </div>
              <p id="lines-help" className={linesValid ? "text-xs text-slate-500" : "text-xs font-medium text-red-700"}>
                Between 50 and 50,000 lines.
              </p>
              <div className="flex flex-wrap gap-2">
                <Button type="submit" disabled={busy || !linesValid}>
                  {analyzeSample.isPending && <Loader2 className="animate-spin" aria-hidden />} Analyze sample
                </Button>
                <Button variant="outline" asChild>
                  <a href={api.sampleDownloadUrl(sample)} download>
                    <Download aria-hidden /> Download
                  </a>
                </Button>
              </div>
              {analyzeSample.error && <ErrorState error={analyzeSample.error} />}
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
