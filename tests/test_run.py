# tests/test_run.py
import os
from unittest.mock import patch, MagicMock
from run import main, _is_pid_alive, _kill_old_instance, _write_pid, _build_html, PID_FILE
from models import RawListing
from datetime import datetime, timezone


def test_main_no_args_starts_bot_and_scheduler():
    with patch("run._kill_old_instance"), \
         patch("run._write_pid"), \
         patch("agent_supervisor.SupervisorAgent"), \
         patch("monitor.start_monitor_thread") as mock_monitor, \
         patch("scheduler.PipelineScheduler") as mock_sched_cls, \
         patch("telegram_bot.build_application") as mock_build:
        mock_sched = MagicMock()
        mock_sched_cls.return_value = mock_sched
        mock_app = MagicMock()
        mock_build.return_value = mock_app
        main(["run.py"])
        mock_monitor.assert_called_once()
        mock_sched.start.assert_called_once()
        mock_app.run_polling.assert_called_once()


def test_is_pid_alive_current_process():
    assert _is_pid_alive(os.getpid()) is True


def test_is_pid_alive_dead_pid():
    assert _is_pid_alive(99999999) is False


def test_kill_old_instance_no_pid_file(tmp_path):
    with patch("run.PID_FILE", tmp_path / "bot.pid"):
        _kill_old_instance()  # should not raise


def test_kill_old_instance_stale_pid(tmp_path):
    pid_file = tmp_path / "bot.pid"
    pid_file.write_text("99999999")
    with patch("run.PID_FILE", pid_file):
        _kill_old_instance()
    assert not pid_file.exists()


def test_kill_old_instance_corrupt_file(tmp_path):
    pid_file = tmp_path / "bot.pid"
    pid_file.write_text("not_a_number")
    with patch("run.PID_FILE", pid_file):
        _kill_old_instance()
    assert not pid_file.exists()


def test_write_pid_creates_file(tmp_path):
    pid_file = tmp_path / "bot.pid"
    with patch("run.PID_FILE", pid_file):
        _write_pid()
    assert pid_file.exists()
    assert int(pid_file.read_text()) == os.getpid()


def test_main_scrape_only():
    with patch("scraper_lbc.scrape_leboncoin", return_value=[]) as mock_lbc, \
         patch("scraper_lacentrale.scrape_lacentrale", return_value=[]) as mock_lc, \
         patch("scraper_leparking.scrape_leparking", return_value=[]) as mock_lp, \
         patch("scraper_autoscout.scrape_autoscout24", return_value=[]) as mock_as:
        main(["run.py", "scrape"])
        mock_lbc.assert_called_once()
        mock_lc.assert_called_once()
        mock_lp.assert_called_once()
        mock_as.assert_called_once()


def test_main_status():
    with patch("state.load_state") as mock_load:
        mock_state = MagicMock()
        mock_state.model_dump_json.return_value = '{"step":"init"}'
        mock_load.return_value = mock_state
        main(["run.py", "status"])


def test_main_analyze_no_files(capsys, tmp_path):
    with patch("run.OUTPUT_DIR", str(tmp_path)):
        main(["run.py", "analyze"])
        captured = capsys.readouterr()
        assert "No raw listings" in captured.out


def test_main_price_no_files(capsys, tmp_path):
    with patch("run.OUTPUT_DIR", str(tmp_path)):
        main(["run.py", "price"])
        captured = capsys.readouterr()
        assert "No approved shortlist" in captured.out


def test_main_unknown_command(capsys):
    main(["run.py", "foobar"])
    captured = capsys.readouterr()
    assert "Unknown command" in captured.out


def test_main_analyze_with_files(capsys, tmp_path):
    """analyze command with files → loads listings, calls analyst."""
    import json
    from datetime import datetime, timezone
    listing_data = [{
        "id": "lbc_1", "platform": "leboncoin", "title": "Toyota iQ",
        "price": 3200, "year": 2011, "mileage_km": 78000, "transmission": "auto",
        "seller_type": "pro", "url": "http://x",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
    }]
    raw_file = tmp_path / "raw_listings_20260328.json"
    raw_file.write_text(json.dumps(listing_data), encoding="utf-8")

    with patch("run.OUTPUT_DIR", str(tmp_path)), \
         patch("llm_client.LLMClient") as mock_llm_cls, \
         patch("agent_analyst.analyze_listings", return_value=([], [])) as mock_analyze:
        main(["run.py", "analyze"])
        mock_analyze.assert_called_once()
        captured = capsys.readouterr()
        assert "Loaded 1 listings" in captured.out
        assert "Shortlist" in captured.out


