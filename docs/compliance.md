# 合规边界（Compliance Guardrails）

> 本文是项目第一性约束。任何报告、对话、摘要、前端展示和文档说明都不得把本项目描述为荐股或投资建议系统。

## 1. Project Positioning

本项目是 Verifiable Company Research Agent / 可溯源企业公开信息研究智能体，用于对公开资料进行检索、抽取、验证、归纳和解释。

它不是：

- 投资建议系统
- 荐股 / 选股工具
- 量化交易策略系统
- 个性化理财顾问

## 2. Forbidden Outputs

禁止输出：

| 类别 | 示例 |
|---|---|
| 买卖建议 | 建议买入、可以加仓、应该卖出、减仓、清仓 |
| 目标价/价格预测 | 目标价 XX 元、短期会涨到、将跌至 |
| 收益承诺 | 预期收益 X%、稳赚、必涨 |
| 个性化推荐 | 适合你买、我建议你持有、这只股票适合你 |
| 投资评级 | 买入评级、强烈推荐、增持、减持 |
| 时机判断 | 现在是买入时机、应该止损 |

## 3. Allowed Outputs

允许输出：

- 公开资料事实摘要
- 经营、财务、技术、舆情、管理层、信息披露风险因素
- 多来源数据冲突提示
- 信息缺口说明
- citations 和来源清单
- 后续可关注的公开信息事项

## 4. Current Guardrail Implementation

当前合规能力是 rule-based MVP，不是生产级合规系统。

已落地点：

| 位置 | 作用 |
|---|---|
| `README.md` | 项目边界声明 |
| `.env.example` | 合规开关 |
| `app/compliance/rules.py` | 违规类别、命中结构、分流动作 |
| `MockLLMProvider.check_compliance` | 最小合规判断入口 |
| `ResearchWorkflowService._compliance_check` | report 输出层检查 |
| `ReportOutputService` | report API 读取兜底 |
| `ChatGuardrailService` / `/api/chat` | 最小 chat 追问合规链路 |
| tests | 防止明显违规输出回归 |

## 5. Report and Chat Checkpoints

### Report

workflow 生成报告后，会进入合规检查。命中违规时，系统会按策略改写或拒绝保存/输出。

### Chat

当前已有最小 `POST /api/chat`。它围绕已有 task/report 回答追问，并返回：

- `answer`
- `compliance_status`
- `violations`

违规追问（例如 “Can I buy this stock?”）会被拦截为 `blocked`，并返回拒绝投资建议的 answer。

这仍不是完整生产级聊天系统。

## 6. Standard Refusal Style

当用户要求买卖建议、目标价、个股推荐等内容时，系统应拒绝，并引导用户询问公开信息研究问题，例如：

> 我不能提供买入、卖出或个性化投资建议。但我可以基于公开资料帮你分析该公司的经营情况、风险因素和信息缺口。

实际话术由 guardrail 逻辑返回，前端只展示后端返回，不在展示层伪造合规结论。

## 7. Current Limitations

- 当前是 rule-based MVP。
- 无生产级语义合规模型。
- 无线上策略治理、灰度、审计后台。
- 不能替代法律、金融、合规专业审查。
- 不能用于投资决策。

## 8. Fixed Disclaimer

> 本报告仅基于公开资料整理生成，用于辅助信息研究，不构成任何投资建议、要约或邀请。资料来源、数据时效、口径差异均可能影响结论；在做出任何决策前，请咨询持牌专业人士并核对原始来源。
