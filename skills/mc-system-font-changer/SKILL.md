---
name: mc-system-font-changer
description: >-
  Discovers installed system fonts (.ttf and .otf) across Linux, Windows, and
  macOS, builds a native Vanilla TrueType font resourcepack from the user's
  chosen font, enables it in options.txt, and optionally removes heavy UI font
  mods like ModernUI.
---

# Minecraft System Font Changer (`mc-system-font-changer`)

## Overview
Heavy UI mods such as `ModernUI` (`24 MB`) add 30 to 60 seconds of boot overhead scanning thousands of emoji shortcodes and initializing custom text layout engines. Vanilla Minecraft 1.20+ natively supports `.ttf` and `.otf` fonts via the `"type": "ttf"` font provider in resourcepacks. This sub-skill locates any system font on Linux, Windows, or macOS, packages it into a native Vanilla resourcepack, enables it in `options.txt`, and optionally removes `ModernUI`.

## Dependencies
- **`uv`**: Required to run `scripts/mc_optimizer.py` (relative to this skill's base directory) via `uv run`.

## Quick Start
```bash
# 1. Search installed system fonts matching a query (e.g., "SUSE")
uv run scripts/mc_optimizer.py change-font \
  --list-fonts \
  --query "SUSE" \
  --limit 25 \
  --output /tmp/mc_fonts.json

# 2. Build and enable a native TTF font resourcepack and remove ModernUI
uv run scripts/mc_optimizer.py change-font \
  --instance "/path/to/instance" \
  --font-path "/usr/share/fonts/TTF/SUSE-SemiBold.ttf" \
  --font-size 11.0 \
  --oversample 4.0 \
  --remove-modernui \
  --apply \
  --output /tmp/mc_font_applied.json
```

## Utility Scripts
### `change-font`
- `--list-fonts` (flag): Searches system font directories (`/usr/share/fonts`, `/usr/local/share/fonts`, `~/.local/share/fonts`, `C:\Windows\Fonts`, `/Library/Fonts`) and outputs matching `.ttf`/`.otf` files.
- `--query <str>` (optional): Case-insensitive substring to filter font names.
- `--instance <dir>` (optional when listing; required when building a pack): Target Minecraft instance path.
- `--font-path <path>` (optional): Explicit path to the `.ttf` or `.otf` font file.
- `--font-size <float>` (default `11.0`): Point size in `assets/minecraft/font/default.json`.
- `--oversample <float>` (default `4.0`): Oversampling resolution for crisp glyph rendering.
- `--remove-modernui` (flag): Removes `ModernUI*.jar` from `minecraft/mods/` when `--apply` is set.
- `--limit <int>` (default `50`): Maximum fonts to return when listing.
- `--apply` (flag): Writes the `.zip` resourcepack, updates `options.txt`, and removes `ModernUI` if requested.
- `--output <file>` (required): Output JSON path.

## Common Mistakes
- **Using variable font collections (`.ttc`) with Vanilla TTF provider**: Minecraft's built-in STB TrueType loader requires a single-face `.ttf` or `.otf` file (such as `SUSE-SemiBold.ttf`) rather than a multi-face `.ttc` collection.
