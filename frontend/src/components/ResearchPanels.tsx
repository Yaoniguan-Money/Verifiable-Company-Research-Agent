import type { ReactNode } from "react";

import type {
  ChatResponse,
  Fact,
  ProviderHealth,
  Report,
  ResearchTask,
  Source,
  VerificationResult,
} from "../types";

interface ResearchFormProps {
  companyName: string;
  question: string;
  running: boolean;
  onCompanyNameChange: (value: string) => void;
  onQuestionChange: (value: string) => void;
  onRun: () => void;
}

export function ResearchForm({
  companyName,
  question,
  running,
  onCompanyNameChange,
  onQuestionChange,
  onRun,
}: ResearchFormProps) {
  return (
    <section className="panel panel-accent">
      <div className="section-eyebrow">Research task</div>
      <h2>发起企业研究</h2>
      <p className="section-desc">输入公司名称与研究问题，系统会采集公开资料、抽取事实并生成可追溯报告。</p>

      <div className="form-grid">
        <label className="field-label" htmlFor="company-name">
          企业名称
        </label>
        <input
          id="company-name"
          className="text-input"
          value={companyName}
          onChange={(event) => onCompanyNameChange(event.target.value)}
          placeholder="例如：某上市公司、某制造企业、某科技企业"
        />

        <label className="field-label" htmlFor="research-question">
          研究问题
        </label>
        <textarea
          id="research-question"
          className="text-area"
          value={question}
          onChange={(event) => onQuestionChange(event.target.value)}
          placeholder="例如：近三年研发投入变化和经营风险"
          rows={4}
        />
      </div>

      <button className="run-button" type="button" onClick={onRun} disabled={running}>
        {running ? "研究任务运行中..." : "运行研究任务"}
      </button>
    </section>
  );
}

export function ProviderHealthPanel({
  health,
  error,
}: {
  health: ProviderHealth | null;
  error: string | null;
}) {
  const mockEnabled = health?.mock_enabled ?? false;
  const searchMode = describeSearchMode(health);
  const hasMockNonSearch =
    health !== null && (health.llm_provider === "mock" || health.embedding_provider === "mock");
  const providerPanelClassName =
    health && !health.search_network_enabled
      ? "panel provider-panel provider-warning"
      : "panel provider-panel";
  const providerStatusClassName =
    health && health.search_network_enabled ? "status-pill status-verified" : "status-pill status-failed";
  const providerStatusText =
    health && health.search_network_enabled ? "搜索已联网" : "搜索未联网";

  return (
    <section className={providerPanelClassName}>
      <div className="panel-heading-row">
        <div>
          <div className="section-eyebrow">Provider status</div>
          <h2>当前运行链路</h2>
        </div>
        {health ? (
          <span className={providerStatusClassName}>
            {providerStatusText}
          </span>
        ) : null}
      </div>

      {health ? (
        <>
          <div className="provider-grid">
            <div>
              <span>LLM</span>
              <strong>{health.llm_provider}</strong>
            </div>
            <div>
              <span>Search</span>
              <strong>{health.search_provider}</strong>
            </div>
            <div>
              <span>Embedding</span>
              <strong>{health.embedding_provider}</strong>
            </div>
          </div>
          <p className={health.search_network_enabled ? "provider-note" : "provider-alert"}>
            {searchMode}
          </p>
          {health.search_provider === "mock" ? (
            <p className="provider-alert">
              当前 SearchProvider 是 mock，不会进行真实联网搜索。sources / citations 只能作为流程演示，不能当作真实公司资料。
            </p>
          ) : null}
          {health.search_provider === "local_documents" ? (
            <p className="provider-alert">
              当前 SearchProvider 是 local_documents，只会读取本地导入文件；如果没有导入真实资料，搜索结果会缺失或失真。
            </p>
          ) : null}
          {mockEnabled && hasMockNonSearch ? (
            <p className="provider-note">
              搜索链路与 LLM/Embedding 分开判断：当前至少一个非搜索 provider 仍使用 mock/local，因此报告生成可能是规则化文本，但搜索来源不会因此退回本地或 mock。
            </p>
          ) : null}
          {!health.baidu_ai_search_api_key_configured && health.search_provider === "baidu_ai_search" ? (
            <p className="provider-alert">Baidu AI Search 已选中但 API key 未配置，后端运行会失败。</p>
          ) : null}
        </>
      ) : (
        <p className="empty-state">{error ?? "正在读取 provider 状态..."}</p>
      )}
    </section>
  );
}

