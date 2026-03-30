# telegram_bot.py
"""Telegram bot pour la recherche Toyota iQ."""
import json
import logging
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

from telegram import Update, Bot, InputMediaPhoto, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters

from config import (
    TELEGRAM_BOT_TOKEN, TELEGRAM_FRIEND_CHAT_ID, TELEGRAM_JEROME_CHAT_ID,
    MIN_INTERVAL_HOURS, MAX_INTERVAL_HOURS, ORLY_LAT, ORLY_LON, OUTPUT_DIR,
)
from models import RawListing, ScoredListing
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


SCORE_THRESHOLD = 50  # Minimum score to auto-notify


def format_listing_notification(listing: ScoredListing, number: int) -> str:
    """Format a scored listing for Telegram notification (plain text FR)."""
    km_str = f"{listing.mileage_km:,} km".replace(",", " ") if listing.mileage_km else "km ?"
    price_str = f"{listing.price:,} EUR".replace(",", " ")

    dist = ""
    if listing.lat and listing.lon:
        d = haversine_km(ORLY_LAT, ORLY_LON, listing.lat, listing.lon)
        dist = f"{d:.0f} km d'Orly"

    seller_name = getattr(listing, "seller_name", None) or ""
    seller_phone = getattr(listing, "seller_phone", None)
    phone_line = f"\nTel: {seller_phone}" if seller_phone else ""

    seller_label = "Pro" if listing.seller_type == "pro" else "Particulier"

    # Analyse detaillee
    plus = ""
    if listing.highlights:
        plus = "\n+ " + ", ".join(listing.highlights[:5])
    moins = ""
    if listing.concerns:
        moins = "\n- " + ", ".join(listing.concerns[:5])
    alertes = ""
    if listing.red_flags:
        alertes = "\n!! " + ", ".join(listing.red_flags[:3])
    summary = ""
    if getattr(listing, "summary_fr", ""):
        summary = f"\n\n🤖 Analyse IA :\n{listing.summary_fr}"

    platform_tag = {"leboncoin": "LBC", "autoscout24": "AutoScout", "lacentrale": "LaCentrale", "leparking": "LeParking"}.get(listing.platform, listing.platform)

    # Stars based on score: 90+=5, 75+=4, 60+=3, 50+=2, else 1
    if listing.score >= 90:
        stars = "⭐⭐⭐⭐⭐"
    elif listing.score >= 75:
        stars = "⭐⭐⭐⭐"
    elif listing.score >= 60:
        stars = "⭐⭐⭐"
    elif listing.score >= 50:
        stars = "⭐⭐"
    else:
        stars = "⭐"

    return (
        f"#{number} {stars} {listing.score}/100\n"
        f"📌 {platform_tag}\n"
        f"{listing.title}\n"
        f"💰 {price_str} | 📅 {listing.year} | 🛣️ {km_str}\n"
        f"📍 {listing.city or '?'} ({listing.department or '?'}) {dist}\n"
        f"👤 {seller_label}: {seller_name}{phone_line}"
        f"{plus}{moins}{alertes}{summary}"
    )


