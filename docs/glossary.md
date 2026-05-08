# Glossary

本文解释项目文档、代码和 demo 中反复出现的核心术语。所有说明都以当前工程 MVP 为边界，不把 mock、fixture 或本地规则能力包装成生产级能力。

## public sources

公开资料来源。当前项目支持 mock、本地导入文档、官方 URL 清单、巨潮资讯公告 PDF、百度 AI 搜索 references 以及混合公开资料 provider。它们用于演示公开信息研究链路，不等同于生产级搜索引擎、企业数据库或完整线上资料覆盖。

## evidence chunk

证据片段。系统会把来源正文切分成较小文本块，保留 `source_id`、`chunk_id`、`task_id` 等追溯字段，供检索、事实抽取和报告引用使用。它是证据链的中间结构，不代表事实本身已经被验证。

## citation

引用信息。报告中的 citation 指向支撑内容的来源和证据片段，通常包含 `source_id`、`chunk_id`、标题、URL 和检索时间。citation 的作用是让输出可追溯，不表示来源一定充分、最新或没有冲突。

## fact extraction

事实抽取。当前主要是 rule-based 抽取，将证据片段中的指标、年份、数值和来源字段结构化为 facts。它能覆盖研发投入、收入、归母净利润、收入结构、产能、产量、销量等常见样本，但不是通用财报理解模型。

## verification

事实验证。系统基于规则比较事实之间的来源、指标、期间和数值，输出 `verified`、`conflicted`、`insufficient`、`outdated`、`rejected` 等状态。当前验证适合工程演示和回归测试，不是生产级事实审计。

## reason_code

验证原因代码。`reason_code` 用于解释 verification 的判定来源，例如单位归一后同值、指标别名归一后同值、多来源冲突、单一来源证据不足等。它帮助 reviewer 理解系统为什么给出某种验证状态。

## workflow decision

工作流决策记录。当前用于记录 workflow 中某些分支判断，例如事实为空时记录证据缺口，或 verification 存在风险时记录风险分支。它让主链路更可观察，而不是让 LLM 自主规划整个任务。

## LangGraph workflow

可选 LangGraph 图编排路径。当前 `WORKFLOW_ENGINE=langgraph` 时会复用同一批业务节点，用图结构表达抽取、验证、风险记录、分析等步骤和条件路由。它展示图编排能力，但不是带长期计划、工具自选和人工审核闭环的生产级 Agent。

## RAG MVP

检索增强生成的最小可运行版本。当前包含文档切分、embedding、vector store、任务内检索、evidence grounding 和 citations。它证明链路和接口边界可运行，但不代表生产级语义检索质量。

## local_hashing embedding

本地词法 hashing embedding。它用于离线、确定性、可测试的向量生成，不需要外部 embedding API。它不是真实语义 embedding，不能被描述为具备生产级语义理解能力。

## SQLite vector store

SQLite 持久化向量存储实现。它用于演示向量写入、任务隔离、相似度查询和本地持久化边界。它不是 Chroma、Qdrant 或其他生产级向量数据库替代品。

## compliance guardrail

合规护栏。当前通过规则限制报告和 chat 输出，避免买卖建议、目标价、收益承诺、个股推荐和个性化投顾表达。它是工程合规边界示范，不等同于生产级合规模型或审计系统。

## fixture regression

离线 fixture 回归评测。项目用固定的公开资料节选测试事实抽取和指标覆盖，避免每次评测依赖真实网络、PDF 下载或外部 API。fixture regression 只证明稳定样本下的链路表现，不代表真实线上搜索质量或最新公开数据覆盖。

## hot memory

热记忆。当前项目没有实现面向实时对话上下文的完整 hot memory 系统；chat follow-up 只围绕已有任务和报告进行最小追问。

## warm memory

温记忆。当前已有 MVP 级 schema、coordinator、coalescing、persistence 和集成测试，用于表达可沉淀的用户偏好或长期上下文。它仍是工程 MVP，不是完整用户画像系统。

## cold memory

冷记忆。当前没有实现跨任务大规模知识库、长期语义索引或生产级知识沉淀。后续若接真实 embedding 和持久向量库，可逐步向 cold memory 演进。
