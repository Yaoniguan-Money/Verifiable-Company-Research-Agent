# 2026-05-07 Open-source Generalization Refactor

## Context

The public release package had to stand on its own as a clean open-source repository. It could not depend on private Git history, presentation context, local `.env` files, local databases, build output, or personal development notes.

## Key Decisions

- Public name standardized to `Verifiable Company Research Agent` / `可溯源企业公开信息研究智能体`.
- Local default route stays offline: `mock + local_documents + local_hashing`.
- DeepSeek, Baidu AI Search, DashScope, Qianfan, and SiliconFlow are documented only as optional provider examples.
- LangGraph is described as the default workflow engine, not as the project name or an architectural lock-in.
- Real-company samples are limited to regression material: `data/eval/*`, `docs/evaluation_cases.md`, and `scripts/run_public_company_regression.py`.

## Errors Found And Fixed

- Documentation mixed local defaults with real-provider smoke settings. Fixed by separating `.env.example` from `.env.providers.example`.
- Earlier secret scanning allowed only `.env.example`; it now also permits the blank `.env.providers.example` template.
- Clean SQLite workflow tests exposed a stale session-factory reference that local state could hide. The test path now uses the reset session factory after engine reset.
- New-user startup docs were too cross-referenced. The detailed paths were moved into `docs/windows_quickstart.md`, `docs/testing_guide.md`, and `docs/demo_walkthrough.md`.

## Review Reminders

- Never commit `.env`, `.venv`, `node_modules`, `frontend/dist`, SQLite databases, caches, logs, or screenshots with secrets/private paths.
- Restart the backend after changing `.env`; PowerShell environment variables can override `.env` within the current terminal.
- `DEEPSEEK_MODEL=deepseek-chat` is the recommended real-chain smoke model.
- `BAIDU_AI_SEARCH_MODEL` must be enabled for the user's own account.
- Weak external search results should produce insufficient-evidence behavior rather than a forced conclusion.
- `local_documents` can only answer from imported files; it is not a live company search provider.
- `scripts/verify_real_chain.py` accepts `--base-url` / `VERIFY_BASE_URL`; keep script defaults simple and avoid hardcoded-port workarounds in docs.

## Validation Commands

```powershell
python -m pytest backend/tests -q
python -m ruff check backend scripts
cd frontend
npm run build
cd ..
powershell -ExecutionPolicy Bypass -File scripts\verify_secrets.ps1
```
