---
name: mc-corrupted-saves-cleaner
description: >-
  Scans Minecraft saves/ and saves_corrupted_backup/ directories to detect
  corrupted worlds (missing or zero-byte level.dat, invalid gzip headers, or
  zero-byte .mca region files) and removes them safely.
---

# Minecraft Corrupted Saves Cleaner (`mc-corrupted-saves-cleaner`)

## Overview
Inspects every world folder in `minecraft/saves/` to verify that `level.dat` (or `level.dat_old`) exists, is non-empty, and has a valid gzip stream header, and checks `region/*.mca` files for 0-byte truncation caused by hard crashes or kernel OOM shutdowns.

## Dependencies
- **`uv`**: Required to run `scripts/mc_optimizer.py` (relative to this skill's base directory) via `uv run`.

## Quick Start
```bash
# 1. Scan for corrupted worlds without deleting anything
uv run scripts/mc_optimizer.py check-corrupted-saves \
  --instance "/path/to/instance" \
  --output /tmp/mc_corrupted_saves.json

# 2. Remove detected corrupted worlds and saves_corrupted_backup/
uv run scripts/mc_optimizer.py check-corrupted-saves \
  --instance "/path/to/instance" \
  --apply \
  --output /tmp/mc_corrupted_saves_removed.json
```

## Utility Scripts
### `check-corrupted-saves`
- `--instance <dir>` (required): Path to the Minecraft instance directory.
- `--apply` (flag): Terminates any running Minecraft process for the instance and deletes only the world directories flagged as corrupted (plus `saves_corrupted_backup/`).
- `--output <file>` (required): Output JSON path.

## Common Mistakes
- **Deleting healthy worlds when only corrupted ones should be removed**: Use `check-corrupted-saves` to target only broken saves; use `cleanup-saves --clear-saves` only when the user wants to wipe all worlds.
