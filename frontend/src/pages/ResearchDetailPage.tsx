import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  chatWithTask,
  getFacts,
  getResearchReport,
  getResearchTask,
  getSources,
  getVerification,
} from "../api";
import { AuditDrawer } from "../components/AuditDrawer";
import { FollowupChat } from "../components/FollowupChat";
import { ReportView } from "../components/ReportView";
import { useResearchStream } from "../hooks/useResearchStream";
import type {
  ChatResponse,
  Fact,
  Report,
  ResearchTask,
  Source,
  VerificationResult,
} from "../types";

export function ResearchDetailPage() {
  const { taskId = "" } = useParams();
  const [task, setTask] = useState<ResearchTask | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [facts, setFacts] = useState<Fact[]>([]);
  const [verifications, setVerifications] = useState<VerificationResult[]>([]);
  const [chatMessage, setChatMessage] = useState("");
  const [chatResult, setChatResult] = useState<ChatResponse | null>(null);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isCompleted = task?.status === "completed";
  const isFailed = task?.status === "failed";
  const isRunning = task && !isCompleted && !isFailed;

  const { events, streamText } = useResearchStream(taskId, Boolean(taskId) && Boolean(isRunning));

  useEffect(() => {
    if (!taskId) return;
    let cancelled = false;
    async function load() {
      try {
        const latestTask = await getResearchTask(taskId);
        if (cancelled) return;
        setTask(latestTask);
        if (latestTask.status === "completed") {
          const [rep, sourceList, factList, verificationList] = await Promise.all([
            getResearchReport(taskId),
            getSources(taskId),
            getFacts(taskId),
            getVerification(taskId),
          ]);
          if (!cancelled) {
            setReport(rep);
            setSources(sourceList.items);
            setFacts(factList.items);
            setVerifications(verificationList.items);
          }
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "加载失败");
        }
      }
    }
    load();
    const timer = window.setInterval(() => {
      if (!cancelled) load();
    }, 4000);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [taskId]);

  async function handleSendMessage() {
    if (!taskId || !chatMessage.trim()) return;
    setChatLoading(true);
    setChatError(null);
    try {
      const response = await chatWithTask({ task_id: taskId, message: chatMessage.trim() });
      setChatResult(response);
      setChatMessage("");
    } catch (err) {
      setChatError(err instanceof Error ? err.message : "追问失败");
    } finally {
      setChatLoading(false);
    }
  }

  const headerRight = useMemo(() => {
    if (!taskId || !isCompleted) return null;
    return (
      <a
        className="text-sm text-accent underline-offset-2 hover:underline"
        href={`/api/research/tasks/${taskId}/report/export?fmt=md`}
      >
        导出 Markdown
      </a>
    );
  }, [taskId, isCompleted]);

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div className="flex items-center justify-between">
        <Link to="/" className="text-sm text-accent underline-offset-2 hover:underline">
          ← 返回首页
        </Link>
        {headerRight}
      </div>

      {taskId ? (
        <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-white px-4 py-2 text-xs text-slate-500">
          <span className="break-all">task_id: {taskId}</span>
          <button
            type="button"
            className="ml-3 rounded-lg border border-slate-200 px-2 py-1 text-slate-600 hover:bg-slate-50"
            onClick={() => navigator.clipboard?.writeText(taskId)}
          >
            Copy
          </button>
        </div>
      ) : null}

      {error && !isCompleted ? (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          加载失败：{error}
        </div>
      ) : null}

      {isFailed ? (
        <div className="rounded-2xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          任务执行失败：{task?.error_message ?? "未提供原因"}
        </div>
      ) : null}

      {isRunning ? (
        <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <h2 className="text-base font-semibold text-ink">研究进行中…</h2>
          <p className="mt-1 text-sm text-slate-500">
            正在采集公开资料并整理结论，完成后这里会显示报告与可追溯来源。
          </p>
          <ul className="mt-3 max-h-32 space-y-1 overflow-auto text-xs text-slate-500">
            {events.slice(-8).map((e, idx) => (
              <li key={`${e.type}-${idx}`}>
                {e.type}
                {e.step ? ` · ${e.step}` : ""}
              </li>
            ))}
          </ul>
          {streamText ? (
            <pre className="mt-3 max-h-40 overflow-auto rounded-xl bg-slate-50 p-3 text-xs">
              {streamText}
            </pre>
          ) : null}
        </section>
      ) : null}

      {isCompleted ? (
        <>
          <ReportView task={task} report={report} />
          <FollowupChat
            taskId={taskId}
            question={task?.question ?? ""}
            disabled={!task?.task_id}
            loading={chatLoading}
            error={chatError}
            result={chatResult}
            message={chatMessage}
            onMessageChange={setChatMessage}
            onSend={handleSendMessage}
          />
          <AuditDrawer sources={sources} facts={facts} verifications={verifications} />
        </>
      ) : null}
    </div>
  );
}
