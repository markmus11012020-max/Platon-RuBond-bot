"""
Менеджер удалённой векторной памяти на базе Pinecone (RAG).

Эмбеддинги:
  1. OpenAI-compatible через AiTunnel (если AITUNNEL_API_KEY задан)
  2. Fallback — детерминированный hash-эмбеддинг (dev/offline, dim=768)
"""

from __future__ import annotations

import hashlib
import struct
from typing import Any, Dict, List, Optional, Sequence
from uuid import uuid4

from src.utils.logger import setup_logger

logger = setup_logger("platon_rubond.memory.pinecone")

DEFAULT_INDEX = "platon-rubond"
DEFAULT_DIM = 768
DEFAULT_NAMESPACE = "bonds-news"


class HashEmbedding:
    """
    Детерминированный локальный эмбеддер (без внешних API).
    Подходит для dev/тестов; для продакшена используйте AiTunnel/OpenAI.
    """

    def __init__(self, dim: int = DEFAULT_DIM) -> None:
        self.dim = dim

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return [self._embed_one(t) for t in texts]

    def embed_query(self, text: str) -> List[float]:
        return self._embed_one(text)

    def _embed_one(self, text: str) -> List[float]:
        # Несколько хэшей → псевдо-случайный единичный вектор фиксированной размерности
        vec: List[float] = []
        seed = text.encode("utf-8")
        counter = 0
        while len(vec) < self.dim:
            h = hashlib.sha256(seed + counter.to_bytes(4, "little")).digest()
            for i in range(0, len(h), 4):
                if len(vec) >= self.dim:
                    break
                val = struct.unpack("!i", h[i : i + 4])[0] / 2**31
                vec.append(val)
            counter += 1
        # L2-нормализация
        norm = sum(x * x for x in vec) ** 0.5 or 1.0
        return [x / norm for x in vec]


