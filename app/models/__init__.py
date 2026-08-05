"""
Alembic's env.py needs `Base.metadata` to already know about every table
when it autogenerates a migration. SQLAlchemy only registers a model with
Base when the *module defining it* has been imported somewhere. Importing
all model modules here -- and importing this package from alembic/env.py --
is what makes that happen in one place instead of scattering imports.
"""

from app.models.category import Category  # noqa: F401
from app.models.product import Product, ProductStatus  # noqa: F401
from app.models.product_media import ProductMedia  # noqa: F401
from app.models.product_variant import ProductVariant  # noqa: F401
from app.models.user import User, UserRole  # noqa: F401
