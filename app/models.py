"""ORM models.

Users and organizations exist from day one so that multi-user support and passkey
authentication can be added without reshaping the data.
"""

import enum
from datetime import UTC, date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(200))
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ManufacturerRole(enum.StrEnum):
    reference = "reference"  # the parts being crossed (Skyworks)
    competitor = "competitor"


class Manufacturer(Base):
    __tablename__ = "manufacturers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    role: Mapped[ManufacturerRole] = mapped_column(Enum(ManufacturerRole))
    website: Mapped[str | None] = mapped_column(String(300))
    parts: Mapped[list["Part"]] = relationship(back_populates="manufacturer")


class Package(Base):
    """Physical package. Two parts share a footprint only if all dimensions match."""

    __tablename__ = "packages"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)  # e.g. SOIC-16W
    name: Mapped[str] = mapped_column(String(200))
    pin_count: Mapped[int] = mapped_column(Integer)
    pitch_mm: Mapped[float] = mapped_column(Float)
    body_length_mm: Mapped[float] = mapped_column(Float)
    body_width_mm: Mapped[float] = mapped_column(Float)
    span_mm: Mapped[float] = mapped_column(Float)  # lead tip to lead tip
    height_mm: Mapped[float | None] = mapped_column(Float)
    exposed_pad: Mapped[bool] = mapped_column(Boolean, default=False)
    # Packages that leave pin positions empty: total positions and the position
    # of each numbered pin (e.g. a 16-position body with 12 pins).
    positions_total: Mapped[int | None] = mapped_column(Integer)
    pin_positions: Mapped[list[int] | None] = mapped_column(JSON)

    @property
    def footprint_mm2(self) -> float:
        return round(self.body_length_mm * self.span_mm, 2)


class LifecycleStatus(enum.StrEnum):
    preview = "preview"  # pre-production / sampling
    active = "active"
    nrnd = "nrnd"  # not recommended for new designs
    last_time_buy = "last_time_buy"
    obsolete = "obsolete"
    unknown = "unknown"


part_datasheets = Table(
    "part_datasheets",
    Base.metadata,
    Column("part_id", ForeignKey("parts.id", ondelete="CASCADE"), primary_key=True),
    Column("datasheet_id", ForeignKey("datasheets.id", ondelete="CASCADE"), primary_key=True),
)


