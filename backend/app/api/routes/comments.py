"""Comment endpoints (T-CM-0; design.md §6, CM-1 through CM-9).

A sub-resource of a service request, so every route here answers two visibility
questions rather than one:

* **May the caller see the parent request at all?** Delegated to
  ``get_visible_parent_request`` — a comment is visible exactly when its parent
  is (CM-4, CM-9), and a 404 here is byte-identical to SR-12's because it comes
  from the same place.
* **Which of that request's comments may they see?** CM-2: a `user`-role caller
  never receives an internal one. That is a ``WHERE`` clause, on the page *and*
  on the count — a comment excluded from the items but counted in ``total``
  still tells the caller it exists.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import Pagination, get_current_user, is_admin, pagination_params
from app.api.errors import ForbiddenError
from app.api.schemas.comment import CommentCreate, CommentOut
from app.api.schemas.common import Page
from app.api.visibility import get_visible_parent_request
from app.database import get_db
from app.db.models import Comment, ServiceRequest, User

# The `/api/v1` half of the path is applied at mount time in `create_app()`.
# `{request_id}` is the name `get_visible_parent_request` reads, so the prefix
# and the dependency have to agree on it.
router = APIRouter(
    prefix="/service-requests/{request_id}/comments", tags=["comments"]
)

INTERNAL_COMMENT_MESSAGE = (
    "Only an administrator may mark a comment as internal."
)


def _audience_conditions(user: User) -> list:
    """CM-2 / CM-3 as a ``WHERE`` clause: who may see an internal comment.

    Returned as conditions rather than applied to a statement so the item query
    and the count get the identical predicate. Filtering internals out after the
    fetch would be worse than it looks: design.md §6 calls this a trust
    boundary, and a row that reached the response handler has already been
    serialised into memory next to the payload it was excluded from — one
    logging statement or one error message away from leaving the building.
    """
    if is_admin(user):
        return []
    return [Comment.is_internal.is_(False)]


@router.get("", response_model=Page[CommentOut])
def list_comments(
    pagination: Pagination = Depends(pagination_params),
    parent: ServiceRequest = Depends(get_visible_parent_request),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Page[CommentOut]:
    """A page of this request's comments the caller may see (CM-1 to CM-4).

    ``user`` is declared alongside ``parent`` even though the parent dependency
    resolves it too — FastAPI caches a dependency per request, so this is one
    lookup, not two, and the alternative is reading the caller off the parent
    object, which it is not.
    """
    conditions = [
        Comment.service_request_id == parent.id,
        *_audience_conditions(user),
    ]

    total = db.execute(
        select(func.count()).select_from(Comment).where(*conditions)
    ).scalar_one()

    rows = (
        db.execute(
            select(Comment)
            # `author` is embedded on every item (design.md §6), so lazy-loading
            # it costs 1 + n queries for a page of n.
            .options(joinedload(Comment.author))
            .where(*conditions)
            # CM-1's order, with `id` breaking ties. The tiebreaker is not
            # decoration: `now()` is transaction-scoped in Postgres, so comments
            # written by one request share a `created_at` exactly, and
            # equal-keyed rows come back in whatever order the planner likes —
            # which under paging means a row can appear on two pages or on none.
            .order_by(Comment.created_at.asc(), Comment.id.asc())
            .offset(pagination.offset)
            .limit(pagination.page_size)
        )
        .scalars()
        .all()
    )

    return Page[CommentOut](
        items=[CommentOut.model_validate(row) for row in rows],
        total=total,
        page=pagination.page,
        # The clamped value, not what was asked for (XC-11).
        page_size=pagination.page_size,
    )


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CommentOut)
def create_comment(
    payload: CommentCreate,
    parent: ServiceRequest = Depends(get_visible_parent_request),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CommentOut:
    """Post a comment on a request the caller may see (CM-5 to CM-9).

    ``author_id`` is the authenticated user and is never read from the body
    (XC-8) — the schema has no field for it, so a body supplying one creates
    exactly the same row as one that doesn't.
    """
    # CM-7, and the locked decision behind it (design.md §6, decision 3): a
    # non-admin asking for an internal comment is refused, not quietly given a
    # public one. Coercing to `false` would leave them believing they had
    # written a note their requestor cannot read, which is the more damaging of
    # the two failures by some distance.
    if payload.is_internal and not is_admin(user):
        raise ForbiddenError(INTERNAL_COMMENT_MESSAGE)

    comment = Comment(
        service_request_id=parent.id,
        author_id=user.id,
        body=payload.body,
        is_internal=payload.is_internal,
    )
    db.add(comment)
    # Flushed before the commit so the server-generated id is readable without
    # depending on what the session expires on commit.
    db.flush()
    new_id = comment.id
    db.commit()

    # Re-read through the same eager-loading path the list route uses, so the
    # 201 body is assembled identically to the one a follow-up GET returns —
    # and so `author` is a join rather than a lazy load after the commit
    # expired it.
    created = db.execute(
        select(Comment).options(joinedload(Comment.author)).where(Comment.id == new_id)
    ).scalar_one()
    return CommentOut.model_validate(created)
