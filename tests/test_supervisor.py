import json
import pytest
from unittest.mock import MagicMock, patch
from agent_supervisor import (
    SUPERVISOR_TOOLS, build_supervisor_system_prompt,
    execute_tool, SupervisorAgent,
)

def test_supervisor_tools_defined():
    assert len(SUPERVISOR_TOOLS) == 8
    tool_names = [t["name"] for t in SUPERVISOR_TOOLS]
    assert "scrape_platforms" in tool_names
    assert "get_raw_listings" in tool_names
    assert "dispatch_analyst" in tool_names
    assert "dispatch_pricer" in tool_names
    assert "ask_human" in tool_names
    assert "read_state" in tool_names
    assert "write_state" in tool_names
    assert "notify_telegram" in tool_names

def test_system_prompt_contains_mission():
    prompt = build_supervisor_system_prompt()
    assert "Toyota iQ" in prompt
    assert "automatic" in prompt.lower() or "automatique" in prompt.lower()

def test_execute_tool_read_state():
    agent = SupervisorAgent.__new__(SupervisorAgent)
    agent.state_path = "fake_path"
    with patch("agent_supervisor.load_state") as mock_load:
        mock_state = MagicMock()
        mock_state.model_dump_json.return_value = '{"step":"init"}'
        mock_load.return_value = mock_state
        result = execute_tool("read_state", {}, agent)
        assert "init" in result

def test_supervisor_agent_init():
    with patch("agent_supervisor.load_state") as mock_load, \
         patch("agent_supervisor.LLMClient"):
        mock_load.return_value = MagicMock()
        agent = SupervisorAgent(state_path="test_state.json")
        assert agent is not None

def test_ask_human_uses_hitl_when_shortlists_present():
    agent = SupervisorAgent.__new__(SupervisorAgent)
    agent._shortlist_pro = [MagicMock()]
    agent._shortlist_part = []
    agent._raw_listings = [MagicMock(platform="leboncoin")]
    with patch("agent_supervisor.run_hitl_review") as mock_hitl:
        mock_hitl.return_value = {"action": "approve", "approved_ids": ["lbc_1"]}
        result = execute_tool("ask_human", {"question": "Review?"}, agent)
        mock_hitl.assert_called_once()
        assert "approved" in result
        assert "lbc_1" in result

def test_ask_human_falls_back_to_input_without_shortlists():
    agent = SupervisorAgent.__new__(SupervisorAgent)
    agent._shortlist_pro = []
    agent._shortlist_part = []
    with patch("builtins.input", return_value="yes"):
        result = execute_tool("ask_human", {"question": "Continue?"}, agent)
        assert "yes" in result


def test_execute_tool_write_state():
    agent = SupervisorAgent.__new__(SupervisorAgent)
    agent.state_path = "fake_path"
    mock_state = MagicMock()
    mock_state.step = "init"
    agent.state = mock_state
    with patch("agent_supervisor.save_state"):
        result = execute_tool("write_state", {"updates": {"step": "scraped"}}, agent)
        data = json.loads(result)
        assert data["status"] == "ok"
        assert "step" in data["updated"]


def test_execute_tool_unknown():
    agent = SupervisorAgent.__new__(SupervisorAgent)
    result = execute_tool("nonexistent_tool", {}, agent)
    data = json.loads(result)
    assert "error" in data


def test_execute_tool_get_raw_listings_empty():
    agent = SupervisorAgent.__new__(SupervisorAgent)
    agent._raw_listings = []
    with patch("agent_supervisor.Path") as mock_path:
        mock_path.return_value.glob.return_value = []
        result = execute_tool("get_raw_listings", {}, agent)
        data = json.loads(result)
        assert data["count"] == 0


def test_execute_tool_scrape_platforms():
    agent = SupervisorAgent.__new__(SupervisorAgent)
    agent._raw_listings = []
    agent.state = MagicMock()
    agent.state_path = "fake_path"
    with patch("scraper_lbc.scrape_leboncoin", return_value=[]), \
         patch("scraper_lacentrale.scrape_lacentrale", return_value=[]), \
         patch("scraper_leparking.scrape_leparking", return_value=[]), \
         patch("scraper_autoscout.scrape_autoscout24", return_value=[]), \
         patch("agent_supervisor.save_state"), \
         patch("agent_supervisor.Path"):
        result = execute_tool("scrape_platforms", {"platforms": ["leboncoin", "lacentrale"]}, agent)
        data = json.loads(result)
        assert "leboncoin" in data["platforms_ok"]
        assert "lacentrale" in data["platforms_ok"]


