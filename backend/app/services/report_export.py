"""报告导出：Markdown 直出 / PDF（基于 WeasyPrint，可选依赖）。"""

from __future__ import annotations

from html import escape


def export_markdown(*, title: str, content: str) -> str:
    """直接拼接 ``# title`` + 原 content，便于前端按 ``.md`` 下载。"""
    return f"# {title}\n\n{content}\n"


def export_pdf_bytes(*, title: str, content: str) -> bytes:
    """用 WeasyPrint 渲染为 PDF。

    - 标题与正文都做 HTML 转义，避免报告中 HTML 片段被错误解析。
    - 当前未引入 Markdown→HTML 转换，正文以 ``<pre>`` 保留原样排版。
    """
    try:
        from weasyprint import HTML  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError("PDF 导出需要 weasyprint: pip install weasyprint") from exc

    safe_title = escape(title)
    safe_body = escape(content)
    html = (
        f"<html><head><meta charset='utf-8'><title>{safe_title}</title></head>"
        f"<body><pre>{safe_body}</pre></body></html>"
    )
    return HTML(string=html).write_pdf()
