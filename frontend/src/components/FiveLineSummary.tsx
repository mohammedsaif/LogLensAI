import { Lightbulb } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { ConfidenceBadge } from "@/components/badges";
import { LineRefText } from "@/components/LineRefText";
import type { Confidence } from "@/lib/types";
import { cn } from "@/lib/utils";

const LABELS = ["Incident", "Impact", "Evidence", "Possible Cause", "Recommended Action"] as const;

export function splitSummaryLine(line: string): { label: string; qualifier: string | null; body: string } {
  const match = line.match(/^([A-Za-z ]+?)(?:\s*\(([^)]*)\))?:\s*(.*)$/s);
  if (!match) return { label: "", qualifier: null, body: line };
  return { label: match[1].trim(), qualifier: match[2] ?? null, body: match[3] };
}

/** The five-line incident summary. Possible Cause is always visually marked as a hypothesis. */
export function FiveLineSummary({ lines, analysisId }: { lines: string[]; analysisId: string }) {
  return (
    <dl className="divide-y divide-slate-100" aria-label="Five-line incident summary">
      {lines.map((line, i) => {
        const { label, qualifier, body } = splitSummaryLine(line);
        const isCause = label === "Possible Cause";
        const confidence = qualifier?.match(/(low|medium|high) confidence/)?.[1] as Confidence | undefined;
        return (
          <div key={i} className="grid gap-1 py-3 sm:grid-cols-[11rem_1fr] sm:gap-4">
            <dt className="flex flex-wrap items-center gap-1.5 text-sm font-semibold text-navy-900">
              {label || LABELS[i]}
              {isCause && (
                <Badge variant="dashed">
                  <Lightbulb className="size-3" aria-hidden /> Hypothesis
                </Badge>
              )}
            </dt>
            <dd
              className={cn(
                "text-sm leading-relaxed text-slate-700",
                isCause && "rounded-md border border-dashed border-slate-300 bg-slate-50/60 px-3 py-2",
              )}
              data-testid={`summary-line-${i}`}
            >
              {isCause && (
                <span className="mb-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
                  <ConfidenceBadge confidence={confidence} />
                  <span>Not confirmed: inferred from log evidence only.</span>
                </span>
              )}
              <LineRefText text={body} analysisId={analysisId} />
            </dd>
          </div>
        );
      })}
    </dl>
  );
}
