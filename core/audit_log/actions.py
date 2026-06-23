"""Audit log action codes.

Action codes follow the ``domain.entity.verb`` convention used by
``crm-backend`` (e.g. ``crm.allocation_key.created``). They are stored as
``VARCHAR(128)`` and the ``AuditAction`` type stays open-ended so call sites
can introduce new codes without round-tripping this module.
"""

from typing import Final

AuditAction = str


class AuditActions:
    """Known action codes emitted by ``optimce-news-board``."""

    POST_CREATED: Final[AuditAction] = "news.post.created"
    POST_UPDATED: Final[AuditAction] = "news.post.updated"
    POST_DELETED: Final[AuditAction] = "news.post.deleted"
    VOTE_CAST: Final[AuditAction] = "news.vote.cast"
    VOTE_RETRACTED: Final[AuditAction] = "news.vote.retracted"
