from __future__ import annotations

from app.services.financial_table_extraction import FinancialTableExtractionService


def test_financial_table_extractor_maps_year_columns_to_metric_rows() -> None:
    """模拟年报中 2024年 / 2023年 / 2022年 横向年度指标表。"""
    result = FinancialTableExtractionService().extract(
        task_id="task_1",
        source_id="source_1",
        chunk_id="chunk_1",
        text="\n".join(
            [
                "项目 2024年 2023年 2022年",
                "研发费用 542亿元 399亿元 202亿元",
                "汽车相关产品收入 6171.48亿元 4834.53亿元 3246.91亿元",
                "乘用车产能 4,479,392辆 3,800,000辆 3,100,000辆",
            ]
        ),
    )

    facts = {(item.metric_name, item.period, item.value, item.claim) for item in result.facts}
    assert ("R&D_expenditure", "2024", "542亿元", "2024年研发费用为542亿元") in facts
    assert (
        "revenue_segment:汽车相关产品",
        "2024",
        "6171.48亿元",
        "2024年汽车相关产品分业务收入为6171.48亿元",
    ) in facts
    assert (
        "production_capacity:乘用车",
        "2024",
        "4479392辆",
        "2024年乘用车产能为4479392辆",
    ) in facts
    assert result.handled_spans


def test_financial_table_extractor_respects_allowed_years() -> None:
    result = FinancialTableExtractionService().extract(
        task_id="task_1",
        source_id="source_1",
        chunk_id="chunk_1",
        text="\n".join(
            [
                "项目 2024年 2023年 2022年",
                "研发费用 542亿元 399亿元 202亿元",
            ]
        ),
        allowed_years={2024},
    )
    periods = {item.period for item in result.facts}
    assert periods == {"2024"}


def test_financial_table_extractor_ignores_sentence_like_lines() -> None:
    """模拟 PDF 文本中夹杂的叙述句，确认表格抽取器不处理非表格披露。"""
    result = FinancialTableExtractionService().extract(
        task_id="task_1",
        source_id="source_1",
        chunk_id="chunk_1",
        text="2024年研发费用为542亿元；2023年研发费用为399亿元。",
    )

    assert result.facts == []
    assert result.handled_spans == []


def test_financial_table_extractor_uses_unit_context_for_bare_numbers() -> None:
    """模拟年报财务表格以“单位：千元”披露、指标行只给裸数字的形态。"""
    result = FinancialTableExtractionService().extract(
        task_id="task_1",
        source_id="source_1",
        chunk_id="chunk_1",
        text="\n".join(
            [
                "单位：千元",
                "项目 2024年 2023年",
                "研发费用 542000 399000",
                "汽车相关产品收入 617147559 483452607",
            ]
        ),
    )

    facts = {(item.metric_name, item.period, item.value) for item in result.facts}
    assert ("R&D_expenditure", "2024", "542000千元") in facts
    assert ("revenue_segment:汽车相关产品", "2024", "617147559千元") in facts


def test_financial_table_extractor_handles_vehicle_wide_rows() -> None:
    """模拟年报产品类别宽表：同一行披露产能、产量、销量和销售收入。"""
    result = FinancialTableExtractionService().extract(
        task_id="task_1",
        source_id="source_1",
        chunk_id="chunk_1",
        text="\n".join(
            [
                "2025年",
                "产品类别 产能状况 快报产量 快报销量 销售收入",
                "乘用车 4,479,392辆 4,479,392辆 4,545,423辆 541,917,643,000元",
            ]
        ),
    )

    facts = {(item.metric_name, item.period, item.value) for item in result.facts}
    assert ("production_capacity:乘用车", "2025", "4479392辆") in facts
    assert ("production_volume:乘用车", "2025", "4479392辆") in facts
    assert ("sales_volume:乘用车", "2025", "4545423辆") in facts
    assert ("revenue_segment:乘用车", "2025", "541917643000元") in facts


