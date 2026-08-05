"""
Integration tests for category CRUD and authorization.
"""

import uuid


def create_user_and_token(
    client,
    *,
    role: str,
) -> str:
    """
    Small test helper:
    register a unique user → login → return JWT.
    """

    email = f"test-{role}-{uuid.uuid4()}@example.com"

    client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "password123",
            "full_name": f"Test {role}",
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


def test_merchant_can_create_category(client):
    """
    Merchants are allowed to create categories.
    """

    token = create_user_and_token(
        client,
        role="merchant",
    )

    name = f"TEST-Category-{uuid.uuid4()}"

    response = client.post(
        "/categories",
        json={
            "name": name,
            "order_index": 1,
        },
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    assert response.status_code == 201
    assert response.json()["name"] == name


def test_customer_cannot_create_category(client):
    """
    A valid customer is authenticated but not authorized.

    Expected:
        403 Forbidden
    """

    token = create_user_and_token(
        client,
        role="customer",
    )

    response = client.post(
        "/categories",
        json={
            "name": f"TEST-Forbidden-{uuid.uuid4()}",
            "order_index": 1,
        },
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_categories_are_public(client):
    """
    GET /categories requires no authentication.
    """

    response = client.get("/categories")

    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_category_cannot_be_its_own_parent(client):
    """
    Our category service should reject a self-referencing parent.
    """

    token = create_user_and_token(
        client,
        role="merchant",
    )

    create_response = client.post(
        "/categories",
        json={
            "name": f"TEST-SelfParent-{uuid.uuid4()}",
            "order_index": 1,
        },
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    category_id = create_response.json()["id"]

    response = client.patch(
        f"/categories/{category_id}",
        json={
            "parent_id": category_id
        },
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_failed"