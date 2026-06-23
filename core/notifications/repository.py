from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.crm_models import AppUserModel, CommunityUserModel, NotificationModel


class NotificationRepository:
    """Read community membership / write notifications against the CRM database.

    All three tables (``app_user``, ``community_user``, ``notification``) are
    owned by ``crm-backend``; the News service reads the first two and inserts
    into the last when a post or poll is published.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def resolve_internal_user_id(self, auth_user_id: str) -> int | None:
        """Map a Keycloak ``sub`` to its internal ``app_user.id`` (``None`` if absent)."""
        stmt = select(AppUserModel.id).where(AppUserModel.auth_user_id == auth_user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_community_recipient_ids(
        self,
        community_id: int,
        *,
        exclude_user_id: int | None = None,
        roles: Sequence[str] | None = None,
    ) -> list[int]:
        """Return the internal ids of a community's members.

        ``exclude_user_id`` drops one member (typically the author) from the
        fan-out; ``roles`` optionally narrows to specific roles (unused today,
        kept to mirror crm-backend's ``findCommunityRecipientIds``).
        """
        stmt = select(CommunityUserModel.id_user).where(
            CommunityUserModel.id_community == community_id
        )
        if exclude_user_id is not None:
            stmt = stmt.where(CommunityUserModel.id_user != exclude_user_id)
        if roles:
            stmt = stmt.where(CommunityUserModel.role.in_(roles))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def insert_many(self, rows: list[NotificationModel]) -> None:
        """Stage a batch of notification rows. The caller owns the commit."""
        if not rows:
            return
        self.session.add_all(rows)
        await self.session.flush()