def test_financial_table_extractor_uses_yuan_unit_context_for_income_rows() -> None:
    """模拟年报分业务收入表以“单位：元”披露、金额列为裸数字的形态。"""
    result = FinancialTableExtractionService().extract(
        task_id="task_1",
        source_id="source_1",
        chunk_id="chunk_1",
        text="\n".join(
            [
                "单位：元",
                "项目 2024年 2023年",
                "营业收入 合计 409084000000 373710000000",
                "暖通空调收入 176000000000 161000000000",
            ]
        ),
    )

    facts = {(item.metric_name, item.period, item.value, item.claim) for item in result.facts}
    assert (
        "revenue",
        "2024",
        "409084000000元",
        "2024年营业收入为409084000000元",
    ) in facts
    assert (
        "revenue_segment:暖通空调",
        "2024",
        "176000000000元",
        "2024年暖通空调分业务收入为176000000000元",
    ) in facts


def test_financial_table_extractor_uses_ten_thousand_yuan_unit_context_for_rd_rows() -> None:
    """模拟年报研发费用明细表以“单位：万元”披露研发费用的形态。"""
    result = FinancialTableExtractionService().extract(
        task_id="task_1",
        source_id="source_1",
        chunk_id="chunk_1",
        text="\n".join(
            [
                "单位：万元",
                "项目 2024年 2023年 2022年",
                "研发费用 1450000 1260000 1180000",
            ]
        ),
    )

    facts = {(item.metric_name, item.period, item.value, item.claim) for item in result.facts}
    assert (
        "R&D_expenditure",
        "2024",
        "1450000万元",
        "2024年研发费用为1450000万元",
    ) in facts
    assert ("R&D_expenditure", "2023", "1260000万元", "2023年研发费用为1260000万元") in facts
    assert ("R&D_expenditure", "2022", "1180000万元", "2022年研发费用为1180000万元") in facts


def test_financial_table_extractor_uses_hundred_million_yuan_unit_context_for_revenue_rows() -> None:
    """模拟年报主营业务收入表以“单位：亿元”披露收入结构的形态。"""
    result = FinancialTableExtractionService().extract(
        task_id="task_1",
        source_id="source_1",
        chunk_id="chunk_1",
        text="\n".join(
            [
                "单位：亿元",
                "项目 2024年 2023年 2022年",
                "营业收入 合计 850.00 832.72 739.69",
                "核心产品收入 665.00 628.80 553.35",
                "系列酒产品收入 140.00 136.40 122.50",
            ]
        ),
    )

    facts = {(item.metric_name, item.period, item.value) for item in result.facts}
    assert ("revenue", "2024", "850.00亿元") in facts
    assert ("revenue_segment:核心产品", "2024", "665.00亿元") in facts
    assert ("revenue_segment:系列酒产品", "2023", "136.40亿元") in facts


def test_financial_table_extractor_maps_current_and_prior_period_amount_columns() -> None:
    """模拟利润表/研发费用表中“本期金额 / 上期金额”列并在表头标明对应年份。"""
    result = FinancialTableExtractionService().extract(
        task_id="task_1",
        source_id="source_1",
        chunk_id="chunk_1",
        text="\n".join(
            [
                "单位：万元",
                "项目 2024年本期金额 2023年上期金额",
                "研发费用 800000 750000",
                "营业收入 合计 20500000 20390000",
            ]
        ),
    )

    facts = {(item.metric_name, item.period, item.value) for item in result.facts}
    assert ("R&D_expenditure", "2024", "800000万元") in facts
    assert ("R&D_expenditure", "2023", "750000万元") in facts
    assert ("revenue", "2024", "20500000万元") in facts
    assert ("revenue", "2023", "20390000万元") in facts


def test_financial_table_extractor_maps_business_revenue_table_with_multiple_segments() -> None:
    """模拟年报分业务收入表：多业务行横向披露三年销售收入。"""
    result = FinancialTableExtractionService().extract(
        task_id="task_1",
        source_id="source_1",
        chunk_id="chunk_1",
        text="\n".join(
            [
                "项目 2024年 2023年 2022年",
                "药品事业部收入 113.00亿元 108.00亿元 101.00亿元",
                "健康品事业部收入 246.00亿元 241.00亿元 230.00亿元",
                "中药资源事业部收入 32.00亿元 42.00亿元 38.00亿元",
            ]
        ),
    )

    facts = {(item.metric_name, item.period, item.value) for item in result.facts}
    assert ("revenue_segment:药品事业部", "2024", "113.00亿元") in facts
    assert ("revenue_segment:健康品事业部", "2023", "241.00亿元") in facts
    assert ("revenue_segment:中药资源事业部", "2022", "38.00亿元") in facts


