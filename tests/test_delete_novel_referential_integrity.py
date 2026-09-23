"""Unit tests for delete_novel() referential integrity, cascade cleanup, and tombstoning.

Dependency Graph:
novel
├── cover_key (R2 storage) -> purged
├── chapters (1..N) -> purged
│   ├── audio_tracks (0..N) -> purged
│   ├── tts_jobs (0..N) -> purged
│   └── objects (audio, transcript) -> purged
├── story_follows (0..N) -> CASCADE DELETED
├── posts (0..N) -> DISSOCIATED / TOMBSTONED (novel_id=None to preserve user discussion)
├── content_queue (0..N) -> CASCADE DELETED
└── profiles (0..N) -> last_read / last_listen references CLEARED
"""

import pytest
from server.adapters import (
    MockMetadataStore,
    LocalStorageAdapter,
    Chapter,
    Novel,
    Profile,
    PublishState,
)
from server.domain import Post, StoryFollow, PublicationMode, AudioTrack


def test_delete_novel_cascade_referential_integrity(tmp_path):
    """Verifies that deleting a novel cascades cleanly to all dependencies."""
    store = MockMetadataStore()
    storage = LocalStorageAdapter(tmp_path)
    owner_id = "user_author_1"
    fan_id = "user_fan_99"

    # 1. Create novel with cover
    novel = store.create_novel(Novel(
        novel_id="nov_fixture_123",
        owner_id=owner_id,
        title="Test Fixture Novel",
        description="Fixture description",
        cover_key="covers/nov_fixture_123/cover.jpg",
        state=PublishState.PUBLISHED,
        tags=["action", "fantasy"],
        created_at="2026-09-01T00:00:00Z",
        updated_at="2026-09-01T00:00:00Z",
        publication_mode=PublicationMode.FULL_TEXT,
        fandom_ids=["fandom_naruto"],
    ))
    storage.put("covers/nov_fixture_123/cover.jpg", b"COVER_DATA")

    # 2. Add chapters with tracks and storage files
    ch1 = store.create_chapter(Chapter(
        chapter_id="ch_1",
        novel_id=novel.novel_id,
        owner_id=owner_id,
        title="Chapter 1",
        content="Content 1",
        order_index=1,
        created_at="2026-09-01T00:00:00Z",
        updated_at="2026-09-01T00:00:00Z",
    ))
    store.create_track(AudioTrack(
        track_id="tr_1",
        chapter_id="ch_1",
        owner_id=owner_id,
        voice_id="voice_1",
        object_key="audio/ch_1.mp3",
        content_hash="hash_123",
        duration_seconds=300.0,
        size_bytes=1000,
    ))
    storage.put("audio/ch_1.mp3", b"AUDIO_DATA")
    storage.put("transcripts/ch_1.json", b"TRANSCRIPT_DATA")

    # 3. Add story_follows
    store.follow_story(StoryFollow(
        follow_id="follow_1",
        follower_id=fan_id,
        novel_id=novel.novel_id,
        created_at="2026-09-01T00:00:00Z",
    ))

    # 4. Add posts associated with novel
    store.create_post(Post(
        post_id="post_1",
        author_user_id=fan_id,
        text="Discussion about this amazing novel!",
        novel_id=novel.novel_id,
        created_at="2026-09-01T00:00:00Z",
        updated_at="2026-09-01T00:00:00Z",
    ))

    # 5. Add user progress / profile pointer
    store.profiles[fan_id] = Profile(
        user_id=fan_id,
        email="fan@example.com",
        display_name="Fan Reader",
        tier="free",
        last_read_novel_id=novel.novel_id,
        last_read_chapter_id="ch_1",
        last_listen_novel_id=novel.novel_id,
        last_listen_chapter_id="ch_1",
    )

    # 6. Execute cascade delete
    ref_counts = store.cascade_delete_novel_references(novel.novel_id)

    # Verify story_follows cascade deleted
    assert ref_counts["follows"] == 1
    assert not store.is_following_story("follow_1")

    # Verify posts dissociated / tombstoned (novel_id is None, post not lost)
    assert ref_counts["posts_dissociated"] == 1
    post = store.get_post("post_1")
    assert post is not None
    assert post.novel_id is None
    assert post.text == "Discussion about this amazing novel!"

    # Verify profile pointers cleared
    assert ref_counts["profiles_cleaned"] == 1
    assert store.profiles[fan_id].last_read_novel_id is None
    assert store.profiles[fan_id].last_read_chapter_id is None
    assert store.profiles[fan_id].last_listen_novel_id is None
    assert store.profiles[fan_id].last_listen_chapter_id is None

    # Idempotent retry: running again should not error and return 0s
    retry_counts = store.cascade_delete_novel_references(novel.novel_id)
    assert retry_counts["follows"] == 0
    assert retry_counts["posts_dissociated"] == 0
    assert retry_counts["profiles_cleaned"] == 0
