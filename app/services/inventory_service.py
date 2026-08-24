import uuid

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.product_variant import ProductVariant



def try_reserve_stock(
    db: Session,
    variant_id: uuid.UUID,
    qty: int,
    *,
    commit: bool = True,
) -> bool:
    """
    Atomically decrement stock only when enough stock exists.

    commit=False lets a caller include the stock change in a larger
    transaction, such as creating an InventoryReservation row.
    """
    if qty <= 0:
        raise ValueError(
            "Reservation quantity must be greater than 0"
        )

    stmt = (
        update(ProductVariant)
        .where(
            ProductVariant.id == variant_id,
            ProductVariant.stock >= qty,
        )
        .values(
            stock=ProductVariant.stock - qty
        )
        .returning(ProductVariant.id)
    )

    row = db.execute(stmt).first()

    if commit:
        db.commit()

    return row is not None


def release_stock(
    db: Session,
    variant_id: uuid.UUID,
    qty: int,
    *,
    commit: bool = True,
) -> None:
    """
    Add previously reserved stock back.
    """
    if qty <= 0:
        raise ValueError(
            "Release quantity must be greater than 0"
        )

    stmt = (
        update(ProductVariant)
        .where(
            ProductVariant.id == variant_id
        )
        .values(
            stock=ProductVariant.stock + qty
        )
    )

    db.execute(stmt)

    if commit:
        db.commit()