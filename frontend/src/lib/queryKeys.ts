export const queryKeys = {
  providerHealth: ["providerHealth"] as const,
  researchTasks: (limit: number) => ["researchTasks", limit] as const,
  researchTask: (taskId: string) => ["researchTask", taskId] as const,
};
