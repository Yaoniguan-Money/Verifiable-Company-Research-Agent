# Release Notes（Public Release）

## 0. 2026-05-20 开源前整理摘要

- 修复真实联网研究链路：默认搜索口径保持 `public_sources` 联网公开来源，可选真实链路支持 DeepSeek、Baidu AI Search 和 DashScope；真实 provider 缺 key 时显式失败，不静默 fallback 到 mock。
- 改善报告可读性：主报告优先呈现人能读懂的核心事实、支撑事实、证据不足说明和引用，技术字段收敛到证据/API/附录层。
- 收敛 Baidu AI Search 引用处理边界：API 调用、引用抓取、来源质量判断和业务相关性判断分层处理，业务登记类来源按第三方背景证据处理，不写死具体公司。
- 收敛事实相关性规则：问题意图、业务事实 token、风险 token、财务/产能指标排序拆成可测试常量，避免临时补丁散落在方法体里。
- 清理开源隐私风险：`.env` 不入库，真实 key 模板留空；本地 private/local evaluation case 被 `.gitignore`、CI 和 `scripts/verify_secrets.ps1` 拦截。
- 固定真实公司 live 回归样例迁到 `data/eval/live_public_company_cases.example.json`，脚本只读取 case 文件，不再把公司名硬编码到代码。
- 已验证：`pytest`、`ruff`、前端 `typecheck/build`、`verify_secrets.ps1` 全部通过。

## 1. 项目定位

Verifiable Company Research Agent / 可溯源企业公开信息研究智能体：通用公开资料研究框架，支持可替换 provider、可替换 workflow engine、citation-bound report 和合规输出。

## 2. 本轮开源前重构

- 去掉主链路中的具体企业兜底逻辑
- 将 `ResearchWorkflowService` 拆成 application-facing `WorkflowFacade` 和可替换 `WorkflowEngine`
- 新增 `LangGraphWorkflowEngine` 作为默认实现
- 保留 `ServiceWorkflowEngine` 作为 legacy fallback
- 新增 `ResearchDomainServices`，让 graph node 只做 state 映射和 domain service 调用
- 更新 provider 文档口径：默认配置是 `mock + public_sources + local_hashing`；搜索默认走联网公开来源，DeepSeek、Baidu AI Search、DashScope 是可选真实链路示例，不是架构限制
- 前端默认输入和根 README 改为中性示例
- 固定真实公司样例只保留在 evaluation cases 与 data/eval case 文件层，回归脚本不内置公司名

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
