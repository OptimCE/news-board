import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from shared.const import AdminVisibility, MemberDisplay, MemberVisibility, PostType

# ---------------------------------------------------------------------------
# Requests
# ---------------------------------------------------------------------------


class PollOptionInput(BaseModel):
    option_value: str = Field(..., min_length=1, max_length=2000)
    display_order: int | None = Field(
        default=None,
        description="Render order. Defaults to the option's position in the list.",
    )


class CreatePostRequest(BaseModel):
    """Create a plain post or a poll.

    For ``type == POST`` the poll fields are ignored. For a poll, ``options``
    (>= 2), the full visibility matrix, and a future ``expires_at`` are required —
    validated in the service layer.
    """

    type: PostType = Field(..., description="0=post, 1=poll single-choice, 2=poll multi-choice.")
    post: str = Field(..., min_length=1, description="Markdown source.")
    options: list[PollOptionInput] | None = Field(default=None, description="Poll options.")
    expires_at: datetime.datetime | None = Field(default=None, description="Poll vote deadline.")
    admin_visibility: AdminVisibility | None = None
    member_visibility: MemberVisibility | None = None
    member_display: MemberDisplay | None = None


class UpdatePostRequest(BaseModel):
    """Edit a post/poll (manager/admin).

    ``post`` text and the poll's visibility/expiry are editable any time;
    ``options`` may be replaced **only while no vote exists** (enforced in the
    service). All fields optional — only provided fields are applied.
    """

    post: str | None = Field(default=None, min_length=1)
    options: list[PollOptionInput] | None = None
    expires_at: datetime.datetime | None = None
    admin_visibility: AdminVisibility | None = None
    member_visibility: MemberVisibility | None = None
    member_display: MemberDisplay | None = None


class CastVoteRequest(BaseModel):
    option_ids: list[int] = Field(
        ...,
        description="Selected option ids. Exactly one for a single-choice poll; "
        "zero or more for a multiple-choice poll.",
    )


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------


class PollOptionOut(BaseModel):
    id: int
    option_value: str
    display_order: int


class PostListItem(BaseModel):
    id: int
    type: PostType
    author_id: str
    author_email: str | None
    body_html: str = Field(..., description="Rendered + sanitised HTML of the Markdown body.")
    created_at: datetime.datetime
    updated_at: datetime.datetime
    expires_at: datetime.datetime | None
    is_poll: bool
    poll_ended: bool
    option_count: int
    has_voted: bool


class PostDetail(BaseModel):
    id: int
    type: PostType
    author_id: str
    author_email: str | None
    post: str = Field(..., description="Markdown source.")
    body_html: str = Field(..., description="Rendered + sanitised HTML of the Markdown body.")
    created_at: datetime.datetime
    updated_at: datetime.datetime
    expires_at: datetime.datetime | None
    is_poll: bool
    poll_ended: bool
    options: list[PollOptionOut]
    has_voted: bool
    my_option_ids: list[int] = Field(..., description="Option ids the requester has selected.")
    admin_visibility: AdminVisibility | None
    member_visibility: MemberVisibility | None
    member_display: MemberDisplay | None


class CreatePostResponse(BaseModel):
    id: int


class ResultsMode(StrEnum):
    AGGREGATE = "aggregate"
    FULL = "full"


class VoterIdentity(BaseModel):
    voter_id: str
    email: str | None


class OptionTally(BaseModel):
    option_id: int
    option_value: str
    count: int
    voters: list[VoterIdentity] | None = Field(
        default=None,
        description="Per-voter identities; populated only under 'full' visibility.",
    )


class PollResults(BaseModel):
    """Visibility-enforced poll results.

    ``visible`` is False when the requester is not (yet) entitled to any results
    (e.g. member_visibility=none, or a member_display timing not met); the
    options/counts are then withheld entirely — the server is the boundary.
    """

    post_id: int
    poll_ended: bool
    visible: bool
    mode: ResultsMode | None = None
    total_voters: int | None = None
    options: list[OptionTally] | None = None
