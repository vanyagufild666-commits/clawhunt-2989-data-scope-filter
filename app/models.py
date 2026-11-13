"""Test models: org/site/user reference + probe_records (test-only table per spec)."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow():
    # naive UTC (SQLite-compatible)
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_uuid():
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Org(Base):
    __tablename__ = "orgs"
    __scope_exempt__ = True  # reference table, not a scoped business object
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))


class Site(Base):
    __tablename__ = "sites"
    __scope_exempt__ = True
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(128))


class User(Base):
    __tablename__ = "users"
    __scope_exempt__ = True
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(128))


class ProbeRecord(Base):
    """probe_records — test-only table per task spec (id, org_id, site_id, owner_id, title)."""
    __tablename__ = "probe_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    org_id: Mapped[str] = mapped_column(String(36), index=True)
    site_id: Mapped[str] = mapped_column(String(36), index=True)
    owner_id: Mapped[str] = mapped_column(String(36), index=True)
    title: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(), server_default=func.now())
