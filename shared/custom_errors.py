from core.errors.errors import Error


# ---------------------------------------------------------------------------
# Auth (no domain code — use xxx)
# ---------------------------------------------------------------------------
class _AuthErrors:
    UNAUTHORIZED = Error(code=1, key="ERRORS.AUTH.UNAUTHORIZED")
    FORBIDDEN = Error(code=2, key="ERRORS.AUTH.FORBIDDEN")
    RATE_LIMITED = Error(code=3, key="ERRORS.AUTH.RATE_LIMITED")
    AUTHORIZATION_MISSING = Error(code=4, key="ERRORS.AUTH.AUTHORIZATION_MISSING")


class _SubscriptionErrors:
    NOT_SUBSCRIBED = Error(code=1003, key="ERRORS.SUBSCRIPTION.NOT_SUBSCRIBED")


class _NewsErrors:
    GET_POSTS = Error(code=2300, key="ERRORS.NEWS.GET_POSTS")
    GET_POST = Error(code=2301, key="ERRORS.NEWS.GET_POST")
    POST_NOT_FOUND = Error(code=2302, key="ERRORS.NEWS.POST_NOT_FOUND")
    CREATE_POST = Error(code=2303, key="ERRORS.NEWS.CREATE_POST")
    UPDATE_POST = Error(code=2304, key="ERRORS.NEWS.UPDATE_POST")
    DELETE_POST = Error(code=2305, key="ERRORS.NEWS.DELETE_POST")
    # Poll payload is invalid: fewer than two options, a missing visibility
    # field, or an expiry that is not in the future.
    INVALID_POLL = Error(code=2306, key="ERRORS.NEWS.INVALID_POLL")
    # Voting (or vote-related action) was attempted on a plain post.
    NOT_A_POLL = Error(code=2307, key="ERRORS.NEWS.NOT_A_POLL")
    # The poll's expiry has passed; voting and vote editing are locked.
    POLL_EXPIRED = Error(code=2308, key="ERRORS.NEWS.POLL_EXPIRED")
    # Options cannot be edited once the first vote exists (renaming would
    # silently reassign cast votes).
    OPTIONS_FROZEN = Error(code=2309, key="ERRORS.NEWS.OPTIONS_FROZEN")
    # Submitted option ids don't belong to the poll, or the selection count is
    # invalid for the poll type (single-choice requires exactly one).
    INVALID_VOTE = Error(code=2310, key="ERRORS.NEWS.INVALID_VOTE")
    CAST_VOTE = Error(code=2311, key="ERRORS.NEWS.CAST_VOTE")
    GET_RESULTS = Error(code=2312, key="ERRORS.NEWS.GET_RESULTS")


class _Errors:
    auth = _AuthErrors()
    subscription = _SubscriptionErrors()
    news = _NewsErrors()


errors = _Errors()
