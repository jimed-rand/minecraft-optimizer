---
name: mc-jvm-and-config-tuner
description: >-
  Tunes G1GC JVM arguments in Prism/Fjord instance.cfg to prevent swap thrashing
  on low-end systems while preserving user heap size, and optimizes ModernFix,
  TaCZ, and vanilla options.txt settings.
---

# Minecraft JVM and Config Tuner (`mc-jvm-and-config-tuner`)

## Overview
Updates `JvmArgs` in `instance.cfg` to prevent G1GC from thrashing disk/eMMC swap during startup (`-XX:InitiatingHeapOccupancyPercent=45 -XX:SoftRefLRUPolicyMSPerMB=50 -XX:G1HeapRegionSize=16M`), enables `dynamic_resources=true` and `clear_mixin_classinfo=true` in `modernfix-mixins.properties`, and sets `mipmapLevels:0` in `options.txt`.

## Dependencies
- **`uv`**: Required to run `scripts/mc_optimizer.py` (relative to this skill's base directory) via `uv run`.

## Quick Start
```bash
# Dry-run config inspection
uv run scripts/mc_optimizer.py tune-instance \
  --instance "/path/to/instance" \
  --preserve-heap \
  --output /tmp/mc_tune_dryrun.json

# Apply JVM and config optimizations (keeping user MaxMemAlloc intact)
uv run scripts/mc_optimizer.py tune-instance \
  --instance "/path/to/instance" \
  --preserve-heap \
  --apply \
  --output /tmp/mc_tune_applied.json
```

## Utility Scripts
### `tune-instance`
- `--instance <dir>` (required): Target instance directory.
- `--preserve-heap` (default `true`): Keeps the user's existing `MaxMemAlloc` and `MinMemAlloc` values untouched.
- `--set-max-mem <MB>` (optional): Overrides `MaxMemAlloc` only when explicitly requested by the user.
- `--apply` (flag): Terminates any running Minecraft process and writes changes to disk.
- `--output <file>` (required): Output JSON path.

## Common Mistakes
- **Setting `InitiatingHeapOccupancyPercent=20` on low-RAM machines**: When part of the heap is in swap, a 20% threshold causes continuous full-heap marking and 10+ minute startup freezes. Use `45`.
- **Changing `MaxMemAlloc` without asking**: Always respect the user's configured heap allocation unless they ask to change it.
