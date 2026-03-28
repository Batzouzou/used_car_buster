# run.py
"""CLI entry point for Toyota iQ search pipeline."""
import atexit
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path

from config import OUTPUT_DIR

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

logger = logging.getLogger(__name__)

PID_FILE = Path(OUTPUT_DIR) / "bot.pid"


def _is_pid_alive(pid: int) -> bool:
    """Check if a process with given PID is still running."""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def _kill_old_instance() -> None:
    """Kill any existing bot instance using PID file."""
    if not PID_FILE.exists():
        return
    try:
        old_pid = int(PID_FILE.read_text().strip())
    except (ValueError, OSError):
        PID_FILE.unlink(missing_ok=True)
        return
    if old_pid == os.getpid():
        return
    if _is_pid_alive(old_pid):
        logger.warning(f"Killing old bot instance (PID {old_pid})")
        try:
            os.kill(old_pid, signal.SIGTERM)
            for _ in range(30):  # wait up to 3s
                time.sleep(0.1)
                if not _is_pid_alive(old_pid):
                    break
            else:
                os.kill(old_pid, signal.SIGKILL)
        except OSError:
            pass
    PID_FILE.unlink(missing_ok=True)


def _write_pid() -> None:
    """Write current PID to lock file."""
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))
    atexit.register(lambda: PID_FILE.unlink(missing_ok=True))


def main(argv: list[str] | None = None):
    args = argv or sys.argv
    command = args[1] if len(args) > 1 else "run"

    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    if command == "run":
        from agent_supervisor import SupervisorAgent
        from scheduler import PipelineScheduler
        from telegram_bot import build_application

        _kill_old_instance()
        _write_pid()

        def run_pipeline():
            agent = SupervisorAgent()
            agent.run()

        # Start scheduler
        scheduler = PipelineScheduler(run_pipeline_fn=run_pipeline)
        scheduler.start()

        # Start Telegram bot (blocking — runs event loop)
        app = build_application()
        app.bot_data["scheduler"] = scheduler
        app.run_polling()

    elif command == "scrape":
        from scraper_lbc import scrape_leboncoin
        from scraper_lacentrale import scrape_lacentrale
        from scraper_leparking import scrape_leparking
        from scraper_autoscout import scrape_autoscout24
        from datetime import datetime

        print("Scraping LeBonCoin...")
        lbc = scrape_leboncoin()
        print(f"  LBC: {len(lbc)} listings")

        print("Scraping La Centrale...")
        lc = scrape_lacentrale()
        print(f"  LC: {len(lc)} listings")

        print("Scraping Le Parking...")
        lp = scrape_leparking()
        print(f"  LP: {len(lp)} listings")

        print("Scraping AutoScout24...")
        asc = scrape_autoscout24()
        print(f"  AS: {len(asc)} listings")

        all_listings = lbc + lc + lp + asc
        output = Path(OUTPUT_DIR) / f"raw_listings_{datetime.now().strftime('%Y%m%d')}.json"
        output.write_text(
            json.dumps([l.model_dump() for l in all_listings], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Saved {len(all_listings)} listings to {output}")

    elif command == "analyze":
        from agent_analyst import analyze_listings
        from llm_client import LLMClient
        from models import RawListing

        files = sorted(Path(OUTPUT_DIR).glob("raw_listings_*.json"), reverse=True)
        if not files:
            print("No raw listings found. Run 'scrape' first.")
            return
        data = json.loads(files[0].read_text(encoding="utf-8"))
        listings = [RawListing.model_validate(d) for d in data]
        print(f"Loaded {len(listings)} listings from {files[0].name}")

        client = LLMClient()
        pro, part = analyze_listings(listings, client)
        print(f"Shortlist: {len(pro)} pro, {len(part)} particulier")

    elif command == "price":
        from agent_pricer import price_listings
        from llm_client import LLMClient
        from models import ScoredListing

        files = sorted(Path(OUTPUT_DIR).glob("shortlist_approved_*.json"), reverse=True)
        if not files:
            print("No approved shortlist found. Run full pipeline first.")
            return
        data = json.loads(files[0].read_text(encoding="utf-8"))
        listings = [ScoredListing.model_validate(d) for d in data]

        client = LLMClient()
        priced = price_listings(listings, client)
        print(f"Priced {len(priced)} listings")

    elif command == "status":
        from state import load_state
        state = load_state(str(Path(OUTPUT_DIR) / "state.json"))
        print(state.model_dump_json(indent=2))

    else:
        print(f"Unknown command: {command}")
        print("Usage: python run.py [run|scrape|analyze|price|status]")


if __name__ == "__main__":
    main()
