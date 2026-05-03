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

export interface DetectedCategory {
  slug: string;
  label: string;
  persona: string;
  confidence: 'high' | 'medium' | 'low';
  signals: string[];
}

export interface PromptDeepLinks {
  chatgpt: string;
  perplexity: string;
  claude: string;
  google_ai: string;
}

export type PromptAngle = 'category' | 'use_case' | 'comparison' | 'long_tail';

export interface TestPrompt {
  angle: PromptAngle;
  label: string;
  text: string;
  rationale: string;
  deep_links: PromptDeepLinks;
}

export interface CategoryOption {
  slug: string;
  label: string;
}

export interface TestPromptsBundle {
  detected_category: DetectedCategory;
  brand: string;
  prompts: TestPrompt[];
  all_categories: CategoryOption[];
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
  test_prompts?: TestPromptsBundle | null;
  errors: string[];
}

// ---- Compare ----

export interface CategorySummary {
  id: CategoryId;
  label: string;
  score: number;
}

export interface CompareSummary {
  domain: string;
  url: string;
  score: number;
  // '?' is returned for rows where the scan failed entirely.
  grade: 'A' | 'B' | 'C' | 'D' | 'F' | '?';
  categories: CategorySummary[];
  duration_ms: number;
  error?: string | null;
  cached: boolean;
}

export interface CompareResponse {
  target: CompareSummary;
  competitors: CompareSummary[];
}
