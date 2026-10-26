import { CheckCircle2, Circle, Loader2, XCircle } from "lucide-react";
import { useEffect } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ErrorState } from "@/components/StateViews";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { useAnalysisStatus } from "@/hooks/queries";
import { cn } from "@/lib/utils";

export const STAGES = [
  { id: "validating", label: "Validating upload" },
  { id: "parsing", label: "Parsing & normalizing lines" },
  { id: "aggregating", label: "Grouping duplicate events" },
  { id: "detecting_signals", label: "Detecting critical signals" },
  { id: "selecting_evidence", label: "Redacting & selecting evidence" },
  { id: "saving_lines", label: "Saving raw lines" },
  { id: "ai_analysis", label: "AI analysis & validation" },
  { id: "completed", label: "Done" },
];

export function stageIndex(stage: string): number {
  const i = STAGES.findIndex((s) => s.id === stage);
  return i === -1 ? 0 : i;
}

export function ProgressPage() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { data, error, refetch } = useAnalysisStatus(id);

  useEffect(() => {
    if (data?.status === "completed") {
      const t = setTimeout(() => navigate(`/analyses/${id}`, { replace: true }), 400);
      return () => clearTimeout(t);
    }
  }, [data?.status, id, navigate]);

  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;
  const current = data ? stageIndex(data.stage) : 0;
  const failed = data?.status === "failed";

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-navy-900">Analyzing {data?.filename ?? "log file"}</h1>
        <p className="mt-1 text-sm text-slate-500">You'll be taken to the incident summary when analysis finishes.</p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>{failed ? "Analysis failed" : data?.status === "completed" ? "Analysis complete" : "Processing"}</CardTitle>
          <CardDescription aria-live="polite">
            {failed ? data?.error_message : `${STAGES[current]?.label ?? "Queued"} · ${data?.progress ?? 0}%`}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-5">
          <Progress value={data?.progress ?? 0} label="Analysis progress" className={cn(failed && "[&>div]:bg-red-500")} />
          <ol className="space-y-2.5">
            {STAGES.map((stage, i) => {
              const done = !failed && (i < current || data?.status === "completed");
              const active = !failed && i === current && data?.status !== "completed";
              return (
                <li key={stage.id} className="flex items-center gap-3 text-sm">
                  {done ? (
                    <CheckCircle2 className="size-4 text-teal-600" aria-label="done" />
                  ) : active ? (
                    <Loader2 className="size-4 animate-spin text-teal-600" aria-label="in progress" />
                  ) : failed && i === current ? (
                    <XCircle className="size-4 text-red-600" aria-label="failed" />
                  ) : (
                    <Circle className="size-4 text-slate-300" aria-label="pending" />
                  )}
                  <span className={cn(done || active ? "text-navy-900" : "text-slate-500", active && "font-medium")}>{stage.label}</span>
                </li>
              );
            })}
          </ol>
          {failed && (
            <div className="flex flex-wrap items-center gap-2 border-t border-slate-100 pt-4">
              <span className="font-mono text-xs text-red-700">{data?.error_code}</span>
              <Button asChild className="ml-auto">
                <Link to="/upload">Back to upload</Link>
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
