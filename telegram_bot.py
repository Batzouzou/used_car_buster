# telegram_bot.py
"""Telegram bot pour la recherche Toyota iQ."""
import logging
import re
from datetime import datetime, timezone

from telegram import Update, Bot
from telegram.ext import Application, CommandHandler, ContextTypes

from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_FRIEND_CHAT_ID, TELEGRAM_JEROME_CHAT_ID,
    MIN_INTERVAL_HOURS, MAX_INTERVAL_HOURS, ORLY_LAT, ORLY_LON,
)
from models import ScoredListing
from utils import haversine_km

logger = logging.getLogger(__name__)


def format_listing_telegram(listing: ScoredListing, number: int) -> str:
    """Format a single listing for Telegram display (plain text, no markdown)."""
    km_str = f"{listing.mileage_km:,} km" if listing.mileage_km else "km ?"
    price_str = f"{listing.price:,} EUR"

    dist = None
    if listing.lat and listing.lon:
        dist = haversine_km(ORLY_LAT, ORLY_LON, listing.lat, listing.lon)
    dist_str = f"({dist:.0f} km d'Orly)" if dist else ""

    highlights = ", ".join(listing.highlights) if listing.highlights else "-"
    flags = ", ".join(listing.red_flags) if listing.red_flags else "-"

    lines = [
        f"#{number} [{listing.score}/100] {listing.year} {listing.title}",
        f"  {km_str} - {price_str}",
        f"  {listing.city} {dist_str}",
        f"  + {highlights}",
        f"  Alertes: {flags}",
        f"  {listing.url}",
    ]
    return "\n".join(lines)


def format_shortlist_telegram(
    pro: list[ScoredListing],
    part: list[ScoredListing],
) -> str:
    """Format full shortlist for Telegram (plain text, global numbering)."""
    lines = []
    number = 1

    if pro:
        lines.append("=== PROFESSIONNELS ===")
        for listing in pro:
            lines.append(format_listing_telegram(listing, number))
            lines.append("")
            number += 1

    if part:
        lines.append("=== PARTICULIERS ===")
        for listing in part:
            lines.append(format_listing_telegram(listing, number))
            lines.append("")
            number += 1

    if not pro and not part:
        lines.append("Aucune annonce dans la shortlist.")

    return "\n".join(lines)


def parse_interval(text: str) -> float | None:
    """Parse interval string like '4h', '1j', '1s' into hours. Returns None if invalid."""
    text = text.strip().lower()

    match = re.match(r"^(\d+(?:\.\d+)?)\s*(h|j|s|m)$", text)
    if not match:
        return None

    value = float(match.group(1))
    unit = match.group(2)

    if unit == "h":
        hours = value
    elif unit == "j":
        hours = value * 24
    elif unit == "s":
        hours = value * 168
    elif unit == "m":
        hours = value / 60
    else:
        return None

    if hours < MIN_INTERVAL_HOURS or hours > MAX_INTERVAL_HOURS:
        return None

    return hours


class TelegramNotifier:
    """Envoi de messages vers les chats Telegram."""

    def __init__(self, token: str = "", friend_chat_id: str = "", jerome_chat_id: str = ""):
        self.token = token or TELEGRAM_BOT_TOKEN
        self.friend_chat_id = friend_chat_id or TELEGRAM_FRIEND_CHAT_ID
        self.jerome_chat_id = jerome_chat_id or TELEGRAM_JEROME_CHAT_ID
        self.bot = Bot(token=self.token) if self.token else None

    async def send_to_friend(self, text: str) -> None:
        if self.bot and self.friend_chat_id:
            try:
                await self.bot.send_message(chat_id=self.friend_chat_id, text=text)
            except Exception as e:
                logger.error(f"Echec envoi ami: {e}")

    async def send_to_jerome(self, text: str) -> None:
        if self.bot and self.jerome_chat_id:
            try:
                await self.bot.send_message(chat_id=self.jerome_chat_id, text=text)
            except Exception as e:
                logger.error(f"Echec envoi Jerome: {e}")

    async def send_to_both(self, text: str) -> None:
        await self.send_to_friend(text)
        await self.send_to_jerome(text)


# --- Commandes ---

