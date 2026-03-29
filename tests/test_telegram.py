"""Tests for Telegram bot formatting, parsing, commands, and notifications."""
import pytest
from datetime import datetime, timezone
from unittest.mock import patch, MagicMock, AsyncMock
from models import ScoredListing, ScoreBreakdown
from telegram_bot import (
    format_listing_telegram,
    format_listing_notification,
    format_shortlist_telegram,
    parse_interval,
    TelegramNotifier,
    SCORE_THRESHOLD,
    build_application,
    cmd_demarrer,
    cmd_approuver,
    cmd_rejeter,
    cmd_intervalle,
    cmd_liste,
    cmd_chercher,
    cmd_details,
    cmd_statut,
)


def _make_scored(id="lbc_1", score=78, seller_type="pro", **kw):
    defaults = dict(
        platform="leboncoin", title="Toyota iQ 1.33 CVT",
        price=3200, year=2011, mileage_km=78000, transmission="auto",
        city="Vitry", lat=48.787, lon=2.392, url="http://x.com/listing",
        scraped_at=datetime.now(timezone.utc).isoformat(),
        score_breakdown=ScoreBreakdown(price=25, mileage=15, year=10, proximity=8, condition=10, transmission=10),
        excluded=False, red_flags=[], highlights=["CT OK"], concerns=[], summary_fr="Bon etat",
    )
    defaults.update(kw)
    return ScoredListing(id=id, seller_type=seller_type, score=score, **defaults)


def test_format_listing_telegram():
    listing = _make_scored()
    text = format_listing_telegram(listing, 1)
    assert "#1" in text
    assert "78" in text  # score
    assert "3" in text   # price contains 3 (from 3200)
    assert "Vitry" in text
    assert "http://x.com/listing" in text


def test_format_shortlist_telegram():
    pro = [_make_scored(id="lbc_1", score=80)]
    part = [_make_scored(id="lbc_2", score=75, seller_type="private")]
    text = format_shortlist_telegram(pro, part)
    assert "PROFESSIONNEL" in text.upper()
    assert "PARTICULIER" in text.upper()
    assert "#1" in text
    assert "#2" in text  # global numbering


def test_parse_interval_hours():
    assert parse_interval("4h") == 4


def test_parse_interval_days():
    assert parse_interval("1j") == 24


def test_parse_interval_weeks():
    assert parse_interval("1s") == 168


def test_parse_interval_below_minimum():
    assert parse_interval("30m") is None


def test_parse_interval_invalid():
    assert parse_interval("xyz") is None


def test_notifier_init():
    notifier = TelegramNotifier(token="fake", friend_chat_id="123", jerome_chat_id="456")
    assert notifier.friend_chat_id == "123"
    assert notifier.jerome_chat_id == "456"


def test_notifier_no_token():
    with patch("telegram_bot.TELEGRAM_BOT_TOKEN", ""):
        notifier = TelegramNotifier(token="", friend_chat_id="123", jerome_chat_id="456")
        assert notifier.bot is None


def test_build_application_registers_handlers():
    with patch("telegram_bot.TELEGRAM_BOT_TOKEN", "fake:token"):
        with patch("telegram_bot.Application") as mock_app_cls:
            mock_builder = MagicMock()
            mock_app = MagicMock()
            mock_builder.token.return_value = mock_builder
            mock_builder.post_init.return_value = mock_builder
            mock_builder.build.return_value = mock_app
            mock_app_cls.builder.return_value = mock_builder
            app = build_application()
            assert mock_app.add_handler.call_count == 8


@pytest.mark.asyncio
async def test_cmd_demarrer():
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    await cmd_demarrer(update, context)
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "Toyota iQ" in text


@pytest.mark.asyncio
async def test_cmd_approuver_with_numbers():
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["1,3,5"]
    context.application.bot_data = {}
    await cmd_approuver(update, context)
    update.message.reply_text.assert_called_once()
    assert context.application.bot_data["approved_numbers"] == [1, 3, 5]


@pytest.mark.asyncio
async def test_cmd_approuver_no_args():
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = []
    await cmd_approuver(update, context)
    text = update.message.reply_text.call_args[0][0]
    assert "Usage" in text


@pytest.mark.asyncio
async def test_cmd_rejeter_with_numbers():
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["2,4"]
    context.application.bot_data = {}
    await cmd_rejeter(update, context)
    assert context.application.bot_data["rejected_numbers"] == [2, 4]


@pytest.mark.asyncio
async def test_cmd_intervalle_valid():
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["6h"]
    context.application.bot_data = {}
    await cmd_intervalle(update, context)
    assert context.application.bot_data["interval_hours"] == 6


@pytest.mark.asyncio
async def test_cmd_intervalle_invalid():
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["30m"]
    await cmd_intervalle(update, context)
    text = update.message.reply_text.call_args[0][0]
    assert "invalide" in text.lower()


