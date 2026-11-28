"""The news-board part of a data export (api/data_export.py).

Through the kit's own contract check (`run_contract_check`): the answer matches the contract,
every file listed was written, and each JSON file is checked here against its item schema
(core/export/schemas/files/news-board/).
"""

from __future__ import annotations

import json
import pathlib
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from api.data_export import export_handler
from core.export import ExportHandler, run_contract_check
from shared.const import PostType
from tests.factories.news_factory import (
    add_community_member,
    add_vote,
    create_app_user,
    create_poll,
    create_post,
    setup_active_news,
)

pytestmark = pytest.mark.asyncio

SERVICE = "news-board"
SCHEMAS = pathlib.Path(__file__).resolve().parent.parent / f"core/export/schemas/files/{SERVICE}"


def handler_for(session: AsyncSession) -> ExportHandler:
    @asynccontextmanager
    async def shared() -> AsyncIterator[AsyncSession]:
        yield session

    return export_handler(local=shared, crm=shared)


def _validators() -> dict[str, Draft202012Validator]:
    schemas = [json.loads(p.read_text(encoding="utf-8")) for p in SCHEMAS.glob("*.schema.json")]
    registry: Registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas
    )
    return {
        schema["title"].split("/")[1].removesuffix(".json item"): Draft202012Validator(
            schema, registry=registry, format_checker=FormatChecker()
        )
        for schema in schemas
        if schema.get("title", "").endswith(" item")
    }


async def export(
    session: AsyncSession, *, scope: dict[str, str], requester: str
) -> tuple[dict[str, Any], dict[str, list[dict[str, Any]]]]:
    """Runs one part; returns part.done and each JSON file's items, checked against its schema."""
    result = await run_contract_check(
        handler_for(session), service=SERVICE, scope=scope, requester_id=requester
    )
    assert result.outcome == "done", result.message
    validators = _validators()
    files: dict[str, list[dict[str, Any]]] = {}
    for file in result.message["files"]:
        document = json.loads(result.store.text(file["key"]))
        entity = document["entity"]
        errors = [
            f"{entity}[{i}]: {error.message}"
            for i, item in enumerate(document["items"])
            for error in validators[entity].iter_errors(item)
        ]
        assert not errors, errors
        files[entity] = document["items"]
    return result.message, files


def counters(done: dict[str, Any]) -> dict[str, int]:
    prefix = f"export.{SERVICE}."
    return {item["labelKey"].removeprefix(prefix): item["count"] for item in done["summary"]}


def user(sub: str) -> dict[str, Any]:
    return {"scope": {"type": "user", "id": sub}, "requester": sub}


async def world(session: AsyncSession) -> dict[str, Any]:
    """Two communities. In the first: an admin's post and poll (A, B), someone else's post, and
    two votes; voter-1 also voted in the second community. Accounts: admin, manager, voter-1."""
    community, _ = await setup_active_news(session, auth_id=f"comm-{uuid.uuid4().hex[:6]}")
    other, _ = await setup_active_news(session, auth_id=f"comm-{uuid.uuid4().hex[:6]}")
    accounts = {}
    for sub, role in (("user-admin", "ADMIN"), ("user-manager", "MANAGER"), ("voter-1", "MEMBER")):
        account = await create_app_user(session, auth_user_id=sub, email=f"{sub}@example.test")
        await add_community_member(
            session, id_community=community.id, id_user=account.id, role=role
        )
        accounts[sub] = account
    post = await create_post(session, id_community=community.id, author_id="user-admin")
    poll, (option_a, option_b) = await create_poll(
        session, id_community=community.id, options=["A", "B"], author_id="user-admin"
    )
    await create_post(session, id_community=community.id, author_id="someone-else")
    await add_vote(
        session,
        id_community=community.id,
        id_post=poll.id,
        id_post_poll=option_a.id,
        voter_id="voter-1",
    )
    await add_vote(
        session,
        id_community=community.id,
        id_post=poll.id,
        id_post_poll=option_b.id,
        voter_id="voter-2",
    )
    elsewhere, (there,) = await create_poll(
        session, id_community=other.id, options=["Oui"], author_id="someone-else"
    )
    await add_vote(
        session,
        id_community=other.id,
        id_post=elsewhere.id,
        id_post_poll=there.id,
        voter_id="voter-1",
    )
    return {
        "community": community,
        "other": other,
        "post": post,
        "poll": poll,
        "a": option_a,
        "b": option_b,
    }


