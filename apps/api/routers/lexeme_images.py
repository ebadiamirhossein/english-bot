"""`GET /lexeme-images/{id}.{ext}` — a picturable word's picture. W13d.

**Served from our API, never hot-linked**, and that is the privacy decision as
much as the offline one: a learner's browser asks this server, so Wikimedia
never sees a learner's address and no third party joins the list of processors
(#364's family). The bytes are the operator-approved thumbnail stored by
`core.images.bank --load --apply`.

Signed-in only, like `GET /items/{id}/audio`: the pictures are not learner
content, but this API is not a public image host.

**`immutable` for a year, and that is safe by construction:** a replaced
picture gets a NEW id (`lexeme_images.replace` deletes and inserts), so a URL
never changes what it names.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response

from apps.api.deps import rate_limit, require_current_user
from core.images import EXTENSION
from core.services import lexeme_images
from core.services.auth import AuthenticatedUser

router = APIRouter(prefix="/lexeme-images", tags=["cards"])

_CACHE = "private, max-age=31536000, immutable"


@router.get(
    "/{image_id}.{ext}",
    response_class=Response,
    responses={200: {"content": {"image/jpeg": {}, "image/png": {}}}},
    dependencies=[
        Depends(rate_limit("lexeme_images", per_client=600, overall=2400, window_seconds=3600))
    ],
)
def picture(
    image_id: int,
    ext: str,
    session: AuthenticatedUser = Depends(require_current_user),
) -> Response:
    """The stored bytes, or 404 — including for a right id with the wrong
    extension, so a URL names exactly one representation."""
    found = lexeme_images.image_file(image_id)
    if found is None or EXTENSION[found[1]] != ext:
        raise HTTPException(status_code=404, detail="not_found")
    data, mime = found
    return Response(content=data, media_type=mime, headers={"Cache-Control": _CACHE})
