"""
Development seed data for SmartRetail.

Purpose:
- Give the local database predictable data for development/testing.
- Provide enough products to test:
    * public visibility
    * merchant visibility
    * categories
    * price filters
    * stock filters
    * search
    * pagination

This script is NOT an Alembic migration.

Alembic creates the database STRUCTURE.
This script inserts example DATA into that structure.
"""

from decimal import Decimal

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.category import Category
from app.models.product import Product, ProductStatus
from app.models.product_media import ProductMedia
from app.models.product_variant import ProductVariant
from app.models.user import User, UserRole


# ---------------------------------------------------------------------
# Helper: get an existing user or create it
# ---------------------------------------------------------------------


def get_or_create_user(
    db,
    *,
    email: str,
    password: str,
    full_name: str,
    role: UserRole,
) -> User:
    """
    Look for a user by email.

    If the user already exists:
        return the existing row

    Otherwise:
        create it

    This makes the seed script safer to run multiple times.
    """

    user = db.scalar(
        select(User).where(User.email == email)
    )

    if user is not None:
        return user

    user = User(
        email=email,

        # Never store the plaintext seed password.
        password_hash=hash_password(password),

        full_name=full_name,
        role=role,
    )

    db.add(user)

    # flush() sends the INSERT to PostgreSQL without committing the
    # entire transaction yet.
    #
    # We need this because the user's generated UUID may be needed
    # immediately when creating products.
    db.flush()

    return user


# ---------------------------------------------------------------------
# Helper: get an existing category or create it
# ---------------------------------------------------------------------


def get_or_create_category(
    db,
    *,
    name: str,
    order_index: int,
    parent: Category | None = None,
) -> Category:
    """
    Find a category by name.

    If it does not exist, create it.
    """

    category = db.scalar(
        select(Category).where(Category.name == name)
    )

    if category is not None:
        return category

    category = Category(
        name=name,

        # If parent is None, this becomes a top-level category.
        parent_id=parent.id if parent else None,

        order_index=order_index,
    )

    db.add(category)
    db.flush()

    return category


# ---------------------------------------------------------------------
# Helper: check whether a product already exists using its SKU
# ---------------------------------------------------------------------


def sku_exists(
    db,
    sku: str,
) -> bool:
    """
    SKU is globally unique in our database.

    We can therefore use it as a simple way to detect whether a seeded
    product/variant has already been inserted.
    """

    existing = db.scalar(
        select(ProductVariant).where(
            ProductVariant.sku == sku
        )
    )

    return existing is not None


# ---------------------------------------------------------------------
# Helper: create one product + one variant + optional media
# ---------------------------------------------------------------------


def create_product(
    db,
    *,
    merchant: User,
    category: Category,
    title: str,
    description: str,
    status: ProductStatus,
    sku: str,
    price: Decimal,
    stock: int,
    attributes: dict,
    media_url: str | None = None,
) -> None:
    """
    Create one seeded product.

    For our initial test dataset, every seeded product gets one variant.
    That is enough to test price/stock/search/pagination behavior.

    If the SKU already exists, we skip this product so rerunning the
    seed script does not create duplicates.
    """

    if sku_exists(db, sku):
        print(f"Skipping existing SKU: {sku}")
        return

    product = Product(
        # Ownership comes from the actual seeded merchant.
        merchant_id=merchant.id,

        category_id=category.id,

        title=title,
        description=description,

        # Unlike normal POST /products, seed data may deliberately start
        # as published/draft/inactive so we can test visibility rules.
        status=status,
    )

    # Create the variant through the SQLAlchemy relationship.
    product.variants.append(
        ProductVariant(
            sku=sku,
            price=price,
            stock=stock,
            attributes=attributes,
            is_active=True,
        )
    )

    if media_url is not None:
        product.media.append(
            ProductMedia(
                url=media_url,
                order_index=0,

                # Week 1 doesn't actually process media yet.
                processed=False,
            )
        )

    db.add(product)


# ---------------------------------------------------------------------
# Main seed function
# ---------------------------------------------------------------------


