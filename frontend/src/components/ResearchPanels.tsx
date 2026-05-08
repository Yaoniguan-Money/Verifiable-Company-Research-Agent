import type { ChatResponse, Fact, Report, ResearchTask, Source, VerificationResult } from "../types";

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
    <section className="panel">
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

      <button className="run-button" onClick={onRun} disabled={running}>
        {running ? "运行中..." : "运行研究任务"}
      </button>
    </section>
  );
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
      <h2>任务状态</h2>
      {task ? (
        <dl className="status-list">
          <div>
            <dt>task_id</dt>
            <dd>{task.task_id}</dd>
          </div>
          <div>
            <dt>status</dt>
            <dd>{task.status}</dd>
          </div>
          <div>
            <dt>error</dt>
            <dd>{error ?? "-"}</dd>
          </div>
        </dl>
      ) : (
        <p>尚未运行任务。</p>
      )}
      {error ? <p className="error-text">错误：{error}</p> : null}
    </section>
  );
}

export function ReportPanel({ report }: { report: Report | null }) {
  return (
    <section className="panel">
      <h2>报告</h2>
      {report ? (
        <>
          <p>
            <strong>标题：</strong>
            {report.title ?? "-"}
          </p>
          <p>
            <strong>合规状态：</strong>
            {report.compliance_status}
          </p>
          <MarkdownBlock content={report.content} />
        </>
      ) : (
        <p>尚未加载报告。</p>
      )}
    </section>
  );
}

function MarkdownBlock({ content }: { content: string }) {
  const elements = content.split("\n").map((line, index) => {
    const key = `${index}-${line.slice(0, 16)}`;
    if (line.startsWith("# ")) {
      return <h3 key={key}>{line.slice(2)}</h3>;
    }
    if (line.startsWith("## ")) {
      return <h4 key={key}>{line.slice(3)}</h4>;
    }
    if (line.startsWith("- ")) {
      return <li key={key}>{line.slice(2)}</li>;
    }
    if (!line.trim()) {
      return <div key={key} className="markdown-gap" />;
    }
    return <p key={key}>{line}</p>;
  });

  return <div className="markdown-block">{elements}</div>;
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
      <h2>citations</h2>
      <p className="hint-text">优先展示 report.citations，同时补充 sources 列表用于核对来源元数据。</p>
      {report?.citations.length ? (
        <ul className="list-block">
          {report.citations.map((citation) => (
            <li key={`${citation.source_id}-${citation.chunk_id}`}>
              <div>source_id: {citation.source_id}</div>
              <div>chunk_id: {citation.chunk_id}</div>
              <div>title: {citation.title}</div>
              <div>url: {citation.url ?? "-"}</div>
              <div>retrieved_at: {citation.retrieved_at}</div>
            </li>
          ))}
        </ul>
      ) : (
        <p>当前无 citations。</p>
      )}

      <h3>sources</h3>
      {sources.length ? (
        <ul className="list-block">
          {sources.map((source) => (
            <li key={source.id}>
              <div>id: {source.id}</div>
              <div>title: {source.title}</div>
              <div>url: {source.url ?? "-"}</div>
              <div>source_type: {source.source_type}</div>
              <div>authority: {authorityLabel(source.credibility_score)}</div>
              <div>retrieved_at: {source.retrieved_at}</div>
            </li>
          ))}
        </ul>
      ) : (
        <p>当前无 sources。</p>
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
      <h2>verification / audit</h2>
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
          <ul className="list-block">
            {verifications.map((item) => (
              <li key={item.id}>
                <div>status: {item.status}</div>
                <div>reason_code: {item.reason_code ?? "-"}</div>
                <div>explanation: {explainReasonCode(item.reason_code)}</div>
                <div>reason: {item.reason}</div>
                <div>supporting_sources: {item.supporting_sources.join(", ") || "-"}</div>
                <div>conflicting_sources: {item.conflicting_sources.join(", ") || "-"}</div>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <p>当前无 verification 结果。</p>
      )}

      <h3>facts</h3>
      {facts.length ? (
        <ul className="list-block">
          {facts.map((fact) => (
            <li key={fact.id}>
              <div>claim: {fact.claim}</div>
              <div>metric_name: {fact.metric_name ?? "-"}</div>
              <div>value: {fact.value ?? "-"}</div>
              <div>period: {fact.period ?? "-"}</div>
              <div>confidence: {fact.confidence}</div>
              <div>source_id: {fact.source_id}</div>
              <div>chunk_id: {fact.chunk_id}</div>
            </li>
          ))}
        </ul>
      ) : (
        <p>当前无 facts。</p>
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
    outdated_period_or_source: "来源或期间过旧",
    invalid_numeric_value: "数值异常",
    low_credibility_source: "来源可信度过低",
    missing_source_id: "缺少来源标识",
    missing_required_fields: "缺少关键字段",
    unknown_reason: "未知原因",
  };
  return descriptions[code ?? "unknown_reason"] ?? code ?? "-";
}

function authorityLabel(credibilityScore: number | null) {
  if (credibilityScore === null) return "unknown";
  if (credibilityScore >= 0.85) return "high_authority";
  if (credibilityScore < 0.6) return "low_authority";
  return "medium_authority";
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
    <section className="panel">
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
      <button className="run-button" onClick={onSend} disabled={chatLoading || !task?.task_id}>
        {chatLoading ? "发送中..." : "发送追问"}
      </button>
      {!task?.task_id ? <p className="hint-text">请先运行任务后再发送追问。</p> : null}
      {chatError ? <p className="error-text">错误：{chatError}</p> : null}

      <h3>chat 回复</h3>
      {chatResult ? (
        <div className="chat-block">
          <p>
            <strong>answer：</strong>
            {chatResult.answer}
          </p>
          <p>
            <strong>compliance_status：</strong>
            {chatResult.compliance_status}
          </p>
          <p>
            <strong>violations：</strong>
            {chatResult.violations.length ? chatResult.violations.join(", ") : "无违规命中"}
          </p>
        </div>
      ) : (
        <p>尚未收到追问回复。</p>
      )}
    </section>
  );
}
