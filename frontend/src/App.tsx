import { Link, Route, Routes } from "react-router-dom";

import { ProviderHealthPanel } from "./components/ResearchPanels";
import { ComparePage } from "./pages/ComparePage";
import { DashboardPage } from "./pages/DashboardPage";
import { EvaluationPage } from "./pages/EvaluationPage";
import { ResearchDetailPage } from "./pages/ResearchDetailPage";
import { ResearchListPage } from "./pages/ResearchListPage";
import { SettingsPage } from "./pages/SettingsPage";
import { useProviderHealthQuery } from "./hooks/queries";

function AppShell() {
  const providerQuery = useProviderHealthQuery();
  const providerHealth = providerQuery.data ?? null;
  const providerHealthError =
    providerQuery.error instanceof Error
      ? providerQuery.error.message
      : providerQuery.isError
        ? "读取 provider 状态失败"
        : null;

  return (
    <div className="min-h-screen">
      <nav className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-6xl items-center gap-6 px-6 py-4">
          <Link to="/" className="font-semibold text-ink">
            VCRA
          </Link>
          <Link to="/" className="text-sm text-slate-600 hover:text-accent">
            首页
          </Link>
          <Link to="/research" className="text-sm text-slate-600 hover:text-accent">
            任务列表
          </Link>
          <Link to="/compare" className="text-sm text-slate-600 hover:text-accent">
            对比
          </Link>
          <Link to="/evaluation" className="text-sm text-slate-600 hover:text-accent">
            评测
          </Link>
          <Link to="/settings" className="text-sm text-slate-600 hover:text-accent">
            设置
          </Link>
        </div>
      </nav>
      <main className="mx-auto max-w-6xl px-6 py-8">
        <ProviderHealthPanel health={providerHealth} error={providerHealthError} />
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/research" element={<ResearchListPage />} />
          <Route path="/research/:taskId" element={<ResearchDetailPage />} />
          <Route path="/compare" element={<ComparePage />} />
          <Route path="/evaluation" element={<EvaluationPage />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Routes>
      </main>
    </div>
  );
}

export default AppShell;
