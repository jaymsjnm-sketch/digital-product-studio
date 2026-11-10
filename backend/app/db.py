"""Database layer (SQLAlchemy 2.x).

SQLite by default; set DATABASE_URL=postgresql+psycopg://... to move to PostgreSQL.
All structured blobs use the portable JSON column type.
"""
from __future__ import annotations

import datetime as dt
from contextlib import contextmanager
from typing import Any, Iterator

from sqlalchemy import (JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text,
                        create_engine, event, select)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from .config import settings


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class ResearchRun(Base):
    __tablename__ = "research_runs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")
    sources_used: Mapped[list] = mapped_column(JSON, default=list)
    unavailable_sources: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")
    niches_analyzed: Mapped[int] = mapped_column(Integer, default=0)
    trigger: Mapped[str] = mapped_column(String(20), default="manual")


class Niche(Base):
    __tablename__ = "niches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(80))
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    seasonality: Mapped[str] = mapped_column(String(120), default="evergreen")
    discovered: Mapped[bool] = mapped_column(Boolean, default=False)  # found automatically vs seeded
    parent_slug: Mapped[str | None] = mapped_column(String(120), nullable=True)
    analyst: Mapped[dict] = mapped_column(JSON, default=dict)  # analyst-assessed signals w/ rationale
    insights: Mapped[dict] = mapped_column(JSON, default=dict)  # buyer values, gaps, design trends
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)  # latest computed metrics (API etc.)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    evidence: Mapped[list["Evidence"]] = relationship(back_populates="niche", cascade="all, delete-orphan")


class Evidence(Base):
    __tablename__ = "evidence"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    niche_id: Mapped[int] = mapped_column(ForeignKey("niches.id"))
    kind: Mapped[str] = mapped_column(String(30))  # demand|competition|price|listing|trend|keyword
    claim: Mapped[str] = mapped_column(Text)
    value: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_title: Mapped[str] = mapped_column(String(300), default="")
    url: Mapped[str] = mapped_column(String(600), default="")
    published: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source_type: Mapped[str] = mapped_column(String(30))  # etsy_api|public_web|csv_import|claude_web|user
    retrieved_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    niche: Mapped[Niche] = relationship(back_populates="evidence")


class Opportunity(Base):
    __tablename__ = "opportunities"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    niche_id: Mapped[int] = mapped_column(ForeignKey("niches.id"))
    run_id: Mapped[int | None] = mapped_column(ForeignKey("research_runs.id"), nullable=True)
    key: Mapped[str] = mapped_column(String(200), unique=True)  # niche+product_type (dedupe)
    concept: Mapped[str] = mapped_column(String(300))
    product_type: Mapped[str] = mapped_column(String(50))
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    factor_scores: Mapped[dict] = mapped_column(JSON, default=dict)
    score: Mapped[float] = mapped_column(Float, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(20), default="new")  # new|saved|dismissed|produced
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    niche: Mapped[Niche] = relationship()


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("opportunities.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(200))
    product_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|review|approved|rejected|published
    fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    current_version: Mapped[int] = mapped_column(Integer, default=0)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    review_note: Mapped[str] = mapped_column(Text, default="")
    production_cost: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    versions: Mapped[list["ProductVersion"]] = relationship(back_populates="product", cascade="all, delete-orphan",
                                                            order_by="ProductVersion.version")
    listing: Mapped["Listing | None"] = relationship(back_populates="product", uselist=False,
                                                    cascade="all, delete-orphan")


class ProductVersion(Base):
    __tablename__ = "product_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    version: Mapped[int] = mapped_column(Integer)
    params: Mapped[dict] = mapped_column(JSON, default=dict)
    files: Mapped[dict] = mapped_column(JSON, default=dict)  # {pieces:[...], bundle_zip, deliverables:[...]}
    qc: Mapped[dict] = mapped_column(JSON, default=dict)
    qc_score: Mapped[float] = mapped_column(Float, default=0)
    revision_note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    product: Mapped[Product] = relationship(back_populates="versions")


class Listing(Base):
    __tablename__ = "listings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), unique=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|approved|sent_to_etsy
    etsy_listing_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    product: Mapped[Product] = relationship(back_populates="listing")


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued|running|done|failed
    progress: Mapped[float] = mapped_column(Float, default=0)
    message: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    steps: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Spend(Base):
    __tablename__ = "spend"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(40))
    units: Mapped[float] = mapped_column(Float, default=1)
    cost_usd: Mapped[float] = mapped_column(Float, default=0)
    note: Mapped[str] = mapped_column(String(300), default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=utcnow, index=True)


class CacheEntry(Base):
    __tablename__ = "cache"
    key: Mapped[str] = mapped_column(String(300), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)
    expires_at: Mapped[dt.datetime] = mapped_column(DateTime)


class Setting(Base):
    __tablename__ = "settings"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON)


class SaleRecord(Base):
    """Actual shop performance (imported from Etsy order CSV or synced via API)."""
    __tablename__ = "sales"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[str] = mapped_column(String(60))
    sale_date: Mapped[str] = mapped_column(String(20))
    item_title: Mapped[str] = mapped_column(String(300))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    price: Mapped[float] = mapped_column(Float, default=0)
    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="csv")


_engine = None
_SessionLocal = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        url = settings.database_url
        kwargs: dict = {"future": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
        _engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):
            @event.listens_for(_engine, "connect")
            def _pragma(dbapi_conn, _):  # noqa: ANN001
                cur = dbapi_conn.cursor()
                cur.execute("PRAGMA journal_mode=WAL")
                cur.execute("PRAGMA foreign_keys=ON")
                cur.close()
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


def reset_engine() -> None:
    """Used by tests to point at a fresh database."""
    global _engine, _SessionLocal
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionLocal = None


def init_db() -> None:
    Base.metadata.create_all(get_engine())


@contextmanager
def session_scope() -> Iterator:
    get_engine()
    s = _SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


# ---------- settings helpers ----------
DEFAULT_SETTINGS: dict[str, Any] = {
    "weights": {"demand": 25, "competition": 20, "profitability": 20, "automation": 15, "bundle": 10, "seasonal": 10},
    "budget": {"daily_usd": 2.00, "monthly_usd": 20.00, "image_cost_usd": 0.07, "max_images_per_product": 6},
    "schedule": {"enabled": False, "hour": 7, "minute": 30, "auto_generate_drafts": False, "max_drafts_per_run": 2,
                 "top_n": 5},
    "shop": {"shop_name": "Your Shop", "currency": "USD", "offsite_ads_rate": 0.15, "include_offsite_ads": False},
    "quality": {"min_qc_score": 80, "max_fix_iterations": 3},
}


def get_setting(key: str) -> Any:
    with session_scope() as s:
        row = s.get(Setting, key)
        if row is None:
            return DEFAULT_SETTINGS.get(key)
        value = row.value
        default = DEFAULT_SETTINGS.get(key)
        if isinstance(default, dict) and isinstance(value, dict):
            return {**default, **value}
        return value


def set_setting(key: str, value: Any) -> None:
    with session_scope() as s:
        row = s.get(Setting, key)
        if row is None:
            s.add(Setting(key=key, value=value))
        else:
            row.value = value


__all__ = [n for n in dir() if not n.startswith("_")] + ["select"]
