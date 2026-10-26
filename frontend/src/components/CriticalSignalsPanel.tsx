import { ShieldAlert, Siren } from "lucide-react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { SeverityBadge } from "@/components/badges";
import type { Signal } from "@/lib/types";
import { SIGNAL_LABELS, formatTime } from "@/lib/utils";

/** Deterministically preserved signals: shown above everything else so volume never hides them. */
export function CriticalSignalsPanel({ signals, analysisId, limit }: { signals: Signal[]; analysisId: string; limit?: number }) {
  const critical = signals.filter((s) => s.must_include);
  const shown = limit ? critical.slice(0, limit) : critical;
  return (
    <Card className="border-amber-300">
      <CardHeader className="bg-amber-50/70">
        <CardTitle className="flex items-center gap-2">
          <Siren className="size-4 text-amber-700" aria-hidden /> Critical signals
          <Badge variant="warn">{critical.length}</Badge>
        </CardTitle>
        <CardDescription>
          Selected by deterministic rules (critical severity, precursors, threshold breaches, rare high-severity events). These
          are always included in the analysis, whatever the AI returns.
        </CardDescription>
      </CardHeader>
      <CardContent className="p-0">
        {shown.length === 0 ? (
          <p className="px-5 py-4 text-sm text-slate-500">No critical signals were found in this file.</p>
        ) : (
          <ul className="divide-y divide-slate-100" aria-label="Critical signals">
            {shown.map((s) => (
              <li key={`${s.line_no}-${s.kind}`} className="flex flex-col gap-1.5 px-5 py-3 sm:flex-row sm:items-start sm:gap-4">
                <div className="flex shrink-0 items-center gap-2 sm:w-60">
                  <SeverityBadge severity={s.severity} />
                  <Link
                    to={`/analyses/${analysisId}/logs?line=${s.line_no}`}
                    className="font-mono text-sm font-semibold text-teal-700 hover:underline"
                    aria-label={`Inspect line ${s.line_no}`}
                  >
                    L{s.line_no}
                  </Link>
                  <span className="font-mono text-xs text-slate-500">{formatTime(s.ts)}</span>
                </div>
                <div className="min-w-0 flex-1">
                  <p className="break-words font-mono text-[13px] text-navy-900">
                    {s.kind === "prompt_injection" ? (
                      <span className="inline-flex items-center gap-1 text-fuchsia-800">
                        <ShieldAlert className="size-3.5" aria-hidden /> Suspected prompt-injection text (withheld from AI)
                      </span>
                    ) : (
                      s.message
                    )}
                  </p>
                  <p className="mt-0.5 text-xs text-slate-600">{s.reason}</p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {s.tags.map((t) => (
                      <Badge key={t} variant={t === s.kind ? "warn" : "outline"}>
                        {SIGNAL_LABELS[t] ?? t}
                      </Badge>
                    ))}
                    {s.service && <Badge variant="default">{s.service}</Badge>}
                    {s.count > 1 && <Badge variant="default">{s.count}×</Badge>}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
        {limit && critical.length > limit && (
          <p className="border-t border-slate-100 px-5 py-2 text-xs text-slate-500">+{critical.length - limit} more on the incident page</p>
        )}
      </CardContent>
    </Card>
  );
}