def test_financial_table_extractor_filters_tax_and_financial_income_noise() -> None:
    result = FinancialTableExtractionService().extract(
        task_id="task_1",
        source_id="source_1",
        chunk_id="chunk_1",
        text="\n".join(
            [
                "单位：元",
                "项目 2024年 2023年",
                "一、营业总收入 150560330316.45 127553959355.97",
                "增值税 商品销售收入税率 13% 13%",
                "A.公司在贵州银行的期末存款余额为 2409693.12 2300000.00",
                "本期确认利息收入 70.68 65.00",
            ]
        ),
    )

    facts = {(item.metric_name, item.period, item.value) for item in result.facts}
    assert ("revenue", "2024", "150560330316.45元") in facts
    assert all("增值税" not in item.metric_name for item in result.facts)
    assert all("银行" not in item.metric_name for item in result.facts)
    assert all(not item.value.endswith("%") for item in result.facts)


def test_financial_table_extractor_filters_accounting_line_noise_and_rd_ratios() -> None:
    result = FinancialTableExtractionService().extract(
        task_id="task_1",
        source_id="source_1",
        chunk_id="chunk_1",
        text="\n".join(
            [
                "项目 2024年 2023年",
                "其中 营业收入 40033300814.72元 39111292156.00元",
                "加 营业外收入 1165403.30元 1000000.00元",
                "研发投入占营业收入比例 1.02% 0.94%",
                "研发费用 5.12亿元 4.80亿元",
            ]
        ),
    )

    facts = {(item.metric_name, item.period, item.value) for item in result.facts}
    assert ("R&D_expenditure", "2024", "5.12亿元") in facts
    assert all("其中" not in item.metric_name for item in result.facts)
    assert all("营业外" not in item.metric_name for item in result.facts)
    assert all(not item.value.endswith("%") for item in result.facts)


def test_financial_table_extractor_parses_rd_expense_row_with_comma_in_note() -> None:
    """年报「3、费用」表中说明含顿号，研发费用行仍应被识别。"""
    result = FinancialTableExtractionService().extract(
        task_id="task_1",
        source_id="source_1",
        chunk_id="chunk_1",
        text="\n".join(
            [
                "单位：元",
                "2025 年 2024 年 同比增减 重大变动说明",
                "研发费用 57,978,105,000.00 53,194,745,000.00 8.99% 主要是折旧及摊销、检测费增加",
                "4、研发投入",
            ]
        ),
    )

    facts = {(item.metric_name, item.period, item.value) for item in result.facts}
    assert ("R&D_expenditure", "2025", "57978105000.00元") in facts
    assert ("R&D_expenditure", "2024", "53194745000.00元") in facts
    assert all(value != "4元" for _, _, value in facts)


def test_financial_table_extractor_maps_capacity_production_and_sales_volume_rows() -> None:
    """模拟年报产能 / 产量 / 销量表：产品行按年度横向披露运营指标。"""
    result = FinancialTableExtractionService().extract(
        task_id="task_1",
        source_id="source_1",
        chunk_id="chunk_1",
        text="\n".join(
            [
                "项目 2024年 2023年 2022年",
                "动力电池产能 760.00GWh 600.00GWh 450.00GWh",
                "动力电池产量 520.00GWh 390.00GWh 310.00GWh",
                "动力电池销量 500.00GWh 380.00GWh 295.00GWh",
            ]
        ),
    )

    facts = {(item.metric_name, item.period, item.value, item.claim) for item in result.facts}
    assert (
        "production_capacity:动力电池",
        "2024",
        "760.00GWh",
        "2024年动力电池产能为760.00GWh",
    ) in facts
    assert (
        "production_volume:动力电池",
        "2023",
        "390.00GWh",
        "2023年动力电池产量为390.00GWh",
    ) in facts
    assert (
        "sales_volume:动力电池",
        "2022",
        "295.00GWh",
        "2022年动力电池销量为295.00GWh",
    ) in facts


