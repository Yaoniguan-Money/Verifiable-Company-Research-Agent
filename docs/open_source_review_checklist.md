# Open Source Review Checklist

这份 checklist 面向开源 reviewer，帮助快速判断项目能演示什么、不能证明什么。项目定位是开源 MVP / reference implementation，不是生产级投研系统，也不提供投资建议。

## 1. 快速启动

- [ ] 阅读根目录 `README.md` 的项目目标、当前能力和当前边界。
- [ ] 按 `README.md` 或 `docs/demo.md` 启动后端。
- [ ] 启动前端并打开 React/Vite demo 页面。
- [ ] 使用 mock provider 或本地公开资料样例跑通一次研究任务。
- [ ] 确认页面能展示 report、citations、verification、facts、sources 和 chat follow-up。

参考文档：

- `README.md`
- `docs/demo.md`
- `docs/api.md`

## 2. 运行测试

- [ ] 运行后端测试：`.\.venv\Scripts\python -m pytest backend\tests -q`
- [ ] 运行后端 lint：`.\.venv\Scripts\python -m ruff check backend scripts`
- [ ] 运行前端构建：`cd frontend && npm run build`
- [ ] 阅读 `docs/eval.md`，理解这些测试能证明什么、不能证明什么。

注意：测试通过不代表真实搜索质量、真实 LLM 推理质量或生产级事实审计质量。

## 3. 查看公开资料 fixture 回归

- [ ] 查看 `data/eval/public_company_regression.json` 中固定的公司、问题和预期指标组。
- [ ] 查看 `data/eval/public_company_regression_fixtures.json` 中离线样本。
- [ ] 运行离线 fixture 回归：`.\.venv\Scripts\python scripts\run_public_company_regression.py --use-fixtures --extract --json`
- [ ] 如需报告格式，运行：`.\.venv\Scripts\python scripts\run_public_company_regression.py --use-fixtures --extract --format markdown`
- [ ] 确认前端“公开资料回归评测结果”只是静态摘要，不调用后端新接口。

注意：fixture regression 是稳定离线样本，不是真实线上评测，也不声明为最新公开数据。

## 4. 查看 LangGraph workflow

- [ ] 阅读 `docs/workflow.md` 和 `docs/architecture.md`。
- [ ] 查看 `WORKFLOW_ENGINE=service` 与 `WORKFLOW_ENGINE=langgraph` 的边界说明。
- [ ] 确认 LangGraph 路径复用业务节点，用于图编排和条件路由。
- [ ] 确认当前不是让 LLM 自主规划任务的全自动 Agent。

## 5. 查看 RAG MVP

- [ ] 阅读 `docs/rag_design.md`。
- [ ] 查看 evidence chunk、embedding、vector store、retrieval、grounding 和 citation 的链路。
- [ ] 确认 `local_hashing` 是本地词法 hashing，不是真实语义 embedding。
- [ ] 确认 SQLite vector store 是本地持久化实现，不是生产级向量数据库替代品。

## 6. 查看合规边界

- [ ] 阅读 `docs/compliance.md`。
- [ ] 测试 chat follow-up 中的买卖建议、目标价、收益承诺等违规表达。
- [ ] 确认项目只做公开资料事实摘要、风险因素、数据冲突提示和来源追溯。
- [ ] 确认 README、docs、后端输出和前端文案没有把系统包装成荐股或投研推荐系统。

## 7. 查看当前非生产级边界

- [ ] 确认 mock provider、rule-based extraction、rule-based verification 和 rule-based compliance 的定位。
- [ ] 确认真实搜索质量依赖 provider 和外部来源，不由 fixture regression 证明。
- [ ] 确认没有登录、权限、审计后台、生产级配置治理或前端 E2E。
- [ ] 确认当前 DeepSeek 只作为可选 chat provider，不改变证据链和合规边界。

## 8. 查看后续路线图

- [ ] 阅读 README 的“后续路线图”。
- [ ] 优先关注真实 embedding provider、生产级 vector store adapter、公开数据集评测和前端 E2E。
- [ ] 评估是否需要补充迁移工具、权限系统、审计日志、异步队列和生产级配置治理。

## Reviewer 结论模板

- [ ] 项目定位是否诚实：开源 MVP / reference implementation，而非生产级系统。
- [ ] 证据链是否清晰：sources -> chunks -> retrieval -> facts -> verification -> citations -> report。
- [ ] 合规边界是否一致：不输出投资建议，不做荐股定位。
- [ ] 测试是否覆盖关键边界：API、DB、RAG MVP、verification、compliance、fixture regression、frontend build。
- [ ] 非生产级边界是否写清楚：mock、local_hashing、fixture、rule-based、InMemory / SQLite。
