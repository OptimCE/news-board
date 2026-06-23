from api.news.schemas import PollOptionOut, PostDetail, PostListItem
from shared.const import AdminVisibility, MemberDisplay, MemberVisibility, PostType
from shared.markdown import render_markdown
from shared.models.local_models import PostModel, PostPollModel


def to_poll_option_out(option: PostPollModel) -> PollOptionOut:
    return PollOptionOut(
        id=option.id,
        option_value=option.option_value,
        display_order=option.display_order,
    )


def to_post_list_item(
    post: PostModel,
    *,
    has_voted: bool,
    poll_ended: bool,
    option_count: int,
) -> PostListItem:
    post_type = PostType(post.type)
    return PostListItem(
        id=post.id,
        type=post_type,
        author_id=post.author_id,
        author_email=post.author_email,
        body_html=render_markdown(post.post),
        created_at=post.created_at,
        updated_at=post.updated_at,
        expires_at=post.expires_at,
        is_poll=post_type.is_poll,
        poll_ended=poll_ended,
        option_count=option_count,
        has_voted=has_voted,
    )


def to_post_detail(
    post: PostModel,
    options: list[PostPollModel],
    *,
    has_voted: bool,
    poll_ended: bool,
    my_option_ids: list[int],
) -> PostDetail:
    post_type = PostType(post.type)
    return PostDetail(
        id=post.id,
        type=post_type,
        author_id=post.author_id,
        author_email=post.author_email,
        post=post.post,
        body_html=render_markdown(post.post),
        created_at=post.created_at,
        updated_at=post.updated_at,
        expires_at=post.expires_at,
        is_poll=post_type.is_poll,
        poll_ended=poll_ended,
        options=[to_poll_option_out(o) for o in options],
        has_voted=has_voted,
        my_option_ids=my_option_ids,
        admin_visibility=(
            AdminVisibility(post.admin_visibility) if post.admin_visibility is not None else None
        ),
        member_visibility=(
            MemberVisibility(post.member_visibility) if post.member_visibility is not None else None
        ),
        member_display=(
            MemberDisplay(post.member_display) if post.member_display is not None else None
        ),
    )
