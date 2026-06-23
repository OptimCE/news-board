"""Notifications fanned out when a post or poll is published.

A published post/poll inserts one CRM ``notification`` row per community member
*except the author*. The write rides on the same per-test session as the post
(``get_crm_session``/``get_local_session`` both resolve to ``db_session``), and is
best-effort: a failure in the fan-out must never fail the publish itself.
"""

import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database.models import Community
from core.notifications.repository import NotificationRepository
from shared.models.crm_models import AppUserModel, NotificationModel
from tests.factories.news_factory import (
    add_community_member,
    create_app_user,
    setup_active_news,
)

pytestmark = pytest.mark.asyncio


def _future_iso(hours: int = 24) -> str:
    return (datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=hours)).isoformat()


async def _seed_members(
    session: AsyncSession, community: Community, specs: list[tuple[str, str, str]]
) -> dict[str, AppUserModel]:
    """Create an ``app_user`` + ``community_user`` row per ``(auth_id, email, role)``."""
    users: dict[str, AppUserModel] = {}
    for auth_id, email, role in specs:
        user = await create_app_user(session, auth_user_id=auth_id, email=email)
        await add_community_member(session, id_community=community.id, id_user=user.id, role=role)
        users[auth_id] = user
    return users


async def _notifications(session: AsyncSession) -> list[NotificationModel]:
    result = await session.execute(select(NotificationModel))
    return list(result.scalars().all())


async def test_publishing_post_notifies_all_members_except_author(
    client: AsyncClient, db_session: AsyncSession
):
    community, headers = await setup_active_news(db_session)  # author = "user-1", MANAGER
    users = await _seed_members(
        db_session,
        community,
        [
            ("user-1", "mgr@example.test", "MANAGER"),  # the author — must be excluded
            ("member-1", "m1@example.test", "MEMBER"),
            ("member-2", "m2@example.test", "MEMBER"),
        ],
    )

    resp = await client.post("/posts", json={"type": 0, "post": "Hello **world**"}, headers=headers)
    assert resp.status_code == 200, resp.text
    post_id = resp.json()["data"]["id"]

    notifs = await _notifications(db_session)
    recipient_ids = {n.id_user for n in notifs}
    assert recipient_ids == {users["member-1"].id, users["member-2"].id}
    assert users["user-1"].id not in recipient_ids
    assert all(n.type == "news_post.published" for n in notifs)
    assert all(n.id_community == community.id for n in notifs)
    assert all(n.data == {"post_id": post_id} for n in notifs)
    assert all(n.read_at is None for n in notifs)


async def test_publishing_poll_uses_the_poll_type(client: AsyncClient, db_session: AsyncSession):
    community, headers = await setup_active_news(db_session)
    users = await _seed_members(
        db_session,
        community,
        [
            ("user-1", "mgr@example.test", "MANAGER"),
            ("member-1", "m1@example.test", "MEMBER"),
        ],
    )

    resp = await client.post(
        "/posts",
        json={
            "type": 2,
            "post": "Pick any",
            "options": [{"option_value": "A"}, {"option_value": "B"}],
            "expires_at": _future_iso(),
            "admin_visibility": 1,
            "member_visibility": 1,
            "member_display": 2,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    notifs = await _notifications(db_session)
    assert [n.id_user for n in notifs] == [users["member-1"].id]
    assert notifs[0].type == "news_poll.published"


async def test_no_other_members_yields_no_notifications(
    client: AsyncClient, db_session: AsyncSession
):
    _, headers = await setup_active_news(db_session)
    # The author exists but the community has no other members.
    await create_app_user(db_session, auth_user_id="user-1", email="mgr@example.test")

    resp = await client.post("/posts", json={"type": 0, "post": "Solo"}, headers=headers)
    assert resp.status_code == 200, resp.text

    assert await _notifications(db_session) == []


async def test_notification_failure_does_not_abort_publish(
    client: AsyncClient, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
):
    community, headers = await setup_active_news(db_session)
    await _seed_members(
        db_session,
        community,
        [
            ("user-1", "mgr@example.test", "MANAGER"),
            ("member-1", "m1@example.test", "MEMBER"),
        ],
    )

    async def _boom(self: NotificationRepository, rows: list[NotificationModel]) -> None:
        raise RuntimeError("notification store unavailable")

    monkeypatch.setattr(NotificationRepository, "insert_many", _boom)

    resp = await client.post("/posts", json={"type": 0, "post": "Resilient"}, headers=headers)
    # The post is created and returned even though the fan-out blew up ...
    assert resp.status_code == 200, resp.text
    post_id = resp.json()["data"]["id"]

    listing = await client.get("/posts", headers=headers)
    assert listing.json()["pagination"]["total"] == 1
    assert listing.json()["data"][0]["id"] == post_id
    # ... and the rolled-back fan-out leaves no notification rows behind.
    assert await _notifications(db_session) == []
