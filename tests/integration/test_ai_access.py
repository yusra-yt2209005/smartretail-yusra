"""
Week 5 AI endpoint authorization tests.

These tests verify that:
- the customer assistant requires authentication
- customers cannot use merchant AI generation
- merchants cannot generate content for products they do not own
"""

import uuid


def create_user_and_token(
    client,
    *,
    role: str,
) -> str:
    """
    Register a unique test user and return their JWT.
    """

    email = (
        f"test-ai-{role}-"
        f"{uuid.uuid4()}@example.com"
    )

    register = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "password123",
            "full_name": f"Test AI {role}",
            "role": role,
        },
    )

    assert register.status_code in (
        200,
        201,
    )

    login = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "password123",
        },
    )

    assert login.status_code == 200

    return login.json()[
        "access_token"
    ]


def create_category(
    client,
    token: str,
) -> str:
    """
    Create a test category.
    """

    response = client.post(
        "/categories",
        json={
            "name": (
                f"TEST-AI-Category-"
                f"{uuid.uuid4()}"
            ),
            "order_index": 1,
        },
        headers={
            "Authorization": (
                f"Bearer {token}"
            )
        },
    )

    assert response.status_code == 201

    return response.json()["id"]


def create_product(
    client,
    token: str,
    category_id: str,
) -> str:
    """
    Create a product owned by the supplied merchant.
    """

    response = client.post(
        "/products",
        json={
            "title": (
                f"TEST-AI-Product-"
                f"{uuid.uuid4()}"
            ),
            "description": (
                "TEST product for AI "
                "authorization checks."
            ),
            "category_id": category_id,
            "variants": [
                {
                    "sku": (
                        f"TEST-AI-SKU-"
                        f"{uuid.uuid4()}"
                    ),
                    "price": 999.99,
                    "stock": 5,
                    "attributes": {
                        "color": "black"
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


def test_assistant_requires_authentication(
    client,
):
    """
    Anonymous users must not access the customer AI assistant.
    """

    response = client.post(
        "/assistant/ask",
        json={
            "question": (
                "Which phone should I buy?"
            ),
            "top_k": 5,
        },
    )

    assert response.status_code == 401

    assert (
        response.json()["error"]["code"]
        == "unauthorized"
    )


def test_customer_cannot_generate_product_description(
    client,
):
    """
    Merchant AI generation endpoints must reject customers.
    """

    customer_token = (
        create_user_and_token(
            client,
            role="customer",
        )
    )

    fake_product_id = uuid.uuid4()

    response = client.post(
        (
            f"/products/"
            f"{fake_product_id}"
            f"/generate/description"
        ),
        headers={
            "Authorization": (
                f"Bearer "
                f"{customer_token}"
            )
        },
    )

    assert response.status_code == 403

    assert (
        response.json()["error"]["code"]
        == "forbidden"
    )


def test_merchant_cannot_generate_for_another_merchants_product(
    client,
):
    """
    A merchant role is not enough:
    the merchant must also own the product.
    """

    merchant_one = (
        create_user_and_token(
            client,
            role="merchant",
        )
    )

    merchant_two = (
        create_user_and_token(
            client,
            role="merchant",
        )
    )

    category_id = create_category(
        client,
        merchant_one,
    )

    product_id = create_product(
        client,
        merchant_one,
        category_id,
    )

    response = client.post(
        (
            f"/products/"
            f"{product_id}"
            f"/generate/description"
        ),
        headers={
            "Authorization": (
                f"Bearer "
                f"{merchant_two}"
            )
        },
    )

    assert response.status_code == 403

    assert (
        response.json()["error"]["code"]
        == "forbidden"
    )

    assert (
        response.json()["error"]["message"]
        == "You do not own this product"
    )