"""Response models"""

from datetime import datetime
from typing import Any, Dict, List

from pydantic import BaseModel, Field


class JobAd(BaseModel):
    """Job advertisement"""

    class Config:
        extra = "allow"


class SearchResult(BaseModel):
    """Search result"""

    class Config:
        extra = "allow"


class StatsResult(BaseModel):
    """Statistics result"""

    class Config:
        extra = "allow"


class FiltersResult(BaseModel):
    """Filters result"""

    occupations: List[Dict[str, Any]] = Field(default_factory=list)
    regions: List[Dict[str, Any]] = Field(default_factory=list)
    municipalities: List[Dict[str, Any]] = Field(default_factory=list)
    employment_types: List[Dict[str, Any]] = Field(default_factory=list)
    occupation_fields: List[Dict[str, Any]] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """Health check response"""

    status: str
    version: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ErrorResponse(BaseModel):
    """Error response"""

    error: str
    message: str
