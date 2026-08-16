"""Dependency-free chart rendering: pure-Python SVG (no matplotlib/numpy needed).

Produces standalone .svg files you can open in a browser, drop into slides, or
export to PNG. Two chart types cover the SCCUR asks:

  - grouped_bar_svg : first-pass vs post-loop validity across conditions/models
  - stacked_bar_svg : the six failure codes stacked per condition/model

Also writes a small combined HTML report embedding the SVGs + a data table.
"""
from __future__ import annotations

import html

# A colour-blind-safe categorical palette (Okabe-Ito).
PALETTE = ["#0072B2", "#E69F00", "#009E73", "#D55E00", "#CC79A7", "#56B4E9",
           "#F0E442", "#999999"]

_W, _H = 720, 420
_PAD_L, _PAD_R, _PAD_T, _PAD_B = 60, 20, 50, 90


def _text(x: float, y: float, s: str, size: int = 13, anchor: str = "middle",
          weight: str = "normal", fill: str = "#111827", rotate: float = 0.0) -> str:
    tf = f' transform="rotate({rotate} {x} {y})"' if rotate else ""
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{size}" text-anchor="{anchor}" '
            f'font-family="system-ui,Arial,sans-serif" font-weight="{weight}" '
            f'fill="{fill}"{tf}>{html.escape(s)}</text>')


def _axes(title: str, ymax: float, y_label: str) -> tuple[list[str], float, float, float, float]:
    x0, x1 = _PAD_L, _W - _PAD_R
    y0, y1 = _H - _PAD_B, _PAD_T
    parts = [f'<rect width="{_W}" height="{_H}" fill="#ffffff"/>',
             _text(_W / 2, 26, title, size=16, weight="700")]
    # Horizontal gridlines + y ticks (0..ymax in 5 steps).
    for i in range(6):
        frac = i / 5
        y = y0 + (y1 - y0) * frac
        val = ymax * frac
        parts.append(f'<line x1="{x0}" y1="{y:.1f}" x2="{x1}" y2="{y:.1f}" '
                     f'stroke="#e5e7eb" stroke-width="1"/>')
        label = f"{val:.0%}" if ymax <= 1.0 else f"{val:.0f}"
        parts.append(_text(x0 - 8, y + 4, label, size=11, anchor="end", fill="#6b7280"))
    parts.append(_text(16, _H / 2, y_label, size=12, anchor="middle", fill="#6b7280", rotate=-90))
    return parts, x0, x1, y0, y1


def _legend(names: list[str], y: float) -> list[str]:
    parts, x = [], _PAD_L
    for i, name in enumerate(names):
        c = PALETTE[i % len(PALETTE)]
        parts.append(f'<rect x="{x}" y="{y - 10}" width="12" height="12" fill="{c}" rx="2"/>')
        parts.append(_text(x + 18, y, name, size=12, anchor="start"))
        x += 20 + 8.2 * len(name) + 24
    return parts


def grouped_bar_svg(title: str, categories: list[str], series: dict[str, list[float]],
                    ymax: float = 1.0, y_label: str = "validity") -> str:
    parts, x0, x1, y0, y1 = _axes(title, ymax, y_label)
    n_cat, n_ser = len(categories), len(series)
    group_w = (x1 - x0) / max(1, n_cat)
    bar_w = group_w * 0.8 / max(1, n_ser)
    for ci, cat in enumerate(categories):
        gx = x0 + group_w * ci + group_w * 0.1
        for si, (name, vals) in enumerate(series.items()):
            v = vals[ci] if ci < len(vals) else 0.0
            h = (y0 - y1) * (v / ymax if ymax else 0)
            bx = gx + bar_w * si
            parts.append(f'<rect x="{bx:.1f}" y="{y0 - h:.1f}" width="{bar_w - 2:.1f}" '
                         f'height="{h:.1f}" fill="{PALETTE[si % len(PALETTE)]}" rx="2"/>')
            vlabel = f"{v:.0%}" if ymax <= 1.0 else f"{v:.2f}"
            parts.append(_text(bx + bar_w / 2, y0 - h - 5, vlabel, size=10, fill="#374151"))
        parts.append(_text(gx + group_w * 0.4, y0 + 16, cat, size=11, fill="#374151"))
    parts += _legend(list(series.keys()), _H - 28)
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_W} {_H}">{"".join(parts)}</svg>'


def stacked_bar_svg(title: str, categories: list[str], segments: dict[str, list[float]],
                    y_label: str = "rejected attempts") -> str:
    totals = [sum(segments[k][i] for k in segments) for i in range(len(categories))]
    ymax = max(totals) or 1
    parts, x0, x1, y0, y1 = _axes(title, ymax, y_label)
    group_w = (x1 - x0) / max(1, len(categories))
    bar_w = group_w * 0.6
    seg_names = list(segments.keys())
    for ci, cat in enumerate(categories):
        bx = x0 + group_w * ci + (group_w - bar_w) / 2
        acc = 0.0
        for si, name in enumerate(seg_names):
            v = segments[name][ci] if ci < len(segments[name]) else 0
            if v <= 0:
                continue
            h = (y0 - y1) * (v / ymax)
            parts.append(f'<rect x="{bx:.1f}" y="{y0 - acc - h:.1f}" width="{bar_w:.1f}" '
                         f'height="{h:.1f}" fill="{PALETTE[si % len(PALETTE)]}"/>')
            acc += h
        parts.append(_text(bx + bar_w / 2, y0 + 16, cat, size=11, fill="#374151"))
        if totals[ci]:
            parts.append(_text(bx + bar_w / 2, y0 - acc - 6, f"{int(totals[ci])}", size=10, fill="#374151"))
    parts += _legend(seg_names, _H - 28)
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_W} {_H}">{"".join(parts)}</svg>'


def html_report(title: str, intro: str, svgs: list[str], table_html: str) -> str:
    body = "".join(f'<div class="chart">{s}</div>' for s in svgs)
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>{html.escape(title)}</title><style>
body{{font-family:system-ui,Arial,sans-serif;max-width:860px;margin:32px auto;padding:0 16px;color:#111827}}
.chart{{margin:24px 0;border:1px solid #e5e7eb;border-radius:10px;padding:8px}}
table{{border-collapse:collapse;width:100%;font-size:14px;margin-top:8px}}
th,td{{border:1px solid #e5e7eb;padding:6px 10px;text-align:left}}
th{{background:#f8fafc}} .note{{color:#6b7280;font-size:13px}}
</style></head><body><h1>{html.escape(title)}</h1><p class="note">{intro}</p>
{body}<h2>Data</h2>{table_html}</body></html>"""


def table_html(headers: list[str], rows: list[list]) -> str:
    head = "".join(f"<th>{html.escape(str(h))}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in r) + "</tr>"
                   for r in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"
