import math

import pytest

from app.ai.embeddings import (
    FakeEmbeddings,
)


def test_fake_embeddings_returns_one_vector_per_text():
    provider = FakeEmbeddings(
        dimensions=16
    )

    result = provider.embed_batch(
        [
            "Lenovo laptop",
            "Samsung phone",
            "USB-C charger",
        ]
    )

    assert len(result) == 3

    assert all(
        len(vector) == 16
        for vector in result
    )


def test_fake_embeddings_are_deterministic():
    provider = FakeEmbeddings(
        dimensions=16
    )

    first = provider.embed_batch(
        [
            "Lenovo business laptop"
        ]
    )

    second = provider.embed_batch(
        [
            "Lenovo business laptop"
        ]
    )

    assert first == second


def test_fake_embeddings_are_normalized():
    provider = FakeEmbeddings(
        dimensions=32
    )

    vector = provider.embed_batch(
        [
            "Lenovo laptop 16GB SSD"
        ]
    )[0]

    norm = math.sqrt(
        sum(
            value * value
            for value in vector
        )
    )

    assert norm == pytest.approx(
        1.0
    )


def test_fake_embeddings_shared_words_have_similarity():
    provider = FakeEmbeddings(
        dimensions=128
    )

    laptop_a, laptop_b = (
        provider.embed_batch(
            [
                "Lenovo business laptop",
                "Lenovo lightweight laptop",
            ]
        )
    )

    dot_product = sum(
        a * b
        for a, b in zip(
            laptop_a,
            laptop_b,
        )
    )

    assert dot_product > 0


def test_fake_embeddings_empty_batch():
    provider = FakeEmbeddings(
        dimensions=16
    )

    assert provider.embed_batch([]) == []


def test_fake_embeddings_reject_empty_text():
    provider = FakeEmbeddings(
        dimensions=16
    )

    with pytest.raises(
        ValueError
    ):
        provider.embed_batch(
            [""]
        )