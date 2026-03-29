"""Supervisor Agent: Claude Sonnet tool_use loop that orchestrates the pipeline."""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from config import CACHE_FRESHNESS_HOURS, OUTPUT_DIR, PLATFORMS
from hitl import run_hitl_review
from llm_client import LLMClient
from models import RawListing, ScoredListing
from state import PipelineState, load_state, save_state

logger = logging.getLogger(__name__)


def build_supervisor_system_prompt() -> str:
    return """You are the supervisor of a car search mission for a Toyota iQ automatic.

YOUR MISSION: Find the best Toyota iQ automatic deals in France for a friend.
Budget: max 5000 EUR. Max 150k km. Min 2009. Automatic only.

YOU HAVE TOOLS. Use them. You are in a loop.

WORKFLOW:
1. Call read_state to check current pipeline state.
2. If no fresh data (last scrape > 4 hours), call scrape_platforms.
3. After scraping, call get_raw_listings to see the data.
4. Call dispatch_analyst to score and rank the listings.
5. Call ask_human to present shortlists and get approval.
6. If human approves listings, call dispatch_pricer for approved ones.
7. Present final pricing to human. Done.

DECISION RULES:
- 0 listings after scrape? Tell human via ask_human, suggest retry later.
- 1 platform failed? Continue with partial data, note it.
- Analyst returns bad output? Retry up to 2x with dispatch_analyst.
- Human says "rescrape"? Call scrape_platforms again.
- Human says "top N"? Call dispatch_analyst again with new top_n.
- Human says "quit"? Stop immediately.

NEVER proceed without validating the previous step output.
ALWAYS explain your reasoning before calling a tool."""


SUPERVISOR_TOOLS = [
    {
        "name": "scrape_platforms",
        "description": "Scrape platforms (leboncoin, lacentrale, leparking, autoscout24) for Toyota iQ listings. Returns count and status per platform.",
        "input_schema": {
            "type": "object",
            "properties": {
                "platforms": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Platforms to scrape: 'leboncoin', 'lacentrale', 'leparking', 'autoscout24'"
                }
            },
            "required": ["platforms"]
        }
    },
    {
        "name": "get_raw_listings",
        "description": "Get the most recent raw listings from cache.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "dispatch_analyst",
        "description": "Send listings to the analyst agent for scoring. Returns two shortlists (pro + private).",
        "input_schema": {
            "type": "object",
            "properties": {
                "top_n": {
                    "type": "integer",
                    "description": "Max listings per shortlist (default 10)"
                }
            }
        }
    },
    {
        "name": "dispatch_pricer",
        "description": "Send approved listings to the pricer agent for market pricing and negotiation messages.",
        "input_schema": {
            "type": "object",
            "properties": {
                "listing_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "IDs of approved listings"
                }
            },
            "required": ["listing_ids"]
        }
    },
    {
        "name": "ask_human",
        "description": "Present information to the human and get their response via terminal.",
        "input_schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string", "description": "What to ask or show"},
                "context": {"type": "string", "description": "Additional context"}
            },
            "required": ["question"]
        }
    },
    {
        "name": "read_state",
        "description": "Read the current pipeline state.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "write_state",
        "description": "Update the pipeline state.",
        "input_schema": {
            "type": "object",
            "properties": {
                "updates": {"type": "object", "description": "State fields to update"}
            },
            "required": ["updates"]
        }
    },
    {
        "name": "notify_telegram",
        "description": "Send a message to the friend and Jerome via Telegram.",
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Text to send"},
                "target": {"type": "string", "enum": ["friend", "jerome", "both"], "description": "Who to notify (default: both)"}
            },
            "required": ["message"]
        }
    },
]


class SupervisorAgent:
    """Supervisor agent: Claude Sonnet in a tool_use loop."""

    def __init__(self, state_path: str | None = None):
        self.llm = LLMClient()
        self.state_path = state_path or str(Path(OUTPUT_DIR) / "state.json")
        self.state = load_state(self.state_path)
        self.messages: list[dict] = []
        self._raw_listings: list[RawListing] = []
        self._shortlist_pro: list[ScoredListing] = []
        self._shortlist_part: list[ScoredListing] = []

    def run(self) -> None:
        """Main supervisor loop."""
        system = build_supervisor_system_prompt()
        self.messages = [
            {"role": "user", "content": "Begin the Toyota iQ automatic search mission. Start by reading the current state."}
        ]

        max_iterations = 20
        for i in range(max_iterations):
            logger.info(f"Supervisor iteration {i+1}")

            response = self.llm.query_with_tools(
                messages=self.messages,
                tools=SUPERVISOR_TOOLS,
                system=system,
            )

            assistant_content = response["content"]
            self.messages.append({"role": "assistant", "content": assistant_content})

            if response["stop_reason"] == "tool_use":
                tool_results = []
                for block in assistant_content:
                    if block.type == "tool_use":
                        logger.info(f"Supervisor calls tool: {block.name}")
                        result = execute_tool(block.name, block.input, self)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        })
                self.messages.append({"role": "user", "content": tool_results})

            elif response["stop_reason"] == "end_turn":
                for block in assistant_content:
                    if hasattr(block, "text"):
                        print(f"\n[Supervisor] {block.text}")
                break

        save_state(self.state, self.state_path)
        logger.info("Supervisor loop ended")


