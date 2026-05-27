import { RegressionEvalPanel } from "../components/RegressionEvalPanel";

export function EvaluationPage() {
  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">评测结果</h1>
        <p className="text-slate-600">公开公司回归集与工程验收指标。</p>
      </header>
      <RegressionEvalPanel />
    </div>
  );
}
