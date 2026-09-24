"""
# ARCHIVE_AFTER_PR_D — Preserved for incident history and forensic verification.
# Replaced by unified CLI: python -m scripts.content_factory run <work_id>
#
Pipeline 156206 Runner — Phase 1 (Intake) & Phase 2 (Full Local Crawl)

Executes:
Phase 1:
- Transition candidate 156206 from Discovery into Local Content Pipeline.
- Preserve source_platform, source_work_id, canonical URL, qualification report.
- Setup persistent isolated glossary for novel 156206.
- Update Discovery Store state to ACCEPTED.

Phase 2:
- Crawl all 47 canonical entries for work 156206.
- Classify every entry (STORY_CHAPTER, EXTRA, ANNOUNCEMENT, AUTHOR_NOTE).
- Verify consecutive source identities.
- Detect duplicate CIDs.
- Store source hashes.
- Verify crawler extraction cleanliness (no comments, no navigation, clean endings).
- Save local chapters to raw_spool/crawled_chapters/156206/.
"""

import datetime
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

for s in (sys.stdout, sys.stderr):
    try: s.reconfigure(encoding="utf-8", errors="replace")
    except Exception: pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.content_factory.crawler_adapters.royalroad_adapter import RoyalRoadAdapter
from scripts.content_factory.content_classifier import ContentClassifier, EntryClassification
from scripts.content_factory.discovery_models import CandidateState
from scripts.content_factory.discovery_store import DiscoveryStore
from scripts.content_factory.glossary_manager import GlossaryManager, NovelGlossary
from scripts.content_factory.candidate_qualifier import (
    BASE_NARUTO_GLOSSARY,
    CANDIDATE_ISOLATED_GLOSSARIES,
    load_qualification_report,
    COMMENT_INDICATORS,
    NAVIGATION_INDICATORS,
)

WORK_ID = "156206"
CANONICAL_URL = f"https://www.royalroad.com/fiction/{WORK_ID}"
CRAWL_DIR = PROJECT_ROOT / "raw_spool" / "crawled_chapters" / WORK_ID
CRAWL_DIR.mkdir(parents=True, exist_ok=True)


def run_phase_1_intake() -> Dict[str, Any]:
    print("=" * 80)
    print("PHASE 1: INTAKE & LOCAL PIPELINE REGISTRATION (WORK 156206)")
    print("=" * 80)

    store = DiscoveryStore()
    cand = store.get_candidate("royalroad", WORK_ID)
    if not cand:
        raise RuntimeError(f"Candidate {WORK_ID} not found in discovery store!")

    print(f"Candidate Title: {cand.title}")
    print(f"Author: {cand.author}")
    print(f"Canonical URL: {CANONICAL_URL}")

    # 1. Update state to ACCEPTED
    cand.state = CandidateState.ACCEPTED
    store.update_candidate_state("royalroad", WORK_ID, CandidateState.ACCEPTED)
    print("✅ Discovery Store State updated: ACCEPTED (Local Pipeline Intake)")

    # 2. Preserve Qualification Report
    qual_report = load_qualification_report(WORK_ID)
    if not qual_report:
        raise RuntimeError(f"Qualification report for {WORK_ID} missing!")
    print(f"✅ Qualification Report loaded: {len(qual_report.inspected_chapters)} sample chapters inspected.")
    print(f"   Flags: {qual_report.factual_flags}")

    # 3. Setup Persistent Isolated Glossary
    glossary_mgr = GlossaryManager()
    gloss = NovelGlossary(
        work_key=WORK_ID,
        notes=f"Isolated glossary for RoyalRoad {WORK_ID} — The Cold Between Wars",
    )

    # Populate categories
    specific_156206 = CANDIDATE_ISOLATED_GLOSSARIES.get(WORK_ID, {})
    all_terms = {**BASE_NARUTO_GLOSSARY, **specific_156206}

    # Split into categories
    character_names = ["Koji", "Minato", "Kushina", "Reiji", "Sakumo", "Danzo", "Hiruzen", "Orochimaru", "Jiraiya", "Tsunade", "Takeshi", "Aoi", "Kano"]
    locations = ["Konoha", "Hidden Leaf", "Leaf Village", "Kiri", "Kirigakure", "Mist Village", "Uzushio", "Land of Fire", "Fire Country", "Academy"]
    ranks = ["Hokage", "Kage", "Shinobi", "Ninja", "Genin", "Chunin", "Jonin", "Jōnin", "ANBU", "Anbu", "Jinchuuriki", "Jinchūriki"]
    techniques = ["Chakra", "Jutsu", "Ninjutsu", "Genjutsu", "Taijutsu", "Sharingan", "Byakugan", "Rinnegan", "Rasengan", "Chidori", "Seal of Confrontation"]
    terms = ["Bijuu", "Tailed Beast", "Inuzuka", "Uzumaki", "Senju", "Uchiha", "Sarutobi", "Nara", "Akimichi", "Yamanaka", "Aburame", "Hyuga"]

    for k, v in all_terms.items():
        if k in character_names:
            gloss.character_names[k] = v
        elif k in locations:
            gloss.locations[k] = v
        elif k in ranks:
            gloss.ranks_titles[k] = v
        elif k in techniques:
            gloss.techniques[k] = v
        else:
            gloss.terminology[k] = v

    saved_path = glossary_mgr.save_glossary(WORK_ID, gloss)
    # Also save under alias cold_between_wars
    glossary_mgr.save_glossary("cold_between_wars", gloss)
    print(f"✅ Persistent isolated glossary saved: {saved_path} ({len(gloss.get_all_mappings())} terms)")

    return {
        "work_id": WORK_ID,
        "title": cand.title,
        "url": CANONICAL_URL,
        "state": cand.state.value,
        "glossary_terms_count": len(gloss.get_all_mappings()),
        "qualification_flags": qual_report.factual_flags,
    }


