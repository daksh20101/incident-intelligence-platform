"""Shared building blocks for the API routes.

`SessionDep` is FastAPI *dependency injection*: a route that asks for a
`session: SessionDep` parameter gets a fresh database session, and FastAPI
closes it after the response. Tests swap in a test database by overriding
`get_session`, without changing any route code.
"""

from typing import Annotated

from fastapi import Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from incident_intel.storage.db import get_session

SessionDep = Annotated[Session, Depends(get_session)]

# Pagination parameters: ?limit=50&offset=100 means "50 items, skipping the first 100".
Limit = Annotated[int, Query(ge=1, le=500, description="Items per page (1-500)")]
Offset = Annotated[int, Query(ge=0, description="Items to skip")]


class Page[T](BaseModel):
    """One page of results, plus what a client needs to fetch the next one."""

    items: list[T]
    total: int
    limit: int
    offset: int
