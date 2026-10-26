import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { loadPrefs } from "@/lib/prefs";
import type { LinesQuery } from "@/lib/types";

export const keys = {
  config: ["config"] as const,
  list: (limit: number, offset: number) => ["analyses", limit, offset] as const,
  detail: (id: string) => ["analysis", id] as const,
  status: (id: string) => ["analysis-status", id] as const,
  lines: (id: string, q: LinesQuery) => ["lines", id, q] as const,
};

export function useConfig() {
  return useQuery({ queryKey: keys.config, queryFn: api.config, staleTime: 60_000 });
}

export function useAnalyses(limit = 20, offset = 0) {
  return useQuery({ queryKey: keys.list(limit, offset), queryFn: () => api.list(limit, offset) });
}

export function useAnalysis(id: string | undefined) {
  return useQuery({
    queryKey: keys.detail(id ?? ""),
    queryFn: () => api.get(id!),
    enabled: Boolean(id),
  });
}

export function useAnalysisStatus(id: string | undefined) {
  return useQuery({
    queryKey: keys.status(id ?? ""),
    queryFn: () => api.status(id!),
    enabled: Boolean(id),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "completed" || status === "failed" ? false : loadPrefs().pollIntervalMs;
    },
  });
}

export function useLines(id: string | undefined, q: LinesQuery) {
  return useQuery({
    queryKey: keys.lines(id ?? "", q),
    queryFn: () => api.lines(id!, q),
    enabled: Boolean(id),
    placeholderData: (prev) => prev,
  });
}

export function useDeleteAnalysis() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.remove(id),
    onSuccess: () => client.invalidateQueries({ queryKey: ["analyses"] }),
  });
}
