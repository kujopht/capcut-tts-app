# Living Novel Continuous Update Semantics Design (V1)

*Document Version: 1.0.0*  
*Target Environment: Fanfic World Content Ingestion Pipeline*  
*Status: Approved Design Specification*

---

## 1. Executive Summary & Decoupling Boundary

Fanfic World distinguishes itself by treating **ongoing novels as living digital assets**. An ongoing novel ("Living Novel") published on Fanfic World continues to receive upstream chapters, edits, and revisions from author platforms (e.g. RoyalRoad, WebNovel, Faloo, Syosetu, AO3) while maintaining:
1. **Decoupled Architecture**: Scrapers and crawlers remain **100% external**. The Fanfic World repository contains **zero scraping, crawling, or HTML extraction logic**.
2. **Text-First Publication**: New chapters publish text immediately upon translation. Audio generation is an asynchronous background enhancement and **never blocks reader access to text**.
3. **Deterministic Synchronization**: Every synchronization check is idempotent. If upstream content is unchanged, the system makes **zero LLM translation calls, zero TTS synthesis requests, and zero Appwrite database writes**.
4. **Isolated Operational State**: Crawler synchronization checkpoints, poller state, and upstream revision hashes live in a local, durable SQLite registry (`raw_spool/pipeline_state/living_novel_sync.sqlite`), never polluting production Appwrite document schemas.

```
┌─────────────────────────┐
│ External Crawler System │  (Independent Runner / Lambda / Cron / Local Worker)
└───────────┬─────────────┘
            │ Submits normalized manifest:
            │ LivingNovelSyncManifest
            ▼
┌────────────────────────────────────────────────────────┐
│ Living Novel Sync Orchestrator                         │
│ (server/living_novel_sync.py)                          │
├────────────────────────────────────────────────────────┤
│ 1. Verify Source Identity & Hash                       │
│ 2. Check Local Registry (living_novel_sync.sqlite)    │
│ 3. Classify Chapters:                                  │
│    ├── NEW_CHAPTER    -> Translate -> Publish Text     │
│    │                               -> Enqueue Async TTS│
│    ├── EDITED_CHAPTER -> Re-translate -> Update Text  │
│    │                               -> Invalidate Audio │
│    └── UNCHANGED      -> No-op (0 writes, 0 cost)      │
└───────────┬────────────────────────────────────────────┘
            ▼
┌─────────────────────────┐       ┌──────────────────────┐
│ Appwrite Production DB  │       │ Async Audio Queue    │
│ (novels, chapters)      │       │ (Piper / CapCut TTS) │
└─────────────────────────┘       └──────────────────────┘
```

---

## 2. Source Identity Schema

Every novel tracked for continuous updates is uniquely identified by its canonical source tuple `(source_platform, source_work_id)`:

```json
{
  "source_identity": {
    "source_platform": "royalroad",
    "source_work_id": "156690",
    "canonical_source_url": "https://www.royalroad.com/fiction/156690/naruto-si-reborn-in-the-hatake-clan",
    "source_status": "ongoing",
    "author_original": "SoGarrulous",
    "title_original": "Naruto SI : Reborn in the Hatake Clan",
    "last_seen_source_chapter": 32,
    "last_successful_sync_at": "2026-09-19T06:45:00Z",
    "next_check_at": "2026-09-19T18:45:00Z",
    "sync_state": "ACTIVE",
    "failure_count": 0
  }
}
```

### Source Status Enumeration
- `ongoing`: Novel actively publishes new chapters upstream. Polling is active.
- `completed`: Upstream novel marked complete by author. Terminal state: poller stops automatic scheduling.
- `hiatus`: Author announced pause or no updates detected for >= 60 days. Polling intervals back off significantly.
- `abandoned`: Source deleted, paywalled, or 404 for >= 5 consecutive checks. Marked paused for operator review.

---

## 3. Chapter Identity & Content Hashing

A chapter's identity is defined deterministically to guarantee alignment between upstream releases and Fanfic World chapter documents:

