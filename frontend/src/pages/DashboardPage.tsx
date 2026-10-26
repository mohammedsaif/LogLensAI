import { ArrowRight, FlaskConical, Upload } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { AiStatusBadge, ConfidenceBadge } from "@/components/badges";
import { SeverityChart, TimelineChart } from "@/components/Charts";
import { CriticalSignalsPanel } from "@/components/CriticalSignalsPanel";
import { FiveLineSummary } from "@/components/FiveLineSummary";
import { KpiCards } from "@/components/KpiCards";
import { EmptyState, ErrorState, PageSkeleton } from "@/components/StateViews";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAnalyses, useAnalysis } from "@/hooks/queries";
import { api } from "@/lib/api";
import { formatDateTime } from "@/lib/utils";

export function DashboardPage() {
  const navigate = useNavigate();
  const list = useAnalyses(20, 0);
  const latestId = list.data?.items.find((a) => a.status === "completed")?.id;
  const latest = useAnalysis(latestId);
  const sample = useMutation({
    mutationFn: () => api.analyzeSample({ scenario: "pool_exhaustion", lines: 1000, format: "text" }),
    onSuccess: (s) => navigate(`/analyses/${s.id}/progress`),
  });

  if (list.isLoading || (latestId && latest.isLoading)) return <PageSkeleton />;
  if (list.error) return <ErrorState error={list.error} onRetry={() => list.refetch()} />;

  if (!latestId || !latest.data) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold text-navy-900">Dashboard</h1>
        <EmptyState
          title="No analyses yet"
          body="Upload a log file, or try a synthetic incident: 1,000 lines with a pool warning at line 120 followed by 143 database timeouts."
          action={
            <>
              <Button asChild>
                <Link to="/upload">
                  <Upload aria-hidden /> Upload logs
                </Link>
              </Button>
              <Button variant="outline" onClick={() => sample.mutate()} disabled={sample.isPending}>
                <FlaskConical aria-hidden /> Try a sample incident
              </Button>
            </>
          }
        />
        {sample.error && <ErrorState error={sample.error} />}
      </div>
    );
  }

  const d = latest.data;
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-navy-900">Dashboard</h1>
          <p className="mt-1 text-sm text-slate-500">
            Latest analysis: <span className="font-medium text-slate-700">{d.filename}</span> · {formatDateTime(d.created_at)}
          </p>
        </div>
        <Button asChild>
          <Link to={`/analyses/${d.id}`}>
            Open incident <ArrowRight aria-hidden />
          </Link>
        </Button>
      </div>

      {d.stats && <KpiCards stats={d.stats} />}

      <CriticalSignalsPanel signals={d.signals} analysisId={d.id} limit={3} />

      <Card>
        <CardHeader className="flex-row flex-wrap items-center justify-between gap-2">
          <div>
            <CardTitle>{d.analysis?.incident_title}</CardTitle>
            <CardDescription>Five-line summary</CardDescription>
          </div>
          <div className="flex gap-2">
            <AiStatusBadge status={d.ai_status} provider={d.ai_provider} />
            <ConfidenceBadge confidence={d.confidence} />
          </div>
        </CardHeader>
        <CardContent className="py-1">
          <FiveLineSummary lines={d.summary_lines ?? []} analysisId={d.id} />
        </CardContent>
      </Card>

      {d.stats && (
        <div className="grid gap-4 xl:grid-cols-2 [&>*]:min-w-0">
          <Card>
            <CardHeader>
              <CardTitle>Severity distribution</CardTitle>
            </CardHeader>
            <CardContent>
              <SeverityChart stats={d.stats} />
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Event timeline</CardTitle>
            </CardHeader>
            <CardContent>
              <TimelineChart stats={d.stats} />
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