class TelegramNotifier:
    """Envoi de messages vers les chats Telegram."""

    def __init__(self, token: str = "", friend_chat_id: str = "", jerome_chat_id: str = ""):
        self.token = token or TELEGRAM_BOT_TOKEN
        self.friend_chat_id = friend_chat_id or TELEGRAM_FRIEND_CHAT_ID
        self.jerome_chat_id = jerome_chat_id or TELEGRAM_JEROME_CHAT_ID
        self.bot = Bot(token=self.token) if self.token else None
        self.sent_message_ids: dict[str, list[int]] = {}  # chat_id → [msg_ids]

    async def send_to_friend(self, text: str) -> None:
        if self.bot and self.friend_chat_id:
            try:
                await self.bot.send_message(chat_id=self.friend_chat_id, text=text)
            except Exception as e:
                logger.error(f"Echec envoi ami: {e}")

    def _track(self, chat_id: str, msg) -> None:
        """Track sent message ID for later cleanup."""
        if msg and hasattr(msg, "message_id"):
            self.sent_message_ids.setdefault(chat_id, []).append(msg.message_id)

    async def send_to_jerome(self, text: str) -> None:
        if self.bot and self.jerome_chat_id:
            try:
                msg = await self.bot.send_message(chat_id=self.jerome_chat_id, text=text)
                self._track(self.jerome_chat_id, msg)
            except Exception as e:
                logger.error(f"Echec envoi Jerome: {e}")

    async def send_to_both(self, text: str) -> None:
        await self.send_to_friend(text)
        await self.send_to_jerome(text)

    async def send_listing_with_photo(self, chat_id: str, listing: ScoredListing, number: int) -> None:
        """Send a listing with its main photo + caption to a chat."""
        if not self.bot or not chat_id:
            return
        caption = format_listing_notification(listing, number)
        photo_url = listing.images[0] if listing.images else None
        phone = getattr(listing, "seller_phone", None)

        # Build inline keyboard buttons
        buttons = []
        buttons.append([InlineKeyboardButton("🚗 ➤ VOIR L'ANNONCE ➤ 🚗", url=listing.url)])
        if phone:
            buttons.append([InlineKeyboardButton(f"📞 APPELER : {phone}", url=f"tel:{phone}")])
        buttons.append([InlineKeyboardButton("🗑️ Pas interessant", callback_data=f"trash_{listing.id}")])
        keyboard = InlineKeyboardMarkup(buttons)

        try:
            if photo_url:
                msg = await self.bot.send_photo(
                    chat_id=chat_id, photo=photo_url, caption=caption,
                    reply_markup=keyboard,
                )
            else:
                msg = await self.bot.send_message(
                    chat_id=chat_id, text=caption,
                    reply_markup=keyboard,
                )
            self._track(chat_id, msg)
        except Exception as e:
            logger.error(f"Echec envoi listing {listing.id}: {e}")
            try:
                await self.bot.send_message(chat_id=chat_id, text=caption)
            except Exception:
                pass

    async def notify_shortlist(self, listings: list[ScoredListing], max_results: int = 10) -> None:
        """Send top listings (score >= SCORE_THRESHOLD, max 10) to Jerome with full analysis."""
        top = sorted(
            [l for l in listings if l.score >= SCORE_THRESHOLD],
            key=lambda x: x.score, reverse=True,
        )[:max_results]

        if not top:
            logger.info("No listings above score threshold, skipping Telegram notification")
            return

        header = (
            f"Toyota iQ Auto - TOP {len(top)} annonces\n"
            f"Recherche du {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
            f"Score minimum: {SCORE_THRESHOLD}/100"
        )
        await self.send_to_both(header)
        for i, listing in enumerate(top, 1):
            await self.send_listing_with_photo(self.friend_chat_id, listing, i)
            await self.send_listing_with_photo(self.jerome_chat_id, listing, i)

    async def delete_sent_messages(self, chat_id: str) -> int:
        """Delete all tracked messages in a chat. Returns count deleted."""
        if not self.bot or not chat_id:
            return 0
        msg_ids = self.sent_message_ids.pop(chat_id, [])
        deleted = 0
        for mid in msg_ids:
            try:
                await self.bot.delete_message(chat_id=chat_id, message_id=mid)
                deleted += 1
            except Exception:
                pass  # message already deleted or too old (>48h)
        return deleted


# Shared notifier instance for tracking message IDs across commands
_notifier: TelegramNotifier | None = None


def _get_notifier() -> TelegramNotifier:
    global _notifier
    if _notifier is None:
        _notifier = TelegramNotifier()
    return _notifier


# --- Commandes ---

