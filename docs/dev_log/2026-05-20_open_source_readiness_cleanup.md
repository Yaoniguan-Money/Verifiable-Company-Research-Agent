# 2026-05-20 Open-source Readiness Cleanup

## Context

The project had reached a usable local demo state, but the codebase still needed a release-oriented pass before publishing: provider wiring had to avoid silent offline behavior, reports had to be readable, and local secrets / run artifacts had to stay out of the repository.

## Changes

- Default search posture remains online public-source discovery via `public_sources`; local documents and mock providers are explicit development paths, not the implicit company-search path.
- Optional real-provider chain is documented and validated as DeepSeek LLM, Baidu AI Search, and DashScope embedding, without treating those vendors as architecture requirements.
- Baidu AI Search reference processing now has explicit source-quality policy constants for authoritative domains, low-authority domains, business registry domains, blocked pages, and evidence keywords.
- Fact relevance logic now has explicit intent and fact-token constants for business, risk, R&D, revenue, profit, and capacity questions.
- Business registry pages are accepted as third-party background evidence when they match the target company identity, including normalized fullwidth / halfwidth punctuation.
- Report rendering was adjusted so the primary report reads like a human-facing summary instead of a raw evidence/debug dump.
- Live public-company regression cases moved from script constants to `data/eval/live_public_company_cases.example.json`; the script reads case files and does not embed company names.
- `.gitignore`, CI, and `scripts/verify_secrets.ps1` now block local/private evaluation files in addition to real `.env` files and common key patterns.
- Local `.env` was removed after validation. Local SQLite database and `node_modules` remain ignored and should not be packaged manually.

## Validation

```powershell
python -m pytest -q
python -m ruff check backend scripts
cd frontend
npm run typecheck
npm run build
cd ..
powershell -ExecutionPolicy Bypass -File scripts\verify_secrets.ps1
```

All commands passed on 2026-05-20. Pytest emitted only third-party deprecation warnings from installed dependencies.

## Release Notes

- Do not publish existing local service processes as evidence of current `.env` state. Restarting the backend after deleting `.env` will use only committed templates or shell-provided environment variables.
- If real API keys were ever pasted into chat, screenshots, logs, or external systems, rotate them before making the repository public.
- `data/dev.db` is a local development database and is intentionally ignored. If a zip archive is created manually instead of using Git, exclude it.