function describeSearchMode(health: ProviderHealth | null) {
  if (!health) return "";
  if (health.search_mode === "online_discovery") {
    return "搜索路径：联网公开来源。默认会访问公开公告来源；配置 Baidu AI Search key 后会叠加 AI Search。";
  }
  if (health.search_mode === "online_seeded") {
    return "搜索路径：联网抓取指定 URL。它会访问白名单 URL，但不会自行发现全网来源。";
  }
  if (health.search_mode === "local") {
    return "搜索路径：本地导入资料。不会联网发现新来源。";
  }
  return "搜索路径：mock 演示占位。不会联网。";
}

export function TaskStatusPanel({
  task,
  error,
}: {
  task: ResearchTask | null;
  error: string | null;
}) {
  return (
    <section className="panel">
      <div className="panel-heading-row">
        <div>
          <div className="section-eyebrow">Run status</div>
          <h2>任务状态</h2>
        </div>
        {task ? <span className={statusClassName(task.status)}>{statusLabel(task.status)}</span> : null}
      </div>

      {task ? (
        <dl className="status-list">
          <div>
            <dt>task_id</dt>
            <dd>{task.task_id}</dd>
          </div>
          <div>
            <dt>company</dt>
            <dd>{task.company_name}</dd>
          </div>
          <div>
            <dt>updated</dt>
            <dd>{formatDate(task.updated_at)}</dd>
          </div>
          <div>
            <dt>error</dt>
            <dd>{error ?? task.error_message ?? "-"}</dd>
          </div>
        </dl>
      ) : (
        <p className="empty-state">尚未运行任务。</p>
      )}

      {error ? <p className="error-text">错误：{error}</p> : null}
    </section>
  );
}

export function ReportPanel({ report }: { report: Report | null }) {
  return (
    <section className="panel report-panel">
      <div className="panel-heading-row">
        <div>
          <div className="section-eyebrow">Readable report</div>
          <h2>研究报告</h2>
        </div>
        {report ? (
          <div className="report-actions">
            <button className="print-button" type="button" onClick={() => window.print()}>
              打印 / 导出报告
            </button>
            <span className={complianceClassName(report.compliance_status)}>
              {report.compliance_status}
            </span>
          </div>
        ) : null}
      </div>

      {report ? (
        <>
          <div className="report-summary-card">
            <div>
              <span className="summary-kicker">报告标题</span>
              <h3>{report.title ?? "未命名报告"}</h3>
            </div>
            <div className="report-stat-grid">
              <div>
                <strong>{report.citations.length}</strong>
                <span>引用来源</span>
              </div>
              <div>
                <strong>{report.compliance_status}</strong>
                <span>合规状态</span>
              </div>
            </div>
          </div>
          <MarkdownBlock content={report.content} />
        </>
      ) : (
        <p className="empty-state">尚未加载报告。</p>
      )}
    </section>
  );
}

