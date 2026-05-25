"""Simple bar-chart PNG snapshots (Pillow) for dashboard pack exports."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from PIL import Image, ImageDraw


def bar_chart_png(
    rows: list[dict[str, Any]],
    *,
    title: str,
    label_key: str = "label",
    value_key: str = "value",
    max_rows: int = 14,
) -> bytes:
    slice_rows = [r for r in rows if isinstance(r, dict)][:max_rows]
    im = Image.new("RGB", (760, 420), (252, 252, 252))
    draw = ImageDraw.Draw(im)
    draw.rectangle([0, 0, 759, 419], outline=(220, 220, 220))
    draw.text((28, 16), title[:80], fill=(15, 23, 42))
    if not slice_rows:
        draw.text((28, 200), "No data", fill=(100, 116, 139))
        buf = BytesIO()
        im.save(buf, format="PNG")
        return buf.getvalue()
    mx = max(int(r.get(value_key) or 0) for r in slice_rows) or 1
    y = 52
    for r in slice_rows:
        lab = str(r.get(label_key) or "")[:48]
        v = int(r.get(value_key) or 0)
        wv = int(460 * v / mx)
        draw.text((28, y + 2), lab, fill=(30, 41, 59))
        draw.rectangle([240, y, 240 + max(2, wv), y + 20], fill=(37, 99, 235))
        draw.text((248 + wv, y + 2), str(v), fill=(51, 65, 85))
        y += 26
    buf = BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()
