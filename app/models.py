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
    Index,
    Integer,
    LargeBinary,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


def aware(dt: datetime | None) -> datetime | None:
    """A stored time as UTC-aware (SQLite gives naive datetimes back); None stays None."""
    return dt if dt is None or dt.tzinfo else dt.replace(tzinfo=UTC)


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


class BusinessInput(Base):
    """Commercial inputs for the Business opportunity pages: ASP per function (USD) or annual production
    volume per application (units). Missing values stay missing; nothing is estimated."""

    __tablename__ = "business_inputs"
    __table_args__ = (UniqueConstraint("kind", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))  # asp | volume
    key: Mapped[str] = mapped_column(String(300))  # function id (asp) or application name (volume)
    value: Mapped[float] = mapped_column(Float)
    note: Mapped[str | None] = mapped_column(String(300))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Case(Base):
    """Case analysis: inputs gathered for a possible new product, an analysis brief for an AI market analysis, the
    pasted result and the discussion. Nothing is sent anywhere by the app."""

    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    fn: Mapped[str | None] = mapped_column(String(80))  # function id from the block catalogue
    # collecting | analysing | discussing | decided
    status: Mapped[str] = mapped_column(String(20), default="collecting")
    inputs: Mapped[dict] = mapped_column(JSON, default=dict)
    analysis: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    notes: Mapped[list["CaseNote"]] = relationship(back_populates="case", cascade="all, delete-orphan",
                                                   order_by="CaseNote.created_at")  # fmt: skip


class CaseNote(Base):
    """One point in a case discussion: an upside, a risk, a feature idea or a comment."""

    __tablename__ = "case_notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"))
    kind: Mapped[str] = mapped_column(String(20), default="comment")  # upside | risk | feature | comment
    author: Mapped[str | None] = mapped_column(String(100))
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    case: Mapped[Case] = relationship(back_populates="notes")


