import { useState } from "react";

import type { ChatResponse } from "../types";

interface FollowupChatProps {
  taskId: string;
  question: string;
  disabled?: boolean;
  loading: boolean;
  error: string | null;
  result: ChatResponse | null;
  message: string;
  onMessageChange: (value: string) => void;
  onSend: () => void;
}

// 围绕报告做追问：突出回答正文，工程字段折叠
export function FollowupChat({
  taskId,
  question,
  disabled,
  loading,
  error,
  result,
  message,
  onMessageChange,
  onSend,
}: FollowupChatProps) {
  const [history, setHistory] = useState<Array<{ q: string; a: string }>>([]);

  function handleSend() {
    if (!message.trim()) return;
    const q = message;
    onSend();
    setHistory((prev) => (result ? [...prev, { q, a: result.answer }] : prev));
  }

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <h2 className="text-base font-semibold text-ink">继续追问</h2>
      <p className="mt-1 text-sm text-slate-500">
        围绕「{question}」继续提问，回答基于上方报告与来源。
      </p>

      <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:items-stretch">
        <textarea
          className="min-h-12 flex-1 resize-y rounded-xl border border-slate-200 px-3 py-2 text-sm"
          value={message}
          onChange={(e) => onMessageChange(e.target.value)}
          placeholder="例如：再具体说明研发投入的同比变化"
          rows={2}
          disabled={disabled}
        />
        <button
          className="btn-primary self-end whitespace-nowrap"
          onClick={handleSend}
          disabled={loading || disabled || !taskId || !message.trim()}
        >
          {loading ? "请稍候..." : "发送"}
        </button>
      </div>
      {error ? <p className="mt-2 text-sm text-red-600">{error}</p> : null}

      <div className="mt-4 space-y-3">
        {history.length === 0 && !result ? (
          <p className="text-sm text-slate-400">尚未发起追问。</p>
        ) : null}
        {[
          ...history,
          ...(result && (history.length === 0 || history[history.length - 1].a !== result.answer)
            ? [{ q: result.message, a: result.answer }]
            : []),
        ].map((turn, idx) => (
          <div
            key={`${idx}-${turn.q.slice(0, 12)}`}
            className="rounded-xl border border-slate-100 bg-slate-50 p-3"
          >
            <div className="text-xs uppercase tracking-wider text-slate-400">你的问题</div>
            <div className="mt-1 text-sm text-slate-800">{turn.q}</div>
            <div className="mt-2 text-xs uppercase tracking-wider text-slate-400">回答</div>
            <div className="mt-1 whitespace-pre-wrap text-[15px] leading-7 text-ink">
              {turn.a}
            </div>
          </div>
        ))}
      </div>

      {result ? (
        <details className="mt-3 text-xs text-slate-400">
          <summary className="cursor-pointer select-none">查看合规检查结果</summary>
          <div className="mt-2">
            compliance_status: {result.compliance_status}
            <br />
            violations: {result.violations.length ? result.violations.join(", ") : "无违规命中"}
          </div>
        </details>
      ) : null}
    </section>
  );
}
