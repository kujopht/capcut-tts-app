"""
Story mode honesty (release gate B) — what the story mode ACTUALLY receives:
a capped excerpt of the chapter the user has open, only if that user may read
it; otherwise an explicit "no chapter text" note. Never another chapter,
never another user's draft, never a silently empty context.
"""
from __future__ import annotations

import unittest
from dataclasses import dataclass
from typing import Any, Dict, Iterator, List, Optional
from unittest import mock

from fastapi.testclient import TestClient

from server.ai_assistant.gateway import AiGateway
from server.ai_assistant.prompts import STORY_NO_CHAPTER_NOTE, system_prompt
from server.ai_assistant.tools import (
    MAX_CHAPTER_EXCERPT_CHARS, ChapterExcerpt, ToolContext, build_chapter_excerpt_fn,
    current_chapter_excerpt, retrieve_story_chunks,
)
from server.chat.embedding_provider import EmbeddingProvider
from server.chat.vector_store import VectorStore
from server.domain import PublishState
from server.llm_gateway.chat_provider import (
    ChatProvider, Delta, Done, GenerateRequest, GenerateResult, ProviderCapabilities,
    ProviderUsageSnapshot, StreamEvent,
)

from server.tests.test_ai_routes import _auth, _enabled_runtime, _make_app

PUB, DRAFT = PublishState.PUBLISHED, PublishState.DRAFT


