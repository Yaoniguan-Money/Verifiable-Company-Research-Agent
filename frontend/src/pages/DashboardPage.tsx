import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { createResearchTask, runResearchTaskAsync } from "../api";
import { AshareScopeNotice } from "../components/AshareScopeNotice";

export function DashboardPage() {
  const navigate = useNavigate();
  const [companyName, setCompanyName] = useState("");
  const [question, setQuestion] = useState("");
  const [lastTaskId, setLastTaskId] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit() {
    if (!companyName.trim() || !question.trim()) {
      setError("请填写企业名称和研究问题。");
      return;
    }
    setRunning(true);
    setError(null);
    try {
      const created = await createResearchTask({
        company_name: companyName.trim(),
        question: question.trim(),
      });
      setLastTaskId(created.task_id);
      await runResearchTaskAsync(created.task_id);
      navigate(`/research/${created.task_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "创建任务失败");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <header className="space-y-2">
        <p className="text-sm uppercase tracking-[0.2em] text-slate-500">Dashboard</p>
        <h1 className="text-3xl font-semibold">新建企业研究</h1>
        <p className="text-slate-600">基于公开披露资料生成可溯源研究报告。</p>
      </header>
      <AshareScopeNotice />
      <section className="card space-y-4">
        <label className="block space-y-1">
          <span className="text-sm text-slate-600">企业名称（A 股）</span>
          <input
            className="w-full rounded-xl border border-slate-200 px-3 py-2"
            value={companyName}
            onChange={(e) => setCompanyName(e.target.value)}
            placeholder="输入 A 股上市公司全称或常用简称"
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm text-slate-600">研究问题</span>
          <textarea
            className="min-h-28 w-full rounded-xl border border-slate-200 px-3 py-2"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
          />
        </label>
        {error ? <p className="text-sm text-red-600">{error}</p> : null}
        {lastTaskId ? (
          <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500">
            <span className="break-all">task_id: {lastTaskId}</span>
            <button
              type="button"
              className="ml-3 rounded-lg border border-slate-200 bg-white px-2 py-1 text-slate-600 hover:bg-slate-50"
              onClick={() => navigator.clipboard?.writeText(lastTaskId)}
            >
              Copy
            </button>
          </div>
        ) : null}
        <button className="btn-primary" disabled={running} onClick={handleSubmit}>
          {running ? "启动中..." : "异步运行研究"}
        </button>
      </section>
      <p className="text-sm text-slate-500">
        也可前往 <Link className="text-accent underline" to="/evaluation">评测面板</Link>
      </p>
    </div>
  );
}
