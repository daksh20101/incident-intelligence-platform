"""Database tables, described as Python classes (SQLAlchemy 2.0 ORM).

Each class is one table; each `Mapped[...]` attribute is one column. These are
*storage* classes: the rest of the platform keeps using the Pydantic domain
models, and `repository.py` converts between the two. Keeping them separate
means the database layout can change without touching the business logic.
"""

from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, Float, Index, String, Text, TypeDecorator
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class UTCDateTime(TypeDecorator[datetime]):
    """Store timestamps in UTC and always hand them back timezone-aware.

    SQLite has no timezone type: it silently drops `+00:00`, so a time read back
    would be "naive" and Pydantic's AwareDatetime would reject it. This column
    type converts to UTC on the way in and re-attaches UTC on the way out.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Refusing to store a timestamp without a timezone")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return None if value is None else value.replace(tzinfo=UTC)


class Base(DeclarativeBase):
    """Parent of every table class; `Base.metadata` knows all tables."""


class ServiceRow(Base):
    __tablename__ = "services"

    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    tier: Mapped[str] = mapped_column(String(20))
    team: Mapped[str] = mapped_column(String(50))
    criticality: Mapped[str] = mapped_column(String(10))
    depends_on: Mapped[list[str]] = mapped_column(JSON, default=list)


class DeploymentRow(Base):
    __tablename__ = "deployments"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    service: Mapped[str] = mapped_column(String(100), index=True)
    version: Mapped[str] = mapped_column(String(50))
    deployed_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    author: Mapped[str] = mapped_column(String(200))
    change_summary: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20))
    rolled_back_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class IncidentRow(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    opened_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    service: Mapped[str] = mapped_column(String(100), index=True)
    title: Mapped[str] = mapped_column(String(300))
    description: Mapped[str] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(2), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    alert_metric: Mapped[str | None] = mapped_column(String(30))
    observed_value: Mapped[float | None] = mapped_column(Float)
    threshold: Mapped[float | None] = mapped_column(Float)


class TicketRow(Base):
    __tablename__ = "tickets"

    id: Mapped[str] = mapped_column(String(50), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, index=True)
    reporter: Mapped[str] = mapped_column(String(200))
    channel: Mapped[str] = mapped_column(String(20))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(30), index=True)
    priority: Mapped[str] = mapped_column(String(2), index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class LogRow(Base):
    __tablename__ = "logs"
    # Queries look like "ERROR logs of order-service between 14:00 and 15:00",
    # so one index covering (service, timestamp) makes them fast.
    __table_args__ = (Index("ix_logs_service_time", "service", "timestamp"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime)
    service: Mapped[str] = mapped_column(String(100))
    level: Mapped[str] = mapped_column(String(10), index=True)
    message: Mapped[str] = mapped_column(Text)
    trace_id: Mapped[str | None] = mapped_column(String(32))


class MetricRow(Base):
    __tablename__ = "metrics"
    __table_args__ = (Index("ix_metrics_series_time", "service", "metric", "timestamp"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime)
    service: Mapped[str] = mapped_column(String(100))
    metric: Mapped[str] = mapped_column(String(30))
    value: Mapped[float] = mapped_column(Float)
