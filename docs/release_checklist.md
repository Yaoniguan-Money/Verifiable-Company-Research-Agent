# 开源发布前检查清单

## 1) 必须确认

- `.env` 未被提交，且 `git status` 不出现 `.env`。
- `.env.example` 不包含真实 key。
- secret scan 通过（如 `scripts/verify_secrets.ps1`）。
- GitHub Actions 只跑离线检查，不依赖真实 API key，不运行 `verify_real_chain.py`。
- 后端测试通过：`pytest backend/tests -q`。
- 代码风格检查通过：`ruff check backend scripts`。
- 前端构建通过：`frontend npm run build`。
- `verify_real_chain.py` 或固定回归样例（如 `--case Sample HK Public Company`）至少一次通过。
- README 明确项目是开源 MVP / reference implementation、非生产级、非投顾。
- `sample_hk_public_company_case_002` / `SAMPLE_CN_PUBLIC_COMPANY` 不写成已真实验收。
- demo 截图/GIF（如提供）不暴露 key、token、账号敏感信息。

## 2) 可选加强项

- GitHub Actions（离线测试与 lint）
- demo GIF / 截图
- issue template
- license
- contribution guide

## 3) 当前不建议在本阶段做

- 接入 Qdrant/Chroma/Milvus
- 生产级公告爬虫体系
- 多用户权限生产化
- 成本监控后台
- 大规模前端重写
