---
name: minecraft-optimizer
description: >-
  Optimizes Minecraft instances on Prism-based launchers (Prism Launcher, Fjord
  Launcher, MultiMC, PollyMC) across Linux, Linux Flatpak, Windows, and macOS
  for low-end hardware. Profiles CPU/RAM/swap/iGPU limits, analyzes boot log
  bottlenecks, audits and trims mods across Forge/NeoForge/Fabric/Quilt/LiteLoader,
  downscales oversized 2K/4K/8K textures, tunes JVM G1GC flags, updates TaCZ
  gunpacks via CurseForge API, clears corrupted saves, repairs missing-content
  boot errors, and replaces heavy font mods with native TTF resourcepacks from
  system fonts.
---

# Minecraft Optimizer for Prism-Based Launchers

## Overview
This skill diagnoses and optimizes modded Minecraft instances managed by Prism Launcher, Fjord Launcher, MultiMC, and PollyMC on low-end computers. It combines 10 specialized sub-skills and a unified CLI script (`scripts/mc_optimizer.py`, relative to this skill's base directory) to reduce 25-to-30-minute startup times down to a few minutes while preserving the user's preferred mod themes.

Reference documentation:
- [Prism launcher paths and layout](./references/prism_launcher_paths.md)
- [Low-end JVM and mod configs](./references/low_end_jvm_and_mod_configs.md)
- [Mod loader metadata formats](./references/modloader_metadata_formats.md)
- [CurseForge API and missing-content fixes](./references/curseforge_and_missing_content_fixes.md)

## Dependencies
- **`uv`**: Required to execute `scripts/mc_optimizer.py` (relative to this skill's base directory) in an isolated Python environment (`uv run --with pillow`). Follow the `uv` skill to verify or install `uv` before running commands.
- **`credentials`**: Required only when running the `update-tacz-gunpacks` subcommand (`mc-tacz-curseforge-updater`), which uses `CURSEFORGE_API_KEY` from `~/.env`.

## Sub-skills in this package
1. [`mc-hardware-profiler`](../mc-hardware-profiler/SKILL.md): Inspect CPU cores, RAM, `zram` vs. slow disk/eMMC swap, and iGPU shared VRAM (`Shmem`).
2. [`mc-boot-analyzer`](../mc-boot-analyzer/SKILL.md): Discover Prism/Fjord instances across OS paths and analyze `latest.log` / `debug.log` timestamp stalls.
3. [`mc-mod-auditor`](../mc-mod-auditor/SKILL.md): Audit mods and dependency graphs across Forge, NeoForge, Fabric, Quilt, and LiteLoader.
4. [`mc-texture-downscaler`](../mc-texture-downscaler/SKILL.md): Proportionally downscale oversized 2K/4K/8K PNG textures in unpacked gunpacks and mod JARs.
5. [`mc-jvm-and-config-tuner`](../mc-jvm-and-config-tuner/SKILL.md): Fix G1GC swap-thrashing flags in `instance.cfg` and tune ModernFix, TaCZ, and `options.txt`.
6. [`mc-instance-cleaner`](../mc-instance-cleaner/SKILL.md): Terminate running Minecraft processes and remove approved saves, backups, `tacz_default_gun`, and old logs.
7. [`mc-tacz-curseforge-updater`](../mc-tacz-curseforge-updater/SKILL.md): Search and download TaCZ gunpacks via the CurseForge Core API using `curl`, `wget`, or PowerShell.
8. [`mc-corrupted-saves-cleaner`](../mc-corrupted-saves-cleaner/SKILL.md): Detect and remove worlds with corrupted `level.dat` or 0-byte `.mca` region files.
9. [`mc-missing-content-fixer`](../mc-missing-content-fixer/SKILL.md): Patch broken gunpack language JSONs, invalid `PassThroughBlocks` tags, missing ADS presets, and broken recipes.
10. [`mc-system-font-changer`](../mc-system-font-changer/SKILL.md): Build a native Vanilla TrueType (`"type": "ttf"`) font resourcepack from any installed system font to replace heavy mods like `ModernUI`.

## Quick Start
Always run diagnostics and present a summary to the user before passing `--apply` to any mutating subcommand (run `scripts/mc_optimizer.py` from this skill's base directory, or pass its full path):

```bash
# 1. Discover Prism/Fjord instances across Linux, Flatpak, Windows, and macOS
uv run scripts/mc_optimizer.py discover \
  --limit 20 --output /tmp/mc_instances.json

# 2. Profile system hardware and live swap/iGPU memory pressure
uv run scripts/mc_optimizer.py check-hardware \
  --instance "/path/to/instance" --output /tmp/mc_hardware.json

# 3. Analyze boot log timestamp bottlenecks
uv run scripts/mc_optimizer.py analyze-boot \
  --instance "/path/to/instance" --min-gap-seconds 3.0 --limit 25 --output /tmp/mc_boot.json
```

## Utility Scripts
All subcommands are provided by `scripts/mc_optimizer.py` (relative to this skill's base directory) and write structured JSON to `--output`:

- `discover --limit <N> --output <file> [--custom-path <dir>]`
- `check-hardware --output <file> [--instance <dir>]`
- `analyze-boot --instance <dir> --limit <N> --output <file> [--min-gap-seconds <sec>]`
- `audit-mods --instance <dir> --limit <N> --output <file> [--delete-list <mods>] [--apply]`
- `downscale-textures --instance <dir> --output <file> [--max-item-size 128] [--max-model-size 512] [--apply]`
- `tune-instance --instance <dir> --output <file> [--preserve-heap] [--set-max-mem <MB>] [--apply]`
- `change-font --output <file> [--list-fonts] [--query <name>] [--instance <dir>] [--font-path <ttf>] [--remove-modernui] [--apply]`
- `check-corrupted-saves --instance <dir> --output <file> [--apply]`
- `fix-missing-content --instance <dir> --output <file> [--apply]`
- `update-tacz-gunpacks --instance <dir> --action <search|check-updates|download> --limit <N> --output <file> [--query <q>] [--mod-id <id>] [--mc-version 1.20.1] [--apply]`
- `cleanup-saves --instance <dir> --output <file> [--kill-running] [--clear-saves] [--clear-backups] [--reset-tacz-default] [--clear-logs] [--apply]`

## Rate Limiting
The `update-tacz-gunpacks` subcommand enforces a 1 request per second rate limit (`time.monotonic()`) across processes via `/tmp/mc_optimizer_cf_api.lock`, with exponential backoff on HTTP 429 and 5xx responses. All other subcommands operate locally without network requests.

## Common Mistakes
- **Modifying files while Minecraft is running**: Always let `--apply` terminate active Minecraft Java processes for the target instance before deleting mods, saves, or rewriting JAR textures.
- **Overriding user RAM settings without permission**: Keep `--preserve-heap` enabled when running `tune-instance` unless the user explicitly asks to change `MaxMemAlloc`.
- **Downscaling signed JARs or animated `.mcmeta` textures**: Never bypass the script's built-in checks that skip signed JARs (`META-INF/*.SF`, `*.RSA`) and animated sprite strips (`.png.mcmeta`).
