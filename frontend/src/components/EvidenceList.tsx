import { ChevronDown, Star } from "lucide-react";
import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { SeverityBadge } from "@/components/badges";
import { useLines } from "@/hooks/queries";
import type { EvidenceItem } from "@/lib/types";
import { PATTERN_LABELS, cn, formatTime, lineLabel } from "@/lib/utils";

function RawLines({ analysisId, lines }: { analysisId: string; lines: number[] }) {
  const { data, isLoading, error } = useLines(analysisId, { line_numbers: lines, page_size: 50 });
  if (isLoading) return <Skeleton className="h-16 w-full" />;
  if (error) return <p className="text-sm text-red-700">Could not load the original lines.</p>;
  return (
    <ol className="overflow-x-auto rounded-md bg-navy-950 p-3 font-mono text-xs leading-5 text-slate-100" aria-label="Original log lines">
      {data?.items.map((l) => (
        <li key={l.line_no} className="flex gap-3 whitespace-pre">
          <Link
            to={`/analyses/${analysisId}/logs?line=${l.line_no}`}
            className="w-12 shrink-0 select-none text-right text-teal-300 hover:underline"
          >
            {l.line_no}
          </Link>
          <span>{l.raw}</span>
        </li>
      ))}
    </ol>
  );
}

function EvidenceRow({ item, analysisId, defaultOpen }: { item: EvidenceItem; analysisId: string; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  const panelId = useId();
  return (
    <li className={cn("rounded-md border", item.must_include ? "border-amber-300" : "border-slate-200")}>
      <button
        type="button"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-start gap-3 px-3 py-2.5 text-left hover:bg-slate-50"
      >
        <span className="mt-0.5 font-mono text-xs font-semibold text-slate-500">{item.id}</span>
        <SeverityBadge severity={item.severity} />
        <span className="min-w-0 flex-1">
          <span className="block truncate font-mono text-[13px] text-navy-900">{item.count > 1 ? item.template : item.text}</span>
          <span className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
            <span className="font-mono font-semibold text-teal-700">{lineLabel(item.first_line, item.last_line)}</span>
            <span>{formatTime(item.first_ts)}</span>
            {item.count > 1 && <Badge>{item.count}×</Badge>}
            {item.service && <Badge variant="outline">{item.service}</Badge>}
            {item.pattern_ids.map((p) => (
              <Badge key={p} variant="teal">
                {PATTERN_LABELS[p] ?? p}
              </Badge>
            ))}
            {item.must_include && (
              <Badge variant="warn">
                <Star className="size-3" aria-hidden /> critical signal
              </Badge>
            )}
          </span>
        </span>
        <ChevronDown className={cn("mt-1 size-4 shrink-0 text-slate-400 transition-transform", open && "rotate-180")} aria-hidden />
      </button>
      {open && (
        <div id={panelId} className="space-y-2 border-t border-slate-100 px-3 py-3">
          {item.reason && <p className="text-xs text-slate-600">Why selected: {item.reason}</p>}
          <RawLines analysisId={analysisId} lines={item.line_refs} />
          {item.count > item.line_refs.length && (
            <p className="text-xs text-slate-500">
              Showing {item.line_refs.length} of {item.count} occurrences.{" "}
              <Link className="text-teal-700 hover:underline" to={`/analyses/${analysisId}/logs?line=${item.first_line}`}>
                Open in explorer
              </Link>
            </p>
          )}
        </div>
      )}
    </li>
  );
}

/** Expandable evidence items, each revealing the original raw lines from the uploaded file. */
export function EvidenceList({ items, analysisId }: { items: EvidenceItem[]; analysisId: string }) {
  return (
    <ul className="space-y-2" aria-label="Evidence">
      {items.map((item, i) => (
        <EvidenceRow key={item.id} item={item} analysisId={analysisId} defaultOpen={i === 0} />
      ))}
    </ul>
  );
}
