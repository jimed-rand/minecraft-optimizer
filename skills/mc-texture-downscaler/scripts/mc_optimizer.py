#!/usr/bin/env python3
"""CLI helper for optimizing Prism-based Minecraft instances on low-end PCs.

Supports Prism Launcher, Fjord Launcher, MultiMC, and PollyMC across Linux,
Linux Flatpak, Windows, and macOS, covering Forge, NeoForge, Fabric, Quilt,
and LiteLoader.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import gzip
import io
import json
import os
import platform
import re
import shutil
import signal
import struct
import subprocess
import sys
import tempfile
import time
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request
import zipfile


class RateLimitError(Exception):
    """Raised when an external API rate limit (HTTP 429) is exceeded."""


def write_output(data, output_file):
    """Serializes result data as formatted JSON to output_file."""
    try:
        out_dir = os.path.dirname(os.path.abspath(output_file))
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Success! Data written to: {output_file}")
    except (OSError, TypeError) as e:
        print(f"Error writing to file {output_file}: {e}", file=sys.stderr)
        sys.exit(1)


def resolve_mc_dir(instance_path):
    """Returns the .minecraft or minecraft subdirectory for a Prism instance."""
    inst = os.path.abspath(os.path.expanduser(instance_path))
    for sub in ("minecraft", ".minecraft"):
        candidate = os.path.join(inst, sub)
        if os.path.isdir(candidate):
            return inst, candidate
    if os.path.isdir(os.path.join(inst, "mods")) or os.path.isfile(os.path.join(inst, "options.txt")):
        parent = os.path.dirname(inst)
        return parent, inst
    return inst, os.path.join(inst, "minecraft")


def find_running_mc_pids(instance_path):
    """Finds running Java PIDs whose command line references instance_path."""
    inst_Root, mc_dir = resolve_mc_dir(instance_path)
    pids = []
    if os.path.isdir("/proc"):
        for entry in os.listdir("/proc"):
            if not entry.isdigit():
                continue
            pid = int(entry)
            if pid == os.getpid():
                continue
            try:
                with open(f"/proc/{pid}/cmdline", "rb") as f:
                    cmd = f.read().decode("utf-8", errors="replace").replace("\x00", " ")
                if ("java" in cmd.lower()) and (inst_Root in cmd or mc_dir in cmd):
                    pids.append(pid)
            except OSError:
                continue
    return pids


def terminate_instance_processes(instance_path):
    """Cleanly terminates running Minecraft Java processes for the instance."""
    pids = find_running_mc_pids(instance_path)
    killed = []
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            continue
    if pids:
        time.sleep(2.0)
    for pid in pids:
        try:
            os.kill(pid, 0)
            os.kill(pid, signal.SIGKILL)
            killed.append({"pid": pid, "signal": "SIGKILL"})
        except OSError:
            killed.append({"pid": pid, "signal": "SIGTERM"})
    return killed


def get_default_launcher_roots():
    """Returns candidate Prism/Fjord/MultiMC/PollyMC instance directories across OSes."""
    home = os.path.expanduser("~")
    roots = []
    # Linux native
    for launcher in ("PrismLauncher", "FjordLauncher", "PollyMC", "multimc"):
        roots.append(("linux-native", launcher, os.path.join(home, ".local", "share", launcher, "instances")))
    # Linux Flatpak
    flatpak_map = [
        ("org.prismlauncher.PrismLauncher", "PrismLauncher"),
        ("org.unmojang.FjordLauncher", "FjordLauncher"),
        ("org.fn2006.PollyMC", "PollyMC"),
    ]
    for app_id, folder in flatpak_map:
        roots.append((
            "linux-flatpak",
            folder,
            os.path.join(home, ".var", "app", app_id, "data", folder, "instances"),
        ))
    # Windows
    appdata = os.environ.get("APPDATA") or os.path.join(home, "AppData", "Roaming")
    for launcher in ("PrismLauncher", "FjordLauncher", "PollyMC", "MultiMC"):
        roots.append(("windows", launcher, os.path.join(appdata, launcher, "instances")))
    # macOS
    mac_sup = os.path.join(home, "Library", "Application Support")
    for launcher in ("PrismLauncher", "FjordLauncher", "PollyMC", "MultiMC"):
        roots.append(("macos", launcher, os.path.join(mac_sup, launcher, "instances")))
    return roots


def parse_instance_metadata(inst_dir):
    """Parses instance.cfg and mmc-pack.json in a Prism-based instance folder."""
    cfg_path = os.path.join(inst_dir, "instance.cfg")
    pack_path = os.path.join(inst_dir, "mmc-pack.json")
    meta = {
        "path": inst_dir,
        "name": os.path.basename(inst_dir),
        "mc_version": None,
        "mod_loader": "vanilla",
        "loader_version": None,
        "max_mem_mb": None,
        "min_mem_mb": None,
        "jvm_args": None,
    }
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("name="):
                        meta["name"] = line.split("=", 1)[1]
                    elif line.startswith("MaxMemAlloc="):
                        try:
                            meta["max_mem_mb"] = int(line.split("=", 1)[1])
                        except ValueError:
                            pass
                    elif line.startswith("MinMemAlloc="):
                        try:
                            meta["min_mem_mb"] = int(line.split("=", 1)[1])
                        except ValueError:
                            pass
                    elif line.startswith("JvmArgs="):
                        meta["jvm_args"] = line.split("=", 1)[1].strip('"')
        except OSError:
            pass
    if os.path.isfile(pack_path):
        try:
            with open(pack_path, "r", encoding="utf-8", errors="replace") as f:
                pack = json.load(f)
            loader_uids = {
                "net.minecraftforge": "forge",
                "net.neoforged": "neoforge",
                "net.fabricmc.fabric-loader": "fabric",
                "org.quiltmc.quilt-loader": "quilt",
                "com.mumfrey.liteloader": "liteloader",
            }
            for comp in pack.get("components", []):
                uid = comp.get("uid", "")
                ver = comp.get("version")
                if uid == "net.minecraft":
                    meta["mc_version"] = ver
                elif uid in loader_uids:
                    meta["mod_loader"] = loader_uids[uid]
                    meta["loader_version"] = ver
        except (OSError, json.JSONDecodeError):
            pass
    return meta


def cmd_discover(args):
    """Discovers Prism/Fjord/MultiMC instances across standard and custom paths."""
    candidates = get_default_launcher_roots()
    if args.custom_path:
        custom = os.path.abspath(os.path.expanduser(args.custom_path))
        candidates.insert(0, ("custom", "custom", custom))

    instances = []
    seen = set()
    for platform_kind, launcher, root in candidates:
        if not os.path.isdir(root):
            continue
        # Check if root itself is an instance
        if os.path.isfile(os.path.join(root, "instance.cfg")) or os.path.isfile(os.path.join(root, "mmc-pack.json")):
            real = os.path.realpath(root)
            if real not in seen:
                seen.add(real)
                info = parse_instance_metadata(root)
                info["platform"] = platform_kind
                info["launcher"] = launcher
                instances.append(info)
            continue
        try:
            for entry in sorted(os.listdir(root)):
                inst_dir = os.path.join(root, entry)
                if not os.path.isdir(inst_dir):
                    continue
                if os.path.isfile(os.path.join(inst_dir, "instance.cfg")) or os.path.isfile(os.path.join(inst_dir, "mmc-pack.json")):
                    real = os.path.realpath(inst_dir)
                    if real in seen:
                        continue
                    seen.add(real)
                    info = parse_instance_metadata(inst_dir)
                    info["platform"] = platform_kind
                    info["launcher"] = launcher
                    instances.append(info)
                    if len(instances) >= args.limit:
                        break
        except OSError:
            continue
        if len(instances) >= args.limit:
            break

    write_output({
        "host_os": platform.system(),
        "discovered_count": len(instances),
        "limit": args.limit,
        "instances": instances,
    }, args.output)


def cmd_check_hardware(args):
    """Profiles CPU, RAM, swap devices, iGPU Shmem, and running Minecraft process."""
    cpu_model = platform.processor() or "Unknown"
    logical_cores = os.cpu_count() or 1
    max_mhz = None
    if os.path.isfile("/proc/cpuinfo"):
        try:
            with open("/proc/cpuinfo", "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    if "model name" in line and ":" in line:
                        cpu_model = line.split(":", 1)[1].strip()
                        break
        except OSError:
            pass
    freq_path = "/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq"
    if os.path.isfile(freq_path):
        try:
            with open(freq_path, "r", encoding="utf-8") as f:
                max_mhz = round(int(f.read().strip()) / 1000.0, 1)
        except (OSError, ValueError):
            pass

    mem = {}
    if os.path.isfile("/proc/meminfo"):
        try:
            with open("/proc/meminfo", "r", encoding="utf-8") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 2:
                        key = parts[0].rstrip(":")
                        try:
                            mem[key] = round(int(parts[1]) / 1024.0, 1)
                        except ValueError:
                            pass
        except OSError:
            pass

    swaps = []
    has_slow_disk_swap_active = False
    if os.path.isfile("/proc/swaps"):
        try:
            with open("/proc/swaps", "r", encoding="utf-8") as f:
                lines = f.readlines()[1:]
            for line in lines:
                parts = line.split()
                if len(parts) >= 5:
                    dev = parts[0]
                    size_mb = round(int(parts[2]) / 1024.0, 1)
                    used_mb = round(int(parts[3]) / 1024.0, 1)
                    prio = int(parts[4])
                    is_zram = "zram" in dev
                    if not is_zram and used_mb > 256:
                        has_slow_disk_swap_active = True
                    swaps.append({
                        "device": dev,
                        "type": parts[1],
                        "size_mb": size_mb,
                        "used_mb": used_mb,
                        "priority": prio,
                        "is_zram": is_zram,
                    })
        except (OSError, ValueError):
            pass

    total_ram_mb = mem.get("MemTotal", 0.0)
    avail_ram_mb = mem.get("MemAvailable", 0.0)
    shmem_mb = mem.get("Shmem", 0.0)

    if logical_cores <= 2 or (total_ram_mb and total_ram_mb <= 8192):
        tier = "low_end"
    elif logical_cores <= 4 or (total_ram_mb and total_ram_mb <= 12288):
        tier = "mid_range"
    else:
        tier = "high_end"

    mc_proc_info = []
    if args.instance:
        for pid in find_running_mc_pids(args.instance):
            status_path = f"/proc/{pid}/status"
            pinfo = {"pid": pid, "vm_rss_mb": 0.0, "vm_swap_mb": 0.0}
            if os.path.isfile(status_path):
                try:
                    with open(status_path, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.startswith("VmRSS:"):
                                pinfo["vm_rss_mb"] = round(int(line.split()[1]) / 1024.0, 1)
                            elif line.startswith("VmSwap:"):
                                pinfo["vm_swap_mb"] = round(int(line.split()[1]) / 1024.0, 1)
                except (OSError, ValueError):
                    pass
            mc_proc_info.append(pinfo)

    recommendations = []
    if tier == "low_end":
        recommendations.append(
            "Cap 2D item/block textures at 128px and 3D model UV textures at 512px to keep the main TextureAtlas and iGPU Shmem small."
        )
        recommendations.append(
            "Set G1GC flags to -XX:G1HeapRegionSize=16M -XX:InitiatingHeapOccupancyPercent=45 -XX:SoftRefLRUPolicyMSPerMB=50 to prevent swap thrashing."
        )
    if has_slow_disk_swap_active:
        recommendations.append(
            "Disk/eMMC swap is actively in use alongside zram; avoidInitiatingHeapOccupancyPercent=20 which forces continuous full-heap scans over swapped pages."
        )
    if shmem_mb > 768:
        recommendations.append(
            f"Shared memory (Shmem) is {shmem_mb} MB (likely iGPU VRAM for oversized TextureAtlas). Downscale item icons >128px and set mipmapLevels:0."
        )

    write_output({
        "hardware_tier": tier,
        "cpu": {
            "model": cpu_model,
            "logical_cores": logical_cores,
            "max_clock_mhz": max_mhz,
        },
        "memory_mb": {
            "total": total_ram_mb,
            "available": avail_ram_mb,
            "shmem_igpu": shmem_mb,
            "swap_total": mem.get("SwapTotal", 0.0),
            "swap_free": mem.get("SwapFree", 0.0),
        },
        "swap_devices": swaps,
        "running_minecraft_processes": mc_proc_info,
        "recommendations": recommendations,
    }, args.output)


def classify_log_gap(prev_line, curr_line):
    """Classifies a timestamp gap between two log lines into a root-cause category."""
    combined = (prev_line + " " + curr_line).lower()
    if "tacz" in combined or "gunpack" in combined or "arcana" in combined or "taczexpands" in combined:
        return "tacz_gunpack_loading"
    if "touhou_little_maid" in combined or "custompackloader" in combined or "molang" in combined:
        return "tlm_or_geckolib_model_loading"
    if "music_player" in combined or "webpo-generator" in combined or "youtube" in combined:
        return "music_player_network_stall"
    if "kubejs" in combined or "kubeloader" in combined or "rhino" in combined:
        return "kubejs_script_compile"
    if "modernui" in combined or "emoji" in combined:
        return "modernui_font_emoji_scan"
    if "textureatlas" in combined or "stitcher" in combined:
        return "texture_atlas_stitching"
    if "entity texture features" in combined or "[etf]" in combined:
        return "post_reload_gc_or_etf_stall"
    if "mixin" in combined or "modlauncher" in combined or "bootstrap" in combined:
        return "modlauncher_mixin_init"
    return "resource_reload_or_gc_stall"


def cmd_analyze_boot(args):
    """Parses latest.log and debug.log for boot duration, atlases, and stalls."""
    inst_root, mc_dir = resolve_mc_dir(args.instance)
    inst_meta = parse_instance_metadata(inst_root)
    logs_dir = os.path.join(mc_dir, "logs")
    ts_re = re.compile(r"^\[(?:\d+[A-Za-z]+\d+\s+)?(\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?\]")
    boot_time_re = re.compile(r"Game took ([0-9.]+) seconds to start")
    atlas_re = re.compile(r"Created:\s*(\d+x\d+x\d+)\s+(\S+)")

    results = {}
    for log_name in ("latest.log", "debug.log"):
        path = os.path.join(logs_dir, log_name)
        if not os.path.isfile(path):
            continue
        gaps = []
        atlases = []
        total_boot_sec = None
        error_counts = {"tlm_molang_errors": 0, "tacz_missing_scripts": 0, "recipe_errors": 0, "malformed_lang": 0}
        prev_sec = None
        start_sec = None
        prev_line = ""
        prev_ln = 0
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                for idx, line in enumerate(f, 1):
                    bm = boot_time_re.search(line)
                    if bm:
                        total_boot_sec = float(bm.group(1))
                    am = atlas_re.search(line)
                    if am:
                        atlases.append({"dimensions": am.group(1), "atlas": am.group(2)})
                    if "touhou_little_maid" in line and "Failed to parse value" in line:
                        error_counts["tlm_molang_errors"] += 1
                    elif "tacz/ScriptLoader" in line or "tacz/CommonGunIndex" in line:
                        error_counts["tacz_missing_scripts"] += 1
                    elif "Parsing error loading recipe" in line:
                        error_counts["recipe_errors"] += 1
                    elif "Skipped language file" in line:
                        error_counts["malformed_lang"] += 1

                    m = ts_re.match(line)
                    if m:
                        hh, mm, ss, ms = int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)
                        frac = float("0." + ms) if ms else 0.0
                        curr_sec = hh * 3600 + mm * 60 + ss + frac
                        if start_sec is None:
                            start_sec = curr_sec
                        if prev_sec is not None:
                            diff = curr_sec - prev_sec
                            if diff < -43200:
                                diff += 86400
                            if diff >= args.min_gap_seconds:
                                gaps.append({
                                    "duration_sec": round(diff, 2),
                                    "category": classify_log_gap(prev_line, line),
                                    "from_line": prev_ln,
                                    "to_line": idx,
                                    "from_text": prev_line.strip()[:160],
                                    "to_text": line.strip()[:160],
                                })
                        prev_sec = curr_sec
                        prev_line = line
                        prev_ln = idx
        except OSError:
            continue

        gaps.sort(key=lambda x: -x["duration_sec"])
        by_cat = {}
        for g in gaps:
            by_cat[g["category"]] = round(by_cat.get(g["category"], 0.0) + g["duration_sec"], 2)

        results[log_name] = {
            "reported_boot_seconds": total_boot_sec,
            "texture_atlases": atlases,
            "error_counts": error_counts,
            "stall_seconds_by_category": by_cat,
            "top_gaps": gaps[:args.limit],
        }

    write_output({
        "instance": inst_meta,
        "logs_analyzed": results,
    }, args.output)


def parse_jar_metadata(jar_path):
    """Extracts mod IDs, dependencies, loader type, and texture stats from a mod JAR."""
    fn = os.path.basename(jar_path)
    size_mb = round(os.path.getsize(jar_path) / (1024.0 * 1024.0), 3)
    mod_ids = []
    req_deps = []
    opt_deps = []
    jij_provided = []
    loader = "unknown"
    png_count = 0
    png_bytes = 0
    is_signed = False

    ignore_deps = {"minecraft", "forge", "neoforge", "fabricloader", "fabric-loader", "fabric", "quilt_loader", "java"}

    try:
        with zipfile.ZipFile(jar_path, "r") as z:
            names = z.namelist()
            for info in z.infolist():
                n = info.filename
                if n.startswith("META-INF/") and (n.endswith(".SF") or n.endswith(".RSA") or n.endswith(".DSA")):
                    is_signed = True
                elif n.endswith(".png") and "/textures/" in n:
                    png_count += 1
                    png_bytes += info.file_size
                elif n.startswith("META-INF/jarjar/") and n.endswith(".jar"):
                    base = os.path.basename(n).lower()
                    jij_provided.append(base.split("-")[0])

            # 1. Forge / NeoForge mods.toml
            toml_path = None
            if "META-INF/neoforge.mods.toml" in names:
                toml_path = "META-INF/neoforge.mods.toml"
                loader = "neoforge"
            elif "META-INF/mods.toml" in names:
                toml_path = "META-INF/mods.toml"
                loader = "forge"

            if toml_path:
                txt = z.read(toml_path).decode("utf-8", errors="replace")
                for m in re.findall(r"\[\[mods\]\](.*?)(?=\[\[|\Z)", txt, re.S):
                    mid = re.search(r'modId\s*=\s*"([^"]+)"', m)
                    if mid:
                        mod_ids.append(mid.group(1))
                for b in re.findall(r"\[\[dependencies\.[^\]]+\]\](.*?)(?=\[\[|\Z)", txt, re.S):
                    did = re.search(r'modId\s*=\s*"([^"]+)"', b)
                    mand = re.search(r"mandatory\s*=\s*(true|false)", b, re.I)
                    if did:
                        d_val = did.group(1)
                        if d_val.lower() in ignore_deps:
                            continue
                        is_req = (not mand) or (mand.group(1).lower() == "true")
                        if is_req:
                            req_deps.append(d_val)
                        else:
                            opt_deps.append(d_val)

            # 2. Fabric fabric.mod.json
            elif "fabric.mod.json" in names:
                loader = "fabric"
                fjson = json.loads(z.read("fabric.mod.json").decode("utf-8", errors="replace"))
                if "id" in fjson:
                    mod_ids.append(fjson["id"])
                for d_id in (fjson.get("depends") or {}):
                    if d_id.lower() not in ignore_deps:
                        req_deps.append(d_id)
                for d_id in (fjson.get("recommends") or {}):
                    if d_id.lower() not in ignore_deps:
                        opt_deps.append(d_id)
                for nested in (fjson.get("jars") or []):
                    if isinstance(nested, dict) and "file" in nested:
                        jij_provided.append(os.path.basename(nested["file"]).split("-")[0].lower())

            # 3. Quilt quilt.mod.json
            elif "quilt.mod.json" in names:
                loader = "quilt"
                qjson = json.loads(z.read("quilt.mod.json").decode("utf-8", errors="replace"))
                ql = qjson.get("quilt_loader", {})
                if "id" in ql:
                    mod_ids.append(ql["id"])
                for dep in (ql.get("depends") or []):
                    d_id = dep.get("id") if isinstance(dep, dict) else str(dep)
                    if d_id and d_id.lower() not in ignore_deps:
                        if isinstance(dep, dict) and dep.get("optional"):
                            opt_deps.append(d_id)
                        else:
                            req_deps.append(d_id)

            # 4. LiteLoader litemod.json
            elif "litemod.json" in names:
                loader = "liteloader"
                ljson = json.loads(z.read("litemod.json").decode("utf-8", errors="replace"))
                if "name" in ljson:
                    mod_ids.append(ljson["name"])
    except Exception:
        pass

    return {
        "file": fn,
        "enabled": fn.endswith(".jar"),
        "size_mb": size_mb,
        "loader": loader,
        "mod_ids": mod_ids,
        "required_dependencies": sorted(list(set(req_deps))),
        "optional_dependencies": sorted(list(set(opt_deps))),
        "jar_in_jar": sorted(list(set(jij_provided))),
        "texture_png_count": png_count,
        "texture_compressed_mb": round(png_bytes / (1024.0 * 1024.0), 3),
        "is_signed": is_signed,
    }


def cmd_audit_mods(args):
    """Scans all mods in an instance, validates dependencies, and deletes approved mods."""
    _, mc_dir = resolve_mc_dir(args.instance)
    mods_dir = os.path.join(mc_dir, "mods")
    if not os.path.isdir(mods_dir):
        write_output({"error": f"Mods directory not found: {mods_dir}"}, args.output)
        sys.exit(1)

    all_mods = []
    for fn in sorted(os.listdir(mods_dir)):
        if not (fn.endswith(".jar") or fn.endswith(".jar.disabled")):
            continue
        p = os.path.join(mods_dir, fn)
        if os.path.isfile(p):
            all_mods.append(parse_jar_metadata(p))

    delete_targets = set()
    if args.delete_list:
        for item in args.delete_list.split(","):
            item = item.strip()
            if item:
                delete_targets.add(item)

    # Validate dependency graph for remaining enabled mods
    provided = {"minecraft", "forge", "neoforge", "fabric", "quilt", "ea", "kotlinforforge", "l2library", "l2harvester", "xaerolib", "flywheel", "ponder"}
    kept_mods = []
    to_remove_mods = []
    for m in all_mods:
        if m["file"] in delete_targets or any(mid in delete_targets for mid in m["mod_ids"]):
            to_remove_mods.append(m)
        else:
            kept_mods.append(m)
            if m["enabled"]:
                for mid in m["mod_ids"]:
                    provided.add(mid)
                for jij in m["jar_in_jar"]:
                    provided.add(jij)

    unmet_dependencies = []
    for m in kept_mods:
        if not m["enabled"]:
            continue
        for req in m["required_dependencies"]:
            if req not in provided and req not in m["mod_ids"]:
                unmet_dependencies.append({"mod_file": m["file"], "missing_required_dependency": req})

    deleted_files = []
    freed_mb = 0.0
    killed_procs = []
    if args.apply and to_remove_mods:
        if unmet_dependencies:
            write_output({
                "status": "aborted_unmet_dependencies",
                "unmet_dependencies": unmet_dependencies,
                "planned_removals": [m["file"] for m in to_remove_mods],
            }, args.output)
            sys.exit(1)
        killed_procs = terminate_instance_processes(args.instance)
        for m in to_remove_mods:
            p = os.path.join(mods_dir, m["file"])
            if os.path.isfile(p):
                freed_mb += m["size_mb"]
                os.remove(p)
                deleted_files.append(m["file"])

    all_mods_sorted = sorted(all_mods, key=lambda x: -x["size_mb"])
    write_output({
        "mods_directory": mods_dir,
        "total_mod_files": len(all_mods),
        "apply_mode": bool(args.apply),
        "killed_processes": killed_procs,
        "unmet_dependencies": unmet_dependencies,
        "planned_or_deleted_files": deleted_files if args.apply else [m["file"] for m in to_remove_mods],
        "freed_mb": round(freed_mb, 2),
        "mods": all_mods_sorted[:args.limit],
    }, args.output)


def get_png_dimensions(data):
    """Extracts width and height from a 32-byte PNG header."""
    if len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return struct.unpack(">II", data[16:24])
    return 0, 0


def cmd_downscale_textures(args):
    """Scans and proportionally downscales oversized PNG textures in unpacked packs and JARs."""
    from PIL import Image

    _, mc_dir = resolve_mc_dir(args.instance)
    killed_procs = terminate_instance_processes(args.instance) if args.apply else []

    unpacked_tasks = []
    for folder_name in ("tacz", "resourcepacks"):
        target_root = os.path.join(mc_dir, folder_name)
        if not os.path.isdir(target_root):
            continue
        for root, _, files in os.walk(target_root):
            fset = set(files)
            for f in files:
                if not f.endswith(".png") or (f + ".mcmeta") in fset:
                    continue
                p = os.path.join(root, f)
                try:
                    with open(p, "rb") as fp:
                        w, h = get_png_dimensions(fp.read(32))
                except OSError:
                    continue
                is_item = ("/textures/item/" in root or "/textures/block/" in root)
                cap = args.max_item_size if is_item else args.max_model_size
                if max(w, h) > cap and min(w, h) >= 16:
                    scale = max(w, h) / float(cap)
                    nw = max(1, int(round(w / scale)))
                    nh = max(1, int(round(h / scale)))
                    unpacked_tasks.append((p, w, h, nw, nh))

    unpacked_old_rgba = sum(w * h * 4 for _, w, h, _, _ in unpacked_tasks)
    unpacked_new_rgba = sum(nw * nh * 4 for _, _, _, nw, nh in unpacked_tasks)
    unpacked_resized = 0

    if args.apply and unpacked_tasks:
        def _resize_disk_png(task):
            p, _, _, nw, nh = task
            try:
                with Image.open(p) as im:
                    im_r = im.resize((nw, nh), Image.Resampling.BOX)
                    im_r.save(p, format="PNG", compress_level=2)
                return 1
            except Exception:
                return 0

        with ThreadPoolExecutor(max_workers=4) as ex:
            unpacked_resized = sum(ex.map(_resize_disk_png, unpacked_tasks))

    # Scan mod JARs
    mods_dir = os.path.join(mc_dir, "mods")
    jar_reports = []
    jar_old_rgba = 0
    jar_new_rgba = 0
    jar_resized_count = 0

    if os.path.isdir(mods_dir):
        for fn in sorted(os.listdir(mods_dir)):
            if not fn.endswith(".jar"):
                continue
            jar_path = os.path.join(mods_dir, fn)
            try:
                with zipfile.ZipFile(jar_path, "r") as zin:
                    names = set(zin.namelist())
                    if any(n.startswith("META-INF/") and (n.endswith(".SF") or n.endswith(".RSA") or n.endswith(".DSA")) for n in names):
                        continue
                    to_resize = {}
                    for info in zin.infolist():
                        n = info.filename
                        if not n.endswith(".png") or "/textures/" not in n or (n + ".mcmeta") in names:
                            continue
                        with zin.open(n) as zf:
                            w, h = get_png_dimensions(zf.read(32))
                        is_item = ("/textures/item/" in n or "/textures/block/" in n)
                        cap = args.max_item_size if is_item else args.max_model_size
                        if max(w, h) > cap and min(w, h) >= 16:
                            scale = max(w, h) / float(cap)
                            nw = max(1, int(round(w / scale)))
                            nh = max(1, int(round(h / scale)))
                            to_resize[n] = (w, h, nw, nh)

                    if not to_resize:
                        continue

                    j_old = sum(v[0] * v[1] * 4 for v in to_resize.values())
                    j_new = sum(v[2] * v[3] * 4 for v in to_resize.values())
                    jar_old_rgba += j_old
                    jar_new_rgba += j_new
                    jar_reports.append({
                        "jar": fn,
                        "oversized_textures": len(to_resize),
                        "old_rgba_mb": round(j_old / (1024.0 * 1024.0), 2),
                        "new_rgba_mb": round(j_new / (1024.0 * 1024.0), 2),
                    })

                    if args.apply:
                        fd, tmp_path = tempfile.mkstemp(suffix=".jar", dir=mods_dir)
                        os.close(fd)
                        try:
                            with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=3) as zout:
                                for info in zin.infolist():
                                    data = zin.read(info.filename)
                                    if info.filename in to_resize:
                                        w, h, nw, nh = to_resize[info.filename]
                                        try:
                                            with Image.open(io.BytesIO(data)) as im:
                                                im_r = im.resize((nw, nh), Image.Resampling.BOX)
                                                buf = io.BytesIO()
                                                im_r.save(buf, format="PNG", compress_level=2)
                                                data = buf.getvalue()
                                            jar_resized_count += 1
                                        except Exception:
                                            pass
                                    zout.writestr(info, data)
                            shutil.move(tmp_path, jar_path)
                        except Exception:
                            if os.path.exists(tmp_path):
                                os.remove(tmp_path)
            except Exception:
                continue

    write_output({
        "apply_mode": bool(args.apply),
        "killed_processes": killed_procs,
        "max_item_size": args.max_item_size,
        "max_model_size": args.max_model_size,
        "unpacked_folders": {
            "oversized_count": len(unpacked_tasks),
            "resized_count": unpacked_resized if args.apply else 0,
            "old_rgba_mb": round(unpacked_old_rgba / (1024.0 * 1024.0), 2),
            "new_rgba_mb": round(unpacked_new_rgba / (1024.0 * 1024.0), 2),
            "saved_rgba_mb": round((unpacked_old_rgba - unpacked_new_rgba) / (1024.0 * 1024.0), 2),
        },
        "mod_jars": {
            "jars_with_oversized_textures": len(jar_reports),
            "oversized_count": sum(r["oversized_textures"] for r in jar_reports),
            "resized_count": jar_resized_count if args.apply else 0,
            "old_rgba_mb": round(jar_old_rgba / (1024.0 * 1024.0), 2),
            "new_rgba_mb": round(jar_new_rgba / (1024.0 * 1024.0), 2),
            "saved_rgba_mb": round((jar_old_rgba - jar_new_rgba) / (1024.0 * 1024.0), 2),
            "details": jar_reports,
        },
    }, args.output)


def cmd_tune_instance(args):
    """Tunes G1GC JVM flags in instance.cfg and low-end mod/client configs."""
    inst_root, mc_dir = resolve_mc_dir(args.instance)
    cfg_path = os.path.join(inst_root, "instance.cfg")
    changes = []
    killed_procs = terminate_instance_processes(args.instance) if args.apply else []

    recommended_jvm = (
        '"-XX:+UseG1GC -XX:+ParallelRefProcEnabled -XX:ParallelGCThreads=2 '
        '-XX:ConcGCThreads=1 -XX:MaxGCPauseMillis=100 -XX:+UnlockExperimentalVMOptions '
        '-XX:+DisableExplicitGC -XX:G1NewSizePercent=20 -XX:G1MaxNewSizePercent=35 '
        '-XX:G1ReservePercent=15 -XX:G1HeapRegionSize=16M '
        '-XX:InitiatingHeapOccupancyPercent=45 -XX:SoftRefLRUPolicyMSPerMB=50"'
    )

    if os.path.isfile(cfg_path):
        with open(cfg_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        new_lines = []
        found_jvm = False
        for line in lines:
            if line.startswith("JvmArgs="):
                found_jvm = True
                new_lines.append(f"JvmArgs={recommended_jvm}\n")
                changes.append("Updated JvmArgs in instance.cfg (IHOP=45, SoftRefLRU=50, G1HeapRegionSize=16M)")
            elif line.startswith("MaxMemAlloc=") and args.set_max_mem and not args.preserve_heap:
                new_lines.append(f"MaxMemAlloc={args.set_max_mem}\n")
                changes.append(f"Updated MaxMemAlloc to {args.set_max_mem} MB")
            else:
                new_lines.append(line)
        if not found_jvm:
            new_lines.append(f"JvmArgs={recommended_jvm}\n")
            changes.append("Added optimized JvmArgs to instance.cfg")
        if args.apply:
            with open(cfg_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)

    # ModernFix config
    mf_path = os.path.join(mc_dir, "config", "modernfix-mixins.properties")
    if os.path.isfile(mf_path):
        with open(mf_path, "r", encoding="utf-8", errors="replace") as f:
            mf_txt = f.read()
        additions = []
        if "mixin.perf.dynamic_resources=true" not in mf_txt:
            additions.append("mixin.perf.dynamic_resources=true")
        if "mixin.perf.clear_mixin_classinfo=true" not in mf_txt:
            additions.append("mixin.perf.clear_mixin_classinfo=true")
        if additions:
            changes.append(f"Enabled {', '.join(additions)} in modernfix-mixins.properties")
            if args.apply:
                with open(mf_path, "a", encoding="utf-8") as f:
                    f.write("\n" + "\n".join(additions) + "\n")

    # options.txt mipmapLevels:0
    opt_path = os.path.join(mc_dir, "options.txt")
    if os.path.isfile(opt_path):
        with open(opt_path, "r", encoding="utf-8", errors="replace") as f:
            opt_txt = f.read()
        if "mipmapLevels:0" not in opt_txt and "mipmapLevels:" in opt_txt:
            changes.append("Set mipmapLevels:0 in options.txt to reduce TextureAtlas VRAM footprint")
            if args.apply:
                opt_txt = re.sub(r"mipmapLevels:\d+", "mipmapLevels:0", opt_txt)
                with open(opt_path, "w", encoding="utf-8") as f:
                    f.write(opt_txt)

    write_output({
        "apply_mode": bool(args.apply),
        "killed_processes": killed_procs,
        "preserve_heap": bool(args.preserve_heap),
        "changes": changes,
    }, args.output)


def find_system_fonts(query=None, limit=50):
    """Discovers .ttf and .otf font files across Linux, Windows, and macOS."""
    home = os.path.expanduser("~")
    font_dirs = [
        "/usr/share/fonts",
        "/usr/local/share/fonts",
        os.path.join(home, ".local", "share", "fonts"),
        os.path.join(home, ".fonts"),
        "C:\\Windows\\Fonts",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"),
        "/System/Library/Fonts",
        "/Library/Fonts",
        os.path.join(home, "Library", "Fonts"),
    ]
    matches = []
    q_lower = query.lower() if query else None
    for d in font_dirs:
        if not d or not os.path.isdir(d):
            continue
        for root, _, files in os.walk(d):
            for f in sorted(files):
                if not (f.lower().endswith(".ttf") or f.lower().endswith(".otf")):
                    continue
                if q_lower and q_lower not in f.lower() and q_lower not in root.lower():
                    continue
                full_p = os.path.join(root, f)
                matches.append({
                    "name": os.path.splitext(f)[0],
                    "file": f,
                    "path": full_p,
                })
                if len(matches) >= limit:
                    return matches
    return matches


def cmd_change_font(args):
    """Lists system fonts or builds a native Vanilla TTF font resourcepack."""
    if args.list_fonts:
        fonts = find_system_fonts(query=args.query, limit=args.limit)
        write_output({
            "query": args.query,
            "count": len(fonts),
            "fonts": fonts,
        }, args.output)
        return

    if not args.instance:
        write_output({"error": "--instance is required when building a font pack"}, args.output)
        sys.exit(1)

    font_path = args.font_path
    if not font_path and args.query:
        found = find_system_fonts(query=args.query, limit=1)
        if found:
            font_path = found[0]["path"]

    if not font_path or not os.path.isfile(font_path):
        write_output({"error": f"Font file not found: {font_path or args.query}"}, args.output)
        sys.exit(1)

    _, mc_dir = resolve_mc_dir(args.instance)
    rp_dir = os.path.join(mc_dir, "resourcepacks")
    os.makedirs(rp_dir, exist_ok=True)
    font_stem = re.sub(r"[^a-zA-Z0-9_-]", "_", os.path.splitext(os.path.basename(font_path))[0])
    ext = os.path.splitext(font_path)[1].lower()
    internal_font_name = f"{font_stem.lower()}{ext}"
    pack_filename = f"{font_stem}-Font.zip"
    pack_path = os.path.join(rp_dir, pack_filename)

    killed_procs = terminate_instance_processes(args.instance) if args.apply else []
    removed_modernui = []

    if args.apply:
        with zipfile.ZipFile(pack_path, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("pack.mcmeta", json.dumps({
                "pack": {
                    "pack_format": 15,
                    "description": f"{font_stem} Custom Font Pack (Native TTF)",
                }
            }, indent=2))
            z.writestr("assets/minecraft/font/default.json", json.dumps({
                "providers": [{
                    "type": "ttf",
                    "file": f"minecraft:{internal_font_name}",
                    "shift": [0.0, 0.5],
                    "size": args.font_size,
                    "oversample": args.oversample,
                }]
            }, indent=2))
            z.write(font_path, f"assets/minecraft/font/{internal_font_name}")

        opt_path = os.path.join(mc_dir, "options.txt")
        if os.path.isfile(opt_path):
            with open(opt_path, "r", encoding="utf-8", errors="replace") as f:
                opt_txt = f.read()
            entry = f'"file/{pack_filename}"'
            if entry not in opt_txt:
                opt_txt = re.sub(
                    r"(resourcePacks:\[.*?)(\])",
                    lambda m: f"{m.group(1)},{entry}]" if m.group(1) != "resourcePacks:[" else f"resourcePacks:[{entry}]",
                    opt_txt,
                )
                with open(opt_path, "w", encoding="utf-8") as f:
                    f.write(opt_txt)

        if args.remove_modernui:
            mods_dir = os.path.join(mc_dir, "mods")
            if os.path.isdir(mods_dir):
                for fn in os.listdir(mods_dir):
                    if "modernui" in fn.lower() and fn.endswith(".jar"):
                        os.remove(os.path.join(mods_dir, fn))
                        removed_modernui.append(fn)

    write_output({
        "apply_mode": bool(args.apply),
        "killed_processes": killed_procs,
        "source_font": font_path,
        "generated_resourcepack": pack_path,
        "enabled_in_options_txt": True,
        "removed_modernui_jars": removed_modernui,
    }, args.output)


def cmd_check_corrupted_saves(args):
    """Detects and optionally removes corrupted worlds in saves/ and saves_corrupted_backup/."""
    _, mc_dir = resolve_mc_dir(args.instance)
    saves_dir = os.path.join(mc_dir, "saves")
    corrupted_backup_dir = os.path.join(mc_dir, "saves_corrupted_backup")
    corrupted_worlds = []
    healthy_worlds = []

    if os.path.isdir(saves_dir):
        for entry in sorted(os.listdir(saves_dir)):
            wdir = os.path.join(saves_dir, entry)
            if not os.path.isdir(wdir):
                continue
            reasons = []
            ldat = os.path.join(wdir, "level.dat")
            ldat_old = os.path.join(wdir, "level.dat_old")
            if not os.path.isfile(ldat) and not os.path.isfile(ldat_old):
                reasons.append("missing_level_dat_and_backup")
            else:
                target_dat = ldat if os.path.isfile(ldat) else ldat_old
                if os.path.getsize(target_dat) == 0:
                    reasons.append("zero_byte_level_dat")
                else:
                    try:
                        with gzip.open(target_dat, "rb") as gf:
                            gf.read(16)
                    except Exception:
                        reasons.append("corrupted_gzip_level_dat")

            region_dir = os.path.join(wdir, "region")
            if os.path.isdir(region_dir):
                zero_mca = 0
                for rf in os.listdir(region_dir):
                    if rf.endswith(".mca"):
                        rp = os.path.join(region_dir, rf)
                        if os.path.getsize(rp) == 0:
                            zero_mca += 1
                if zero_mca > 0:
                    reasons.append(f"{zero_mca}_zero_byte_region_mca_files")

            if reasons:
                corrupted_worlds.append({"world": entry, "path": wdir, "reasons": reasons})
            else:
                healthy_worlds.append(entry)

    has_corrupted_backup_folder = os.path.isdir(corrupted_backup_dir)
    removed = []
    if args.apply:
        terminate_instance_processes(args.instance)
        for cw in corrupted_worlds:
            if os.path.isdir(cw["path"]):
                shutil.rmtree(cw["path"])
                removed.append(cw["path"])
        if has_corrupted_backup_folder:
            shutil.rmtree(corrupted_backup_dir)
            removed.append(corrupted_backup_dir)

    write_output({
        "apply_mode": bool(args.apply),
        "healthy_worlds_count": len(healthy_worlds),
        "corrupted_worlds": corrupted_worlds,
        "has_saves_corrupted_backup_dir": has_corrupted_backup_folder,
        "removed_paths": removed,
    }, args.output)


def cmd_fix_missing_content(args):
    """Scans configs and unpacked gunpacks for missing-content errors that stall Minecraft boot."""
    _, mc_dir = resolve_mc_dir(args.instance)
    fixes = []

    # 1. tacz-common.toml empty PassThroughBlocks = [""]
    tacz_common = os.path.join(mc_dir, "config", "tacz-common.toml")
    if os.path.isfile(tacz_common):
        with open(tacz_common, "r", encoding="utf-8", errors="replace") as f:
            txt = f.read()
        if 'PassThroughBlocks = [""]' in txt:
            fixes.append({
                "type": "invalid_empty_block_tag",
                "file": tacz_common,
                "action": "Replace PassThroughBlocks = [\"\"] with PassThroughBlocks = []",
            })
            if args.apply:
                txt = txt.replace('PassThroughBlocks = [""]', "PassThroughBlocks = []")
                with open(tacz_common, "w", encoding="utf-8") as f:
                    f.write(txt)

    # 2. Scan unpacked tacz gunpacks for malformed lang/*.json, broken tick.json, broken tacz:nbt recipes, and tacz:renew ADS preset
    tacz_dir = os.path.join(mc_dir, "tacz")
    if os.path.isdir(tacz_dir):
        for root, _, files in os.walk(tacz_dir):
            for f in files:
                if not f.endswith(".json"):
                    continue
                p = os.path.join(root, f)
                rel = os.path.relpath(p, mc_dir)
                try:
                    with open(p, "r", encoding="utf-8", errors="replace") as fp:
                        raw = fp.read()
                except OSError:
                    continue

                # Check malformed lang JSON
                if "/lang/" in root:
                    try:
                        json.loads(raw)
                    except json.JSONDecodeError as je:
                        fixes.append({
                            "type": "malformed_lang_json",
                            "file": rel,
                            "error": str(je),
                            "action": "Sanitize control characters / trailing commas or replace with valid empty JSON object if unrecoverable",
                        })
                        if args.apply:
                            cleaned = re.sub(r",\s*([}\]])", r"\1", raw.replace("\r", ""))
                            try:
                                json.loads(cleaned)
                                with open(p, "w", encoding="utf-8") as fp:
                                    fp.write(cleaned)
                            except json.JSONDecodeError:
                                with open(p, "w", encoding="utf-8") as fp:
                                    fp.write("{}\n")

                # Check missing ADS preset tacz:renew in gun display JSONs
                elif "/display/" in root and '"tacz:renew"' in raw:
                    fixes.append({
                        "type": "missing_ads_preset_tacz_renew",
                        "file": rel,
                        "action": "Replace missing tacz:renew ADS preset with tacz:legacy",
                    })
                    if args.apply:
                        with open(p, "w", encoding="utf-8") as fp:
                            fp.write(raw.replace('"tacz:renew"', '"tacz:legacy"'))

                # Check broken minecraft:tick tag referencing missing function
                elif f == "tick.json" and "/tags/functions" in root:
                    try:
                        tdata = json.loads(raw)
                        vals = tdata.get("values", [])
                        if vals:
                            fixes.append({
                                "type": "unverified_tick_function_tag",
                                "file": rel,
                                "values": vals,
                                "action": "Clear broken tick function tag references in gunpack",
                            })
                            if args.apply:
                                tdata["values"] = []
                                with open(p, "w", encoding="utf-8") as fp:
                                    json.dump(tdata, fp, indent=2)
                    except json.JSONDecodeError:
                        pass

                # Check unsupported recipe ingredient tacz:nbt
                elif "/recipes/" in root and '"tacz:nbt"' in raw:
                    fixes.append({
                        "type": "unsupported_recipe_ingredient_tacz_nbt",
                        "file": rel,
                        "action": "Disable broken vanilla crafting recipe using non-existent tacz:nbt ingredient",
                    })
                    if args.apply:
                        os.rename(p, p + ".disabled")

    write_output({
        "apply_mode": bool(args.apply),
        "issues_found": len(fixes),
        "fixes": fixes,
    }, args.output)


class CurseForgeClient:
    """Rate-limited client for CurseForge Core API v1 (Minecraft gameId=432)."""

    BASE_URL = "https://api.curseforge.com/v1"
    REQUESTS_PER_SECOND = 1
    LOCK_FILE = os.path.join(tempfile.gettempdir(), "mc_optimizer_cf_api.lock")

    def __init__(self, api_key):
        self.api_key = api_key
        self.delay = 1.0 / self.REQUESTS_PER_SECOND
        self.last_request_time = 0.0

    def _wait_for_rate_limit(self):
        elapsed = time.monotonic() - self.last_request_time
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

    def _request(self, path, params=None, retries=3):
        url = f"{self.BASE_URL}{path}"
        if params:
            url = f"{url}?{urllib_parse.urlencode(params)}"

        lock_fd = open(self.LOCK_FILE, "w", encoding="utf-8")
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)
            for attempt in range(retries):
                self._wait_for_rate_limit()
                try:
                    req = urllib_request.Request(url)
                    req.add_header("Accept", "application/json")
                    req.add_header("x-api-key", self.api_key)
                    req.add_header("User-Agent", "minecraft-optimizer/1.0")
                    with urllib_request.urlopen(req, timeout=30) as response:
                        self.last_request_time = time.monotonic()
                        return json.loads(response.read().decode("utf-8"))
                except urllib_error.HTTPError as e:
                    self.last_request_time = time.monotonic()
                    if e.code == 429:
                        wait = 2 ** attempt
                        print(
                            f"Rate limited (429), retrying in {wait}s (attempt {attempt + 1}/{retries})...",
                            file=sys.stderr,
                        )
                        if attempt == retries - 1:
                            raise RateLimitError(
                                f"HTTP 429 Too Many Requests from {url}. "
                                f"Rate limit ({self.REQUESTS_PER_SECOND} req/s) exceeded after {retries} retries."
                            ) from e
                        time.sleep(wait)
                        continue
                    if e.code >= 500:
                        wait = 2 ** attempt
                        print(
                            f"Server error {e.code}, retrying in {wait}s (attempt {attempt + 1}/{retries})...",
                            file=sys.stderr,
                        )
                        if attempt == retries - 1:
                            raise RuntimeError(
                                f"Server error {e.code} from {url} after {retries} retries."
                            ) from e
                        time.sleep(wait)
                        continue
                    try:
                        body = e.read().decode("utf-8", errors="replace")[:1000]
                    except OSError:
                        body = str(e.reason)
                    raise RuntimeError(f"HTTP {e.code} from {url} (rate limit {self.REQUESTS_PER_SECOND} req/s): {body}") from e
                except urllib_error.URLError as e:
                    if attempt == retries - 1:
                        raise RuntimeError(f"Failed to connect to {url} after {retries} attempts: {e}") from e
                    time.sleep(2 ** attempt)
        finally:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
                lock_fd.close()
            except OSError:
                pass


def load_env_key(var_name="CURSEFORGE_API_KEY"):
    """Loads an API key from environment or ~/.env without printing it."""
    if os.environ.get(var_name):
        return os.environ[var_name].strip()
    for env_path in (os.path.expanduser("~/.env"), os.path.abspath(".env")):
        if os.path.isfile(env_path):
            try:
                with open(env_path, "r", encoding="utf-8", errors="replace") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith(f"{var_name}="):
                            val = line.split("=", 1)[1].strip().strip('"').strip("'")
                            if val:
                                return val
            except OSError:
                continue
    return None


def download_file_cross_platform(url, dest_path):
    """Downloads url to dest_path using curl, wget, PowerShell, or urllib fallback."""
    sys_name = platform.system().lower()
    if sys_name in ("linux", "darwin"):
        if shutil.which("curl"):
            res = subprocess.run(["curl", "-fL", "-sS", "-o", dest_path, url], check=False)
            if res.returncode == 0 and os.path.isfile(dest_path):
                return "curl"
        if shutil.which("wget"):
            res = subprocess.run(["wget", "-q", "-O", dest_path, url], check=False)
            if res.returncode == 0 and os.path.isfile(dest_path):
                return "wget"
    elif sys_name == "windows":
        if shutil.which("curl.exe"):
            res = subprocess.run(["curl.exe", "-fL", "-sS", "-o", dest_path, url], check=False)
            if res.returncode == 0 and os.path.isfile(dest_path):
                return "curl.exe"
        if shutil.which("powershell"):
            ps_cmd = f"Invoke-WebRequest -Uri '{url}' -OutFile '{dest_path}'"
            res = subprocess.run(["powershell", "-NoProfile", "-Command", ps_cmd], check=False)
            if res.returncode == 0 and os.path.isfile(dest_path):
                return "powershell"

    req = urllib_request.Request(url, headers={"User-Agent": "minecraft-optimizer/1.0"})
    with urllib_request.urlopen(req, timeout=60) as resp, open(dest_path, "wb") as out_f:
        shutil.copyfileobj(resp, out_f)
    return "urllib"


def cmd_update_tacz_gunpacks(args):
    """Searches or downloads TaCZ gunpacks via the CurseForge Core API."""
    api_key = load_env_key("CURSEFORGE_API_KEY")
    if not api_key:
        write_output({
            "error": "CURSEFORGE_API_KEY is missing from ~/.env. Follow the credentials skill protocol to add it.",
        }, args.output)
        sys.exit(1)

    client = CurseForgeClient(api_key)
    _, mc_dir = resolve_mc_dir(args.instance)

    if args.action == "search":
        q = args.query or "tacz"
        resp = client._request("/mods/search", params={
            "gameId": 432,
            "searchFilter": q,
            "gameVersion": args.mc_version,
            "pageSize": min(args.limit, 50),
        })
        items = []
        for mod in (resp.get("data") or [])[:args.limit]:
            items.append({
                "mod_id": mod.get("id"),
                "name": mod.get("name"),
                "slug": mod.get("slug"),
                "summary": mod.get("summary"),
                "download_count": mod.get("downloadCount"),
                "date_modified": mod.get("dateModified"),
            })
        write_output({
            "action": "search",
            "query": q,
            "mc_version": args.mc_version,
            "count": len(items),
            "results": items,
        }, args.output)
        return

    if args.action in ("check-updates", "download"):
        if not args.mod_id:
            write_output({"error": "--mod-id is required for check-updates and download"}, args.output)
            sys.exit(1)
        files_resp = client._request(f"/mods/{args.mod_id}/files", params={
            "gameVersion": args.mc_version,
            "pageSize": min(args.limit, 20),
        })
        files_data = (files_resp.get("data") or [])[:args.limit]
        if not files_data:
            write_output({
                "action": args.action,
                "mod_id": args.mod_id,
                "mc_version": args.mc_version,
                "files": [],
            }, args.output)
            return

        latest = files_data[0]
        dl_url = latest.get("downloadUrl")
        fname = latest.get("fileName") or f"tacz_pack_{args.mod_id}.zip"
        result = {
            "action": args.action,
            "mod_id": args.mod_id,
            "latest_file_id": latest.get("id"),
            "file_name": fname,
            "file_date": latest.get("fileDate"),
            "download_url": dl_url,
            "downloaded": False,
        }

        if args.action == "download" and args.apply and dl_url:
            target_dir = os.path.join(mc_dir, "tacz" if args.install_to == "tacz" else "mods")
            os.makedirs(target_dir, exist_ok=True)
            dest_file = os.path.join(target_dir, fname)
            tool_used = download_file_cross_platform(dl_url, dest_file)
            result["downloaded"] = True
            result["downloader_tool"] = tool_used
            result["installed_path"] = dest_file
            result["valid_zip"] = zipfile.is_zipfile(dest_file)

        write_output(result, args.output)


def cmd_cleanup_saves(args):
    """Terminates running Minecraft process and cleans saves, backups, tacz_default_gun, and logs."""
    _, mc_dir = resolve_mc_dir(args.instance)
    killed_procs = terminate_instance_processes(args.instance) if (args.apply and args.kill_running) else []
    removed = []
    freed_bytes = 0

    def _dir_size(path):
        total = 0
        for r, _, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(r, f))
                except OSError:
                    pass
        return total

    targets = []
    if args.clear_saves:
        saves_dir = os.path.join(mc_dir, "saves")
        if os.path.isdir(saves_dir):
            for entry in sorted(os.listdir(saves_dir)):
                targets.append(os.path.join(saves_dir, entry))

    if args.clear_backups:
        for bname in ("saves_corrupted_backup", "tacz_backup", "tacz_legacy_backup"):
            bp = os.path.join(mc_dir, bname)
            if os.path.exists(bp):
                targets.append(bp)
        for entry in sorted(os.listdir(mc_dir)):
            if entry.startswith("XaeroWaypoints_BACKUP"):
                targets.append(os.path.join(mc_dir, entry))

    if args.reset_tacz_default:
        td = os.path.join(mc_dir, "tacz", "tacz_default_gun")
        if os.path.exists(td):
            targets.append(td)

    if args.clear_logs:
        logs_dir = os.path.join(mc_dir, "logs")
        if os.path.isdir(logs_dir):
            for entry in sorted(os.listdir(logs_dir)):
                if entry.endswith(".log.gz"):
                    targets.append(os.path.join(logs_dir, entry))
        cr_dir = os.path.join(mc_dir, "crash-reports")
        if os.path.isdir(cr_dir):
            for entry in sorted(os.listdir(cr_dir)):
                targets.append(os.path.join(cr_dir, entry))

    for t in targets:
        if os.path.isdir(t):
            freed_bytes += _dir_size(t)
            if args.apply:
                shutil.rmtree(t)
            removed.append(t)
        elif os.path.isfile(t):
            try:
                freed_bytes += os.path.getsize(t)
            except OSError:
                pass
            if args.apply:
                os.remove(t)
            removed.append(t)

    write_output({
        "apply_mode": bool(args.apply),
        "killed_processes": killed_procs,
        "freed_mb": round(freed_bytes / (1024.0 * 1024.0), 2),
        "targets_count": len(removed),
        "targets": removed,
    }, args.output)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Optimize Prism-based Minecraft instances for low-end computers."
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # 1. discover
    p_disc = sub.add_parser("discover", help="Auto-discover Prism/Fjord/MultiMC instances across OS paths")
    p_disc.add_argument("--custom-path", help="Optional custom instance or instances root directory")
    p_disc.add_argument("--limit", type=int, required=True, help="Maximum number of instances to return")
    p_disc.add_argument("--output", required=True, help="Output JSON file path")

    # 2. check-hardware
    p_hw = sub.add_parser("check-hardware", help="Profile CPU, RAM, zram/disk swap, and iGPU Shmem")
    p_hw.add_argument("--instance", help="Optional instance path to inspect running Minecraft process memory")
    p_hw.add_argument("--output", required=True, help="Output JSON file path")

    # 3. analyze-boot
    p_boot = sub.add_parser("analyze-boot", help="Analyze latest.log and debug.log boot timestamp gaps")
    p_boot.add_argument("--instance", required=True, help="Path to the Minecraft instance directory")
    p_boot.add_argument("--min-gap-seconds", type=float, default=3.0, help="Minimum gap in seconds to report")
    p_boot.add_argument("--limit", type=int, required=True, help="Maximum number of timestamp gaps to return")
    p_boot.add_argument("--output", required=True, help="Output JSON file path")

    # 4. audit-mods
    p_mods = sub.add_parser("audit-mods", help="Scan mods across Forge/NeoForge/Fabric/Quilt/LiteLoader and verify dependencies")
    p_mods.add_argument("--instance", required=True, help="Path to the Minecraft instance directory")
    p_mods.add_argument("--limit", type=int, required=True, help="Maximum number of mod entries to return in output")
    p_mods.add_argument("--delete-list", help="Comma-separated list of mod filenames or mod IDs to remove")
    p_mods.add_argument("--apply", action="store_true", help="Execute deletion after verifying zero broken dependencies")
    p_mods.add_argument("--output", required=True, help="Output JSON file path")

    # 5. downscale-textures
    p_tex = sub.add_parser("downscale-textures", help="Proportionally downscale oversized 2K/4K/8K textures in gunpacks and JARs")
    p_tex.add_argument("--instance", required=True, help="Path to the Minecraft instance directory")
    p_tex.add_argument("--max-item-size", type=int, default=128, help="Max dimension for 2D item/block atlas textures")
    p_tex.add_argument("--max-model-size", type=int, default=512, help="Max dimension for 3D gun/entity UV textures")
    p_tex.add_argument("--apply", action="store_true", help="Modify oversized textures in place")
    p_tex.add_argument("--output", required=True, help="Output JSON file path")

    # 6. tune-instance
    p_tune = sub.add_parser("tune-instance", help="Tune G1GC flags in instance.cfg and low-end mod configs")
    p_tune.add_argument("--instance", required=True, help="Path to the Minecraft instance directory")
    p_tune.add_argument("--preserve-heap", action="store_true", default=True, help="Preserve user MaxMemAlloc setting")
    p_tune.add_argument("--set-max-mem", type=int, help="Optional MaxMemAlloc override in MB")
    p_tune.add_argument("--apply", action="store_true", help="Write config updates to disk")
    p_tune.add_argument("--output", required=True, help="Output JSON file path")

    # 7. change-font
    p_font = sub.add_parser("change-font", help="List system fonts or build a native Vanilla TTF font resourcepack")
    p_font.add_argument("--instance", help="Path to the Minecraft instance directory")
    p_font.add_argument("--list-fonts", action="store_true", help="List available system TTF/OTF fonts")
    p_font.add_argument("--query", help="Font name substring to search for (e.g. 'SUSE-SemiBold')")
    p_font.add_argument("--font-path", help="Explicit path to a .ttf or .otf file")
    p_font.add_argument("--font-size", type=float, default=11.0, help="TTF provider font size (default 11.0)")
    p_font.add_argument("--oversample", type=float, default=4.0, help="TTF provider oversample (default 4.0)")
    p_font.add_argument("--remove-modernui", action="store_true", help="Remove heavy ModernUI mod JAR if installed")
    p_font.add_argument("--limit", type=int, default=50, help="Maximum fonts to return when listing")
    p_font.add_argument("--apply", action="store_true", help="Generate resourcepack and enable in options.txt")
    p_font.add_argument("--output", required=True, help="Output JSON file path")

    # 8. check-corrupted-saves
    p_csav = sub.add_parser("check-corrupted-saves", help="Detect and clear corrupted worlds in saves/")
    p_csav.add_argument("--instance", required=True, help="Path to the Minecraft instance directory")
    p_csav.add_argument("--apply", action="store_true", help="Remove corrupted world directories")
    p_csav.add_argument("--output", required=True, help="Output JSON file path")

    # 9. fix-missing-content
    p_fix = sub.add_parser("fix-missing-content", help="Repair missing-content errors in unpacked packs and configs")
    p_fix.add_argument("--instance", required=True, help="Path to the Minecraft instance directory")
    p_fix.add_argument("--apply", action="store_true", help="Apply JSON/TOML fixes to suppress boot errors")
    p_fix.add_argument("--output", required=True, help="Output JSON file path")

    # 10. update-tacz-gunpacks
    p_cf = sub.add_parser("update-tacz-gunpacks", help="Search and download TaCZ gunpacks via CurseForge Core API")
    p_cf.add_argument("--instance", required=True, help="Path to the Minecraft instance directory")
    p_cf.add_argument("--action", choices=["search", "check-updates", "download"], required=True)
    p_cf.add_argument("--query", help="Search query string for CurseForge")
    p_cf.add_argument("--mod-id", type=int, help="CurseForge project/mod ID")
    p_cf.add_argument("--mc-version", default="1.20.1", help="Target Minecraft version (default 1.20.1)")
    p_cf.add_argument("--install-to", choices=["tacz", "mods"], default="tacz", help="Target directory for download")
    p_cf.add_argument("--limit", type=int, required=True, help="Max results to retrieve")
    p_cf.add_argument("--apply", action="store_true", help="Download and install the archive")
    p_cf.add_argument("--output", required=True, help="Output JSON file path")

    # 11. cleanup-saves
    p_clean = sub.add_parser("cleanup-saves", help="Kill active Minecraft process and clean saves, backups, and logs")
    p_clean.add_argument("--instance", required=True, help="Path to the Minecraft instance directory")
    p_clean.add_argument("--kill-running", action="store_true", default=True, help="Terminate running Minecraft process")
    p_clean.add_argument("--clear-saves", action="store_true", help="Delete all worlds in saves/")
    p_clean.add_argument("--clear-backups", action="store_true", help="Delete tacz_backup, tacz_legacy_backup, Xaero backups")
    p_clean.add_argument("--reset-tacz-default", action="store_true", help="Delete tacz/tacz_default_gun so TaCZ unpacks a fresh copy")
    p_clean.add_argument("--clear-logs", action="store_true", help="Delete archived logs/*.log.gz and crash-reports/*")
    p_clean.add_argument("--apply", action="store_true", help="Execute deletions")
    p_clean.add_argument("--output", required=True, help="Output JSON file path")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    dispatch = {
        "discover": cmd_discover,
        "check-hardware": cmd_check_hardware,
        "analyze-boot": cmd_analyze_boot,
        "audit-mods": cmd_audit_mods,
        "downscale-textures": cmd_downscale_textures,
        "tune-instance": cmd_tune_instance,
        "change-font": cmd_change_font,
        "check-corrupted-saves": cmd_check_corrupted_saves,
        "fix-missing-content": cmd_fix_missing_content,
        "update-tacz-gunpacks": cmd_update_tacz_gunpacks,
        "cleanup-saves": cmd_cleanup_saves,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()
