from typing import Generic, TypeVar

from pydantic import BaseModel


# T is a placeholder for the item type inside the page.
#
# Example:
# Page[ProductOut]
#
# means:
# "a paginated response whose items are ProductOut objects"
T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """
    Generic pagination response used by listing endpoints.
    """

    # Records returned in the current page.
    items: list[T]

    # Total number of matching records before limit/offset are applied.
    total: int

    # Maximum number of records requested for this page.
    limit: int

    # Number of matching records skipped before this page starts.
    offset: int