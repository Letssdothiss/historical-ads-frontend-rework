"""Models module"""

from .responses import (
    ErrorResponse,
    FiltersResult,
    HealthResponse,
    JobAd,
    SearchResult,
    StatsResult,
)

__all__ = [
    "JobAd",
    "SearchResult",
    "StatsResult",
    "FiltersResult",
    "HealthResponse",
    "ErrorResponse",
]
