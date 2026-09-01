from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod

from app.core.config import settings


_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Structural words from our enriched chunk template and common
# English words provide little product-specific search signal.
_STOPWORDS = frozenset(
    {
        "title",
        "category",
        "specifications",
        "description",
        "uncategorized",
        "the",
        "a",
        "an",
        "for",
        "and",
        "with",
        "of",
        "to",
        "in",
        "on",
        "is",
        "are",
    }
)


class EmbeddingProvider(ABC):
    """
    Interface for embedding backends used by SmartRetail.

    The rest of the application depends on this interface instead of
    directly depending on OpenAI or another external provider.
    """

    model_name: str
    dimensions: int

    @abstractmethod
    def embed_batch(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        """
        Return one vector for every input text.

        Input and output ordering must match.
        """
        raise NotImplementedError


class OpenAIEmbeddingProvider(
    EmbeddingProvider
):
    """
    Real embedding provider using the OpenAI embeddings API.
    """

    def __init__(
        self,
        *,
        model: str | None = None,
        api_key: str | None = None,
        dimensions: int | None = None,
    ) -> None:
        # Import lazily so FakeEmbeddings can be used without
        # initializing the OpenAI client.
        from openai import OpenAI

        self.model_name = (
            model
            or settings.embedding_model
        )

        self.dimensions = (
            dimensions
            or settings.vector_dimensions
        )

        self._client = OpenAI(
            api_key=(
                api_key
                or settings.openai_api_key
            )
        )

    def embed_batch(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        if not texts:
            return []

        if any(
            not text.strip()
            for text in texts
        ):
            raise ValueError(
                "Embedding text cannot be empty"
            )

        response = (
            self._client.embeddings.create(
                model=self.model_name,
                input=texts,
                dimensions=self.dimensions,
            )
        )

        # Explicitly use each response item's index so our
        # abstraction guarantees the same order as the input.
        ordered = sorted(
            response.data,
            key=lambda item: item.index,
        )

        return [
            item.embedding
            for item in ordered
        ]


class FakeEmbeddings(
    EmbeddingProvider
):
    """
    Deterministic offline embeddings for tests and development.

    Each meaningful token is hashed into a vector bucket. Texts that
    share meaningful words therefore tend to have more similar vectors.

    This is useful for exercising vector storage and retrieval without
    calling a real API. It does not understand synonyms or deeper
    semantic meaning like a real embedding model.
    """

    model_name = "fake-hashing-v1"

    def __init__(
        self,
        dimensions: int | None = None,
    ) -> None:
        self.dimensions = (
            dimensions
            or settings.vector_dimensions
        )

        if self.dimensions <= 0:
            raise ValueError(
                "Embedding dimensions must be greater than 0"
            )

    def _embed_one(
        self,
        text: str,
    ) -> list[float]:
        if not text.strip():
            raise ValueError(
                "Embedding text cannot be empty"
            )

        vector = [
            0.0
        ] * self.dimensions

        tokens = [
            token
            for token in _TOKEN_RE.findall(
                text.lower()
            )
            if token not in _STOPWORDS
        ]

        # A string containing only ignored words still needs a stable,
        # valid vector.
        if not tokens:
            vector[0] = 1.0
            return vector

        for token in tokens:
            digest = hashlib.sha256(
                token.encode("utf-8")
            ).digest()

            bucket = (
                int.from_bytes(
                    digest[:4],
                    "big",
                )
                % self.dimensions
            )

            sign = (
                1.0
                if digest[4] % 2 == 0
                else -1.0
            )

            vector[bucket] += sign

        norm = math.sqrt(
            sum(
                component * component
                for component in vector
            )
        )

        if norm == 0:
            vector[0] = 1.0
            return vector

        return [
            component / norm
            for component in vector
        ]

    def embed_batch(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        return [
            self._embed_one(text)
            for text in texts
        ]


def get_embedding_provider() -> EmbeddingProvider:
    """
    Return the embedding backend configured for the application.

    Fake embeddings are the safe default for local development/tests.
    """

    if (
        settings.embedding_provider
        == "openai"
    ):
        return OpenAIEmbeddingProvider()

    if (
        settings.embedding_provider
        == "fake"
    ):
        return FakeEmbeddings()

    raise ValueError(
        "Unknown embedding provider: "
        f"{settings.embedding_provider}"
    )