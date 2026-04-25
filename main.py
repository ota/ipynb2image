#!/usr/bin/env python3
"""ipynb2image: Convert each Jupyter notebook cell to a separate Jupyter-like image."""

import argparse
import io
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageStat


THEMES: dict[str, dict] = {
    "light": {
        "color_scheme": "light",
        "css": """
          body, .jp-Notebook { background: #f5f5f5 !important; }
        """,
        "post_css": "",
        "editor_bg": "",
        "editor_fg": "",
    },
    "dark": {
        "color_scheme": "dark",
        "css": "",  # injected post-JS via page.add_style_tag instead
        "editor_bg": "#313244",
        "editor_fg": "#cdd6f4",
        "post_css": """
          :root {
            --jp-layout-color0: #1e1e2e;
            --jp-layout-color1: #313244;
            --jp-layout-color2: #45475a;
            --jp-layout-color3: #585b70;
            --jp-content-font-color0: #cdd6f4;
            --jp-content-font-color1: #cdd6f4;
            --jp-content-font-color2: rgba(205,214,244,0.7);
            --jp-content-font-color3: rgba(205,214,244,0.5);
            --jp-code-font-color: #cdd6f4;
          }
          body, .jp-Notebook,
          .jp-Cell, .jp-Cell-inputWrapper, .jp-Cell-outputWrapper,
          .jp-OutputArea, .jp-OutputArea-child, .jp-OutputArea-output {
            background: #1e1e2e !important;
            color: #cdd6f4 !important;
          }
          .jp-CodeMirrorEditor,
          .cm-editor, .cm-scroller, .cm-content, .cm-gutters, .cm-line,
          .CodeMirror, .CodeMirror-scroll, .CodeMirror-lines, .CodeMirror-code {
            background: #313244 !important;
            color: #cdd6f4 !important;
          }
          .jp-RenderedText pre, .jp-RenderedText {
            color: #cdd6f4 !important;
          }
        """,
    },
}

CODE_FONT = "'Noto Sans Mono', 'Noto Sans JP', monospace"
BODY_FONT = "'Noto Sans JP', sans-serif"
CODE_FONT_URL = (
    "https://fonts.googleapis.com/css2?family=Noto+Sans+Mono:wght@400;700"
    "&family=Noto+Sans+JP:wght@400;700&display=swap"
)

BASE_CSS = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<style>
  @import url('{font_url}');
  body {{ margin: 0; padding: 0; }}
  .jp-Notebook {{ padding: 16px !important; }}
  .jp-Cell {{ margin-bottom: 0 !important; }}
  .jp-InputPrompt, .jp-OutputPrompt {{ display: none !important; }}
  .jp-Cell, .jp-CodeCell, .jp-Cell-inputWrapper, .jp-Cell-outputWrapper {{
    border: none !important;
    outline: none !important;
    box-shadow: none !important;
    border-radius: 0 !important;
  }}
  .highlight .nb {{
    color: var(--jp-mirror-editor-builtin-color) !important;
  }}
  .jp-CodeMirrorEditor, .highlight, .highlight pre,
  .jp-RenderedText pre {{
    font-family: {code_font} !important;
    font-size: 14px !important;
    line-height: 1.6 !important;
  }}
  .jp-OutputArea-output {{
    font-family: {body_font} !important;
    font-size: 14px !important;
    line-height: 1.6 !important;
  }}
  {theme_css}
