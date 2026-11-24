---
name: mc-boot-analyzer
description: >-
  Auto-discovers Minecraft instances across Prism Launcher, Fjord Launcher,
  MultiMC, and PollyMC on Linux, Linux Flatpak, Windows, and macOS, and parses
  latest.log and debug.log timestamp gaps to identify boot bottlenecks.
---

# Minecraft Boot Analyzer (`mc-boot-analyzer`)

## Overview
Locates Prism-based launcher instances across native and Flatpak directories on Linux, Windows, and macOS, reads `instance.cfg` and `mmc-pack.json`, and analyzes timestamp gaps in `latest.log` and `debug.log` to identify what is slowing down game startup.

## Dependencies
- **`uv`**: Required to run `scripts/mc_optimizer.py` (relative to this skill's base directory) via `uv run`.

## Quick Start
```bash
# 1. Discover instances
uv run scripts/mc_optimizer.py discover \
  --limit 20 --output /tmp/mc_discovered.json

# 2. Analyze boot timestamp gaps >= 3 seconds
uv run scripts/mc_optimizer.py analyze-boot \
  --instance "/path/to/instance" \
  --min-gap-seconds 3.0 \
  --limit 30 \
  --output /tmp/mc_boot_analysis.json
```

## Utility Scripts
### `discover`
- `--custom-path <dir>` (optional): Custom instance or instances root folder.
- `--limit <int>` (required): Maximum number of instances to return.
- `--output <file>` (required): Output JSON path.

### `analyze-boot`
- `--instance <dir>` (required): Target instance directory.
- `--min-gap-seconds <float>` (default `3.0`): Minimum duration between consecutive log lines to flag as a stall.
- `--limit <int>` (required): Maximum number of top timestamp gaps to return.
- `--output <file>` (required): Output JSON path.

## Common Mistakes
- **Only checking `latest.log`**: Some Mixin,ModernFix, and background thread stalls only appear in `debug.log`. The `analyze-boot` command parses both files automatically.
- **Confusing GC swap pauses with mod freezes**: A multi-minute pause right before the title screen (after resource reload listeners finish) is usually G1GC scanning swapped-out heap pages rather than a deadlocked mod.
