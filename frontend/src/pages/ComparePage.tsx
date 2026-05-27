import { useState } from "react";

import { compareCompanies } from "../api";
import { AshareScopeNotice } from "../components/AshareScopeNotice";
import { Button } from "../components/ui/Button";

export function ComparePage() {
  const [companyA, setCompanyA] = useState("");
  const [companyB, setCompanyB] = useState("");
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleCompare() {
    setLoading(true);
    setResult(null);
    try {
      const out = await compareCompanies({
        companies: [
          { company_name: companyA },
          { company_name: companyB },
        ],
        question,
      });
      setResult(
        out.tasks
          .map((t) => `${t.task_id} · ${t.status} · ${t.summary ?? t.error ?? "无摘要"}`)
          .join("\n")
      );
    } catch (err) {
      setResult(err instanceof Error ? err.message : "对比失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <h1 className="text-2xl font-semibold">双公司对比分析</h1>
      <AshareScopeNotice />
      <div className="card space-y-3">
        <input
          className="w-full rounded-xl border px-3 py-2"
          value={companyA}
          onChange={(e) => setCompanyA(e.target.value)}
          placeholder="公司 A（A 股上市）"
        />
        <input
          className="w-full rounded-xl border px-3 py-2"
          value={companyB}
          onChange={(e) => setCompanyB(e.target.value)}
          placeholder="公司 B（A 股上市）"
        />
        <textarea className="min-h-24 w-full rounded-xl border px-3 py-2" value={question} onChange={(e) => setQuestion(e.target.value)} />
        <Button disabled={loading} onClick={handleCompare}>
          {loading ? "对比运行中..." : "运行对比"}
        </Button>
      </div>
      {result ? <pre className="card whitespace-pre-wrap text-sm">{result}</pre> : null}
    </div>
  );
}
