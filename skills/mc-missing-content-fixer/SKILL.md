---
name: mc-missing-content-fixer
description: >-
  Repairs missing-content errors in unpacked gunpacks and mod configs that stall
  Minecraft startup, including malformed language JSON files, invalid empty
  PassThroughBlocks tags in tacz-common.toml, missing tacz:renew ADS presets,
  broken minecraft:tick function tags, and unsupported tacz:nbt recipes.
---

# Minecraft Missing Content Fixer (`mc-missing-content-fixer`)

## Overview
Third-party unpacked gunpacks in `minecraft/tacz/` frequently contain syntax errors in `lang/*.json`, legacy `tacz:renew` ADS preset references, missing `minecraft:tick` datapack functions, or unsupported `tacz:nbt` crafting recipe ingredients. During startup and datapack reload, Forge and TaCZ log hundreds of exceptions and stack traces for these files. This sub-skill detects and repairs those descriptors automatically.

## Dependencies
- **`uv`**: Required to run `scripts/mc_optimizer.py` (relative to this skill's base directory) via `uv run`.

## Quick Start
```bash
# 1. Dry-run scan for missing-content and syntax errors in configs and packs
uv run scripts/mc_optimizer.py fix-missing-content \
  --instance "/path/to/instance" \
  --output /tmp/mc_missing_content_dryrun.json

# 2. Apply repairs to suppress boot exceptions
uv run scripts/mc_optimizer.py fix-missing-content \
  --instance "/path/to/instance" \
  --apply \
  --output /tmp/mc_missing_content_fixed.json
```

## Utility Scripts
### `fix-missing-content`
- `--instance <dir>` (required): Path to the Minecraft instance directory.
- `--apply` (flag): Writes repaired JSON and TOML files to disk and disables incompatible `tacz:nbt` recipe JSONs.
- `--output <file>` (required): Output JSON path.

## Common Mistakes
- **Deleting an entire gunpack because of one malformed `en_us.json` file**: `fix-missing-content` repairs or sanitizes the broken JSON file in place so the gunpack's weapons remain usable.
