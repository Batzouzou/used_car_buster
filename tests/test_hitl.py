from datetime import datetime, timezone
from unittest.mock import patch
from models import ScoredListing, ScoreBreakdown
from hitl import format_listing_line, format_shortlist_display, parse_hitl_command, run_hitl_review, _parse_numbers

def _make_scored(id="lbc_1", score=78, seller_type="pro", **kw):
    defaults = dict(
        platform="leboncoin", title="Toyota iQ 1.33 CVT",
        price=3200, year=2011, mileage_km=78000, transmission="auto",
        city="Vitry", lat=48.787, lon=2.392, url="http://x",
        scraped_at=datetime.now(timezone.utc).isoformat(),
        score_breakdown=ScoreBreakdown(price=25, mileage=15, year=10, proximity=8, condition=10, transmission=10),
        excluded=False, red_flags=[], highlights=["CT OK"], concerns=[], summary_fr="OK",
    )
    defaults.update(kw)
    return ScoredListing(id=id, seller_type=seller_type, score=score, **defaults)

def test_format_listing_line():
    s = _make_scored()
    line = format_listing_line(s, 1, distance_km=8.5)
    assert "#1" in line
    assert "78" in line
    assert "3,200" in line or "3200" in line
    assert "Vitry" in line

def test_format_shortlist_display():
    pro = [_make_scored(id="lbc_1", score=80), _make_scored(id="lbc_2", score=70)]
    part = [_make_scored(id="lbc_3", score=75, seller_type="private")]
    output = format_shortlist_display(pro, part, source_counts={"leboncoin": 2, "lacentrale": 1})
    assert "PROFESSIONNELS" in output
    assert "PARTICULIERS" in output
    assert "#1" in output
    assert "#3" in output

def test_parse_command_ok_all():
    cmd = parse_hitl_command("ok")
    assert cmd["action"] == "approve_all"

def test_parse_command_ok_specific():
    cmd = parse_hitl_command("ok 1,3,5")
    assert cmd["action"] == "approve"
    assert cmd["numbers"] == [1, 3, 5]

def test_parse_command_drop():
    cmd = parse_hitl_command("drop 2,4")
    assert cmd["action"] == "drop"
    assert cmd["numbers"] == [2, 4]

def test_parse_command_details():
    cmd = parse_hitl_command("details 3")
    assert cmd["action"] == "details"
    assert cmd["number"] == 3

def test_parse_command_rescrape():
    cmd = parse_hitl_command("rescrape")
    assert cmd["action"] == "rescrape"

def test_parse_command_top():
    cmd = parse_hitl_command("top 20")
    assert cmd["action"] == "top"
    assert cmd["n"] == 20

def test_parse_command_quit():
    cmd = parse_hitl_command("quit")
    assert cmd["action"] == "quit"

def test_parse_command_unknown():
    cmd = parse_hitl_command("blablabla")
    assert cmd["action"] == "unknown"


def test_format_listing_line_mileage_none():
    """mileage_km=None → 'km ?' in output."""
    s = _make_scored(mileage_km=None)
    line = format_listing_line(s, 1)
    assert "km ?" in line


def test_format_listing_line_no_distance():
    """No distance_km → no distance in output."""
    s = _make_scored()
    line = format_listing_line(s, 1, distance_km=None)
    assert "km)" not in line  # no "(X km)" suffix


def test_format_listing_line_empty_highlights():
    """No highlights → 'none' displayed."""
    s = _make_scored(highlights=[])
    line = format_listing_line(s, 1)
    assert "none" in line


def test_parse_command_case_insensitive():
    """Commands are case-insensitive."""
    assert parse_hitl_command("OK")["action"] == "approve_all"
    assert parse_hitl_command("QUIT")["action"] == "quit"
    assert parse_hitl_command("Rescrape")["action"] == "rescrape"


def test_parse_command_ok_with_spaces():
    """'ok 1 , 3' with spaces → parses correctly."""
    cmd = parse_hitl_command("ok 1 , 3")
    assert cmd["action"] == "approve"
    assert cmd["numbers"] == [1, 3]


def test_parse_command_ok_with_invalid_number():
    """'ok 1,x,3' → skips non-digit 'x'."""
    cmd = parse_hitl_command("ok 1,x,3")
    assert cmd["numbers"] == [1, 3]


def test_parse_command_details_invalid():
    """'details abc' → unknown."""
    cmd = parse_hitl_command("details abc")
    assert cmd["action"] == "unknown"


def test_format_shortlist_display_no_scraped_at():
    """scraped_at=None → no 'Scraped:' line."""
    pro = [_make_scored()]
    output = format_shortlist_display(pro, [], scraped_at=None)
    assert "Scraped:" not in output


def test_format_shortlist_display_with_scraped_at():
    """scraped_at set → 'Scraped:' line present."""
    pro = [_make_scored()]
    output = format_shortlist_display(pro, [], scraped_at="2026-03-28T12:00:00Z")
    assert "Scraped:" in output


