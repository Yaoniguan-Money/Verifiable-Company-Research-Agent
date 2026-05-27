# 贡献指南（CONTRIBUTING）

感谢你关注 `Verifiable Company Research Agent`。

> 仓库地址：<https://github.com/Yaoniguan-Money/Verifiable-Company-Research-Agent>

本项目是“证据优先”的企业公开信息研究开源实现。欢迎提交 bug 修复、测试补充、文档改进和功能增强。

## 一、贡献前请先确认

- 本项目不提供任何投资建议功能。
- 不接受引入荐股、目标价、收益承诺等投顾导向能力。
- 提交前请确保没有泄漏任何密钥、令牌、账号或本地隐私数据。

## 二、环境准备

推荐先阅读：

- `README.md`
- `docs/windows_quickstart.md`
- `docs/testing_guide.md`

常见本地启动方式（Docker）：

```powershell
Copy-Item .env.example .env
docker compose -p vcra up -d --build --force-recreate
```

## 三、开发流程

1. 从主分支拉取最新代码。
2. 创建功能分支，建议命名：
   - `feat/<short-name>`
   - `fix/<short-name>`
   - `docs/<short-name>`
   - `test/<short-name>`
3. 完成修改后先本地自测（见下方“提交前检查”）。
4. 提交 PR，清楚说明：
   - 改动动机（为什么改）
   - 改动范围（改了哪些模块）
   - 验证方式（如何验证）
   - 风险与回滚点（如有）

## 四、提交前检查（必做）

至少完成以下检查：

- 后端测试（`pytest`）通过
- 代码静态检查（如 `ruff`）通过
- 前端构建或类型检查通过（如改动了前端）
- 不包含真实密钥、调试日志、临时产物

如果你的改动涉及以下模块，必须补测试：

- 检索与排序（RAG / reranker / retrieval）
- 事实抽取与验证（fact extraction / verification）
- 报告生成与合规（report / compliance）
- Provider 工厂与配置行为

## 五、代码风格与约束

- 尽量小步提交，避免“超大混合 PR”。
- 优先保证可读性和边界清晰，不引入隐式全局副作用。
- 避免硬编码密钥、账号、真实公司隐私信息。
- 对复杂逻辑补充必要注释，注释要解释“为什么”，而不是重复“做了什么”。

## 六、文档要求

以下情况需要同步更新文档：

- 新增或删除配置项
- 调整运行方式或命令
- 修改系统边界、默认行为、输出语义

建议更新对应 `docs/` 文档并在 PR 描述中注明。

## 七、Issue 与 PR 建议

- Bug：请提供复现步骤、期望行为、实际行为、运行环境。
- Feature：请说明业务价值、边界、潜在风险。
- PR：保持聚焦，一个 PR 尽量解决一类问题。

## 八、安全与隐私

- 发现安全问题请不要直接公开敏感细节。
- 禁止提交任何 `.env` 实值、API key、token、数据库快照、日志脱敏前原文。
- 如发现历史泄漏风险，请在 PR 中说明处理方式（删除、轮换、扫描结果）。

---

再次感谢你的贡献。

稳定、可验证、可追溯，是本项目最核心的工程目标。
