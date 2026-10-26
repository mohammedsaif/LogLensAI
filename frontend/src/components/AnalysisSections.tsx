import { CheckCircle2, Lightbulb } from "lucide-react";
import { Link } from "react-router-dom";
import { Badge } from "@/components/ui/badge";
import { ConfidenceBadge, SeverityBadge } from "@/components/badges";
import type { EventGroup, EvidenceItem, IncidentAnalysis } from "@/lib/types";
import { PATTERN_LABELS, formatNumber, lineLabel } from "@/lib/utils";

function EvidenceChips({ ids, byId, analysisId }: { ids: string[]; byId: Map<string, EvidenceItem>; analysisId: string }) {
  return (
    <span className="mt-1 flex flex-wrap gap-1">
      {ids.map((id) => {
        const item = byId.get(id);
        if (!item) return <Badge key={id}>{id}</Badge>;
        return (
          <Link
            key={id}
            to={`/analyses/${analysisId}/logs?line=${item.first_line}`}
            className="rounded border border-slate-200 bg-white px-1.5 py-0.5 font-mono text-[11px] text-slate-700 hover:border-teal-400"
          >
            {id} · {lineLabel(item.first_line, item.last_line)}
          </Link>
        );
      })}
    </span>
  );
}

/** Observed facts (solid) vs hypotheses (dashed): visually distinct by design. */
export function FactsAndHypotheses({
  analysis,
  evidence,
  analysisId,
}: {
  analysis: IncidentAnalysis;
  evidence: EvidenceItem[];
  analysisId: string;
}) {
  const byId = new Map(evidence.map((e) => [e.id, e]));
  return (
    <div className="grid gap-4 xl:grid-cols-2 [&>*]:min-w-0">
      <section aria-labelledby="facts-heading">
        <h3 id="facts-heading" className="mb-2 flex items-center gap-2 text-sm font-semibold text-navy-900">
          <CheckCircle2 className="size-4 text-teal-600" aria-hidden /> Observed facts
        </h3>
        <ul className="space-y-2">
          {analysis.observed_facts.map((f, i) => (
            <li key={i} className="rounded-md border border-slate-200 bg-white px-3 py-2 text-sm text-slate-700">
              {f.statement}
              <EvidenceChips ids={f.evidence_ids} byId={byId} analysisId={analysisId} />
            </li>
          ))}
        </ul>
      </section>
      <section aria-labelledby="hyp-heading">
        <h3 id="hyp-heading" className="mb-2 flex items-center gap-2 text-sm font-semibold text-navy-900">
          <Lightbulb className="size-4 text-amber-600" aria-hidden /> Hypotheses <span className="font-normal text-slate-500">(not confirmed)</span>
        </h3>
        {analysis.hypotheses.length === 0 ? (
          <p className="rounded-md border border-dashed border-slate-300 px-3 py-2 text-sm text-slate-500">
            Not enough evidence to propose a cause.
          </p>
        ) : (
          <ul className="space-y-2">
            {analysis.hypotheses.map((h, i) => (
              <li key={i} className="rounded-md border border-dashed border-slate-400 bg-slate-50/50 px-3 py-2 text-sm text-slate-700">
                <div className="mb-1 flex items-center gap-2">
                  <Badge variant="dashed">Hypothesis</Badge>
                  <ConfidenceBadge confidence={h.confidence} />
                </div>
                {h.statement}
                {h.rationale && <p className="mt-1 text-xs text-slate-500">Rationale: {h.rationale}</p>}
                <EvidenceChips ids={h.evidence_ids} byId={byId} analysisId={analysisId} />
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}

const PRIORITY_LABEL = { immediate: "Immediate", short_term: "Short term", long_term: "Long term" } as const;

export function Recommendations({ analysis }: { analysis: IncidentAnalysis }) {
  return (
    <ol className="space-y-2">
      {analysis.recommendations.map((r, i) => (
        <li key={i} className="flex gap-3 text-sm text-slate-700">
          <Badge variant={r.priority === "immediate" ? "danger" : r.priority === "short_term" ? "warn" : "default"} className="h-fit shrink-0">
            {PRIORITY_LABEL[r.priority]}
          </Badge>
          <span>{r.action}</span>
        </li>
      ))}
    </ol>
  );
}

export function EventGroupsTable({ groups, analysisId }: { groups: EventGroup[]; analysisId: string }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <caption className="sr-only">Top event groups by risk score</caption>
        <thead className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th scope="col" className="py-2 pr-3 font-medium">Severity</th>
            <th scope="col" className="py-2 pr-3 font-medium">Count</th>
            <th scope="col" className="py-2 pr-3 font-medium">Message template</th>
            <th scope="col" className="hidden py-2 pr-3 font-medium md:table-cell">Service</th>
            <th scope="col" className="py-2 pr-3 font-medium">Lines</th>
            <th scope="col" className="py-2 font-medium" title="Explainable risk score">Risk</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {groups.map((g) => (
            <tr key={g.fingerprint}>
              <td className="py-2 pr-3"><SeverityBadge severity={g.severity} /></td>
              <td className="py-2 pr-3 tabular-nums">{formatNumber(g.count)}</td>
              <td className="max-w-md py-2 pr-3">
                <span className="block truncate font-mono text-xs text-navy-900" title={g.template}>{g.template}</span>
                <span className="flex gap-1">
                  {g.patterns.map((p) => (
                    <Badge key={p} variant="teal" className="mt-0.5">{PATTERN_LABELS[p] ?? p}</Badge>
                  ))}
                </span>
              </td>
              <td className="hidden py-2 pr-3 text-slate-600 md:table-cell">{g.service ?? "—"}</td>
              <td className="py-2 pr-3">
                <Link to={`/analyses/${analysisId}/logs?line=${g.first_line}`} className="font-mono text-xs text-teal-700 hover:underline">
                  {lineLabel(g.first_line, g.last_line)}
                </Link>
              </td>
              <td className="py-2 tabular-nums" title={Object.entries(g.score_breakdown ?? {}).map(([k, v]) => `${k} ${v}`).join(", ")}>
                {g.risk_score}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
