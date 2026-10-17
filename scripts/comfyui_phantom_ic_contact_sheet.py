#!/usr/bin/env python3
"""
Build a self-contained HTML contact sheet with base64-embedded images.

Used by the Phantom identity/context validation workstream so that reference
images and generated frames can be inspected in the Preview tab even though the
preview server only serves the single registered .html file (sibling assets are
not reachable, and parent-relative paths are not served at all).

This is experiment tooling only. It reads images and writes one HTML file.

Usage:
  python3 scripts/comfyui_phantom_ic_contact_sheet.py --spec spec.json --out sheet.html

Spec format:
  {
    "title": "sheet title",
    "columns": 3,
    "thumb_width": 420,
    "groups": [
      {"heading": "Arm A",
       "items": [{"path": "a/f1.png", "caption": "frame 1"}, ...]}
    ]
  }
"""

import argparse
import base64
import html
import io
import json
from pathlib import Path

from PIL import Image


def thumb_data_uri(path: Path, width: int, quality: int = 82) -> tuple[str, str]:
    """Return (data_uri, dims_text). Downscales to `width` px wide."""
    with Image.open(path) as im:
        im = im.convert("RGB")
        w, h = im.size
        if w > width:
            im = im.resize((width, max(1, round(h * width / w))), Image.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=quality)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{b64}", f"{w}x{h}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    spec_path = Path(args.spec)
    spec = json.loads(spec_path.read_text())
    base = spec_path.parent
    cols = int(spec.get("columns", 3))
    tw = int(spec.get("thumb_width", 420))

    parts = [
        "<!doctype html><html><head><meta charset='utf-8'>",
        f"<title>{html.escape(spec.get('title', 'contact sheet'))}</title>",
        "<style>",
        "body{background:#0e0e10;color:#e8e8e8;font:13px/1.35 -apple-system,BlinkMacSystemFont,sans-serif;margin:14px}",
        "h1{font-size:17px;margin:0 0 4px}",
        ".meta{color:#8b93a1;font-size:12px;margin-bottom:12px}",
        f".grid{{display:grid;grid-template-columns:repeat({cols},minmax(0,1fr));gap:10px}}",
        "h2{font-size:14px;color:#7fd7c4;margin:18px 0 6px;border-bottom:1px solid #2a2f36;padding-bottom:4px}",
        "figure{margin:0;background:#17181c;border:1px solid #2a2f36;border-radius:6px;overflow:hidden}",
        "img{width:100%;display:block;background:#000}",
        "figcaption{padding:5px 7px;font-size:11px;color:#c8ccd4;word-break:break-word}",
        ".dims{color:#6c7480;font-weight:400}",
        "</style></head><body>",
        f"<h1>{html.escape(spec.get('title', 'contact sheet'))}</h1>",
        f"<div class='meta'>{html.escape(spec.get('meta', ''))}</div>",
    ]

    for group in spec.get("groups", []):
        if group.get("heading"):
            parts.append(f"<h2>{html.escape(group['heading'])}</h2>")
        parts.append("<div class='grid'>")
        for item in group["items"]:
            p = (base / item["path"]).resolve()
            if not p.exists():
                parts.append(
                    f"<figure><figcaption>MISSING: {html.escape(item['path'])}</figcaption></figure>"
                )
                continue
            uri, dims = thumb_data_uri(p, tw)
            cap = html.escape(item.get("caption", p.name))
            parts.append(
                f"<figure><img src='{uri}'><figcaption>{cap} "
                f"<span class='dims'>({dims})</span></figcaption></figure>"
            )
        parts.append("</div>")

    parts.append("</body></html>")
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(parts))
    kb = out.stat().st_size / 1024
    print(f"wrote {out} ({kb:.0f} KiB)")


if __name__ == "__main__":
    main()
