"""Verifiable Company Research Agent backend package.

本项目是开源 MVP / reference implementation：
- 输入：企业名称 + 研究问题
- 流程：检索公开资料 → 抽取事实 → 交叉验证 → 生成带 citation 的研究报告
- 红线：禁止输出买卖建议、目标价、收益承诺、个股推荐等内容
"""

__version__ = "3.0"
