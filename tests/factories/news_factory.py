"""Async DB factories + auth-header helpers for the news board test suite.

Factories insert via the per-test ``db_session`` and ``flush()`` (never commit)
so rows are visible within the open test transaction and rolled back on teardown.
``org_headers`` builds the exact ``x-user-orgs`` blob KrakenD forwards, so tests
exercise the real ``GatewayScopeMiddleware`` role resolution.
"""

import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from core.database.models import Community, CommunitySubscription
from shared.const import FeatureName, PostType
from shared.models.crm_models import AppUserModel, CommunityUserModel
from shared.models.local_models import PostModel, PostPollModel, PostPollVoteModel


def org_headers(*, community_auth_id: str, user_id: str = "user-1", role: str = "MANAGER") -> dict:
    """Headers as injected by KrakenD: x-user-id, x-community-id and the
    x-user-orgs blob whose org id matches the active community."""
    return {
        "x-user-id": user_id,
        "x-community-id": community_auth_id,
        "x-user-orgs": f"[orgId:{community_auth_id} orgPath:/test roles:[{role}]]",
    }


async def create_community(
    session: AsyncSession, *, auth_community_id: str = "comm-1", name: str = "Test Community"
) -> Community:
    community = Community(name=name, auth_community_id=auth_community_id)
    session.add(community)
    await session.flush()
    return community


async def setup_active_news(
    session: AsyncSession,
    *,
    auth_id: str = "comm-1",
    name: str | None = None,
    role: str = "MANAGER",
    user_id: str = "user-1",
    active: bool = True,
) -> tuple[Community, dict]:
    """Create a community subscribed (or not) to News and return it + auth headers."""
    community = await create_community(
        session, auth_community_id=auth_id, name=name or f"Community {auth_id}"
    )
    await subscribe(session, id_community=community.id, is_active=active)
    return community, org_headers(community_auth_id=auth_id, user_id=user_id, role=role)


async def subscribe(
    session: AsyncSession,
    *,
    id_community: int,
    feature: FeatureName = FeatureName.NEWS,
    is_active: bool = True,
) -> CommunitySubscription:
    sub = CommunitySubscription(id_community=id_community, feature=feature, is_active=is_active)
    session.add(sub)
    await session.flush()
    return sub


async def create_app_user(session: AsyncSession, *, auth_user_id: str, email: str) -> AppUserModel:
    user = AppUserModel(auth_user_id=auth_user_id, email=email)
    session.add(user)
    await session.flush()
    return user


async def add_community_member(
    session: AsyncSession, *, id_community: int, id_user: int, role: str = "MEMBER"
) -> CommunityUserModel:
    """Add a row to the CRM ``community_user`` roster — the audience a published
    post/poll fans a notification out to."""
    member = CommunityUserModel(id_community=id_community, id_user=id_user, role=role)
    session.add(member)
    await session.flush()
    return member


async def create_post(
    session: AsyncSession,
    *,
    id_community: int,
    author_id: str = "author-1",
    author_email: str | None = "author@example.test",
    post: str = "Hello **world**",
) -> PostModel:
    row = PostModel(
        id_community=id_community,
        author_id=author_id,
        author_email=author_email,
        type=PostType.POST,
        post=post,
    )
    session.add(row)
    await session.flush()
    return row


async def create_poll(
    session: AsyncSession,
    *,
    id_community: int,
    options: list[str],
    poll_type: PostType = PostType.POLL_SINGLE_CHOICE,
    author_id: str = "author-1",
    post: str = "Pick one",
    expires_at: datetime.datetime | None = None,
    admin_visibility: int = 1,
    member_visibility: int = 1,
    member_display: int = 1,
) -> tuple[PostModel, list[PostPollModel]]:
    if expires_at is None:
        expires_at = datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=1)
    row = PostModel(
        id_community=id_community,
        author_id=author_id,
        author_email="author@example.test",
        type=poll_type,
        post=post,
        expires_at=expires_at,
        admin_visibility=admin_visibility,
        member_visibility=member_visibility,
        member_display=member_display,
    )
    session.add(row)
    await session.flush()
    option_rows = [
        PostPollModel(
            id_community=id_community,
            id_post=row.id,
            option_value=value,
            display_order=idx,
        )
        for idx, value in enumerate(options)
    ]
    session.add_all(option_rows)
    await session.flush()
    return row, option_rows


async def add_vote(
    session: AsyncSession,
    *,
    id_community: int,
    id_post: int,
    id_post_poll: int,
    voter_id: str,
) -> PostPollVoteModel:
    vote = PostPollVoteModel(
        id_community=id_community,
        id_post=id_post,
        id_post_poll=id_post_poll,
        voter_id=voter_id,
    )
    session.add(vote)
    await session.flush()
    return vote
