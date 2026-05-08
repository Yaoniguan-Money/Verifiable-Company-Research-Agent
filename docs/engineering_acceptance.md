# Engineering Acceptance

本文记录当前开源/交付前的最小工程验收口径，优先服务 public release review 和新人本地启动。

## Secrets Boundary

- 交付目录只保留 `.env.example`，不要提交或打包真实 `.env`。
- 新人本地启动时再执行 `Copy-Item .env.example .env`。
- 真实 LLM 只允许从环境变量读取密钥。Qianfan 使用 `QIANFAN_API_KEY`，DeepSeek 使用 `DEEPSEEK_API_KEY`；不要把真实 key 写入代码、README、测试、日志、截图或提交历史。
- `LLM_PROVIDER=mock` 是默认值，适合无密钥启动；`LLM_PROVIDER=qianfan` 但缺少 `QIANFAN_API_KEY` 时必须报明确配置错误。
- 如果真实 key 曾经写入本地 `.env` 或出现在历史提交、截图、压缩包中，需要到对应服务商控制台轮换；删除文件只能降低继续传播风险，不能撤销已经泄露的 key。

## One-command Local Startup

Windows PowerShell:

```powershell
.\scripts\dev.ps1
```

如果依赖已经装好，可以跳过安装步骤：

```powershell
.\scripts\dev.ps1 -SkipInstall
```

脚本会创建本地 `.env`、确保 `.venv` 存在，并分别启动：

- Backend: `http://127.0.0.1:8000`
- Frontend: `http://127.0.0.1:5173`
- Health check: `http://127.0.0.1:8000/api/health`

Docker Compose:

```powershell
Copy-Item .env.example .env
docker compose up --build
```

Compose 读取本地 `.env`，默认使用 mock provider、容器内 SQLite 和名为 `app_data` 的 Docker volume，适合评审者快速验证前后端能否一起启动。

## LLM Provider Boundary

- 当前支持 `LLM_PROVIDER=mock`、`LLM_PROVIDER=deepseek` 和 `LLM_PROVIDER=qianfan`；默认仍为 `mock`。
- Qianfan 只替换 LLM provider，不启用真实搜索、真实公开资料抓取、真实 embedding 或真实向量库。
- `check_compliance` 必须优先使用本地 rule-based compliance；真实模型输出后仍要经过现有合规护栏。
- `extract_facts` 使用真实 LLM 时必须返回严格 JSON；解析失败时不得把自然语言当结构化事实入库。
- 手动真实 API 连通性测试不进入默认 CI，可通过 `.\.venv\Scripts\python scripts\manual_test_qianfan.py` 在本地显式运行。

## Quality Gate

后端:

```powershell
.\scripts\verify_secrets.ps1
.\.venv\Scripts\python -m ruff check backend scripts
.\.venv\Scripts\python -m pytest backend\tests -q
```

前端:

```powershell
cd frontend
npm run typecheck
npm run build
cd ..
```

`npm run build` 已经包含 `tsc --noEmit`，因此前端构建会先经过 TypeScript 类型检查。

CI:

- `.github/workflows/ci.yml` 会在 GitHub Actions 里跑后端 `ruff + pytest`、前端 `typecheck + build`，并检查 `.env` 类文件和常见 secret 形态。
- 如果 Git 历史里曾经提交过真实 `.env`，CI 会失败；这时必须先在服务商控制台轮换 key，再清理历史后开源。

## Database Migration Boundary

当前数据库策略仍是 MVP：SQLite + SQLAlchemy `create_all`，用于本地演示、测试和 release review。

暂不引入 Alembic 的原因是当前阶段更需要稳定启动、可验证测试和清晰边界。生产化下一步应补 Alembic 迁移体系，并把 schema 变更从应用启动中剥离。