def _make_raw_listing(**overrides):
    now = datetime.now(timezone.utc).isoformat()
    defaults = dict(
        id="lbc_1", platform="leboncoin", title="Toyota iQ Auto",
        price=3200, year=2011, mileage_km=78000, transmission="auto",
        city="Vitry", department="94", lat=48.787, lon=2.392,
        seller_type="private", suspected_pro=False, has_phone=False,
        url="https://lbc.fr/1", scraped_at=now,
    )
    defaults.update(overrides)
    return RawListing(**defaults)


# --- HTML generator tests ---

def test_build_html_splits_pro_and_particulier():
    """HTML must contain separate Pro and Particulier sections."""
    listings = [
        _make_raw_listing(id="lbc_1", seller_type="pro", price=3000),
        _make_raw_listing(id="lbc_2", seller_type="private", price=4000),
    ]
    html = _build_html(listings)
    assert "Professionnels" in html
    assert "Particuliers" in html
    assert "(1)" in html  # 1 pro
    # Global numbering: pro=#1, private=#2
    assert "#1" in html
    assert "#2" in html


def test_build_html_phone_button():
    """seller_phone present must show clickable phone button."""
    listings = [
        _make_raw_listing(id="lbc_1", seller_phone="+33612345678"),
        _make_raw_listing(id="lbc_2", seller_phone=None),
    ]
    html = _build_html(listings)
    assert "tel:+33612345678" in html
    assert "btn-phone" in html
    # Only one phone link (tel:)
    assert html.count("tel:") == 1


def test_build_html_contact_button():
    """Every listing must have a Contacter button."""
    listings = [_make_raw_listing()]
    html = _build_html(listings)
    assert "btn-contact" in html
    assert "Contacter" in html


def test_build_html_pro_badge():
    """Pro sellers must show PRO badge."""
    listings = [_make_raw_listing(seller_type="pro")]
    html = _build_html(listings)
    assert "PRO" in html
    assert "pro-badge" in html


def test_build_html_suspected_pro_badge():
    """suspected_pro=True + seller_type=pro must show 'suspect pro' badge."""
    listings = [_make_raw_listing(seller_type="pro", suspected_pro=True)]
    html = _build_html(listings)
    assert "suspect pro" in html


def test_build_html_no_pro_section_message():
    """When no pros, show 'Aucune annonce professionnelle'."""
    listings = [_make_raw_listing(seller_type="private")]
    html = _build_html(listings)
    assert "Aucune annonce professionnelle" in html


def test_build_html_images():
    """Listings with images must have img tags."""
    listings = [_make_raw_listing(images=["https://img.lbc.fr/1.jpg", "https://img.lbc.fr/2.jpg"])]
    html = _build_html(listings)
    assert html.count("<img") == 2


def test_build_html_price_sorted():
    """Listings within each section must be sorted by price ascending."""
    listings = [
        _make_raw_listing(id="lbc_exp", seller_type="private", price=9000),
        _make_raw_listing(id="lbc_cheap", seller_type="private", price=3000),
    ]
    html = _build_html(listings)
    pos_cheap = html.index("3,000")
    pos_exp = html.index("9,000")
    assert pos_cheap < pos_exp


def test_main_price_with_files(capsys, tmp_path):
    """price command with files → loads shortlist, calls pricer."""
    import json
    from datetime import datetime, timezone
    listing_data = [{
        "id": "lbc_1", "platform": "leboncoin", "title": "iQ",
        "price": 3200, "year": 2011, "seller_type": "pro", "url": "http://x",
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "score": 80, "excluded": False,
        "score_breakdown": {"price": 20, "mileage": 15, "year": 10, "proximity": 8, "condition": 10, "transmission": 10},
        "red_flags": [], "highlights": [], "concerns": [], "summary_fr": "OK",
    }]
    shortlist_file = tmp_path / "approved_20260328.json"
    shortlist_file.write_text(json.dumps(listing_data), encoding="utf-8")

    with patch("run.OUTPUT_DIR", str(tmp_path)), \
         patch("llm_client.LLMClient") as mock_llm_cls, \
         patch("agent_pricer.price_listings", return_value=[]) as mock_price:
        main(["run.py", "price"])
        mock_price.assert_called_once()
        captured = capsys.readouterr()
        assert "Priced" in captured.out
