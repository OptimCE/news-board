"""Server-side enforcement of the poll-visibility matrix (spec section 4).

Covers admin/member x none/aggregate/full x never/before/after/ended, across the
voted / poll-ended states. The server is the boundary: when the requester is not
entitled to results, ``visible`` is False and no counts/identities are returned.
"""

import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories.news_factory import (
    add_vote,
    create_app_user,
    create_poll,
    org_headers,
    setup_active_news,
)

pytestmark = pytest.mark.asyncio


async def _seed_poll(db_session, community, *, av, mv, md, ended, requester_voted):
    """Create a poll with the given matrix + state and seed votes.

    Always seeds one vote from 'other-voter' (so counts > 0). When
    ``requester_voted`` also seeds a vote from 'voter-1' (the results requester).
    """
    expires = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=-1 if ended else 24)
    poll, options = await create_poll(
        db_session,
        id_community=community.id,
        options=["A", "B"],
        admin_visibility=av,
        member_visibility=mv,
        member_display=md,
        expires_at=expires,
    )
    await add_vote(
        db_session,
        id_community=community.id,
        id_post=poll.id,
        id_post_poll=options[0].id,
        voter_id="other-voter",
    )
    if requester_voted:
        await add_vote(
            db_session,
            id_community=community.id,
            id_post=poll.id,
            id_post_poll=options[1].id,
            voter_id="voter-1",
        )
    return poll, options


# (member_visibility, member_display, requester_voted, ended, expect_visible, expect_mode)
_MEMBER_CASES = [
    (0, 1, True, True, False, None),  # NONE -> never, regardless of timing
    (1, 1, False, False, True, "aggregate"),  # aggregate + before_vote -> always
    (1, 2, False, False, False, None),  # after_vote, not voted -> hidden
    (1, 2, True, False, True, "aggregate"),  # after_vote, voted -> shown
    (2, 3, False, False, False, None),  # full + when_ends, not ended -> hidden
    (2, 3, False, True, True, "full"),  # full + when_ends, ended -> shown
    (2, 0, True, True, False, None),  # NEVER -> hidden even when full + voted + ended
    (1, 1, False, True, True, "aggregate"),  # aggregate + before, ended -> shown
]


@pytest.mark.parametrize(
    ("mv", "md", "voted", "ended", "expect_visible", "expect_mode"), _MEMBER_CASES
)
async def test_member_visibility_matrix(
    client: AsyncClient,
    db_session: AsyncSession,
    mv: int,
    md: int,
    voted: bool,
    ended: bool,
    expect_visible: bool,
    expect_mode: str | None,
):
    community, _ = await setup_active_news(db_session, role="MEMBER", user_id="voter-1")
    await create_app_user(db_session, auth_user_id="other-voter", email="other@example.test")
    await create_app_user(db_session, auth_user_id="voter-1", email="voter@example.test")
    poll, _options = await _seed_poll(
        db_session, community, av=1, mv=mv, md=md, ended=ended, requester_voted=voted
    )

    headers = org_headers(community_auth_id="comm-1", user_id="voter-1", role="MEMBER")
    resp = await client.get(f"/posts/{poll.id}/results", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    assert data["visible"] is expect_visible
    assert data["mode"] == expect_mode
    if not expect_visible:
        assert data["options"] is None
        return

    assert data["options"] is not None
    assert data["total_voters"] >= 1
    if expect_mode == "aggregate":
        # counts only — never voter identities for a member under aggregate
        assert all(o["voters"] is None for o in data["options"])
    elif expect_mode == "full":
        assert any(o["voters"] for o in data["options"])


async def test_admin_aggregate_hides_identities(client: AsyncClient, db_session: AsyncSession):
    community, headers = await setup_active_news(db_session, role="ADMIN", user_id="admin-1")
    poll, _ = await _seed_poll(
        db_session, community, av=0, mv=0, md=0, ended=False, requester_voted=False
    )

    resp = await client.get(f"/posts/{poll.id}/results", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    # member_visibility=none does NOT blind the admin; admin sees aggregate.
    assert data["visible"] is True
    assert data["mode"] == "aggregate"
    assert all(o["voters"] is None for o in data["options"])
    assert sum(o["count"] for o in data["options"]) == 1


async def test_admin_full_reveals_identities_with_emails(
    client: AsyncClient, db_session: AsyncSession
):
    community, headers = await setup_active_news(db_session, role="ADMIN", user_id="admin-1")
    await create_app_user(db_session, auth_user_id="other-voter", email="other@example.test")
    poll, _ = await _seed_poll(
        db_session, community, av=1, mv=0, md=0, ended=False, requester_voted=False
    )

    resp = await client.get(f"/posts/{poll.id}/results", headers=headers)
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["visible"] is True
    assert data["mode"] == "full"
    voters = [v for o in data["options"] if o["voters"] for v in o["voters"]]
    assert any(
        v["voter_id"] == "other-voter" and v["email"] == "other@example.test" for v in voters
    )


async def test_results_on_plain_post_rejected(client: AsyncClient, db_session: AsyncSession):
    from tests.factories.news_factory import create_post

    community, headers = await setup_active_news(db_session)
    post = await create_post(db_session, id_community=community.id)
    resp = await client.get(f"/posts/{post.id}/results", headers=headers)
    assert resp.status_code == 400
    assert resp.json()["error_code"] == 2307  # NEWS.NOT_A_POLL
