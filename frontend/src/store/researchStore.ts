import { create } from "zustand";

import type { ResearchTask } from "../types";

type ResearchStore = {
  recentTasks: ResearchTask[];
  setRecentTasks: (tasks: ResearchTask[]) => void;
};

export const useResearchStore = create<ResearchStore>((set) => ({
  recentTasks: [],
  setRecentTasks: (tasks) => set({ recentTasks: tasks }),
}));
