"""Metadata routes for database and ad quality information"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends

from app.services import DataProcessor, HistoricalAdsAPI, get_api, get_processor

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Metadata"])


@router.get("/metadata", response_model=dict)
async def get_database_metadata(
    api: HistoricalAdsAPI = Depends(get_api),
    processor: DataProcessor = Depends(get_processor),
) -> Dict[str, Any]:
    """Get overall database quality metadata and statistics

    Returns information about:
    - Total number of ads
    - Date range of data
    - Field-level completeness statistics
    - Average data quality score
    - Quality distribution summary
    """
    try:
        # Get a sample of ads and stats for metadata calculation
        result = await api.search(limit=100, offset=0)
        ads = result.get("hits", [])
        total_count = result.get("result_count", len(ads))

        metadata = processor.calculate_database_metadata(ads, total_count)
        return metadata
    except Exception as e:
        logger.error(f"Error calculating database metadata: {e}")
        return {"error": "Failed to calculate metadata", "details": str(e)}


@router.get("/metadata/ad/{ad_id}", response_model=dict)
async def get_ad_quality_metadata(
    ad_id: str,
    api: HistoricalAdsAPI = Depends(get_api),
    processor: DataProcessor = Depends(get_processor),
) -> Dict[str, Any]:
    """Get quality metadata for a specific advertisement

    Returns:
    - Completeness score (percentage of non-empty fields)
    - List of missing/empty fields
    - Data structure information
    - Quality issues (if any)
    """
    try:
        ad = await api.get_ad(ad_id)
        quality_metadata = processor.calculate_ad_quality(ad)
        return quality_metadata
    except Exception as e:
        logger.error(f"Error calculating ad quality metadata for {ad_id}: {e}")
        return {
            "error": "Failed to calculate ad metadata",
            "details": str(e),
            "ad_id": ad_id,
        }
