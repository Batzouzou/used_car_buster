from config import (
    SEARCH_CRITERIA, DISTANCE_ZONES, ORLY_LAT, ORLY_LON,
    PLATFORMS, CACHE_FRESHNESS_HOURS, SCORING_WEIGHTS,
    LLM_MAX_RETRIES, LM_STUDIO_MODEL
)

def test_search_criteria_locked():
    assert SEARCH_CRITERIA["make"] == "Toyota"
    assert SEARCH_CRITERIA["model"] == "iQ"
    assert SEARCH_CRITERIA["transmission"] == "automatic"
    assert SEARCH_CRITERIA["max_price"] == 5000
    assert SEARCH_CRITERIA["max_mileage_km"] == 150000
    assert SEARCH_CRITERIA["min_year"] == 2009

def test_orly_coordinates():
    assert abs(ORLY_LAT - 48.7262) < 0.001
    assert abs(ORLY_LON - 2.3652) < 0.001

def test_distance_zones():
    assert DISTANCE_ZONES["PRIME"]["max_km"] == 20
    assert DISTANCE_ZONES["PRIME"]["bonus"] == 15
    assert DISTANCE_ZONES["NEAR"]["max_km"] == 30
    assert DISTANCE_ZONES["NEAR"]["bonus"] == 8
    assert DISTANCE_ZONES["FAR"]["max_km"] == 40
    assert DISTANCE_ZONES["FAR"]["bonus"] == 3
    assert DISTANCE_ZONES["REMOTE"]["bonus"] == 0

def test_scoring_weights_sum_to_100():
    total = sum(SCORING_WEIGHTS.values())
    assert total == 100

def test_cache_freshness():
    assert CACHE_FRESHNESS_HOURS == 4

def test_lm_studio_model_configurable():
    assert isinstance(LM_STUDIO_MODEL, str)
    assert len(LM_STUDIO_MODEL) > 0

def test_platforms_includes_all_four():
    assert "leboncoin" in PLATFORMS
    assert "lacentrale" in PLATFORMS
    assert "leparking" in PLATFORMS
    assert "autoscout24" in PLATFORMS

def test_telegram_config_exists():
    from config import TELEGRAM_BOT_TOKEN, TELEGRAM_FRIEND_CHAT_ID, TELEGRAM_JEROME_CHAT_ID
    assert isinstance(TELEGRAM_BOT_TOKEN, str)
    assert isinstance(TELEGRAM_FRIEND_CHAT_ID, str)
    assert isinstance(TELEGRAM_JEROME_CHAT_ID, str)

def test_scheduler_config():
    from config import DEFAULT_INTERVAL_HOURS, MIN_INTERVAL_HOURS, MAX_INTERVAL_HOURS
    assert DEFAULT_INTERVAL_HOURS == 4
    assert MIN_INTERVAL_HOURS == 1
    assert MAX_INTERVAL_HOURS == 168
