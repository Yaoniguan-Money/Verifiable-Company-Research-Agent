# Testing Guide

本文汇总 Windows PowerShell 下常用验收命令。所有命令默认从项目根目录运行；前端命令需要先进入 `frontend` 目录。

## 0. 测试前依赖安装

运行测试前请先安装开发依赖（包含 `pytest` 与 `ruff`）：

```powershell
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
```

## 1. 后端全量测试

```powershell
.\.venv\Scripts\python -m pytest backend\tests -q
```

如果希望看到更详细测试名：

```powershell
.\.venv\Scripts\python -m pytest backend\tests -v
```

## 2. ruff 检查

检查后端和脚本：

```powershell
.\.venv\Scripts\python -m ruff check backend scripts
```

只检查后端：

```powershell
.\.venv\Scripts\python -m ruff check backend
```

## 3. secret 和交付文件检查

```powershell
.\scripts\verify_secrets.ps1
```

该脚本会检查当前工作目录是否只保留 `.env.example`，并在 Git 仓库中额外检查 `.env` 类文件是否出现在历史记录里。它不能替代服务商控制台里的 key 轮换。

## 4. 前端 build

```powershell
cd frontend
npm run typecheck
npm run build
```

`npm run build` 已经包含 `tsc --noEmit`，这里显式列出 `typecheck` 是为了在验收记录中单独暴露前端类型检查。

回到项目根目录：

```powershell
cd ..
```

## 5. 公开资料 fixture 回归 JSON 输出

```powershell
.\.venv\Scripts\python scripts\run_public_company_regression.py --use-fixtures --extract --json
```

该命令使用离线 fixture，不接真实 API，不下载 PDF。JSON 输出适合机器读取和回归核对。

## 6. 公开资料 fixture 回归 Markdown 输出

```powershell
.\.venv\Scripts\python scripts\run_public_company_regression.py --use-fixtures --extract --format markdown
```

等价写法：

```powershell
.\.venv\Scripts\python scripts\run_public_company_regression.py --use-fixtures --extract --markdown
```

Markdown 输出适合粘贴到评审记录。它仍然是离线 fixture 回归，不代表真实线上搜索质量。

## 7. 真实 provider smoke

先启动后端，并在本地 `.env` 中配置真实 provider。脚本只打印 provider 元数据、任务状态和 citation 概览，不打印 API key 或 `.env` 内容。

```powershell
.\.venv\Scripts\python scripts\verify_real_chain.py --base-url http://localhost:8000
```

如果后端不在 8000 端口，改传对应地址，例如：

```powershell
.\.venv\Scripts\python scripts\verify_real_chain.py --base-url http://localhost:8001
```

## 8. 只跑 LangGraph workflow 测试

```powershell
.\.venv\Scripts\python -m pytest backend\tests\test_langgraph_research_workflow.py -q
```

如果需要同时看 workflow provider 相关测试，可以运行：

```powershell
.\.venv\Scripts\python -m pytest backend\tests\test_langgraph_research_workflow.py backend\tests\test_providers_workflow.py -q
```

## 9. 只跑 PDF 表格抽取测试

```powershell
.\.venv\Scripts\python -m pytest backend\tests\test_financial_table_extraction_service.py -q
```

对应 lint：

```powershell
.\.venv\Scripts\python -m ruff check backend\tests\test_financial_table_extraction_service.py
```

## 10. Docker Compose 启动验收

```powershell
docker compose up --build
```

验收地址：

```text
http://127.0.0.1:8000/api/health
http://127.0.0.1:5173
```

## 11. 常用组合

本地提交前的轻量组合：

```powershell
.\scripts\verify_secrets.ps1
.\.venv\Scripts\python -m ruff check backend scripts
.\.venv\Scripts\python -m pytest backend\tests -q
cd frontend
npm run typecheck
npm run build
cd ..
```

公开资料回归展示组合：

```powershell
.\.venv\Scripts\python scripts\run_public_company_regression.py --use-fixtures --extract --json
.\.venv\Scripts\python scripts\run_public_company_regression.py --use-fixtures --extract --format markdown
```

## 12. 结果边界

- 测试通过不代表生产级搜索质量。
- fixture 回归不代表真实线上评测。
- `local_hashing` embedding 不是真实语义 embedding。
- rule-based verification 和 compliance 不代表生产级事实审计或合规系统。
