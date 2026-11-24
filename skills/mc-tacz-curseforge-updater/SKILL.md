---
name: mc-tacz-curseforge-updater
description: >-
  Searches, checks for updates, and downloads Timeless and Classics Zero (TaCZ)
  gunpacks and addons via the CurseForge Core API (gameId 432) using native OS
  downloaders (curl or wget on Linux/macOS, curl.exe or PowerShell on Windows).
---

# TaCZ CurseForge Gunpack Updater (`mc-tacz-curseforge-updater`)

## Overview
Queries the CurseForge Core API (`https://api.curseforge.com/v1`) to search for TaCZ gunpacks or check for newer files matching the instance's Minecraft version, then downloads and installs archives into `minecraft/tacz/` or `minecraft/mods/` using platform-native CLI tools (`curl`, `wget`, `curl.exe`, or PowerShell `Invoke-WebRequest`).

## Dependencies
- **`uv`**: Required to run `scripts/mc_optimizer.py` (relative to this skill's base directory) via `uv run`.
- **`credentials`**: You MUST verify that `CURSEFORGE_API_KEY` is present in `~/.env` using `grep -sq "^CURSEFORGE_API_KEY=" ~/.env` before running this skill. If missing, follow the `credentials` skill protocol to prompt the user to add their CurseForge Console API key (`https://console.curseforge.com/`).

## Quick Start
```bash
# 1. Verify CURSEFORGE_API_KEY exists safely without printing it
grep -sq "^CURSEFORGE_API_KEY=" ~/.env

# 2. Search CurseForge for TaCZ gunpacks for Minecraft 1.20.1
uv run scripts/mc_optimizer.py update-tacz-gunpacks \
  --instance "/path/to/instance" \
  --action search \
  --query "tacz gunpack" \
  --mc-version 1.20.1 \
  --limit 10 \
  --output /tmp/mc_cf_search.json

# 3. Check latest compatible file for a specific CurseForge mod ID
uv run scripts/mc_optimizer.py update-tacz-gunpacks \
  --instance "/path/to/instance" \
  --action check-updates \
  --mod-id 1028108 \
  --mc-version 1.20.1 \
  --limit 5 \
  --output /tmp/mc_cf_check.json

# 4. Download and install the gunpack into minecraft/tacz/
uv run scripts/mc_optimizer.py update-tacz-gunpacks \
  --instance "/path/to/instance" \
  --action download \
  --mod-id 1028108 \
  --mc-version 1.20.1 \
  --install-to tacz \
  --limit 1 \
  --apply \
  --output /tmp/mc_cf_download.json
```

## Utility Scripts
### `update-tacz-gunpacks`
- `--instance <dir>` (required): Target Minecraft instance directory.
- `--action <search|check-updates|download>` (required): Operation to perform.
- `--query <str>` (optional): Search filter string for `--action search`.
- `--mod-id <int>` (optional): CurseForge project ID for `check-updates` or `download`.
- `--mc-version <str>` (default `1.20.1`): Minecraft version filter.
- `--install-to <tacz|mods>` (default `tacz`): Destination subfolder inside the instance.
- `--limit <int>` (required): Maximum results to retrieve.
- `--apply` (flag): Downloads the archive to disk when `--action download` is used.
- `--output <file>` (required): Output JSON path.

## Rate Limiting
Enforces a limit of 1 request per second using `time.monotonic()` and a cross-process file lock (`/tmp/mc_optimizer_cf_api.lock`). Retries transient HTTP 429 and 5xx errors with exponential backoff (`2**attempt` seconds) and raises `RateLimitError` if still rate-limited.

## Common Mistakes
- **Printing or reading `~/.env` directly**: Never use `cat ~/.env` or pass the API key on the command line. The script loads `CURSEFORGE_API_KEY` from `~/.env` automatically.
- **Installing `.jar` mods into `tacz/`**: Check `file_name` in `check-updates` output first. If the file ends with `.jar`, pass `--install-to mods`; if it is a `.zip` gunpack, pass `--install-to tacz`.
