import datetime
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from api.news.mappers import to_post_detail, to_post_list_item
from api.news.repository import NewsRepository
from api.news.schemas import (
    CreatePostRequest,
    CreatePostResponse,
    OptionTally,
    PollResults,
    PostDetail,
    PostListItem,
    ResultsMode,
    UpdatePostRequest,
    VoterIdentity,
)
from core.api_response import Pagination
from core.audit_log import AuditActions, AuditLogInput, AuditLogService
from core.context_vars import current_user_id, current_user_role
from core.errors.errors import ErrorException
from core.notifications import NotificationService, NotificationTypes
from core.security.user_context import ROLE_HIERARCHY, Role
from shared.const import (
    AdminVisibility,
    MemberDisplay,
    MemberVisibility,
    PostType,
)
from shared.crm_repository import CRMRepository
from shared.custom_errors import errors
from shared.models.local_models import PostModel, PostPollModel, PostPollVoteModel

logger = logging.getLogger(__name__)


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _ensure_aware(dt: datetime.datetime) -> datetime.datetime:
    """Treat a naive client-supplied datetime as UTC so comparisons are safe."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=datetime.UTC)


class NewsService:
    """Orchestrates the news board: posts, polls, voting, and the server-side
    poll-visibility matrix. The service owns the commit boundary."""

    def __init__(self, local_session: AsyncSession, crm_session: AsyncSession):
        self.local_session = local_session
        self.crm_session = crm_session
        self.repository = NewsRepository(local_session)
        self.crm_repository = CRMRepository(crm_session)
        self.audit_log_service = AuditLogService(crm_session)
        self.notification_service = NotificationService(crm_session)

    # ---- posts ------------------------------------------------------------

    async def create_post(
        self, req: CreatePostRequest, internal_community_id: int, author_id: str
    ) -> CreatePostResponse:
        is_poll = req.type.is_poll
        expires = self._validate_poll_payload(req) if is_poll else None

        emails = await self.crm_repository.get_emails_by_auth_ids([author_id])
        post = PostModel(
            id_community=internal_community_id,
            author_id=author_id,
            author_email=emails.get(author_id),
            type=req.type,
            post=req.post,
            expires_at=expires,
            admin_visibility=int(req.admin_visibility) if is_poll else None,  # type: ignore[arg-type]
            member_visibility=int(req.member_visibility) if is_poll else None,  # type: ignore[arg-type]
            member_display=int(req.member_display) if is_poll else None,  # type: ignore[arg-type]
        )
        await self.repository.create_post(post)

        if is_poll and req.options:
            await self.repository.add_options(
                self._build_options(req.options, post.id, internal_community_id)
            )

        await self.local_session.commit()
        await self._audit(
            AuditLogInput(
                action=AuditActions.POST_CREATED,
                entity_type="post",
                entity_id=str(post.id),
                payload={
                    "type": int(req.type),
                    "is_poll": is_poll,
                    "option_count": len(req.options) if req.options else 0,
                    "expires_at": expires.isoformat() if expires else None,
                },
            )
        )
        await self._notify_post_created(post, is_poll, internal_community_id, author_id)
        return CreatePostResponse(id=post.id)

    async def list_posts(self, page: int, page_size: int) -> tuple[list[PostListItem], Pagination]:
        rows, total = await self.repository.list_posts(page, page_size)

        voter_id = current_user_id.get()
        voted_ids: set[int] = set()
        if voter_id:
            poll_ids = [p.id for p in rows if PostType(p.type).is_poll]
            voted_ids = await self.repository.get_voted_post_ids(voter_id, poll_ids)

        data = [
            to_post_list_item(
                p,
                has_voted=p.id in voted_ids,
                poll_ended=self._poll_ended(p),
                option_count=len(p.options),
            )
            for p in rows
        ]
        pagination = Pagination(
            page=page,
            limit=page_size,
            total=total,
            total_pages=-(-total // page_size) if page_size else 0,
        )
        return data, pagination

    async def get_post(self, post_id: int) -> PostDetail:
        post = await self.repository.get_post_with_options(post_id)
        if post is None:
            raise ErrorException(errors.news.POST_NOT_FOUND, status_code=404)

        has_voted, my_option_ids = await self._voter_selection(post)
        return to_post_detail(
            post,
            list(post.options),
            has_voted=has_voted,
            poll_ended=self._poll_ended(post),
            my_option_ids=my_option_ids,
        )

    async def update_post(self, post_id: int, req: UpdatePostRequest) -> PostDetail:
        post = await self.repository.get_post_with_options(post_id)
        if post is None:
            raise ErrorException(errors.news.POST_NOT_FOUND, status_code=404)

        if req.post is not None:
            post.post = req.post

        if PostType(post.type).is_poll:
            if req.expires_at is not None:
                post.expires_at = _ensure_aware(req.expires_at)
            if req.admin_visibility is not None:
                post.admin_visibility = int(req.admin_visibility)
            if req.member_visibility is not None:
                post.member_visibility = int(req.member_visibility)
            if req.member_display is not None:
                post.member_display = int(req.member_display)
            if req.options is not None:
                await self._replace_options(post, req.options)

        await self.local_session.commit()
        await self._audit(
            AuditLogInput(
                action=AuditActions.POST_UPDATED,
                entity_type="post",
                entity_id=str(post_id),
                payload={"options_replaced": req.options is not None},
            )
        )
        return await self.get_post(post_id)

    async def delete_post(self, post_id: int) -> None:
        post = await self.repository.get_post(post_id)
        if post is None:
            raise ErrorException(errors.news.POST_NOT_FOUND, status_code=404)

        post_type = int(post.type)
        await self.repository.delete_post(post)  # DB ON DELETE CASCADE removes options + votes
        await self.local_session.commit()
        await self._audit(
            AuditLogInput(
                action=AuditActions.POST_DELETED,
                entity_type="post",
                entity_id=str(post_id),
                payload={"type": post_type},
            )
        )

    # ---- voting -----------------------------------------------------------

    async def cast_vote(self, post_id: int, option_ids: list[int]) -> None:
        post = await self.repository.get_post_with_options(post_id)
        if post is None:
            raise ErrorException(errors.news.POST_NOT_FOUND, status_code=404)
        post_type = PostType(post.type)
        if not post_type.is_poll:
            raise ErrorException(errors.news.NOT_A_POLL, status_code=400)
        if self._poll_ended(post):
            raise ErrorException(errors.news.POLL_EXPIRED, status_code=403)

        voter_id = self._require_voter()
        selected = self._validate_selection(option_ids, post_type, post.options)

        # Transactional swap: drop the voter's current rows for this poll, insert
        # the new selection. For single-choice this leaves exactly one row.
        existing = await self.repository.get_voter_votes(post_id, voter_id)
        await self.repository.delete_votes(existing)
        await self.repository.add_votes(
            [
                PostPollVoteModel(
                    id_community=post.id_community,
                    id_post=post_id,
                    id_post_poll=option_id,
                    voter_id=voter_id,
                )
                for option_id in selected
            ]
        )
        await self.local_session.commit()
        await self._audit(
            AuditLogInput(
                action=AuditActions.VOTE_CAST,
                entity_type="post_poll_vote",
                entity_id=str(post_id),
                payload={"option_ids": selected},
            )
        )

    async def retract_vote(self, post_id: int) -> None:
        post = await self.repository.get_post(post_id)
        if post is None:
            raise ErrorException(errors.news.POST_NOT_FOUND, status_code=404)
        if not PostType(post.type).is_poll:
            raise ErrorException(errors.news.NOT_A_POLL, status_code=400)
        if self._poll_ended(post):
            raise ErrorException(errors.news.POLL_EXPIRED, status_code=403)

        voter_id = self._require_voter()
        existing = await self.repository.get_voter_votes(post_id, voter_id)
        if not existing:
            return  # idempotent: nothing to retract
        await self.repository.delete_votes(existing)
        await self.local_session.commit()
        await self._audit(
            AuditLogInput(
                action=AuditActions.VOTE_RETRACTED,
                entity_type="post_poll_vote",
                entity_id=str(post_id),
                payload={},
            )
        )

    # ---- results (visibility-enforced) ------------------------------------

    async def get_results(self, post_id: int) -> PollResults:
        post = await self.repository.get_post_with_options(post_id)
        if post is None:
            raise ErrorException(errors.news.POST_NOT_FOUND, status_code=404)
        if not PostType(post.type).is_poll:
            raise ErrorException(errors.news.NOT_A_POLL, status_code=400)

        poll_ended = self._poll_ended(post)
        voter_id = current_user_id.get()
        votes = await self.repository.get_votes_for_post(post_id)
        has_voted = voter_id is not None and any(v == voter_id for _, v in votes)

        visible, mode = self._resolve_results_visibility(
            post, privileged=self._is_privileged(), has_voted=has_voted, poll_ended=poll_ended
        )
        if not visible:
            return PollResults(post_id=post_id, poll_ended=poll_ended, visible=False)

        voters_by_option: dict[int, list[str]] = {}
        for option_id, v in votes:
            voters_by_option.setdefault(option_id, []).append(v)
        distinct_voters = {v for _, v in votes}

        emails: dict[str, str] = {}
        if mode == ResultsMode.FULL:
            emails = await self.crm_repository.get_emails_by_auth_ids(list(distinct_voters))

        options_out: list[OptionTally] = []
        for opt in post.options:  # ordered by display_order
            voters_for_opt = voters_by_option.get(opt.id, [])
            voters_payload = (
                [VoterIdentity(voter_id=v, email=emails.get(v)) for v in voters_for_opt]
                if mode == ResultsMode.FULL
                else None
            )
            options_out.append(
                OptionTally(
                    option_id=opt.id,
                    option_value=opt.option_value,
                    count=len(voters_for_opt),
                    voters=voters_payload,
                )
            )

        return PollResults(
            post_id=post_id,
            poll_ended=poll_ended,
            visible=True,
            mode=mode,
            total_voters=len(distinct_voters),
            options=options_out,
        )

    # ---- helpers ----------------------------------------------------------

    @staticmethod
    def _poll_ended(post: PostModel) -> bool:
        return post.expires_at is not None and _now() >= _ensure_aware(post.expires_at)

    @staticmethod
    def _require_voter() -> str:
        voter_id = current_user_id.get()
        if not voter_id:
            raise ErrorException(errors.auth.UNAUTHORIZED, status_code=401)
        return voter_id

    @staticmethod
    def _current_role() -> Role | None:
        role_str = current_user_role.get()
        if not role_str:
            return None
        try:
            return Role(role_str)
        except ValueError:
            return None

    def _is_privileged(self) -> bool:
        role = self._current_role()
        return role is not None and ROLE_HIERARCHY[role] >= ROLE_HIERARCHY[Role.MANAGER]

    def _validate_poll_payload(self, req: CreatePostRequest) -> datetime.datetime:
        """Validate a poll create payload and return its (aware) expiry."""
        if not req.options or len(req.options) < 2:
            raise ErrorException(errors.news.INVALID_POLL, status_code=422)
        if (
            req.admin_visibility is None
            or req.member_visibility is None
            or req.member_display is None
        ):
            raise ErrorException(errors.news.INVALID_POLL, status_code=422)
        if req.expires_at is None:
            raise ErrorException(errors.news.INVALID_POLL, status_code=422)
        expires = _ensure_aware(req.expires_at)
        if expires <= _now():
            raise ErrorException(errors.news.INVALID_POLL, status_code=422)
        return expires

    @staticmethod
    def _build_options(
        options: list, post_id: int, internal_community_id: int
    ) -> list[PostPollModel]:
        return [
            PostPollModel(
                id_community=internal_community_id,
                id_post=post_id,
                option_value=o.option_value,
                display_order=o.display_order if o.display_order is not None else idx,
            )
            for idx, o in enumerate(options)
        ]

    async def _replace_options(self, post: PostModel, options: list) -> None:
        """Replace a poll's options — allowed only while no vote exists.

        Reassigns the relationship collection so delete-orphan removes the old
        options and the in-session ``post.options`` reflects the new set
        immediately (correct read-after-write within the request)."""
        if len(options) < 2:
            raise ErrorException(errors.news.INVALID_POLL, status_code=422)
        if await self.repository.count_votes_for_post(post.id) > 0:
            raise ErrorException(errors.news.OPTIONS_FROZEN, status_code=409)
        post.options = self._build_options(options, post.id, post.id_community)
        await self.local_session.flush()

    @staticmethod
    def _validate_selection(
        option_ids: list[int], post_type: PostType, options: list[PostPollModel]
    ) -> list[int]:
        selected = list(dict.fromkeys(option_ids))  # dedupe, preserve order
        valid_ids = {o.id for o in options}
        if any(oid not in valid_ids for oid in selected):
            raise ErrorException(errors.news.INVALID_VOTE, status_code=422)
        if post_type == PostType.POLL_SINGLE_CHOICE and len(selected) != 1:
            raise ErrorException(errors.news.INVALID_VOTE, status_code=422)
        return selected

    async def _voter_selection(self, post: PostModel) -> tuple[bool, list[int]]:
        voter_id = current_user_id.get()
        if not PostType(post.type).is_poll or not voter_id:
            return False, []
        votes = await self.repository.get_voter_votes(post.id, voter_id)
        option_ids = [v.id_post_poll for v in votes]
        return bool(option_ids), option_ids

    @staticmethod
    def _resolve_results_visibility(
        post: PostModel, *, privileged: bool, has_voted: bool, poll_ended: bool
    ) -> tuple[bool, ResultsMode | None]:
        """Apply the visibility matrix. Returns (visible, mode)."""
        if privileged:
            av = (
                AdminVisibility(post.admin_visibility)
                if post.admin_visibility is not None
                else AdminVisibility.AGGREGATE
            )
            return True, ResultsMode.FULL if av == AdminVisibility.FULL else ResultsMode.AGGREGATE

        mv = (
            MemberVisibility(post.member_visibility)
            if post.member_visibility is not None
            else MemberVisibility.NONE
        )
        if mv == MemberVisibility.NONE:
            return False, None

        md = (
            MemberDisplay(post.member_display)
            if post.member_display is not None
            else MemberDisplay.NEVER
        )
        timing_ok = (
            md == MemberDisplay.BEFORE_VOTE
            or (md == MemberDisplay.AFTER_VOTE and has_voted)
            or (md == MemberDisplay.WHEN_POLL_ENDS and poll_ended)
        )
        if not timing_ok:
            return False, None
        return True, ResultsMode.FULL if mv == MemberVisibility.FULL else ResultsMode.AGGREGATE

    async def _audit(self, entry: AuditLogInput) -> None:
        """Append an audit entry on the CRM session and commit it best-effort.

        The audit row lives in the CRM DB (separate transaction from the business
        write, which is already committed). A failure here must never surface to
        the caller — the business action has succeeded."""
        await self.audit_log_service.log(entry)
        try:
            await self.crm_session.commit()
        except Exception:
            logger.exception("news: audit commit failed", extra={"action": entry.action})

    async def _notify_post_created(
        self, post: PostModel, is_poll: bool, internal_community_id: int, author_id: str
    ) -> None:
        """Fan a "published" notification out to every community member but the author.

        Runs after the post is durably committed. Like ``_audit`` it owns a
        best-effort CRM commit and never lets a failure surface to the caller —
        the post has already succeeded, so a notification hiccup must not 500 it."""
        await self.notification_service.publish(
            type=(
                NotificationTypes.NEWS_POLL_PUBLISHED
                if is_poll
                else NotificationTypes.NEWS_POST_PUBLISHED
            ),
            data={"post_id": post.id},
            community_id=internal_community_id,
            exclude_author_auth_id=author_id,
        )
        try:
            await self.crm_session.commit()
        except Exception:
            logger.exception("news: notification commit failed", extra={"post_id": post.id})