def test_execute_tool_notify_telegram():
    import asyncio
    agent = SupervisorAgent.__new__(SupervisorAgent)

    async def fake_send(text):
        pass

    with patch("telegram_bot.TelegramNotifier") as mock_notifier_cls:
        mock_notifier = MagicMock()
        mock_notifier.send_to_both = fake_send
        mock_notifier.send_to_friend = fake_send
        mock_notifier.send_to_jerome = fake_send
        mock_notifier_cls.return_value = mock_notifier
        result = execute_tool("notify_telegram", {"message": "test"}, agent)
        data = json.loads(result)
        assert data["status"] == "sent"


def test_execute_tool_dispatch_analyst_no_raw():
    """dispatch_analyst with no raw listings → error."""
    agent = SupervisorAgent.__new__(SupervisorAgent)
    agent._raw_listings = []
    result = execute_tool("dispatch_analyst", {}, agent)
    data = json.loads(result)
    assert "error" in data
    assert "No raw listings" in data["error"]


def test_execute_tool_dispatch_pricer_no_match():
    """dispatch_pricer with non-matching IDs → error."""
    agent = SupervisorAgent.__new__(SupervisorAgent)
    agent._shortlist_pro = []
    agent._shortlist_part = []
    result = execute_tool("dispatch_pricer", {"listing_ids": ["lbc_999"]}, agent)
    data = json.loads(result)
    assert "error" in data
    assert "No matching" in data["error"]


def test_ask_human_eoferror_returns_quit():
    """EOFError during input → quit."""
    agent = SupervisorAgent.__new__(SupervisorAgent)
    agent._shortlist_pro = []
    agent._shortlist_part = []
    with patch("builtins.input", side_effect=EOFError):
        result = execute_tool("ask_human", {"question": "Continue?"}, agent)
        data = json.loads(result)
        assert data["human_response"] == "quit"


def test_execute_tool_exception_returns_error():
    """Tool that raises exception → error JSON (not crash)."""
    agent = SupervisorAgent.__new__(SupervisorAgent)
    agent.state_path = "fake_path"
    with patch("agent_supervisor.load_state", side_effect=Exception("disk error")):
        result = execute_tool("read_state", {}, agent)
        data = json.loads(result)
        assert "error" in data
        assert "disk error" in data["error"]


def test_execute_tool_scrape_deduplicates():
    """scrape_platforms deduplicates by (title, price, year, city)."""
    agent = SupervisorAgent.__new__(SupervisorAgent)
    agent._raw_listings = []
    agent.state = MagicMock()
    agent.state_path = "fake_path"

    dup_listing = MagicMock()
    dup_listing.title = "Toyota iQ"
    dup_listing.price = 3200
    dup_listing.year = 2011
    dup_listing.city = "Paris"
    dup_listing.model_dump.return_value = {"title": "Toyota iQ", "price": 3200}

    with patch("scraper_lbc.scrape_leboncoin", return_value=[dup_listing, dup_listing]), \
         patch("agent_supervisor.save_state"), \
         patch("agent_supervisor.Path"):
        result = execute_tool("scrape_platforms", {"platforms": ["leboncoin"]}, agent)
        data = json.loads(result)
        assert data["total_count"] == 1  # deduped from 2 to 1


def test_execute_tool_scrape_unknown_platform():
    """Unknown platform in list → ignored, not in platforms_ok or platforms_failed."""
    agent = SupervisorAgent.__new__(SupervisorAgent)
    agent._raw_listings = []
    agent.state = MagicMock()
    agent.state_path = "fake_path"

    with patch("agent_supervisor.save_state"), \
         patch("agent_supervisor.Path"):
        result = execute_tool("scrape_platforms", {"platforms": ["fakePlatform"]}, agent)
        data = json.loads(result)
        assert "fakePlatform" not in data["platforms_ok"]
        assert data["total_count"] == 0


def test_execute_tool_scrape_different_cities_not_deduped():
    """Same title/price/year but different city → kept as separate listings."""
    agent = SupervisorAgent.__new__(SupervisorAgent)
    agent._raw_listings = []
    agent.state = MagicMock()
    agent.state_path = "fake_path"

    listing1 = MagicMock()
    listing1.title = "Toyota iQ"
    listing1.price = 3200
    listing1.year = 2011
    listing1.city = "Paris"
    listing1.model_dump.return_value = {}

    listing2 = MagicMock()
    listing2.title = "Toyota iQ"
    listing2.price = 3200
    listing2.year = 2011
    listing2.city = "Lyon"
    listing2.model_dump.return_value = {}

    with patch("scraper_lbc.scrape_leboncoin", return_value=[listing1, listing2]), \
         patch("agent_supervisor.save_state"), \
         patch("agent_supervisor.Path"):
        result = execute_tool("scrape_platforms", {"platforms": ["leboncoin"]}, agent)
        data = json.loads(result)
        assert data["total_count"] == 2  # different cities, not deduped


