// Types mirroring the backend REST API (see docs/04-api.md).

export type Severity = "DEBUG" | "INFO" | "WARN" | "ERROR" | "CRITICAL" | "UNKNOWN";
export type AnalysisStatus = "queued" | "processing" | "completed" | "failed";
export type Confidence = "low" | "medium" | "high";
export type AIStatus = "ok" | "fallback" | "disabled";

export interface AnalysisStatusOut {
  id: string;
  filename: string;
  status: AnalysisStatus;
  stage: string;
  progress: number;
  error_code: string | null;
  error_message: string | null;
  created_at: string;
  completed_at: string | null;
}

export interface AnalysisListItem extends AnalysisStatusOut {
  source: string;
  size_bytes: number;
  total_lines: number;
  ai_status: AIStatus | null;
  ai_provider: string | null;
  confidence: Confidence | null;
  errors: number;
  warnings: number;
  critical: number;
  incident_title: string | null;
}

export interface AnalysisList {
  items: AnalysisListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface EvidenceItem {
  id: string;
  source: "signal" | "group";
  kind: string | null;
  severity: Severity;
  service: string | null;
  count: number;
  first_line: number;
  last_line: number;
  line_refs: number[];
  first_ts: string | null;
  last_ts: string | null;
  text: string;
  template: string;
  pattern_ids: string[];
  must_include: boolean;
  reason: string | null;
  risk_score: number;
}

export interface EvidencePack {
  items: EvidenceItem[];
  stats: Record<string, unknown>;
  omitted_group_count: number;
  token_estimate: number;
  redaction_counts: Record<string, number>;
}

export interface ObservedFact {
  statement: string;
  evidence_ids: string[];
}

export interface Hypothesis {
  statement: string;
  confidence: Confidence;
  rationale: string;
  evidence_ids: string[];
}

export interface Recommendation {
  action: string;
  priority: "immediate" | "short_term" | "long_term";
  evidence_ids: string[];
}

export interface IncidentAnalysis {
  incident_title: string;
  impact: string;
  observed_facts: ObservedFact[];
  hypotheses: Hypothesis[];
  recommendations: Recommendation[];
  critical_evidence_ids: string[];
  overall_confidence: Confidence;
  uncertainty_notes: string[];
  ai_status: AIStatus;
  failure_reason: string | null;
  provider: string;
  model: string;
  prompt_version: string;
  attempts: number;
  reattached_evidence_ids: string[];
  validation_warnings: string[];
}

export interface TimelineBucket {
  t: string;
  DEBUG: number;
  INFO: number;
  WARN: number;
  ERROR: number;
  CRITICAL: number;
  UNKNOWN: number;
  total: number;
}

export interface Stats {
  total_lines: number;
  event_count: number;
  parsed_lines: number;
  malformed_lines: number;
  continuation_lines: number;
  severity_counts: Record<Severity, number>;
  errors: number;
  warnings: number;
  critical: number;
  services: { name: string; count: number; errors: number }[];
  affected_services: string[];
  time_range: { start: string | null; end: string | null; duration_seconds: number | null };
  timeline: TimelineBucket[];
  timeline_bucket_seconds: number;
  pattern_counts: Record<string, number>;
  group_count: number;
  duplicate_group_count: number;
  duplicate_event_count: number;
}

export interface Signal {
  kind: string;
  tags: string[];
  pattern_ids: string[];
  severity: Severity;
  service: string | null;
  line_no: number;
  line_numbers: number[];
  ts: string | null;
  message: string;
  reason: string;
  must_include: boolean;
  count: number;
  risk_score: number;
}

export interface EventGroup {
  fingerprint: string;
  template: string;
  severity: Severity;
  service: string | null;
  count: number;
  first_line: number;
  last_line: number;
  first_ts: string | null;
  last_ts: string | null;
  sample_lines: number[];
  patterns: string[];
  risk_score: number;
  score_breakdown: Record<string, number> | null;
}

export interface AnalysisDetail extends AnalysisListItem {
  parsed_lines: number;
  malformed_lines: number;
  ai_model: string | null;
  prompt_version: string | null;
  summary_lines: string[] | null;
  analysis: IncidentAnalysis | null;
  evidence: EvidencePack | null;
  stats: Stats | null;
  redaction_counts: Record<string, number> | null;
  timings_ms: Record<string, number> | null;
  signals: Signal[];
  groups: EventGroup[];
  services: string[];
}

export interface LogLine {
  line_no: number;
  ts: string | null;
  severity: Severity;
  service: string | null;
  correlation_id: string | null;
  message: string;
  raw: string;
  parse_ok: boolean;
  is_continuation: boolean;
}

export interface LinesPage {
  items: LogLine[];
  total: number;
  page: number;
  page_size: number;
}

export interface AppConfig {
  app_name: string;
  version: string;
  environment: string;
  ai_provider: "mock" | "anthropic" | "disabled";
  ai_model: string;
  ai_mode_label: string;
  prompt_version: string;
  ai_timeout_seconds: number;
  ai_max_retries: number;
  evidence_token_budget: number;
  max_upload_mb: number;
  max_lines: number;
  allowed_extensions: string[];
  retention_days: number;
  redaction_enabled: boolean;
  redact_ip_addresses: boolean;
  scenarios: { id: string; description: string }[];
}

export interface LinesQuery {
  q?: string;
  severity?: Severity[];
  service?: string;
  malformed_only?: boolean;
  line_numbers?: number[];
  around_line?: number;
  page?: number;
  page_size?: number;
}

export interface SampleRequest {
  scenario: string;
  lines: number;
  format: "text" | "jsonl";
}
