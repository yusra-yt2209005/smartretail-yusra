"""
Integration tests for authentication endpoints.

These tests exercise the full FastAPI → service → database flow.
"""

import uuid


def unique_email(prefix: str) -> str:
    """
    Generate a unique email so tests do not conflict with previous runs.
    """

    return f"test-{prefix}-{uuid.uuid4()}@example.com"


def test_register_user(client):
    """
    POST /auth/register should:
    - return 201
    - create the requested account
    - never return password_hash
    """

    email = unique_email("register")

    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "password123",
            "full_name": "Test Merchant",
            "role": "merchant",
        },
    )

    assert response.status_code == 201

    body = response.json()

    assert body["email"] == email
    assert body["role"] == "merchant"
    assert body["is_active"] is True

    # Security check:
    assert "password" not in body
    assert "password_hash" not in body


def test_duplicate_email_returns_409(client):
    """
    Registering the same email twice should return ConflictError → 409.
    """

    email = unique_email("duplicate")

    payload = {
        "email": email,
        "password": "password123",
        "full_name": "Duplicate Test",
        "role": "customer",
    }

    first = client.post(
        "/auth/register",
        json=payload,
    )

    assert first.status_code == 201

    second = client.post(
        "/auth/register",
        json=payload,
    )

    assert second.status_code == 409

    body = second.json()

    assert body["error"]["code"] == "conflict"


def test_login_returns_bearer_token(client):
    """
    A registered user should be able to log in and receive a JWT.
    """

    email = unique_email("login")

    client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "password123",
            "full_name": "Login Test",
            "role": "merchant",
        },
    )

    response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "password123",
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["access_token"]
    assert body["token_type"] == "bearer"


def test_wrong_password_returns_401(client):
    """
    Authentication with the wrong password must fail.
    """

    email = unique_email("wrong-password")

    client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "password123",
            "full_name": "Wrong Password Test",
            "role": "customer",
        },
    )

    response = client.post(
        "/auth/login",
        json={
            "email": email,
            "password": "wrong-password",
        },
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_me_requires_authentication(client):
    """
    GET /auth/me without a bearer token should return 401.
    """

    response = client.get("/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_me_returns_current_user(client):
    """
    A valid JWT should identify and load the current database user.
    """

    email = unique_email("me")

    client.post(
        "/auth/register",
        json={
            "email": email,
            "password": "password123",
            "full_name": "Current User Test",
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

    token = login.json()["access_token"]

    response = client.get(
        "/auth/me",
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    assert response.status_code == 200
    assert response.json()["email"] == email