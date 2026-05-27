export interface Citation {
  chunk_id: string;
  source_id: string;
  url: string | null;
  title: string;
  retrieved_at: string;
}

export interface ResearchTask {
  task_id: string;
  company_name: string;
  question: string;
  status: string;
  error_message?: string | null;
  created_at: string;
  updated_at: string;
}

export interface Report {
  task_id: string;
  title: string | null;
  content: string;
  citations: Citation[];
  compliance_status: string;
}

export interface Source {
  id: string;
  task_id: string;
  title: string;
  url: string | null;
  source_type: string;
  published_at: string | null;
  retrieved_at: string;
  credibility_score: number | null;
}

export interface Fact {
  id: string;
  task_id: string;
  source_id: string;
  chunk_id: string;
  claim: string;
  metric_name: string | null;
  value: string | null;
  period: string | null;
  confidence: number;
  created_at: string;
}

export interface VerificationResult {
  id: string;
  fact_id: string;
  task_id: string;
  status: string;
  confidence: number;
  supporting_sources: string[];
  conflicting_sources: string[];
  reason: string;
  reason_code: string | null;
  created_at: string;
}

export interface ChatRequest {
  task_id: string;
  message: string;
}

export interface ChatResponse {
  task_id: string;
  message: string;
  answer: string;
  compliance_status: string;
  violations: string[];
}

export interface CreateTaskRequest {
  company_name: string;
  question: string;
  session_id?: string | null;
}

export interface CreateTaskResponse {
  task_id: string;
  status: string;
}

export interface RunTaskResponse {
  task_id: string;
  report_id: string | null;
  status: string;
  title: string | null;
  summary: string | null;
  error: string | null;
}

export interface SourceListResponse {
  task_id: string;
  items: Source[];
}

export interface FactListResponse {
  task_id: string;
  items: Fact[];
}

export interface VerificationListResponse {
  task_id: string;
  items: VerificationResult[];
}

export interface RegressionEvalCase {
  company_name: string;
  source_count: number;
  fact_count: number;
  metric_coverage_ratio: number;
  missing_metric_groups: string[];
  unexpected_metric_groups: string[];
  passed: boolean;
}

export interface RegressionEvalSummary {
  case_count: number;
  passed_count: number;
  average_metric_coverage_ratio: number;
  total_source_count: number;
  total_fact_count: number;
  cases: RegressionEvalCase[];
}

export interface FeatureFlag {
  name: string;
  label: string;
  description: string;
  value: unknown;
  default: unknown;
  options: string[] | null;
}

export interface FeatureFlagsResponse {
  flags: FeatureFlag[];
}

export interface ProviderHealth {
  llm_provider: string;
  search_provider: string;
  search_mode: string;
  search_network_enabled: boolean;
  embedding_provider: string;
  embedding_model: string;
  embedding_api_key_configured: boolean;
  embedding_base_url_configured: boolean;
  embedding_base_url_host: string | null;
  embedding_dimension_configured: boolean;
  embedding_max_batch_size: number;
  qianfan_api_key_configured: boolean;
  deepseek_api_key_configured: boolean;
  baidu_ai_search_api_key_configured: boolean;
  mock_enabled: boolean;
}
