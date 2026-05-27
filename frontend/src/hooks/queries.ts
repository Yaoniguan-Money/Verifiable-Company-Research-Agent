import { useQuery } from "@tanstack/react-query";

import { getProviderHealth, getResearchTask, listResearchTasks } from "../api";
import { queryKeys } from "../lib/queryKeys";

export function useProviderHealthQuery() {
  return useQuery({
    queryKey: queryKeys.providerHealth,
    queryFn: getProviderHealth,
    staleTime: 30_000,
  });
}

export function useResearchTasksQuery(limit = 50) {
  return useQuery({
    queryKey: queryKeys.researchTasks(limit),
    queryFn: () => listResearchTasks(limit),
    staleTime: 10_000,
  });
}

export function useResearchTaskQuery(taskId: string, enabled = true) {
  return useQuery({
    queryKey: queryKeys.researchTask(taskId),
    queryFn: () => getResearchTask(taskId),
    enabled: enabled && Boolean(taskId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (status === "running" || status === "pending") {
        return 2000;
      }
      return false;
    },
  });
}
