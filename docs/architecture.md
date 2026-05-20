# 系统架构

当前状态：可溯源企业公开信息研究智能体，开源 MVP / reference implementation。默认 SearchProvider 走联网公开来源；可选真实链路 provider 可以跑真实 API，但系统架构不绑定任何具体厂商、企业或样例。

## 1. Top-level Overview

```text
Frontend (React/Vite)
  -> FastAPI Router
      -> WorkflowFacade / Application Service
          -> WorkflowEngine Interface
              -> LangGraphWorkflowEngine
                  -> StateGraph
                      -> Graph Nodes
                          -> ResearchDomainServices
                              -> Provider adapters
                              -> Repository
          -> ServiceWorkflowEngine (legacy fallback)
```

## 2. Layer Responsibilities

API Router:

- 处理 HTTP 请求、参数校验和响应转换
- 不写研究主流程
- 不直接调用 provider
- 不直接操作 LangGraph node

Application Service / WorkflowFacade:

- 创建任务、claim 任务、启动任务、查询状态
- 管理任务运行前输出清理和失败落库
- 调用 `WorkflowEngine`
- 不逐步执行 search、ingest、extract、verify、report

WorkflowEngine Interface:

- 定义 `run(task_id)`、`get_status(task_id)`、`resume(task_id)` 等契约
- 允许替换 LangGraph 实现

LangGraphWorkflowEngine:

- 默认 workflow engine
- 构建 StateGraph、节点流转、条件边、失败状态和审计状态
- 不承载 provider 细节或复杂业务规则

Graph Nodes:

- 只读写 `WorkflowState`
- 调用 domain service
- 保持薄节点

Domain Services:

- 承载 source collection、ingestion、retrieval、fact extraction、fact verification、report grounding、compliance check 等业务能力
- 不依赖 LangGraph
- 可被单元测试直接调用

Providers / Repository:

- Provider 只负责外部 LLM / Search / Embedding API 或本地 mock/dev provider
- Repository 只负责数据库访问
- 不写业务流程判断

## 3. Backend Modules

```text
backend/app/
  api/              FastAPI routes and dependencies
  compliance/       rule-based compliance rules
  core/             settings
  db/               SQLAlchemy base/session/models/init
  providers/        provider adapters and factory
  repositories/     task/artifact persistence boundary
  schemas/          Pydantic contracts
  services/         domain services, evidence, retrieval, report, chat, memory
  vectorstores/     vector store abstraction
  workflows/        workflow engine interfaces and implementations
```

## 4. Provider Boundary

`ProviderFactory` centralizes provider creation. 默认示例是 `mock + public_sources + local_hashing`；DeepSeek、Baidu AI Search、DashScope 是可选真实链路示例配置，不是系统架构限制。

业务层面依赖接口：

- `LLMProvider`
- `SearchProvider`
- `EmbeddingProvider`
- `VectorStore`

具体厂商名称只应出现在 provider adapter、factory、settings、示例环境变量和验收脚本中。

## 5. Workflow Boundary

LangGraph 是默认 workflow engine，不是自主规划 agent。LLM 不决定主流程，只在局部能力中工作，例如风险分析、报告文本生成或合规判断。

`ServiceWorkflowEngine` 保留旧顺序执行路径，仅用于 `WORKFLOW_ENGINE=service` 回归验证。

## 6. Evidence / RAG Boundary

当前 RAG 组件：

- ingestion / chunking
- embedding provider
- vector store
- retrieval service
- report evidence service
- report grounding / citation formatting

这证明工程边界和 traceability，不代表生产级检索质量。

## 7. Compliance

合规护栏应用在：

- workflow 报告生成后
- report API 输出
- chat follow-up 输出

系统禁止投资建议、买卖建议、目标价、收益承诺、个股推荐和持仓指导。

## 8. Limitations

- 当前不是生产级 RAG、生产级事实审计或生产级合规系统
- 外部搜索质量受上游 provider、页面抓取、PDF 解析影响
- vector store 仍是本地 MVP 实现
- 前端是演示界面，不是生产工作台

真实公司样例仅用于链路回归，见 `docs/evaluation_cases.md`。