async def cmd_demarrer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "🚗✨ Bienvenue sur cet outil magnifique et transcendantal "
        "qui vous livrera la iQ de vos reves, au meilleur prix ! ✨🚗\n\n"
        "🤖 Ce bot parcourt LeBonCoin et AutoScout24 a votre place, "
        "analyse chaque annonce, note les points forts et les pieges, "
        "et vous envoie uniquement la creme de la creme avec photos 📸\n\n"
        "Plus besoin de passer des heures a scroller — "
        "asseyez-vous, on s'occupe de tout 😎🏖️\n\n"
        "Pour commencer : tapez un mot et appuyez sur Envoyer "
        "(comme si vous envoyiez des bisous a Joanna 😘💖)"
    )
    await update.message.reply_text(
        "📋 GUIDE DU SURFEUR D'ARGENT 🏄‍♂️\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🔍 chercher\n"
        "→ Lance la recherche sur LeBonCoin + AutoScout24\n"
        "→ Vous recevez le TOP 10 avec photos 📸\n\n"
        "📋 liste\n"
        "→ Renvoie les dernieres annonces trouvees\n\n"
        "🔎 details 3\n"
        "→ Toutes les photos + description de l'annonce #3\n\n"
        "✅ approuver 1,3\n"
        "→ Garder les annonces #1 et #3\n\n"
        "❌ rejeter 2\n"
        "→ Supprimer l'annonce #2 de la liste\n\n"
        "🧹 effacer\n"
        "→ Nettoyer les messages du bot\n\n"
        "⏰ intervalle 4h\n"
        "→ Recherche auto toutes les 4 heures\n"
        "→ Aussi : 1j (par jour), 1s (par semaine)\n\n"
        "📊 statut\n"
        "→ Voir ou en est la recherche\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 Pas besoin du / devant les commandes !\n"
        "Tapez juste le mot et envoyez 🚀\n\n"
        "🏷️ Chaque annonce montre :\n"
        "📸 Photo | 💰 Prix | 📅 Annee | 🛣️ Km\n"
        "📍 Ville + distance d'Orly\n"
        "👤 Vendeur + 📞 telephone si dispo\n"
        "👍 Points forts | 👎 Points faibles\n"
        "🔗 Lien direct vers l'annonce\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 Bot Tarek IQ v0.2.0\n"
        "Bonne route et bonne chasse ! 🚗💨"
    )


