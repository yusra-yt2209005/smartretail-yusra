import uuid
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload
from app.core.exceptions import ValidationFailedError

from app.core.exceptions import (
    ConflictError,
    ForbiddenError,
    NotFoundError,
)
from app.models.category import Category
from app.models.product import Product, ProductStatus
from app.models.product_media import ProductMedia
from app.models.product_variant import ProductVariant
from app.models.user import User, UserRole
from app.schemas.product import ProductCreate, ProductUpdate, VariantUpdate


def _with_relations(stmt):
    """
    Eager-load variants and media using separate SELECT queries.

    This avoids:
    - N+1 lazy-loading queries
    - duplicate Product rows caused by joining one-to-many relationships
    """
    return stmt.options(
        selectinload(Product.variants),
        selectinload(Product.media),
    )


def get_product(
    db: Session,
    product_id: uuid.UUID,
) -> Product:
    stmt = _with_relations(
        select(Product).where(Product.id == product_id)
    )

    product = db.scalar(stmt)

    if product is None:
        raise NotFoundError("Product", product_id)

    return product


def _assert_can_edit(
    product: Product,
    user: User,
) -> None:
    """
    Admins may edit any product.

    Merchants may only edit products they own.
    """
    if user.role == UserRole.ADMIN:
        return

    if (
        user.role != UserRole.MERCHANT
        or product.merchant_id != user.id
    ):
        raise ForbiddenError(
            "You do not own this product"
        )


def _validate_category(
    db: Session,
    category_id: uuid.UUID | None,
) -> None:
    if category_id is None:
        return

    category = db.get(Category, category_id)

    if category is None:
        raise NotFoundError(
            "Category",
            category_id,
        )


def _validate_unique_sku(
    db: Session,
    sku: str,
) -> None:
    existing = db.scalar(
        select(ProductVariant).where(
            ProductVariant.sku == sku
        )
    )

    if existing is not None:
        raise ConflictError(
            f"Variant with SKU '{sku}' already exists"
        )


def create_product(
    db: Session,
    data: ProductCreate,
    merchant: User,
) -> Product:
    """
    Create a draft product with variants and optional media.

    Ownership comes from the authenticated merchant, never from
    client-supplied merchant_id.
    """
    _validate_category(
        db,
        data.category_id,
    )

    for variant in data.variants:
        _validate_unique_sku(
            db,
            variant.sku,
        )

    product = Product(
        merchant_id=merchant.id,
        title=data.title,
        description=data.description,
        category_id=data.category_id,
        status=ProductStatus.DRAFT,
    )

    product.variants = [
        ProductVariant(
            sku=variant.sku,
            price=variant.price,
            stock=variant.stock,
            attributes=variant.attributes,
        )
        for variant in data.variants
    ]

    product.media = [
        ProductMedia(
            url=media.url,
            order_index=media.order_index,
        )
        for media in data.media
    ]

    db.add(product)
    db.commit()
    db.refresh(product)

    return get_product(
        db,
        product.id,
    )


def update_product(
    db: Session,
    product_id: uuid.UUID,
    data: ProductUpdate,
    user: User,
) -> Product:
    product = get_product(
        db,
        product_id,
    )

    _assert_can_edit(
        product,
        user,
    )

    updates = data.model_dump(
        exclude_unset=True
    )

    if "category_id" in updates:
        _validate_category(
            db,
            updates["category_id"],
        )

    for field, value in updates.items():
        setattr(
            product,
            field,
            value,
        )

    db.commit()
    db.refresh(product)

    return get_product(
        db,
        product.id,
    )


def set_product_status(
    db: Session,
    product_id: uuid.UUID,
    status: ProductStatus,
    user: User,
) -> Product:
    """
    Week 1 status transition.

    Week 2 can replace this with a workflow-driven publishing process.
    """
    product = get_product(
        db,
        product_id,
    )

    _assert_can_edit(
        product,
        user,
    )

    product.status = status

    db.commit()
    db.refresh(product)

    return product