def test_execute_tool_scrape_platform_failure():
    """Platform that raises exception → in platforms_failed, not crash."""
    agent = SupervisorAgent.__new__(SupervisorAgent)
    agent._raw_listings = []
    agent.state = MagicMock()
    agent.state_path = "fake_path"

    with patch("scraper_lbc.scrape_leboncoin", side_effect=Exception("connection timeout")), \
         patch("agent_supervisor.save_state"), \
         patch("agent_supervisor.Path"):
        result = execute_tool("scrape_platforms", {"platforms": ["leboncoin"]}, agent)
        data = json.loads(result)
        assert "leboncoin" in data["platforms_failed"]
        assert data["total_count"] == 0


def test_supervisor_run_end_turn_immediately():
    """run() stops when LLM returns end_turn on first call."""
    agent = SupervisorAgent.__new__(SupervisorAgent)
    agent.state_path = "fake_path"
    agent.state = MagicMock()
    agent.messages = []
    agent._raw_listings = []
    agent._shortlist_pro = []
    agent._shortlist_part = []

    mock_llm = MagicMock()
    agent.llm = mock_llm

    mock_block = MagicMock()
    mock_block.text = "Mission complete"
    mock_llm.query_with_tools.return_value = {
        "content": [mock_block],
        "stop_reason": "end_turn",
        "model": "claude-sonnet-4-20250514",
    }

    with patch("agent_supervisor.save_state"):
        agent.run()

    mock_llm.query_with_tools.assert_called_once()


def test_supervisor_run_tool_use_then_end():
    """run() executes tool_use, then stops on end_turn."""
    agent = SupervisorAgent.__new__(SupervisorAgent)
    agent.state_path = "fake_path"
    agent.state = MagicMock()
    agent.messages = []
    agent._raw_listings = []
    agent._shortlist_pro = []
    agent._shortlist_part = []

    mock_llm = MagicMock()
    agent.llm = mock_llm

    # First call: tool_use (read_state)
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "read_state"
    tool_block.input = {}
    tool_block.id = "tool_123"

    # Second call: end_turn
    end_block = MagicMock()
    end_block.text = "Done"

    mock_llm.query_with_tools.side_effect = [
        {"content": [tool_block], "stop_reason": "tool_use", "model": "claude-sonnet-4-20250514"},
        {"content": [end_block], "stop_reason": "end_turn", "model": "claude-sonnet-4-20250514"},
    ]

    with patch("agent_supervisor.load_state") as mock_load, \
         patch("agent_supervisor.save_state"):
        mock_state = MagicMock()
        mock_state.model_dump_json.return_value = '{"step":"init"}'
        mock_load.return_value = mock_state
        agent.run()

    assert mock_llm.query_with_tools.call_count == 2


def test_execute_tool_dispatch_analyst_success():
    """dispatch_analyst happy path → returns shortlists."""
    agent = SupervisorAgent.__new__(SupervisorAgent)
    agent.state = MagicMock()
    agent.state_path = "fake_path"

    mock_scored = MagicMock()
    mock_scored.id = "lbc_1"
    mock_scored.score = 80
    mock_scored.title = "iQ CVT"
    mock_scored.price = 3200
    mock_scored.seller_type = "pro"

    agent._raw_listings = [MagicMock()]
    agent.llm = MagicMock()

    with patch("agent_analyst.analyze_listings", return_value=([mock_scored], [])), \
         patch("agent_supervisor.save_state"):
        result = execute_tool("dispatch_analyst", {}, agent)
        data = json.loads(result)
        assert len(data["shortlist_pro"]) == 1
        assert data["shortlist_pro"][0]["id"] == "lbc_1"
        assert len(data["shortlist_part"]) == 0


