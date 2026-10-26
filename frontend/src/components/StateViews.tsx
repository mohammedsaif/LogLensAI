import { AlertCircle, Inbox, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ApiError } from "@/lib/api";

export function EmptyState({ title, body, action }: { title: string; body: string; action?: React.ReactNode }) {
  return (
    <Card className="flex flex-col items-center gap-3 px-6 py-12 text-center">
      <Inbox className="size-8 text-slate-400" aria-hidden />
      <div>
        <h2 className="text-base font-semibold text-navy-900">{title}</h2>
        <p className="mt-1 max-w-md text-sm text-slate-500">{body}</p>
      </div>
      {action && <div className="flex flex-wrap justify-center gap-2">{action}</div>}
    </Card>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const code = error instanceof ApiError ? error.code : "ERROR";
  const message = error instanceof Error ? error.message : "Something went wrong.";
  return (
    <Card role="alert" className="flex items-start gap-3 border-red-300 bg-red-50 px-5 py-4">
      <AlertCircle className="mt-0.5 size-5 shrink-0 text-red-600" aria-hidden />
      <div className="flex-1">
        <p className="text-sm font-semibold text-red-900">{message}</p>
        <p className="mt-0.5 font-mono text-xs text-red-700">{code}</p>
      </div>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          <RefreshCw aria-hidden /> Retry
        </Button>
      )}
    </Card>
  );
}

export function PageSkeleton() {
  return (
    <div className="space-y-4" aria-busy="true" aria-label="Loading">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-24" />
        ))}
      </div>
      <Skeleton className="h-48" />
      <Skeleton className="h-64" />
    </div>
  );
}
