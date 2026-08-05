import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationFailedError
from app.models.category import Category
from app.schemas.category import CategoryCreate, CategoryUpdate


def create_category(
    db: Session,
    data: CategoryCreate,
) -> Category:
    """
    Create a new category.

    If parent_id is provided, the referenced parent category must exist.
    """
    if data.parent_id is not None:
        parent = db.get(Category, data.parent_id)

        if parent is None:
            raise NotFoundError("Category", data.parent_id)

    category = Category(
        name=data.name,
        parent_id=data.parent_id,
        order_index=data.order_index,
    )

    db.add(category)
    db.commit()
    db.refresh(category)

    return category


def list_categories(
    db: Session,
) -> list[Category]:
    """
    Return categories in configured display order.
    """
    statement = select(Category).order_by(
        Category.order_index,
        Category.name,
    )

    return list(db.scalars(statement).all())


def get_category(
    db: Session,
    category_id: uuid.UUID,
) -> Category:
    """
    Return one category or raise NotFoundError.
    """
    category = db.get(Category, category_id)

    if category is None:
        raise NotFoundError("Category", category_id)

    return category


def update_category(
    db: Session,
    category_id: uuid.UUID,
    data: CategoryUpdate,
) -> Category:
    """
    Apply a PATCH-style partial update.
    """
    category = get_category(db, category_id)

    updates = data.model_dump(exclude_unset=True)

    if "parent_id" in updates:
        parent_id = updates["parent_id"]

        if parent_id == category.id:
            raise ValidationFailedError(
                ["A category cannot be its own parent"]
            )

        if parent_id is not None:
            parent = db.get(Category, parent_id)

            if parent is None:
                raise NotFoundError("Category", parent_id)

    for field, value in updates.items():
        setattr(category, field, value)

    db.commit()
    db.refresh(category)

    return category


def delete_category(
    db: Session,
    category_id: uuid.UUID,
) -> None:
    """
    Delete an existing category.
    """
    category = get_category(db, category_id)

    db.delete(category)
    db.commit()