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

from config import MONITOR_PORT, OUTPUT_DIR

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


def _build_listing_card(i, l, orly_lat, orly_lon, haversine_km):
    """Build one HTML card for a listing."""
    dist = ""
    if l.lat and l.lon:
        km = haversine_km(orly_lat, orly_lon, l.lat, l.lon)
        dist = f"{km:.0f} km d'Orly"

    imgs_html = ""
    for img_url in (l.images or [])[:6]:
        imgs_html += f'<img src="{img_url}" loading="lazy">'

    km_str = f"{l.mileage_km:,} km".replace(",", " ") if l.mileage_km else "? km"
    phone_icon = '<span class="phone" title="Telephone disponible">&#128222;</span>' if getattr(l, "has_phone", False) else ""
    pro_badge = '<span class="pro-badge">PRO</span>' if l.seller_type == "pro" else ""
    suspected = '<span class="suspected-badge" title="Detecte via mots-cles annonce">suspect pro</span>' if getattr(l, "suspected_pro", False) and l.seller_type == "pro" else ""

    name = getattr(l, "seller_name", None) or ""
    phone = getattr(l, "seller_phone", None)

    seller_line = f'<span class="seller-name">{name}</span>' if name else ""

    phone_btn = ""
    if phone:
        phone_btn = f'<a href="tel:{phone}" class="btn btn-phone">&#128222; {phone}</a>'

    contact_btn = f'<a href="{l.url}" target="_blank" class="btn btn-contact">&#9993; Contacter</a>'

    return f"""
    <div class="card">
      <div class="header">
        <span class="num">#{i}</span>
        <span class="price">{l.price:,} &euro;</span>
        <span class="year">{l.year}</span>
        <span class="km">{km_str}</span>
        <span class="loc">{l.city or '?'} ({l.department or '?'}) &mdash; {dist}</span>
        <span class="platform">{l.platform}</span>
        {pro_badge}{suspected}
      </div>
      <div class="title"><a href="{l.url}" target="_blank">{l.title}</a></div>
      <div class="actions">{seller_line} {phone_btn} {contact_btn}</div>
      <div class="photos">{imgs_html}</div>
      <div class="desc">{(l.description or '')[:500]}</div>
    </div>"""


def _build_html(listings) -> str:
    """Build an HTML page split into Pro / Particulier sections with photos."""
    from config import ORLY_LAT, ORLY_LON
    from utils import haversine_km

    pros = sorted([l for l in listings if l.seller_type == "pro"], key=lambda x: x.price)
    parts = sorted([l for l in listings if l.seller_type != "pro"], key=lambda x: x.price)

    pro_html = ""
    for i, l in enumerate(pros, 1):
        pro_html += _build_listing_card(i, l, ORLY_LAT, ORLY_LON, haversine_km)

    # Particuliers numbering continues after pros (global numbering)
    part_html = ""
    for i, l in enumerate(parts, len(pros) + 1):
        part_html += _build_listing_card(i, l, ORLY_LAT, ORLY_LON, haversine_km)

    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8">
