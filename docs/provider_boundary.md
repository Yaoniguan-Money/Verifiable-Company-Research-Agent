# Provider Boundary

本文说明 provider / repository / service 边界，并补充真实链路 smoke 脚本和真实链路前端联调所需的 provider 选择口径。

## 1. Purpose

本文说明 provider / repository / service 的边界。项目目标是通用企业公开信息研究系统，provider 可替换，不绑定默认示例厂商。

## 2. 默认本地配置与可选 provider 示例

本地默认示例配置（见 `.env.example`）：

```text
LLM_PROVIDER=mock
SEARCH_PROVIDER=local_documents
EMBEDDING_PROVIDER=local_hashing
VECTOR_STORE=in_memory
WORKFLOW_ENGINE=langgraph
```

可选 provider 示例（见 `.env.providers.example`）包括 DeepSeek、Qianfan、Baidu AI Search、DashScope、SiliconFlow 等。它们仅是可选配置示例，不代表架构限制。

## 3. Current Provider Selection

Provider 创建集中在 `app.providers.factory.ProviderFactory`。

| 能力 | 当前实现 | 状态 |
|---|---|---|
| LLM | `MockLLMProvider` | 测试 / 本地开发 |
| LLM | `DeepSeekLLMProvider` | 可选真实链路示例 chat provider |
| LLM | `QianfanLLMProvider` | 可选真实链路示例 chat provider |
| Search | `MockSearchProvider` | 测试 / 本地开发 |
| Search | `LocalDocumentSearchProvider` | 从本地 txt/md 导入公开资料 |
| Search | `OfficialUrlSearchProvider` | 抓取白名单 URL 清单 |
| Search | `BaiduAISearchProvider` | 可选真实链路示例搜索 provider |
| Search | `CninfoAnnouncementProvider` | 公告来源 provider |
| Search | `HybridPublicSearchProvider` | 多公开来源组合 |
| Embedding | `MockEmbeddingProvider` | deterministic mock 向量 |
| Embedding | `LocalHashingEmbeddingProvider` | 本地词法 embedding，非语义验收 |
| Embedding | `OpenAICompatibleEmbeddingProvider` | OpenAI-compatible HTTP embedding |
| Vector Store | `InMemoryVectorStore` | 本地 MVP |
| Vector Store | `SQLiteVectorStore` | 本地持久化 MVP |

## 4. Allowed Places for Provider Names

具体 provider 名称只应出现在：

- provider adapter
- `ProviderFactory`
- `Settings`
- `.env.providers.example`
- provider 文档
- 验收脚本

不应出现在：

- API Router 的业务判断
- WorkflowFacade 的主流程步骤
- LangGraph node 的业务判断
- Domain Service 的厂商分支逻辑

Domain Service 可以依赖 provider interface，但不关心具体厂商。

## 5. Repository Boundary

`ResearchTaskRepository` 与 `ResearchArtifactRepository` 负责：

- task 生命周期查询、创建、运行 claim
- source / chunk / fact / verification / report 查询
- task 输出清理
- report 写入
- source/chunk map 与 source context

Repository 不写业务流程判断。

## 6. Real-chain Validation

真实链路 smoke 应显式说明所用 provider 配置。可选真实链路示例配置可以验证外部 API、embedding、citation、compliance 等链路，但结果质量仍受上游返回和页面可抓取性影响。

真实公司回归样例只用于链路回归，不代表系统绑定特定企业，也不构成投资分析、评级、推荐或建议。

### 6.1 DeepSeek LLM smoke 模型选择

真实链路 smoke 推荐使用 `DEEPSEEK_MODEL=deepseek-chat`。`deepseek-v4-flash` 仍可作为可选模型，但在部分长推理 / 风险分析 prompt 下可能返回 `reasoning_content`，同时 `message.content` 为空；provider 不会把 `reasoning_content` 当最终报告内容使用。

如果后端错误指向 LLM empty response，可先切换到 `deepseek-chat`，或提高对应 LLM 调用的 token 上限。错误信息不应回显 `Authorization` header 或 API key。

### 6.2 Baidu AI Search 常见排错

`BaiduAISearchProvider` 直接对接百度千帆 `POST /v2/ai_search/chat/completions`，以下是真实链路 smoke 中最常见的几种业务错误，与 API key 是否泄露无关，所有 `request_id` 都可拿到百度千帆控制台日志页查询：

- 后端日志看到 `Baidu AI Search business error: invalid_model - The model does not exist or you do not have access to it. (request_id=...)`：当前 `BAIDU_AI_SEARCH_MODEL` 在你的账号下未开通或拼写错误。把 `.env` 里 `BAIDU_AI_SEARCH_MODEL` 换成账号已开通的 chat model，例如 `ernie-4.5-turbo-32k`、`ernie-4.5-turbo-128k`、`deepseek-v3` 等（具体可用列表见百度千帆控制台 → 模型广场）。
- 后端日志看到 `Baidu AI Search business error: invalid_token - ...` 或 HTTP 401 / 403：API key 鉴权失败。检查 `BAIDU_AI_SEARCH_API_KEY` 是否粘贴完整、是否使用了正确账号下的 key。
- 后端日志看到 `Baidu AI search returned no usable references`（业务错误检查通过、references 为空）：百度返回了合法的成功响应但本次搜索没拿到候选；建议换更具体的真实公司名 / 研究问题，或在 `.env` 中开 `BAIDU_AI_SEARCH_ENABLE_DEEP_SEARCH=true`。

provider 不会在错误信息里回显 `Authorization` / `X-Appbuilder-Authorization` header 或 API key 内容；`request_id`、`code`、`message` 是非敏感字段，可在 issue / 内部排查中直接引用。

## 7. Next Improvements

- 固定公开数据集评测
- PDF/表格抽取增强
- embedding 缓存、配额控制和失败重试
- 可选接入生产级 vector store
- 更严格的事实审计和合规策略

## 8. 如何新增 provider

新增 provider 建议按以下边界落地：

1. 在 `app.providers` 下新增 adapter，实现对应接口（`LLMProvider` / `SearchProvider` / `EmbeddingProvider`）。
2. 在 `app.core.config.Settings` 增加可选配置项与运行时校验。
3. 在 `ProviderFactory` 增加 provider 选择分支，不修改 workflow 主链路。
4. 在 `.env.providers.example` 增加注释示例，key 字段保持空值。
5. 增加对应单元测试，验证：
   - key 缺失时失败可解释
   - 不发生隐式 fallback 到其他 provider
   - 不引入企业特判逻辑
