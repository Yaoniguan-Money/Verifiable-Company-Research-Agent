# Demo Walkthrough

本文是浏览器 demo 与真实链路前端联调的详细操作手册，也可在本地 Quick Start 启动完成后作为离线 demo 走查。本文每节都从项目根目录开始，不要求先读其他文档。

## 1. Demo 目标

从 0 跑通一个企业公开信息研究任务，验证项目具备可追溯研究流程，而不是普通聊天输出。

## 2. 环境准备

- Docker Desktop
- Python 3.10+
- Node.js 18+
- npm
- `.env`（由 `.env.example` 复制）

```powershell
Copy-Item .env.example .env
```

## 3. Provider 配置

本地默认配置（来自 `.env.example`）：

```text
LLM_PROVIDER=mock
SEARCH_PROVIDER=local_documents
EMBEDDING_PROVIDER=local_hashing
WORKFLOW_ENGINE=langgraph
```

如果要启用外部 provider，请参考 `.env.providers.example`（所有示例均为可选，不代表架构限制），并将所需配置写入本地 `.env`。密钥只放本地，不提交仓库，也不要写入 `.env.example` 或文档。

## 4. 启动项目

```powershell
docker compose -p vcra up -d --build --force-recreate
```

Docker Compose 会同时启动 backend 与 frontend，端口映射为 `8000:8000` 和 `5173:5173`。

## 5. 健康检查

```powershell
Invoke-RestMethod http://localhost:8000/health/providers
```

本地默认配置下重点确认：

- `mock_enabled=true`
- provider 与 `.env.example` 一致

可选真实链路 smoke 需要先在本地 `.env` 中配置真实 provider 组合与对应 API key，并确认：

- `mock_enabled=false`
- provider 与 `.env` 一致
- key configured 状态符合预期
- DeepSeek 真实链路 smoke 推荐 `DEEPSEEK_MODEL=deepseek-chat`
- `deepseek-v4-flash` 可作为可选模型，但部分长推理 / 风险分析 prompt 可能只返回 `reasoning_content`，同时 `message.content` 为空；项目不会把 `reasoning_content` 当最终报告内容使用
- 如果遇到 LLM empty response，可先切换到 `deepseek-chat` 或提高 token 上限

## 6. 创建任务（PowerShell UTF-8）

```powershell
$bodyObj = @{
  company_name = "demo tech"
  question = "请基于本地公开资料分析该企业最近的经营风险和公开披露一致性，要求给出引用来源，不要给投资建议。"
}

$bodyJson = $bodyObj | ConvertTo-Json -Depth 10
$bodyBytes = [System.Text.Encoding]::UTF8.GetBytes($bodyJson)

$task = Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/api/research/tasks" `
  -ContentType "application/json; charset=utf-8" `
  -Body $bodyBytes

$task
```

`demo tech` 对应仓库内 `data/imports/demo_tech` 的离线公开资料样例，不代表真实企业，也不构成投资分析、评级、推荐或建议。可选真实链路 smoke 请在本地 `.env` 配置真实 provider key 后，显式传入待研究公司和问题。

## 7. 运行任务

```powershell
$taskId = $task.task_id

Invoke-RestMethod `
  -Method Post `
  -Uri "http://localhost:8000/api/research/tasks/$taskId/run"
```

## 8. 查看报告

```powershell
Invoke-RestMethod "http://localhost:8000/api/research/tasks/$taskId/report"
```

## 9. 查看 Citation Source Layer

```powershell
$report = Invoke-RestMethod "http://localhost:8000/api/research/tasks/$taskId/report"
$sources = Invoke-RestMethod "http://localhost:8000/api/sources/$taskId"

$sourceMap = @{}
foreach ($s in $sources.items) { $sourceMap[$s.id] = $s }

$report.citations | ForEach-Object {
  $src = $sourceMap[$_.source_id]
  [PSCustomObject]@{
    title = $_.title
    url = $_.url
    source_layer = if ($src -and $src.source_metadata) { $src.source_metadata.source_layer } else { "unknown" }
    authority = if ($src -and $null -ne $src.credibility_score) {
      if ($src.credibility_score -ge 0.85) { "high_authority" }
      elseif ($src.credibility_score -lt 0.6) { "low_authority" }
      else { "medium_authority" }
    } else { "unknown" }
  }
}
```

## 10. 常见问题

- PowerShell 中文 body 建议使用 `ConvertTo-Json + UTF8 bytes`。
- 启用真实 provider 时必须配置对应 key。
- `mock_enabled=true` 表示当前不是真实 provider 链路。
- 外部 provider 超时、限流、认证失败不会 fallback 到 mock。
- `official_entry_page` 只能证明入口存在，不能单独作为高置信事实来源。

## 11. 回归样例

真实公司回归样例见 `docs/evaluation_cases.md`。这些样例只用于链路回归，不代表系统绑定特定企业，也不构成投资分析、评级、推荐或建议。
