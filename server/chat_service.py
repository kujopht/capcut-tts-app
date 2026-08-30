"""
Fanfic AI Chat V1 — Chat Service integration layer.

Foundation-only implementation:
No Appwrite collection exists yet for chat message history.
An in-memory store is used here, matching how other foundation-stage
features in this repository (e.g. MockWalletStore, MockImageLibraryStore)
operate prior to full Appwrite schema migration.
"""
from __future__ import annotations

import dataclasses
import threading
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable

from server.chat.domain import ChatMessage, ChatScope, UserReadingContext
from server.chat.embedding_provider import HashEmbeddingProvider
from server.chat.pipeline import answer_question
from server.chat.vector_store import InMemoryVectorStore
from server.llm_gateway.gateway import LLMGateway
from server.llm_gateway.provider import MockLLMProvider
from server.llm_gateway.routing import GatewayRouter, RouteTarget, TaskKind


@runtime_checkable
class ChatStore(Protocol):
    """Protocol for storing and listing chat messages."""

    def save_message(self, conversation_id: str, message: ChatMessage) -> None:
        """Save a message under a given conversation."""
        ...

    def list_messages(self, conversation_id: str) -> List[ChatMessage]:
        """List all messages under a given conversation."""
        ...


class InMemoryChatStore:
    """In-memory store for chat messages, keyed by conversation_id."""

    def __init__(self) -> None:
        self._messages: Dict[str, List[ChatMessage]] = {}
        self._lock = threading.Lock()

    def save_message(self, conversation_id: str, message: ChatMessage) -> None:
        with self._lock:
            if conversation_id not in self._messages:
                self._messages[conversation_id] = []
            self._messages[conversation_id].append(message)

    def list_messages(self, conversation_id: str) -> List[ChatMessage]:
        with self._lock:
            return list(self._messages.get(conversation_id, []))


class ChatService:
    """
    Coordinates chat RAG pipeline, vector store, embedding provider,
    and LLM gateway.

    Note on current_chapter_index:
    This repository has no existing backend reading-progress tracking feature;
    V1 has the client reader page itself supply its known chapter position as
    `current_chapter_index`. This is a UX safeguard against accidental
    self-spoiling, not an access-control security boundary.
    """

    def __init__(
        self,
        *,
        vector_store: Optional[InMemoryVectorStore] = None,
        embedding_provider: Optional[HashEmbeddingProvider] = None,
        gateway: Optional[LLMGateway] = None,
        chat_store: Optional[ChatStore] = None,
    ) -> None:
        self.vector_store = vector_store or InMemoryVectorStore()
        self.embedding_provider = embedding_provider or HashEmbeddingProvider()
        if gateway is None:
            mock_provider = MockLLMProvider()
            router = GatewayRouter(
                routes={
                    TaskKind.COMPLEX_GROUNDED: [
                        RouteTarget(provider_name=mock_provider.name, model="mock-model")
                    ],
                    TaskKind.CHEAP_SIMPLE: [
                        RouteTarget(provider_name=mock_provider.name, model="mock-model")
                    ],
                }
            )
            self.gateway = LLMGateway(
                providers={mock_provider.name: mock_provider},
                router=router,
            )
        else:
            self.gateway = gateway
        self.chat_store = chat_store or InMemoryChatStore()

    def ask(
        self,
        question: str,
        *,
        user_id: str = "anonymous",
        novel_id: str,
        chapter_id: Optional[str] = None,
        scope_str: Optional[str] = None,
        selected_text: Optional[str] = None,
        current_chapter_index: int = 1,
        spoiler_protection_enabled: bool = True,
    ) -> Dict[str, Any]:
        """
        Processes a reader's question using RAG and returns a response matching the
        shared API contract:
        {
          "answer": "string",
          "citations": [
            {"novel_id": "string", "chapter_id": "string", "chapter_index": integer,
             "chapter_title": "string", "excerpt": "string", "chunk_order": integer}
          ],
          "evidence_insufficient": boolean
        }
        """
        explicit_scope: Optional[ChatScope] = None
        if scope_str:
            try:
                explicit_scope = ChatScope(scope_str.lower())
            except ValueError:
                explicit_scope = None

        reading_context = UserReadingContext(
            user_id=user_id,
            novel_id=novel_id,
            current_chapter_index=current_chapter_index,
            spoiler_protection_enabled=spoiler_protection_enabled,
        )

        llm_fn = self.gateway.as_llm_complete_fn(task_kind=TaskKind.COMPLEX_GROUNDED)

        result = answer_question(
            question,
            reading_context=reading_context,
            vector_store=self.vector_store,
            embedding_provider=self.embedding_provider,
            llm_complete=llm_fn,
            explicit_scope=explicit_scope,
            selected_text=selected_text,
            active_chapter_id=chapter_id,
        )

        citations_list = [dataclasses.asdict(c) for c in result.citations]

        return {
            "answer": result.answer_text,
            "citations": citations_list,
            "evidence_insufficient": result.evidence_insufficient,
        }


_chat_service_instance: Optional[ChatService] = None
_chat_service_lock = threading.Lock()


def get_chat_service() -> ChatService:
    """Lazy singleton constructor for ChatService."""
    global _chat_service_instance
    if _chat_service_instance is None:
        with _chat_service_lock:
            if _chat_service_instance is None:
                _chat_service_instance = ChatService()
    return _chat_service_instance
