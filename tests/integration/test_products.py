"""
Integration tests for product CRUD, ownership, inventory, and listing.
"""

import uuid

import pytest

from app.api.v1 import products as products_api
from app.db.session import SessionLocal
from app.models.product import Product, ProductStatus

class FakeWorkflowHandle:
    def __init__(
        self,
        workflow_id: str,
        query_step: str = "processing_media",
    ):
        self.id = workflow_id
        self.query_step = query_step

    async def query(self, *args, **kwargs):
        return self.query_step


class FakeTemporalClient:
    def __init__(self):
        self.started_workflows = []
        self.query_step = "processing_media"

    async def start_workflow(
        self,
        workflow,
        product_id,
        *,
        id,
        task_queue,
    ):
        self.started_workflows.append(
            {
                "workflow": workflow,
                "product_id": product_id,
                "workflow_id": id,
                "task_queue": task_queue,
            }
        )

        return FakeWorkflowHandle(id)

    def get_workflow_handle(
        self,
        workflow_id: str,
    ):
        return FakeWorkflowHandle(
            workflow_id,
            query_step=self.query_step,
        )


@pytest.fixture
def fake_temporal(monkeypatch):
    """
    Replace the real Temporal connection with an in-memory fake.

    API integration tests can therefore verify workflow starting/querying
    without requiring a running Temporal server.
    """
    temporal_client = FakeTemporalClient()

    async def get_fake_temporal_client():
        return temporal_client

    monkeypatch.setattr(
        products_api,
        "get_temporal_client",
        get_fake_temporal_client,
    )

    return temporal_client

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

    set_product_status_in_db(
        product_id,
        ProductStatus.PUBLISHED,
    )

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
    set_product_status_in_db(
        product_id,
        ProductStatus.PUBLISHED,
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

    set_product_status_in_db(
        product_id,
        ProductStatus.PUBLISHED,
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



def create_status_test_product(client) -> tuple[str, str]:
    """
    Create a valid draft product and return:
    (merchant_token, product_id)
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
            title=f"TEST-Status-{uuid.uuid4()}",
            sku=f"TEST-SKU-{uuid.uuid4()}",
        ),
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    assert response.status_code == 201

    return token, response.json()["id"]


def set_product_status_in_db(
    product_id: str,
    status: ProductStatus,
) -> None:
    """
    Put a product into a specific lifecycle state for transition tests.

    This bypasses the API intentionally because PUBLISHING and
    PUBLISH_FAILED will normally be controlled by Temporal in Week 2.
    """

    with SessionLocal() as db:
        product = db.get(
            Product,
            uuid.UUID(product_id),
        )

        assert product is not None

        product.status = status
        db.commit()


def test_publish_while_already_publishing_returns_409(client):
    """
    A second publish request must not start while publishing is
    already in progress.
    """

    token, product_id = create_status_test_product(client)

    set_product_status_in_db(
        product_id,
        ProductStatus.PUBLISHING,
    )

    response = client.post(
        f"/products/{product_id}/publish",
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_publish_while_already_published_returns_409(client):
    """
    A successfully published product cannot be published again.
    """

    token, product_id = create_status_test_product(client)

    set_product_status_in_db(
        product_id,
        ProductStatus.PUBLISHED,
    )

    response = client.post(
        f"/products/{product_id}/publish",
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_publish_failed_product_can_retry(
    client,
    fake_temporal,
):
    """
    PUBLISH_FAILED is a legal state from which another Temporal
    publishing workflow can be started.
    """

    token, product_id = create_status_test_product(
        client
    )

    set_product_status_in_db(
        product_id,
        ProductStatus.PUBLISH_FAILED,
    )

    response = client.post(
        f"/products/{product_id}/publish",
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    assert response.status_code == 202

    body = response.json()

    assert body["product_id"] == product_id
    assert body["status"] == "publishing"
    assert (
        body["workflow_id"]
        == f"publish-product-{product_id}"
    )

    # The API performs the entry transition synchronously.
    with SessionLocal() as db:
        product = db.get(
            Product,
            uuid.UUID(product_id),
        )

        assert product is not None
        assert (
            product.status
            == ProductStatus.PUBLISHING
        )

    # And Temporal was actually asked to start the workflow.
    assert len(
        fake_temporal.started_workflows
    ) == 1

    assert (
        fake_temporal.started_workflows[0][
            "product_id"
        ]
        == product_id
    )

def test_publish_starts_temporal_workflow_and_returns_202(
    client,
    fake_temporal,
):
    """
    Publishing a DRAFT product should start Temporal asynchronously
    and immediately return 202 + workflow id.
    """

    token, product_id = create_status_test_product(
        client
    )

    response = client.post(
        f"/products/{product_id}/publish",
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    assert response.status_code == 202

    body = response.json()

    assert body == {
        "product_id": product_id,
        "workflow_id": (
            f"publish-product-{product_id}"
        ),
        "status": "publishing",
    }

    # The API must move DRAFT -> PUBLISHING before returning.
    with SessionLocal() as db:
        product = db.get(
            Product,
            uuid.UUID(product_id),
        )

        assert product is not None
        assert (
            product.status
            == ProductStatus.PUBLISHING
        )

    # Verify start_workflow() was actually called.
    assert len(
        fake_temporal.started_workflows
    ) == 1

    started = fake_temporal.started_workflows[0]

    assert started["product_id"] == product_id
    assert (
        started["workflow_id"]
        == f"publish-product-{product_id}"
    )
def test_publish_status_queries_temporal(
    client,
    fake_temporal,
):
    """
    /publish-status should return both the durable DB status and
    Temporal's finer-grained workflow progress.
    """

    token, product_id = create_status_test_product(
        client
    )

    set_product_status_in_db(
        product_id,
        ProductStatus.PUBLISHING,
    )

    fake_temporal.query_step = "processing_media"

    response = client.get(
        f"/products/{product_id}/publish-status",
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    assert response.status_code == 200

    body = response.json()

    assert body["product_id"] == product_id
    assert body["db_status"] == "publishing"
    assert (
        body["workflow_step"]
        == "processing_media"
    )

def test_draft_product_cannot_be_deactivated(client):
    """
    Only a published product may be deactivated.
    """

    token, product_id = create_status_test_product(client)

    response = client.post(
        f"/products/{product_id}/deactivate",
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_published_product_can_be_deactivated(client):
    """
    PUBLISHED -> INACTIVE is a legal transition.
    """

    token, product_id = create_status_test_product(client)

    set_product_status_in_db(
        product_id,
        ProductStatus.PUBLISHED,
    )

    response = client.post(
        f"/products/{product_id}/deactivate",
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "inactive"


@pytest.mark.parametrize(
    "current_status",
    [
        ProductStatus.PUBLISHING,
        ProductStatus.PUBLISH_FAILED,
        ProductStatus.INACTIVE,
    ],
)
def test_illegal_deactivate_states_return_409(
    client,
    current_status,
):
    """
    Deactivation must reject every state except PUBLISHED.
    """

    token, product_id = create_status_test_product(client)

    set_product_status_in_db(
        product_id,
        current_status,
    )

    response = client.post(
        f"/products/{product_id}/deactivate",
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_second_publish_while_workflow_in_progress_returns_409(
    client,
    fake_temporal,
):
    """
    Once the first request changes DRAFT -> PUBLISHING, another
    publish request must immediately receive 409.
    """

    token, product_id = create_status_test_product(
        client
    )

    first = client.post(
        f"/products/{product_id}/publish",
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    assert first.status_code == 202
    assert first.json()["status"] == "publishing"

    second = client.post(
        f"/products/{product_id}/publish",
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    assert second.status_code == 409
    assert (
        second.json()["error"]["code"]
        == "conflict"
    )

    # Only the first request should have reached Temporal.
    assert len(
        fake_temporal.started_workflows
    ) == 1

def test_cannot_deactivate_draft_product(client):
    """
    Only PUBLISHED products can be deactivated.
    """

    token = create_user_and_token(
        client,
        role="merchant",
    )

    category_id = create_category(
        client,
        token,
    )

    created = client.post(
        "/products",
        json=product_payload(
            category_id,
            title=f"TEST-Draft-Deactivate-{uuid.uuid4()}",
            sku=f"TEST-SKU-{uuid.uuid4()}",
        ),
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    product_id = created.json()["id"]

    # Product is still DRAFT here.
    response = client.post(
        f"/products/{product_id}/deactivate",
        headers={
            "Authorization": f"Bearer {token}"
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"