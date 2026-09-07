from abc import ABC, abstractmethod
import hashlib
import random

from openai import OpenAI


class EmbeddingProvider(ABC):
    """
    Interface used by SmartRetail to generate text embeddings.

    Application code depends on this abstraction rather than directly
    depending on a particular external embedding provider.
    """

    @property
    @abstractmethod
    def dimension(self) -> int:
        """
        Number of values in every embedding vector.
        """
        raise NotImplementedError

    @abstractmethod
    def embed_texts(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        """
        Generate one embedding vector for every input text.

        The output list must preserve the input ordering.
        """
        raise NotImplementedError


class OpenAIEmbeddingProvider(
    EmbeddingProvider
):
    """
    Real embedding provider backed by the OpenAI embeddings API.
    """

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        dimension: int,
    ) -> None:
        self._client = OpenAI(
            api_key=api_key
        )

        self._model = model
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_texts(
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
                model=self._model,
                input=texts,
                dimensions=self._dimension,
            )
        )

        # The API supplies an index for each result.
        # Sorting guarantees output order matches input order.
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
    Deterministic embedding provider for tests.

    It performs no network calls and always produces the same vector
    for the same input text.
    """

    def __init__(
        self,
        dimension: int = 8,
    ) -> None:
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    def embed_texts(
        self,
        texts: list[str],
    ) -> list[list[float]]:
        embeddings: list[list[float]] = []

        for text in texts:
            if not text.strip():
                raise ValueError(
                    "Embedding text cannot be empty"
                )

            # Python's built-in hash() is intentionally randomized
            # between processes, so use SHA-256 for a stable seed.
            digest = hashlib.sha256(
                text.encode("utf-8")
            ).digest()

            seed = int.from_bytes(
                digest[:8],
                byteorder="big",
            )

            rng = random.Random(seed)

            vector = [
                rng.uniform(-1.0, 1.0)
                for _ in range(
                    self._dimension
                )
            ]

            embeddings.append(
                vector
            )

        return embeddings