class Part(Base):
    __tablename__ = "parts"
    __table_args__ = (UniqueConstraint("manufacturer_id", "mpn"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    mpn: Mapped[str] = mapped_column(String(100), index=True)
    manufacturer_id: Mapped[int] = mapped_column(ForeignKey("manufacturers.id"))
    family: Mapped[str] = mapped_column(String(50), index=True)  # matches rules/<family>.yaml
    description: Mapped[str] = mapped_column(Text, default="")
    package_id: Mapped[int] = mapped_column(ForeignKey("packages.id"))
    pinout: Mapped[list[str]] = mapped_column(JSON)  # function of pin 1..N
    # Package lock: only same-package parts may be offered as upgrades
    # (e.g. thermal or creepage requirements that need this exact package).
    package_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    package_lock_reason: Mapped[str | None] = mapped_column(String(300))

    lifecycle_status: Mapped[LifecycleStatus] = mapped_column(Enum(LifecycleStatus), default=LifecycleStatus.unknown)
    release_date: Mapped[date | None] = mapped_column(Date)
    datasheet_revision: Mapped[str | None] = mapped_column(String(50))
    datasheet_date: Mapped[date | None] = mapped_column(Date)
    lifecycle_source: Mapped[str | None] = mapped_column(String(300))
    lifecycle_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    datasheet_url: Mapped[str | None] = mapped_column(String(500))
    product_url: Mapped[str | None] = mapped_column(String(500))
    notes: Mapped[str | None] = mapped_column(Text)  # e.g. "pinout inferred: …"
    pinout_source: Mapped[str | None] = mapped_column(String(300))

    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    manufacturer: Mapped[Manufacturer] = relationship(back_populates="parts", lazy="joined")
    package: Mapped[Package] = relationship(lazy="joined")
    params: Mapped[list["ParamValue"]] = relationship(
        back_populates="part", cascade="all, delete-orphan", lazy="selectin"
    )
    datasheets: Mapped[list["Datasheet"]] = relationship(secondary=part_datasheets)

    @property
    def is_reference(self) -> bool:
        return self.manufacturer.role == ManufacturerRole.reference

    @property
    def label(self) -> str:
        return f"{self.manufacturer.name} {self.mpn}"

    def param_map(self) -> dict[str, object]:
        return {p.key: p.value for p in self.params}


class ParamValue(Base):
    """One parameter of one part. ``value`` holds the raw value (number, [min, max],
    string or list); ``num`` mirrors numeric values for SQL filtering."""

    __tablename__ = "param_values"
    __table_args__ = (UniqueConstraint("part_id", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(String(80), index=True)
    value: Mapped[object] = mapped_column(JSON)
    num: Mapped[float | None] = mapped_column(Float, index=True)
    conditions: Mapped[str | None] = mapped_column(String(300))
    source: Mapped[str | None] = mapped_column(String(300))  # e.g. "si864x-datasheet.pdf p.25"
    datasheet_id: Mapped[int | None] = mapped_column(ForeignKey("datasheets.id"))
    source_page: Mapped[int | None] = mapped_column(Integer)

    part: Mapped[Part] = relationship(back_populates="params")


class Datasheet(Base):
    __tablename__ = "datasheets"
    id: Mapped[int] = mapped_column(primary_key=True)
    sha256: Mapped[str] = mapped_column(String(64), unique=True)
    filename: Mapped[str] = mapped_column(String(300))
    source_url: Mapped[str | None] = mapped_column(String(500))
    revision: Mapped[str | None] = mapped_column(String(50))
    revision_date: Mapped[date | None] = mapped_column(Date)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))


class ChangeEvent(Base):
    """History of lifecycle / datasheet revision changes found by the refresh job."""

    __tablename__ = "change_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(50))  # lifecycle | revision | release
    old_value: Mapped[str | None] = mapped_column(String(200))
    new_value: Mapped[str | None] = mapped_column(String(200))
    source: Mapped[str | None] = mapped_column(String(300))
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    part: Mapped[Part] = relationship(lazy="joined")


class FeedbackVerdict(enum.StrEnum):
    accept = "accept"
    reject = "reject"


class CrossFeedback(Base):
    """An engineer's decision on whether a cross that needs review is FFF."""

    __tablename__ = "cross_feedback"
    __table_args__ = (UniqueConstraint("reference_id", "candidate_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    reference_id: Mapped[int] = mapped_column(ForeignKey("parts.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("parts.id", ondelete="CASCADE"))
    verdict: Mapped[FeedbackVerdict] = mapped_column(Enum(FeedbackVerdict))
    note: Mapped[str] = mapped_column(Text, default="")
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    user: Mapped["User"] = relationship(lazy="joined")


class PriceQuote(Base):
    """Distributor price and stock for a part, cached so pages stay fast and API quotas last."""

    __tablename__ = "price_quotes"
    __table_args__ = (UniqueConstraint("part_id", "source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(String(30))  # e.g. digikey
    found: Mapped[bool] = mapped_column(Boolean, default=False)
    distributor_pn: Mapped[str | None] = mapped_column(String(100))
    product_url: Mapped[str | None] = mapped_column(String(500))
    stock: Mapped[int | None] = mapped_column(Integer)
    status: Mapped[str | None] = mapped_column(String(50))  # distributor's product status, e.g. Active
    lead_weeks: Mapped[str | None] = mapped_column(String(20))
    currency: Mapped[str] = mapped_column(String(3), default="USD")
    # [{"package": "Cut Tape (CT)", "min_qty": 1, "breaks": [[1, 3.21], [10, 2.9], ...]}, ...]
    offers: Mapped[list] = mapped_column(JSON, default=list)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BroadcastConfig(Base):
    """A saved broadcast block diagram: devices, add-on blocks and connections (see broadcast.js)."""

    __tablename__ = "broadcast_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class CrossRequest(Base):
    """A part someone wants crossed that the database does not cover yet."""

    __tablename__ = "cross_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    mpn: Mapped[str] = mapped_column(String(100), index=True)
    manufacturer: Mapped[str | None] = mapped_column(String(100))
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | in_progress | done | cannot
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class BlockDiagram(Base):
    """A saved system block diagram from the block-diagram generator (see blocks.js)."""

    __tablename__ = "block_diagrams"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class BlockFeedback(Base):
    """Feedback on a block diagram, a block or a template, kept for discussion before anything is changed."""

    __tablename__ = "block_feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    diagram_id: Mapped[int | None] = mapped_column(Integer, index=True)
    diagram_name: Mapped[str | None] = mapped_column(String(200))
    target: Mapped[str | None] = mapped_column(String(200))  # e.g. "Gate drive / Isolated gate driver"
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | agreed | rejected | done
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
