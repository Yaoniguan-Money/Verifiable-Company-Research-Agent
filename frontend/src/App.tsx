import { useState } from "react";

import {
  chatWithTask,
  createResearchTask,
  getFacts,
  getResearchReport,
  getResearchTask,
  getSources,
  getVerification,
  runResearchTask,
} from "./api";
import {
  ChatPanel,
  EvidencePanel,
  ReportPanel,
  ResearchForm,
  TaskStatusPanel,
  VerificationPanel,
} from "./components/ResearchPanels";
import { RegressionEvalPanel } from "./components/RegressionEvalPanel";
import type { ChatResponse, Fact, Report, ResearchTask, Source, VerificationResult } from "./types";

function App() {
  const [companyName, setCompanyName] = useState("");
  const [question, setQuestion] = useState("");
  const [task, setTask] = useState<ResearchTask | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [sources, setSources] = useState<Source[]>([]);
  const [facts, setFacts] = useState<Fact[]>([]);
  const [verifications, setVerifications] = useState<VerificationResult[]>([]);
  const [running, setRunning] = useState(false);
  const [chatMessage, setChatMessage] = useState("");
  const [chatResult, setChatResult] = useState<ChatResponse | null>(null);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function loadResearchArtifacts(taskId: string) {
    const [nextReport, sourceList, factList, verificationList] = await Promise.all([
      getResearchReport(taskId),
      getSources(taskId),
      getFacts(taskId),
      getVerification(taskId),
    ]);
    setReport(nextReport);
    setSources(sourceList.items);
    setFacts(factList.items);
    setVerifications(verificationList.items);
  }

  async function handleRun() {
    if (!companyName.trim() || !question.trim()) {
      setError("请先填写企业名称和研究问题。");
      return;
    }
    setRunning(true);
    setError(null);
    try {
      const created = await createResearchTask({
        company_name: companyName.trim(),
        question: question.trim(),
      });
      await runResearchTask(created.task_id);
      const latestTask = await getResearchTask(created.task_id);
      setTask(latestTask);
      if (latestTask.status === "failed") {
        setReport(null);
        setSources([]);
        setFacts([]);
        setVerifications([]);
        setError(latestTask.error_message ?? "研究任务运行失败，未生成报告。");
        return;
      }
      await loadResearchArtifacts(created.task_id);
      setChatResult(null);
      setChatError(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "运行失败，请稍后重试。";
      setError(message);
    } finally {
      setRunning(false);
    }
  }

  async function handleSendMessage() {
    if (!task?.task_id) {
      setChatError("请先运行研究任务，拿到 task_id 后再追问。");
      return;
    }
    if (!chatMessage.trim()) {
      setChatError("请输入追问内容。");
      return;
    }
    setChatLoading(true);
    setChatError(null);
    try {
      const response = await chatWithTask({
        task_id: task.task_id,
        message: chatMessage.trim(),
      });
      setChatResult(response);
    } catch (err) {
      const message = err instanceof Error ? err.message : "追问失败，请稍后重试。";
      setChatError(message);
    } finally {
      setChatLoading(false);
    }
  }

  return (
    <main className="app-shell">
      <h1>可溯源企业公开信息研究智能体</h1>
      <p className="page-desc">
        基于公开资料导入、证据追溯、事实验证、合规输出与报告追问，演示企业信息研究主链路。
      </p>

      <RegressionEvalPanel />
      <ResearchForm
        companyName={companyName}
        question={question}
        running={running}
        onCompanyNameChange={setCompanyName}
        onQuestionChange={setQuestion}
        onRun={handleRun}
      />
      <TaskStatusPanel task={task} error={error} />
      <ReportPanel report={report} />
      <EvidencePanel report={report} sources={sources} />
      <VerificationPanel facts={facts} verifications={verifications} />
      <ChatPanel
        task={task}
        chatMessage={chatMessage}
        chatLoading={chatLoading}
        chatError={chatError}
        chatResult={chatResult}
        onMessageChange={setChatMessage}
        onSend={handleSendMessage}
      />
    </main>
  );
}

export default App;