def _auth_tok(tok: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {tok}"}


@dataclass
class _Novel:
    novel_id: str
    owner_id: str
    state: PublishState


@dataclass
class _Chapter:
    chapter_id: str
    novel_id: str
    owner_id: str
    title: str
    content: str
    state: PublishState


class _FakeStore:
    def __init__(self) -> None:
        self.novels: Dict[str, _Novel] = {}
        self.chapters: Dict[str, _Chapter] = {}

    def get_novel(self, novel_id: str) -> _Novel:
        if novel_id not in self.novels:
            raise KeyError(novel_id)
        return self.novels[novel_id]

    def get_chapter(self, chapter_id: str) -> _Chapter:
        if chapter_id not in self.chapters:
            raise KeyError(chapter_id)
        return self.chapters[chapter_id]


def _store() -> _FakeStore:
    s = _FakeStore()
    s.novels["n_pub"] = _Novel("n_pub", "user_author", PUB)
    s.novels["n_draft"] = _Novel("n_draft", "user_author", DRAFT)
    s.chapters["c_pub"] = _Chapter("c_pub", "n_pub", "user_author", "Chương 3: Mưa", "Trời mưa suốt đêm.", PUB)
    s.chapters["c_draftch"] = _Chapter("c_draftch", "n_pub", "user_author", "Nháp", "Bí mật chưa đăng.", DRAFT)
    s.chapters["c_in_draft_novel"] = _Chapter("c_in_draft_novel", "n_draft", "user_author", "X", "Nội dung nháp.", PUB)
    s.chapters["c_orphan"] = _Chapter("c_orphan", "n_gone", "user_author", "Mồ côi", "Không truyện cha.", PUB)
    s.chapters["c_empty"] = _Chapter("c_empty", "n_pub", "user_author", "Trống", "   ", PUB)
    s.chapters["c_long"] = _Chapter("c_long", "n_pub", "user_author", "Dài", "a" * (MAX_CHAPTER_EXCERPT_CHARS + 500), PUB)
    return s


def _fn(store: _FakeStore):
    return build_chapter_excerpt_fn(
        get_chapter=store.get_chapter, get_novel=store.get_novel,
        is_published=lambda o: o.state is PublishState.PUBLISHED)


class TestChapterExcerptPermissions(unittest.TestCase):
    def setUp(self) -> None:
        self.fn = _fn(_store())

    def test_published_chapter_of_published_novel_is_readable_by_anyone(self) -> None:
        ex = self.fn("n_pub", "c_pub", "user_reader")
        self.assertIsNotNone(ex)
        self.assertEqual(ex.text, "Trời mưa suốt đêm.")
        self.assertEqual(ex.chapter_title, "Chương 3: Mưa")
        self.assertFalse(ex.truncated)

    def test_draft_novel_only_for_its_owner(self) -> None:
        self.assertIsNone(self.fn("n_draft", "c_in_draft_novel", "user_reader"))
        self.assertIsNotNone(self.fn("n_draft", "c_in_draft_novel", "user_author"))

    def test_chapter_state_is_ignored_parent_novel_decides_like_the_reader(self) -> None:
        # Real chapters are created with state DRAFT and never flipped (see
        # server/main.py::_dem_truyen_chuong_da_xuat_ban); GET /api/chapters/{id}
        # lets anyone read them once the NOVEL is published. Story mode must
        # match — the first version denied every real chapter to readers.
        self.assertIsNotNone(self.fn("n_pub", "c_draftch", "user_reader"))
        self.assertIsNotNone(self.fn("n_pub", "c_draftch", "user_author"))

    def test_chapter_must_belong_to_the_claimed_novel(self) -> None:
        # A readable novel id cannot be paired with a chapter of another novel.
        self.assertIsNone(self.fn("n_pub", "c_in_draft_novel", "user_reader"))

    def test_missing_orphan_empty_all_fail_closed(self) -> None:
        self.assertIsNone(self.fn("n_pub", "c_missing", "user_reader"))
        self.assertIsNone(self.fn("n_gone", "c_orphan", "user_author"))
        self.assertIsNone(self.fn("n_pub", "c_empty", "user_reader"))

    def test_anonymous_user_id_never_matches_an_owner(self) -> None:
        self.assertIsNone(self.fn("n_draft", "c_in_draft_novel", ""))

    def test_long_chapter_is_capped_and_marked_truncated(self) -> None:
        ex = self.fn("n_pub", "c_long", "user_reader")
        self.assertEqual(len(ex.text), MAX_CHAPTER_EXCERPT_CHARS)
        self.assertTrue(ex.truncated)


class TestCurrentChapterExcerptGuards(unittest.TestCase):
    def test_unwired_or_missing_ids_is_none(self) -> None:
        self.assertIsNone(current_chapter_excerpt(ToolContext(), novel_id="n", chapter_id="c", user_id="u"))
        ctx = ToolContext(chapter_excerpt_fn=lambda *a: ChapterExcerpt("n", "c", "t", "x", False))
        self.assertIsNone(current_chapter_excerpt(ctx, novel_id="", chapter_id="c", user_id="u"))
        self.assertIsNone(current_chapter_excerpt(ctx, novel_id="n", chapter_id="", user_id="u"))

    def test_callable_that_raises_is_none_not_an_error(self) -> None:
        def boom(*_a: Any) -> Optional[ChapterExcerpt]:
            raise RuntimeError("store down")
        with self.assertLogs("fanfic.ai_assistant", level="WARNING"):
            self.assertIsNone(current_chapter_excerpt(
                ToolContext(chapter_excerpt_fn=boom), novel_id="n", chapter_id="c", user_id="u"))

    def test_mismatched_ids_from_callable_are_rejected(self) -> None:
        ctx = ToolContext(chapter_excerpt_fn=lambda *a: ChapterExcerpt("OTHER", "c", "t", "x", False))
        self.assertIsNone(current_chapter_excerpt(ctx, novel_id="n", chapter_id="c", user_id="u"))

    def test_oversized_callable_output_is_capped_again(self) -> None:
        big = "b" * (MAX_CHAPTER_EXCERPT_CHARS * 2)
        ctx = ToolContext(chapter_excerpt_fn=lambda *a: ChapterExcerpt("n", "c", "t", big, False))
        ex = current_chapter_excerpt(ctx, novel_id="n", chapter_id="c", user_id="u")
        self.assertEqual(len(ex.text), MAX_CHAPTER_EXCERPT_CHARS)
        self.assertTrue(ex.truncated)


class TestVectorRetrievalFailsClosedWhenPermissionUnwired(unittest.TestCase):
    def test_no_permission_fn_means_no_query_even_with_a_vector_store(self) -> None:
        vs = mock.Mock(spec=VectorStore)
        ctx = ToolContext(vector_store=vs, embedding_provider=mock.Mock(spec=EmbeddingProvider))
        self.assertEqual(retrieve_story_chunks(ctx, "q", novel_id="n", current_chapter_index=2,
                                               user_id="u"), [])
        vs.query.assert_not_called()


class TestStoryPromptIsHonest(unittest.TestCase):
    def test_prompt_states_the_real_scope(self) -> None:
        p = system_prompt("story", assistant_name="Fanfic AI")
        self.assertIn("MỘT CHƯƠNG", p)
        self.assertIn("khi bắt đầu hội thoại này", p)
        self.assertIn("không đọc được các chương khác", p)
        self.assertIn("beta", p)


# ------------------------------------------------------------ route integration


class _CapturingProvider(ChatProvider):
    name = "capture"

    def __init__(self) -> None:
        self.requests: List[GenerateRequest] = []

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(streaming=True, tools=False, web_search=False, vision=False,
                                    max_context_tokens=8000)

    def generate(self, req: GenerateRequest) -> GenerateResult:  # pragma: no cover — unused
        raise NotImplementedError

    def stream(self, req: GenerateRequest) -> Iterator[StreamEvent]:
        self.requests.append(req)
        yield Delta(text="ok")
        yield Done()

    def usage(self) -> ProviderUsageSnapshot:
        return ProviderUsageSnapshot()


class TestStoryRouteContext(unittest.TestCase):
    def setUp(self) -> None:
        self.rt = _enabled_runtime()
        self.provider = _CapturingProvider()
        self.rt.gateway = AiGateway(providers={"capture": self.provider}, provider_chain=["capture"])
        self.rt.tool_ctx = ToolContext(chapter_excerpt_fn=_fn(_store()))
        self.client = TestClient(_make_app(self.rt))

    def _ask(self, user: str, novel_id: str, chapter_id: str) -> str:
        r = self.client.post("/api/ai/conversations", headers=_auth(user), json={
            "mode": "story",
            "context": {"novel_id": novel_id, "chapter_id": chapter_id, "current_chapter_index": 3}})
        self.assertEqual(r.status_code, 200)
        cid = r.json()["conversation_id"]
        r = self.client.post(f"/api/ai/conversations/{cid}/messages", headers=_auth(user),
                             json={"content": "Chuyện gì xảy ra trong chương này?", "client_id": f"c-{user}"})
        self.assertEqual(r.status_code, 200)
        return "\n".join(t.content for t in self.provider.requests[-1].messages)

    def test_readable_chapter_text_reaches_the_prompt_as_untrusted_data(self) -> None:
        prompt = self._ask("reader", "n_pub", "c_pub")
        self.assertIn("CHƯƠNG CỦA HỘI THOẠI NÀY (người dùng mở khi bắt đầu hội thoại) — «Chương 3: Mưa»", prompt)
        self.assertIn("Trời mưa suốt đêm.", prompt)
        self.assertIn("DỮ LIỆU KHÔNG ĐÁNG TIN", prompt)
        self.assertNotIn(STORY_NO_CHAPTER_NOTE, prompt)

    def test_someone_elses_unpublished_novel_never_reaches_the_prompt(self) -> None:
        prompt = self._ask("reader", "n_draft", "c_in_draft_novel")
        self.assertNotIn("Nội dung nháp.", prompt)
        self.assertIn(STORY_NO_CHAPTER_NOTE, prompt)

    def test_real_chapter_state_draft_in_published_novel_reaches_a_reader(self) -> None:
        """Regression (independent review): every real chapter has state
        DRAFT; the first version gave readers the 'no chapter' note."""
        prompt = self._ask("reader4", "n_pub", "c_draftch")
        self.assertIn("Bí mật chưa đăng.", prompt)
        self.assertNotIn(STORY_NO_CHAPTER_NOTE, prompt)

    def test_real_store_default_chapter_is_readable_after_the_novel_is_published(self) -> None:
        """Over the REAL `MockMetadataStore` and the excerpt function actually
        wired in server/main.py (no HTTP — avoids the suite-wide register rate
        limiter): a Chapter with its DEFAULT state (DRAFT, like every chapter
        the app creates) becomes readable to another user exactly when its
        novel is published via the store's own `publish_novel`."""
        import server.main as server_main
        from server.adapters import MockMetadataStore
        from server.domain import Chapter, Novel

        cu = server_main.store
        server_main.store = MockMetadataStore()
        try:
            nv = server_main.store.create_novel(Novel(owner_id="user_tacgia", title="Truyện thử Story"))
            ch = server_main.store.create_chapter(Chapter(novel_id=nv.novel_id, owner_id="user_tacgia",
                                                          title="Chương 1", content="Nội dung thật của chương."))
            self.assertIs(ch.state, PublishState.DRAFT)
            fn = server_main.ai_tool_ctx.chapter_excerpt_fn
            self.assertIsNone(fn(nv.novel_id, ch.chapter_id, "user_docgia"),
                              "unpublished novel: another user must not get the excerpt")
            server_main.store.publish_novel(nv.novel_id, "user_tacgia")
            ex = fn(nv.novel_id, ch.chapter_id, "user_docgia")
            self.assertIsNotNone(ex, "published novel: a reader must get the chapter excerpt")
            self.assertEqual(ex.text, "Nội dung thật của chương.")
        finally:
            server_main.store = cu

    def test_no_chapter_context_says_so_explicitly(self) -> None:
        r = self.client.post("/api/ai/conversations", headers=_auth("r2"), json={"mode": "story"})
        cid = r.json()["conversation_id"]
        self.client.post(f"/api/ai/conversations/{cid}/messages", headers=_auth("r2"),
                         json={"content": "Tóm tắt chương?", "client_id": "c-r2"})
        prompt = "\n".join(t.content for t in self.provider.requests[-1].messages)
        self.assertIn(STORY_NO_CHAPTER_NOTE, prompt)

    def test_truncated_chapter_is_labelled_as_cut(self) -> None:
        prompt = self._ask("reader3", "n_pub", "c_long")
        self.assertIn(f"đã cắt còn {MAX_CHAPTER_EXCERPT_CHARS} ký tự đầu", prompt)

    def test_general_mode_gets_no_story_note(self) -> None:
        r = self.client.post("/api/ai/conversations", headers=_auth("g"), json={"mode": "general"})
        cid = r.json()["conversation_id"]
        self.client.post(f"/api/ai/conversations/{cid}/messages", headers=_auth("g"),
                         json={"content": "xin chào", "client_id": "c-g"})
        prompt = "\n".join(t.content for t in self.provider.requests[-1].messages)
        self.assertNotIn(STORY_NO_CHAPTER_NOTE, prompt)


class TestProductionWiring(unittest.TestCase):
    def test_main_wires_chapter_excerpt_and_permission_to_the_real_store(self) -> None:
        import server.main as server_main

        ctx = server_main.ai_tool_ctx
        self.assertIsNotNone(ctx.chapter_excerpt_fn)
        self.assertIsNotNone(ctx.may_read_novel_fn)
        # Goes through the REAL store: an unknown id is a NotFoundError there,
        # which must come back as "no excerpt", never an exception.
        self.assertIsNone(ctx.chapter_excerpt_fn("nov_missing", "chp_missing", "user_x"))
        self.assertFalse(ctx.may_read_novel_fn("nov_missing", "user_x"))


if __name__ == "__main__":
    unittest.main()