class TechFeedback(Base):
    """Feedback on the technology base and technology-fit ratings: a missing technology, a correction or an idea.
    Open items are a to-do for the next data update."""

    __tablename__ = "tech_feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    topic: Mapped[str | None] = mapped_column(String(120))  # platform id, function id or free text
    kind: Mapped[str] = mapped_column(String(20), default="idea")  # missing | correction | idea
    text: Mapped[str] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="open")  # open | done | rejected
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DataReview(Base):
    """A reviewer's check of one business-data item (a competition entry, a technology rating, a path, a customer
    segment, a platform, an evidence entry): correct, wrong or unsure, with an optional comment."""

    __tablename__ = "data_reviews"
    # answers to one item, newest first (review history); created with the table, existing databases work without it
    __table_args__ = (Index("ix_data_reviews_item", "dataset", "key", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    dataset: Mapped[str] = mapped_column(String(40))  # competition | technology | path | patents | foundry | ...
    key: Mapped[str] = mapped_column(String(120))  # function id, segment id or platform id
    verdict: Mapped[str] = mapped_column(String(10))  # correct | wrong | unsure
    comment: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PartMapping(Base):
    """A reviewer's decision whether a catalogue part fills a function it is not mapped to (yes adds it to the
    function's portfolio parts; no hides the suggestion)."""

    __tablename__ = "part_mappings"
    __table_args__ = (UniqueConstraint("fn", "mpn"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    fn: Mapped[str] = mapped_column(String(80))
    mpn: Mapped[str] = mapped_column(String(80))
    manufacturer: Mapped[str] = mapped_column(String(40))
    verdict: Mapped[str] = mapped_column(String(5))  # yes | no
    author: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BusinessAssumption(Base):
    """Where a commercial input comes from: kept next to BusinessInput (same kind and key) so the value table and
    every calculation stay unchanged. All fields are optional; an unknown stays unknown."""

    __tablename__ = "business_assumptions"
    __table_args__ = (UniqueConstraint("kind", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))  # asp | volume
    key: Mapped[str] = mapped_column(String(300))
    source: Mapped[str | None] = mapped_column(String(300))
    year: Mapped[int | None] = mapped_column(Integer)
    geography: Mapped[str | None] = mapped_column(String(60))
    currency: Mapped[str | None] = mapped_column(String(10))
    scenario: Mapped[str | None] = mapped_column(String(20))  # base | low | high
    confidence: Mapped[str | None] = mapped_column(String(10))  # high | medium | low
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class OpportunityDecision(Base):
    """A person's call on a missing function in the Opportunity explorer: keep it under consideration, or set it
    aside for now (kept in a separate list, with a note, and can be restored). The fit score itself is unchanged."""

    __tablename__ = "opportunity_decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    fn: Mapped[str] = mapped_column(String(80), unique=True)
    status: Mapped[str] = mapped_column(String(12))  # keep | set_aside
    note: Mapped[str | None] = mapped_column(String(500))
    author: Mapped[str | None] = mapped_column(String(100))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ShortlistItem(Base):
    """A business-case candidate: pushed from the portfolio pages (explorer, cross-sell, markets, customers) or from
    New ideas. "Start analysing" opens a business case from it and links the two."""

    __tablename__ = "shortlist_items"
    __table_args__ = (UniqueConstraint("origin", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    origin: Mapped[str] = mapped_column(String(20))  # explorer | crosssell | markets | customers | idea
    key: Mapped[str] = mapped_column(String(200))  # function id, market / customer id, or the idea text
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str | None] = mapped_column(Text)
    fn: Mapped[str | None] = mapped_column(String(80))
    note: Mapped[str | None] = mapped_column(Text)
    case_id: Mapped[int | None] = mapped_column(ForeignKey("cases.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CaseLine(Base):
    """One part in a business case: a competitor part and our part for one function (a cross, a part of ours found
    in the same design, or a gap), with the volume and target price assumed for it. A case can hold many lines."""

    __tablename__ = "case_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"))
    role: Mapped[str] = mapped_column(String(10))  # cross | design | gap
    fn: Mapped[str | None] = mapped_column(String(80))
    label: Mapped[str] = mapped_column(String(200))
    competitor_mpn: Mapped[str | None] = mapped_column(String(80))
    our_mpn: Mapped[str | None] = mapped_column(String(80))
    qty: Mapped[int] = mapped_column(Integer, default=1)  # per system
    volume: Mapped[int | None] = mapped_column(Integer)  # systems per year (assumed)
    price: Mapped[float | None] = mapped_column(Float)  # target price per part, USD (assumed)
    price_source: Mapped[str | None] = mapped_column(String(200))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PipelineDraft(Base):
    """The guided path from a part to a business case, saved after every step so it can be resumed: the part and its
    cross, the block diagram, the parts in the design, the numbers, then the case it created or joined."""

    __tablename__ = "pipeline_drafts"

    id: Mapped[int] = mapped_column(primary_key=True)
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    case_id: Mapped[int | None] = mapped_column(ForeignKey("cases.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class SiteFeedback(Base):
    """Feedback from the floating button on every page: what the person wrote and where they were. Similar items
    are grouped in the daily digest (Data management > Site feedback); a response is written once per group and
    shown to the people who sent it."""

    __tablename__ = "site_feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(20), default="idea")  # problem | idea | data | question
    path: Mapped[str] = mapped_column(String(500))  # page path with query string
    page: Mapped[str | None] = mapped_column(String(300))  # section › page › heading, as shown in the panel
    selection: Mapped[str | None] = mapped_column(Text)  # text selected on the page, when included
    author: Mapped[str | None] = mapped_column(String(100))
    client: Mapped[str | None] = mapped_column(String(40), index=True)  # random id kept in the browser
    status: Mapped[str] = mapped_column(String(20), default="new")  # new | planned | done | wont | duplicate
    response: Mapped[str | None] = mapped_column(Text)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ReportQuestion(Base):
    """A question asked on a pre-lim report page. Questions are reviewed once a day (Opportunities > Pre-lim ideas &
    reports > Questions): kept as good, marked as a duplicate of an earlier one, or set aside; the answer is shown
    under the report."""

    __tablename__ = "report_questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(100), index=True)  # report it was asked on
    text: Mapped[str] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="new")  # new | good | duplicate | dropped
    duplicate_of: Mapped[int | None] = mapped_column(Integer)
    answer: Mapped[str | None] = mapped_column(Text)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Upload(Base):
    """A picture, block diagram, document or written explanation added on Data management > Uploads, kept for use in
    the library and the knowledge pages. The file itself is stored under the data directory (uploads/)."""

    __tablename__ = "uploads"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(20), default="picture")  # picture | block_diagram | document | explanation
    explanation: Mapped[str | None] = mapped_column(Text)
    topic: Mapped[str | None] = mapped_column(String(200))  # application, function, part number or page it is about
    source: Mapped[str | None] = mapped_column(String(500))  # where it comes from (URL or reference), if public
    file_name: Mapped[str | None] = mapped_column(String(200))  # stored name under uploads/
    original_name: Mapped[str | None] = mapped_column(String(200))
    content_type: Mapped[str | None] = mapped_column(String(60))
    size: Mapped[int | None] = mapped_column(Integer)
    author: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), default="new")  # new | used | archived
    note: Mapped[str | None] = mapped_column(Text)  # what was done with it
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class VerifyTask(Base):
    """One item of the owner's verification batch (Data management > Verify next): a cross checked against its two
    datasheets, a library block diagram, or a data item behind the scores. Each is picked to stand for many others
    (parts on the same datasheets, diagrams of the same kind); a kind gets its next batch only when its open tasks
    are done."""

    __tablename__ = "verify_tasks"
    __table_args__ = (UniqueConstraint("kind", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(10))  # cross | diagram | data
    key: Mapped[str] = mapped_column(String(600))  # what it stands for, e.g. the two datasheet URLs of a cross
    title: Mapped[str] = mapped_column(String(300))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)  # links and the reason it was picked
    covers: Mapped[int] = mapped_column(Integer, default=1)  # how many items it stands for
    status: Mapped[str] = mapped_column(String(10), default="open")  # open | ok | wrong
    note: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(100))
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TamEstimate(Base):
    """A market size (TAM) estimate for a product or technology added on Data management > TAM estimates, next to the
    researched examples in data/business/tam.yaml. Each carries its source; the owner's agree / disagree is a
    DataReview (dataset "tam", key "u<id>")."""

    __tablename__ = "tam_estimates"

    id: Mapped[int] = mapped_column(primary_key=True)
    product: Mapped[str] = mapped_column(String(200))
    fn: Mapped[str | None] = mapped_column(String(80))
    value: Mapped[str] = mapped_column(String(100))  # as the source states it, e.g. "$1.4 B"
    usd: Mapped[float | None] = mapped_column(Float)
    year: Mapped[int | None] = mapped_column(Integer)
    region: Mapped[str | None] = mapped_column(String(100))
    scope: Mapped[str | None] = mapped_column(String(500))
    source_title: Mapped[str | None] = mapped_column(String(300))
    source_publisher: Mapped[str | None] = mapped_column(String(200))
    source_url: Mapped[str | None] = mapped_column(String(500))
    source_date: Mapped[str | None] = mapped_column(String(40))
    quality: Mapped[str | None] = mapped_column(Text)  # source-quality note
    author: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FeedbackAttachment(Base):
    """A file sent with the Feedback button: the Upload that stores it (same limits and storage as Data management >
    Uploads), linked to the feedback item."""

    __tablename__ = "feedback_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    feedback_id: Mapped[int] = mapped_column(ForeignKey("site_feedback.id", ondelete="CASCADE"), index=True)
    upload_id: Mapped[int] = mapped_column(ForeignKey("uploads.id", ondelete="CASCADE"))


class VolumeRequest(Base):
    """One request for a case on a part (Products › part › prelim case): the volume asked for, by whom and where.
    Rows are never merged, so the total volume asked for a part accrues over every request."""

    __tablename__ = "volume_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    mpn: Mapped[str] = mapped_column(String(100), index=True)
    volume: Mapped[int | None] = mapped_column(Integer)  # pieces of this part per year, as asked
    customer: Mapped[str | None] = mapped_column(String(500))  # one or more customers, "; " between them
    market: Mapped[str | None] = mapped_column(String(500))  # one or more markets, "; " between them
    source: Mapped[str] = mapped_column(String(60), default="pipeline")  # e.g. prelim:<draft id>
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class ScheduledReview(Base):
    """A topic scheduled for a business case review (Future growth > Business cases): pushed from Research & ideas
    (source "research:<report slug>"), from a preliminary case in the Products walk-through ("prelim:<draft id>") or
    from the shortlist. Business cases start from this list; the case it started is linked."""

    __tablename__ = "scheduled_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    source: Mapped[str | None] = mapped_column(String(120), index=True)  # free text, e.g. research:<slug>
    note: Mapped[str | None] = mapped_column(Text)
    part: Mapped[str | None] = mapped_column(String(100))  # part number the topic is about, if any
    volume: Mapped[str | None] = mapped_column(String(60))  # as given, e.g. "200000" or "200 k a year"
    status: Mapped[str] = mapped_column(String(12), default="scheduled")  # scheduled | started | done
    case_id: Mapped[int | None] = mapped_column(ForeignKey("cases.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class TechReviewRequest(Base):
    """A request for a technology review of an existing part (Systems & applications > Technology reviews): what the
    person wants to understand about it. The daily update run writes the review as data/reviews/<slug>.yaml and links
    it here (review_slug); a review that covers the part also answers the request."""

    __tablename__ = "tech_review_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    mpn: Mapped[str] = mapped_column(String(100), index=True)
    question: Mapped[str] = mapped_column(Text)
    application: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(12), default="new")  # new | in_progress | done | dropped
    review_slug: Mapped[str | None] = mapped_column(String(60))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AreaRequest(Base):
    """A request for another application area in the Application library (owner, 22 Oct 2026: the library focuses on
    automotive, data centers, drones and cellular; other areas are asked for here). Reviewed in Data management >
    Requests & reviews and listed in the daily inbox."""

    __tablename__ = "area_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    area: Mapped[str] = mapped_column(String(200))
    why: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(12), default="new")  # new | planned | done | declined
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)



class IdeaRequest(Base):
    """"Expand this idea" on Research & ideas (owner, 25 Oct 2026): the owner asks for a deeper look at a report's
    applications before a business case. One request per report (slug is unique, so the button never comes back);
    the daily run writes the "Applications in depth" section and sets the status to done."""

    __tablename__ = "idea_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    title: Mapped[str] = mapped_column(String(300))
    note: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), default="new")  # new | done | declined
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

