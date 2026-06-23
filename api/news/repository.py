from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.database.with_community import with_community_scope
from shared.models.local_models import PostModel, PostPollModel, PostPollVoteModel


class NewsRepository:
    """Local-DB queries for the news board, all scoped to the request community.

    Reads apply ``with_community_scope`` (the internal community id resolved once
    per request). Writes set ``id_community`` explicitly on each row; the service
    owns the commit boundary so a write and its options/votes share one
    transaction.
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    # ---- posts ------------------------------------------------------------

    async def create_post(self, post: PostModel) -> PostModel:
        self.session.add(post)
        await self.session.flush()
        return post

    async def get_post(self, post_id: int) -> PostModel | None:
        stmt = with_community_scope(select(PostModel), PostModel).where(PostModel.id == post_id)
        result = await self.session.execute(stmt)
        return cast(PostModel | None, result.scalar_one_or_none())

    async def get_post_with_options(self, post_id: int) -> PostModel | None:
        stmt = (
            with_community_scope(select(PostModel), PostModel)
            .options(selectinload(PostModel.options))
            .where(PostModel.id == post_id)
        )
        result = await self.session.execute(stmt)
        return cast(PostModel | None, result.scalar_one_or_none())

    async def list_posts(self, page: int, page_size: int) -> tuple[list[PostModel], int]:
        base = with_community_scope(select(PostModel), PostModel)

        total_result = await self.session.execute(select(func.count()).select_from(base.subquery()))
        total = total_result.scalar_one()

        rows_result = await self.session.execute(
            base.options(selectinload(PostModel.options))
            .order_by(PostModel.created_at.desc(), PostModel.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        rows = list(rows_result.scalars().all())
        return rows, total

    async def delete_post(self, post: PostModel) -> None:
        await self.session.delete(post)
        await self.session.flush()

    # ---- options ----------------------------------------------------------

    async def add_options(self, options: list[PostPollModel]) -> None:
        self.session.add_all(options)
        await self.session.flush()

    # ---- votes ------------------------------------------------------------

    async def count_votes_for_post(self, post_id: int) -> int:
        stmt = with_community_scope(
            select(func.count()).select_from(PostPollVoteModel), PostPollVoteModel
        ).where(PostPollVoteModel.id_post == post_id)
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def get_voter_votes(self, post_id: int, voter_id: str) -> list[PostPollVoteModel]:
        stmt = with_community_scope(select(PostPollVoteModel), PostPollVoteModel).where(
            PostPollVoteModel.id_post == post_id,
            PostPollVoteModel.voter_id == voter_id,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def add_votes(self, votes: list[PostPollVoteModel]) -> None:
        self.session.add_all(votes)
        await self.session.flush()

    async def delete_votes(self, votes: list[PostPollVoteModel]) -> None:
        for vote in votes:
            await self.session.delete(vote)
        await self.session.flush()

    async def get_votes_for_post(self, post_id: int) -> list[tuple[int, str]]:
        """Return ``(id_post_poll, voter_id)`` for every vote on the poll."""
        stmt = with_community_scope(
            select(PostPollVoteModel.id_post_poll, PostPollVoteModel.voter_id),
            PostPollVoteModel,
        ).where(PostPollVoteModel.id_post == post_id)
        result = await self.session.execute(stmt)
        return [(row.id_post_poll, row.voter_id) for row in result.all()]

    async def get_voted_post_ids(self, voter_id: str, post_ids: list[int]) -> set[int]:
        """Which of ``post_ids`` the voter has at least one vote on (for list views)."""
        if not post_ids:
            return set()
        stmt = with_community_scope(
            select(PostPollVoteModel.id_post).distinct(), PostPollVoteModel
        ).where(
            PostPollVoteModel.voter_id == voter_id,
            PostPollVoteModel.id_post.in_(post_ids),
        )
        result = await self.session.execute(stmt)
        return set(result.scalars().all())
