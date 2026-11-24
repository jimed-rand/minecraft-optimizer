# Mod loader metadata and dependency formats

Prism-based launchers support five primary mod loaders. When auditing `minecraft/mods/*.jar` before removing heavy or unused mods, parse all five formats and nested Jar-in-Jar directories to ensure no remaining mod loses a required dependency.

## 1. Minecraft Forge (`META-INF/mods.toml`)

Forge 1.14+ stores metadata in `META-INF/mods.toml`:
- Declared mod IDs appear under `[[mods]]` as `modId = "examplemod"`.
- Dependencies appear under `[[dependencies.<modId>]]` with `modId = "dep_id"` and `mandatory = true` or `mandatory = false`.
- Bundled libraries (Jar-in-Jar) are stored in `META-INF/jarjar/*.jar` with metadata in `META-INF/jarjar/metadata.json`.

## 2. NeoForge (`META-INF/neoforge.mods.toml`)

NeoForge 1.20.5+ uses `META-INF/neoforge.mods.toml` (falling back to `META-INF/mods.toml` on 1.20.1 through 1.20.4). Dependency blocks use `type = "required"` or `mandatory = true`.

## 3. Fabric (`fabric.mod.json`)

Fabric mods place `fabric.mod.json` at the root of the JAR:
- `"id"`: Primary mod identifier string.
- `"provides"`: Optional array of alias mod IDs provided by this JAR.
- `"depends"`: Object mapping required mod IDs to version ranges (ignore `fabricloader`, `fabric-loader`, `fabric`, `minecraft`, and `java` when checking mod-to-mod dependencies).
- `"recommends"`: Object mapping optional mod IDs.
- `"jars"`: Array of `{"file": "META-INF/jars/nested.jar"}` entries for bundled libraries.

## 4. Quilt (`quilt.mod.json`)

Quilt mods place `quilt.mod.json` at the root of the JAR:
- `"quilt_loader.id"`: Primary mod identifier.
- `"quilt_loader.depends"`: Array of dependency objects (`{"id": "dep_id", "optional": false}`).

## 5. LiteLoader (`litemod.json`)

Legacy LiteLoader mods place `litemod.json` at the root of the JAR or `.litemod` archive with `"name"` as the identifier.

## 6. Signed JAR precautions

Some mods (such as certain core libraries or anti-cheat clients) include cryptographic signatures in `META-INF/*.SF`, `META-INF/*.RSA`, or `META-INF/*.DSA`. Never modify or downscale textures inside a signed JAR, because altering any entry invalidates the manifest digest and triggers a `java.lang.SecurityException` during class loading.