class PineconeMemoryManager:
    """
    RAG-слой: индексация новостей/проспектов и семантический поиск.

    Поддерживает namespaces и metadata filtering.
    При отсутствии API-ключа или пакета pinecone работает в offline-режиме
    (in-memory store + HashEmbedding).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        environment: Optional[str] = None,
        index_name: Optional[str] = None,
        dimension: int = DEFAULT_DIM,
        embedding_model: Optional[str] = None,
        aitunnel_api_key: Optional[str] = None,
        aitunnel_base_url: str = "https://api.aitunnel.ru/v1",
    ) -> None:
        self.api_key = api_key
        self.environment = environment
        self.index_name = index_name or DEFAULT_INDEX
        self.dimension = dimension
        self.embedding_model = embedding_model or "text-embedding-3-small"
        self.aitunnel_api_key = aitunnel_api_key
        self.aitunnel_base_url = aitunnel_base_url

        self._index = None
        self._pc = None
        self._offline_store: List[Dict[str, Any]] = []  # fallback
        self._embedder = self._init_embedder()
        self._init_pinecone()

    # ------------------------------------------------------------------
    # Init
    # ------------------------------------------------------------------

    def _init_embedder(self) -> Any:
        """OpenAI-compatible embeddings через AiTunnel, иначе HashEmbedding."""
        if self.aitunnel_api_key:
            try:
                from langchain_openai import OpenAIEmbeddings

                emb = OpenAIEmbeddings(
                    model=self.embedding_model,
                    api_key=self.aitunnel_api_key,
                    base_url=self.aitunnel_base_url,
                    dimensions=self.dimension,
                )
                logger.info("Embeddings: AiTunnel / OpenAI-compatible (%s)", self.embedding_model)
                return emb
            except Exception as exc:
                logger.warning("OpenAIEmbeddings unavailable (%s) — HashEmbedding", exc)

        # langchain_openai may need openai package
        if self.aitunnel_api_key:
            try:
                from openai import OpenAI

                client = OpenAI(api_key=self.aitunnel_api_key, base_url=self.aitunnel_base_url)

                class _OpenAIEmbedder:
                    def __init__(self, client, model, dim):
                        self.client = client
                        self.model = model
                        self.dim = dim

                    def embed_documents(self, texts: List[str]) -> List[List[float]]:
                        resp = self.client.embeddings.create(model=self.model, input=texts)
                        return [d.embedding for d in resp.data]

                    def embed_query(self, text: str) -> List[float]:
                        return self.embed_documents([text])[0]

                logger.info("Embeddings: raw OpenAI client via AiTunnel")
                return _OpenAIEmbedder(client, self.embedding_model, self.dimension)
            except Exception as exc:
                logger.warning("OpenAI client embeddings failed (%s)", exc)

        logger.info("Embeddings: HashEmbedding (offline, dim=%d)", self.dimension)
        return HashEmbedding(dim=self.dimension)

    def _init_pinecone(self) -> None:
        if not self.api_key:
            logger.info("Pinecone: нет API-ключа — offline in-memory mode")
            return
        try:
            from pinecone import Pinecone

            self._pc = Pinecone(api_key=self.api_key)
            existing = [idx.name for idx in self._pc.list_indexes()]
            if self.index_name not in existing:
                try:
                    from pinecone import ServerlessSpec

                    self._pc.create_index(
                        name=self.index_name,
                        dimension=self.dimension,
                        metric="cosine",
                        spec=ServerlessSpec(cloud="aws", region="us-east-1"),
                    )
                    logger.info("Pinecone: создан индекс %s", self.index_name)
                except Exception as exc:
                    logger.warning(
                        "Pinecone: не удалось создать индекс (%s). "
                        "Убедитесь, что индекс '%s' существует.",
                        exc,
                        self.index_name,
                    )
            self._index = self._pc.Index(self.index_name)
            logger.info("Pinecone: подключён к индексу %s", self.index_name)
        except ImportError:
            logger.warning("Пакет pinecone не установлен — offline mode")
        except Exception as exc:
            logger.warning("Pinecone init error: %s — offline mode", exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def upsert_document_vectors(
        self,
        text_chunks: List[str],
        metadata: Optional[List[Dict[str, Any]]] = None,
        namespace: str = DEFAULT_NAMESPACE,
    ) -> int:
        """
        Индексация текстовых чанков.

        Returns
        -------
        int
            Количество успешно загруженных векторов.
        """
        if not text_chunks:
            return 0

        meta_list = metadata or [{} for _ in text_chunks]
        if len(meta_list) < len(text_chunks):
            meta_list = list(meta_list) + [{}] * (len(text_chunks) - len(meta_list))

        try:
            vectors = self._embedder.embed_documents(list(text_chunks))
        except Exception as exc:
            logger.exception("Embedding failed: %s", exc)
            return 0

        records = []
        for i, (text, vec, meta) in enumerate(zip(text_chunks, vectors, meta_list)):
            mid = meta.get("id") or str(uuid4())
            payload = {
                "id": str(mid),
                "values": vec,
                "metadata": {
                    **{k: v for k, v in meta.items() if k != "id" and _is_pinecone_meta(v)},
                    "text": text[:3000],  # Pinecone metadata size limit
                },
            }
            records.append(payload)

        if self._index is not None:
            try:
                self._index.upsert(vectors=records, namespace=namespace)
                logger.info("Pinecone upsert: %d vectors → ns=%s", len(records), namespace)
                return len(records)
            except Exception as exc:
                logger.exception("Pinecone upsert failed: %s", exc)

        # Offline fallback
        for r in records:
            self._offline_store.append(
                {
                    "id": r["id"],
                    "values": r["values"],
                    "metadata": r["metadata"],
                    "namespace": namespace,
                }
            )
        logger.info("Offline upsert: %d vectors (total store=%d)", len(records), len(self._offline_store))
        return len(records)

    def similarity_search(
        self,
        query_text: str,
        top_k: int = 5,
        namespace: Optional[str] = None,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Семантический поиск.

        Returns
        -------
        list[dict]
            [{"text": ..., "score": ..., "metadata": {...}}, ...]
        """
        ns = namespace or DEFAULT_NAMESPACE
        try:
            query_vec = self._embedder.embed_query(query_text)
        except Exception as exc:
            logger.exception("Query embedding failed: %s", exc)
            return []

        if self._index is not None:
            try:
                kwargs: Dict[str, Any] = {
                    "vector": query_vec,
                    "top_k": top_k,
                    "namespace": ns,
                    "include_metadata": True,
                }
                if filter:
                    kwargs["filter"] = filter
                response = self._index.query(**kwargs)
                matches = getattr(response, "matches", None) or response.get("matches", [])
                results = []
                for m in matches:
                    meta = getattr(m, "metadata", None) or m.get("metadata") or {}
                    score = getattr(m, "score", None) or m.get("score")
                    results.append(
                        {
                            "text": meta.get("text", ""),
                            "score": score,
                            "metadata": {k: v for k, v in meta.items() if k != "text"},
                        }
                    )
                return results
            except Exception as exc:
                logger.exception("Pinecone query failed: %s", exc)

        # Offline cosine search
        return self._offline_search(query_vec, top_k, ns, filter)

    def delete_namespace(self, namespace: str = DEFAULT_NAMESPACE) -> None:
        if self._index is not None:
            try:
                self._index.delete(delete_all=True, namespace=namespace)
            except Exception as exc:
                logger.warning("delete_namespace: %s", exc)
        self._offline_store = [r for r in self._offline_store if r.get("namespace") != namespace]

    # ------------------------------------------------------------------
    # Offline helpers
    # ------------------------------------------------------------------

    def _offline_search(
        self,
        query_vec: List[float],
        top_k: int,
        namespace: str,
        filter: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        candidates = [
            r for r in self._offline_store if r.get("namespace") == namespace
        ]
        if filter:
            def _match(meta: dict) -> bool:
                for k, v in filter.items():
                    if meta.get(k) != v:
                        return False
                return True

            candidates = [r for r in candidates if _match(r.get("metadata") or {})]

        scored = []
        for r in candidates:
            score = _cosine(query_vec, r["values"])
            meta = r.get("metadata") or {}
            scored.append(
                {
                    "text": meta.get("text", ""),
                    "score": score,
                    "metadata": {k: v for k, v in meta.items() if k != "text"},
                }
            )
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:top_k]


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5 or 1.0
    nb = sum(x * x for x in b) ** 0.5 or 1.0
    return dot / (na * nb)


def _is_pinecone_meta(v: Any) -> bool:
    """Pinecone metadata: str, int, float, bool, list[str]."""
    if isinstance(v, (str, int, float, bool)):
        return True
    if isinstance(v, list) and all(isinstance(i, str) for i in v):
        return True
    return False