async def cmd_chercher(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text("🔍 C'est parti ! Je fouille LeBonCoin et AutoScout24 pour vous... 🕵️‍♂️\nPatience, ca prend 2-3 minutes ☕")

    try:
        # Scrape
        from scraper_lbc import scrape_leboncoin
        from scraper_lacentrale import scrape_lacentrale
        from scraper_leparking import scrape_leparking
        from scraper_autoscout import scrape_autoscout24

        all_listings = scrape_leboncoin() + scrape_lacentrale() + scrape_leparking() + scrape_autoscout24()

        # Dedup
        seen = set()
        deduped = []
        for l in all_listings:
            key = (l.title.lower().strip(), l.price, l.year, (l.city or "").lower().strip())
            if key not in seen:
                seen.add(key)
                deduped.append(l)

        await update.message.reply_text(f"🎣 {len(deduped)} annonces trouvees ! J'analyse tout ca... 🧠")

        # Save raw
        raw_path = Path(OUTPUT_DIR) / f"raw_listings_{datetime.now().strftime('%Y%m%d')}.json"
        raw_path.write_text(
            json.dumps([l.model_dump() for l in deduped], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Analyze (run in thread to keep Telegram responsive)
        from agent_analyst import analyze_listings
        from llm_client import LLMClient
        import asyncio, concurrent.futures

        client = LLMClient()
        loop = asyncio.get_event_loop()

        # Send patience message after 30s
        async def _send_patience():
            await asyncio.sleep(30)
            try:
                await update.message.reply_text("⏳ Bougez pas, ca vient... l'IA mouline ! 🤖💭")
            except Exception:
                pass
        patience_task = asyncio.create_task(_send_patience())

        # Run blocking analysis in thread pool
        with concurrent.futures.ThreadPoolExecutor() as pool:
            pro, part = await loop.run_in_executor(
                pool, lambda: analyze_listings(deduped, client)
            )
        patience_task.cancel()
        approved = pro + part

        # Save approved
        if approved:
            approved_path = Path(OUTPUT_DIR) / f"approved_{datetime.now().strftime('%Y%m%d')}.json"
            approved_path.write_text(
                json.dumps([s.model_dump() for s in approved], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        # Store in bot_data for /liste
        context.application.bot_data["last_pro"] = pro
        context.application.bot_data["last_part"] = part

        await update.message.reply_text(
            f"✅ Analyse terminee !\n"
            f"🏪 {len(pro)} pro + 🙋 {len(part)} particuliers\n"
            f"Voici le TOP — bonne chasse ! 🎯"
        )

        # Auto-send top listings with photos
        notifier = _get_notifier()
        await notifier.notify_shortlist(approved)

    except Exception as e:
        logger.error(f"Erreur /chercher: {e}")
        await update.message.reply_text(f"Erreur: {e}")


async def cmd_liste(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envoyer la derniere shortlist avec photos."""
    files = sorted(Path(OUTPUT_DIR).glob("approved_*.json"), reverse=True)
    if not files:
        await update.message.reply_text("Pas de shortlist disponible. Lancez /chercher d'abord.")
        return

    try:
        data = json.loads(files[0].read_text(encoding="utf-8"))
        listings = [ScoredListing.model_validate(d) for d in data]
        notifier = _get_notifier()
        await notifier.notify_shortlist(listings)
    except Exception as e:
        logger.error(f"Erreur /liste: {e}")
        await update.message.reply_text(f"Erreur: {e}")


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

    try:
        num = int(args[0])
    except ValueError:
        await update.message.reply_text("Numero invalide.")
        return

    files = sorted(Path(OUTPUT_DIR).glob("approved_*.json"), reverse=True)
    if not files:
        await update.message.reply_text("Pas de shortlist. Lancez /chercher.")
        return

    data = json.loads(files[0].read_text(encoding="utf-8"))
    top = [ScoredListing.model_validate(d) for d in data if d.get("score", 0) >= SCORE_THRESHOLD]
    top.sort(key=lambda x: x.score, reverse=True)

    if num < 1 or num > len(top):
        await update.message.reply_text(f"Numero {num} invalide. Dispo: 1-{len(top)}")
        return

    listing = top[num - 1]
    notifier = TelegramNotifier()

    # Send all photos (up to 10)
    photos = listing.images[:10]
    if len(photos) > 1:
        media = [InputMediaPhoto(media=url) for url in photos]
        try:
            await context.bot.send_media_group(chat_id=update.effective_chat.id, media=media)
        except Exception as e:
            logger.warning(f"Media group failed: {e}")

    # Send full details
    km_str = f"{listing.mileage_km:,} km".replace(",", " ") if listing.mileage_km else "?"
    desc = (listing.description or "Pas de description")[:1500]
    await update.message.reply_text(
        f"#{num} - {listing.title}\n"
        f"Prix: {listing.price:,} EUR | {listing.year} | {km_str}\n"
        f"Score: {listing.score}/100\n"
        f"Ville: {listing.city} ({listing.department})\n"
        f"Vendeur: {getattr(listing, 'seller_name', '') or '?'}\n"
        f"Tel: {getattr(listing, 'seller_phone', '') or 'non dispo'}\n\n"
        f"{desc}\n\n"
        f"{listing.url}"
    )


async def cmd_intervalle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    args = context.args
    if not args:
        await update.message.reply_text(
            "Comment programmer la recherche automatique ?\n\n"
            "C'est simple : tapez le mot 'intervalle' suivi du delai souhaite, "
            "puis appuyez sur Envoyer (comme un message normal).\n\n"
            "Exemple : pour une recherche toutes les 2 heures, envoyez :\n"
            "intervalle 2h\n\n"
            "Autres exemples :\n"
            "  intervalle 4h  = toutes les 4 heures\n"
            "  intervalle 1j  = une fois par jour\n"
            "  intervalle 1s  = une fois par semaine\n\n"
            "Minimum : 1 heure | Maximum : 1 semaine"
        )
        return
    hours = parse_interval(args[0])
    if hours is None:
        await update.message.reply_text(f"Intervalle invalide. Min {MIN_INTERVAL_HOURS}h, max {MAX_INTERVAL_HOURS}h.")
        return
    context.application.bot_data["interval_hours"] = hours
    await update.message.reply_text(f"⏰ C'est programme ! Recherche automatique toutes les {hours}h 🔄\nJe vous previens des que je trouve quelque chose 📬")


async def cmd_statut(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    from state import load_state
    from config import OUTPUT_DIR
    from pathlib import Path
    state = load_state(str(Path(OUTPUT_DIR) / "state.json"))
    step_fr = {
        "init": "initial", "scraped": "scrape termine", "analyzed": "analyse terminee",
        "hitl": "validation", "priced": "pricing termine", "done": "termine",
    }.get(state.step, state.step)
    status_fr = {"pending": "en attente", "done": "termine", "running": "en cours", "failed": "echoue"}
    await update.message.reply_text(
        f"Etape: {step_fr}\n"
        f"Dernier scrape: {state.last_scrape_at or 'jamais'}\n"
        f"Annonces brutes: {state.raw_listing_count}\n"
        f"Analyse: {status_fr.get(state.analysis_status, state.analysis_status)}\n"
        f"Pricing: {status_fr.get(state.pricing_status, state.pricing_status)}"
    )


async def cmd_effacer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Supprimer les messages envoyes par le bot."""
    notifier = _get_notifier()
    chat_id = str(update.effective_chat.id)
    deleted = await notifier.delete_sent_messages(chat_id)
    await update.message.reply_text(f"{deleted} messages supprimes.")


async def post_init(app: Application) -> None:
    from telegram import BotCommand
    await app.bot.set_my_commands([
        BotCommand("chercher", "Lancer une recherche"),
        BotCommand("liste", "Voir la shortlist"),
        BotCommand("approuver", "Approuver des annonces"),
        BotCommand("rejeter", "Rejeter des annonces"),
        BotCommand("details", "Details d'une annonce"),
        BotCommand("effacer", "Supprimer les messages du bot"),
        BotCommand("intervalle", "Changer la frequence"),
        BotCommand("statut", "Etat du pipeline"),
    ])


async def callback_trash(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle trash button — delete the message with the listing."""
    query = update.callback_query
    await query.answer("Annonce supprimee 🗑️")
    try:
        await query.message.delete()
    except Exception:
        pass


def build_application() -> Application:
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", cmd_demarrer))
    app.add_handler(CommandHandler("chercher", cmd_chercher))
    app.add_handler(CommandHandler("liste", cmd_liste))
    app.add_handler(CommandHandler("approuver", cmd_approuver))
    app.add_handler(CommandHandler("rejeter", cmd_rejeter))
    app.add_handler(CommandHandler("details", cmd_details))
    app.add_handler(CommandHandler("effacer", cmd_effacer))
    app.add_handler(CommandHandler("intervalle", cmd_intervalle))
    app.add_handler(CommandHandler("statut", cmd_statut))

    # Trash button callback
    app.add_handler(CallbackQueryHandler(callback_trash, pattern="^trash_"))

    # Free text handler — supports typing without /
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    return app


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle free text input — route to appropriate command."""
    text = (update.message.text or "").strip().lower()

    if text in ("chercher", "rechercher", "search"):
        await cmd_chercher(update, context)
    elif text in ("liste", "list"):
        await cmd_liste(update, context)
    elif text in ("statut", "status"):
        await cmd_statut(update, context)
    elif text in ("effacer", "clear"):
        await cmd_effacer(update, context)
    elif text.startswith("details ") or text.startswith("detail "):
        num = text.split()[-1]
        context.args = [num]
        await cmd_details(update, context)
    elif text.startswith("approuver ") or text.startswith("ok "):
        nums = text.split(None, 1)[-1]
        context.args = [nums]
        await cmd_approuver(update, context)
    elif text.startswith("rejeter ") or text.startswith("drop "):
        nums = text.split(None, 1)[-1]
        context.args = [nums]
        await cmd_rejeter(update, context)
    elif text.startswith("intervalle "):
        val = text.split(None, 1)[-1]
        context.args = [val]
        await cmd_intervalle(update, context)
    else:
        await update.message.reply_text(
            "Tapez un de ces mots et appuyez sur Envoyer :\n\n"
            "chercher → Lancer une nouvelle recherche\n"
            "liste → Revoir les meilleures annonces\n"
            "details 3 → Voir toutes les photos de l'annonce #3\n"
            "approuver 1,3 → Garder les annonces #1 et #3\n"
            "rejeter 2 → Supprimer l'annonce #2\n"
            "effacer → Nettoyer les messages du bot\n"
            "intervalle → Programmer la recherche automatique\n"
            "statut → Voir ou en est la recherche"
        )
