from utils import haversine_km, get_distance_zone, get_proximity_bonus, clean_text, extract_json_from_text

def test_haversine_paris_orly():
    dist = haversine_km(48.8566, 2.3522, 48.7262, 2.3652)
    assert 13 < dist < 16

def test_haversine_same_point():
    assert haversine_km(48.0, 2.0, 48.0, 2.0) == 0.0

def test_distance_zone_prime():
    assert get_distance_zone(10) == "PRIME"

def test_distance_zone_near():
    assert get_distance_zone(25) == "NEAR"

def test_distance_zone_far():
    assert get_distance_zone(35) == "FAR"

def test_distance_zone_remote():
    assert get_distance_zone(100) == "REMOTE"

def test_clean_text():
    assert clean_text("  Hello   World  ") == "Hello World"
    assert clean_text(None) == ""
    assert clean_text("") == ""

def test_extract_json_simple():
    text = 'Some preamble {"key": "value"} trailing'
    result = extract_json_from_text(text)
    assert result == {"key": "value"}

def test_extract_json_array():
    text = 'blah [{"a": 1}] blah'
    result = extract_json_from_text(text)
    assert result == [{"a": 1}]

def test_extract_json_none_on_failure():
    result = extract_json_from_text("no json here")
    assert result is None


def test_proximity_bonus_prime():
    assert get_proximity_bonus(10) == 15


def test_proximity_bonus_near():
    assert get_proximity_bonus(25) == 8


def test_proximity_bonus_remote():
    assert get_proximity_bonus(100) == 0


def test_extract_json_object_before_array():
    """Text with { before [ → picks the object."""
    text = 'prefix {"key": [1,2]} suffix'
    result = extract_json_from_text(text)
    assert result == {"key": [1, 2]}


def test_extract_json_balanced_but_invalid():
    """Balanced brackets but invalid JSON inside → returns None."""
    text = "prefix {not: valid: json} suffix"
    result = extract_json_from_text(text)
    assert result is None


def test_extract_json_array_only_no_braces():
    """Text with [ but no { → picks array (obj_idx == -1 branch)."""
    text = "result: [1, 2, 3] done"
    result = extract_json_from_text(text)
    assert result == [1, 2, 3]


def test_distance_zone_exact_prime_boundary():
    """20 km = exactly PRIME max → still PRIME (<=)."""
    assert get_distance_zone(20) == "PRIME"


def test_distance_zone_exact_near_boundary():
    """30 km = exactly NEAR max → still NEAR (<=)."""
    assert get_distance_zone(30) == "NEAR"


def test_distance_zone_exact_far_boundary():
    """40 km = exactly FAR max → still FAR (<=)."""
    assert get_distance_zone(40) == "FAR"


def test_distance_zone_just_over_prime():
    """20.1 km = just over PRIME → NEAR."""
    assert get_distance_zone(20.1) == "NEAR"
