"""
Integration tests for product CRUD, ownership, inventory, and listing.
"""

import uuid


def create_user_and_token(
    client,
    *,
    role: str,
) -> str:
    """
    Register a unique user and return their JWT.
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


def create_category(
    client,
    token: str,
) -> str:
    """
    Create a category for product tests and return its UUID.
    """

    response = client.post(
        "/categories",
        json={
            "name": f"TEST-Products-{uuid.uuid4()}",
            "order_index": 1,
        },
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    return response.json()["id"]


def product_payload(
    category_id: str,
    *,
    title: str,
    sku: str,
    price: float = 1000.00,
    stock: int = 10,
):
    """
    Reusable product request body.
    """

    return {
        "title": title,
        "description": "TEST product description",
        "category_id": category_id,
        "variants": [
            {
                "sku": sku,
                "price": price,
                "stock": stock,
                "attributes": {
                    "color": "black"
                },
            }
        ],
        "media": [],
    }


def test_merchant_can_create_product(client):
    """
    Merchant should be able to create a draft product with a variant.
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
        json=product_payload(
            category_id,
            title=f"TEST-Phone-{uuid.uuid4()}",
            sku=f"TEST-SKU-{uuid.uuid4()}",
        ),
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    assert response.status_code == 201

    body = response.json()

    # New products always start as draft.
    assert body["status"] == "draft"

    assert len(body["variants"]) == 1
    assert body["variants"][0]["stock"] == 10


def test_customer_cannot_create_product(client):
    """
    Product creation is merchant-only.
    """

    token = create_user_and_token(
        client,
        role="customer",
    )

    # We don't even need a real category because role authorization
    # should fail before create_product() executes.
    fake_category = str(uuid.uuid4())

    response = client.post(
        "/products",
        json=product_payload(
            fake_category,
            title=f"TEST-Customer-{uuid.uuid4()}",
            sku=f"TEST-SKU-{uuid.uuid4()}",
        ),
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"


def test_merchant_cannot_edit_another_merchants_product(client):
    """
    Role authorization alone is not enough.

    Merchant 2 is a valid merchant, but must not edit Merchant 1's
    product.
    """

    merchant_one = create_user_and_token(
        client,
        role="merchant",
    )

    merchant_two = create_user_and_token(
        client,
        role="merchant",
    )

    category_id = create_category(
        client,
        merchant_one,
    )

    created = client.post(
        "/products",
        json=product_payload(
            category_id,
            title=f"TEST-Owned-{uuid.uuid4()}",
            sku=f"TEST-SKU-{uuid.uuid4()}",
        ),
        headers={
            "Authorization": f"Bearer {merchant_one}"
        },
    )

    product_id = created.json()["id"]

    response = client.patch(
        f"/products/{product_id}",
        json={
            "title": "TEST-Unauthorized Edit"
        },
        headers={
            "Authorization": f"Bearer {merchant_two}"
        },
    )

    assert response.status_code == 403

    assert (
        response.json()["error"]["message"]
        == "You do not own this product"
    )


def test_duplicate_sku_returns_409(client):
    """
    SKU uniqueness should produce a clean ConflictError instead of a raw
    database IntegrityError.
    """

    token = create_user_and_token(
        client,
        role="merchant",
    )

    category_id = create_category(
        client,
        token,
    )

    sku = f"TEST-SKU-{uuid.uuid4()}"

    first = client.post(
        "/products",
        json=product_payload(
            category_id,
            title=f"TEST-First-{uuid.uuid4()}",
            sku=sku,
        ),
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    assert first.status_code == 201

    second = client.post(
        "/products",
        json=product_payload(
            category_id,
            title=f"TEST-Second-{uuid.uuid4()}",
            sku=sku,
        ),
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    assert second.status_code == 409
    assert second.json()["error"]["code"] == "conflict"


def test_published_in_stock_product_is_public(client):
    """
    Anonymous visitors should see published products that have stock.
    """

    token = create_user_and_token(
        client,
        role="merchant",
    )

    category_id = create_category(
        client,
        token,
    )

    title = f"TEST-Public-Phone-{uuid.uuid4()}"

    created = client.post(
        "/products",
        json=product_payload(
            category_id,
            title=title,
            sku=f"TEST-SKU-{uuid.uuid4()}",
            stock=10,
        ),
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    product_id = created.json()["id"]

    # Change draft → published.
    publish = client.post(
        f"/products/{product_id}/publish",
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    assert publish.status_code == 200
    assert publish.json()["status"] == "published"

    # No Authorization header here: anonymous visitor.
    listing = client.get(
        "/products",
        params={
            "search": title
        },
    )

    assert listing.status_code == 200

    body = listing.json()

    assert body["total"] == 1
    assert body["items"][0]["title"] == title


def test_out_of_stock_product_is_hidden_publicly(client):
    """
    Published alone is not enough for anonymous/customer visibility.

    There must also be an active variant with stock > 0.
    """

    token = create_user_and_token(
        client,
        role="merchant",
    )

    category_id = create_category(
        client,
        token,
    )

    title = f"TEST-SoldOut-{uuid.uuid4()}"

    created = client.post(
        "/products",
        json=product_payload(
            category_id,
            title=title,
            sku=f"TEST-SKU-{uuid.uuid4()}",
            stock=0,
        ),
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    product_id = created.json()["id"]

    client.post(
        f"/products/{product_id}/publish",
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    listing = client.get(
        "/products",
        params={
            "search": title
        },
    )

    assert listing.status_code == 200
    assert listing.json()["total"] == 0


def test_product_price_filter(client):
    """
    Price filters operate on ProductVariant.price.
    """

    token = create_user_and_token(
        client,
        role="merchant",
    )

    category_id = create_category(
        client,
        token,
    )

    title = f"TEST-Price-{uuid.uuid4()}"

    created = client.post(
        "/products",
        json=product_payload(
            category_id,
            title=title,
            sku=f"TEST-SKU-{uuid.uuid4()}",
            price=1500.00,
            stock=5,
        ),
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    product_id = created.json()["id"]

    client.post(
        f"/products/{product_id}/publish",
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    response = client.get(
        "/products",
        params={
            "search": title,
            "min_price": 1000,
            "max_price": 2000,
        },
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1


def test_pagination_limit_is_respected(client):
    """
    limit controls the maximum number of returned items.

    total still represents all matching records.
    """

    response = client.get(
        "/products",
        params={
            "limit": 2,
            "offset": 0,
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["limit"] == 2
    assert body["offset"] == 0
    assert len(body["items"]) <= 2