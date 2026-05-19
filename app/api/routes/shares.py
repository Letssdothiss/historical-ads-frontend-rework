"""Share routes for creating a reusable search URL."""

from fastapi import APIRouter, Request

from app.utils.config import settings

router = APIRouter(tags=["Shares"])


@router.get("/share-url")
async def get_share_url(request: Request) -> dict[str, str]:
    """Return a shareable search URL based on the current query string."""
    query_string = request.url.query
    base_url = f"{settings.API_PREFIX}/search"

    if query_string:
        return {"share_url": f"{base_url}?{query_string}"}

    return {"share_url": base_url}
