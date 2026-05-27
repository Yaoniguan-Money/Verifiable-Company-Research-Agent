import { useMemo } from "react";

import type { Fact, Source, VerificationResult } from "../types";

interface AuditDrawerProps {
  sources: Source[];
  facts: Fact[];
  verifications: VerificationResult[];
}

function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    verified: "已采信",
    conflicted: "口径冲突",
    insufficient: "线索待补证",
    outdated: "信息偏旧",
    rejected: "已排除",
  };
  return labels[status] ?? status;
}

function statusTone(status: string): string {
  switch (status) {
    case "verified":
      return "bg-emerald-50 text-emerald-700";
    case "conflicted":
      return "bg-amber-50 text-amber-700";
    case "insufficient":
      return "bg-slate-100 text-slate-600";
    case "outdated":
      return "bg-slate-100 text-slate-500";
    case "rejected":
      return "bg-rose-50 text-rose-700";
    default:
      return "bg-slate-100 text-slate-600";
  }
}

// 工程审计抽屉：默认收起，只在用户想查证时展开
export function AuditDrawer({ sources, facts, verifications }: AuditDrawerProps) {
  const verificationStats = useMemo(() => {
    const counts = new Map<string, number>();
    for (const item of verifications) {
      counts.set(item.status, (counts.get(item.status) ?? 0) + 1);
    }
    return [...counts.entries()];
  }, [verifications]);

  const factsByStatus = useMemo(() => {
    const statusByFact = new Map<string, string>();
    for (const v of verifications) statusByFact.set(v.fact_id, v.status);
    return facts.map((fact) => ({
      fact,
      status: statusByFact.get(fact.id) ?? "unknown",
    }));
  }, [facts, verifications]);

  if (!sources.length && !facts.length && !verifications.length) {
    return null;
  }

  return (
    <details className="rounded-2xl border border-slate-200 bg-white p-4 text-sm shadow-sm">
      <summary className="cursor-pointer select-none text-slate-600">
        审计明细（来源 / 事实 / 校验记录，仅供核对）
      </summary>

      <div className="mt-4 space-y-6">
        <div>
          <div className="mb-2 flex flex-wrap gap-2">
            {verificationStats.map(([status, count]) => (
              <span
                key={status}
                className={`rounded-full px-2 py-0.5 text-xs ${statusTone(status)}`}
              >
                {statusLabel(status)} {count}
              </span>
            ))}
          </div>
        </div>

        <section>
          <h3 className="mb-2 font-medium text-slate-700">已抽取事实</h3>
          {factsByStatus.length === 0 ? (
            <p className="text-slate-400">无</p>
          ) : (
            <ul className="space-y-2">
              {factsByStatus.slice(0, 50).map(({ fact, status }) => (
                <li
                  key={fact.id}
                  className="rounded-xl border border-slate-100 bg-slate-50 p-3"
                >
                  <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
                    <span className={`rounded-full px-2 py-0.5 ${statusTone(status)}`}>
                      {statusLabel(status)}
                    </span>
                    {fact.metric_name ? <span>{fact.metric_name}</span> : null}
                    {fact.period ? <span>· {fact.period}</span> : null}
                    {fact.value ? <span>· {fact.value}</span> : null}
                  </div>
                  <div className="mt-1 text-slate-800">{fact.claim}</div>
                </li>
              ))}
              {factsByStatus.length > 50 ? (
                <li className="text-xs text-slate-400">
                  共 {factsByStatus.length} 条，已截取前 50 条；其余可通过 API 拉取。
                </li>
              ) : null}
            </ul>
          )}
        </section>

        <section>
          <h3 className="mb-2 font-medium text-slate-700">来源列表</h3>
          {sources.length === 0 ? (
            <p className="text-slate-400">无</p>
          ) : (
            <ul className="space-y-1.5">
              {sources.map((s) => (
                <li key={s.id} className="text-slate-700">
                  <span>{s.title}</span>
                  {s.url ? (
                    <>
                      {" — "}
                      <a
                        href={s.url}
                        target="_blank"
                        rel="noreferrer"
                        className="break-all text-accent"
                      >
                        {s.url}
                      </a>
                    </>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </details>
  );
}
