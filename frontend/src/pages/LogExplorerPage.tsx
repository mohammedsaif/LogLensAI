import { ArrowLeft, ChevronLeft, ChevronRight, Search, X } from "lucide-react";
import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { SeverityBadge } from "@/components/badges";
import { EmptyState, ErrorState } from "@/components/StateViews";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input, Label, Select } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useAnalysis, useLines } from "@/hooks/queries";
import { loadPrefs } from "@/lib/prefs";
import type { Severity } from "@/lib/types";
import { cn, formatNumber, formatTime } from "@/lib/utils";

const SEVERITIES: Severity[] = ["CRITICAL", "ERROR", "WARN", "INFO", "DEBUG", "UNKNOWN"];

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

export function LogExplorerPage() {
  const { id = "" } = useParams();
  const [params, setParams] = useSearchParams();
  const highlight = params.get("line") ? Number(params.get("line")) : undefined;
  const pageSize = loadPrefs().explorerPageSize;

  const [text, setText] = useState(params.get("q") ?? "");
  const q = useDebounced(text, 300);
  const [severities, setSeverities] = useState<Severity[]>([]);
  const [service, setService] = useState("");
  const [malformedOnly, setMalformedOnly] = useState(false);
  const [page, setPage] = useState(1);
  const [jump, setJump] = useState<number | undefined>(highlight);
  const [expanded, setExpanded] = useState<number | null>(highlight ?? null);
  const highlightRef = useRef<HTMLTableRowElement>(null);

  const detail = useAnalysis(id);
  const query = useMemo(
    () => ({ q, severity: severities, service: service || undefined, malformed_only: malformedOnly, page, page_size: pageSize, around_line: jump }),
    [q, severities, service, malformedOnly, page, pageSize, jump],
  );
  const { data, isLoading, isFetching, error, refetch } = useLines(id, query);

  // After an around_line jump, adopt the page the server resolved and stop jumping.
  useEffect(() => {
    if (jump !== undefined && data && data.page !== page) setPage(data.page);
    if (jump !== undefined && data) setJump(undefined);
  }, [data, jump, page]);

  useEffect(() => {
    highlightRef.current?.scrollIntoView({ block: "center" });
  }, [data, highlight]);

  const resetPage = () => setPage(1);
  const clearFilters = () => {
    setText("");
    setSeverities([]);
    setService("");
    setMalformedOnly(false);
    setPage(1);
    setParams({});
  };
  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="ghost" size="sm" asChild>
          <Link to={`/analyses/${id}`}>
            <ArrowLeft aria-hidden /> Incident
          </Link>
        </Button>
        <h1 className="text-2xl font-semibold text-navy-900">Raw log explorer</h1>
        <span className="text-sm text-slate-500">{detail.data?.filename}</span>
      </div>

      <Card className="space-y-3 p-4">
        <div className="flex flex-col gap-3 md:flex-row md:items-end">
          <div className="flex-1 space-y-1">
            <Label htmlFor="log-search">Search</Label>
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-slate-400" aria-hidden />
              <Input
                id="log-search"
                placeholder="Text in message or raw line…"
                className="pl-8"
                value={text}
                onChange={(e) => {
                  setText(e.target.value);
                  resetPage();
                }}
              />
            </div>
          </div>
          <div className="space-y-1 md:w-56">
            <Label htmlFor="service-filter">Service</Label>
            <Select
              id="service-filter"
              value={service}
              onChange={(e) => {
                setService(e.target.value);
                resetPage();
              }}
            >
              <option value="">All services</option>
              {detail.data?.services.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </Select>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Severity filter">
          {SEVERITIES.map((sev) => {
            const on = severities.includes(sev);
            return (
              <button
                key={sev}
                type="button"
                aria-pressed={on}
                onClick={() => {
                  setSeverities(on ? severities.filter((s) => s !== sev) : [...severities, sev]);
                  resetPage();
                }}
                className={cn(
                  "rounded-md border px-2 py-1 font-mono text-xs font-semibold",
                  on ? "border-teal-600 bg-teal-600 text-white" : "border-slate-300 bg-white text-slate-700 hover:bg-slate-50",
                )}
              >
                {sev}
              </button>
            );
          })}
          <label className="ml-2 flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              className="size-4 accent-teal-600"
              checked={malformedOnly}
              onChange={(e) => {
                setMalformedOnly(e.target.checked);
                resetPage();
              }}
            />
            Malformed only
          </label>
          <Button variant="link" size="sm" className="ml-auto" onClick={clearFilters}>
            <X aria-hidden /> Clear filters
          </Button>
        </div>
      </Card>

      {error ? (
        <ErrorState error={error} onRetry={() => refetch()} />
      ) : isLoading ? (
        <Skeleton className="h-96" />
      ) : data && data.total === 0 ? (
        <EmptyState title="No lines match these filters" body="Try a different search term or clear the filters." action={<Button onClick={clearFilters}>Clear filters</Button>} />
      ) : (
        <Card className="overflow-hidden">
          <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2 text-sm text-slate-600">
            <span aria-live="polite">
              {formatNumber(data?.total)} line(s){isFetching ? " · loading…" : ""}
            </span>
            <span>
              Page {data?.page} of {totalPages}
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-[13px]">
              <caption className="sr-only">Log lines</caption>
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th scope="col" className="px-3 py-2 font-medium">Line</th>
                  <th scope="col" className="px-3 py-2 font-medium">Time (UTC)</th>
                  <th scope="col" className="px-3 py-2 font-medium">Severity</th>
                  <th scope="col" className="hidden px-3 py-2 font-medium md:table-cell">Service</th>
                  <th scope="col" className="px-3 py-2 font-medium">Message</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 font-mono">
                {data?.items.map((line) => {
                  const isHighlight = line.line_no === highlight;
                  const isOpen = expanded === line.line_no;
                  return (
                    <Fragment key={line.line_no}>
                      <tr
                        ref={isHighlight ? highlightRef : undefined}
                        className={cn("cursor-pointer hover:bg-slate-50", isHighlight && "bg-teal-100 ring-2 ring-inset ring-teal-500", !line.parse_ok && "text-slate-500")}
                        onClick={() => setExpanded(isOpen ? null : line.line_no)}
                        aria-expanded={isOpen}
                        data-testid={`log-row-${line.line_no}`}
                      >
                        <td className="whitespace-nowrap px-3 py-1.5 text-right text-slate-500">{line.line_no}</td>
                        <td className="whitespace-nowrap px-3 py-1.5 text-slate-600">{formatTime(line.ts)}</td>
                        <td className="px-3 py-1.5">
                          <SeverityBadge severity={line.severity} />
                        </td>
                        <td className="hidden whitespace-nowrap px-3 py-1.5 text-slate-600 md:table-cell">{line.service ?? "—"}</td>
                        <td className="max-w-xl truncate px-3 py-1.5 text-navy-900">
                          {line.is_continuation && <span className="mr-1 text-slate-400">↳</span>}
                          {line.message}
                          {!line.parse_ok && <span className="ml-2 font-sans text-xs text-amber-700">(unparsed)</span>}
                        </td>
                      </tr>
                      {isOpen && (
                        <tr className="bg-slate-50">
                          <td colSpan={5} className="px-3 py-2">
                            <pre className="whitespace-pre-wrap break-all rounded bg-navy-950 p-2 text-xs text-slate-100">{line.raw}</pre>
                            {line.correlation_id && <p className="mt-1 font-sans text-xs text-slate-600">Correlation ID: {line.correlation_id}</p>}
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
          <div className="flex items-center justify-end gap-2 border-t border-slate-100 px-4 py-2">
            <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} aria-label="Previous page">
              <ChevronLeft aria-hidden />
            </Button>
            <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} aria-label="Next page">
              <ChevronRight aria-hidden />
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}
