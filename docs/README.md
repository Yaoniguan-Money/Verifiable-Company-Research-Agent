# Documentation Index

这个目录收录项目设计、演示、评测、合规和开发日志文档。

当前主口径：Verifiable Company Research Agent / 可溯源企业公开信息研究智能体。默认配置使用 `mock + public_sources + local_hashing`；搜索默认访问联网公开来源且不需要外部厂商 API key。DeepSeek、Baidu AI Search、DashScope 等是可选真实 provider 示例。LangGraph 是默认 workflow engine。项目定位是开源 MVP / reference implementation，不是生产级投研系统，也不提供投资建议。

## 推荐阅读顺序

1. [Glossary](glossary.md)：先理解核心术语和当前边界。
2. [Windows Quickstart](windows_quickstart.md)：按 Windows PowerShell 启动本地环境。
3. [Testing Guide](testing_guide.md)：运行后端测试、ruff、前端 build 和 fixture 回归。
4. [Project Structure](PROJECT_STRUCTURE.md)：按目录理解代码阅读路径。
5. [Architecture](architecture.md)：查看整体模块边界。
6. [LangGraph Orchestration](langgraph_orchestration.md)：理解默认主编排。
7. [Workflow](workflow.md)：理解 LangGraph workflow 与 legacy service fallback。
8. [Compliance](compliance.md)：理解合规护栏和禁止输出范围。
9. [Evaluation](eval.md)：理解测试、fixture regression 和评测边界。
10. [Demo Walkthrough](demo_walkthrough.md)：真实链路演示与验收流程。

## 核心展示文档

- [Glossary](glossary.md)
- [Windows Quickstart](windows_quickstart.md)
- [Testing Guide](testing_guide.md)
- [Project Structure](PROJECT_STRUCTURE.md)
- [Architecture](architecture.md)
- [API](api.md)
- [Demo Walkthrough](demo_walkthrough.md)
- [Evaluation and Testing](eval.md)
- [Compliance](compliance.md)
- [Provider Boundary](provider_boundary.md)
- [LangGraph Orchestration](langgraph_orchestration.md)
- [Memory Design](memory_design.md)

## Evaluation / Regression

- [固定评测样例](evaluation_cases.md)
- `scripts/verify_real_chain.py`（单次真实链路验收）
- `scripts/run_public_company_regression.py`（轻量回归入口，支持从 case 文件读取的 `--list` / `--case`）
- 固定真实公司样例仅用于链路回归，不代表系统绑定特定企业，也不应写死在生产代码里。

## Demo

- [Demo Walkthrough](demo_walkthrough.md)

## 诚实边界

阅读文档时请注意：

- mock provider 只用于测试，不代表真实搜索或真实 embedding 能力。
- `local_hashing` 是 dev/test 词法向量，不是真实语义 embedding。
- DashScope 是可选真实链路 embedding provider 示例；SiliconFlow 是 OpenAI-compatible 配置示例。
- fixture regression 是离线稳定样本，不是真实线上评测。
- rule-based verification 和 compliance 不是生产级事实审计或合规系统。
- 项目不提供买卖建议、目标价、收益承诺、荐股或个性化投顾。
