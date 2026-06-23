import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories.news_factory import (
    create_app_user,
    create_poll,
    create_post,
    org_headers,
    setup_active_news,
)

pytestmark = pytest.mark.asyncio


def _future_iso(hours: int = 24) -> str:
    return (datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=hours)).isoformat()


async def test_create_post_as_manager_then_listed(client: AsyncClient, db_session: AsyncSession):
    await create_app_user(db_session, auth_user_id="user-1", email="mgr@example.test")
    _, headers = await setup_active_news(db_session)

    resp = await client.post("/posts", json={"type": 0, "post": "Hello **world**"}, headers=headers)
    assert resp.status_code == 200, resp.text
    post_id = resp.json()["data"]["id"]

    listing = await client.get("/posts", headers=headers)
    assert listing.status_code == 200
    body = listing.json()
    assert body["pagination"]["total"] == 1
    item = body["data"][0]
    assert item["id"] == post_id
    assert item["is_poll"] is False
    assert "<strong>world</strong>" in item["body_html"]
    assert item["author_email"] == "mgr@example.test"


async def test_create_post_forbidden_for_member(client: AsyncClient, db_session: AsyncSession):
    _, headers = await setup_active_news(db_session, role="MEMBER")
    resp = await client.post("/posts", json={"type": 0, "post": "Hi"}, headers=headers)
    assert resp.status_code == 403
    assert resp.json()["error_code"] == 2  # AUTH.FORBIDDEN


async def test_create_requires_active_subscription(client: AsyncClient, db_session: AsyncSession):
    _, headers = await setup_active_news(db_session, active=False)
    resp = await client.post("/posts", json={"type": 0, "post": "Hi"}, headers=headers)
    assert resp.status_code == 403
    assert resp.json()["error_code"] == 1003  # SUBSCRIPTION.NOT_SUBSCRIBED


async def test_unknown_community_is_forbidden(client: AsyncClient, db_session: AsyncSession):
    # Header points at a community that does not exist / no subscription row.
    headers = org_headers(community_auth_id="ghost", user_id="user-1", role="MANAGER")
    resp = await client.post("/posts", json={"type": 0, "post": "Hi"}, headers=headers)
    assert resp.status_code == 403