def update_variant(
    db: Session,
    product_id: uuid.UUID,
    variant_id: uuid.UUID,
    data: VariantUpdate,
    user: User,
) -> ProductVariant:
    product = get_product(
        db,
        product_id,
    )

    _assert_can_edit(
        product,
        user,
    )

    variant = db.get(
        ProductVariant,
        variant_id,
    )

    if (
        variant is None
        or variant.product_id != product.id
    ):
        raise NotFoundError(
            "Variant",
            variant_id,
        )

    updates = data.model_dump(
        exclude_unset=True
    )

    for field, value in updates.items():
        setattr(
            variant,
            field,
            value,
        )

    db.commit()
    db.refresh(variant)

    return variant


def delete_product(
    db: Session,
    product_id: uuid.UUID,
    user: User,
) -> None:
    product = get_product(
        db,
        product_id,
    )

    _assert_can_edit(
        product,
        user,
    )

    db.delete(product)
    db.commit()


def list_products(
    db: Session,
    *,
    viewer: User | None,
    category_id: uuid.UUID | None = None,
    min_price: Decimal | None = None,
    max_price: Decimal | None = None,
    in_stock: bool | None = None,
    search: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[Product], int]:
    """
    Return visible products plus total count.

    Visibility:
    - anonymous/customer:
        published products only
    - merchant:
        published products + their own products in any status
    - admin:
        all products
    """
    stmt = select(Product)

    if viewer is None or viewer.role == UserRole.CUSTOMER:
        stmt = stmt.where(
            Product.status == ProductStatus.PUBLISHED
        )

        # Public/customer catalog should only expose products that have
        # at least one active, in-stock variant.
        stmt = stmt.where(
            select(ProductVariant.id)
            .where(
                ProductVariant.product_id == Product.id,
                ProductVariant.is_active.is_(True),
                ProductVariant.stock > 0,
            )
            .exists()
        )

    elif viewer.role == UserRole.MERCHANT:
        stmt = stmt.where(
            (Product.status == ProductStatus.PUBLISHED)
            | (Product.merchant_id == viewer.id)
        )

    # ADMIN: no visibility restriction.

    if category_id is not None:
        stmt = stmt.where(
            Product.category_id == category_id
        )

    if search:
        stmt = stmt.where(
            Product.title.ilike(
                f"%{search}%"
            )
        )

    if (
        min_price is not None
        or max_price is not None
        or in_stock is not None
    ):
        variant_conditions = [
            ProductVariant.product_id == Product.id
        ]

        if min_price is not None:
            variant_conditions.append(
                ProductVariant.price >= min_price
            )

        if max_price is not None:
            variant_conditions.append(
                ProductVariant.price <= max_price
            )

        if in_stock is not None:
            variant_conditions.append(
                ProductVariant.stock > 0
                if in_stock
                else ProductVariant.stock == 0
            )

        stmt = stmt.where(
            select(ProductVariant.id)
            .where(*variant_conditions)
            .exists()
        )

    total = db.scalar(
        select(func.count())
        .select_from(stmt.subquery())
    )

    stmt = (
        _with_relations(stmt)
        .order_by(Product.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    items = list(
        db.scalars(stmt).all()
    )

    return items, total or 0


def publish_product(
    db: Session,
    product_id: uuid.UUID,
    user: User,
) -> Product:
    """
    Week 1 synchronous publish validation.

    Week 2 can replace the internal implementation with the Temporal
    publishing workflow while keeping the API endpoint stable.
    """
    product = get_product(
        db,
        product_id,
    )

    _assert_can_edit(
        product,
        user,
    )

    errors: list[str] = []

    if not product.title.strip():
        errors.append("title is required")

    if not product.description.strip():
        errors.append("description is required")

    if not product.variants:
        errors.append(
            "at least one variant is required"
        )

    for variant in product.variants:
        if variant.price <= 0:
            errors.append(
                f"variant '{variant.sku}' must have a price greater than 0"
            )

        if variant.stock < 0:
            errors.append(
                f"variant '{variant.sku}' cannot have negative stock"
            )

    if errors:
        raise ValidationFailedError(errors)

    product.status = ProductStatus.PUBLISHED

    db.commit()
    db.refresh(product)

    return get_product(
        db,
        product.id,
    )