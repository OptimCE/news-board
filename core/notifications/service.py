import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from core.notifications.repository import NotificationRepository
from shared.models.crm_models import NotificationModel

logger = logging.getLogger(__name__)


class NotificationTypes:
    """Notification ``type`` keys this service publishes.

    ``<feature>.<event>`` strings, matching crm-backend's free-form taxonomy.
    The frontend localises the displayed text from the key
    (``NOTIFICATIONS.TYPES.<type>.title``); the backend stores only key + data.
    """

    NEWS_POST_PUBLISHED = "news_post.published"
    NEWS_POLL_PUBLISHED = "news_poll.published"


class NotificationService:
    """Publish durable notifications into the shared CRM ``notification`` table.

    Mirrors ``AuditLogService``: the write rides on the caller's CRM session
    inside a SAVEPOINT and never raises — a notification failure must not abort
    the business write that triggered it. The caller owns the commit.
    """

    def __init__(self, crm_session: AsyncSession):
        self.crm_session = crm_session
        self.repository = NotificationRepository(crm_session)

    async def publish(
        self,
        *,
        type: str,
        data: dict[str, Any] | None,
        community_id: int,
        exclude_author_auth_id: str | None = None,
    ) -> int:
        """Fan a notification out to every member of ``community_id``.

        One row per recipient. ``exclude_author_auth_id`` (a Keycloak ``sub``) is
        resolved to its internal id and dropped from the audience so the author
        never notifies themselves. Returns the number of rows staged (0 when the
        community has no other members, or on any swallowed failure).
        """
        try:
            exclude_user_id = (
                await self.repository.resolve_internal_user_id(exclude_author_auth_id)
                if exclude_author_auth_id
                else None
            )
            recipient_ids = await self.repository.find_community_recipient_ids(
                community_id, exclude_user_id=exclude_user_id
            )
            if not recipient_ids:
                return 0
            rows = [
                NotificationModel(
                    id_community=community_id,
                    id_user=user_id,
                    type=type,
                    data=data or {},
                )
                for user_id in recipient_ids
            ]
            # Stage inside a SAVEPOINT so a failure (FK violation, transient
            # error) rolls back only this nested write and leaves the caller's
            # CRM transaction clean and committable.
            async with self.crm_session.begin_nested():
                await self.repository.insert_many(rows)
            return len(rows)
        except Exception:
            logger.exception(
                "notification.publish failed",
                extra={"operation": "notification:publish", "type": type},
            )
            return 0
