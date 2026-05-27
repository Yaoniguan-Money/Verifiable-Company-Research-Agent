"""报告图表辅助：将关键指标趋势渲染为 base64 PNG，内嵌到 Markdown 报告中。

设计取舍
--------
- ``matplotlib`` 是**可选依赖**：未安装时 ``build_trend_chart_base64`` 返回 ``None``，
  ``append_charts_section`` 直接透传原文本，工作流不会因为缺图表而失败。
- 轴标题中文常因 Matplotlib 默认字体缺失而触发 UserWarning，统一用 ASCII fallback；
  真正的中文标题留在 Markdown 图注里展示，不影响用户阅读。
"""

from __future__ import annotations

import base64
import io
import warnings

_CHART_FIGSIZE = (6, 3)
_CHART_DPI = 120
_ASCII_AXIS_FALLBACK = "Metrics trend"


def _chart_axis_title(title: str) -> str:
    """非 ASCII 标题回退到 ``Metrics trend``，避开缺字体 UserWarning。"""
    return title if title.isascii() else _ASCII_AXIS_FALLBACK


def build_trend_chart_base64(
    *, labels: list[str], values: list[float], title: str
) -> str | None:
    """渲染单条折线趋势图，返回 ``data:image/png;base64,...`` 字符串。

    输入为空或长度不匹配时返回 ``None``，由上层决定是否插入图表段落。
    """
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt  # noqa: PLC0415 — Agg 后端必须在 import 前设定。
    except ImportError:
        return None

    if not labels or not values or len(labels) != len(values):
        return None

    fig, ax = plt.subplots(figsize=_CHART_FIGSIZE)
    ax.plot(labels, values, marker="o")
    ax.set_title(_chart_axis_title(title))
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    buffer = io.BytesIO()
    with warnings.catch_warnings():
        # 屏蔽 Matplotlib 字形缺失的 UserWarning，避免污染日志。
        warnings.simplefilter("ignore", UserWarning)
        fig.savefig(buffer, format="png", dpi=_CHART_DPI)
    plt.close(fig)

    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def append_charts_section(
    content: str, *, labels: list[str], values: list[float], title: str
) -> str:
    """在 Markdown 报告末尾追加趋势图章节；无图时原样返回。"""
    chart = build_trend_chart_base64(labels=labels, values=values, title=title)
    if chart is None:
        return content
    return content + f"\n\n## 数据趋势图\n\n![{title}]({chart})\n"
