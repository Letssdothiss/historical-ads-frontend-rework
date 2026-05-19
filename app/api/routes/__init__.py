"""Routes module"""

from fastapi import APIRouter

from .export import router as export_router
from .filters import router as filters_router
from .metadata import router as metadata_router
from .related_occupations import router as related_occupations_router
from .search import router as search_router
from .saved_searches import router as saved_searches_router
from .shared_searches import router as shared_searches_router
from .shares import router as shares_router
from .statistics import router as stats_router

api_router = APIRouter()
api_router.include_router(search_router)
api_router.include_router(stats_router)
api_router.include_router(filters_router)
api_router.include_router(export_router)
api_router.include_router(metadata_router)
api_router.include_router(related_occupations_router)
api_router.include_router(saved_searches_router)
api_router.include_router(shared_searches_router)
api_router.include_router(shares_router)

__all__ = [
    "api_router",
    "search_router",
    "stats_router",
    "filters_router",
    "export_router",
    "metadata_router",
    "related_occupations_router",
    "saved_searches_router",
    "shared_searches_router",
    "shares_router",
]
