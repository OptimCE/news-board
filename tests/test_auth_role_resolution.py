"""Role resolution from the KrakenD ``x-user-orgs`` blob.

The effective role is the one attached to the org whose id equals the active
``x-community-id`` — not the highest role across all the user's communities.
This is the glue that makes ``require_min_role`` correct for the news writes.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from core.security.gateway_auth import parse_user_orgs
from core.security.user_context import Role
from tests.factories.news_factory import create_community, subscribe


def _multi_org_blob(orgs: list[tuple[str, str]]) -> str:
    """Build the ``[orgId:.. orgPath:.. roles:[..]],map[..]`` header KrakenD sends."""
    return ",map".join(f"[orgId:{oid} orgPath:/{oid} roles:[{role}]]" for oid, role in orgs)


def test_parse_single_org():
    tokens = parse_user_orgs("[orgId:abc orgPath:/x roles:[ADMIN]]")
    assert len(tokens) == 1
    assert tokens[0].org_id == "abc"
    assert tokens[0].role == Role.ADMIN


def test_parse_multi_org_picks_highest_role_per_org():
    tokens = parse_user_orgs(_multi_org_blob([("abc", "MEMBER,MANAGER"), ("def", "MEMBER")]))
    by_id = {t.org_id: t.role for t in tokens}
    assert by_id["abc"] == Role.MANAGER  # highest of MEMBER, MANAGER
    assert by_id["def"] == Role.MEMBER


def test_parse_org_path_with_spaces():
    # Keycloak group names (and thus orgPath) routinely contain spaces; the old
    # whitespace-split parser raised IndexError here -> "Failed to parse org token".
    tokens = parse_user_orgs("[orgId:abc orgPath:/Mon Comité roles:[ADMIN]]")
    assert len(tokens) == 1
    assert tokens[0].org_id == "abc"
    assert tokens[0].org_path == "/Mon Comité"
    assert tokens[0].role == Role.ADMIN


def test_parse_multi_org_with_spaces_in_paths():
    blob = (
        "[orgId:2c8a orgPath:/Mon Comité roles:[ADMIN]],"
        "map[orgId:100 orgPath:/Autre CE roles:[MEMBER]]"
    )
    by_id = {t.org_id: t.role for t in parse_user_orgs(blob)}
    assert by_id["2c8a"] == Role.ADMIN
    assert by_id["100"] == Role.MEMBER


def test_parse_space_separated_roles():
    # Go renders string slices space-separated (roles:[MEMBER MANAGER]); the
    # highest role must still resolve.
    tokens = parse_user_orgs("[orgId:abc orgPath:/x roles:[MEMBER MANAGER]]")
    assert len(tokens) == 1
    assert tokens[0].role == Role.MANAGER


@pytest.mark.asyncio
async def test_role_is_resolved_per_active_community(client: AsyncClient, db_session: AsyncSession):
    # Same user: MEMBER in comm-1, ADMIN in comm-2. Both subscribed to News.
    c1 = await create_community(db_session, auth_community_id="comm-1", name="One")
    c2 = await create_community(db_session, auth_community_id="comm-2", name="Two")
    await subscribe(db_session, id_community=c1.id)
    await subscribe(db_session, id_community=c2.id)

    blob = _multi_org_blob([("comm-1", "MEMBER"), ("comm-2", "ADMIN")])
    base = {"x-user-id": "user-1", "x-user-orgs": blob}

    # Active community comm-1 -> resolved role MEMBER -> create forbidden.
    forbidden = await client.post(
        "/posts", json={"type": 0, "post": "hi"}, headers={**base, "x-community-id": "comm-1"}
    )
    assert forbidden.status_code == 403
    assert forbidden.json()["error_code"] == 2  # AUTH.FORBIDDEN

    # Active community comm-2 -> resolved role ADMIN -> create allowed.
    allowed = await client.post(
        "/posts", json={"type": 0, "post": "hi"}, headers={**base, "x-community-id": "comm-2"}
    )
    assert allowed.status_code == 200, allowed.text
