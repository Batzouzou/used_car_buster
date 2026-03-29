"""Utility functions: distance, geocoding, text cleanup, JSON extraction."""
import json
import math
import re
from config import DISTANCE_ZONES


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in km between two GPS points."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def get_distance_zone(distance_km: float) -> str:
    """Return zone name based on distance from Orly."""
    for zone_name in ["PRIME", "NEAR", "FAR"]:
        if distance_km <= DISTANCE_ZONES[zone_name]["max_km"]:
            return zone_name
    return "REMOTE"


def get_proximity_bonus(distance_km: float) -> int:
    """Return scoring bonus for distance zone."""
    zone = get_distance_zone(distance_km)
    return DISTANCE_ZONES[zone]["bonus"]


def clean_text(text: str | None) -> str:
    """Normalize whitespace, strip."""
    if not text:
        return ""
    return re.sub(r'\s+', ' ', text).strip()


def extract_json_from_text(text: str):
    """Extract first JSON object or array from LLM text output."""
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    # Strip markdown code fences (```json ... ``` or ``` ... ```)
    fence_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?\s*```', text, re.DOTALL)
    if fence_match:
        try:
            return json.loads(fence_match.group(1))
        except (json.JSONDecodeError, TypeError):
            pass

    # Find earliest occurrence of '[' or '{' in text
    arr_idx = text.find('[')
    obj_idx = text.find('{')

    # Determine which comes first
    if arr_idx == -1 and obj_idx == -1:
        return None
    elif arr_idx == -1:
        start = obj_idx
        start_char, end_char = '{', '}'
    elif obj_idx == -1:
        start = arr_idx
        start_char, end_char = '[', ']'
    else:
        if arr_idx < obj_idx:
            start = arr_idx
            start_char, end_char = '[', ']'
        else:
            start = obj_idx
            start_char, end_char = '{', '}'

    depth = 0
    for i in range(start, len(text)):
        if text[i] == start_char:
            depth += 1
        elif text[i] == end_char:
            depth -= 1
        if depth == 0:
            try:
                return json.loads(text[start:i + 1])
            except json.JSONDecodeError:
                break
    return None
