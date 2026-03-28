"""Human-in-the-loop terminal interface for shortlist review."""
import re
from config import ORLY_LAT, ORLY_LON
from models import ScoredListing
from utils import haversine_km


def format_listing_line(listing: ScoredListing, number: int, distance_km: float | None = None) -> str:
    """Format a single listing for terminal display."""
    km_str = f"{listing.mileage_km:,} km" if listing.mileage_km else "km ?"
    price_str = f"{listing.price:,} EUR"
    dist_str = f"({distance_km:.0f} km)" if distance_km is not None else ""
    seller = listing.seller_type.upper() if listing.seller_type else "?"

    highlights = ", ".join(listing.highlights) if listing.highlights else "none"
    flags = ", ".join(listing.red_flags) if listing.red_flags else "none"

    lines = [
        f" #{number} [{listing.score}/100] {listing.year} {listing.title} -- {km_str} -- {price_str}",
        f"    {listing.city} {dist_str} | {seller}",
        f"    + {highlights} | Flags: {flags}",
        f"    {listing.url}",
    ]
    return "\n".join(lines)


def format_shortlist_display(
    pro: list[ScoredListing],
    part: list[ScoredListing],
    source_counts: dict[str, int] | None = None,
    scraped_at: str | None = None,
) -> str:
    """Format the full shortlist display for terminal."""
    lines = []
    total_filtered = len(pro) + len(part)
    src = source_counts or {}
    src_str = ", ".join(f"{k}({v})" for k, v in src.items()) if src else "?"

    lines.append("=" * 55)
    lines.append("  TOYOTA iQ AUTO -- SHORTLIST REVIEW")
    if scraped_at:
        lines.append(f"  Scraped: {scraped_at} | Sources: {src_str}")
    lines.append(f"  Showing: {total_filtered} listings")
    lines.append("=" * 55)

    lines.append("")
    lines.append(f"-- PROFESSIONNELS ({len(pro)}) " + "-" * 30)
    lines.append("")
    number = 1
    for s in pro:
        dist = _calc_distance(s)
        lines.append(format_listing_line(s, number, dist))
        lines.append("")
        number += 1

    lines.append(f"-- PARTICULIERS ({len(part)}) " + "-" * 30)
    lines.append("")
    for s in part:
        dist = _calc_distance(s)
        lines.append(format_listing_line(s, number, dist))
        lines.append("")
        number += 1

    lines.append("=" * 55)
    lines.append("COMMANDS:")
    lines.append("  ok          -> approve all, proceed to pricing")
    lines.append("  ok 1,3,7    -> approve only these numbers")
    lines.append("  drop 2,4    -> remove these numbers")
    lines.append("  details N   -> show full description")
    lines.append("  rescrape    -> re-run scrapers")
    lines.append("  top N       -> change shortlist size")
    lines.append("  quit        -> exit")
    lines.append("=" * 55)

    return "\n".join(lines)


def parse_hitl_command(user_input: str) -> dict:
    """Parse user command from terminal input."""
    text = user_input.strip().lower()

    if text == "ok":
        return {"action": "approve_all"}

    if text.startswith("ok "):
        nums = _parse_numbers(text[3:])
        return {"action": "approve", "numbers": nums}

    if text.startswith("drop "):
        nums = _parse_numbers(text[5:])
        return {"action": "drop", "numbers": nums}

    if text.startswith("details "):
        try:
            n = int(text.split()[1])
            return {"action": "details", "number": n}
        except (ValueError, IndexError):
            return {"action": "unknown"}

    if text == "rescrape":
        return {"action": "rescrape"}

    if text.startswith("top "):
        try:
            n = int(text.split()[1])
            return {"action": "top", "n": n}
        except (ValueError, IndexError):
            return {"action": "unknown"}

    if text == "quit":
        return {"action": "quit"}

    return {"action": "unknown"}


def _parse_numbers(text: str) -> list[int]:
    """Parse comma-separated numbers from text."""
    return [int(x.strip()) for x in text.split(",") if x.strip().isdigit()]


def _calc_distance(listing: ScoredListing) -> float | None:
    """Calculate distance from Orly if GPS coordinates available."""
    if listing.lat is not None and listing.lon is not None:
        return haversine_km(ORLY_LAT, ORLY_LON, listing.lat, listing.lon)
    return None


def run_hitl_review(
    pro: list[ScoredListing],
    part: list[ScoredListing],
    source_counts: dict[str, int] | None = None,
) -> dict:
    """Interactive HITL review loop. Returns command dict with approved IDs."""
    display = format_shortlist_display(pro, part, source_counts)
    print(display)

    all_listings = pro + part

    while True:
        try:
            user_input = input("> ")
        except (EOFError, KeyboardInterrupt):
            return {"action": "quit"}

        cmd = parse_hitl_command(user_input)

        if cmd["action"] == "approve_all":
            return {"action": "approve", "approved_ids": [l.id for l in all_listings]}

        elif cmd["action"] == "approve":
            ids = []
            for n in cmd["numbers"]:
                idx = n - 1
                if 0 <= idx < len(all_listings):
                    ids.append(all_listings[idx].id)
            return {"action": "approve", "approved_ids": ids}

        elif cmd["action"] == "drop":
            for n in sorted(cmd["numbers"], reverse=True):
                idx = n - 1
                if 0 <= idx < len(all_listings):
                    all_listings.pop(idx)
            new_pro = [l for l in all_listings if l.seller_type == "pro"]
            new_part = [l for l in all_listings if l.seller_type != "pro"]
            display = format_shortlist_display(new_pro, new_part, source_counts)
            print(display)

        elif cmd["action"] == "details":
            idx = cmd["number"] - 1
            if 0 <= idx < len(all_listings):
                l = all_listings[idx]
                print(f"\n--- Details #{cmd['number']} ---")
                print(f"Title: {l.title}")
                print(f"Description: {l.description or 'N/A'}")
                print(f"Summary: {l.summary_fr}")
                print(f"Score breakdown: {l.score_breakdown.model_dump()}")
                print(f"URL: {l.url}")
                print("---\n")

        elif cmd["action"] == "rescrape":
            return {"action": "rescrape"}

        elif cmd["action"] == "top":
            return {"action": "top", "n": cmd["n"]}

        elif cmd["action"] == "quit":
            return {"action": "quit"}

        else:
            print("Unknown command. Type 'ok', 'ok 1,3', 'drop 2', 'details 3', 'rescrape', 'top N', or 'quit'.")