@pytest.mark.asyncio
async def test_cmd_liste_no_data(tmp_path):
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    with patch("telegram_bot.OUTPUT_DIR", str(tmp_path)):
        await cmd_liste(update, context)
    text = update.message.reply_text.call_args[0][0]
    assert "Pas de shortlist" in text


def test_format_shortlist_telegram_empty():
    text = format_shortlist_telegram([], [])
    assert "Aucune" in text


def test_parse_interval_fractional_hours():
    assert parse_interval("2.5h") == 2.5


def test_format_listing_telegram_mileage_none():
    listing = _make_scored(mileage_km=None)
    text = format_listing_telegram(listing, 1)
    assert "km ?" in text


def test_format_listing_telegram_no_coords():
    listing = _make_scored(lat=None, lon=None)
    text = format_listing_telegram(listing, 1)
    assert "d'Orly" not in text


def test_format_listing_telegram_empty_highlights():
    listing = _make_scored(highlights=[])
    text = format_listing_telegram(listing, 1)
    assert "+ -" in text


@pytest.mark.asyncio
async def test_cmd_chercher_runs_pipeline():
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.application.bot_data = {}

    with patch("scraper_lbc.scrape_leboncoin", return_value=[]), \
         patch("scraper_lacentrale.scrape_lacentrale", return_value=[]), \
         patch("scraper_leparking.scrape_leparking", return_value=[]), \
         patch("scraper_autoscout.scrape_autoscout24", return_value=[]), \
         patch("agent_analyst.analyze_listings", return_value=([], [])), \
         patch("llm_client.LLMClient"):
        await cmd_chercher(update, context)
    # Should have sent at least "scrape termine" and "analyse terminee"
    assert update.message.reply_text.call_count >= 3


@pytest.mark.asyncio
async def test_cmd_rejeter_no_args():
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = []
    await cmd_rejeter(update, context)
    text = update.message.reply_text.call_args[0][0]
    assert "Usage" in text


@pytest.mark.asyncio
async def test_cmd_details_no_args():
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = []
    await cmd_details(update, context)
    text = update.message.reply_text.call_args[0][0]
    assert "Usage" in text


@pytest.mark.asyncio
async def test_cmd_details_no_shortlist(tmp_path):
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["1"]
    with patch("telegram_bot.OUTPUT_DIR", str(tmp_path)):
        await cmd_details(update, context)
    text = update.message.reply_text.call_args[0][0]
    assert "Pas de shortlist" in text


def test_parse_interval_at_min_boundary():
    from config import MIN_INTERVAL_HOURS
    assert parse_interval(f"{MIN_INTERVAL_HOURS}h") == MIN_INTERVAL_HOURS


def test_parse_interval_below_min_boundary():
    assert parse_interval("0.5h") is None


@pytest.mark.asyncio
async def test_cmd_statut():
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    with patch("state.load_state") as mock_load:
        mock_state = MagicMock()
        mock_state.step = "init"
        mock_state.last_scrape_at = None
        mock_state.raw_listing_count = 0
        mock_state.analysis_status = "pending"
        mock_state.pricing_status = "pending"
        mock_load.return_value = mock_state
        await cmd_statut(update, context)
    update.message.reply_text.assert_called_once()
    text = update.message.reply_text.call_args[0][0]
    assert "initial" in text


@pytest.mark.asyncio
async def test_cmd_intervalle_no_args():
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = []
    await cmd_intervalle(update, context)
    text = update.message.reply_text.call_args[0][0]
    assert "Usage" in text


@pytest.mark.asyncio
async def test_cmd_approuver_invalid_numbers():
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["a,b,c"]
    await cmd_approuver(update, context)
    text = update.message.reply_text.call_args[0][0]
    assert "invalide" in text.lower()


def test_parse_interval_valid_minutes():
    assert parse_interval("120m") == 2.0


def test_parse_interval_above_max():
    """2s = 336 hours, above MAX_INTERVAL_HOURS (168) → None."""
    assert parse_interval("2s") is None


def test_format_shortlist_telegram_pro_empty_part_present():
    part = [_make_scored(id="lbc_1", score=75, seller_type="private")]
    text = format_shortlist_telegram([], part)
    assert "PARTICULIER" in text.upper()
    assert "#1" in text


@pytest.mark.asyncio
async def test_notifier_send_to_friend_success():
    notifier = TelegramNotifier(token="fake", friend_chat_id="123", jerome_chat_id="456")
    notifier.bot = AsyncMock()
    await notifier.send_to_friend("hello")
    notifier.bot.send_message.assert_called_once_with(chat_id="123", text="hello")


@pytest.mark.asyncio
async def test_notifier_send_to_jerome_success():
    notifier = TelegramNotifier(token="fake", friend_chat_id="123", jerome_chat_id="456")
    notifier.bot = AsyncMock()
    await notifier.send_to_jerome("hello")
    notifier.bot.send_message.assert_called_once_with(chat_id="456", text="hello")


