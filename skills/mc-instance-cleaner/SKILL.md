---
name: mc-instance-cleaner
description: >-
  Terminates active Minecraft JVM processes for a target instance and shreds
  approved world saves, old gunpack backups (tacz_backup, tacz_legacy_backup),
  tacz_default_gun (for fresh regeneration), crash reports, and archived logs.
---

# Minecraft Instance Cleaner (`mc-instance-cleaner`)

## Overview
Frees disk space and resets cached default gunpacks in a Prism/Fjord instance by terminating any running Minecraft process for that instance and deleting user-approved saves, backup folders, `tacz/tacz_default_gun`, crash reports, and compressed log archives (`logs/*.log.gz`).

## Dependencies
- **`uv`**: Required to run `scripts/mc_optimizer.py` (relative to this skill's base directory) via `uv run`.

## Quick Start
```bash
# 1. Dry-run check of space to be freed
uv run scripts/mc_optimizer.py cleanup-saves \
  --instance "/path/to/instance" \
  --clear-saves \
  --clear-backups \
  --reset-tacz-default \
  --clear-logs \
  --output /tmp/mc_cleanup_dryrun.json

# 2. Execute cleanup after user confirmation
uv run scripts/mc_optimizer.py cleanup-saves \
  --instance "/path/to/instance" \
  --kill-running \
  --clear-saves \
  --clear-backups \
  --reset-tacz-default \
  --clear-logs \
  --apply \
  --output /tmp/mc_cleanup_applied.json
```

## Utility Scripts
### `cleanup-saves`
- `--instance <dir>` (required): Path to the Minecraft instance directory.
- `--kill-running` (default `true`): Stops any running Minecraft Java process for the instance before deleting files.
- `--clear-saves`: Removes all world folders inside `minecraft/saves/`.
- `--clear-backups`: Removes `saves_corrupted_backup`, `tacz_backup`, `tacz_legacy_backup`, and `XaeroWaypoints_BACKUP*`.
- `--reset-tacz-default`: Removes `minecraft/tacz/tacz_default_gun` so TaCZ unpacks a fresh default gunpack on next launch.
- `--clear-logs`: Removes `logs/*.log.gz` and `crash-reports/*`.
- `--apply` (flag): Performs the deletions.
- `--output <file>` (required): Output JSON path.

## Common Mistakes
- **Deleting `saves/` without explicit user confirmation**: World saves cannot be recovered once deleted. Always verify with the user before passing `--clear-saves --apply`.
- **Resetting `tacz_default_gun` when `DefaultPackDebug = true`**: Ensure `DefaultPackDebug = false` in `tacz/tacz-pre.toml` so TaCZ regenerates `tacz_default_gun` automatically on startup.
