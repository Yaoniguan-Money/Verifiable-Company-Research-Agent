# Windows Quickstart

本文面向 Windows PowerShell 本地启动，覆盖 Docker 一键启动、本地开发启动和常见端口排障。本文每节都从项目根目录开始，自己装自己需要的依赖，不需要跨节跳读。不要把真实 API key 写入文档、截图或提交记录。

## 0. 一键启动

如果只是想快速跑起本地演示：

```powershell
.\scripts\dev.ps1
```

如果已经安装过依赖：

```powershell
.\scripts\dev.ps1 -SkipInstall
```

脚本会从 `.env.example` 创建本地 `.env`，并分别启动后端 `http://127.0.0.1:8000` 与前端 `http://127.0.0.1:5173`。真实 key 只放本地 `.env`，不要提交或打包。

如果使用 Docker Compose：

```powershell
Copy-Item .env.example .env
docker compose -p vcra up -d --build --force-recreate
```

Docker Compose 会同时启动 backend 与 frontend，端口映射为 `8000:8000` 和 `5173:5173`。默认使用 mock provider 和容器内 SQLite，适合只验证项目是否能稳定跑起来。

## 1. 环境要求

- Python 3.10+
- Node.js 18+
- PowerShell 5+ 或 PowerShell 7+
- pip / npm

检查版本：

```powershell
python --version
node --version
npm --version
```

## 2. 创建并激活虚拟环境

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
```

如果已经创建过 `.venv`，只需要激活：

```powershell
.\.venv\Scripts\Activate.ps1
```

激活成功后，PowerShell prompt 通常会出现 `(.venv)` 前缀。

## 3. 安装后端依赖

运行依赖（启动服务所需）：

```powershell
pip install -r requirements.txt
```

也可以显式使用虚拟环境里的 Python：

```powershell
.\.venv\Scripts\python -m pip install -r requirements.txt
```

如果要运行测试和 `ruff`，再安装开发依赖：

```powershell
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
```

## 4. 创建本地环境文件

```powershell
Copy-Item .env.example .env
```

`.env` 是本地配置文件，不要提交真实 key。本文不要求读取 `.env`，也不会展示任何真实 API key。

如需启用外部 provider，请参考 `.env.providers.example` 与 `docs/provider_boundary.md`，按需把对应配置写入本地 `.env`。

如果跑真实链路 smoke，DeepSeek 示例模型推荐使用 `DEEPSEEK_MODEL=deepseek-chat`。`deepseek-v4-flash` 可作为可选模型，但在部分长推理 / 风险分析 prompt 下可能只返回 `reasoning_content`，同时 `message.content` 为空；项目不会把 `reasoning_content` 当最终报告内容使用。遇到 LLM empty response 时，先切换 `deepseek-chat` 或提高 token 上限。

## 5. 启动后端

```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --reload --app-dir backend --host 127.0.0.1 --port 8000
```

启动成功后窗口里应当持续打印 `Uvicorn running on http://127.0.0.1:8000`。如果看到 `WinError 10013`，说明 `8000` 被其他进程占用，请按下面"## 8. 常见问题 → 端口占用"小节中的 4 种情况之一处理。

默认地址：

```text
http://127.0.0.1:8000
```

健康检查：

```text
http://127.0.0.1:8000/api/health
```

## 6. 启动前端

打开一个新的 PowerShell 窗口，进入项目根目录后运行：

```powershell
cd frontend
npm ci
npm run dev
```

Vite 会输出本地页面地址，通常是：

```text
http://127.0.0.1:5173
```

开发模式下，前端 `/api` 请求会代理到 `http://127.0.0.1:8000`。

## 7. 打开本地页面

在浏览器打开 Vite 输出地址，例如：

```text
http://127.0.0.1:5173
```

可以先使用默认 mock provider 跑通最小 demo，再按 `docs/demo_walkthrough.md` 和 `docs/provider_boundary.md` 切换本地公开资料或外部 provider。

## 8. 常见问题

### 端口占用

后端启动时报 `OSError: [WinError 10013]`（套接字访问权限错误），或前端 `http://localhost:5173` 打不开 / `npm run dev` 提示端口被占用，通常都是端口被旧后端、Docker 服务或其他程序占用。下面 4 种情况各给出从项目根目录开始就能复制执行的完整命令，按你的实际情况选一种即可。

#### 情况 1：8000 被占用 — 安全排查

先关掉之前可能用 Docker 启动的旧后端：

```powershell
docker compose -p vcra down
```

查看 8000 端口占用：

```powershell
netstat -ano | findstr :8000
```

