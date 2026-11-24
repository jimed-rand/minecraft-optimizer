---
name: mc-mod-auditor
description: >-
  Audits Minecraft mods across Forge, NeoForge, Fabric, Quilt, and LiteLoader.
  Extracts mod IDs, texture counts, Jar-in-Jar libraries, and dependency graphs,
  verifies zero unmet dependencies before removal, and deletes approved mods.
---

# Minecraft Mod Auditor (`mc-mod-auditor`)

## Overview
Scans all `.jar` and `.jar.disabled` files in an instance's `mods/` folder across all mod loaders supported by Prism-based launchers (`Forge`, `NeoForge`, `Fabric`, `Quilt`, `LiteLoader`). Maps required and optional dependencies (including nested Jar-in-Jar libraries) so heavy or unwanted mods can be removed without breaking remaining mods.

## Dependencies
- **`uv`**: Required to run `scripts/mc_optimizer.py` (relative to this skill's base directory) via `uv run`.

## Quick Start
```bash
# 1. Audit all mods and inspect sizes, textures, and dependencies
uv run scripts/mc_optimizer.py audit-mods \
  --instance "/path/to/instance" \
  --limit 250 \
  --output /tmp/mc_mods_audit.json

# 2. Dry-run verify removing specific mods leaves 0 broken dependencies
uv run scripts/mc_optimizer.py audit-mods \
  --instance "/path/to/instance" \
  --limit 250 \
  --delete-list "music_player-forge-1.20.1-2.7.4.393.jar,u_team_core-forge-1.20.1-5.1.4.382.jar" \
  --output /tmp/mc_mods_dryrun.json

# 3. Apply removal after user approval (automatically kills running Minecraft first)
uv run scripts/mc_optimizer.py audit-mods \
  --instance "/path/to/instance" \
  --limit 250 \
  --delete-list "music_player-forge-1.20.1-2.7.4.393.jar,u_team_core-forge-1.20.1-5.1.4.382.jar" \
  --apply \
  --output /tmp/mc_mods_removed.json
```

## Utility Scripts
### `audit-mods`
- `--instance <dir>` (required): Path to the Minecraft instance directory.
- `--limit <int>` (required): Maximum number of mods to include in the JSON output.
- `--delete-list <csv>` (optional): Comma-separated filenames or mod IDs to test/delete.
- `--apply` (flag): Terminates any running Minecraft process for the instance and deletes the listed mods if `unmet_dependencies` is empty.
- `--output <file>` (required): Output JSON path.

## Common Mistakes
- **Deleting bridging gunpack JARs without checking**: Some TaCZ addon JARs act as bridges for unpacked folders in `minecraft/tacz/`. Confirm with the user before deleting theme-related addons.
- **Deleting a library still required by a kept mod**: Always run `audit-mods --delete-list ...` without `--apply` first and verify `"unmet_dependencies": []`.
