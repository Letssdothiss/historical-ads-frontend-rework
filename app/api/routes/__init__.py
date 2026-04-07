"""Routes module"""

from fastapi import APIRouter
from .search import router as search_router
from .statistics import router as stats_router
from .filters import router as filters_router
from .export import router as export_router
from .metadata import router as metadata_router
from .shares import router as shares_router

api_router = APIRouter()
api_router.include_router(search_router)
api_router.include_router(stats_router)
api_router.include_router(filters_router)
api_router.include_router(export_router)
api_router.include_router(metadata_router)
api_router.include_router(shares_router)

all = [
    "api_router",
    "search_router",
    "stats_router",
    "filters_router",
    "export_router",
    "metadata_router",
    "shares_router",
]
