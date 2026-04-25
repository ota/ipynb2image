# ipynb2image

Convert each code cell of a Jupyter notebook into a separate Jupyter Lab-styled PNG image.

## Features

- One image per code cell (code + output as a set)
- Jupyter Lab-like styling with syntax highlighting
- Light and dark themes
- High-resolution output (2x by default)
- Auto-trims right-side whitespace
- Skips empty cells and markdown cells
- Japanese font support (Noto Sans JP)

## Requirements

- Python 3.12+
- [uv](https://github.com/astral-sh/uv)

## Installation

```bash
git clone https://github.com/ota/ipynb2image
cd ipynb2image
uv sync
uv run playwright install chromium
```

## Usage

```bash
uv run main.py notebook.ipynb
```

Output images are saved to `output/` as `<notebook stem>_001.png`, `_002.png`, ...

### Options

| Option | Default | Description |
|--------|---------|-------------|
| `-o`, `--output-dir` | `output/` | Output directory |
| `--width` | `1100` | Viewport width in CSS pixels |
| `--scale` | `2` | Device pixel ratio (`1`, `2`, `3`) |
| `--theme` | `light` | Color theme (`light`, `dark`) |

### Examples

```bash
# Dark theme at 3x resolution
uv run main.py notebook.ipynb --theme dark --scale 3

# Custom output directory
uv run main.py notebook.ipynb -o /path/to/output
```

## Output example

| Light | Dark |
|-------|------|
| ![light](https://github.com/ota/ipynb2image/assets/light.png) | ![dark](https://github.com/ota/ipynb2image/assets/dark.png) |
