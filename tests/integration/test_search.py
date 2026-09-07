import hashlib
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.ai.embeddings import FakeEmbeddings
from app.core.config import settings
from app.db.session import SessionLocal
from app.models.content_chunk import ContentChunk
from app.models.product import Product, ProductStatus
from app.models.product_variant import ProductVariant
from app.services import search_service
from app.temporal.activities import (
    ChunkProductInput,
    chunk_product_activity,
)


def create_search_product(
    client,
    *,
    title: str,
    stock: int = 10,
    price: float = 1000.00,
) -> str:
    """
    Create a real product through the API and return its product id.
    """

    email = (
        f"test-search-{uuid.uuid4()}@example.com"
    )

    client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "password123",
            "full_name": "Test Search Merchant",
            "role": "merchant",
        },
    )

    login = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "password123",
        },
    )

    token = login.json()[
        "access_token"
    ]

    category = client.post(
        "/categories",
        json={
            "name": (
                f"TEST-Search-{uuid.uuid4()}"
            ),
            "order_index": 1,
        },
        headers={
            "Authorization": (
                f"Bearer {token}"
            )
        },
    )

    category_id = category.json()["id"]

    response = client.post(
        "/products",
        json={
            "title": title,
            "description": (
                "TEST searchable product description"
            ),
            "category_id": category_id,
            "variants": [
                {
                    "sku": (
                        f"TEST-SEARCH-SKU-"
                        f"{uuid.uuid4()}"
                    ),
                    "price": price,
                    "stock": stock,
                    "attributes": {
                        "brand": "TestBrand",
                        "color": "black",
                    },
                }
            ],
            "media": [],
        },
        headers={
            "Authorization": (
                f"Bearer {token}"
            )
        },
    )

    assert response.status_code == 201

    return response.json()["id"]


def index_product(
    product_id: str,
) -> None:
    """
    Simulate an already completed Week 4 indexing pipeline.

    This keeps /search tests independent from Temporal/network calls.
    """

    with SessionLocal() as db:
        product = db.get(
            Product,
            uuid.UUID(product_id),
        )

        assert product is not None

        variant = db.scalar(
            select(ProductVariant)
            .where(
                ProductVariant.product_id
                == product.id
            )
        )

        assert variant is not None

        product.status = (
            ProductStatus.PUBLISHED
        )

        chunk_text = (
            f"Title: {product.title}\n"
            f"Category: TEST Search\n"
            f"Specifications: "
            f"brand: TestBrand, color: black\n"
            f"Description: "
            f"{product.description}"
        )

        text_hash = hashlib.sha256(
            chunk_text.encode("utf-8")
        ).hexdigest()

        provider = FakeEmbeddings(
            dimensions=(
                settings.vector_dimensions
            )
        )

        vector = provider.embed_batch(
            [chunk_text]
        )[0]

        db.add(
            ContentChunk(
                product_id=product.id,
                variant_id=None,
                category_id=(
                    product.category_id
                ),
                chunk_index=0,
                text=chunk_text,
                text_hash=text_hash,
                embedding=vector,
                price=variant.price,
                status=(
                    ProductStatus.PUBLISHED.value
                ),
                available=(
                    variant.is_active
                ),
                in_stock=(
                    variant.is_active
                    and variant.stock > 0
                ),
                embedded_at=datetime.now(
                    UTC
                ),
            )
        )

        db.commit()


def test_search_returns_buyable_indexed_product(
    client,
):
    """
    A published, active, in-stock indexed product should be searchable.
    """

    title = (
        f"TEST-SearchPhone-"
        f"{uuid.uuid4()}"
    )

    product_id = create_search_product(
        client,
        title=title,
        stock=10,
    )

    index_product(
        product_id
    )

    response = client.post(
        "/search",
        json={
            "query": title,
            "top_k": 5,
        },
    )

    assert response.status_code == 200

    body = response.json()

    result_ids = [
        item["product_id"]
        for item in body["items"]
    ]

    assert product_id in result_ids


def test_search_excludes_out_of_stock_product(
    client,
):
    """
    Even a very strong vector match must not return an out-of-stock
    product.
    """

    title = (
        f"TEST-LogitechMouse-"
        f"{uuid.uuid4()}"
    )

    product_id = create_search_product(
        client,
        title=title,
        stock=0,
    )

    index_product(
        product_id
    )

    response = client.post(
        "/search",
        json={
            "query": title,
            "top_k": 5,
        },
    )

    assert response.status_code == 200

    result_ids = [
        item["product_id"]
        for item in response.json()[
            "items"
        ]
    ]

    assert product_id not in result_ids


def test_search_discards_results_below_threshold(
    client,
    monkeypatch,
):
    """
    Nearest-neighbour search always finds something.

    A similarity threshold must be able to turn weak results into the
    valid "no matching products" outcome.
    """

    title = (
        f"TEST-ThresholdPhone-"
        f"{uuid.uuid4()}"
    )

    product_id = create_search_product(
        client,
        title=title,
    )

    index_product(
        product_id
    )

    # Even an identical vector has cosine similarity <= 1.
    # Therefore 1.1 guarantees that every result is discarded.
    monkeypatch.setattr(
        search_service.settings,
        "search_similarity_threshold",
        1.1,
    )

    response = client.post(
        "/search",
        json={
            "query": title,
            "top_k": 5,
        },
    )

    assert response.status_code == 200
    assert response.json()["items"] == []
    assert (
        response.json()["message"]
        == "No matching products found."
    )