def test_financial_table_extractor_maps_net_profit_parent_row() -> None:
    """模拟年报利润表中「归属于上市公司股东的净利润」行。"""
    result = FinancialTableExtractionService().extract(
        task_id="task_1",
        source_id="source_1",
        chunk_id="chunk_1",
        text="\n".join(
            [
                "项目 2024年 2023年",
                "归属于上市公司股东的净利润 862.28亿元 747.21亿元",
                "归属于上市公司股东的扣除非经常性损益的净利润 858.00亿元 740.00亿元",
            ]
        ),
    )

    facts = {(item.metric_name, item.period, item.value, item.claim) for item in result.facts}
    assert (
        "net_profit_parent",
        "2024",
        "862.28亿元",
        "2024年归母净利润为862.28亿元",
    ) in facts
    assert (
        "net_profit_parent",
        "2023",
        "747.21亿元",
        "2023年归母净利润为747.21亿元",
    ) in facts


def test_financial_table_extractor_maps_deducted_net_profit_row() -> None:
    """模拟年报利润表中「扣除非经常性损益的净利润」行。"""
    result = FinancialTableExtractionService().extract(
        task_id="task_1",
        source_id="source_1",
        chunk_id="chunk_1",
        text="\n".join(
            [
                "项目 2024年 2023年",
                "归属于上市公司股东的扣除非经常性损益的净利润 858.00亿元 740.00亿元",
            ]
        ),
    )

    facts = {(item.metric_name, item.period, item.value, item.claim) for item in result.facts}
    assert (
        "net_profit_deducted",
        "2024",
        "858.00亿元",
        "2024年扣非净利润为858.00亿元",
    ) in facts


def test_financial_table_extractor_maps_net_profit_row() -> None:
    """模拟年报利润表中「净利润」行。"""
    result = FinancialTableExtractionService().extract(
        task_id="task_1",
        source_id="source_1",
        chunk_id="chunk_1",
        text="\n".join(
            [
                "项目 2024年 2023年",
                "净利润 862.28亿元 747.21亿元",
            ]
        ),
    )

    facts = {(item.metric_name, item.period, item.value) for item in result.facts}
    assert ("net_profit", "2024", "862.28亿元") in facts
    assert ("net_profit", "2023", "747.21亿元") in facts


def test_financial_table_extractor_profit_row_not_confused_with_revenue() -> None:
    """「净利润」行不应被「收入」规则误判为 revenue_segment。"""
    result = FinancialTableExtractionService().extract(
        task_id="task_1",
        source_id="source_1",
        chunk_id="chunk_1",
        text="\n".join(
            [
                "项目 2024年 2023年",
                "净利润 862.28亿元 747.21亿元",
                "营业收入 1741.44亿元 1505.60亿元",
            ]
        ),
    )

    metrics = {item.metric_name for item in result.facts}
    assert "net_profit" in metrics
    assert "revenue" in metrics
    # 「净利润」不应被误判为收入：
    assert all(not item.metric_name.startswith("revenue_segment:净") for item in result.facts)


def test_financial_table_extractor_maps_profit_table_with_unit_context() -> None:
    """模拟年报利润表以「单位：元」披露，金额列为裸数字的形态。"""
    result = FinancialTableExtractionService().extract(
        task_id="task_1",
        source_id="source_1",
        chunk_id="chunk_1",
        text="\n".join(
            [
                "单位：元",
                "项目 2024年 2023年",
                "归属于上市公司股东的净利润 86,228,146,421.62 74,720,924,904.14",
                "净利润 86,228,146,421.62 74,720,924,904.14",
            ]
        ),
    )

    facts = {(item.metric_name, item.period, item.value) for item in result.facts}
    assert ("net_profit_parent", "2024", "86228146421.62元") in facts
    assert ("net_profit", "2023", "74720924904.14元") in facts


def test_financial_table_extractor_filters_profit_ratio_rows() -> None:
    """利润相关百分比行（如净利率）不应被当作金额抽取。"""
    result = FinancialTableExtractionService().extract(
        task_id="task_1",
        source_id="source_1",
        chunk_id="chunk_1",
        text="\n".join(
            [
                "项目 2024年 2023年",
                "净利润 862.28亿元 747.21亿元",
                "净利率 49.5% 48.9%",
            ]
        ),
    )

    # 百分比行「净利率」不应被抽取（净利润行本身仍应正确抽取）
    assert all(not item.value.endswith("%") or "net_profit" not in (item.metric_name or "") for item in result.facts)
    assert ("net_profit", "2024", "862.28亿元") in {
        (item.metric_name, item.period, item.value) for item in result.facts
    }
