# `minecraft-optimizer`: Low-End PC Optimizer Skills for Prism-Based Minecraft Launchers

[![skills.sh](https://skills.sh/b/jimed-rand/minecraft-optimizer)](https://skills.sh/jimed-rand/minecraft-optimizer)

A collection of modular agent skills and a cross-platform Python CLI (`scripts/mc_optimizer.py`) for diagnosing and optimizing heavy modded Minecraft instances on Prism Launcher, Fjord Launcher, MultiMC, and PollyMC across Linux, Linux Flatpak, Windows, and macOS.

Built from real-world forensic profiling on dual-core low-end hardware (Intel Celeron N4020, 8 GB RAM, integrated UHD 600 GPU, eMMC storage), where modpacks with 180+ mods and 3.4 GB of unpacked TaCZ gunpacks suffered 27-to-30-minute startup times due to `16384x8192` TextureAtlas expansion, 30 GB of uncompressed 2K/4K/8K RGBA textures, and G1GC swap thrashing across `zram` and disk swap partitions.

---

## Included Skills

| Skill | CLI Subcommand(s) | Purpose |
|---|---|---|
| [`minecraft-optimizer`](./skills/minecraft-optimizer/SKILL.md) | All 11 subcommands | Root orchestrator skill covering the full diagnostic and optimization workflow. |
| [`mc-hardware-profiler`](./skills/mc-hardware-profiler/SKILL.md) | `check-hardware` | Profiles CPU cores/clock, RAM, `zram` vs. slow disk/eMMC swap, iGPU `Shmem`, and live JVM `VmRSS`/`VmSwap`. |
| [`mc-boot-analyzer`](./skills/mc-boot-analyzer/SKILL.md) | `discover`, `analyze-boot` | Auto-discovers Prism/Fjord instances across Linux, Flatpak, Windows, and macOS, and parses `latest.log` / `debug.log` timestamp stalls. |
| [`mc-mod-auditor`](./skills/mc-mod-auditor/SKILL.md) | `audit-mods` | Scans mods across **Forge, NeoForge, Fabric, Quilt, and LiteLoader** (including Jar-in-Jar), verifies zero broken dependencies, and removes unwanted mods. |
| [`mc-texture-downscaler`](./skills/mc-texture-downscaler/SKILL.md) | `downscale-textures` | Proportionally downscales oversized 2K/4K/8K PNGs in unpacked packs (`tacz/`, `resourcepacks/`) and mod JARs while skipping signed JARs and `.mcmeta` animations. |
| [`mc-jvm-and-config-tuner`](./skills/mc-jvm-and-config-tuner/SKILL.md) | `tune-instance` | Fixes G1GC swap-thrashing flags in `instance.cfg` (preserving user `MaxMemAlloc`) and tunes `modernfix-mixins.properties` and `options.txt`. |
| [`mc-instance-cleaner`](./skills/mc-instance-cleaner/SKILL.md) | `cleanup-saves` | Terminates active Minecraft JVM processes and clears approved world saves, old backups (`tacz_backup`), `tacz_default_gun`, crash reports, and `*.log.gz`. |
| [`mc-tacz-curseforge-updater`](./skills/mc-tacz-curseforge-updater/SKILL.md) | `update-tacz-gunpacks` | Searches and downloads TaCZ gunpacks via the CurseForge Core API (`gameId=432`) using `curl`, `wget`, or PowerShell with file-locked 1 req/s rate limiting. |
| [`mc-corrupted-saves-cleaner`](./skills/mc-corrupted-saves-cleaner/SKILL.md) | `check-corrupted-saves` | Detects and removes worlds with missing/0-byte `level.dat`, invalid gzip headers, or 0-byte `.mca` region files. |
| [`mc-missing-content-fixer`](./skills/mc-missing-content-fixer/SKILL.md) | `fix-missing-content` | Repairs malformed `lang/*.json` files, empty `PassThroughBlocks` tags in `tacz-common.toml`, missing `tacz:renew` ADS presets, broken `tick.json` tags, and unsupported `tacz:nbt` recipes. |
| [`mc-system-font-changer`](./skills/mc-system-font-changer/SKILL.md) | `change-font` | Scans installed system `.ttf`/`.otf` fonts on Linux, Windows, and macOS, builds a native Vanilla TrueType font resourcepack, enables it in `options.txt`, and optionally removes `ModernUI`. |

---

## Installation

### 1. Via `skills.sh` / Skills CLI (Recommended)
Install all 11 skills:
```bash
npx skills add jimed-rand/minecraft-optimizer
```

Or install specific skills only:
```bash
npx skills add jimed-rand/minecraft-optimizer --skill minecraft-optimizer
npx skills add jimed-rand/minecraft-optimizer --skill mc-texture-downscaler
```

### 2. Local / Global Symlink Installation for Antigravity, Gemini CLI, or Claude Code
```bash
git clone https://github.com/jimed-rand/minecraft-optimizer.git
ln -s "$(pwd)/minecraft-optimizer/skills/"* ~/.gemini/config/skills/
```

---

## Prerequisites
- **Python 3.10+** and **[`uv`](https://docs.astral.sh/uv/)** (`uv run --with pillow` automatically provisions Pillow in an ephemeral environment when running `downscale-textures`).
- For `mc-tacz-curseforge-updater`: A CurseForge Console API key stored as `CURSEFORGE_API_KEY=...` in `~/.env`.

---

## License
Licensed under the **GNU General Public License v2.0 or later (`GPL-2.0-or-later`)** — see [`LICENSE`](./LICENSE).
