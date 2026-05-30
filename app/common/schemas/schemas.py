"""Request/Response schemas"""

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ExportFormat(str, Enum):
    """Export format enum"""

    JSON = "json"
    CSV = "csv"
    XLSX = "xlsx"


class SearchQuery(BaseModel):
    """Search query parameters"""

    q: Optional[str] = Field(None, description="Free text search")
    offset: int = Field(0, ge=0, description="Pagination offset")
    limit: int = Field(10, ge=1, le=100, description="Number of results")
    published_before: Optional[str] = Field(None, description="Before date YYYY-MM-DD")
    published_after: Optional[str] = Field(None, description="After date YYYY-MM-DD")
    occupation: Optional[List[str]] = Field(None, description="Occupation IDs")
    occupation_group: Optional[List[str]] = Field(None, description="Occupation group IDs")
    occupation_field: Optional[List[str]] = Field(None, description="Occupation field IDs")
    municipality: Optional[List[str]] = Field(None, description="Municipality IDs")
    region: Optional[List[str]] = Field(None, description="Region IDs")
    country: Optional[List[str]] = Field(None, description="Country IDs")
    employment_type: Optional[List[str]] = Field(None, description="Employment type IDs")
    experience_required: Optional[bool] = Field(None, description="Experience required")


class ExportQuery(BaseModel):
    """Export query parameters"""

    search: SearchQuery = Field(default_factory=SearchQuery) # type: ignore[call-arg]
    format: ExportFormat = Field(ExportFormat.JSON, description="Export format")
    fields: Optional[List[str]] = Field(None, description="Fields to export")


class FieldMetadata(BaseModel):
    """Metadata about a single field"""

    field_name: str = Field(description="Field name")
    data_type: str = Field(description="Data type (string, date, number, etc)")
    completeness: float = Field(ge=0, le=100, description="Percentage of non-null values")
    total_records: int = Field(ge=0, description="Total records in database")
    filled_records: int = Field(ge=0, description="Records with non-null value")
    sample_values: List[Any] = Field(description="Sample values from the field")


class AdQualityMetadata(BaseModel):
    """Quality indicators for a specific ad"""

    ad_id: str = Field(description="Advertisement ID")
    completeness_score: float = Field(ge=0, le=100, description="Overall completeness percentage")
    missing_fields: List[str] = Field(description="List of empty/missing fields")
    quality_issues: List[str] = Field(default_factory=list, description="Known quality issues")
    data_structure: Dict[str, Any] = Field(description="Structure of the ad data")


class DatabaseMetadata(BaseModel):
    """Overall database quality metadata"""

    total_ads: int = Field(description="Total number of ads in database")
    date_range: Dict[str, str] = Field(description="Date range of ads (min_date, max_date)")
    field_metadata: List[FieldMetadata] = Field(description="Metadata for each field")
    average_completeness: float = Field(ge=0, le=100, description="Average field completeness")
    data_quality_summary: Dict[str, Any] = Field(description="Summary of data quality issues")
    last_updated: str = Field(description="Last database update timestamp")
