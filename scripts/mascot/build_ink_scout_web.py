"""Build the WEB RUNTIME SUBSET of the approved Ink Scout mascot pack.

    python scripts/mascot/build_ink_scout_web.py [--pack C:/Users/nguye/Projects/Fanfic-World-Mascot] [--check]

Source of truth: the UNPACKED canonical project (never the 73 MB ZIP). Output:
``web/public/mascot/ink-scout/`` with

* ``runtime/ink-scout*.js`` — the supplied player + walk rig + physics + presence (v1.3.0), each BYTE-IDENTICAL (sha256 recorded);
* the supplied optimized WebP sprite atlases for the 10 AI states and the 8
  movement transitions, the 9 static state posters (reduced motion) and the two
  poses the runtime shows after a movement — copied byte-for-byte, same
  relative paths as the pack, never re-encoded, recolored or mirrored;
* ``manifest.json`` — the pack manifest reduced to what the runtime reads
  (states / animations / transitions / poses), PNG / Lottie / animated-WebP
  keys removed, animation posters pointed at the static WebP (no PNG on the web);
* ``SUBSET.json`` — inventory: every file with bytes + sha256 (+ equality with
  the pack), totals, and what was deliberately excluded.

``--check`` rebuilds in memory and fails if the committed subset drifted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "web" / "public" / "mascot" / "ink-scout"
DEFAULT_PACK = Path("C:/Users/nguye/Projects/Fanfic-World-Mascot")

STATES = ("idle", "hover", "listening", "thinking", "searching", "writing", "answering", "success", "error", "offline")
TRANSITIONS = ("hop-left", "hop-right", "walk", "jump-onto-panel", "sit-down", "stand-up", "peek-out", "return-home")
#: v1.3.0 directional walk: the physics runtime plays `walk-left` / `walk-right` (independent artwork, never mirrored).
WALK_TRANSITIONS = ("walk-left", "walk-right")
POSES = ("sitting-edge", "peeking")  # shown by the runtime at the end of sit-down / peek-out
#: Runtime scripts, in the ORDER the pack requires (classic IIFEs): player -> walk rig -> physics -> presence. Every one is copied
#: BYTE-IDENTICAL (sha256 in SUBSET.json); the web never edits the approved runtime.
RUNTIME = ("ink-scout.js", "ink-scout-walk-rig.js", "ink-scout-physics.js", "ink-scout-presence.js")
STATE_KEYS = ("animation", "playback", "after", "static", "image", "loop", "durationMs", "fps", "frames")
ANIM_KEYS = ("image", "loop", "durationMs", "fps", "frames")
#: Extra keys the physics runtime reads from the directional walk animations (stride, frame count, rig description).
WALK_ANIM_KEYS = ANIM_KEYS + ("direction", "cycleFrames", "strideAt128Px", "rig")
#: Budget for the whole web subset (bytes on disk). The v1.3.0 pack is ~94.7 MB; the subset must stay under 5% of it.
#: v1.0 subset was 2.22 MB; v1.3.0 adds the directional walk sprites (~1.2 MB, fetched lazily and only when the mascot walks),
#: the walk rig parts (PNG only in the pack, ~165 KB), four motion poses and three small runtime scripts.
SUBSET_BUDGET = 4_100_000


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def build(pack: Path) -> tuple[dict, dict[str, Path]]:
    m = pack / "mascot"
    man = json.loads((m / "manifest.json").read_text(encoding="utf-8"))
    if man["version"] != "1.3.0":
        raise SystemExit(f"expected the Ink Scout 1.3.0 pack, found {man['version']}")
    files: dict[str, Path] = {f"runtime/{name}": m / "runtime" / name for name in RUNTIME}

    states = {}
    for s in STATES:
        spec = man["states"][s]
        states[s] = {k: spec[k] for k in STATE_KEYS}
        files[spec["image"]] = m / spec["image"]
        files[spec["static"]] = m / spec["static"]

    anims, trans = {}, {}
    for t in TRANSITIONS:
        tr = man["transitions"][t]
        name = tr["animation"]
        spec = man["animations"][name]
        a = {k: spec[k] for k in ANIM_KEYS}
        # Reduced motion never needs the PNG poster: the host repositions
        # instantly and shows the static state / pose (see AiCompanion.tsx).
        a["poster"] = man["states"]["idle"]["static"]
        anims[name] = a
        trans[t] = {"animation": name, "durationMs": tr["durationMs"]}
        files[spec["image"]] = m / spec["image"]

    for t in WALK_TRANSITIONS:
        tr = man["transitions"][t]
        name = tr["animation"]
        spec = man["animations"][name]
        a = {k: spec[k] for k in WALK_ANIM_KEYS}
        a["poster"] = man["states"]["idle"]["static"]  # reduced motion never walks: the host repositions instantly
        anims[name] = a
        trans[t] = {"animation": name, "durationMs": tr["durationMs"]}
        files[spec["image"]] = m / spec["image"]
        for part in spec["rig"]["parts"].values():  # PNG only in the pack (no WebP export): copied untouched
            files[part["image"]] = m / part["image"]

    # Physics: four procedural motion poses (pickup / anticipation / airborne / landing) and the directional walk cycles.
    physics = {"poses": dict(man["physics"]["poses"]), "walkCycles": dict(man["physics"]["walkCycles"])}
    for rel in physics["poses"].values():
        files[rel] = m / rel

    poses = {}
    for p in POSES:
        poses[p] = {"webp": man["poses"][p]["webp"]}
        files[man["poses"][p]["webp"]] = m / man["poses"][p]["webp"]

    # The pack ships some byte-identical files under two paths (measured:
    # transitions/jump-onto-panel/sprite.webp == transitions/hop-right/sprite.webp).
    # Serve ONE copy: point every reference at the first path with that hash.
    first_by_hash: dict[str, str] = {}
    alias: dict[str, str] = {}
    for rel in sorted(files):
        h = sha(files[rel])
        if h in first_by_hash:
            alias[rel] = first_by_hash[h]
        else:
            first_by_hash[h] = rel
    for rel in alias:
        files.pop(rel)
    for group in (states, anims):
        for spec in group.values():
            for k in ("image", "static", "poster"):
                if spec.get(k) in alias:
                    spec[k] = alias[spec[k]]
    # Rig parts live one level deeper (animations[*].rig.parts[*].image). The pack reuses ONE left-facing boot cutout for both boots
    # of the left rig (see runtime/README.txt), so near-boot.png == far-boot.png byte for byte: point both at the single copy.
    for spec in anims.values():
        for part in (spec.get("rig") or {}).get("parts", {}).values():
            if part["image"] in alias:
                part["image"] = alias[part["image"]]
    for spec in physics["poses"], physics["walkCycles"]:
        for k, v in list(spec.items()):
            if v in alias:
                spec[k] = alias[v]

    web_manifest = {
        "schemaVersion": man["schemaVersion"], "id": man["id"], "name": man["name"], "version": man["version"],
        "rendering": {k: man["rendering"][k] for k in ("primary", "frameSize", "displayPx", "reducedMotion",
                                                        "pauseWhenHidden", "lazyLoad", "maxDecodedSpriteSheets")},
        # identity rules only (mirrorAllowed=false, streak side); the PNG reference
        # path stays in the pack — the web never downloads it.
        "identity": {k: v for k, v in (man.get("identity") or {}).items() if k != "reference"},
        "states": states, "animations": anims, "transitions": trans, "poses": poses, "physics": physics,
    }
    web_manifest["dedupedAliases"] = alias
    return web_manifest, files


def inventory(web_manifest: dict, files: dict[str, Path], pack: Path) -> dict:
    items = []
    for rel, src in sorted(files.items()):
        items.append({"path": rel, "bytes": src.stat().st_size, "sha256": sha(src)})
    manifest_bytes = len(json.dumps(web_manifest, ensure_ascii=False, separators=(",", ":")).encode())
    pack_bytes = sum(f.stat().st_size for f in (pack / "mascot").rglob("*") if f.is_file())
    total = sum(i["bytes"] for i in items) + manifest_bytes
    by_kind: dict[str, int] = {}
    for i in items:
        p = i["path"]
        kind = ("runtime" if p.startswith("runtime/") else "static-poster" if "/states/" in p
                else "walk-rig-part" if "/rig/" in p else "walk-sprite" if "/walk-left/" in p or "/walk-right/" in p
                else "pose" if p.startswith("poses/") else "transition-sprite"
                if p.startswith("transitions/") or "/walk/" in p else "state-sprite")
        by_kind[kind] = by_kind.get(kind, 0) + i["bytes"]
    return {
        "source": "unpacked canonical project (mascot/), NOT the ZIP",
        "runtimeUnchanged": True,
        "files": items, "manifestBytes": manifest_bytes, "totalBytes": total, "budgetBytes": SUBSET_BUDGET,
        "packBytes": pack_bytes, "byKind": by_kind,
        "excluded": ["sources/ (generation sheets)", "*.png sprite atlases / posters / master PNGs (except the walk rig parts, PNG-only in the pack)",
                     "Lottie animation.json (embedded PNG frames)", "animated.webp", "sprite.json (coords are in manifest)",
                     "rig.json (the rig description is inlined in the web manifest)",
                     "expressions/", "poses/ except sitting-edge, peeking and the four motion poses", "stickers/ (not integrated)",
                     "master front/side/back/three-quarter references", "qa/, tools/, vendor/, node_modules/, the ZIP"],
    }


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack", default=str(DEFAULT_PACK))
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args(argv)
    pack = Path(a.pack)
    web_manifest, files = build(pack)
    inv = inventory(web_manifest, files, pack)
    if inv["totalBytes"] > SUBSET_BUDGET:
        raise SystemExit(f"web subset {inv['totalBytes']} B exceeds budget {SUBSET_BUDGET} B")
    manifest_text = json.dumps(web_manifest, ensure_ascii=False, separators=(",", ":"))
    inv_text = json.dumps(inv, ensure_ascii=False, indent=1) + "\n"
    if a.check:
        bad = [rel for rel, src in files.items() if not (OUT / rel).is_file() or sha(OUT / rel) != sha(src)]
        if (OUT / "manifest.json").read_text(encoding="utf-8") != manifest_text:
            bad.append("manifest.json")
        extra = sorted(str(p.relative_to(OUT)).replace("\\", "/") for p in OUT.rglob("*") if p.is_file()
                       and str(p.relative_to(OUT)).replace("\\", "/") not in set(files) | {"manifest.json", "SUBSET.json"})
        if bad or extra:
            print("DRIFT:", bad, "extra:", extra)
            return 1
        print("subset OK:", len(files), "files +manifest,", inv["totalBytes"], "B")
        return 0
    if OUT.exists():
        shutil.rmtree(OUT)
    for rel, src in files.items():
        dst = OUT / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    (OUT / "manifest.json").write_text(manifest_text, encoding="utf-8")
    (OUT / "SUBSET.json").write_text(inv_text, encoding="utf-8")
    print(f"wrote {len(files)} files + manifest ({inv['manifestBytes']} B) = {inv['totalBytes']} B "
          f"(pack {inv['packBytes']} B) by kind {inv['byKind']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
