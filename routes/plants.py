from typing import Optional
from fastapi import APIRouter, Query
from helpers import _build_response_data, _config_payload
from state import get_state

from services.scheduler import hydrate_state_from_cache

router = APIRouter()

@router.get("/api/plants")
def get_plants(source: Optional[str] = Query(None, description="Filter by source platform")):
    state = get_state()
    if not state.classified:
        hydrate_state_from_cache()
        state = get_state()

    if not state.classified:
        return {"data": {}, "counts": {}, "config": _config_payload()}

    data, counts = _build_response_data()

    if source:
        src_clean = source.lower().strip()
        filtered_data = {}
        filtered_counts = {}
        for status, items in data.items():
            filtered_items = [it for it in items if it.get("source", "").lower() == src_clean]
            filtered_data[status] = filtered_items
            filtered_counts[status] = len(filtered_items)
        return {"data": filtered_data, "counts": filtered_counts, "config": _config_payload()}

    return {"data": data, "counts": counts, "config": _config_payload()}
