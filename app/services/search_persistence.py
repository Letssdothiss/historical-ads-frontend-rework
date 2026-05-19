"""Persistence helpers for saved and shared searches."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4


def _storage_dir() -> Path:
    override = os.getenv("HISTORICAL_ADS_STORAGE_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "logs"


def _collection_path(collection_name: str) -> Path:
    return _storage_dir() / collection_name


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return uuid4().hex[:12]


def load_collection(collection_name: str) -> List[Dict[str, Any]]:
    path = _collection_path(collection_name)
    if not path.exists():
        return []

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        items = payload.get("items")
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]

    return []


def save_collection(collection_name: str, items: List[Dict[str, Any]]) -> None:
    storage_dir = _storage_dir()
    storage_dir.mkdir(parents=True, exist_ok=True)

    path = _collection_path(collection_name)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(
        json.dumps(items, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    tmp_path.replace(path)


def append_record(collection_name: str, record: Dict[str, Any]) -> Dict[str, Any]:
    items = load_collection(collection_name)
    items.insert(0, record)
    save_collection(collection_name, items)
    return record


def get_record(
    collection_name: str, record_id: str, id_field: str = "id"
) -> Optional[Dict[str, Any]]:
    for item in load_collection(collection_name):
        if item.get(id_field) == record_id:
            return item
    return None