def execute_tool(tool_name: str, tool_input: dict, agent: SupervisorAgent) -> str:
    """Execute a supervisor tool and return result as string."""
    try:
        if tool_name == "read_state":
            state = load_state(agent.state_path)
            return state.model_dump_json(indent=2)

        elif tool_name == "write_state":
            updates = tool_input.get("updates", {})
            for k, v in updates.items():
                if hasattr(agent.state, k):
                    setattr(agent.state, k, v)
            save_state(agent.state, agent.state_path)
            return json.dumps({"status": "ok", "updated": list(updates.keys())})

        elif tool_name == "scrape_platforms":
            return _tool_scrape(tool_input, agent)

        elif tool_name == "get_raw_listings":
            return _tool_get_raw(agent)

        elif tool_name == "dispatch_analyst":
            return _tool_analyst(tool_input, agent)

        elif tool_name == "dispatch_pricer":
            return _tool_pricer(tool_input, agent)

        elif tool_name == "ask_human":
            return _tool_ask_human(tool_input, agent)

        elif tool_name == "notify_telegram":
            return _tool_notify_telegram(tool_input, agent)

        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    except Exception as e:
        logger.error(f"Tool {tool_name} failed: {e}")
        return json.dumps({"error": str(e)})


def _tool_scrape(tool_input: dict, agent: SupervisorAgent) -> str:
    from scraper_lbc import scrape_leboncoin
    from scraper_lacentrale import scrape_lacentrale
    from scraper_leparking import scrape_leparking
    from scraper_autoscout import scrape_autoscout24

    platforms = tool_input.get("platforms", PLATFORMS)
    results = {"platforms_ok": [], "platforms_failed": [], "total_count": 0}
    all_listings = []

    scrapers = {
        "leboncoin": scrape_leboncoin,
        "lacentrale": scrape_lacentrale,
        "leparking": scrape_leparking,
        "autoscout24": scrape_autoscout24,
    }

    for p in platforms:
        try:
            if p in scrapers:
                listings = scrapers[p]()
                all_listings.extend(listings)
                results["platforms_ok"].append(p)
            else:
                logger.warning(f"Unknown platform: {p}")
        except Exception as e:
            logger.error(f"Scrape {p} failed: {e}")
            results["platforms_failed"].append(p)

    # Dedup by (title_lower, price, year, city_lower)
    seen = set()
    deduped = []
    for l in all_listings:
        key = (l.title.lower().strip(), l.price, l.year, (l.city or "").lower().strip())
        if key not in seen:
            seen.add(key)
            deduped.append(l)

    agent._raw_listings = deduped
    results["total_count"] = len(deduped)

    # Save raw listings
    output_path = Path(OUTPUT_DIR) / f"raw_listings_{datetime.now().strftime('%Y%m%d')}.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps([l.model_dump() for l in deduped], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Update state
    agent.state.last_scrape_at = datetime.now(timezone.utc).isoformat()
    agent.state.last_scrape_platforms = results["platforms_ok"]
    agent.state.raw_listing_count = len(deduped)
    agent.state.step = "scraped"
    save_state(agent.state, agent.state_path)

    return json.dumps(results)


def _tool_get_raw(agent: SupervisorAgent) -> str:
    if not agent._raw_listings:
        output_dir = Path(OUTPUT_DIR)
        files = sorted(output_dir.glob("raw_listings_*.json"), reverse=True)
        if files:
            data = json.loads(files[0].read_text(encoding="utf-8"))
            agent._raw_listings = [RawListing.model_validate(d) for d in data]

    summary = []
    for l in agent._raw_listings:
        summary.append({
            "id": l.id, "title": l.title, "price": l.price,
            "year": l.year, "mileage_km": l.mileage_km,
            "transmission": l.transmission, "city": l.city,
            "seller_type": l.seller_type,
        })
    return json.dumps({"count": len(summary), "listings": summary}, ensure_ascii=False)