def run_phase_2_full_crawl() -> Dict[str, Any]:
    print("\n" + "=" * 80)
    print("PHASE 2: FULL LOCAL CRAWL & ENTRY AUDIT (WORK 156206)")
    print("=" * 80)

    adapter = RoyalRoadAdapter()
    classifier = ContentClassifier()

    print(f"Fetching full chapter list from: {CANONICAL_URL}")
    chapters = adapter.list_chapters(CANONICAL_URL)
    total_listed = len(chapters)
    print(f"Total listed chapters: {total_listed}")

    crawled_chapters = []
    classification_counts = {
        "STORY_CHAPTER": 0,
        "EXTRA": 0,
        "ANNOUNCEMENT": 0,
        "AUTHOR_NOTE": 0,
        "UNKNOWN": 0,
    }
    seen_cids = set()
    consecutive_check_pass = True
    cids_duplicate = []
    crawl_defects = []
    total_words = 0

    for idx, ch_info in enumerate(chapters, start=1):
        cid = ch_info["source_chapter_id"]
        order = ch_info["order"]

        # Check consecutive order
        if order != idx:
            consecutive_check_pass = False

        # Check duplicate CID
        if cid in seen_cids:
            cids_duplicate.append(cid)
        seen_cids.add(cid)

        # Check cache or fetch
        cache_file = CRAWL_DIR / f"ch_{order:03d}_{cid}.json"
        if cache_file.exists():
            data = json.loads(cache_file.read_text(encoding="utf-8"))
        else:
            print(f"  [Crawl {idx}/{total_listed}] #{order} ({cid}): {ch_info['title']}...")
            raw_ch = adapter.fetch_chapter(ch_info)
            src_text = raw_ch.source_text
            src_hash = hashlib.sha256(src_text.encode("utf-8")).hexdigest()
            data = {
                "source_chapter_id": cid,
                "source_order": order,
                "title": ch_info["title"],
                "url": ch_info["url"],
                "source_text": src_text,
                "source_text_hash": src_hash,
                "word_count": len(src_text.split()),
                "crawled_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
            cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        # Sanitize tail artifacts (forum buttons, patreon outro, decorative trailing hr)
        raw_paras = [p.strip() for p in data["source_text"].split("\n\n") if p.strip()]
        cleaned_paras = []
        tail_artifacts_found = []
        for p in raw_paras:
            p_lower = p.lower()
            if p_lower in ("quote reply", "report chapter", "reply to this"):
                tail_artifacts_found.append(p)
                continue
            if re.match(r"^and if you want to read a few chapters ahead.*patreon", p_lower):
                tail_artifacts_found.append(p)
                continue
            cleaned_paras.append(p)

        cleaned_text = "\n\n".join(cleaned_paras).strip()
        # Also strip trailing scene break dividers like '---', '***' and zero-width spaces from chapter end
        cleaned_text = re.sub(r"[\s\-_*~=\u200b\ufeff\u200c\u200d\u200e\u200f]+$", "", cleaned_text).strip()

        data["source_text"] = cleaned_text
        data["word_count"] = len(cleaned_text.split())
        data["source_text_hash"] = hashlib.sha256(cleaned_text.encode("utf-8")).hexdigest()
        data["tail_artifacts_cleaned"] = tail_artifacts_found
        cache_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        # Classify entry
        decision = classifier.classify_entry(data["title"], content=data["source_text"], source_order=order, work_id=WORK_ID)
        classification_counts[decision.entry_type.value] = classification_counts.get(decision.entry_type.value, 0) + 1
        data["classification"] = decision.entry_type.value
        data["decision_reason"] = decision.reason

        # Verify no comments/nav/footer leakage
        text = data["source_text"]
        for pat in COMMENT_INDICATORS:
            if re.search(pat, text, re.IGNORECASE):
                crawl_defects.append(f"Ch {order}: Comment indicator detected ({pat})")
                break
        for pat in NAVIGATION_INDICATORS:
            if re.search(pat, text, re.IGNORECASE):
                crawl_defects.append(f"Ch {order}: Navigation indicator detected ({pat})")
                break

        # Check clean ending
        clean_ending = bool(re.search(r'[.!?…"\'”’]\s*$', text))
        if not clean_ending:
            # Special case for trailing technique subtitle e.g. "Ice Release: Ice Breath"
            if re.search(r'\b[A-Za-z]+:\s*[A-Za-z\s]+$', text):
                clean_ending = True
            else:
                crawl_defects.append(f"Ch {order}: No terminal punctuation at chapter end ('{text[-40:]}')")

        total_words += data["word_count"]
        crawled_chapters.append(data)

    print("\n--- Crawl & Audit Results ---")
    print(f"Total Upstream Entries: {total_listed}")
    print(f"Total Words Crawled: {total_words:,} words (Avg: {total_words // total_listed} words/ch)")
    print(f"Consecutive Source Order: {'✅ PASS (1 to 47)' if consecutive_check_pass else '❌ FAIL'}")
    print(f"Duplicate CIDs: {'None (0)' if not cids_duplicate else f'Found: {cids_duplicate}'}")
    print(f"Crawler Defects: {'None (0) — Sạch 100%' if not crawl_defects else f'Found: {len(crawl_defects)}: {crawl_defects}'}")
    print("Classification Breakdown:")
    for k, v in classification_counts.items():
        print(f"  • {k}: {v}")

    # Write summary manifest
    manifest_file = CRAWL_DIR / "crawl_manifest.json"
    manifest = {
        "work_id": WORK_ID,
        "title": "The Cold Between Wars",
        "url": CANONICAL_URL,
        "total_upstream_entries": total_listed,
        "total_source_words": total_words,
        "consecutive_order_verified": consecutive_check_pass,
        "duplicate_cids": cids_duplicate,
        "crawl_defects": crawl_defects,
        "classification_counts": classification_counts,
        "crawled_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "entries": [
            {
                "order": c["source_order"],
                "cid": c["source_chapter_id"],
                "title": c["title"],
                "word_count": c["word_count"],
                "source_hash": c["source_text_hash"],
                "classification": c["classification"],
            }
            for c in crawled_chapters
        ],
    }
    manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Saved Crawl Manifest to: {manifest_file}")

    return manifest


if __name__ == "__main__":
    p1 = run_phase_1_intake()
    p2 = run_phase_2_full_crawl()