function MarkdownBlock({ content }: { content: string }) {
  const elements: ReactNode[] = [];
  let listItems: string[] = [];
  let listKind: "unordered" | "ordered" = "unordered";

  const flushList = () => {
    if (!listItems.length) return;
    const items = listItems;
    const currentListKind = listKind;
    listItems = [];
    const ListTag = currentListKind === "ordered" ? "ol" : "ul";
    elements.push(
      <ListTag
        className={`markdown-list ${currentListKind === "ordered" ? "ordered" : ""}`}
        key={`list-${elements.length}`}
      >
        {items.map((item, index) => (
          <li key={`${index}-${item.slice(0, 24)}`}>{renderInlineText(item, `li-${index}`)}</li>
        ))}
      </ListTag>,
    );
  };

  content.split("\n").forEach((line, index) => {
    const trimmed = line.trim();
    const key = `${index}-${trimmed.slice(0, 24)}`;

    if (!trimmed) {
      flushList();
      return;
    }
    if (trimmed.startsWith("- ")) {
      if (listItems.length && listKind !== "unordered") flushList();
      listKind = "unordered";
      listItems.push(trimmed.slice(2));
      return;
    }
    const orderedMatch = trimmed.match(/^\d+\.\s+(.+)$/);
    if (orderedMatch) {
      if (listItems.length && listKind !== "ordered") flushList();
      listKind = "ordered";
      listItems.push(orderedMatch[1]);
      return;
    }

    flushList();
    if (trimmed.startsWith("# ")) {
      elements.push(<h3 key={key}>{renderInlineText(trimmed.slice(2), key)}</h3>);
      return;
    }
    if (trimmed.startsWith("## ")) {
      elements.push(<h4 key={key}>{renderInlineText(trimmed.slice(3), key)}</h4>);
      return;
    }
    if (trimmed.startsWith("> ")) {
      elements.push(<blockquote key={key}>{renderInlineText(trimmed.slice(2), key)}</blockquote>);
      return;
    }
    elements.push(<p key={key}>{renderInlineText(trimmed, key)}</p>);
  });
  flushList();

  return <article className="markdown-block">{elements}</article>;
}

function renderInlineText(text: string, keyPrefix: string): ReactNode {
  const nodes: ReactNode[] = [];
  const pattern = /\*\*([^*]+)\*\*/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }
    nodes.push(<strong key={`${keyPrefix}-bold-${match.index}`}>{match[1]}</strong>);
    lastIndex = match.index + match[0].length;
  }
  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }
  return nodes.length ? nodes : text;
}

export function EvidencePanel({
  report,
  sources,
}: {
  report: Report | null;
  sources: Source[];
}) {
  return (
    <section className="panel">
      <div className="panel-heading-row">
        <div>
          <div className="section-eyebrow">Evidence</div>
          <h2>引用与来源</h2>
        </div>
        <span className="readonly-badge">只读证据</span>
      </div>
      <p className="hint-text">优先展示 report.citations，并补充 sources 方便核对来源元数据。</p>

      {report?.citations.length ? (
        <div className="card-grid">
          {report.citations.map((citation, index) => (
            <article className="evidence-card" key={`${citation.source_id}-${citation.chunk_id}`}>
              <div className="card-index">C{index + 1}</div>
              <h3>{citation.title}</h3>
              <dl>
                <div>
                  <dt>source_id</dt>
                  <dd>{citation.source_id}</dd>
                </div>
                <div>
                  <dt>chunk_id</dt>
                  <dd>{citation.chunk_id}</dd>
                </div>
                <div>
                  <dt>retrieved</dt>
                  <dd>{formatDate(citation.retrieved_at)}</dd>
                </div>
              </dl>
              {isHttpUrl(citation.url) ? (
                <a className="source-link" href={citation.url ?? undefined} target="_blank" rel="noreferrer">
                  打开来源
                </a>
              ) : (
                <span className="muted-text">{citation.url ? `非网页来源：${citation.url}` : "无 URL"}</span>
              )}
            </article>
          ))}
        </div>
      ) : (
        <p className="empty-state">当前无 citations。</p>
      )}

      <h3 className="subsection-title">Sources</h3>
      {sources.length ? (
        <div className="source-list">
          {sources.map((source) => (
            <article className="source-row" key={source.id}>
              <div>
                <h4>{source.title}</h4>
                <p>{source.url ?? "无 URL"}</p>
              </div>
              <div className="source-meta">
                <span className={authorityClassName(source.credibility_score, source.url)}>
                  {authorityLabel(source.credibility_score, source.url)}
                </span>
                <span>{source.source_type}</span>
                <span>{formatDate(source.retrieved_at)}</span>
              </div>
            </article>
          ))}
        </div>
      ) : (
        <p className="empty-state">当前无 sources。</p>
      )}
    </section>
  );
}

