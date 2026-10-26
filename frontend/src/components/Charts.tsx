import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { SEVERITY_COLORS } from "@/components/badges";
import type { Severity, Stats } from "@/lib/types";
import { formatNumber, formatTime } from "@/lib/utils";

const ORDER: Severity[] = ["CRITICAL", "ERROR", "WARN", "INFO", "DEBUG", "UNKNOWN"];
const AXIS = { fontSize: 11, fill: "#64748b" };

/** Horizontal bars: magnitude per severity, with value labels (identity is never color-only). */
export function SeverityChart({ stats }: { stats: Stats }) {
  const data = ORDER.map((sev) => ({ severity: sev, count: stats.severity_counts[sev] ?? 0 })).filter(
    (d) => d.count > 0 || ["CRITICAL", "ERROR", "WARN"].includes(d.severity),
  );
  const summary = data.map((d) => `${d.severity} ${d.count}`).join(", ");
  return (
    <figure aria-label={`Severity distribution: ${summary}`} className="h-56 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 48, bottom: 4, left: 8 }} barCategoryGap={6}>
          <CartesianGrid horizontal={false} stroke="#e2e8f0" />
          <XAxis type="number" tick={AXIS} axisLine={false} tickLine={false} allowDecimals={false} />
          <YAxis type="category" dataKey="severity" tick={AXIS} axisLine={false} tickLine={false} width={72} />
          <Tooltip
            cursor={{ fill: "#f1f5f9" }}
            formatter={(value: number) => [formatNumber(value), "Events"]}
            contentStyle={{ fontSize: 12, borderRadius: 6, borderColor: "#e2e8f0" }}
          />
          <Bar dataKey="count" radius={[0, 4, 4, 0]} maxBarSize={22} isAnimationActive={false}>
            {data.map((d) => (
              <Cell key={d.severity} fill={SEVERITY_COLORS[d.severity]} />
            ))}
            <LabelList dataKey="count" position="right" style={{ fontSize: 11, fill: "#334155" }} formatter={formatNumber} />
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </figure>
  );
}

/** Stacked area per time bucket for the severities that matter during an incident. */
export function TimelineChart({ stats }: { stats: Stats }) {
  // Only draw severities that actually occur, so an empty series never outlines the stack.
  const series = (["WARN", "ERROR", "CRITICAL"] as Severity[]).filter((sev) => stats.timeline.some((b) => b[sev] > 0));
  const data = stats.timeline.map((b) => ({ ...b, label: formatTime(b.t).slice(0, 8) }));
  if (!data.length || !series.length) {
    return <p className="py-10 text-center text-sm text-slate-500">
        {data.length ? "No warnings or errors over time." : "No timestamps found, so no timeline is available."}
      </p>;
  }
  const peak = data.reduce((best, b) => (b.ERROR + b.CRITICAL > best.ERROR + best.CRITICAL ? b : best), data[0]);
  return (
    <figure
      aria-label={`Timeline of warnings and errors in ${stats.timeline_bucket_seconds}-second buckets. Peak errors at ${peak.label} UTC.`}
      className="h-56 w-full"
    >
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -12 }}>
          <CartesianGrid vertical={false} stroke="#e2e8f0" />
          <XAxis dataKey="label" tick={AXIS} axisLine={false} tickLine={false} minTickGap={32} />
          <YAxis tick={AXIS} axisLine={false} tickLine={false} allowDecimals={false} />
          <Tooltip
            labelFormatter={(l) => `${l} UTC (${stats.timeline_bucket_seconds}s bucket)`}
            contentStyle={{ fontSize: 12, borderRadius: 6, borderColor: "#e2e8f0" }}
            cursor={{ stroke: "#94a3b8", strokeDasharray: "3 3" }}
          />
          <Legend iconType="square" iconSize={10} wrapperStyle={{ fontSize: 12, color: "#334155" }} />
          {series.map((sev) => (
            <Area
              key={sev}
              type="monotone"
              dataKey={sev}
              stackId="1"
              stroke={SEVERITY_COLORS[sev]}
              strokeWidth={2}
              fill={SEVERITY_COLORS[sev]}
              fillOpacity={0.25}
              isAnimationActive={false}
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </figure>
  );
}
