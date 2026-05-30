"""API dependencies"""

from app.common.utils.config import settings
from app.v1.services.data_processor import DataProcessor, get_processor
from app.v1.services.external_api import HistoricalAdsAPI, get_api


def get_settings():
    """Get settings"""
    return settings