export function VerificationPanel({
  facts,
  verifications,
}: {
  facts: Fact[];
  verifications: VerificationResult[];
}) {
  const reasonSummary = buildVerificationReasonSummary(verifications);

  return (
    <section className="panel">
      <div className="section-eyebrow">Verification</div>
      <h2>校验与审计</h2>

      {verifications.length ? (
        <>
          <div className="audit-summary">
            {reasonSummary.map((item) => (
              <div key={item.code}>
                <strong>{item.label}</strong>
                <span>{item.count}</span>
              </div>
            ))}
          </div>
          <div className="verification-list">
            {verifications.map((item) => (
              <article className="verification-card" key={item.id}>
                <div className="verification-card-header">
                  <span className={statusClassName(item.status)}>{statusLabel(item.status)}</span>
                  <span>{scorePercent(item.confidence)}</span>
                </div>
                <p>{item.reason}</p>
                <dl>
                  <div>
                    <dt>reason</dt>
                    <dd>{explainReasonCode(item.reason_code)}</dd>
                  </div>
                  <div>
                    <dt>supporting</dt>
                    <dd>{item.supporting_sources.join(", ") || "-"}</dd>
                  </div>
                  <div>
                    <dt>conflicting</dt>
                    <dd>{item.conflicting_sources.join(", ") || "-"}</dd>
                  </div>
                </dl>
              </article>
            ))}
          </div>
        </>
      ) : (
        <p className="empty-state">当前无 verification 结果。</p>
      )}

      <h3 className="subsection-title">Facts</h3>
      {facts.length ? (
        <div className="fact-grid">
          {facts.map((fact) => (
            <article className="fact-card" key={fact.id}>
              <p>{fact.claim}</p>
              <dl>
                <div>
                  <dt>metric</dt>
                  <dd>{fact.metric_name ?? "-"}</dd>
                </div>
                <div>
                  <dt>value</dt>
                  <dd>{fact.value ?? "-"}</dd>
                </div>
                <div>
                  <dt>period</dt>
                  <dd>{fact.period ?? "-"}</dd>
                </div>
                <div>
                  <dt>confidence</dt>
                  <dd>{scorePercent(fact.confidence)}</dd>
                </div>
              </dl>
              <span className="muted-text">
                {fact.source_id} / {fact.chunk_id}
              </span>
            </article>
          ))}
        </div>
      ) : (
        <p className="empty-state">当前无 facts。</p>
      )}
    </section>
  );
}

function buildVerificationReasonSummary(verifications: VerificationResult[]) {
  const counts = new Map<string, number>();
  verifications.forEach((item) => {
    const code = item.reason_code ?? "unknown_reason";
    counts.set(code, (counts.get(code) ?? 0) + 1);
  });
  return [...counts.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([code, count]) => ({
      code,
      count,
      label: explainReasonCode(code),
    }));
}

function explainReasonCode(code: string | null) {
  const descriptions: Record<string, string> = {
    same_value_multi_source: "多来源同值",
    unit_normalized_match: "单位归一后同值",
    metric_alias_normalized_match: "指标别名归一后同值",
    metric_and_unit_normalized_match: "指标和单位归一后同值",
    different_value_multi_source: "多来源取值冲突",
    single_source_only: "单一来源，证据不足",
    outdated_period_or_source: "来源或期间过时",
    invalid_numeric_value: "数值异常",
    low_credibility_source: "来源可信度过低",
    missing_source_id: "缺少来源标识",
    missing_required_fields: "缺少关键字段",
    unknown_reason: "未知原因",
  };
  return descriptions[code ?? "unknown_reason"] ?? code ?? "-";
}