def _tool_analyst(tool_input: dict, agent: SupervisorAgent) -> str:
    from agent_analyst import analyze_listings

    top_n = tool_input.get("top_n", 10)
    if not agent._raw_listings:
        return json.dumps({"error": "No raw listings loaded. Call get_raw_listings first."})

    pro, part = analyze_listings(agent._raw_listings, agent.llm, top_n=top_n)
    agent._shortlist_pro = pro
    agent._shortlist_part = part

    agent.state.analysis_status = "done"
    agent.state.shortlist_pro_count = len(pro)
    agent.state.shortlist_part_count = len(part)
    agent.state.step = "analyzed"
    save_state(agent.state, agent.state_path)

    return json.dumps({
        "shortlist_pro": [{"id": s.id, "score": s.score, "title": s.title, "price": s.price} for s in pro],
        "shortlist_part": [{"id": s.id, "score": s.score, "title": s.title, "price": s.price} for s in part],
    }, ensure_ascii=False)


def _tool_pricer(tool_input: dict, agent: SupervisorAgent) -> str:
    from agent_pricer import price_listings

    listing_ids = tool_input.get("listing_ids", [])
    all_scored = agent._shortlist_pro + agent._shortlist_part
    to_price = [s for s in all_scored if s.id in listing_ids]

    if not to_price:
        return json.dumps({"error": "No matching listings found for the given IDs."})

    # Save approved shortlist so CLI `price` command can re-use it
    approved_path = Path(OUTPUT_DIR) / f"approved_{datetime.now().strftime('%Y%m%d')}.json"
    approved_path.write_text(
        json.dumps([s.model_dump() for s in to_price], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    priced = price_listings(to_price, agent.llm)

    output_path = Path(OUTPUT_DIR) / f"priced_{datetime.now().strftime('%Y%m%d')}.json"
    output_path.write_text(
        json.dumps([p.model_dump() for p in priced], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    agent.state.pricing_status = "done"
    agent.state.step = "priced"
    save_state(agent.state, agent.state_path)

    result = []
    for p in priced:
        result.append({
            "id": p.id, "title": p.title,
            "market_estimate": f"{p.market_estimate_low}-{p.market_estimate_high} EUR",
            "opening_offer": p.opening_offer,
            "max_acceptable": p.max_acceptable,
            "message_digital": p.message_digital[:100] + "...",
        })
    return json.dumps(result, ensure_ascii=False)


def _tool_ask_human(tool_input: dict, agent: SupervisorAgent) -> str:
    question = tool_input.get("question", "")
    context = tool_input.get("context", "")

    # If shortlists are available, use the full HITL review interface
    if agent._shortlist_pro or agent._shortlist_part:
        source_counts = {}
        for l in agent._raw_listings:
            source_counts[l.platform] = source_counts.get(l.platform, 0) + 1

        result = run_hitl_review(
            agent._shortlist_pro,
            agent._shortlist_part,
            source_counts=source_counts,
        )

        if result["action"] == "approve":
            return json.dumps({
                "human_response": "approved",
                "approved_ids": result.get("approved_ids", []),
            })
        elif result["action"] == "rescrape":
            return json.dumps({"human_response": "rescrape"})
        elif result["action"] == "top":
            return json.dumps({"human_response": f"top {result['n']}"})
        elif result["action"] == "quit":
            return json.dumps({"human_response": "quit"})
        else:
            return json.dumps({"human_response": str(result)})

    # Fallback: simple question/answer for non-shortlist interactions
    print(f"\n[Supervisor asks]: {question}")
    if context:
        print(f"[Context]: {context}")

    try:
        response = input("> ")
        return json.dumps({"human_response": response})
    except (EOFError, KeyboardInterrupt):
        return json.dumps({"human_response": "quit"})


def _tool_notify_telegram(tool_input: dict, agent: SupervisorAgent) -> str:
    """Send a Telegram notification."""
    import asyncio
    from telegram_bot import TelegramNotifier

    message = tool_input.get("message", "")
    target = tool_input.get("target", "both")

    if not hasattr(agent, "_notifier") or agent._notifier is None:
        agent._notifier = TelegramNotifier()

    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        if target == "friend":
            loop.run_until_complete(agent._notifier.send_to_friend(message))
        elif target == "jerome":
            loop.run_until_complete(agent._notifier.send_to_jerome(message))
        else:
            loop.run_until_complete(agent._notifier.send_to_both(message))
        return json.dumps({"status": "sent", "target": target})
    except Exception as e:
        logger.error(f"Telegram notification failed: {e}")
        return json.dumps({"error": str(e)})
