import datetime

from sqlalchemy import (
    TIMESTAMP,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database.database import LocalBase
from shared.const import PostType


class PostModel(LocalBase):
    """A board entry: a Markdown post or a poll (single/multiple choice).

    ``post`` stores the Markdown **source** (the source of truth); HTML is
    rendered and sanitised on read. ``author_id`` is a logical reference to a
    core user (the Keycloak ``sub`` forwarded as ``x-user-id``) — not an FK, the
    user lives in the separate CRM DB; ``author_email`` is snapshotted at
    creation so the board can show the author without a cross-DB join. Poll-only
    columns (``expires_at`` and the visibility matrix) are null for plain posts.
    """

    __tablename__ = "post"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_community: Mapped[int] = mapped_column(Integer, nullable=False)

    author_id: Mapped[str] = mapped_column(String(255), nullable=False)
    author_email: Mapped[str | None] = mapped_column(String(256), nullable=True)

    type: Mapped[PostType] = mapped_column(SmallInteger, nullable=False, default=PostType.POST)
    post: Mapped[str] = mapped_column(Text, nullable=False)

    # Poll vote deadline; null for plain posts. After this instant voting and
    # vote editing are locked (enforced in the service layer).
    expires_at: Mapped[datetime.datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    # Poll visibility matrix (null for plain posts). Stored as smallints and
    # interpreted via AdminVisibility / MemberVisibility / MemberDisplay.
    admin_visibility: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    member_visibility: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    member_display: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)

    options: Mapped[list["PostPollModel"]] = relationship(
        "PostPollModel",
        lazy="select",
        back_populates="post_ref",
        cascade="all, delete-orphan",
        order_by="PostPollModel.display_order",
        passive_deletes=True,
    )
    votes: Mapped[list["PostPollVoteModel"]] = relationship(
        "PostPollVoteModel",
        lazy="select",
        back_populates="post_ref",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.UTC),
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.UTC),
        onupdate=lambda: datetime.datetime.now(datetime.UTC),
    )


class PostPollModel(LocalBase):
    """One selectable option of a poll. Frozen once the first vote exists."""

    __tablename__ = "post_poll"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_community: Mapped[int] = mapped_column(Integer, nullable=False)
    id_post: Mapped[int] = mapped_column(
        Integer, ForeignKey("post.id", ondelete="CASCADE"), nullable=False
    )
    option_value: Mapped[str] = mapped_column(Text, nullable=False)
    display_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)

    post_ref: Mapped["PostModel"] = relationship(
        "PostModel", lazy="select", back_populates="options"
    )

    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.UTC),
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.UTC),
        onupdate=lambda: datetime.datetime.now(datetime.UTC),
    )


class PostPollVoteModel(LocalBase):
    """A single member's vote for one poll option.

    ``voter_id`` is a logical reference to a core user (the Keycloak ``sub``).
    ``id_post`` is carried alongside ``id_post_poll`` so tally/edit queries scope
    by poll without joining. ``UNIQUE (id_post_poll, voter_id)`` guards against a
    double-click casting the same option twice; the "one option per single-choice
    poll" rule is enforced transactionally in the service layer.
    """

    __tablename__ = "post_poll_vote"
    __table_args__ = (
        UniqueConstraint("id_post_poll", "voter_id", name="uq_post_poll_vote_option_voter"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    id_community: Mapped[int] = mapped_column(Integer, nullable=False)
    id_post: Mapped[int] = mapped_column(
        Integer, ForeignKey("post.id", ondelete="CASCADE"), nullable=False
    )
    id_post_poll: Mapped[int] = mapped_column(
        Integer, ForeignKey("post_poll.id", ondelete="CASCADE"), nullable=False
    )
    voter_id: Mapped[str] = mapped_column(String(255), nullable=False)

    post_ref: Mapped["PostModel"] = relationship("PostModel", lazy="select", back_populates="votes")

    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.UTC),
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=lambda: datetime.datetime.now(datetime.UTC),
        onupdate=lambda: datetime.datetime.now(datetime.UTC),
    )
