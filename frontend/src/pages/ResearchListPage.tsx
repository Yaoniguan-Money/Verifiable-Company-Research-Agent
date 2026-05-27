import { useEffect } from "react";
import { Link } from "react-router-dom";

import { useResearchTasksQuery } from "../hooks/queries";
import { useResearchStore } from "../store/researchStore";

export function ResearchListPage() {
  const { recentTasks, setRecentTasks } = useResearchStore();
  const tasksQuery = useResearchTasksQuery();

  useEffect(() => {
    if (tasksQuery.data?.items) {
      setRecentTasks(tasksQuery.data.items);
    } else if (tasksQuery.isError) {
      setRecentTasks([]);
    }
  }, [tasksQuery.data, tasksQuery.isError, setRecentTasks]);

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">研究任务</h1>
          <p className="text-slate-600">最近创建的研究任务与状态。</p>
        </div>
        <Link className="btn-primary" to="/">
          新建研究
        </Link>
      </header>
      <div className="card overflow-hidden p-0">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              <th className="px-4 py-3">企业</th>
              <th className="px-4 py-3">问题</th>
              <th className="px-4 py-3">状态</th>
              <th className="px-4 py-3">操作</th>
            </tr>
          </thead>
          <tbody>
            {recentTasks.map((task) => (
              <tr key={task.task_id} className="border-t border-slate-100">
                <td className="px-4 py-3">{task.company_name}</td>
                <td className="max-w-md truncate px-4 py-3">{task.question}</td>
                <td className="px-4 py-3">{task.status}</td>
                <td className="px-4 py-3">
                  <Link className="text-accent underline" to={`/research/${task.task_id}`}>
                    查看
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {recentTasks.length === 0 ? (
          <p className="px-4 py-6 text-sm text-slate-500">暂无任务，请从首页创建。</p>
        ) : null}
      </div>
    </div>
  );
}
