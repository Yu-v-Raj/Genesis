"""Stable keyset cursors for newest-first lists ordered by ``(created_at, id)``.

A timestamp alone is ambiguous: records created in the same microsecond would be skipped
at a page boundary. A cursor therefore names the last record returned, by its creation
time *and* its id, and the next page continues strictly after that pair in the same
descending order, so successive pages never skip or repeat a record.

The cursor travels as an opaque, URL-safe string: ``2026-10-16T10:00:00.000000Z_<hex id>``.
A bare ISO timestamp is still accepted and means "created strictly before this time".
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypeVar
from uuid import UUID

from sqlalchemy import and_, or_
from sqlalchemy.sql.elements import ColumnElement


T = TypeVar("T")
_SEPARATOR = "_"


@dataclass(frozen=True, slots=True)
class PageCursor:
    """The position after which the next page starts. ``record_id`` None: timestamp only."""

    created_at: datetime
    record_id: UUID | None = None


def encode_cursor(created_at: datetime, record_id: UUID) -> str:
    moment = _utc(created_at).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return f"{moment}{_SEPARATOR}{record_id.hex}"


def decode_cursor(text: str) -> PageCursor:
    """Raises ValueError for anything that isn't a cursor or an ISO timestamp."""
    moment, separator, identifier = text.strip().partition(_SEPARATOR)
    created_at = _utc(datetime.fromisoformat(moment))
    return PageCursor(created_at, UUID(identifier) if separator else None)


def comes_after(created_at: datetime, record_id: UUID, cursor: PageCursor | None) -> bool:
    """Whether a record belongs to the page that starts after ``cursor`` (newest first)."""
    if cursor is None:
        return True
    created_at = _utc(created_at)
    if cursor.record_id is None:
        return created_at < cursor.created_at
    return (created_at, record_id) < (cursor.created_at, cursor.record_id)


def newest_first(items: Iterable[T], created_at: Callable[[T], datetime], record_id: Callable[[T], UUID]) -> list[T]:
    """The deterministic order every page uses: creation time, then id, both descending."""
    return sorted(items, key=lambda item: (_utc(created_at(item)), record_id(item)), reverse=True)


def after_cursor(created_column, id_column, cursor: PageCursor) -> ColumnElement[bool]:  # type: ignore[no-untyped-def]
    """SQL form of ``comes_after`` for a query ordered by ``created_column DESC, id_column DESC``."""
    if cursor.record_id is None:
        return created_column < cursor.created_at
    return or_(created_column < cursor.created_at, and_(created_column == cursor.created_at, id_column < cursor.record_id))


def next_cursor(page: list[T] | tuple[T, ...], limit: int, created_at: Callable[[T], datetime], record_id: Callable[[T], UUID]) -> str | None:
    """Given ``limit + 1`` fetched rows, the cursor for the next page (None when there is none)."""
    if len(page) <= limit or limit < 1:
        return None
    last = page[limit - 1]
    return encode_cursor(created_at(last), record_id(last))


def _utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