def test_execute_tool_dispatch_pricer_success():
    """dispatch_pricer happy path → returns priced listings."""
    agent = SupervisorAgent.__new__(SupervisorAgent)
    agent.state = MagicMock()
    agent.state_path = "fake_path"
    agent.llm = MagicMock()

    mock_scored = MagicMock()
    mock_scored.id = "lbc_1"
    mock_scored.seller_type = "pro"

    agent._shortlist_pro = [mock_scored]
    agent._shortlist_part = []

    mock_priced = MagicMock()
    mock_priced.id = "lbc_1"
    mock_priced.title = "iQ CVT"
    mock_priced.market_estimate_low = 2500
    mock_priced.market_estimate_high = 3200
    mock_priced.opening_offer = 2400
    mock_priced.max_acceptable = 3000
    mock_priced.message_digital = "Bonjour, je me permets de vous contacter au sujet de votre Toyota iQ..."
    mock_priced.model_dump.return_value = {"id": "lbc_1"}

    with patch("agent_pricer.price_listings", return_value=[mock_priced]), \
         patch("agent_supervisor.save_state"), \
         patch("agent_supervisor.Path") as mock_path:
        mock_path.return_value.__truediv__ = MagicMock(return_value=MagicMock())
        result = execute_tool("dispatch_pricer", {"listing_ids": ["lbc_1"]}, agent)
        data = json.loads(result)
        assert len(data) == 1
        assert data[0]["id"] == "lbc_1"
        assert data[0]["opening_offer"] == 2400


def test_execute_tool_get_raw_loads_from_file(tmp_path):
    """get_raw_listings loads from disk when agent._raw_listings is empty."""
    agent = SupervisorAgent.__new__(SupervisorAgent)
    agent._raw_listings = []

    listing_data = [{
        "id": "lbc_1", "platform": "leboncoin", "title": "Toyota iQ 1.33 CVT",
        "price": 3200, "year": 2011, "mileage_km": 78000, "transmission": "auto",
        "seller_type": "pro", "url": "http://x",
        "scraped_at": "2026-03-28T12:00:00+00:00",
    }]
    raw_file = tmp_path / "raw_listings_20260328.json"
    raw_file.write_text(json.dumps(listing_data), encoding="utf-8")

    with patch("agent_supervisor.OUTPUT_DIR", str(tmp_path)):
        result = execute_tool("get_raw_listings", {}, agent)
        data = json.loads(result)
        assert data["count"] == 1
        assert data["listings"][0]["id"] == "lbc_1"


def test_supervisor_run_exhausts_max_iterations():
    """run() silently exits after 20 iterations of continuous tool_use."""
    agent = SupervisorAgent.__new__(SupervisorAgent)
    agent.state_path = "fake_path"
    agent.state = MagicMock()
    agent.messages = []
    agent._raw_listings = []
    agent._shortlist_pro = []
    agent._shortlist_part = []

    mock_llm = MagicMock()
    agent.llm = mock_llm

    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.name = "read_state"
    tool_block.input = {}
    tool_block.id = "tool_loop"

    mock_state = MagicMock()
    mock_state.model_dump_json.return_value = '{}'

    # Always return tool_use, never end_turn
    mock_llm.query_with_tools.return_value = {
        "content": [tool_block],
        "stop_reason": "tool_use",
        "model": "claude-sonnet-4-20250514",
    }

    with patch("agent_supervisor.load_state", return_value=mock_state), \
         patch("agent_supervisor.save_state"):
        agent.run()

    assert mock_llm.query_with_tools.call_count == 20


def test_ask_human_hitl_rescrape():
    """ask_human returns rescrape when HITL says rescrape."""
    agent = SupervisorAgent.__new__(SupervisorAgent)
    agent._shortlist_pro = [MagicMock()]
    agent._shortlist_part = []
    agent._raw_listings = [MagicMock(platform="leboncoin")]
    with patch("agent_supervisor.run_hitl_review") as mock_hitl:
        mock_hitl.return_value = {"action": "rescrape"}
        result = execute_tool("ask_human", {"question": "Review?"}, agent)
        data = json.loads(result)
        assert data["human_response"] == "rescrape"


def test_ask_human_hitl_top_n():
    """ask_human returns top N when HITL says top."""
    agent = SupervisorAgent.__new__(SupervisorAgent)
    agent._shortlist_pro = [MagicMock()]
    agent._shortlist_part = []
    agent._raw_listings = [MagicMock(platform="leboncoin")]
    with patch("agent_supervisor.run_hitl_review") as mock_hitl:
        mock_hitl.return_value = {"action": "top", "n": 5}
        result = execute_tool("ask_human", {"question": "Review?"}, agent)
        data = json.loads(result)
        assert data["human_response"] == "top 5"


