"""The news-board part of a data export (monorepo contracts/export/README.md, §7).

User scope — what the requester wrote and chose, in every community:
- ``my-posts.json``: the posts and polls they published (``author_id`` = their Keycloak sub), with
  each poll's options;
- ``my-votes.json``: each option they voted for, with its poll.

Community scope (an ADMIN, re-checked in crm_db by the kit): every post and poll of the
community, with each option's vote count and the poll's number of voters. Who voted for what is
never in it: an individual vote is the member's own data, in their personal export.

No file: a post is Markdown text kept in the database. The module's subscription is not checked
(an export is not a use of the module). NATS is this service's only use of the broker: the
consumer connects in the background and retries, so a broker outage never stops the API.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable, Iterable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.export import (
    ExportHandler,
    ExportStorageSettings,
    PartContext,
    Requester,
    S3PartStore,
    SqlCrmLookup,
    resolve_requester,
)
from shared.const import AdminVisibility, MemberDisplay, MemberVisibility, PostType
from shared.models.local_models import PostModel, PostPollModel, PostPollVoteModel

logger = logging.getLogger(__name__)

SERVICE = "news-board"
SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]
_RETRY_SECONDS = 15.0


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _name(enum: type[Enum], value: int | None) -> str | int | None:
    """A code by its name; a code retired since keeps its number rather than failing the export."""
    if value is None:
        return None
    try:
        return str(enum(value).name)
    except ValueError:
        return int(value)


def post_item(post: PostModel, options: list[PostPollModel]) -> dict[str, Any]:
    """A post or a poll as stored, codes by name; its options in their display order."""
    return {
        "id": post.id,
        "type": _name(PostType, post.type),
        "post": post.post,
        "expires_at": _iso(post.expires_at),
        "admin_visibility": _name(AdminVisibility, post.admin_visibility),
        "member_visibility": _name(MemberVisibility, post.member_visibility),
        "member_display": _name(MemberDisplay, post.member_display),
        "created_at": _iso(post.created_at),
        "updated_at": _iso(post.updated_at),
        "options": [
            {"id": o.id, "option_value": o.option_value, "display_order": o.display_order}
            for o in sorted(options, key=lambda o: (o.display_order, o.id))
        ],
    }


class _Part:
    def __init__(self, ctx: PartContext, *, local: AsyncSession, crm: AsyncSession) -> None:
        self.ctx = ctx
        self.local = local
        self.crm = crm

    async def community_names(self, ids: Iterable[int]) -> dict[int, str | None]:
        wanted = sorted(set(ids))
        if not wanted:
            return {}
        result = await self.crm.execute(
            text("SELECT id, name FROM community WHERE id = ANY(:ids)"), {"ids": wanted}
        )
        return {int(row[0]): row[1] for row in result}

    async def options_of(self, post_ids: list[int]) -> dict[int, list[PostPollModel]]:
        out: dict[int, list[PostPollModel]] = {i: [] for i in post_ids}
        if post_ids:
            for option in (
                await self.local.execute(
                    select(PostPollModel).where(PostPollModel.id_post.in_(post_ids))
                )
            ).scalars():
                out[option.id_post].append(option)
        return out

    # ---- user scope --------------------------------------------------------------------------

    async def user_export(self, requester: Requester) -> None:
        sub = requester.auth_user_id
        posts = list(
            (
                await self.local.execute(
                    select(PostModel).where(PostModel.author_id == sub).order_by(PostModel.id)
                )
            ).scalars()
        )
        votes = (
            await self.local.execute(
                select(PostPollVoteModel, PostPollModel, PostModel)
                .join(PostPollModel, PostPollModel.id == PostPollVoteModel.id_post_poll)
                .join(PostModel, PostModel.id == PostPollVoteModel.id_post)
                .where(PostPollVoteModel.voter_id == sub)
                .order_by(PostPollVoteModel.id)
            )
        ).all()
        names = await self.community_names(
            [p.id_community for p in posts] + [v.id_community for v, _o, _p in votes]
        )
        options = await self.options_of([p.id for p in posts])
        written = await self.ctx.write_json(
            "my-posts",
            (
                {
                    "id_community": p.id_community,
                    "community": names.get(p.id_community),
                    **post_item(p, options[p.id]),
                }
                for p in posts
            ),
        )
        self.ctx.count("posts", written)
        written = await self.ctx.write_json(
            "my-votes",
            (
                {
                    "id": vote.id,
                    "id_community": vote.id_community,
                    "community": names.get(vote.id_community),
                    "id_post": vote.id_post,
                    "poll": post.post,
                    "id_post_poll": vote.id_post_poll,
                    "option_value": option.option_value,
                    "created_at": _iso(vote.created_at),
                    "updated_at": _iso(vote.updated_at),
                }
                for vote, option, post in votes
            ),
        )
        self.ctx.count("votes", written)

    # ---- community scope ---------------------------------------------------------------------

    async def community_export(self, id_community: int) -> None:
        posts = list(
            (
                await self.local.execute(
                    select(PostModel)
                    .where(PostModel.id_community == id_community)
                    .order_by(PostModel.id)
                )
            ).scalars()
        )
        ids = [p.id for p in posts]
        options = await self.options_of(ids)
        per_option: dict[int, int] = {}
        voters: dict[int, int] = {}
        if ids:
            for option_id, count in (
                await self.local.execute(
                    select(PostPollVoteModel.id_post_poll, func.count())
                    .where(PostPollVoteModel.id_post.in_(ids))
                    .group_by(PostPollVoteModel.id_post_poll)
                )
            ).all():
                per_option[int(option_id)] = int(count)
            for post_id, count in (
                await self.local.execute(
                    select(
                        PostPollVoteModel.id_post,
                        func.count(func.distinct(PostPollVoteModel.voter_id)),
                    )
                    .where(PostPollVoteModel.id_post.in_(ids))
                    .group_by(PostPollVoteModel.id_post)
                )
            ).all():
                voters[int(post_id)] = int(count)

        def item(post: PostModel) -> dict[str, Any]:
            base = post_item(post, options[post.id])
            poll = post.type != PostType.POST.value
            for option in base["options"]:
                option["votes"] = per_option.get(option["id"], 0)
            return {
                **base,
                "author_id": post.author_id,
                "author_email": post.author_email,
                "voters": voters.get(post.id, 0) if poll else None,
            }

        self.ctx.count("posts", await self.ctx.write_json("posts", (item(p) for p in posts)))
        self.ctx.count("polls", sum(1 for p in posts if p.type != PostType.POST.value))
        self.ctx.count("votes", sum(per_option.values()))


def export_handler(*, local: SessionFactory, crm: SessionFactory) -> ExportHandler:
    """The handler the kit calls for each part of this service."""

    async def handle(ctx: PartContext) -> None:
        async with crm() as crm_session, local() as local_session:
            requester = await resolve_requester(SqlCrmLookup(crm_session), ctx.request)
            part = _Part(ctx, local=local_session, crm=crm_session)
            if requester.community_id is None:
                await part.user_export(requester)
            else:
                await part.community_export(requester.community_id)

    return handle


async def _consume(stop: asyncio.Event, storage: ExportStorageSettings) -> None:
    """Connects to NATS (retried in the background), then runs the kit's consumer until stop."""
    import nats

    from core.database.database import AsyncSessionCRMFactory, AsyncSessionLocalFactory
    from core.export.consumer import run_export_consumer

    servers = [u.strip() for u in settings.NATS_URL.split(",") if u.strip()]
    client = None
    while client is None and not stop.is_set():
        try:
            client = await nats.connect(
                servers=servers,
                reconnect_time_wait=2,
                max_reconnect_attempts=-1,
                connect_timeout=5,
            )
        except Exception as err:
            logger.warning(
                "Data export: NATS unreachable; retrying",
                extra={"operation": "export:nats_retry", "error": type(err).__name__},
            )
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=_RETRY_SECONDS)
    if client is None:
        return
    try:
        await run_export_consumer(
            client.jetstream(),
            service=SERVICE,
            handler=export_handler(local=AsyncSessionLocalFactory, crm=AsyncSessionCRMFactory),
            store=S3PartStore(storage),
            stop=stop,
            expected_bucket=storage.bucket,
        )
    finally:
        with contextlib.suppress(Exception):
            await client.drain()


def start_export_consumer(stop: asyncio.Event) -> asyncio.Task[None] | None:
    """Starts this service's export consumer, or logs why it cannot (and the API runs on).

    Needs NATS_URL and the export account (EXPORT_STORAGE_*), never another storage account.
    """
    try:
        if not settings.NATS_URL.strip():
            raise RuntimeError("NATS_URL is not set")
        storage = ExportStorageSettings.from_env()
    except RuntimeError as err:
        logger.warning(
            "Data export disabled: %s",
            err,
            extra={"operation": "export:consumer_disabled", "service": SERVICE},
        )
        return None
    return asyncio.create_task(_consume(stop, storage), name="news-board-export-consumer")


async def stop_export_consumer(
    task: asyncio.Task[None] | None, stop: asyncio.Event, grace: float = 10.0
) -> None:
    """Stops pulling; a part in progress is aborted and nak'ed (redelivered later)."""
    stop.set()
    if task is None:
        return
    try:
        await asyncio.wait_for(task, timeout=grace)
    except TimeoutError:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