```json
{
  "source_chapter_id": "3137774",
  "source_order": 1,
  "chapter_title_source": "Chapter 1: Taco Bellll",
  "source_url": "https://www.royalroad.com/fiction/156690/naruto-si-reborn-in-the-hatake-clan/chapter/3137774/chapter-1-taco-bellll",
  "source_text_hash": "sha256:7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069",
  "word_count_source": 7771,
  "last_synced_hash": "sha256:7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069",
  "published_chapter_id": "appwrite_chapter_doc_991823",
  "has_published_text": true,
  "has_published_audio": true
}
```

### Deterministic Source Hash Calculation
- Upstream chapter raw content is normalized before hashing:
  1. Trim leading/trailing whitespace.
  2. Normalize line endings (`\r\n` -> `\n`).
  3. Strip transient crawler artifacts (e.g. ad banners, watermarks, timestamps).
  4. Compute `SHA-256` over the UTF-8 encoded text string.

---

## 4. Reconciliation State Machine

When the external crawler submits a sync payload for a novel, the orchestrator evaluates every chapter against the local SQLite registry:

```
                  ┌──────────────────────────────┐
                  │ Evaluate Chapter against DB  │
                  └──────────────┬───────────────┘
                                 │
         ┌───────────────────────┼───────────────────────┐
         │ Not in registry       │ In registry           │ In registry
         │                       │ Hash matches          │ Hash differs
         ▼                       ▼                       ▼
   ┌──────────────┐        ┌──────────────┐        ┌──────────────┐
   │ NEW_CHAPTER  │        │  UNCHANGED   │        │ STALE_SOURCE │
   └──────┬───────┘        └──────┬───────┘        └──────┬───────┘
          │                       │                       │
          ▼                       ▼                       ▼
Translate Text            Zero LLM Calls          Re-translate Text
Publish Text -> Appwrite  Zero Writes             Update Appwrite Text
Queue Async TTS Job       Status = OK             Invalidate Old Audio
Mark in Registry                                  Queue Audio Rebuild
```

### Case A: New Chapter Detected (`NEW_CHAPTER`)
1. **Intake Validation**: Verify chapter order, word count, and non-empty content.
2. **Translation**: Route to `TranslationScheduler` using the 13-account Gemini pool rotation.
3. **Immediate Publication**: Publish text chapter immediately to Appwrite `chapters` collection. Novel `total_chapters` increments.
4. **Async Audio Enqueue**: If novel has audio enabled, publish an async job to the TTS spool (`raw_spool/tts_queue/`).
5. **Registry Update**: Record `(source_work_id, source_chapter_id, source_order, source_text_hash, published_chapter_id)` in local SQLite.

### Case B: Upstream Chapter Edited (`STALE_SOURCE`)
*Scenario: Author rewrites a plot point, fixes typos, or replaces a scene upstream.*
1. **Hash Mismatch**: `source_text_hash != last_synced_hash`.
2. **Re-translation**: Re-translate the revised source text.
3. **In-Place Update**: Update existing Appwrite chapter document `content` without changing `chapter_id`. Reader bookmarks and comments remain intact.
4. **Audio Invalidation**: Mark existing `audio_tracks` record as obsolete. Enqueue new TTS synthesis job.
5. **Registry Update**: Update `last_synced_hash = new_source_text_hash`.

### Case C: Unchanged Chapter (`UNCHANGED`)
1. **Hash Match**: `source_text_hash == last_synced_hash`.
2. **No-Op**: Absolute zero writes, zero LLM calls, zero TTS generation.
3. Execution returns in < 1 millisecond per chapter.

---

## 5. Polling Cadence & Adaptive Backoff

To balance real-time freshness against system load, polling intervals dynamically adapt based on novel activity:

| Novel State | Update Frequency Detected | Polling Interval | Maximum Backoff |
| :--- | :--- | :--- | :--- |
| **High Frequency** | >= 1 chapter per 48 hours | **Every 4 hours** | 6 hours |
| **Normal Ongoing** | 1–3 chapters per week | **Every 12 hours** | 24 hours |
| **Slow Ongoing** | 1 chapter per 2–4 weeks | **Every 48 hours** | 72 hours |
| **Hiatus / Dormant** | 0 chapters for >= 30 days | **Every 7 days** | 14 days |
| **Completed** | Marked completed upstream | **Polling Stopped** | N/A (Manual only) |