def seed() -> None:
    """
    Insert the development dataset.

    Everything runs through one SQLAlchemy Session.
    """

    db = SessionLocal()

    try:
        # -------------------------------------------------------------
        # USERS
        # -------------------------------------------------------------

        # These credentials are intentionally simple because this is
        # LOCAL DEVELOPMENT seed data, not production data.

        merchant_one = get_or_create_user(
            db,
            email="seedmerchant1@example.com",
            password="password123",
            full_name="Seed Merchant One",
            role=UserRole.MERCHANT,
        )

        merchant_two = get_or_create_user(
            db,
            email="seedmerchant2@example.com",
            password="password123",
            full_name="Seed Merchant Two",
            role=UserRole.MERCHANT,
        )

        get_or_create_user(
            db,
            email="seedcustomer@example.com",
            password="password123",
            full_name="Seed Customer",
            role=UserRole.CUSTOMER,
        )

        get_or_create_user(
            db,
            email="seedadmin@example.com",
            password="password123",
            full_name="Seed Admin",
            role=UserRole.ADMIN,
        )

        # -------------------------------------------------------------
        # CATEGORIES
        # -------------------------------------------------------------

        electronics = get_or_create_category(
            db,
            name="Seed Electronics",
            order_index=1,
        )

        phones = get_or_create_category(
            db,
            name="Seed Phones",
            order_index=1,
            parent=electronics,
        )

        laptops = get_or_create_category(
            db,
            name="Seed Laptops",
            order_index=2,
            parent=electronics,
        )

        accessories = get_or_create_category(
            db,
            name="Seed Accessories",
            order_index=3,
            parent=electronics,
        )

        # -------------------------------------------------------------
        # PRODUCTS
        # -------------------------------------------------------------

        # 1. Published + in stock + relatively cheap phone.
        create_product(
            db,
            merchant=merchant_one,
            category=phones,
            title="Budget Phone",
            description="Affordable smartphone for everyday use.",
            status=ProductStatus.PUBLISHED,
            sku="SEED-PHONE-BUDGET",
            price=Decimal("499.00"),
            stock=25,
            attributes={
                "color": "black",
                "storage": "64GB",
            },
            media_url="https://example.com/budget-phone.jpg",
        )

        # 2. Published + in stock + mid-range phone.
        create_product(
            db,
            merchant=merchant_one,
            category=phones,
            title="Smartphone Alpha",
            description="Mid-range smartphone with 128GB storage.",
            status=ProductStatus.PUBLISHED,
            sku="SEED-PHONE-ALPHA",
            price=Decimal("1499.00"),
            stock=10,
            attributes={
                "color": "blue",
                "storage": "128GB",
            },
            media_url="https://example.com/phone-alpha.jpg",
        )

        # 3. Published but OUT OF STOCK.
        #
        # Anonymous/customer listing should NOT show this product because
        # our visibility rule requires an active variant with stock > 0.
        create_product(
            db,
            merchant=merchant_one,
            category=phones,
            title="Sold Out Phone",
            description="Published phone with no available inventory.",
            status=ProductStatus.PUBLISHED,
            sku="SEED-PHONE-SOLDOUT",
            price=Decimal("899.00"),
            stock=0,
            attributes={
                "color": "white",
                "storage": "128GB",
            },
        )

        # 4. Published + in stock + expensive laptop.
        create_product(
            db,
            merchant=merchant_one,
            category=laptops,
            title="Laptop Pro",
            description="High-performance laptop for professional work.",
            status=ProductStatus.PUBLISHED,
            sku="SEED-LAPTOP-PRO",
            price=Decimal("3499.00"),
            stock=5,
            attributes={
                "ram": "16GB",
                "storage": "1TB",
            },
            media_url="https://example.com/laptop-pro.jpg",
        )

        # 5. Another published laptop for pagination/filter testing.
        create_product(
            db,
            merchant=merchant_two,
            category=laptops,
            title="Laptop Air",
            description="Lightweight laptop for students and travel.",
            status=ProductStatus.PUBLISHED,
            sku="SEED-LAPTOP-AIR",
            price=Decimal("2499.00"),
            stock=8,
            attributes={
                "ram": "8GB",
                "storage": "512GB",
            },
        )

        # 6. Published accessory.
        create_product(
            db,
            merchant=merchant_two,
            category=accessories,
            title="Wireless Charger",
            description="Fast wireless charging pad.",
            status=ProductStatus.PUBLISHED,
            sku="SEED-CHARGER-WIRELESS",
            price=Decimal("149.00"),
            stock=50,
            attributes={
                "color": "black",
            },
        )

        # 7. DRAFT belonging to Merchant One.
        #
        # Anonymous/customer:
        #     must NOT see it.
        #
        # Merchant One:
        #     SHOULD see it.
        create_product(
            db,
            merchant=merchant_one,
            category=phones,
            title="Secret Draft Phone",
            description="A phone that has not been published yet.",
            status=ProductStatus.DRAFT,
            sku="SEED-PHONE-DRAFT",
            price=Decimal("1299.00"),
            stock=12,
            attributes={
                "color": "green",
                "storage": "256GB",
            },
        )

        # 8. DRAFT belonging to Merchant Two.
        #
        # Merchant One should NOT see this through the merchant-specific
        # visibility rule unless it becomes published.
        create_product(
            db,
            merchant=merchant_two,
            category=laptops,
            title="Merchant Two Draft Laptop",
            description="Unpublished laptop owned by merchant two.",
            status=ProductStatus.DRAFT,
            sku="SEED-LAPTOP-DRAFT",
            price=Decimal("1999.00"),
            stock=4,
            attributes={
                "ram": "16GB",
            },
        )

        # 9. INACTIVE product.
        #
        # Public/customer users must not see this.
        create_product(
            db,
            merchant=merchant_one,
            category=accessories,
            title="Old USB Cable",
            description="Inactive catalog item.",
            status=ProductStatus.INACTIVE,
            sku="SEED-CABLE-INACTIVE",
            price=Decimal("39.00"),
            stock=100,
            attributes={
                "length": "1m",
            },
        )

        # -------------------------------------------------------------
        # COMMIT
        # -------------------------------------------------------------

        # Until this point, changes are part of the current transaction.
        #
        # commit() makes all inserted rows permanent.
        db.commit()

        print("Seed completed successfully.")

    except Exception:
        # If anything fails halfway through, undo all uncommitted changes.
        #
        # This prevents a partially seeded database.
        db.rollback()
        raise

    finally:
        # Always release the database connection.
        db.close()


# ---------------------------------------------------------------------
# Script entry point
# ---------------------------------------------------------------------


if __name__ == "__main__":
    seed()