</style>
"""

# Real text has many anti-aliased intermediate pixel values; structural artifacts
# (separators, background color boundaries) have only 2-3 distinct values per column.
STDDEV_THRESHOLD = 13.0   # skip separator(~2.4 light/~88 dark) AND empty bg borders
MIN_DISTINCT_VALUES = 5   # must have this many unique greyscale values to count as content
TRIM_PADDING_CSS_PX = 30  # px after last content column to cover anti-aliased edges


def convert_to_html(ipynb_path: Path) -> str:
    result = subprocess.run(
        [
            sys.executable, "-m", "nbconvert",
            "--to", "html",
            "--template", "lab",
            "--stdout",
            str(ipynb_path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    return result.stdout


def build_css(theme: str) -> str:
    return BASE_CSS.format(
        font_url=CODE_FONT_URL,
        code_font=CODE_FONT,
        body_font=BODY_FONT,
        theme_css=THEMES[theme]["css"],
    )


def inject_css(html: str, theme: str) -> str:
    import re
    html = re.sub(r'<html([^>]*?)lang="[^"]*"', '<html\\1lang="ja"', html, count=1)
    return html.replace("</head>", build_css(theme) + "</head>", 1)


def trim_right(img: Image.Image, scale: int) -> Image.Image | None:
    """Crop trailing right columns by finding the rightmost dense-content column.

    Returns None if no content is detected (empty cell).
    """
    gray = img.convert("L")
    w, h = gray.size
    padding = TRIM_PADDING_CSS_PX * scale

    for x in range(w - 1, -1, -1):
        col = gray.crop((x, 0, x + 1, h))
        if ImageStat.Stat(col).stddev[0] > STDDEV_THRESHOLD:
            if len(set(col.tobytes())) >= MIN_DISTINCT_VALUES:
                right = min(x + 1 + padding, w)
                return img.crop((0, 0, right, h))

    return None  # empty cell


def screenshot_cells(
    html: str, output_dir: Path, stem: str, width: int, scale: int, theme: str
) -> int:
    from playwright.sync_api import sync_playwright

    with tempfile.NamedTemporaryFile(suffix=".html", mode="w", delete=False, encoding="utf-8") as f:
        f.write(html)
        tmp_path = Path(f.name)

    count = 0
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(
                viewport={"width": width, "height": 800},
                device_scale_factor=scale,
            )
            page.emulate_media(color_scheme=THEMES[theme]["color_scheme"])
            page.goto(tmp_path.as_uri())
            page.wait_for_load_state("networkidle")
            if post_css := THEMES[theme]["post_css"]:
                page.add_style_tag(content=post_css)
                # Strip all borders/outlines that would create high-contrast right edges
                page.evaluate("""() => {
                    ['.jp-Cell', '.jp-CodeCell',
                     '.jp-Cell-inputWrapper', '.jp-Cell-outputWrapper'].forEach(sel => {
                        document.querySelectorAll(sel).forEach(el => {
                            el.style.setProperty('border', 'none', 'important');
                            el.style.setProperty('outline', 'none', 'important');
                            el.style.setProperty('box-shadow', 'none', 'important');
                        });
                    });
                }""")
                # Force inline styles so nothing (including !important sheets) can override
                page.evaluate("""([bg, fg]) => {
                    const sels = [
                        '.jp-CodeMirrorEditor', '.highlight',
                        '.cm-editor', '.cm-scroller', '.cm-content',
                        '.cm-gutters', '.cm-gutter', '.cm-line',
                        '.CodeMirror', '.CodeMirror-scroll',
                        '.CodeMirror-sizer', '.CodeMirror-lines',
                        '.CodeMirror-code', '.CodeMirror-line',
                        '.jp-Cell-inputWrapper', '.jp-Cell-outputWrapper',
                        '.jp-OutputArea-output', '.jp-RenderedText pre'
                    ];
                    sels.forEach(sel => {
                        document.querySelectorAll(sel).forEach(el => {
                            el.style.setProperty('background', bg, 'important');
                            el.style.setProperty('background-color', bg, 'important');
                            el.style.setProperty('color', fg, 'important');
                        });
                    });
                }""", [THEMES[theme]["editor_bg"], THEMES[theme]["editor_fg"]])

            cells = page.locator(".jp-CodeCell").all()
            total = len(cells)

            for i, cell in enumerate(cells, start=1):
                png_bytes = cell.screenshot()
                img = Image.open(io.BytesIO(png_bytes))
                img = trim_right(img, scale)

                if img is None:
                    print(f"  [{i}/{total}] skipped (empty cell)")
                    continue

                out_path = output_dir / f"{stem}_{count + 1:03d}.png"
                img.save(out_path)
                count += 1
                print(f"  [{i}/{total}] {out_path.name}")

            browser.close()
    finally:
        tmp_path.unlink(missing_ok=True)

    return count


def main():
    parser = argparse.ArgumentParser(
        description="Convert each Jupyter notebook cell to a separate image."
    )
    parser.add_argument("notebook", type=Path, help="Input .ipynb file")
    parser.add_argument(
        "-o", "--output-dir", type=Path, default=None,
        help="Output directory (default: output/)",
    )
    parser.add_argument(
        "--width", type=int, default=1100,
        help="Viewport width in CSS pixels (default: 1100)",
    )
    parser.add_argument(
        "--scale", type=int, default=3, choices=[1, 2, 3],
        help="Device pixel ratio for image sharpness (default: 3)",
    )
    parser.add_argument(
        "--theme", default="light", choices=list(THEMES),
        help="Color theme (default: light)",
    )
    args = parser.parse_args()

    if not args.notebook.exists():
        print(f"Error: {args.notebook} not found", file=sys.stderr)
        sys.exit(1)

    stem = args.notebook.stem
    output_dir = args.output_dir or args.notebook.parent / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Converting {args.notebook} → {output_dir}/  [theme={args.theme}, scale={args.scale}x]")
    html = convert_to_html(args.notebook)
    html = inject_css(html, args.theme)

    count = screenshot_cells(html, output_dir, stem, args.width, args.scale, args.theme)
    print(f"Done: {count} images saved to {output_dir}/")


if __name__ == "__main__":
    main()