class TestUserExport:
    async def test_her_votes_in_every_community_and_nothing_else(self, db_session):
        w = await world(db_session)
        done, files = await export(db_session, **user("voter-1"))
        assert files["my-posts"] == []
        votes = files["my-votes"]
        assert {(v["id_community"], v["option_value"]) for v in votes} == {
            (w["community"].id, "A"),
            (w["other"].id, "Oui"),
        }
        assert all(v["poll"] == "Pick one" and v["community"] for v in votes)
        assert counters(done) == {"posts": 0, "votes": 2}

    async def test_an_author_gets_what_they_published_with_the_options(self, db_session):
        w = await world(db_session)
        _done, files = await export(db_session, **user("user-admin"))
        posts = {p["id"]: p for p in files["my-posts"]}
        assert set(posts) == {w["post"].id, w["poll"].id}
        assert posts[w["post"].id]["type"] == "POST" and posts[w["post"].id]["options"] == []
        poll = posts[w["poll"].id]
        assert poll["type"] == PostType.POLL_SINGLE_CHOICE.name
        assert [o["option_value"] for o in poll["options"]] == ["A", "B"]
        assert "votes" not in json.dumps(poll["options"])
        assert files["my-votes"] == []


class TestCommunityExport:
    async def test_every_post_and_poll_with_counts_never_who_voted(self, db_session):
        w = await world(db_session)
        community = {"type": "community", "id": w["community"].auth_community_id}
        done, files = await export(db_session, scope=community, requester="user-admin")

        posts = {p["id"]: p for p in files["posts"]}
        assert len(posts) == 3
        poll = posts[w["poll"].id]
        assert {o["option_value"]: o["votes"] for o in poll["options"]} == {"A": 1, "B": 1}
        assert poll["voters"] == 2 and posts[w["post"].id]["voters"] is None
        assert poll["author_id"] == "user-admin" and poll["author_email"]
        assert "voter-1" not in json.dumps(files) and "voter-2" not in json.dumps(files)
        assert counters(done) == {"posts": 3, "polls": 1, "votes": 2}

    async def test_the_module_off_hides_nothing(self, db_session):
        w = await world(db_session)
        await db_session.execute(
            text("UPDATE community_subscription SET is_active = false WHERE id_community = :c"),
            {"c": w["community"].id},
        )
        community = {"type": "community", "id": w["community"].auth_community_id}
        _done, files = await export(db_session, scope=community, requester="user-admin")
        assert len(files["posts"]) == 3

    @pytest.mark.parametrize("sub", ["user-manager", "voter-1"])
    async def test_only_an_admin_exports_the_community(self, db_session, sub):
        w = await world(db_session)
        result = await run_contract_check(
            handler_for(db_session),
            service=SERVICE,
            scope={"type": "community", "id": w["community"].auth_community_id},
            requester_id=sub,
        )
        assert result.outcome == "failed"
        assert result.message["errorCode"] == "forbidden"

    async def test_an_unknown_community_is_scope_not_found(self, db_session):
        await world(db_session)
        result = await run_contract_check(
            handler_for(db_session),
            service=SERVICE,
            scope={"type": "community", "id": str(uuid.uuid4())},
            requester_id="user-admin",
        )
        assert result.outcome == "failed"
        assert result.message["errorCode"] == "scope_not_found"