### Failure Backoff
If the crawler fails to connect to the source platform (HTTP 429, Cloudflare challenge, 503):
- Attempt 1: Retry in 15 minutes.
- Attempt 2: Retry in 1 hour.
- Attempt 3+: Exponential backoff doubling up to 24 hours. Novel state marked `SYNC_WARNING`.

---

## 6. External Crawler Decoupling Contract

The external crawler communicates with Fanfic World strictly through a clean JSON manifest (`LivingNovelSyncManifest`):

```json
{
  "manifest_version": "1.0",
  "generated_at": "2026-09-19T07:00:00Z",
  "crawler_agent_id": "external-worker-us-east-1",
  "novel": {
    "source_platform": "royalroad",
    "source_work_id": "156690",
    "canonical_source_url": "https://www.royalroad.com/fiction/156690/naruto-si-reborn-in-the-hatake-clan",
    "title_original": "Naruto SI : Reborn in the Hatake Clan",
    "author_original": "SoGarrulous",
    "source_status": "ongoing",
    "latest_source_chapter_index": 33
  },
  "chapters": [
    {
      "source_chapter_id": "3137774",
      "chapter_order": 1,
      "chapter_title": "Chapter 1: Taco Bellll",
      "source_url": "https://www.royalroad.com/.../chapter-1-taco-bellll",
      "source_text": "...raw source text content...",
      "source_text_hash": "sha256:7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069",
      "word_count": 7771
    }
  ]
}
```

---

## 7. Durable SQLite Registry Schema

The tracking state is persisted locally at:
`raw_spool/pipeline_state/living_novel_sync.sqlite`

```sql
-- Novel source tracking table
CREATE TABLE IF NOT EXISTS source_novel_registry (
    source_platform TEXT NOT NULL,
    source_work_id TEXT NOT NULL,
    appwrite_novel_id TEXT,
    canonical_source_url TEXT NOT NULL,
    title_original TEXT NOT NULL,
    author_original TEXT,
    source_status TEXT NOT NULL DEFAULT 'ongoing',
    sync_state TEXT NOT NULL DEFAULT 'ACTIVE',
    last_seen_chapter INTEGER NOT NULL DEFAULT 0,
    check_interval_hours INTEGER NOT NULL DEFAULT 12,
    last_synced_at TEXT,
    next_check_at TEXT,
    failure_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (source_platform, source_work_id)
);

-- Chapter source tracking and revision hash table
CREATE TABLE IF NOT EXISTS source_chapter_registry (
    source_platform TEXT NOT NULL,
    source_work_id TEXT NOT NULL,
    source_chapter_id TEXT NOT NULL,
    chapter_order INTEGER NOT NULL,
    appwrite_chapter_id TEXT,
    source_text_hash TEXT NOT NULL,
    translation_hash TEXT,
    audio_track_id TEXT,
    sync_status TEXT NOT NULL DEFAULT 'SYNCED',
    synced_at TEXT NOT NULL,
    last_edited_at TEXT,
    PRIMARY KEY (source_platform, source_work_id, source_chapter_id),
    FOREIGN KEY (source_platform, source_work_id) 
        REFERENCES source_novel_registry(source_platform, source_work_id)
);

CREATE INDEX IF NOT EXISTS idx_source_novel_next_check 
    ON source_novel_registry(sync_state, next_check_at);
```

---

## 8. Operator Controls & CLI Interface

The operator has full programmatic control over continuous synchronization:

| Command | Action |
| :--- | :--- |
| `python -m server.sync_cli status` | List all tracked living novels, last sync, and next check schedule. |
| `python -m server.sync_cli force --novel-id <id>` | Trigger immediate sync check regardless of backoff schedule. |
| `python -m server.sync_cli pause --novel-id <id>` | Temporarily pause polling for a specific novel. |
| `python -m server.sync_cli resume --novel-id <id>` | Resume normal schedule for a paused novel. |
| `python -m server.sync_cli ingest-manifest <file.json>` | Ingest a manifest submitted by the external crawler. |