async def cmd_demarrer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Bot de recherche Toyota iQ\n\n"
        "/chercher - Lancer une recherche\n"
        "/liste - Voir la shortlist actuelle\n"
        "/approuver 1,3,5 - Approuver des annonces\n"
        "/rejeter 2,4 - Rejeter des annonces\n"
        "/details 3 - Details d'une annonce\n"
        "/intervalle 4h - Changer la frequence\n"
        "/statut - Etat du pipeline"
    )


async def cmd_chercher(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Lancement de la recherche... Patience.")
    context.application.bot_data.setdefault("pending_search", True)


async def cmd_liste(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    shortlist_text = context.application.bot_data.get("last_shortlist", "Pas de shortlist disponible.")
    await update.message.reply_text(shortlist_text)


async def cmd_approuver(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /approuver 1,3,5")
        return
    try:
        numbers = [int(n.strip()) for n in " ".join(args).split(",")]
        approved = context.application.bot_data.setdefault("approved_numbers", [])
        approved.extend(numbers)
        await update.message.reply_text(f"Approuve: {numbers}")
    except ValueError:
        await update.message.reply_text("Numeros invalides. Usage: /approuver 1,3,5")


async def cmd_rejeter(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /rejeter 2,4")
        return
    try:
        numbers = [int(n.strip()) for n in " ".join(args).split(",")]
        rejected = context.application.bot_data.setdefault("rejected_numbers", [])
        rejected.extend(numbers)
        await update.message.reply_text(f"Rejete: {numbers}")
    except ValueError:
        await update.message.reply_text("Numeros invalides. Usage: /rejeter 2,4")


async def cmd_details(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /details 3")
        return
    await update.message.reply_text(f"Details pour #{args[0]} (bientot disponible)")


async def cmd_intervalle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /intervalle 4h (min 1h, max 1s)\n  h=heures, j=jours, s=semaine")
        return
    hours = parse_interval(args[0])
    if hours is None:
        await update.message.reply_text(f"Intervalle invalide. Min {MIN_INTERVAL_HOURS}h, max {MAX_INTERVAL_HOURS}h.")
        return
    context.application.bot_data["interval_hours"] = hours
    await update.message.reply_text(f"Intervalle mis a jour: {hours}h")


async def cmd_statut(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from state import load_state
    from config import OUTPUT_DIR
    from pathlib import Path
    state = load_state(str(Path(OUTPUT_DIR) / "state.json"))
    step_fr = {
        "init": "initial", "scrape": "scrape", "analyze": "analyse",
        "hitl": "validation", "price": "pricing", "done": "termine",
    }.get(state.step, state.step)
    status_fr = {"pending": "en attente", "done": "termine", "running": "en cours", "failed": "echoue"}
    await update.message.reply_text(
        f"Etape: {step_fr}\n"
        f"Dernier scrape: {state.last_scrape_at or 'jamais'}\n"
        f"Annonces brutes: {state.raw_listing_count}\n"
        f"Analyse: {status_fr.get(state.analysis_status, state.analysis_status)}\n"
        f"Pricing: {status_fr.get(state.pricing_status, state.pricing_status)}"
    )


async def post_init(app: Application) -> None:
    from telegram import BotCommand
    await app.bot.set_my_commands([
        BotCommand("chercher", "Lancer une recherche"),
        BotCommand("liste", "Voir la shortlist"),
        BotCommand("approuver", "Approuver des annonces"),
        BotCommand("rejeter", "Rejeter des annonces"),
        BotCommand("details", "Details d'une annonce"),
        BotCommand("intervalle", "Changer la frequence"),
        BotCommand("statut", "Etat du pipeline"),
    ])


def build_application() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", cmd_demarrer))
    app.add_handler(CommandHandler("chercher", cmd_chercher))
    app.add_handler(CommandHandler("liste", cmd_liste))
    app.add_handler(CommandHandler("approuver", cmd_approuver))
    app.add_handler(CommandHandler("rejeter", cmd_rejeter))
    app.add_handler(CommandHandler("details", cmd_details))
    app.add_handler(CommandHandler("intervalle", cmd_intervalle))
    app.add_handler(CommandHandler("statut", cmd_statut))

    return app
