"""Generate HTML polishing reports in a paragraph-by-paragraph format."""

from __future__ import annotations

import html
from typing import Dict, List


def build_html_report(results: List[Dict[str, str]]) -> bytes:
    parts: List[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="zh-CN">')
    parts.append("<head>")
    parts.append('<meta charset="utf-8" />')
    parts.append('<meta name="viewport" content="width=device-width, initial-scale=1" />')
    parts.append("<title>润色报告</title>")
    parts.append("<style>")
    parts.append(
        "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Noto Sans CJK SC','PingFang SC','Microsoft YaHei',sans-serif;"
        "line-height:1.7;max-width:980px;margin:24px auto;padding:0 18px;color:#1f2937;}"
    )
    parts.append("h1{font-size:22px;margin:28px 0 12px;color:#111827;border-bottom:1px solid #e5e7eb;padding-bottom:6px;}")
    parts.append("h2{font-size:17px;margin:18px 0 8px;color:#0f172a;}")
    parts.append("p{margin:10px 0;white-space:pre-wrap;}")
    parts.append(".meta{color:#475569;font-size:14px;}")
    parts.append("</style>")
    parts.append("</head>")
    parts.append("<body>")

    for idx, row in enumerate(results, start=1):
        parts.append(f"<h1>==========段落 {idx}============</h1>")
        parts.append("<h2>1 原文</h2>")
        parts.extend(_render_paragraphs(row.get("original", "")))
        parts.append("<h2>2 内容评价</h2>")
        parts.extend(_render_paragraphs(row.get("evaluation", "")))
        parts.append("<h2>3 首次润色</h2>")
        parts.extend(_render_paragraphs(row.get("first_polish", "")))
        parts.append("<h2>4 再次润色</h2>")
        parts.extend(_render_paragraphs(row.get("second_polish", "")))
        parts.append("<h2>5 消耗时间</h2>")
        parts.append(
            f"<p class=\"meta\">{html.escape(row.get('elapsed', '0:00:00'))}</p>"
        )

    parts.append("</body>")
    parts.append("</html>")

    return "\n".join(parts).encode("utf-8")


def _render_paragraphs(text: str) -> List[str]:
    safe = html.escape((text or "").strip())
    if not safe:
        return ["<p></p>"]

    blocks = [blk.strip() for blk in safe.split("\n\n") if blk.strip()]
    if not blocks:
        return [f"<p>{safe.replace(chr(10), '<br>')}</p>"]

    rendered: List[str] = []
    for blk in blocks:
        rendered.append(f"<p>{blk.replace(chr(10), '<br>')}</p>")
    return rendered
