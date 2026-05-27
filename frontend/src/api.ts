import type {
  ChatRequest,
  ChatResponse,
  CreateTaskRequest,
  CreateTaskResponse,
  FactListResponse,
  ProviderHealth,
  Report,
  ResearchTask,
  RunTaskResponse,
  SourceListResponse,
  VerificationListResponse,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    ...init,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`API 请求失败 (${response.status}): ${text}`);
  }
  return (await response.json()) as T;
}

export function createResearchTask(payload: CreateTaskRequest): Promise<CreateTaskResponse> {
  return request<CreateTaskResponse>("/api/research/tasks", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function runResearchTask(taskId: string): Promise<RunTaskResponse> {
  return request<RunTaskResponse>(`/api/research/tasks/${taskId}/run`, {
    method: "POST",
  });
}

export function runResearchTaskAsync(taskId: string): Promise<{ task_id: string; status: string }> {
  return request<{ task_id: string; status: string }>(`/api/research/tasks/${taskId}/run/async`, {
    method: "POST",
  });
}

export function getResearchTask(taskId: string): Promise<ResearchTask> {
  return request<ResearchTask>(`/api/research/tasks/${taskId}`);
}

export function getResearchReport(taskId: string): Promise<Report> {
  return request<Report>(`/api/research/tasks/${taskId}/report`);
}

export function getFacts(taskId: string): Promise<FactListResponse> {
  return request<FactListResponse>(`/api/facts/${taskId}`);
}

export function getVerification(taskId: string): Promise<VerificationListResponse> {
  return request<VerificationListResponse>(`/api/verification/${taskId}`);
}

export function getSources(taskId: string): Promise<SourceListResponse> {
  return request<SourceListResponse>(`/api/sources/${taskId}`);
}

export function chatWithTask(payload: ChatRequest): Promise<ChatResponse> {
  return request<ChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getProviderHealth(): Promise<ProviderHealth> {
  return request<ProviderHealth>("/api/health/providers");
}

export interface ResearchTaskListItem {
  task_id: string;
  company_name: string;
  question: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export function listResearchTasks(limit = 50): Promise<{ items: ResearchTaskListItem[]; total: number }> {
  return request<{ items: ResearchTaskListItem[]; total: number }>(`/api/research/tasks?limit=${limit}`);
}

export function getFeatureFlags(): Promise<{ flags: Array<{ name: string; label: string; description: string; value: unknown; default: unknown; options: string[] | null }> }> {
  return request("/api/admin/flags");
}

export function updateFeatureFlag(name: string, value: unknown): Promise<{ ok: boolean; name: string; value: unknown }> {
  return request("/api/admin/flags", {
    method: "PATCH",
    body: JSON.stringify({ name, value }),
  });
}

export function resetFeatureFlags(): Promise<{ ok: boolean }> {
  return request("/api/admin/flags/reset", { method: "POST" });
}

export function compareCompanies(payload: {
  companies: Array<{ company_name: string; stock_code?: string }>;
  question: string;
}): Promise<{ question: string; tasks: RunTaskResponse[] }> {
  return request("/api/research/compare", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
