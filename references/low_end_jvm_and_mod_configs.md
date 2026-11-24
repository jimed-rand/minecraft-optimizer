# Low-end JVM and mod configuration reference

This guide documents JVM Garbage Collection flags and mod configuration settings tested on dual-core processors (such as the Intel Celeron N4020) with integrated graphics and 4 GB to 8 GB of system RAM.

## 1. Preventing G1GC swap thrashing in `instance.cfg`

Many public JVM flag guides recommend `-XX:InitiatingHeapOccupancyPercent=20` and `-XX:SoftRefLRUPolicyMSPerMB=0`. On a machine with 8 GB of total RAM and a 5.5 GB Java heap (`MaxMemAlloc=5634`), the operating system often swaps 3 GB to 4.5 GB of the Java process onto `zram` or a disk/eMMC swap partition.

When `InitiatingHeapOccupancyPercent` is set to `20`, G1GC begins continuous concurrent marking across the entire heap as soon as heap usage exceeds 20% (around 1.1 GB). Because swapped pages must be faulted back from storage during marking, the final resource reload phase can stall for 10 to 15 minutes.

### Recommended `JvmArgs` for low-end 2-core / 4-core systems

```ini
JvmArgs="-XX:+UseG1GC -XX:+ParallelRefProcEnabled -XX:ParallelGCThreads=2 -XX:ConcGCThreads=1 -XX:MaxGCPauseMillis=100 -XX:+UnlockExperimentalVMOptions -XX:+DisableExplicitGC -XX:G1NewSizePercent=20 -XX:G1MaxNewSizePercent=35 -XX:G1ReservePercent=15 -XX:G1HeapRegionSize=16M -XX:InitiatingHeapOccupancyPercent=45 -XX:SoftRefLRUPolicyMSPerMB=50"
```

Key adjustments:
- `-XX:InitiatingHeapOccupancyPercent=45`: Delays old-generation concurrent marking until 45% occupancy, reducing swap page faults during resource loading.
- `-XX:SoftRefLRUPolicyMSPerMB=50`: Keeps soft references alive for 50 ms per free MB instead of flushing model caches immediately on every GC cycle.
- `-XX:G1HeapRegionSize=16M`: Reduces region-tracking overhead for large modpack textures.
- Respect user heap settings: Do not alter `MaxMemAlloc` or `MinMemAlloc` unless the user explicitly approves changing heap allocation.

## 2. Shrinking the main `TextureAtlas` and iGPU shared VRAM

On integrated GPUs (such as Intel UHD Graphics 600), OpenGL textures are stored in shared system memory (`Shmem` in `/proc/meminfo`). When mods place 1024x1024 or 2560x2560 PNG sprites into `assets/<namespace>/textures/item/` or `textures/block/`, Minecraft expands `minecraft:textures/atlas/blocks.png-atlas` to `16384x8192` (536 MB raw RGBA per mipmap level).

To cut atlas RAM and VRAM usage by over 85%:
1. Set `mipmapLevels:0` in `minecraft/options.txt`.
2. Proportionally downscale static 2D item/block PNGs (`textures/item/` and `textures/block/` without `.png.mcmeta`) to a maximum of `128x128`.
3. Proportionally downscale 3D model and gun UV textures (`textures/gun/`, `textures/attachment/`, `textures/entity/` without `.png.mcmeta`) to a maximum of `512x512`. Because OpenGL normalizes UV coordinates to `[0.0, 1.0]`, proportional scaling preserves UV mapping without modifying model geometry JSON files.

## 3. ModernFix and TaCZ client settings

### `config/modernfix-mixins.properties`
```ini
mixin.perf.clear_mixin_classinfo=true
mixin.perf.dynamic_resources=true
```
- `dynamic_resources=true` avoids baking all block and item models upfront during startup.
- `clear_mixin_classinfo=true` frees Mixin metadata trees after boot finishes.

### `config/tacz-client.toml`
```toml
[resource]
EnableLazyClientAssetLoad = true
```
- Loads heavy gun animations and state machines on demand rather than blocking the client setup thread.
