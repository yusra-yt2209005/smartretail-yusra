import uuid


from sqlalchemy.orm import Session

from sqlalchemy import func, select

from app.core.exceptions import ConflictError

from app.core.exceptions import NotFoundError, ValidationFailedError
from app.models.category import Category
from app.schemas.category import CategoryCreate, CategoryUpdate


def create_category(
    db: Session,
    data: CategoryCreate,
) -> Category:
    """
    Create a category.

    Category names must be unique.
    The comparison is case-insensitive, so:

        Electronics
        electronics
        ELECTRONICS

    are considered the same category.
    """

    # Look for an existing category with the same name.
    #
    # func.lower() makes the check case-insensitive.
    existing_category = db.scalar(
        select(Category).where(
            func.lower(Category.name) == data.name.strip().lower()
        )
    )

    if existing_category is not None:
        raise ConflictError(
            f"Category '{data.name}' already exists"
        )

    # If this is a subcategory, make sure its parent exists.
    if data.parent_id is not None:
        parent = db.get(Category, data.parent_id)

        if parent is None:
            raise NotFoundError("Parent category not found")

    category = Category(
        # strip() prevents names like:
        #
        # "Electronics"
        # " Electronics "
        #
        # from being treated differently.
        name=data.name.strip(),
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

    # ------------------------------------------------------------
    # CHECK CATEGORY NAME UNIQUENESS
    # ------------------------------------------------------------

    # Only run this check if the PATCH request actually includes "name".
    if "name" in updates:
        # Remove accidental spaces around the category name.
        new_name = updates["name"].strip()

        # Look for another category with the same name,
        # ignoring capitalization.
        #
        # Example:
        # "Electronics" and "electronics" are treated as the same.
        existing_category = db.scalar(
            select(Category).where(
                func.lower(Category.name) == new_name.lower(),

                # Do not compare the category against itself.
                Category.id != category.id,
            )
        )

        # If another category already has this name,
        # reject the update with HTTP 409 Conflict.
        if existing_category is not None:
            raise ConflictError(
                f"Category '{new_name}' already exists"
            )

        # Store the cleaned version of the name.
        updates["name"] = new_name

    # ------------------------------------------------------------
    # CHECK PARENT CATEGORY
    # ------------------------------------------------------------

    if "parent_id" in updates:
        parent_id = updates["parent_id"]

        # Prevent:
        #
        # Electronics
        #   parent_id = Electronics.id
        #
        # A category cannot be its own parent.
        if parent_id == category.id:
            raise ValidationFailedError(
                ["A category cannot be its own parent"]
            )

        # If parent_id is not null, make sure that category exists.
        if parent_id is not None:
            parent = db.get(Category, parent_id)

            if parent is None:
                raise NotFoundError("Category", parent_id)

    # ------------------------------------------------------------
    # APPLY PATCH FIELDS
    # ------------------------------------------------------------

    # Example:
    #
    # updates = {
    #     "name": "Gaming Laptops",
    #     "order_index": 2
    # }
    #
    # setattr() applies each supplied field to the SQLAlchemy object.
    for field, value in updates.items():
        setattr(category, field, value)

    # Save the changes permanently.
    db.commit()

    # Reload the object with the latest database values.
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