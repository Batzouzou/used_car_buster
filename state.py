"""Pipeline state persistence."""
import json
from datetime import datetime, timezone
from pathlib import Path
from pydantic import BaseModel, Field
from typing import Optional


class PipelineState(BaseModel):
    """Tracks pipeline progress. Saved to JSON after every supervisor action."""
    step: str = "init"
    last_scrape_at: Optional[str] = None
    last_scrape_platforms: list[str] = Field(default_factory=list)
    raw_listing_count: int = 0
    analysis_status: str = "pending"
    shortlist_pro_count: int = 0
    shortlist_part_count: int = 0
    approved_ids: list[str] = Field(default_factory=list)
    pricing_status: str = "pending"

    def is_data_fresh(self, max_hours: int = 4) -> bool:
        if not self.last_scrape_at:
            return False
        try:
            scrape_time = datetime.fromisoformat(self.last_scrape_at)
            now = datetime.now(timezone.utc)
            return (now - scrape_time).total_seconds() < max_hours * 3600
        except (ValueError, TypeError):
            return False


def load_state(path: str) -> PipelineState:
    """Load state from JSON file, or return default if missing."""
    p = Path(path)
    if not p.exists():
        return PipelineState()
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return PipelineState.model_validate(data)
    except (json.JSONDecodeError, Exception):
        return PipelineState()


def save_state(state: PipelineState, path: str) -> None:
    """Save state to JSON file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(state.model_dump_json(indent=2), encoding="utf-8")
