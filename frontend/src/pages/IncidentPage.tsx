import { FileJson, FileText, ListTree, ShieldCheck, TriangleAlert } from "lucide-react";
import { Link, Navigate, useParams } from "react-router-dom";
import { EventGroupsTable, FactsAndHypotheses, Recommendations } from "@/components/AnalysisSections";
import { AiStatusBadge, ConfidenceBadge } from "@/components/badges";
import { SeverityChart, TimelineChart } from "@/components/Charts";
import { CriticalSignalsPanel } from "@/components/CriticalSignalsPanel";
import { EvidenceList } from "@/components/EvidenceList";
import { FiveLineSummary } from "@/components/FiveLineSummary";
import { KpiCards } from "@/components/KpiCards";
import { ErrorState, PageSkeleton } from "@/components/StateViews";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAnalysis } from "@/hooks/queries";
import { api } from "@/lib/api";
import { formatDateTime, formatNumber } from "@/lib/utils";

export function IncidentPage() {
  const { id = "" } = useParams();
  const { data, isLoading, error, refetch } = useAnalysis(id);

  if (isLoading) return <PageSkeleton />;
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (!data) return null;
  if (data.status === "queued" || data.status === "processing") return <Navigate to={`/analyses/${id}/progress`} replace />;
  if (data.status === "failed")
    return <ErrorState error={new Error(data.error_message ?? "Analysis failed")} />;

  const analysis = data.analysis!;
  const stats = data.stats!;
  const evidence = data.evidence!;
  const redactions = Object.entries(data.redaction_counts ?? {});

  return (
    <div className="min-w-0 space-y-6">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0">
          <p className="text-sm text-slate-500">
            {data.filename} · {formatNumber(data.total_lines)} lines · {formatDateTime(data.created_at)}
          </p>
          <h1 className="mt-1 text-2xl font-semibold text-navy-900">{analysis.incident_title}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <AiStatusBadge status={data.ai_status} provider={data.ai_provider} />
            <ConfidenceBadge confidence={data.confidence} />
            <Badge variant="outline" title="Versioned prompt template">{data.prompt_version}</Badge>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap gap-2" aria-label="Export and navigation">
          <Button variant="outline" size="sm" asChild>
            <Link to={`/analyses/${id}/logs`}>
              <ListTree aria-hidden /> Raw logs
            </Link>
          </Button>
          <Button variant="outline" size="sm" asChild>
            <a href={api.exportUrl(id, "json")} download data-testid="export-json">
              <FileJson aria-hidden /> Export JSON
            </a>
          </Button>
          <Button variant="secondary" size="sm" asChild>
            <a href={api.exportUrl(id, "markdown")} download data-testid="export-markdown">
              <FileText aria-hidden /> Export Markdown
            </a>
          </Button>
        </div>
      </div>

      {data.ai_status === "fallback" && (
        <Alert variant="warn">
          <TriangleAlert aria-hidden />
          <span>
            <strong>AI analysis unavailable</strong> ({analysis.failure_reason}). Showing a deterministic, pattern-based summary.
            Facts and critical signals are unaffected.
          </span>
        </Alert>
      )}
      {data.ai_provider === "mock" && data.ai_status === "ok" && (
        <Alert variant="info">
          <ShieldCheck aria-hidden />
          <span>
            <strong>Mock AI mode.</strong> This summary was written by LogLens's offline rule-based model, not Claude. Set{" "}
            <code className="font-mono">AI_PROVIDER=anthropic</code> to enable Claude.
          </span>
        </Alert>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Incident summary</CardTitle>
          <CardDescription>Five lines, generated from validated structured data. Line references open the original log.</CardDescription>
        </CardHeader>
        <CardContent className="py-1">
          <FiveLineSummary lines={data.summary_lines ?? []} analysisId={id} />
        </CardContent>
      </Card>

      <CriticalSignalsPanel signals={data.signals} analysisId={id} />

      <KpiCards stats={stats} />

      <div className="grid gap-4 xl:grid-cols-2 [&>*]:min-w-0">
        <Card>
          <CardHeader>
            <CardTitle>Severity distribution</CardTitle>
          </CardHeader>
          <CardContent>
            <SeverityChart stats={stats} />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Event timeline</CardTitle>
            <CardDescription>Warnings, errors and critical events per {stats.timeline_bucket_seconds}s (UTC)</CardDescription>
          </CardHeader>
          <CardContent>
            <TimelineChart stats={stats} />
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Analysis</CardTitle>
          <CardDescription>Facts are what the logs show. Hypotheses are interpretations with qualitative confidence.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <FactsAndHypotheses analysis={analysis} evidence={evidence.items} analysisId={id} />
          <section aria-labelledby="recs-heading">
            <h3 id="recs-heading" className="mb-2 text-sm font-semibold text-navy-900">Recommended actions</h3>
            <Recommendations analysis={analysis} />
          </section>
          {analysis.uncertainty_notes.length > 0 && (
            <section aria-labelledby="unc-heading">
              <h3 id="unc-heading" className="mb-2 text-sm font-semibold text-navy-900">Uncertainty</h3>
              <ul className="list-disc space-y-1 pl-5 text-sm text-slate-600">
                {analysis.uncertainty_notes.map((n, i) => (
                  <li key={i}>{n}</li>
                ))}
              </ul>
            </section>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_20rem]">
        <Card className="min-w-0">
          <CardHeader>
            <CardTitle>Evidence ({evidence.items.length})</CardTitle>
            <CardDescription>
              Exactly what the AI saw (redacted). Expand an item to inspect the original lines.
              {evidence.omitted_group_count > 0 && ` ${evidence.omitted_group_count} lower-risk groups omitted by the token budget.`}
            </CardDescription>
          </CardHeader>
          <CardContent>
            <EvidenceList items={evidence.items} analysisId={id} />
          </CardContent>
        </Card>
        <Card className="h-fit">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldCheck className="size-4 text-teal-600" aria-hidden /> Privacy
            </CardTitle>
            <CardDescription>Redactions applied before any external AI call.</CardDescription>
          </CardHeader>
          <CardContent>
            {redactions.length === 0 ? (
              <p className="text-sm text-slate-500">No sensitive values detected in the evidence.</p>
            ) : (
              <ul className="space-y-1 text-sm" aria-label="Redaction counts">
                {redactions.map(([k, v]) => (
                  <li key={k} className="flex justify-between">
                    <span className="text-slate-600">{k.replace(/_/g, " ")}</span>
                    <span className="font-mono tabular-nums">{v}</span>
                  </li>
                ))}
              </ul>
            )}
            <p className="mt-3 text-xs text-slate-500">
              Evidence tokens ≈ {formatNumber(evidence.token_estimate)} · attempts {analysis.attempts} · model {analysis.model}
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Top event groups</CardTitle>
          <CardDescription>Duplicates collapsed by message template. Risk = severity + pattern + volume + rarity + precursor.</CardDescription>
        </CardHeader>
        <CardContent>
          <EventGroupsTable groups={data.groups.slice(0, 15)} analysisId={id} />
        </CardContent>
      </Card>
    </div>
  );
}
