---
name: mc-hardware-profiler
description: >-
  Profiles system hardware and live memory pressure for Minecraft instances on
  low-end computers. Inspects CPU cores and frequency, physical RAM, compressed
  zram versus slow disk or eMMC swap partitions, integrated GPU shared memory
  (Shmem), and running Minecraft JVM VmRSS and VmSwap usage.
---

# Minecraft Hardware Profiler (`mc-hardware-profiler`)

## Overview
Evaluates the host computer's CPU, physical RAM, swap devices, and integrated GPU shared memory (`Shmem`) to classify the machine into a hardware tier (`low_end`, `mid_range`, or `high_end`) and detect swap thrashing during Minecraft startup.

## Dependencies
- **`uv`**: Required to run `scripts/mc_optimizer.py` (relative to this skill's base directory) via `uv run`.

## Quick Start
```bash
uv run scripts/mc_optimizer.py check-hardware \
  --instance "/path/to/PrismLauncher/instances/MyInstance" \
  --output /tmp/mc_hardware.json
```

## Utility Scripts
### `check-hardware`
- `--instance <path>` (optional): Path to a Prism/Fjord instance directory. When provided, the script inspects `/proc/<pid>/status` for any running Minecraft process tied to that instance and reports `VmRSS` (resident physical RAM) and `VmSwap` (swapped memory).
- `--output <file>` (required): Path to write the JSON diagnostic report.

## Common Mistakes
- **Ignoring slow disk swap behind `zram`**: Systems with 4 GB to 8 GB of RAM often fill `/dev/zram0` and spill gigabytes onto an eMMC or HDD swap partition. Check `swap_devices` in the JSON report to see if non-zram swap is active.
- **Overlooking `shmem_igpu`**: On integrated GPUs (such as Intel UHD Graphics), a `16384x8192` Minecraft `TextureAtlas` consumes over 1 GB of `Shmem`, reducing physical RAM available to the Java heap.