def test_run_hitl_review_eoferror():
    """EOFError during input → quit."""
    pro = [_make_scored()]
    with patch("builtins.input", side_effect=EOFError):
        result = run_hitl_review(pro, [])
    assert result["action"] == "quit"


def test_run_hitl_review_approve_all():
    """'ok' → approve all, returns IDs."""
    pro = [_make_scored(id="lbc_1")]
    part = [_make_scored(id="lbc_2", seller_type="private")]
    with patch("builtins.input", return_value="ok"):
        result = run_hitl_review(pro, part)
    assert result["action"] == "approve"
    assert "lbc_1" in result["approved_ids"]
    assert "lbc_2" in result["approved_ids"]


def test_run_hitl_review_approve_specific():
    """'ok 1' → approve only #1."""
    pro = [_make_scored(id="lbc_1"), _make_scored(id="lbc_2")]
    with patch("builtins.input", return_value="ok 1"):
        result = run_hitl_review(pro, [])
    assert result["action"] == "approve"
    assert result["approved_ids"] == ["lbc_1"]


def test_run_hitl_review_drop_then_ok():
    """'drop 1' then 'ok' → approve remaining."""
    pro = [_make_scored(id="lbc_1"), _make_scored(id="lbc_2")]
    with patch("builtins.input", side_effect=["drop 1", "ok"]):
        result = run_hitl_review(pro, [])
    assert result["action"] == "approve"
    assert result["approved_ids"] == ["lbc_2"]


def test_run_hitl_review_drop_out_of_bounds():
    """'drop 99' on 1-item list → silently ignored, then 'ok'."""
    pro = [_make_scored(id="lbc_1")]
    with patch("builtins.input", side_effect=["drop 99", "ok"]):
        result = run_hitl_review(pro, [])
    assert result["action"] == "approve"
    assert result["approved_ids"] == ["lbc_1"]


def test_run_hitl_review_rescrape():
    """'rescrape' → returns rescrape action."""
    pro = [_make_scored()]
    with patch("builtins.input", return_value="rescrape"):
        result = run_hitl_review(pro, [])
    assert result["action"] == "rescrape"


def test_run_hitl_review_quit():
    """'quit' → returns quit action."""
    pro = [_make_scored()]
    with patch("builtins.input", return_value="quit"):
        result = run_hitl_review(pro, [])
    assert result["action"] == "quit"


def test_run_hitl_review_unknown_then_ok():
    """Unknown command prints help, then 'ok' works."""
    pro = [_make_scored(id="lbc_1")]
    with patch("builtins.input", side_effect=["blah", "ok"]):
        result = run_hitl_review(pro, [])
    assert result["action"] == "approve"
    assert "lbc_1" in result["approved_ids"]


def test_parse_numbers_valid():
    """Comma-separated numbers parsed correctly."""
    assert _parse_numbers("1,3,5") == [1, 3, 5]


def test_parse_numbers_mixed_valid_invalid():
    """Non-numeric tokens silently dropped."""
    assert _parse_numbers("1,a,3") == [1, 3]


def test_parse_numbers_empty_string():
    """Empty string returns empty list."""
    assert _parse_numbers("") == []


def test_parse_numbers_spaces():
    """Whitespace around numbers handled."""
    assert _parse_numbers(" 1 , 2 , 3 ") == [1, 2, 3]


def test_run_hitl_review_details_command():
    """details command in loop prints listing info, then ok approves."""
    pro = [_make_scored(id="lbc_1", description="Clean car", summary_fr="Bon etat")]
    with patch("builtins.input", side_effect=["details 1", "ok"]):
        result = run_hitl_review(pro, [])
    assert result["action"] == "approve"
    assert "lbc_1" in result["approved_ids"]


def test_run_hitl_review_details_out_of_bounds():
    """details with out-of-bounds number is silently ignored."""
    pro = [_make_scored(id="lbc_1")]
    with patch("builtins.input", side_effect=["details 99", "ok"]):
        result = run_hitl_review(pro, [])
    assert result["action"] == "approve"
    assert "lbc_1" in result["approved_ids"]


def test_run_hitl_review_top_command():
    """top N command returns action=top with n value."""
    pro = [_make_scored(id="lbc_1"), _make_scored(id="lbc_2")]
    with patch("builtins.input", return_value="top 3"):
        result = run_hitl_review(pro, [])
    assert result["action"] == "top"
    assert result["n"] == 3


def test_parse_hitl_command_top_invalid():
    """'top abc' → ValueError → unknown action."""
    cmd = parse_hitl_command("top abc")
    assert cmd["action"] == "unknown"


def test_parse_hitl_command_top_no_number():
    """'top' with no number → IndexError → unknown action."""
    cmd = parse_hitl_command("top")
    assert cmd["action"] == "unknown"


def test_calc_distance_partial_coords():
    """lat set but lon=None → returns None."""
    from hitl import _calc_distance
    listing = _make_scored(lat=48.787, lon=None)
    assert _calc_distance(listing) is None
