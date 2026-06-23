import datetime
from typing import Any

from sqlalchemy import TIMESTAMP, BigInteger, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from core.database.database import CrmBase


class AppUserModel(CrmBase):
    """Partial mapping of the CRM ``app_user`` table.

    Only the columns the News service needs to resolve a logical user reference
    (Keycloak ``sub`` → internal id + email): the audit log denormalises the
    writer's identity onto each row, and poll results denormalise author/voter
    emails for display under "full" visibility.
    """

    __tablename__ = "app_user"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    auth_user_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String(256), nullable=False)


class CommunityUserModel(CrmBase):
    """Partial mapping of the CRM ``community_user`` join table.

    The membership roster of a community (one row per user, with their role).
    The News service reads it to fan a "published" notification out to every
    member of a community. Owned by ``crm-backend``; read-only here.
    """

    __tablename__ = "community_user"
    id_community: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_user: Mapped[int] = mapped_column(Integer, primary_key=True)
    role: Mapped[str] = mapped_column(String(50), nullable=False)


class NotificationModel(CrmBase):
    """Mapping of the shared CRM ``notification`` table.

    A durable, per-recipient notification row (one row per user). The table is
    owned by ``crm-backend`` — which serves the read API the frontend polls —
    so the News service only ever *inserts* here when a post or poll is
    published; ``read_at``/``created_at`` and the bigint ``id`` are managed by
    the DB. Mirrors ``AuditLogModel`` conventions in ``core/database/models.py``.
    """

    __tablename__ = "notification"
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_community: Mapped[int | None] = mapped_column(Integer, nullable=True)
    id_user: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(128), nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    read_at: Mapped[datetime.datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