def test_ask_human_hitl_quit():
    """ask_human returns quit when HITL says quit."""
    agent = SupervisorAgent.__new__(SupervisorAgent)
    agent._shortlist_pro = [MagicMock()]
    agent._shortlist_part = []
    agent._raw_listings = [MagicMock(platform="leboncoin")]
    with patch("agent_supervisor.run_hitl_review") as mock_hitl:
        mock_hitl.return_value = {"action": "quit"}
        result = execute_tool("ask_human", {"question": "Review?"}, agent)
        data = json.loads(result)
        assert data["human_response"] == "quit"


def test_notify_telegram_friend_target():
    """notify_telegram with target=friend calls send_to_friend."""
    import asyncio
    agent = SupervisorAgent.__new__(SupervisorAgent)

    async def fake_send(text):
        pass

    with patch("telegram_bot.TelegramNotifier") as mock_cls:
        mock_notifier = MagicMock()
        mock_notifier.send_to_friend = fake_send
        mock_cls.return_value = mock_notifier
        result = execute_tool("notify_telegram", {"message": "hi", "target": "friend"}, agent)
        data = json.loads(result)
        assert data["status"] == "sent"
        assert data["target"] == "friend"


def test_notify_telegram_jerome_target():
    """notify_telegram with target=jerome calls send_to_jerome."""
    import asyncio
    agent = SupervisorAgent.__new__(SupervisorAgent)

    async def fake_send(text):
        pass

    with patch("telegram_bot.TelegramNotifier") as mock_cls:
        mock_notifier = MagicMock()
        mock_notifier.send_to_jerome = fake_send
        mock_cls.return_value = mock_notifier
        result = execute_tool("notify_telegram", {"message": "hi", "target": "jerome"}, agent)
        data = json.loads(result)
        assert data["status"] == "sent"
        assert data["target"] == "jerome"


def test_notify_telegram_exception_returns_error():
    """notify_telegram exception returns error JSON, not crash."""
    agent = SupervisorAgent.__new__(SupervisorAgent)

    with patch("telegram_bot.TelegramNotifier") as mock_cls:
        mock_cls.side_effect = Exception("network down")
        result = execute_tool("notify_telegram", {"message": "hi"}, agent)
        data = json.loads(result)
        assert "error" in data
        assert "network down" in data["error"]


def test_write_state_unknown_key_silently_dropped():
    """write_state with unknown key does not crash, key is NOT set on state."""
    from state import PipelineState
    agent = SupervisorAgent.__new__(SupervisorAgent)
    agent.state_path = "fake_path"
    agent.state = PipelineState()
    with patch("agent_supervisor.save_state"):
        result = execute_tool("write_state", {"updates": {"nonexistent_field_xyz": "val"}}, agent)
        data = json.loads(result)
        assert data["status"] == "ok"
        # Real PipelineState has no 'nonexistent_field_xyz' → hasattr is False → not set
        assert not hasattr(agent.state, "nonexistent_field_xyz")


def test_ask_human_hitl_unknown_action():
    """ask_human with unknown HITL action → returns str(result)."""
    agent = SupervisorAgent.__new__(SupervisorAgent)
    agent._shortlist_pro = [MagicMock()]
    agent._shortlist_part = []
    agent._raw_listings = [MagicMock(platform="leboncoin")]
    with patch("agent_supervisor.run_hitl_review") as mock_hitl:
        mock_hitl.return_value = {"action": "something_unexpected", "data": 42}
        result = execute_tool("ask_human", {"question": "Review?"}, agent)
        data = json.loads(result)
        assert "something_unexpected" in data["human_response"]


def test_ask_human_fallback_with_context():
    """ask_human fallback prints context when provided."""
    agent = SupervisorAgent.__new__(SupervisorAgent)
    agent._shortlist_pro = []
    agent._shortlist_part = []
    with patch("builtins.input", return_value="got it"):
        result = execute_tool("ask_human", {"question": "Q?", "context": "Some context"}, agent)
        data = json.loads(result)
        assert data["human_response"] == "got it"


def test_notify_telegram_inner_exception():
    """Telegram notifier send raises → returns error JSON (inner except)."""
    import asyncio
    agent = SupervisorAgent.__new__(SupervisorAgent)

    async def fail_send(text):
        raise RuntimeError("bot token revoked")

    with patch("telegram_bot.TelegramNotifier") as mock_cls:
        mock_notifier = MagicMock()
        mock_notifier.send_to_both = fail_send
        mock_cls.return_value = mock_notifier
        result = execute_tool("notify_telegram", {"message": "test"}, agent)
        data = json.loads(result)
        assert "error" in data
        assert "bot token revoked" in data["error"]
