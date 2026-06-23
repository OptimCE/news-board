import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from shared.const import PostType
from tests.factories.news_factory import (
    create_poll,
    create_post,
    org_headers,
    setup_active_news,
)

pytestmark = pytest.mark.asyncio


def _member(community_auth_id: str = "comm-1", user_id: str = "voter-1") -> dict:
    return org_headers(community_auth_id=community_auth_id, user_id=user_id, role="MEMBER")


async def _my_option_ids(client: AsyncClient, post_id: int, headers: dict) -> list[int]:
    detail = await client.get(f"/posts/{post_id}", headers=headers)
    assert detail.status_code == 200, detail.text
    return list(detail.json()["data"]["my_option_ids"])


async def test_single_choice_edit_leaves_one_row(client: AsyncClient, db_session: AsyncSession):
    community, _ = await setup_active_news(db_session)
    poll, options = await create_poll(db_session, id_community=community.id, options=["A", "B"])
    headers = _member()

    first = await client.post(
        f"/posts/{poll.id}/votes", json={"option_ids": [options[0].id]}, headers=headers
    )
    assert first.status_code == 200, first.text
    assert await _my_option_ids(client, poll.id, headers) == [options[0].id]

    # Change the vote: must replace, not accumulate.
    second = await client.post(
        f"/posts/{poll.id}/votes", json={"option_ids": [options[1].id]}, headers=headers
    )
    assert second.status_code == 200
    assert await _my_option_ids(client, poll.id, headers) == [options[1].id]


async def test_single_choice_rejects_multiple_selection(
    client: AsyncClient, db_session: AsyncSession
):
    community, _ = await setup_active_news(db_session)
    poll, options = await create_poll(db_session, id_community=community.id, options=["A", "B"])

    resp = await client.post(
        f"/posts/{poll.id}/votes",
        json={"option_ids": [options[0].id, options[1].id]},
        headers=_member(),
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == 2310  # NEWS.INVALID_VOTE


async def test_multi_choice_add_and_remove(client: AsyncClient, db_session: AsyncSession):
    community, _ = await setup_active_news(db_session)
    poll, options = await create_poll(
        db_session,
        id_community=community.id,
        options=["A", "B", "C"],
        poll_type=PostType.POLL_MULTIPLE_CHOICE,
    )
    headers = _member()

    await client.post(
        f"/posts/{poll.id}/votes",
        json={"option_ids": [options[0].id, options[1].id]},
        headers=headers,
    )
    assert set(await _my_option_ids(client, poll.id, headers)) == {options[0].id, options[1].id}

    # Re-vote a different subset: B + C.
    await client.post(
        f"/posts/{poll.id}/votes",
        json={"option_ids": [options[1].id, options[2].id]},
        headers=headers,
    )
    assert set(await _my_option_ids(client, poll.id, headers)) == {options[1].id, options[2].id}


async def test_vote_rejects_unknown_option(client: AsyncClient, db_session: AsyncSession):
    community, _ = await setup_active_news(db_session)
    poll, _options = await create_poll(db_session, id_community=community.id, options=["A", "B"])

    resp = await client.post(
        f"/posts/{poll.id}/votes", json={"option_ids": [999999]}, headers=_member()
    )
    assert resp.status_code == 422
    assert resp.json()["error_code"] == 2310


async def test_vote_on_plain_post_rejected(client: AsyncClient, db_session: AsyncSession):
    community, _ = await setup_active_news(db_session)
    post = await create_post(db_session, id_community=community.id)

    resp = await client.post(f"/posts/{post.id}/votes", json={"option_ids": [1]}, headers=_member())
    assert resp.status_code == 400
    assert resp.json()["error_code"] == 2307  # NEWS.NOT_A_POLL


async def test_vote_after_expiry_locked(client: AsyncClient, db_session: AsyncSession):
    community, _ = await setup_active_news(db_session)
    past = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)
    poll, options = await create_poll(
        db_session, id_community=community.id, options=["A", "B"], expires_at=past
    )

    resp = await client.post(
        f"/posts/{poll.id}/votes", json={"option_ids": [options[0].id]}, headers=_member()
    )
    assert resp.status_code == 403
    assert resp.json()["error_code"] == 2308  # NEWS.POLL_EXPIRED


async def test_retract_vote(client: AsyncClient, db_session: AsyncSession):
    community, _ = await setup_active_news(db_session)
    poll, options = await create_poll(db_session, id_community=community.id, options=["A", "B"])
    headers = _member()

    await client.post(
        f"/posts/{poll.id}/votes", json={"option_ids": [options[0].id]}, headers=headers
    )
    assert await _my_option_ids(client, poll.id, headers) == [options[0].id]

    retract = await client.delete(f"/posts/{poll.id}/votes", headers=headers)
    assert retract.status_code == 200
    assert await _my_option_ids(client, poll.id, headers) == []


async def test_retract_after_expiry_locked(client: AsyncClient, db_session: AsyncSession):
    community, _ = await setup_active_news(db_session)
    past = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)
    poll, _options = await create_poll(
        db_session, id_community=community.id, options=["A", "B"], expires_at=past
    )
    resp = await client.delete(f"/posts/{poll.id}/votes", headers=_member())
    assert resp.status_code == 403
    assert resp.json()["error_code"] == 2308