如果看到 `LISTENING` 行，记下最后一列的 PID（例如 `12345`）。查看进程名：

```powershell
tasklist /FI "PID eq 12345"
```

确认该进程可以关闭后，结束它（把 `12345` 替换成你实际看到的 PID）：

```powershell
Stop-Process -Id 12345 -Force
```

然后重新启动后端：

```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --reload --app-dir backend --host 127.0.0.1 --port 8000
```

#### 情况 2：8000 被占用 — 开发环境快捷清理

如果你确认 `8000` 是旧开发服务占用、不是其他重要程序，可以一键清掉所有监听 `8000` 的进程（执行前请确认不是其他重要程序）：

```powershell
$port = 8000
$connections = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
$connections | ForEach-Object { Get-Process -Id $_.OwningProcess }
$connections.OwningProcess | Sort-Object -Unique | ForEach-Object { Stop-Process -Id $_ -Force }
```

清理后重新启动后端：

```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --reload --app-dir backend --host 127.0.0.1 --port 8000
```

#### 情况 3：5173 被占用 — 开发环境快捷清理

如果前端 `http://localhost:5173` 打不开，或 `npm run dev` 提示 `5173` 被占用，先看一眼占用情况：

```powershell
netstat -ano | findstr :5173
```

如果你确认是旧前端 dev server，可以一键清掉所有监听 `5173` 的进程（执行前请确认不是其他重要程序）：

```powershell
$port = 5173
$connections = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
$connections | ForEach-Object { Get-Process -Id $_.OwningProcess }
$connections.OwningProcess | Sort-Object -Unique | ForEach-Object { Stop-Process -Id $_ -Force }
```

然后重新启动前端：

```powershell
cd frontend
npm run dev
```

#### 情况 4：不关闭 8000，临时让后端跑 8001

适用场景：`8000` 被你不愿打断的进程占着，或你只想快速换一份本地后端跑 8001。

真实链路 smoke 也可以使用 8001，但需要把脚本的后端地址显式指向 8001：

```powershell
.\.venv\Scripts\python scripts\verify_real_chain.py --base-url http://localhost:8001
```

等价地，也可以在当前 PowerShell 窗口设置 `$env:VERIFY_BASE_URL="http://localhost:8001"` 后再运行脚本。

窗口 1 启动后端到 8001：

```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --reload --app-dir backend --host 127.0.0.1 --port 8001
```

窗口 2 启动前端，让它把 `/api` 代理到 8001（项目原生支持，不需要修改 `vite.config.ts`）：

```powershell
cd frontend
$env:VITE_PROXY_TARGET="http://127.0.0.1:8001"
npm run dev
```

注意：

- PowerShell 的 `$env:VITE_PROXY_TARGET="..."` 只对当前终端窗口有效；新开一个终端要重新设置后再 `npm run dev`，否则前端会回到默认代理目标 `http://127.0.0.1:8000`。
- 如果后端在 8001、前端没设置 `VITE_PROXY_TARGET`，前端页面能打开，但创建任务、查询健康检查这些请求会落到 8000，从而失败。
- 如果真实链路 smoke 脚本也要访问 8001，请传 `--base-url http://localhost:8001` 或设置 `VERIFY_BASE_URL`。
- 后端 OpenAPI 在这种情况下访问 `http://localhost:8001/docs`，前端仍然访问 `http://localhost:5173`。

### 虚拟环境未激活

如果出现 `ModuleNotFoundError` 或命令使用了全局 Python，先确认：

```powershell
Get-Command python
python --version
```

重新激活：

```powershell
.\.venv\Scripts\Activate.ps1
```

也可以直接使用虚拟环境 Python：

```powershell
.\.venv\Scripts\python -m pytest backend\tests -q
```

### PowerShell 执行策略阻止激活脚本

如果 `Activate.ps1` 被执行策略阻止，可以只对当前用户放宽脚本执行策略：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

然后重新打开 PowerShell，再运行：

```powershell
.\.venv\Scripts\Activate.ps1
```

如果不想修改执行策略，也可以不激活虚拟环境，直接使用：

```powershell
.\.venv\Scripts\python -m uvicorn app.main:app --reload --app-dir backend --host 127.0.0.1 --port 8000
```

### 环境变量未生效

修改 `.env` 后需要重启后端进程。PowerShell 临时环境变量只对当前窗口有效，例如：

```powershell
$env:WORKFLOW_ENGINE = "langgraph"
.\.venv\Scripts\python -m uvicorn app.main:app --reload --app-dir backend --host 127.0.0.1 --port 8000
```

如果新开了 PowerShell 窗口，需要重新设置临时环境变量，或把配置写入本地 `.env`。
