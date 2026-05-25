"""CSV export + dashboard pack (CSV, SVG, PNG) for batch evidence dashboard."""

from __future__ import annotations

import csv
import zipfile
from io import BytesIO, StringIO
from typing import Any
from xml.sax.saxutils import escape

from app.services.dashboard_chart_png import bar_chart_png


def batch_dashboard_to_csv(payload: dict[str, Any]) -> str:
    buf = StringIO()
    w = csv.writer(buf)
    w.writerow(["section", "label", "metric", "value", "pct"])

    ed = payload.get("evidence_dashboard") or {}
    kpis = ed.get("kpis") or {}
    w.writerow(["kpi", "interview_count", "count", kpis.get("interview_count", ""), ""])
    w.writerow(["kpi", "entity_rows", "count", kpis.get("entity_rows", ""), ""])
    w.writerow(["kpi", "evidence_quotes", "count", kpis.get("evidence_quotes", ""), ""])
    w.writerow(["kpi", "data_coverage_score", "score", kpis.get("data_coverage_score", ""), ""])

    dq = payload.get("data_quality") or {}
    for row in dq.get("gates_checklist") or []:
        if isinstance(row, dict):
            w.writerow(
                [
                    "gate",
                    row.get("id", ""),
                    "passed" if row.get("passed") else "failed",
                    row.get("current", ""),
                    row.get("threshold", ""),
                ]
            )

    for key in ("topics_pie", "problems_bar", "risks_bar"):
        for row in (payload.get(key) or []):
            if isinstance(row, dict):
                w.writerow(
                    [
                        key,
                        row.get("label", ""),
                        "mentions",
                        row.get("value", ""),
                        row.get("pct", ""),
                    ]
                )

    for row in (ed.get("pr_insight_rollups") or []):
        if isinstance(row, dict):
            w.writerow(
                [
                    "pr_insight",
                    row.get("insight_label", ""),
                    row.get("pr_signal_type", row.get("taxonomy", "")),
                    row.get("count", ""),
                    row.get("evidence_status", ""),
                ]
            )

    wpt = ed.get("word_phrase_tables") or {}
    for row in (wpt.get("words") or [])[:80]:
        if isinstance(row, dict):
            w.writerow(["word_freq", row.get("word", ""), "count", row.get("count", ""), ""])
    for row in (wpt.get("bigrams") or [])[:60]:
        if isinstance(row, dict):
            w.writerow(["bigram", row.get("phrase", ""), "count", row.get("count", ""), ""])
    for row in (wpt.get("trigrams") or [])[:40]:
        if isinstance(row, dict):
            w.writerow(["trigram", row.get("phrase", ""), "count", row.get("count", ""), ""])

    for row in (ed.get("pr_taxonomy_totals") or []):
        if isinstance(row, dict):
            w.writerow(
                [
                    "pr_taxonomy",
                    row.get("pr_signal_type", ""),
                    "count",
                    row.get("value", ""),
                    row.get("pct", ""),
                ]
            )

    for row in (ed.get("traceability") or {}).get("rows") or []:
        if isinstance(row, dict):
            w.writerow(
                [
                    "traceability",
                    row.get("insight_label", ""),
                    row.get("pr_signal_type", ""),
                    row.get("count", ""),
                    ";".join(str(x) for x in (row.get("source_ids") or [])[:12]),
                ]
            )

    return buf.getvalue()


def topics_bar_chart_svg(payload: dict[str, Any], *, kind: str = "topics", max_bars: int = 12) -> str:
    """Minimal SVG bar preview for snapshot-style export (no external deps)."""
    if kind == "pr_taxonomy":
        rows = [r for r in (payload.get("pr_taxonomy_totals") or []) if isinstance(r, dict)][:max_bars]
        title = "pr_taxonomy_totals"
        label_key = "pr_signal_type"
    else:
        key = "topics_pie" if kind == "topics" else "problems_bar" if kind == "problems" else "risks_bar"
        rows = [r for r in (payload.get(key) or []) if isinstance(r, dict)][:max_bars]
        title = key
        label_key = "label"
    if not rows:
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="120" viewBox="0 0 600 120">'
            '<text x="20" y="60" font-size="14" fill="#666">No data</text></svg>'
        )
    mx = max(int(r.get("value") or 0) for r in rows) or 1
    parts: list[str] = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="320" viewBox="0 0 640 320">',
        f'<text x="20" y="28" font-size="16" font-weight="600">{escape(title)}</text>',
    ]
    y = 50
    for r in rows:
        v = int(r.get("value") or 0)
        wv = int(400 * v / mx)
        lab = escape(str(r.get(label_key) or "")[:42])
        parts.append(f'<text x="20" y="{y + 14}" font-size="11" fill="#222">{lab}</text>')
        parts.append(
            f'<rect x="220" y="{y}" width="{wv}" height="18" rx="3" fill="#2563eb" opacity="0.85"/>'
        )
        parts.append(f'<text x="{230 + wv}" y="{y + 14}" font-size="11" fill="#444">{v}</text>')
        y += 28
    parts.append("</svg>")
    return "\n".join(parts)


def dashboard_pack_summary(payload: dict[str, Any]) -> str:
    b = payload.get("batch") or {}
    ed = payload.get("evidence_dashboard") or {}
    kp = ed.get("kpis") or {}
    lines = [
        f"Batch: {b.get('name', '')}",
        f"Sources: {b.get('source_count', '')}",
        f"Entities (filtered scope): {kp.get('entity_rows', '')}",
        f"Evidence quotes: {kp.get('evidence_quotes', '')}",
        f"Data coverage: {kp.get('data_coverage_score', '')}",
        "",
        "PR taxonomy (counts):",
    ]
    for row in (ed.get("pr_taxonomy_totals") or [])[:12]:
        if isinstance(row, dict):
            lines.append(f"  - {row.get('pr_signal_type')}: {row.get('value')}")
    return "\n".join(lines) + "\n"


def build_dashboard_pack_zip(payload: dict[str, Any]) -> bytes:
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("summary.txt", dashboard_pack_summary(payload))
        zf.writestr("dashboard.csv", batch_dashboard_to_csv(payload))
        for kind in ("topics", "problems", "risks", "pr_taxonomy"):
            zf.writestr(f"charts/{kind}.svg", topics_bar_chart_svg(payload, kind=kind))
            rows: list[dict[str, Any]]
            title = f"chart_{kind}"
            lk, vk = "label", "value"
            if kind == "pr_taxonomy":
                rows = [r for r in (payload.get("pr_taxonomy_totals") or []) if isinstance(r, dict)]
                lk = "pr_signal_type"
            else:
                key = "topics_pie" if kind == "topics" else "problems_bar" if kind == "problems" else "risks_bar"
                rows = [r for r in (payload.get(key) or []) if isinstance(r, dict)]
            zf.writestr(
                f"charts/{kind}.png",
                bar_chart_png(rows, title=title, label_key=lk, value_key=vk),
            )
    return buf.getvalue()
