# 固定评测样例

这些样例只用于链路回归，不代表系统绑定特定企业，也不构成投资分析、评级、推荐或建议。

真实公司名称仅允许出现在评测样例、fixtures 或回归脚本层。根 README、默认 API 示例、默认配置、workflow 主流程和前端默认输入不得绑定具体企业。

## 1. 评测目标

固定评测样例用于补齐“只靠单次 demo”带来的不确定性，统一检查真实链路质量信号：

- provider health 与 `mock_enabled` 状态
- source layer 与 citation 质量
- 报告合规状态
- 失败可读性

真实 API 场景存在外部波动，失败不应被伪造成成功。

## 2. 当前验收指标

真实链路验收至少检查：

- provider health 正常
- `mock_enabled=false`
- task `status=completed`
- `compliance_status=passed`
- 官方来源 citation 可见
- `low_authority` 不进入高置信 citation
- 报告不包含投资建议、买卖建议、目标价、收益承诺
- strict 模式不 fallback 到 mock

## 3. 固定真实公司样例

### sample_hk_public_company_case

- `company_name`: 某港股上市科技公司
- `stock_code`: 01XXX
- `question`: 请基于公开资料分析该公司的经营风险和公开披露一致性，要求给出引用来源，不要给投资建议。
- `status`: 已真实验收过的回归样例
- `expected`:
  - 官方来源 citation 可见
  - `compliance_status = passed`
  - 不输出投资建议

### sample_hk_public_company_case_002

- `company_name`: 某港股上市互联网公司
- `stock_code`: 00XXX
- `status`: 设计样例 / 待真实验收
- `expected`:
  - 官方来源至少 1 条
  - `compliance_status = passed`
  - 不输出投资建议

### sample_cn_public_company_case

- `company_name`: 某 A+H 股上市新能源公司
- `stock_code`: 002XXX / XXXX.HK
- `status`: 设计样例 / 待真实验收
- `expected`:
  - 官方来源至少 1 条
  - `compliance_status = passed`
  - 不输出投资建议

## 4. 真实链路波动说明

- 外部 provider 可能出现 `ReadTimeout`、`Remote end closed`、`401`、`429` 或余额不足。
- strict 模式不会 fallback 到 mock。
- 失败需要结合失败节点和错误分类排查。

## 5. 轻量回归入口

```powershell
python scripts/run_public_company_regression.py --list
python scripts/run_public_company_regression.py --case sample_hk_public_company_case
```

`--list`、`--case` 和 `--run-all-cases` 默认读取 `data/eval/live_public_company_cases.example.json`。如需本地私有样例，请传 `--live-cases-file data/eval/live_public_company_cases.local.json`；`*.local*.json` 已被 `.gitignore` 忽略。

默认不建议一次跑多个真实公司样例，避免成本和外部 API 波动扩大。

## 6. 后续升级计划

- 增加更多固定行业样例
- 固定 `source_layer_counts` 的期望区间
- 增加报告文本合规扫描覆盖
- 增加 provider 调用耗时统计
- 增加成本记录与对比
