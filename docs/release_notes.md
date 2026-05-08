# Release Notes（Public Release）

## 1. 项目定位

Verifiable Company Research Agent / 可溯源企业公开信息研究智能体：通用公开资料研究框架，支持可替换 provider、可替换 workflow engine、citation-bound report 和合规输出。

## 2. 本轮开源前重构

- 去掉主链路中的具体企业兜底逻辑
- 将 `ResearchWorkflowService` 拆成 application-facing `WorkflowFacade` 和可替换 `WorkflowEngine`
- 新增 `LangGraphWorkflowEngine` 作为默认实现
- 保留 `ServiceWorkflowEngine` 作为 legacy fallback
- 新增 `ResearchDomainServices`，让 graph node 只做 state 映射和 domain service 调用
- 更新 provider 文档口径：本地默认配置是 `mock + local_documents + local_hashing`；DeepSeek、Baidu AI Search、DashScope 是可选真实链路示例，不是架构限制
- 前端默认输入和根 README 改为中性示例
- 固定真实公司样例只保留在 evaluation cases 与回归脚本层

## 3. 当前能力

- LangGraph 固定编排主链路（非自主规划 agent）
- Provider abstraction and factory
- source authority / source layer 分层与门控
- fact extraction / verification（规则化 MVP）
- compliance guardrail（非投顾输出约束）
- citation-bound report（可回查 source/chunk）
- 回归与验收入口：`verify_real_chain.py`、`run_public_company_regression.py`

## 4. 不适合的使用场景

- 生产级投研系统直接上线
- 个股买卖建议、目标价、收益承诺输出
- 需要生产级高可用、低延迟、强治理的金融系统

## 5. 已知边界

- 项目定位是开源 MVP / reference implementation，不是生产级系统
- vector store 仍为 `in_memory/sqlite`
- 真实 API 会受 timeout、限流和外部波动影响
- verification / compliance 为规则化 MVP
- 真实公司样例只用于链路回归，不构成投资分析、评级、推荐或建议

## 6. 推荐验收命令

```powershell
& ".\.venv\Scripts\python.exe" -m pytest backend/tests -q
& ".\.venv\Scripts\python.exe" -m ruff check backend scripts

cd frontend
npm run build
cd ..
```

## 7. 下一步计划

- 增强固定评测样例覆盖
- 增加 provider latency / failure metrics
- 评估 embedding cache 和生产级 vector store
- 增强 PDF/表格抽取和事实审计
