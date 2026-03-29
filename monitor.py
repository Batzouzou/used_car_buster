"""Flask monitor dashboard for Toyota iQ search pipeline."""
import json
import logging
import threading
from pathlib import Path

from flask import Flask, jsonify

from config import OUTPUT_DIR

logger = logging.getLogger(__name__)


def _load_state_dict() -> dict:
    """Load state.json as dict, return empty dict on failure."""
    state_path = Path(OUTPUT_DIR) / "state.json"
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _load_latest_json(prefix: str) -> list:
    """Load most recent JSON file matching prefix_*.json, return empty list on failure."""
    output_dir = Path(OUTPUT_DIR)
    if not output_dir.exists():
        return []
    files = sorted(output_dir.glob(f"{prefix}_*.json"), reverse=True)
    if not files:
        return []
    try:
        data = json.loads(files[0].read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


DASHBOARD_HTML = """<!DOCTYPE html>
<html><head><title>Toyota iQ Monitor</title>
<meta http-equiv="refresh" content="60">
<style>
body { background: #1a1a2e; color: #e0e0e0; font-family: monospace; margin: 2em; }
h1 { color: #00d4ff; }
a { color: #00d4ff; }
table { border-collapse: collapse; width: 100%%; margin: 1em 0; }
th, td { border: 1px solid #333; padding: 6px 12px; text-align: left; }
th { background: #16213e; color: #00d4ff; }
tr:nth-child(even) { background: #0f3460; }
.stat { font-size: 1.2em; margin: 0.3em 0; }
nav { margin-bottom: 1em; }
nav a { margin-right: 1.5em; }
</style></head><body>
<h1>Toyota iQ Search Monitor</h1>
<nav>
<a href="/">Dashboard</a>
<a href="/shortlist">Shortlist</a>
<a href="/raw">Raw Listings</a>
<a href="/priced">Priced</a>
<a href="/api/state">API: State</a>
<a href="/api/listings">API: Listings</a>
</nav>
%s
</body></html>"""


def _render_listings_table(listings: list, fields: list[str]) -> str:
    """Render a list of dicts as an HTML table."""
    if not listings:
        return "<p>No data available.</p>"
    header = "".join(f"<th>{f}</th>" for f in fields)
    rows = ""
    for item in listings:
        cells = "".join(f"<td>{item.get(f, '')}</td>" for f in fields)
        rows += f"<tr>{cells}</tr>"
    return f"<table><tr>{header}</tr>{rows}</table>"


def create_monitor_app() -> Flask:
    """Create and configure the Flask monitor app."""
    app = Flask(__name__)

    @app.route("/")
    def dashboard():
        state = _load_state_dict()
        if not state:
            body = "<p>No pipeline state found. Run the pipeline first.</p>"
        else:
            body = "<h2>Pipeline State</h2>"
            for key, val in state.items():
                body += f'<p class="stat"><b>{key}:</b> {val}</p>'
        return DASHBOARD_HTML % body

    @app.route("/shortlist")
    def shortlist():
        listings = _load_latest_json("approved")
        fields = ["id", "title", "price", "year", "mileage_km", "score", "city", "seller_type"]
        table = _render_listings_table(listings, fields)
        body = f"<h2>Approved Shortlist</h2>{table}"
        return DASHBOARD_HTML % body

    @app.route("/raw")
    def raw():
        listings = _load_latest_json("raw_listings")
        fields = ["id", "platform", "title", "price", "year", "mileage_km", "city", "seller_type"]
        table = _render_listings_table(listings, fields)
        body = f"<h2>Raw Listings ({len(listings)})</h2>{table}"
        return DASHBOARD_HTML % body

    @app.route("/priced")
    def priced():
        listings = _load_latest_json("priced")
        fields = ["id", "title", "price", "market_estimate_low", "market_estimate_high",
                  "opening_offer", "max_acceptable"]
        table = _render_listings_table(listings, fields)
        body = f"<h2>Priced Listings</h2>{table}"
        return DASHBOARD_HTML % body

    @app.route("/api/state")
    def api_state():
        return jsonify(_load_state_dict())

    @app.route("/api/listings")
    def api_listings():
        return jsonify({
            "raw": _load_latest_json("raw_listings"),
            "approved": _load_latest_json("approved"),
            "priced": _load_latest_json("priced"),
        })

    return app


def start_monitor_thread(port: int = 5050) -> threading.Thread:
    """Start the monitor Flask app in a daemon thread."""
    app = create_monitor_app()

    def _run():
        app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

    thread = threading.Thread(target=_run, name="monitor", daemon=True)
    thread.start()
    logger.info(f"Monitor dashboard started on http://localhost:{port}")
    return thread