function authorityLabel(credibilityScore: number | null, url?: string | null) {
  if (isMockUrl(url)) return "MOCK 占位来源";
  if (credibilityScore === null) return "可信度未知";
  if (credibilityScore >= 0.85) return `高可信 ${scorePercent(credibilityScore)}`;
  if (credibilityScore < 0.6) return `低可信 ${scorePercent(credibilityScore)}`;
  return `中可信 ${scorePercent(credibilityScore)}`;
}

function authorityClassName(credibilityScore: number | null, url?: string | null) {
  if (isMockUrl(url)) return "authority-pill authority-low";
  if (credibilityScore === null) return "authority-pill authority-unknown";
  if (credibilityScore >= 0.85) return "authority-pill authority-high";
  if (credibilityScore < 0.6) return "authority-pill authority-low";
  return "authority-pill authority-medium";
}

function statusLabel(status: string) {
  const labels: Record<string, string> = {
    pending: "等待中",
    running: "运行中",
    completed: "已完成",
    failed: "失败",
    verified: "已验证",
    conflicted: "存在冲突",
    insufficient: "证据不足",
    outdated: "已过时",
    rejected: "已拒绝",
  };
  return labels[status] ?? status;
}

function statusClassName(status: string) {
  return `status-pill status-${status.toLowerCase().replace(/[^a-z0-9_-]/g, "-")}`;
}

function complianceClassName(status: string) {
  return `compliance-pill compliance-${status.toLowerCase().replace(/[^a-z0-9_-]/g, "-")}`;
}

function formatDate(value: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function scorePercent(value: number | null) {
  if (value === null) return "未知";
  return `${Math.round(value * 100)}%`;
}

function isHttpUrl(value: string | null) {
  return typeof value === "string" && /^https?:\/\//i.test(value);
}

function isMockUrl(value?: string | null) {
  return typeof value === "string" && value.startsWith("mock://");
}

interface ChatPanelProps {
  task: ResearchTask | null;
  chatMessage: string;
  chatLoading: boolean;
  chatError: string | null;
  chatResult: ChatResponse | null;
  onMessageChange: (value: string) => void;
  onSend: () => void;
}

export function ChatPanel({
  task,
  chatMessage,
  chatLoading,
  chatError,
  chatResult,
  onMessageChange,
  onSend,
}: ChatPanelProps) {
  return (
    <section className="panel chat-panel">
      <div className="section-eyebrow">Follow-up</div>
      <h2>报告追问</h2>
      <label className="field-label" htmlFor="follow-up-message">
        围绕当前报告追问
      </label>
      <textarea
        id="follow-up-message"
        className="text-area"
        value={chatMessage}
        onChange={(event) => onMessageChange(event.target.value)}
        placeholder="例如：请说明报告中的主要经营风险和证据来源"
        rows={3}
      />
      <button className="run-button secondary-button" type="button" onClick={onSend} disabled={chatLoading || !task?.task_id}>
        {chatLoading ? "发送中..." : "发送追问"}
      </button>
      {!task?.task_id ? <p className="hint-text">请先运行任务后再发送追问。</p> : null}
      {chatError ? <p className="error-text">错误：{chatError}</p> : null}

      <h3 className="subsection-title">Chat 回复</h3>
      {chatResult ? (
        <div className="chat-block">
          <p>{chatResult.answer}</p>
          <div className="chat-meta">
            <span>compliance_status: {chatResult.compliance_status}</span>
            <span>
              violations: {chatResult.violations.length ? chatResult.violations.join(", ") : "无违规命中"}
            </span>
          </div>
        </div>
      ) : (
        <p className="empty-state">尚未收到追问回复。</p>
      )}
    </section>
  );
}