async def test_create_poll_requires_two_options(client: AsyncClient, db_session: AsyncSession):
    _, headers = await setup_active_news(db_session)
    resp = await client.post(
        "/posts",
        json={
            "type": 1,
            "post": "Q",
            "options": [{"option_value": "only one"}],
            "expires_at": _future_iso(),
            "admin_visibility": 1,
            "member_visibility": 1,
            "member_display": 1,
        },
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == 2306  # NEWS.INVALID_POLL


async def test_create_poll_rejects_past_expiry(client: AsyncClient, db_session: AsyncSession):
    _, headers = await setup_active_news(db_session)
    resp = await client.post(
        "/posts",
        json={
            "type": 1,
            "post": "Q",
            "options": [{"option_value": "A"}, {"option_value": "B"}],
            "expires_at": _future_iso(-1),
            "admin_visibility": 1,
            "member_visibility": 1,
            "member_display": 1,
        },
        headers=headers,
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == 2306


async def test_create_poll_success_and_detail(client: AsyncClient, db_session: AsyncSession):
    _, headers = await setup_active_news(db_session)
    resp = await client.post(
        "/posts",
        json={
            "type": 2,
            "post": "Pick any",
            "options": [{"option_value": "A"}, {"option_value": "B"}, {"option_value": "C"}],
            "expires_at": _future_iso(),
            "admin_visibility": 1,
            "member_visibility": 1,
            "member_display": 2,
        },
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    post_id = resp.json()["data"]["id"]

    detail = await client.get(f"/posts/{post_id}", headers=headers)
    assert detail.status_code == 200
    data = detail.json()["data"]
    assert data["is_poll"] is True
    assert data["type"] == 2
    assert [o["option_value"] for o in data["options"]] == ["A", "B", "C"]
    assert data["has_voted"] is False
    assert data["member_display"] == 2


async def test_list_newest_first(client: AsyncClient, db_session: AsyncSession):
    community, headers = await setup_active_news(db_session)
    await create_post(db_session, id_community=community.id, post="older")
    await create_post(db_session, id_community=community.id, post="newer")

    listing = await client.get("/posts", headers=headers)
    bodies = [item["body_html"] for item in listing.json()["data"]]
    assert "newer" in bodies[0]
    assert "older" in bodies[1]


async def test_get_not_found(client: AsyncClient, db_session: AsyncSession):
    _, headers = await setup_active_news(db_session)
    resp = await client.get("/posts/99999", headers=headers)
    assert resp.status_code == 404
    assert resp.json()["error_code"] == 2302  # NEWS.POST_NOT_FOUND


async def test_update_text(client: AsyncClient, db_session: AsyncSession):
    community, headers = await setup_active_news(db_session)
    post = await create_post(db_session, id_community=community.id, post="before")

    resp = await client.patch(f"/posts/{post.id}", json={"post": "after"}, headers=headers)
    assert resp.status_code == 200, resp.text
    assert "after" in resp.json()["data"]["body_html"]


async def test_delete_post(client: AsyncClient, db_session: AsyncSession):
    community, headers = await setup_active_news(db_session)
    post = await create_post(db_session, id_community=community.id)

    resp = await client.delete(f"/posts/{post.id}", headers=headers)
    assert resp.status_code == 200
    gone = await client.get(f"/posts/{post.id}", headers=headers)
    assert gone.status_code == 404


async def test_delete_forbidden_for_member(client: AsyncClient, db_session: AsyncSession):
    community, headers = await setup_active_news(db_session, role="MEMBER")
    post = await create_post(db_session, id_community=community.id)
    resp = await client.delete(f"/posts/{post.id}", headers=headers)
    assert resp.status_code == 403


async def test_options_frozen_after_first_vote(client: AsyncClient, db_session: AsyncSession):
    community, headers = await setup_active_news(db_session)
    poll, options = await create_poll(db_session, id_community=community.id, options=["A", "B"])
    # A member casts a vote.
    member_headers = org_headers(community_auth_id="comm-1", user_id="voter-1", role="MEMBER")
    vote = await client.post(
        f"/posts/{poll.id}/votes", json={"option_ids": [options[0].id]}, headers=member_headers
    )
    assert vote.status_code == 200, vote.text

    # Manager tries to replace the options -> frozen.
    resp = await client.patch(
        f"/posts/{poll.id}",
        json={"options": [{"option_value": "X"}, {"option_value": "Y"}]},
        headers=headers,
    )
    assert resp.status_code == 409
    assert resp.json()["error_code"] == 2309  # NEWS.OPTIONS_FROZEN


async def test_options_editable_before_vote(client: AsyncClient, db_session: AsyncSession):
    community, headers = await setup_active_news(db_session)
    poll, _ = await create_poll(db_session, id_community=community.id, options=["A", "B"])

    resp = await client.patch(
        f"/posts/{poll.id}",
        json={"options": [{"option_value": "X"}, {"option_value": "Y"}, {"option_value": "Z"}]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    values = [o["option_value"] for o in resp.json()["data"]["options"]]
    assert values == ["X", "Y", "Z"]


async def test_community_isolation(client: AsyncClient, db_session: AsyncSession):
    comm1, _ = await setup_active_news(db_session, auth_id="comm-1", name="One")
    await create_post(db_session, id_community=comm1.id, post="secret of one")

    _, headers2 = await setup_active_news(db_session, auth_id="comm-2", name="Two", user_id="u2")
    listing = await client.get("/posts", headers=headers2)
    assert listing.status_code == 200
    assert listing.json()["pagination"]["total"] == 0