# --- Sign-in with passkeys and invited guests (owner, 23 Oct 2026) ---------------------------------------------------
# The older `User` table above stays as it is (it carries no role); the people who can sign in are `Account` rows.


class Account(Base):
    """A person who can sign in: the owner (password or passkey) or an invited guest (passkey only). Bumping
    session_version signs the person out everywhere at once."""

    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(String(10), default="guest")  # owner | guest
    disabled: Mapped[bool] = mapped_column(Boolean, default=False)
    session_version: Mapped[int] = mapped_column(Integer, default=1)
    handle: Mapped[str] = mapped_column(String(64), unique=True)  # random WebAuthn user handle (base64url)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    passkeys: Mapped[list["PasskeyCredential"]] = relationship(
        back_populates="account", cascade="all, delete-orphan", order_by="PasskeyCredential.created_at"
    )


class PasskeyCredential(Base):
    __tablename__ = "passkey_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"), index=True)
    credential_id: Mapped[str] = mapped_column(String(1400), unique=True)  # base64url
    public_key: Mapped[bytes] = mapped_column(LargeBinary)
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    transports: Mapped[list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    account: Mapped[Account] = relationship(back_populates="passkeys")


class Invite(Base):
    """A one-time invite link. Only the SHA-256 of the token is stored; the link itself is shown once."""

    __tablename__ = "invites"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"))


class WebauthnChallenge(Base):
    """A passkey challenge: random, single use, valid 5 minutes, bound to the browser by a cookie holding a nonce
    (only its SHA-256 is stored)."""

    __tablename__ = "webauthn_challenges"

    id: Mapped[int] = mapped_column(primary_key=True)
    nonce_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    challenge: Mapped[bytes] = mapped_column(LargeBinary)
    purpose: Mapped[str] = mapped_column(String(20))  # login | invite | owner | confirm
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    invite_id: Mapped[int | None] = mapped_column(ForeignKey("invites.id", ondelete="CASCADE"))
    handle: Mapped[str | None] = mapped_column(String(64))  # user handle offered to a new guest's passkey
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class ExternalSubmission(Base):
    """Something a guest sent (comment, vote, request, saved design...). It changes nothing until the owner approves
    it; approval replays the stored request through the same route the owner uses, with the guest's name as author."""

    __tablename__ = "external_submissions"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id", ondelete="SET NULL"), index=True)
    author: Mapped[str] = mapped_column(String(100))  # the guest's name when it was sent
    kind: Mapped[str] = mapped_column(String(60))  # plain-English label of the input, e.g. "Site feedback"
    method: Mapped[str] = mapped_column(String(10), default="POST")
    target: Mapped[str] = mapped_column(String(500))  # the route the input was sent to
    payload: Mapped[dict] = mapped_column(JSON)  # content type, query and body as sent
    page: Mapped[str | None] = mapped_column(String(500))  # the page the guest was on
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)  # pending | approved | rejected
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    owner_note: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict | None] = mapped_column(JSON)  # what the replay answered (status, id of what was created)


