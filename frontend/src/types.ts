export type CheckStatus = 'pass' | 'warn' | 'fail' | 'skip';

export interface CheckResult {
  id: string;
  label: string;
  status: CheckStatus;
  score: number;
  weight: number;
  detail: string;
  evidence?: Record<string, unknown> | null;
}

export type CategoryId =
  | 'agent_access'
  | 'discoverability'
  | 'structured_data'
  | 'content_clarity'
  | 'citation_probe';

export interface CategoryResult {
  id: CategoryId;
  label: string;
  weight: number;
  score: number;
  checks: CheckResult[];
  summary: string;
}

export type Severity = 'critical' | 'important' | 'minor';
export type Effort = 'low' | 'medium' | 'high';

export interface Fix {
  severity: Severity;
  category: CategoryId;
  title: string;
  detail: string;
  score_lift: number;
  effort: Effort;
  snippet?: string | null;
  snippet_language?: string | null;
  docs_url?: string | null;
}

export interface Report {
  url: string;
  normalized_url: string;
  domain: string;
  scanned_at: string;
  duration_ms: number;
  score: number;
  grade: 'A' | 'B' | 'C' | 'D' | 'F';
  categories: CategoryResult[];
  fixes: Fix[];
  suggested_llms_txt: string;
  errors: string[];
}
