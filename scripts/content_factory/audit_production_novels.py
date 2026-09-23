"""Audit all production novels in Appwrite for text chapters and audio tracks."""
import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Safe encoding
for s in (sys.stdout, sys.stderr):
    if hasattr(s, "reconfigure"):
        try: s.reconfigure(encoding="utf-8", errors="replace")
        except Exception: pass

load_dotenv(PROJECT_ROOT / "server" / ".env.production", override=True)
from server.config import get_settings
from server.appwrite_store import AppwriteMetadataStore

def main():
    store = AppwriteMetadataStore(get_settings().appwrite)
    print("Fetching novels from Appwrite...")
    novels = store.list_novels(published_only=False)
    print(f"Total novels found: {len(novels)}")
    
    # Query chapters per novel
    novel_ids = [n.novel_id for n in novels]
    print("Fetching chapter counts...")
    raw_counts = store.chapter_counts(novel_ids)
    
    print("Fetching audio counts...")
    audio_counts = store.audio_chapter_counts(novel_ids)
    
    rows = []
    print("\nAuditing novels...")
    for idx, nov in enumerate(novels, 1):
        nid = nov.novel_id
        title = nov.title or "Untitled"
        chs = store.list_chapters(nid)
        
        # Check text content of chapters: non-empty readable text (>50 chars)
        readable_chs = [
            c for c in chs
            if (getattr(c, "content", "") or "").strip() and len(getattr(c, "content", "").strip()) > 50
        ]
        
        audio_cnt = audio_counts.get(nid, 0)
        has_direct_audio = bool(getattr(nov, "dub_audio_key", None))
        effective_audio_cnt = audio_cnt + (1 if has_direct_audio and audio_cnt == 0 else 0)
        
        classification = "READABLE_FANFIC" if len(readable_chs) >= 1 else "LEGACY_AUDIO_ONLY"
        
        rows.append({
            "novel_id": nid,
            "title": title,
            "text_chapters": len(readable_chs),
            "raw_chapters": len(chs),
            "audio_tracks": effective_audio_cnt,
            "classification": classification,
            "state": nov.state.value if hasattr(nov.state, "value") else str(nov.state),
            "fandom": getattr(nov, "fandom", "") or getattr(nov, "fandom_ids", []),
            "tags": getattr(nov, "tags", []) or [],
        })

    # Sort: READABLE_FANFIC first, then by text_chapters desc
    rows.sort(key=lambda r: (1 if r["classification"] == "READABLE_FANFIC" else 0, r["text_chapters"]), reverse=True)

    readable_count = sum(1 for r in rows if r["classification"] == "READABLE_FANFIC")
    legacy_count = sum(1 for r in rows if r["classification"] == "LEGACY_AUDIO_ONLY")
    
    print(f"\n=======================================================")
    print(f"AUDIT SUMMARY: {len(rows)} TOTAL NOVELS")
    print(f" - READABLE_FANFIC: {readable_count}")
    print(f" - LEGACY_AUDIO_ONLY: {legacy_count}")
    print(f"=======================================================\n")

    print("| novel_id | title | text chapters | audio tracks | classification | state |")
    print("|---|---|---|---|---|---|")
    for r in rows:
        print(f"| `{r['novel_id']}` | {r['title']} | {r['text_chapters']} | {r['audio_tracks']} | **{r['classification']}** | {r['state']} |")
        
    out_file = PROJECT_ROOT / "scripts" / "content_factory" / "novel_audit_result.json"
    out_file.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nWrote full audit to {out_file}")

if __name__ == "__main__":
    main()
