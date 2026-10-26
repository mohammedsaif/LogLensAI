import { Trash2, Upload } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { AiStatusBadge, ConfidenceBadge } from "@/components/badges";
import { EmptyState, ErrorState, PageSkeleton } from "@/components/StateViews";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useAnalyses, useDeleteAnalysis } from "@/hooks/queries";
import type { AnalysisListItem } from "@/lib/types";
import { formatDateTime, formatNumber } from "@/lib/utils";

const PAGE = 20;

function StatusBadge({ item }: { item: AnalysisListItem }) {
  const variant = item.status === "completed" ? "teal" : item.status === "failed" ? "danger" : "outline";
  return <Badge variant={variant}>{item.status}</Badge>;
}

export function HistoryPage() {
  const [offset, setOffset] = useState(0);
  const { data, isLoading, error, refetch } = useAnalyses(PAGE, offset);
  const remove = useDeleteAnalysis();

  if (isLoading) return <PageSkeleton />;
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold text-navy-900">Incident history</h1>
      {!data || data.total === 0 ? (
        <EmptyState
          title="No incidents analyzed yet"
          body="Analyses you run will appear here."
          action={
            <Button asChild>
              <Link to="/upload">
                <Upload aria-hidden /> Upload logs
              </Link>
            </Button>
          }
        />
      ) : (
        <Card className="overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <caption className="sr-only">Previous analyses</caption>
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th scope="col" className="px-4 py-2 font-medium">Incident</th>
                  <th scope="col" className="hidden px-4 py-2 font-medium md:table-cell">Created</th>
                  <th scope="col" className="px-4 py-2 font-medium">Status</th>
                  <th scope="col" className="hidden px-4 py-2 font-medium sm:table-cell">Lines</th>
                  <th scope="col" className="px-4 py-2 font-medium">Errors</th>
                  <th scope="col" className="hidden px-4 py-2 font-medium lg:table-cell">AI</th>
                  <th scope="col" className="px-4 py-2 font-medium"><span className="sr-only">Actions</span></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.items.map((item) => (
                  <tr key={item.id} className="hover:bg-slate-50">
                    <td className="max-w-xs px-4 py-2.5">
                      <Link
                        to={item.status === "completed" ? `/analyses/${item.id}` : `/analyses/${item.id}/progress`}
                        className="block truncate font-medium text-navy-900 hover:text-teal-700 hover:underline"
                      >
                        {item.incident_title ?? item.filename}
                      </Link>
                      <span className="block truncate text-xs text-slate-500">{item.filename}</span>
                    </td>
                    <td className="hidden whitespace-nowrap px-4 py-2.5 text-slate-600 md:table-cell">{formatDateTime(item.created_at)}</td>
                    <td className="px-4 py-2.5">
                      <StatusBadge item={item} />
                    </td>
                    <td className="hidden px-4 py-2.5 tabular-nums sm:table-cell">{formatNumber(item.total_lines)}</td>
                    <td className="px-4 py-2.5 tabular-nums">
                      {formatNumber(item.errors)}
                      {item.critical > 0 && <span className="ml-1 text-xs text-fuchsia-700">+{item.critical} crit</span>}
                    </td>
                    <td className="hidden px-4 py-2.5 lg:table-cell">
                      <div className="flex gap-1">
                        {item.ai_status && <AiStatusBadge status={item.ai_status} provider={item.ai_provider} />}
                        <ConfidenceBadge confidence={item.confidence} />
                      </div>
                    </td>
                    <td className="px-4 py-2.5 text-right">
                      <Button
                        variant="ghost"
                        size="icon"
                        aria-label={`Delete analysis ${item.filename}`}
                        disabled={remove.isPending}
                        onClick={() => {
                          if (window.confirm(`Delete the analysis of ${item.filename}? This removes its stored log lines.`)) remove.mutate(item.id);
                        }}
                      >
                        <Trash2 className="text-slate-500" aria-hidden />
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-between border-t border-slate-100 px-4 py-2 text-sm text-slate-600">
            <span>
              {offset + 1}–{Math.min(offset + PAGE, data.total)} of {data.total}
            </span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={offset === 0} onClick={() => setOffset(offset - PAGE)}>
                Previous
              </Button>
              <Button variant="outline" size="sm" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>
                Next
              </Button>
            </div>
          </div>
        </Card>
      )}
      {remove.error && <ErrorState error={remove.error} />}
    </div>
  );
}
