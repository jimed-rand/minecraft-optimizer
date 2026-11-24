# CurseForge API gunpack updates and missing-content boot fixes

## 1. CurseForge Core API v1 for TaCZ gunpacks

The `update-tacz-gunpacks` command queries the official CurseForge Core API (`https://api.curseforge.com/v1`) for Minecraft (`gameId = 432`).

### Authentication and rate limits
- Requires an API key stored as `CURSEFORGE_API_KEY` in `~/.env` and passed in the `x-api-key` HTTP header.
- Enforces a rate limit of 1 request per second (`time.monotonic()`) across processes via `/tmp/mc_optimizer_cf_api.lock`, with exponential backoff on HTTP 429 and 5xx responses.

### Key endpoints
- Search TaCZ gunpacks: `GET /v1/mods/search?gameId=432&searchFilter=tacz&gameVersion=1.20.1`
- List compatible files for a project: `GET /v1/mods/{modId}/files?gameVersion=1.20.1`

### Cross-platform file downloading
Once a file's `downloadUrl` is retrieved, `mc_optimizer.py` downloads the archive using native tools in priority order:
1. Linux and macOS: `curl -fL -sS -o <dest> <url>`, falling back to `wget -q -O <dest> <url>`.
2. Windows: `curl.exe -fL -sS -o <dest> <url>`, falling back to `powershell -NoProfile -Command "Invoke-WebRequest -Uri '<url>' -OutFile '<dest>'"`.
3. Universal fallback: Python standard library `urllib.request.urlopen`.

## 2. Common missing-content errors that stall Minecraft boot

When unpacking third-party TaCZ gunpacks or running large modpacks, malformed JSON and TOML descriptors cause Forge and TaCZ to throw thousands of exceptions during resource reload:

1. **Empty string in `tacz-common.toml` (`PassThroughBlocks = [""]`)**:
   - Symptom in log: `[tacz/]: Ignoring invalid block ID or tag '' in ammo.PassThroughBlocks`
   - Fix: Replace `PassThroughBlocks = [""]` with `PassThroughBlocks = []`.
2. **Malformed language files in unpacked gunpacks (`lang/*.json`)**:
   - Symptom in log: `[ClientLanguage/]: Skipped language file: ww:lang/en_us.json (MalformedJsonException: Unterminated object)`
   - Fix: Strip raw control characters and trailing commas, or replace unrecoverable language files with `{}`.
3. **Missing ADS preset `tacz:renew` in legacy gunpacks**:
   - Symptom in log: `[tacz/]: Missing ADS preset tacz:renew referenced by gun display ...; falling back to tacz:legacy`
   - Fix: Replace `"tacz:renew"` with `"tacz:legacy"` in unpacked gun display JSON files.
4. **Missing function references in `data/minecraft/tags/functions/tick.json`**:
   - Symptom in log: `Failed to load function stimshot:tick ... Couldn't load tag minecraft:tick`
   - Fix: Clear invalid function references from the gunpack's `tick.json`.
5. **Unsupported `tacz:nbt` ingredient in vanilla crafting recipes**:
   - Symptom in log: `Parsing error loading recipe spearhead:gun/...: Unknown ingredient type: tacz:nbt`
   - Fix: Rename the incompatible recipe JSON to `.json.disabled` when the required recipe-ingredient addon mod is not installed.