def test_reindex_keeps_single_chunk_and_clears_stale_vector(
    client,
):
    """
    A semantic product edit must update the existing chunk rather than
    leave duplicate/stale vectors behind.
    """

    product_id = create_search_product(
        client,
        title=(
            f"TEST-Reindex-"
            f"{uuid.uuid4()}"
        ),
    )

    first_text = (
        "Title: TEST Reindex Laptop\n"
        "Category: Laptops\n"
        "Specifications: memory: 16GB\n"
        "Description: Business laptop"
    )

    first_result = (
        chunk_product_activity(
            ChunkProductInput(
                product_id=product_id,
                catalog_text=first_text,
            )
        )
    )

    assert (
        first_result["text_changed"]
        is True
    )

    with SessionLocal() as db:
        chunk = db.scalar(
            select(ContentChunk)
            .where(
                ContentChunk.product_id
                == uuid.UUID(product_id)
            )
        )

        assert chunk is not None

        original_chunk_id = chunk.id
        original_hash = chunk.text_hash

        provider = FakeEmbeddings(
            dimensions=(
                settings.vector_dimensions
            )
        )

        chunk.embedding = (
            provider.embed_batch(
                [first_text]
            )[0]
        )

        chunk.embedded_at = (
            datetime.now(UTC)
        )

        db.commit()

    second_text = (
        "Title: TEST Reindex Laptop\n"
        "Category: Laptops\n"
        "Specifications: memory: 32GB\n"
        "Description: Powerful business laptop"
    )

    second_result = (
        chunk_product_activity(
            ChunkProductInput(
                product_id=product_id,
                catalog_text=second_text,
            )
        )
    )

    assert (
        second_result["text_changed"]
        is True
    )

    with SessionLocal() as db:
        count = db.scalar(
            select(
                func.count(
                    ContentChunk.id
                )
            )
            .where(
                ContentChunk.product_id
                == uuid.UUID(product_id)
            )
        )

        assert count == 1

        chunk = db.scalar(
            select(ContentChunk)
            .where(
                ContentChunk.product_id
                == uuid.UUID(product_id)
            )
        )

        assert chunk is not None

        # Same row updated instead of duplicate insertion.
        assert (
            chunk.id
            == original_chunk_id
        )

        # Semantic text changed.
        assert (
            chunk.text_hash
            != original_hash
        )

        # Old vector is stale and must no longer be used.
        assert chunk.embedding is None
        assert chunk.embedded_at is None


def test_price_only_reindex_reuses_embedding(
    client,
):
    """
    If semantic text is unchanged, changing only price must preserve
    the existing vector.
    """

    product_id = create_search_product(
        client,
        title=(
            f"TEST-PriceReuse-"
            f"{uuid.uuid4()}"
        ),
        price=1000.00,
    )

    catalog_text = (
        "Title: TEST Price Reuse Phone\n"
        "Category: Phones\n"
        "Specifications: brand: TestBrand\n"
        "Description: Smartphone"
    )

    chunk_product_activity(
        ChunkProductInput(
            product_id=product_id,
            catalog_text=catalog_text,
        )
    )

    with SessionLocal() as db:
        chunk = db.scalar(
            select(ContentChunk)
            .where(
                ContentChunk.product_id
                == uuid.UUID(product_id)
            )
        )

        variant = db.scalar(
            select(ProductVariant)
            .where(
                ProductVariant.product_id
                == uuid.UUID(product_id)
            )
        )

        assert chunk is not None
        assert variant is not None

        provider = FakeEmbeddings(
            dimensions=(
                settings.vector_dimensions
            )
        )

        chunk.embedding = (
            provider.embed_batch(
                [catalog_text]
            )[0]
        )

        original_embedded_at = (
            datetime.now(UTC)
        )

        chunk.embedded_at = (
            original_embedded_at
        )

        original_chunk_id = chunk.id
        original_hash = chunk.text_hash

        variant.price = 750.00

        db.commit()

    result = chunk_product_activity(
        ChunkProductInput(
            product_id=product_id,
            catalog_text=catalog_text,
        )
    )

    assert (
        result["text_changed"]
        is False
    )

    assert (
        result["reused_embedding"]
        is True
    )

    with SessionLocal() as db:
        chunk = db.scalar(
            select(ContentChunk)
            .where(
                ContentChunk.product_id
                == uuid.UUID(product_id)
            )
        )

        assert chunk is not None

        assert (
            chunk.id
            == original_chunk_id
        )

        assert (
            chunk.text_hash
            == original_hash
        )

        assert chunk.embedding is not None

        assert (
            chunk.embedded_at
            == original_embedded_at
        )

        assert float(chunk.price) == 750.00