---
name: mc-texture-downscaler
description: >-
  Scans unpacked content packs (such as tacz/ and resourcepacks/) and mod JAR
  files for oversized 2K, 4K, and 8K PNG textures, and proportionally downscales
  2D item/block icons and 3D model UV textures for low-end GPUs and RAM.
---

# Minecraft Texture Downscaler (`mc-texture-downscaler`)

## Overview
Many third-party gunpacks and mods bundle 2048x2048 to 8192x8192 PNG textures, inflating the main block/item `TextureAtlas` to `16384x8192` and consuming tens of gigabytes of uncompressed RGBA memory during startup. This sub-skill proportionally downscales static 2D item/block sprites ($\le 128\text{px}$) and 3D model UV textures ($\le 512\text{px}$) while skipping signed JARs and animated `.png.mcmeta` sprites.

## Dependencies
- **`uv`**: Required to run `scripts/mc_optimizer.py` (relative to this skill's base directory) with Pillow (`uv run --with pillow`).

## Quick Start
```bash
# 1. Dry-run analysis to calculate exact uncompressed RGBA savings
uv run --with pillow scripts/mc_optimizer.py downscale-textures \
  --instance "/path/to/instance" \
  --max-item-size 128 \
  --max-model-size 512 \
  --output /tmp/mc_tex_dryrun.json

# 2. Apply texture downscaling in place
uv run --with pillow scripts/mc_optimizer.py downscale-textures \
  --instance "/path/to/instance" \
  --max-item-size 128 \
  --max-model-size 512 \
  --apply \
  --output /tmp/mc_tex_applied.json
```

## Utility Scripts
### `downscale-textures`
- `--instance <dir>` (required): Path to the Minecraft instance directory.
- `--max-item-size <int>` (default `128`): Maximum width/height for 2D sprites under `/textures/item/` and `/textures/block/`.
- `--max-model-size <int>` (default `512`): Maximum width/height for 3D model UV textures under `/textures/gun/`, `/textures/attachment/`, `/textures/entity/`, etc.
- `--apply` (flag): Kills any running Minecraft process for the instance and resizes textures in place using atomic temporary files.
- `--output <file>` (required): Output JSON path.

## Common Mistakes
- **Modifying signed JARs**: Never touch JARs containing `META-INF/*.SF` or `*.RSA`; the script skips them automatically to prevent `SecurityException` crashes.
- **Resizing animated sprite strips**: Textures with a `.png.mcmeta` file rely on exact frame aspect ratios and are skipped automatically.
