from enum import IntEnum, StrEnum


class PostType(IntEnum):
    """Discriminates a board entry: a plain post or a poll.

    Stored in ``post.type``. Poll behaviour (options, voting, the visibility
    matrix, expiry) applies only to the two poll variants.
    """

    POST = 0
    POLL_SINGLE_CHOICE = 1
    POLL_MULTIPLE_CHOICE = 2

    @property
    def is_poll(self) -> bool:
        return self in (PostType.POLL_SINGLE_CHOICE, PostType.POLL_MULTIPLE_CHOICE)


class AdminVisibility(IntEnum):
    """What a manager/admin is shown on a poll's results."""

    AGGREGATE = 0  # counts only
    FULL = 1  # per-option voter identities


class MemberVisibility(IntEnum):
    """What a member is *allowed* to see on a poll's results."""

    NONE = 0  # never any results
    AGGREGATE = 1  # counts only
    FULL = 2  # per-voter identities


class MemberDisplay(IntEnum):
    """*When* a member may see whatever ``MemberVisibility`` grants."""

    NEVER = 0
    BEFORE_VOTE = 1  # always
    AFTER_VOTE = 2  # only once the member has voted
    WHEN_POLL_ENDS = 3  # only once the poll has expired


class FeatureName(StrEnum):
    """Feature key matched against ``community_subscription.feature`` to gate the
    annex per community (see ``require_feature``)."""

    NEWS = "news"