class PowSpent(Base):
    """A proof-of-work challenge already used on the sign-in or invite page (each works once)."""

    __tablename__ = "pow_spent"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class SiteSetting(Base):
    """An owner setting changed on the site (for example whether password sign-in is allowed)."""

    __tablename__ = "site_settings"

    key: Mapped[str] = mapped_column(String(60), primary_key=True)
    value: Mapped[str] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PageTextVersion(Base):
    """One save of the owner's edits to a shareable page (Shareable > Technology overview, 24 Oct 2026): the full set
    of overrides over the page's defaults (data/business/tech_overview.yaml and the catalogue numbers). The newest
    version not undone is the page; older ones are the history. Never reset by a run (docs/daily_update.md)."""

    __tablename__ = "page_text_versions"

    id: Mapped[int] = mapped_column(primary_key=True)
    page: Mapped[str] = mapped_column(String(60), index=True)
    fields: Mapped[dict] = mapped_column(JSON)  # field id -> value (text, list of chips, or list of paragraphs)
    auto: Mapped[dict] = mapped_column(JSON)  # automatic value of each overridden number when it was saved
    note: Mapped[str] = mapped_column(String(500), default="")  # what changed, in words
    author: Mapped[str] = mapped_column(String(100), default="Owner")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PageComment(Base):
    """The owner's instruction on one paragraph or text of a shareable page ("make this shorter"); the daily run
    answers it in data/business/tech_overview_answers.yaml and the site applies the answer and marks it done."""

    __tablename__ = "page_comments"

    id: Mapped[int] = mapped_column(primary_key=True)
    page: Mapped[str] = mapped_column(String(60), index=True)
    block: Mapped[str] = mapped_column(String(160))  # field id, or para.<paragraph id>
    text: Mapped[str] = mapped_column(Text)
    block_text: Mapped[str] = mapped_column(Text, default="")  # the text it was about, when it was written
    author: Mapped[str] = mapped_column(String(100), default="Owner")
    status: Mapped[str] = mapped_column(String(10), default="open", index=True)  # open | done
    reply: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
