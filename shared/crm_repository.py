from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from shared.models.crm_models import AppUserModel


class CRMRepository:
    """Read-only access to the core (CRM) database."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_emails_by_auth_ids(self, auth_ids: list[str]) -> dict[str, str]:
        """Map Keycloak ``sub`` values to their core ``app_user`` email.

        Used to snapshot a post author's email at creation and to denormalise
        voter identities under "full" poll visibility, without a cross-DB join.
        Auth ids not found in core are simply absent from the result.
        """
        unique_ids = [a for a in dict.fromkeys(auth_ids) if a]
        if not unique_ids:
            return {}
        stmt = select(AppUserModel.auth_user_id, AppUserModel.email).where(
            AppUserModel.auth_user_id.in_(unique_ids)
        )
        result = await self.session.execute(stmt)
        return {row.auth_user_id: row.email for row in result.all()}
