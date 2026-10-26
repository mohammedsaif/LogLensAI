import { AlertOctagon, AlertTriangle, FileText, XCircle } from "lucide-react";
import { Card } from "@/components/ui/card";
import type { Stats } from "@/lib/types";
import { formatDuration, formatNumber } from "@/lib/utils";

interface Kpi {
  label: string;
  value: number;
  hint: string;
  icon: React.ReactNode;
  accent: string;
}

export function KpiCards({ stats }: { stats: Stats }) {
  const kpis: Kpi[] = [
    {
      label: "Total lines",
      value: stats.total_lines,
      hint: `${formatNumber(stats.malformed_lines)} malformed · ${formatNumber(stats.duplicate_event_count)} duplicates`,
      icon: <FileText aria-hidden />,
      accent: "text-navy-700",
    },
    {
      label: "Errors",
      value: stats.errors,
      hint: `${stats.affected_services.length} service(s) with errors`,
      icon: <XCircle aria-hidden />,
      accent: "text-red-600",
    },
    {
      label: "Warnings",
      value: stats.warnings,
      hint: `${Object.keys(stats.pattern_counts).length} pattern type(s) detected`,
      icon: <AlertTriangle aria-hidden />,
      accent: "text-amber-600",
    },
    {
      label: "Critical",
      value: stats.critical,
      hint: `Window ${formatDuration(stats.time_range.duration_seconds)}`,
      icon: <AlertOctagon aria-hidden />,
      accent: "text-fuchsia-700",
    },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4" role="list" aria-label="Key metrics">
      {kpis.map((k) => (
        <Card key={k.label} className="p-4" role="listitem">
          <div className="flex items-center justify-between text-sm text-slate-500">
            <span>{k.label}</span>
            <span className={`[&_svg]:size-4 ${k.accent}`}>{k.icon}</span>
          </div>
          <div className="mt-1 text-2xl font-semibold tabular-nums text-navy-900" data-testid={`kpi-${k.label.toLowerCase().replace(" ", "-")}`}>
            {formatNumber(k.value)}
          </div>
          <div className="mt-1 truncate text-xs text-slate-500">{k.hint}</div>
        </Card>
      ))}
    </div>
  );
}