<title>Toyota iQ Auto &mdash; {len(listings)} annonces</title>
<style>
  body {{ font-family: system-ui, sans-serif; background: #1a1a2e; color: #e0e0e0; margin: 20px; }}
  h1 {{ color: #00d4ff; }}
  h2 {{ color: #ff9f43; margin-top: 40px; border-bottom: 1px solid #333; padding-bottom: 8px; }}
  .card {{ background: #16213e; border-radius: 10px; padding: 16px; margin-bottom: 20px; }}
  .header {{ display: flex; gap: 16px; flex-wrap: wrap; align-items: center; margin-bottom: 8px; }}
  .num {{ color: #888; font-weight: bold; }}
  .price {{ color: #00ff88; font-size: 1.3em; font-weight: bold; }}
  .year, .km, .loc {{ color: #aaa; }}
  .phone {{ font-size: 1.2em; }}
  .platform {{ background: #2d3a5e; color: #7eb8da; padding: 2px 8px; border-radius: 4px; font-size: 0.75em; text-transform: uppercase; }}
  .actions {{ display: flex; align-items: center; gap: 12px; margin: 8px 0; flex-wrap: wrap; }}
  .seller-name {{ color: #e8b84a; font-size: 0.95em; }}
  .btn {{ display: inline-block; padding: 10px 20px; border-radius: 8px; text-decoration: none; font-weight: bold; font-size: 1em; cursor: pointer; }}
  .btn-phone {{ background: #00cc66; color: #000; }}
  .btn-phone:hover {{ background: #00ff88; }}
  .btn-contact {{ background: #0088cc; color: #fff; }}
  .btn-contact:hover {{ background: #00aaff; }}
  .pro-badge {{ background: #ff6b6b; color: #fff; padding: 2px 8px; border-radius: 4px; font-size: 0.8em; font-weight: bold; }}
  .suspected-badge {{ background: #f59e0b; color: #000; padding: 2px 6px; border-radius: 4px; font-size: 0.75em; }}
  .title a {{ color: #00d4ff; text-decoration: none; font-size: 1.1em; }}
  .title a:hover {{ text-decoration: underline; }}
  .photos {{ display: flex; gap: 8px; overflow-x: auto; padding: 10px 0; }}
  .photos img {{ height: 180px; border-radius: 6px; object-fit: cover; flex-shrink: 0; }}
  .desc {{ color: #999; font-size: 0.9em; white-space: pre-wrap; margin-top: 8px; }}
  .count {{ color: #888; font-weight: normal; font-size: 0.8em; }}
</style></head><body>
<h1>Toyota iQ Automatique &mdash; {len(listings)} annonces</h1>
<p>Tri par prix croissant | Photos: max 6 par annonce</p>

<h2>Professionnels <span class="count">({len(pros)})</span></h2>
{pro_html if pro_html else '<p style="color:#666">Aucune annonce professionnelle</p>'}

<h2>Particuliers <span class="count">({len(parts)})</span></h2>
{part_html}

</body></html>"""


def main(argv: list[str] | None = None):
    args = argv or sys.argv
    command = args[1] if len(args) > 1 else "run"

    Path(OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    if command == "run":
        from agent_supervisor import SupervisorAgent
        from monitor import start_monitor_thread
        from scheduler import PipelineScheduler
        from telegram_bot import build_application

        _kill_old_instance()
        _write_pid()

        def run_pipeline():
            agent = SupervisorAgent()
            agent.run()

        # Start monitor dashboard (daemon thread)
        start_monitor_thread(port=MONITOR_PORT)

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
        # Dedup by (title_lower, price, year, city_lower) — same logic as supervisor
        seen = set()
        deduped = []
        for l in all_listings:
            key = (l.title.lower().strip(), l.price, l.year, (l.city or "").lower().strip())
            if key not in seen:
                seen.add(key)
                deduped.append(l)
        removed = len(all_listings) - len(deduped)
        if removed:
            print(f"  Dedup: removed {removed} duplicates")
        output = Path(OUTPUT_DIR) / f"raw_listings_{datetime.now().strftime('%Y%m%d')}.json"
        output.write_text(
            json.dumps([l.model_dump() for l in deduped], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"Saved {len(deduped)} listings to {output}")

        # Generate HTML viewer with photos
        html_path = Path(OUTPUT_DIR) / f"listings_{datetime.now().strftime('%Y%m%d')}.html"
        html_path.write_text(_build_html(deduped), encoding="utf-8")
        print(f"HTML viewer: {html_path}")
        os.startfile(str(html_path))

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

        # Save approved shortlist for pricing step
        approved = pro + part
        if approved:
            from datetime import datetime as dt
            approved_path = Path(OUTPUT_DIR) / f"approved_{dt.now().strftime('%Y%m%d')}.json"
            approved_path.write_text(
                json.dumps([s.model_dump() for s in approved], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"Saved {len(approved)} approved to {approved_path.name}")

            # Generate scored HTML
            html_path = Path(OUTPUT_DIR) / f"shortlist_{dt.now().strftime('%Y%m%d')}.html"
            html_path.write_text(_build_html(approved), encoding="utf-8")
            print(f"Shortlist HTML: {html_path}")
            os.startfile(str(html_path))

    elif command == "price":
        from agent_pricer import price_listings
        from llm_client import LLMClient
        from models import ScoredListing

        files = sorted(Path(OUTPUT_DIR).glob("approved_*.json"), reverse=True)
        if not files:
            print("No approved shortlist found. Run full pipeline first.")
            return
        data = json.loads(files[0].read_text(encoding="utf-8"))
        listings = [ScoredListing.model_validate(d) for d in data]

        client = LLMClient()
        priced = price_listings(listings, client)
        print(f"Priced {len(priced)} listings")

        if priced:
            from datetime import datetime as dt
            priced_path = Path(OUTPUT_DIR) / f"priced_{dt.now().strftime('%Y%m%d')}.json"
            priced_path.write_text(
                json.dumps([p.model_dump() for p in priced], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"Saved to {priced_path.name}")

            # Print summary
            for p in priced:
                km = f"{p.mileage_km:,}km".replace(",", " ") if p.mileage_km else "?"
                print(f"\n  {p.id}  {p.price:,} EUR  {p.year}  {km}  score:{p.score}")
                print(f"  Marche: {p.market_estimate_low}-{p.market_estimate_high} EUR")
                print(f"  Offre: {p.opening_offer} EUR | Max: {p.max_acceptable} EUR")
                print(f"  Ancres: {', '.join(p.anchors[:2])}")

    elif command == "status":
        from state import load_state
        state = load_state(str(Path(OUTPUT_DIR) / "state.json"))
        print(state.model_dump_json(indent=2))

    else:
        print(f"Unknown command: {command}")
        print("Usage: python run.py [run|scrape|analyze|price|status]")


if __name__ == "__main__":
    main()
