import { Bot, Cpu, ShieldAlert } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import type { AIStatus, Confidence, Severity } from "@/lib/types";
import { cn } from "@/lib/utils";

// Chart/series colors (validated with the dataviz palette checker for the light surface).
export const SEVERITY_COLORS: Record<Severity, string> = {
  CRITICAL: "#a21caf",
  ERROR: "#dc2626",
  WARN: "#ca8a04",
  INFO: "#0d9488",
  DEBUG: "#94a3b8",
  UNKNOWN: "#64748b",
};

const SEVERITY_STYLES: Record<Severity, string> = {
  CRITICAL: "bg-fuchsia-100 text-fuchsia-900",
  ERROR: "bg-red-100 text-red-800",
  WARN: "bg-amber-100 text-amber-900",
  INFO: "bg-teal-50 text-teal-800",
  DEBUG: "bg-slate-100 text-slate-600",
  UNKNOWN: "bg-slate-100 text-slate-600",
};

export function SeverityBadge({ severity, className }: { severity: Severity; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex min-w-[4.5rem] justify-center rounded px-1.5 py-0.5 font-mono text-[11px] font-semibold",
        SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.UNKNOWN,
        className,
      )}
    >
      {severity}
    </span>
  );
}

export function ConfidenceBadge({ confidence }: { confidence: Confidence | null | undefined }) {
  if (!confidence) return null;
  const variant = confidence === "high" ? "teal" : confidence === "medium" ? "outline" : "warn";
  return (
    <Badge variant={variant} title="Qualitative confidence. Hypotheses are not confirmed causes.">
      {confidence} confidence
    </Badge>
  );
}

export function AiStatusBadge({ status, provider }: { status: AIStatus | null; provider: string | null }) {
  if (status === "fallback")
    return (
      <Badge variant="warn">
        <ShieldAlert className="size-3" aria-hidden /> Deterministic fallback
      </Badge>
    );
  if (status === "disabled")
    return (
      <Badge variant="outline">
        <Cpu className="size-3" aria-hidden /> AI disabled
      </Badge>
    );
  return (
    <Badge variant={provider === "anthropic" ? "navy" : "teal"}>
      <Bot className="size-3" aria-hidden /> {provider === "anthropic" ? "Claude" : "Mock AI"}
    </Badge>
  );
}
