"""
Shared pytest fixtures.

Pytest automatically discovers this file.

The fixtures here provide:
- a FastAPI TestClient
- direct database access when a test needs it
- automatic cleanup of records created by our tests

Integration tests use the real FastAPI application and PostgreSQL
database, so they exercise the same layers as normal API requests.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.db.session import SessionLocal
from app.main import app
from app.models.category import Category
from app.models.product import Product
from app.models.user import User


@pytest.fixture
def client():
    """
    Give each test access to FastAPI's TestClient.

    TestClient lets us call:

        client.post("/auth/login", ...)

    without manually running curl.
    """

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def db():
    """
    Give tests direct database access when needed.

    Most integration tests should use the API instead.
    Direct DB access is useful for setup/verification/cleanup.
    """

    session = SessionLocal()

    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def cleanup_test_data():
    """
    Automatically clean records created by tests.

    Our test records use predictable prefixes:
        users:      test-...@example.com
        categories: TEST-...
        products:   TEST-...

    This lets us run pytest repeatedly without duplicate-email/SKU
    failures while leaving normal development/seed data untouched.
    """

    yield

    db = SessionLocal()

    try:
        # Delete test products first because they reference both users
        # and categories.
        #
        # Product variants/media disappear through the product cascade.
        db.execute(
            delete(Product).where(
                Product.title.like("TEST-%")
            )
        )

        # Delete test categories after products no longer reference them.
        db.execute(
            delete(Category).where(
                Category.name.like("TEST-%")
            )
        )

        # Finally delete test users.
        db.execute(
            delete(User).where(
                User.email.like("test-%@example.com")
            )
        )

        db.commit()

    finally:
        db.close()