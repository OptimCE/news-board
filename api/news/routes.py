from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.news.schemas import (
    CastVoteRequest,
    CreatePostRequest,
    CreatePostResponse,
    PollResults,
    PostDetail,
    PostListItem,
    UpdatePostRequest,
)
from api.news.service import NewsService
from core.api_response import ApiResponse, ApiResponsePaginated
from core.context_vars import current_internal_community_id, current_user_id
from core.database.database import get_crm_session, get_local_session
from core.errors.errors import ErrorException
from core.errors.with_default_error import with_default_error
from core.security.community_scope import resolve_internal_community
from core.security.dependencies import require_feature, require_min_role
from core.security.user_context import Role
from shared.const import FeatureName
from shared.custom_errors import errors

# Mounted at `/posts`; the KrakenD gateway prepends the public `/news` prefix, so
# public paths are /news/posts, /news/posts/{id}, /news/posts/{id}/votes,
# /news/posts/{id}/results. Every route is community-scoped and gated on an active
# News subscription; writes additionally require manager/admin.
news_routes = APIRouter(
    dependencies=[
        Depends(resolve_internal_community),
        Depends(require_feature(FeatureName.NEWS)),
    ]
)

_manager_only = [Depends(require_min_role(Role.MANAGER))]


# POST (/posts) : Create a post or a poll. Manager/admin only.
@news_routes.post("", response_model=ApiResponse[CreatePostResponse], dependencies=_manager_only)
@with_default_error(default_error=errors.news.CREATE_POST)
async def create_post(
    body: CreatePostRequest,
    local_session: Annotated[AsyncSession, Depends(get_local_session)],
    crm_session: Annotated[AsyncSession, Depends(get_crm_session)],
):
    internal_community_id = current_internal_community_id.get()
    author_id = current_user_id.get()
    if internal_community_id is None or not author_id:
        raise ErrorException(error=errors.auth.UNAUTHORIZED, status_code=401)
    service = NewsService(local_session, crm_session)
    data = await service.create_post(body, internal_community_id, author_id)
    return ApiResponse[CreatePostResponse](data=data)


# GET (/posts) : Paginated board, newest first. Any member.
@news_routes.get("", response_model=ApiResponsePaginated[list[PostListItem]])
@with_default_error(default_error=errors.news.GET_POSTS)
async def list_posts(
    local_session: Annotated[AsyncSession, Depends(get_local_session)],
    crm_session: Annotated[AsyncSession, Depends(get_crm_session)],
    page: Annotated[int, Query(ge=1, description="Page number.")] = 1,
    page_size: Annotated[int, Query(ge=1, le=100, description="Page size.")] = 20,
):
    service = NewsService(local_session, crm_session)
    data, pagination = await service.list_posts(page, page_size)
    return ApiResponsePaginated[list[PostListItem]](data=data, pagination=pagination)


# GET (/posts/{id}) : Single post, rendered body + poll state. Any member.
@news_routes.get("/{post_id}", response_model=ApiResponse[PostDetail])
@with_default_error(default_error=errors.news.GET_POST)
async def get_post(
    post_id: int,
    local_session: Annotated[AsyncSession, Depends(get_local_session)],
    crm_session: Annotated[AsyncSession, Depends(get_crm_session)],
):
    service = NewsService(local_session, crm_session)
    data = await service.get_post(post_id)
    return ApiResponse[PostDetail](data=data)


# PATCH (/posts/{id}) : Edit text/visibility/expiry; options only if no votes.
@news_routes.patch("/{post_id}", response_model=ApiResponse[PostDetail], dependencies=_manager_only)
@with_default_error(default_error=errors.news.UPDATE_POST)
async def update_post(
    post_id: int,
    body: UpdatePostRequest,
    local_session: Annotated[AsyncSession, Depends(get_local_session)],
    crm_session: Annotated[AsyncSession, Depends(get_crm_session)],
):
    service = NewsService(local_session, crm_session)
    data = await service.update_post(post_id, body)
    return ApiResponse[PostDetail](data=data)


# DELETE (/posts/{id}) : Delete a post/poll (cascades options + votes).
@news_routes.delete("/{post_id}", response_model=ApiResponse[str], dependencies=_manager_only)
@with_default_error(default_error=errors.news.DELETE_POST)
async def delete_post(
    post_id: int,
    local_session: Annotated[AsyncSession, Depends(get_local_session)],
    crm_session: Annotated[AsyncSession, Depends(get_crm_session)],
):
    service = NewsService(local_session, crm_session)
    await service.delete_post(post_id)
    return ApiResponse[str](data="success")


# POST (/posts/{id}/votes) : Cast or update a vote. Any member, until expiry.
@news_routes.post("/{post_id}/votes", response_model=ApiResponse[str])
@with_default_error(default_error=errors.news.CAST_VOTE)
async def cast_vote(
    post_id: int,
    body: CastVoteRequest,
    local_session: Annotated[AsyncSession, Depends(get_local_session)],
    crm_session: Annotated[AsyncSession, Depends(get_crm_session)],
):
    service = NewsService(local_session, crm_session)
    await service.cast_vote(post_id, body.option_ids)
    return ApiResponse[str](data="success")


# DELETE (/posts/{id}/votes) : Retract the requester's vote, until expiry.
@news_routes.delete("/{post_id}/votes", response_model=ApiResponse[str])
@with_default_error(default_error=errors.news.CAST_VOTE)
async def retract_vote(
    post_id: int,
    local_session: Annotated[AsyncSession, Depends(get_local_session)],
    crm_session: Annotated[AsyncSession, Depends(get_crm_session)],
):
    service = NewsService(local_session, crm_session)
    await service.retract_vote(post_id)
    return ApiResponse[str](data="success")


# GET (/posts/{id}/results) : Visibility-enforced poll results. Member/admin.
@news_routes.get("/{post_id}/results", response_model=ApiResponse[PollResults])
@with_default_error(default_error=errors.news.GET_RESULTS)
async def get_results(
    post_id: int,
    local_session: Annotated[AsyncSession, Depends(get_local_session)],
    crm_session: Annotated[AsyncSession, Depends(get_crm_session)],
):
    service = NewsService(local_session, crm_session)
    data = await service.get_results(post_id)
    return ApiResponse[PollResults](data=data)
