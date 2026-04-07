"""Statistics routes"""
from typing import Dict, Any
from fastapi import APIRouter, Depends, Request

from app.services import get_api, HistoricalAdsAPI

router = APIRouter(tags=["Statistics"])


@router.get("/stats")
async def get_stats(
    request: Request,
    api: HistoricalAdsAPI = Depends(get_api),
) -> Dict[str, Any]:
    """Get statistics about job ads"""
    params: Dict[str, Any] = {}
    for key, value in request.query_params.multi_items():
        normalized_key = key.replace("-", "_")
        if normalized_key in params:
            existing = params[normalized_key]
            if isinstance(existing, list):
                existing.append(value)
            else:
                params[normalized_key] = [existing, value]
        else:
            params[normalized_key] = value

    return await api.get_stats(**params)
