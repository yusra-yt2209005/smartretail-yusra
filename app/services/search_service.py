"""
Semantic catalog search for Week 4.

The customer's query is embedded using the same EmbeddingProvider used
by the indexing pipeline. pgvector cosine distance is then used to find
the nearest product chunks.

Customer search is deliberately conservative:
- product must currently be PUBLISHED
- indexed metadata must say available/in-stock
- the product must still have an active variant with stock > 0

The live variant check prevents stale index metadata from causing a
sold-out product to be recommended.
"""

from __future__ import annotations

from sqlalchemy import (
    and_,
    func,
    select,
)
from sqlalchemy.orm import Session

from app.ai.embeddings import (
    get_embedding_provider,
)
from app.core.config import settings
from app.models.content_chunk import (
    ContentChunk,
)
from app.models.product import (
    Product,
    ProductStatus,
)
from app.models.product_variant import (
    ProductVariant,
)


def search_products(
    db: Session,
    *,
    query: str,
    top_k: int | None = None,
    threshold: float | None = None,
    include_context: bool = False,
) -> list[dict]:
    """
    Return the most semantically relevant buyable products.

    Results are ordered by cosine similarity, highest first.
    """

    query = query.strip()

    if not query:
        return []

    if top_k is None:
        top_k = (
            settings.search_default_top_k
        )

    if threshold is None:
        threshold = (
            settings.search_similarity_threshold
        )

    # ---------------------------------------------------------
    # 1. Embed the customer's query
    # ---------------------------------------------------------

    provider = get_embedding_provider()

    query_vector = provider.embed_batch(
        [query]
    )[0]

    # ---------------------------------------------------------
    # 2. Find one currently buyable variant per product
    # ---------------------------------------------------------
    #
    # A product can have several variants.
    #
    # We rank active + in-stock variants by price and use the
    # cheapest one as the representative buyable variant returned
    # by search.
    # ---------------------------------------------------------

    ranked_variants = (
        select(
            ProductVariant.id.label(
                "variant_id"
            ),
            ProductVariant.product_id.label(
                "product_id"
            ),
            ProductVariant.price.label(
                "price"
            ),
            func.row_number()
            .over(
                partition_by=(
                    ProductVariant.product_id
                ),
                order_by=(
                    ProductVariant.price.asc(),
                    ProductVariant.id.asc(),
                ),
            )
            .label("variant_rank"),
        )
        .where(
            ProductVariant.is_active.is_(
                True
            ),
            ProductVariant.stock > 0,
        )
        .subquery()
    )

    # ---------------------------------------------------------
    # 3. pgvector cosine distance
    # ---------------------------------------------------------

    distance = (
        ContentChunk.embedding
        .cosine_distance(
            query_vector
        )
    )

    # ---------------------------------------------------------
    # 4. Semantic retrieval + correctness filters
    # ---------------------------------------------------------

    stmt = (
        select(
            Product.id.label(
                "product_id"
            ),
            ranked_variants.c.variant_id,
            Product.title,
            Product.category_id,
            ranked_variants.c.price,
            ContentChunk.text.label(
                "context_text"
            ),
            distance.label(
                "distance"
            ),
        )
        .join(
            ContentChunk,
            ContentChunk.product_id
            == Product.id,
        )
        .join(
            ranked_variants,
            and_(
                ranked_variants.c.product_id
                == Product.id,
                ranked_variants.c.variant_rank
                == 1,
            ),
        )
        .where(
            # Current product state.
            Product.status
            == ProductStatus.PUBLISHED,

            # Vector must actually exist.
            ContentChunk.embedding.is_not(
                None
            ),

            # Metadata stored with the vector.
            ContentChunk.status
            == ProductStatus.PUBLISHED.value,

            ContentChunk.available.is_(
                True
            ),

            ContentChunk.in_stock.is_(
                True
            ),
        )
        .order_by(
            distance.asc()
        )
        .limit(
            top_k
        )
    )

    rows = db.execute(
        stmt
    ).all()

    # ---------------------------------------------------------
    # 5. Convert distance into similarity
    # ---------------------------------------------------------

    results: list[dict] = []

    for row in rows:
        similarity = (
            1.0
            - float(row.distance)
        )

        # Nearest-neighbour search always finds something.
        # The threshold prevents unrelated products from being
        # presented as valid matches.
        if similarity < threshold:
            continue



        result = {
            "product_id": (
                row.product_id
            ),
            "variant_id": (
                row.variant_id
            ),
            "title": row.title,
            "category_id": (
                row.category_id
            ),
            "price": row.price,
            "similarity": round(
                similarity,
                4,
            ),
        }

        if include_context:
            result["context_text"] = (
                row.context_text
            )

        results.append(result)

    return results