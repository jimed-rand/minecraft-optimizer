# Prism-based launcher paths and instance structure

This document lists the filesystem locations and metadata schemas used by Prism Launcher, Fjord Launcher, MultiMC, and PollyMC across Linux, Windows, and macOS.

## 1. Instance root paths by operating system

### Linux (Native package / AppImage / AUR)
- Prism Launcher: `~/.local/share/PrismLauncher/instances/`
- Fjord Launcher: `~/.local/share/FjordLauncher/instances/`
- PollyMC: `~/.local/share/PollyMC/instances/`
- MultiMC: `~/.local/share/multimc/instances/`

### Linux (Flatpak sandbox)
- Prism Launcher: `~/.var/app/org.prismlauncher.PrismLauncher/data/PrismLauncher/instances/`
- Fjord Launcher: `~/.var/app/org.unmojang.FjordLauncher/data/FjordLauncher/instances/`
- PollyMC: `~/.var/app/org.fn2006.PollyMC/data/PollyMC/instances/`

### Windows
- Prism Launcher: `%APPDATA%\PrismLauncher\instances\`
- Fjord Launcher: `%APPDATA%\FjordLauncher\instances\`
- PollyMC: `%APPDATA%\PollyMC\instances\`
- MultiMC: `%APPDATA%\MultiMC\instances\` (or portable folder `instances\`)

### macOS
- Prism Launcher: `~/Library/Application Support/PrismLauncher/instances/`
- Fjord Launcher: `~/Library/Application Support/FjordLauncher/instances/`
- PollyMC: `~/Library/Application Support/PollyMC/instances/`
- MultiMC: `~/Library/Application Support/MultiMC/instances/`

## 2. Instance directory layout

Each instance directory contains two top-level configuration files and a game folder named either `minecraft/` or `.minecraft/`:

```text
<instance_name>/
├── instance.cfg          # Key-value launcher settings (RAM, JVM args, Java path)
├── mmc-pack.json         # Component versions (Minecraft version, mod loader UID)
└── minecraft/            # Game working directory (may be named .minecraft)
    ├── config/           # Mod configuration files (.toml, .json, .properties)
    ├── crash-reports/    # Crash dumps
    ├── logs/             # latest.log, debug.log, and archived *.log.gz
    ├── mods/             # Mod .jar and disabled .jar.disabled files
    ├── options.txt       # Vanilla client settings (mipmapLevels, resourcePacks)
    ├── resourcepacks/    # Resource packs and native TTF font packs
    ├── saves/            # Singleplayer world folders
    └── tacz/             # Unpacked Timeless and Classics Zero gunpacks
```

## 3. Component UIDs in `mmc-pack.json`

Inspect the `components` array in `mmc-pack.json` to identify the Minecraft version and active mod loader:

| Component UID | Meaning |
|---|---|
| `net.minecraft` | Base Minecraft version (for example, `1.20.1`) |
| `net.minecraftforge` | Minecraft Forge loader |
| `net.neoforged` | NeoForge loader |
| `net.fabricmc.fabric-loader` | Fabric loader |
| `org.quiltmc.quilt-loader` | Quilt loader |
| `com.mumfrey.liteloader` | LiteLoader |
| `org.lwjgl3` / `org.lwjgl` | LWJGL native runtime |
