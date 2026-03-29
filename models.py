"""Pydantic v2 data models for the pipeline."""
from __future__ import annotations
from pydantic import BaseModel, Field, field_validator
from typing import Optional


class RawListing(BaseModel):
    """Raw listing scraped from a platform."""
    id: str
    platform: str
    title: str
    price: int = Field(ge=0)
    year: int = Field(ge=2000, le=2030)
    mileage_km: Optional[int] = Field(default=None, ge=0)
    transmission: Optional[str] = None
    fuel: Optional[str] = None
    city: Optional[str] = None
    department: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    seller_type: str = "unknown"
    url: str
    description: Optional[str] = None
    images: list[str] = Field(default_factory=list)
    scraped_at: str


class ScoreBreakdown(BaseModel):
    """Breakdown of the 100-point scoring rubric."""
    price: int = Field(ge=0, le=30)
    mileage: int = Field(ge=0, le=20)
    year: int = Field(ge=0, le=15)
    proximity: int = Field(ge=0, le=15)
    condition: int = Field(ge=-10, le=10)
    transmission: int = Field(ge=-1, le=10)

    @field_validator("condition", mode="before")
    @classmethod
    def cap_condition(cls, v: int) -> int:
        return min(v, 10)


class ScoredListing(RawListing):
    """Listing with analyst score."""
    score: int = Field(ge=-1, le=100)
    score_breakdown: ScoreBreakdown
    excluded: bool = False
    exclusion_reason: Optional[str] = None
    red_flags: list[str] = Field(default_factory=list)
    highlights: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    summary_fr: str = ""


class PricedListing(ScoredListing):
    """Listing with pricing and negotiation data."""
    market_estimate_low: int = Field(ge=0)
    market_estimate_high: int = Field(ge=0)
    opening_offer: int = Field(ge=0)
    max_acceptable: int = Field(ge=0)
    anchors: list[str] = Field(default_factory=list)
    message_digital: str = ""
    message_oral_points: list[str] = Field(default_factory=list)