@pytest.mark.asyncio
async def test_notifier_send_to_friend_exception_swallowed():
    notifier = TelegramNotifier(token="fake", friend_chat_id="123", jerome_chat_id="456")
    notifier.bot = AsyncMock()
    notifier.bot.send_message.side_effect = Exception("network error")
    await notifier.send_to_friend("hello")  # should not raise


@pytest.mark.asyncio
async def test_notifier_send_to_friend_no_chat_id():
    with patch("telegram_bot.TELEGRAM_FRIEND_CHAT_ID", ""):
        notifier = TelegramNotifier(token="fake", friend_chat_id="", jerome_chat_id="456")
        notifier.bot = AsyncMock()
        await notifier.send_to_friend("hello")
        notifier.bot.send_message.assert_not_called()


@pytest.mark.asyncio
async def test_notifier_send_to_jerome_exception_swallowed():
    notifier = TelegramNotifier(token="fake", friend_chat_id="123", jerome_chat_id="456")
    notifier.bot = AsyncMock()
    notifier.bot.send_message.side_effect = Exception("jerome chat error")
    await notifier.send_to_jerome("hello")  # should not raise


@pytest.mark.asyncio
async def test_notifier_send_to_both_calls_both():
    notifier = TelegramNotifier(token="fake", friend_chat_id="123", jerome_chat_id="456")
    notifier.bot = AsyncMock()
    await notifier.send_to_both("hello")
    assert notifier.bot.send_message.call_count == 2


@pytest.mark.asyncio
async def test_cmd_rejeter_invalid_numbers():
    update = MagicMock()
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    context.args = ["a,b"]
    await cmd_rejeter(update, context)
    text = update.message.reply_text.call_args[0][0]
    assert "invalide" in text.lower()


# --- New tests: notification with photos ---

def test_format_listing_notification():
    listing = _make_scored(seller_name="Jean Dupont", seller_phone="+33612345678")
    text = format_listing_notification(listing, 1)
    assert "#1" in text
    assert "78/100" in text
    assert "3 200 EUR" in text
    assert "Vitry" in text
    assert "Jean Dupont" in text
    assert "+33612345678" in text
    assert "http://x.com/listing" in text


def test_format_listing_notification_no_phone():
    listing = _make_scored()
    text = format_listing_notification(listing, 2)
    assert "Tel:" not in text


@pytest.mark.asyncio
async def test_notifier_send_listing_with_photo():
    notifier = TelegramNotifier(token="fake", friend_chat_id="123", jerome_chat_id="456")
    notifier.bot = AsyncMock()
    listing = _make_scored(images=["https://img.lbc.fr/1.jpg"])
    await notifier.send_listing_with_photo("456", listing, 1)
    notifier.bot.send_photo.assert_called_once()
    call_kwargs = notifier.bot.send_photo.call_args
    assert call_kwargs.kwargs["photo"] == "https://img.lbc.fr/1.jpg"


@pytest.mark.asyncio
async def test_notifier_send_listing_no_photo():
    notifier = TelegramNotifier(token="fake", friend_chat_id="123", jerome_chat_id="456")
    notifier.bot = AsyncMock()
    listing = _make_scored(images=[])
    await notifier.send_listing_with_photo("456", listing, 1)
    notifier.bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_notifier_send_listing_photo_fails_falls_back():
    """If send_photo fails, fall back to send_message."""
    notifier = TelegramNotifier(token="fake", friend_chat_id="123", jerome_chat_id="456")
    notifier.bot = AsyncMock()
    notifier.bot.send_photo.side_effect = Exception("photo failed")
    listing = _make_scored(images=["https://img.lbc.fr/1.jpg"])
    await notifier.send_listing_with_photo("456", listing, 1)
    notifier.bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_notifier_notify_shortlist_filters_by_score():
    notifier = TelegramNotifier(token="fake", friend_chat_id="123", jerome_chat_id="456")
    notifier.bot = AsyncMock()
    listings = [
        _make_scored(id="lbc_high", score=85, images=["https://img.lbc.fr/1.jpg"]),
        _make_scored(id="lbc_low", score=30, images=["https://img.lbc.fr/2.jpg"]),
    ]
    await notifier.notify_shortlist(listings)
    # Header + 1 high-score listing (send_photo), score=30 filtered out
    assert notifier.bot.send_message.call_count == 1  # header
    assert notifier.bot.send_photo.call_count == 1    # only the 85-score one


@pytest.mark.asyncio
async def test_notifier_notify_shortlist_empty():
    notifier = TelegramNotifier(token="fake", friend_chat_id="123", jerome_chat_id="456")
    notifier.bot = AsyncMock()
    await notifier.notify_shortlist([])
    notifier.bot.send_message.assert_called_once()
    text = notifier.bot.send_message.call_args.kwargs.get("text", notifier.bot.send_message.call_args[1].get("text", ""))
    assert "Aucune" in text
