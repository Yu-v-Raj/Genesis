"""Query parameters for cursor-paged lists (see core_services/pagination.py)."""

from typing import Annotated

from fastapi import HTTPException, Query, status

from backend.app.core.core_services.pagination import PageCursor, decode_cursor

BeforeCursor = Annotated[
    str | None,
    Query(max_length=100, description="Continue after this cursor: the previous page's next_before. A bare ISO time means created strictly before it."),
]


def page_cursor(before: str | None) -> PageCursor | None:
    if before is None or not before.strip():
        return None
    try:
        return decode_cursor(before)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="That page cursor isn't valid. Use next_before from the previous page.") from error
