"""
Integration tests for concurrency-safe inventory reservation.
"""

import uuid
from concurrent.futures import ThreadPoolExecutor

from app.db.session import SessionLocal
from app.models.product_variant import ProductVariant
from app.services.inventory_service import try_reserve_stock


def create_user_and_token(
    client,
    *,
    role: str,
) -> str:
    email = f"inventory-{role}-{uuid.uuid4()}@example.com"

    client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "password123",
            "full_name": f"Inventory Test {role}",
            "role": role,
        },
    )

    login = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "password123",
        },
    )

    return login.json()["access_token"]


def create_category(
    client,
    token: str,
) -> str:
    response = client.post(
        "/categories",
        json={
            "name": f"TEST-Inventory-{uuid.uuid4()}",
            "order_index": 1,
        },
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    assert response.status_code == 201

    return response.json()["id"]


def create_variant_with_stock(
    client,
    *,
    stock: int,
) -> str:
    """
    Create a product with one variant and return the variant UUID.
    """

    token = create_user_and_token(
        client,
        role="merchant",
    )

    category_id = create_category(
        client,
        token,
    )

    response = client.post(
        "/products",
        json={
            "title": f"TEST-Concurrent-{uuid.uuid4()}",
            "description": "Inventory concurrency test product",
            "category_id": category_id,
            "variants": [
                {
                    "sku": f"TEST-CONCURRENT-{uuid.uuid4()}",
                    "price": 100.00,
                    "stock": stock,
                    "attributes": {},
                }
            ],
            "media": [],
        },
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    assert response.status_code == 201

    return response.json()["variants"][0]["id"]


def reserve_one(
    variant_id: str,
) -> bool:
    """
    One independent reservation attempt.

    Each thread MUST have its own SQLAlchemy Session.
    Sessions are not shared between threads.
    """

    with SessionLocal() as db:
        return try_reserve_stock(
            db,
            uuid.UUID(variant_id),
            1,
        )


def test_concurrent_reservations_do_not_oversell(
    client,
):
    """
    With stock=3 and 50 competing reservation attempts:

    - exactly 3 should succeed
    - the other 47 should fail
    - final stock must be 0
    - stock must never become negative
    """

    variant_id = create_variant_with_stock(
        client,
        stock=3,
    )

    attempts = 50

    with ThreadPoolExecutor(
        max_workers=attempts
    ) as executor:

        results = list(
            executor.map(
                lambda _: reserve_one(
                    variant_id
                ),
                range(attempts),
            )
        )

    successful = sum(results)
    failed = attempts - successful

    assert successful == 3
    assert failed == 47

    with SessionLocal() as db:
        variant = db.get(
            ProductVariant,
            uuid.UUID(variant_id),
        )

        assert variant is not None
        assert variant.stock == 0
        assert variant.stock >= 0