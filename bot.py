"""
AnonBot -- one-sided anonymous inbox, 4th bot in the family (see
ARCHITECTURE.md). Anyone can grab a permanent personal link (/link) and
post it somewhere public; anyone who taps it can send them anonymous
messages here without the owner seeing who they are. The owner's identity
is never hidden -- it's their own bot chat -- only the person asking is.

The two things this bot is built around (both explicitly requested):
  1. Every incoming anonymous message carries a "Reply" button (and a
     "Block" button). Tapping Reply forces the owner's next message to be a
     Telegram reply to that specific message (via ForceReply) -- so even
     with a dozen different people messaging the owner in the same chat,
     there's never any doubt about who a given answer is going to. A native
     swipe-reply works exactly the same way, no button required.
  2. When the owner replies, it's delivered as a genuine Telegram reply on
     the follower's end too (quoting their own earlier message) -- so it
     visibly looks like a real back-and-forth, not a wall of disconnected
     bot messages. See anon_logic.relay_content() for how.

Tapping the SAME link again always starts a brand-new conversation (a fresh
conv_number, a fresh reply-chain anchor) -- it does not continue whatever
was last open with that owner.

Commands:
  /start, /help     - greeting + how it works (also handles /start q_<token>,
                       i.e. someone tapping a link)
  /link             - get your own permanent inbox link
  /newlink          - reset your link (invalidates the old one)
  /pause / /resume  - stop/resume NEW conversations (open ones keep working)
  /blocked          - review + undo who you've blocked
  /stats            - quick counts for your own inbox
  /donate           - support hosting costs (voluntary)
  /en, /uz, /rus    - switch language (English/Uzbek/Russian); also asked
                       once, trilingually, on first /start

Requires: python-telegram-bot[job-queue]>=21.3, python-dotenv>=1.0
Env vars: ABOT_TOKEN, ABOT_USERNAME (no @), ABOT_ADMIN_ID (optional,
          comma-separated, gates /messageas, /dbdump and /status),
          DATABASE_URL and DB_SCHEMA (the shared family database, and this
          bot's schema in it), SIBLING_BOTS (see shared_features.py)
"""
import asyncio
import html
import logging
import os
from datetime import datetime, timedelta, timezone
from io import BytesIO

try:  # optional convenience: load env vars from a local .env file
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from telegram import (
    BotCommand, ForceReply, InlineKeyboardButton, InlineKeyboardMarkup, Message, Update,
)
from telegram.constants import ParseMode
from telegram.error import BadRequest, Forbidden
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    PreCheckoutQueryHandler,
    TypeHandler,
    filters,
)

import family_link
import i18n
import lifecycle
from live_message import LiveMessage, edit_in_place
from anon_logic import italicize, relay_content
from db import (
    clear_follower_state,
    get_active_conversation_for_follower,
    get_anon_link_state,
    get_anon_stats,
    get_conversation,
    get_conversation_for_relay,
    list_anon_blocks_with_conversations,
    get_delivery_context,
    get_link_view,
    get_or_create_anon_link,
    get_user_language,
    set_user_language,
    init_db,
    record_relay_and_touch,
    record_anon_relays,
    mark_follower_opened,
    count_owner_conversations,
    regenerate_anon_link,
    set_anon_blocked,
    set_anon_link_paused,
    start_new_anon_conversation,
    dump_database_csv_zip,
    count_active_users_since,
)
from shared_features import (
    attach_maintenance,
    CANCEL_PICK_ALL,
    CANCEL_PICK_NONE,
    CancelItem,
    ask_cancel_choice,
    cancel_choice_key,
    cancel_items,
    cancel_shared_item,
    finish_cancel_choice,
    keep_going,
    finish_cancel,
    flush_on_shutdown,
    language_keyboard,
    remember_force_reply,
    tune_runtime,
    donate_amount_chosen,
    donate_fiat_amount_chosen,
    donate_custom_button_chosen,
    donate_custom_amount_received,
    donate_command,
    donation_payment_callback,
    donation_precheckout_callback,
    maybe_donation_nudge,
    sibling_bots_blurb,
    sibling_bots_keyboard_row,
    setup_logging,
    error_handler,
    track_activity,
    build_status_text,
)

setup_logging(__file__)
logger = logging.getLogger(__name__)

START_TIME = datetime.now(timezone.utc)

BOT_TOKEN = os.environ.get("ABOT_TOKEN")
BOT_USERNAME = os.environ.get("ABOT_USERNAME")  # no @
BOT_NAME = "anonbot"  # this bot's id within SIBLING_BOTS

# Owner-only admin tools (/messageas, /dbdump, /status) -- comma-separated
# Telegram user ids. Empty/unset means disabled for everyone.
ADMIN_IDS = {int(x) for x in os.environ.get("ABOT_ADMIN_ID", "").split(",") if x.strip()}

# Telegram's long-poll window -- see the note in main().
POLL_TIMEOUT = int(os.environ.get("POLL_TIMEOUT", "30"))


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


async def _reply(update: Update, text: str, **kwargs):
    """Works whether this came from a command or a button tap -- the first-run
    language picker means a brand-new user can reach any of these paths from
    a callback query, which has no message of its own to reply to.

    The button path evolves the tapped message in place, but only while it is
    still the last thing in the chat; once the user has typed anything since,
    a rewrite would land above their own message and out of sight, so a new
    message is sent instead. See live_message.py."""
    if update.message:
        return await LiveMessage.reply_to(update.message, text, **kwargs)
    return await edit_in_place(update.callback_query.message, update.get_bot(), text, **kwargs)


def build_help_text(lang: str) -> str:
    return i18n.t(lang, "help_text") + sibling_bots_blurb(BOT_NAME, lang)


# Public command menu (the "/" button in Telegram's chat UI) -- set on
# startup via set_my_commands() below instead of pasting into @BotFather by
# hand. The owner-only /dbdump is deliberately left off. Language-switch
# commands are described in the language they switch to (self-explanatory
# by script/language, since Telegram's command menu itself isn't per-user).
BOT_COMMANDS = [
    BotCommand("start", "Start here / see the instructions"),
    BotCommand("link", "Get your inbox link"),
    BotCommand("newlink", "Reset your link (invalidates the old one)"),
    BotCommand("pause", "Stop accepting new conversations"),
    BotCommand("resume", "Resume accepting new conversations"),
    BotCommand("blocked", "Review who you've blocked"),
    BotCommand("stats", "Quick counts for your inbox"),
    BotCommand("cancel", "Stop whatever I'm waiting for"),
    BotCommand("help", "How this bot works"),
    BotCommand("donate", "Chip in for hosting costs"),
    BotCommand("language", "Choose your language / Tilni tanlash / Выбрать язык"),
    BotCommand("en", "Switch to English"),
    BotCommand("uz", "O'zbekchaga o'tish"),
    BotCommand("rus", "Переключиться на русский"),
]


def _link_url(token: str) -> str:
    return f"https://t.me/{BOT_USERNAME}?start=q_{token}"


def _incoming_keyboard(conversation_id: int, lang: str) -> InlineKeyboardMarkup:
    """Under a message arriving in the OWNER's chat."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(i18n.t(lang, "reply_button"), callback_data=f"aq_reply:{conversation_id}"),
                InlineKeyboardButton(i18n.t(lang, "block_button"), callback_data=f"aq_block:{conversation_id}"),
            ]
        ]
    )


def _follower_keyboard(conversation_id: int, lang: str) -> InlineKeyboardMarkup:
    """Under a message arriving in the GUEST's chat. Reply only -- blocking
    is the inbox owner's tool, and a guest who wants out just stops
    answering."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton(i18n.t(lang, "reply_button"), callback_data=f"aq_reply:{conversation_id}")]]
    )


def _quote_of(message, limit: int = 120) -> str:
    """A one-line echo of the message being answered, for the reply prompt.

    Telegram's ForceReply has no way to aim the reply box at some *earlier*
    message -- it always targets the message that carries it -- so the prompt
    cannot make the client quote the guest's message directly. Putting the
    text inside the prompt is the next best thing: whatever the reply box
    quotes, what it quotes now contains the words being answered.
    """
    body = message.text or message.caption or ""
    body = " ".join(body.split())
    if not body:
        return italicize("[media]")
    if len(body) > limit:
        body = body[: limit - 1].rstrip() + "\u2026"
    return italicize(body)


# ---------- /start (also handles someone tapping an inbox link: /start q_<token>) ----------

async def _continue_start(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str, args):
    if args and args[0].startswith("q_"):
        return await start_follow_link(update, context, args[0][2:], lang)

    kb = sibling_bots_keyboard_row(BOT_NAME)
    await _reply(
        update,
        i18n.t(lang, "start_greeting") + build_help_text(lang),
        reply_markup=InlineKeyboardMarkup([kb]) if kb else None,
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start prints the instructions -- except the very first one, which
    asks for a language first.

    v0.7.0 made every /start the language picker, which put a three-button
    detour in front of the one command every Telegram user types by reflex,
    for the sake of a choice that is made once. The 0.6.0 shape is back, and
    the picker has moved to a command of its own:

      * No language on record -- a brand-new user -- and /start does exactly
        what /language does: greet in all three languages and ask. Picking
        one prints the instructions (see _apply_language), so the first
        /start still ends where every later one begins. This is the only
        time /start asks.
      * A language on record, and /start prints the instructions in it.
        Anyone who wants the picker back asks for it by name: /language.

    A deep link (/start q_<token>, someone opening an inbox link) still goes
    straight to that inbox, and a brand-new user who arrives on one picks a
    language first and is carried there afterwards by pending_start_args.
    """
    lang = await asyncio.to_thread(get_user_language, update.effective_user.id)
    if lang is None:
        context.user_data["pending_start_args"] = context.args
        await update.message.reply_text(i18n.LANGUAGE_PROMPT, reply_markup=language_keyboard())
        return

    context.user_data["lang"] = lang
    if context.args:
        await _continue_start(update, context, lang, context.args)
        return

    context.user_data.pop("pending_start_args", None)
    await _continue_start(update, context, lang, None)


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/language -- the picker on demand, which is what /start used to be.

    Same trilingual greeting and same three buttons, with a tick on the
    language in force so a returning user can see which one they are on
    before deciding to change it. The tap that follows runs through
    _apply_language exactly as /en, /uz and /rus do, so it ends where they
    end: at the instructions, in the language just chosen.
    """
    lang = await asyncio.to_thread(get_user_language, update.effective_user.id)
    # Keep the cached language warm even though the picker itself is
    # trilingual -- the next handler this user hits would otherwise pay for
    # a database read that /language had already done.
    if lang:
        context.user_data["lang"] = lang
    await update.message.reply_text(i18n.LANGUAGE_PROMPT, reply_markup=language_keyboard(lang))


async def _apply_language(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str):
    """The single path every language change goes through -- /en, /uz, /rus
    and a tap on the picker alike -- so all four end the same way: with the
    instructions, printed in the language just chosen.

    Answering a language change with nothing but "Language set" (which is all
    /en, /uz and /rus used to do for anyone who was not brand new) leaves
    someone looking at a bot whose manual they have just made themselves
    unable to reach. pending_start_args carries a brand-new user who arrived
    on an inbox link through to that inbox once they have picked.
    """
    await asyncio.to_thread(set_user_language, update.effective_user.id, lang)
    context.user_data["lang"] = lang
    pending = context.user_data.pop("pending_start_args", None) or []
    await _continue_start(update, context, lang, pending)


async def _set_language(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str):
    await update.message.reply_text(i18n.t(lang, "language_set_confirmation"))
    await _apply_language(update, context, lang)


async def set_language_en(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _set_language(update, context, "en")


async def set_language_uz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _set_language(update, context, "uz")


async def set_language_rus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await _set_language(update, context, "ru")


async def language_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """A tap on the picker. Carries any pending /start q_<token> through, so
    someone whose very first action was opening a link lands in the
    conversation it points at rather than back at the greeting."""
    query = update.callback_query
    lang = query.data.split(":", 1)[1]
    await query.answer(i18n.t(lang, "language_set_confirmation"))
    await _apply_language(update, context, lang)


async def start_follow_link(update: Update, context: ContextTypes.DEFAULT_TYPE, token: str, lang: str):
    follower = update.effective_user
    # One query for "who owns this token, are they paused, and have they
    # blocked me" -- it used to be three, run one after the other.
    owner_id, is_paused, blocked = await asyncio.to_thread(
        get_link_view, token, follower.id
    )
    if owner_id is None:
        await _reply(update, i18n.t(lang, "follow_link_invalid"))
        return

    if owner_id == follower.id:
        await _reply(update, i18n.t(lang, "follow_link_own"))
        return

    if blocked:
        await _reply(update, i18n.t(lang, "follow_link_blocked"))
        return

    if is_paused:
        await _reply(update, i18n.t(lang, "follow_link_paused"))
        return

    conv = await asyncio.to_thread(start_new_anon_conversation, owner_id, follower.id)
    opening = await _reply(
        update, i18n.t(lang, "follow_link_started", conv_number=conv["conv_number"])
    )
    # Registered as a relay target so the guest's *first* message has
    # something to reply to. Every later message in this chat is a real
    # message from the owner; this one stands in for them until then.
    if opening is not None:
        await asyncio.to_thread(
            record_anon_relays, follower.id, [opening.message_id], conv["id"]
        )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = await i18n.get_lang(update.effective_user.id, context)
    await update.message.reply_text(build_help_text(lang))


# ---------- owner: inbox link management ----------

def _link_message(token: str, paused: bool, lang: str, note: str = "") -> tuple[str, InlineKeyboardMarkup]:
    """Shared by /link and its Pause/Resume/New-link buttons, so tapping
    one edits the same message back into an up-to-date version of itself
    instead of you needing to type /pause, /resume, or /newlink by hand."""
    status = i18n.t(lang, "link_status_paused" if paused else "link_status_active")
    text = i18n.t(lang, "link_message", status=status, url=html.escape(_link_url(token)))
    if note:
        text = f"{note}\n\n{text}"
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    i18n.t(lang, "link_button_resume" if paused else "link_button_pause"),
                    callback_data="anonlink:toggle",
                ),
                InlineKeyboardButton(i18n.t(lang, "link_button_newlink"), callback_data="anonlink:newlink"),
            ]
        ]
    )
    return text, kb


async def link_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    owner = update.effective_user
    lang = await i18n.get_lang(owner.id, context)
    token, is_paused = await asyncio.to_thread(get_or_create_anon_link, owner.id)
    text, kb = _link_message(token, is_paused, lang)
    await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def anonlink_toggle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    owner_id = update.effective_user.id
    lang = await i18n.get_lang(owner_id, context)
    state = await asyncio.to_thread(get_anon_link_state, owner_id)
    if not state:
        await query.answer(i18n.t(lang, "anonlink_no_link_yet"), show_alert=True)
        return
    new_paused = not state["is_paused"]
    await asyncio.to_thread(set_anon_link_paused, owner_id, new_paused)
    await query.answer(i18n.t(lang, "anonlink_paused_answer" if new_paused else "anonlink_resumed_answer"))
    text, kb = _link_message(state["token"], new_paused, lang)
    await edit_in_place(query.message, context.bot, text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def anonlink_newlink_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    owner_id = update.effective_user.id
    lang = await i18n.get_lang(owner_id, context)
    # A new link does not un-pause the inbox, and the screen has to keep
    # saying so -- the paused flag comes back from the same statement rather
    # than costing a second query.
    token, is_paused = await asyncio.to_thread(regenerate_anon_link, owner_id)
    await query.answer(i18n.t(lang, "anonlink_newlink_answer"))
    text, kb = _link_message(token, is_paused, lang)
    await edit_in_place(query.message, context.bot, text, parse_mode=ParseMode.HTML, reply_markup=kb)


async def newlink_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    owner = update.effective_user
    lang = await i18n.get_lang(owner.id, context)
    token, _ = await asyncio.to_thread(regenerate_anon_link, owner.id)
    await update.message.reply_text(
        i18n.t(lang, "newlink_message", url=html.escape(_link_url(token))),
        parse_mode=ParseMode.HTML,
    )


async def pause_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    owner = update.effective_user
    lang = await i18n.get_lang(owner.id, context)
    await asyncio.to_thread(get_or_create_anon_link, owner.id)  # idempotent
    await asyncio.to_thread(set_anon_link_paused, owner.id, True)
    await update.message.reply_text(i18n.t(lang, "pause_message"))


async def resume_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = await i18n.get_lang(update.effective_user.id, context)
    await asyncio.to_thread(set_anon_link_paused, update.effective_user.id, False)
    await update.message.reply_text(i18n.t(lang, "resume_message"))


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = await i18n.get_lang(update.effective_user.id, context)
    stats = await asyncio.to_thread(get_anon_stats, update.effective_user.id)
    await update.message.reply_text(
        i18n.t(lang, "stats_message", followers=stats["distinct_followers"], conversations=stats["conversations"])
    )


async def dbdump_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/dbdump -- exports every table in this bot's own database as one
    zip of CSVs. Owner-only: this is every user's data, not something to
    hand out on request."""
    if not _is_admin(update.effective_user.id):
        return
    status = await LiveMessage.reply_to(update.message, "Exporting the database...")
    try:
        data = await asyncio.to_thread(dump_database_csv_zip)
    except Exception as exc:
        await status.set(context.bot, f"⚠️ Export failed: {exc}")
        return
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M")
    await update.message.reply_document(document=BytesIO(data), filename=f"anonbot_db_{stamp}.zip")
    await status.delete(context.bot)


async def messageas_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/messageas <user_id> <text> -- sends a message to that user as this
    bot. Only works if the user has messaged the bot before (Telegram
    doesn't let bots cold-message anyone). Owner-only for obvious reasons."""
    if not _is_admin(update.effective_user.id):
        return

    if len(context.args) < 2 or not context.args[0].lstrip("-").isdigit():
        await update.message.reply_text("Usage: /messageas <user_id> <message text>")
        return

    user_id = int(context.args[0])
    text = " ".join(context.args[1:])
    try:
        await context.bot.send_message(chat_id=user_id, text=text)
        await update.message.reply_text("✅ Sent.")
    except Exception as exc:
        await update.message.reply_text(f"⚠️ Couldn't send it: {exc}")


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/status -- uptime, hosting environment, any crashes since this
    process started, and active-user counts. Owner-only, same reasoning as
    /dbdump: this is operational info, not something every user should see."""
    if not _is_admin(update.effective_user.id):
        return
    now = datetime.now(timezone.utc)
    users_hour = await asyncio.to_thread(count_active_users_since, now - timedelta(hours=1))
    users_since_start = await asyncio.to_thread(count_active_users_since, START_TIME)
    await update.message.reply_text(build_status_text(START_TIME, users_hour, users_since_start))


async def _blocked_list_text_and_kb(owner_id: int, lang: str):
    rows = await asyncio.to_thread(list_anon_blocks_with_conversations, owner_id)
    if not rows:
        return i18n.t(lang, "blocked_none"), None
    lines = [i18n.t(lang, "blocked_header")]
    kb = []
    for follower_id, conv_numbers in rows:
        # Conversation numbers instead of a pseudonym: the owner has seen
        # these in their own chat, and unlike a stable hash they say nothing
        # about the guest beyond "we spoke, in this thread".
        if conv_numbers:
            joined = ", ".join(f"#{n}" for n in conv_numbers)
            line = i18n.t(lang, "blocked_guest_line", conversations=joined)
            button = i18n.t(lang, "blocked_unblock_button", conversations=joined)
        else:
            line = i18n.t(lang, "blocked_guest_line_unknown")
            button = i18n.t(lang, "blocked_unblock_button_unknown")
        lines.append(line)
        kb.append([InlineKeyboardButton(button, callback_data=f"aq_unblockg:{follower_id}")])
    return "\n".join(lines), InlineKeyboardMarkup(kb)


async def blocked_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = await i18n.get_lang(update.effective_user.id, context)
    text, kb = await _blocked_list_text_and_kb(update.effective_user.id, lang)
    await update.message.reply_text(text, reply_markup=kb)


# ---------- the Reply / Block buttons under an incoming message ----------

async def reply_button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Works for whichever side tapped it. Both chats now carry relay rows,
    so a conversation has two legitimate participants and the only question
    is whether this user is one of them."""
    query = update.callback_query
    user_id = update.effective_user.id
    lang = await i18n.get_lang(user_id, context)
    conversation_id = int(query.data.split(":", 1)[1])
    conv = await asyncio.to_thread(get_conversation, conversation_id)
    if not conv or user_id not in (conv["owner_user_id"], conv["follower_user_id"]):
        await query.answer(i18n.t(lang, "not_your_conversation"), show_alert=True)
        return
    await query.answer()

    prompt = await context.bot.send_message(
        chat_id=user_id,
        text=i18n.t(lang, "reply_prompt", conv_number=conv["conv_number"],
                    quote=_quote_of(query.message)),
        parse_mode=ParseMode.HTML,
        reply_to_message_id=query.message.message_id,
        reply_markup=ForceReply(selective=True, input_field_placeholder=i18n.t(lang, "reply_placeholder")),
    )
    # Registering the PROMPT itself as a relay target is what makes this
    # work reliably even with several Reply buttons tapped back-to-back
    # before any of them are answered: Telegram's ForceReply guarantees the
    # owner's next message is a reply-to THIS prompt specifically, so
    # handle_message() below resolves the right conversation regardless of
    # tap order -- no fragile "last button tapped" state involved.
    await asyncio.to_thread(
        record_anon_relays, user_id, [prompt.message_id], conversation_id
    )
    remember_force_reply(context, prompt)


async def block_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    lang = await i18n.get_lang(update.effective_user.id, context)
    conversation_id = int(query.data.split(":", 1)[1])
    conv = await asyncio.to_thread(get_conversation, conversation_id)
    if not conv or conv["owner_user_id"] != update.effective_user.id:
        await query.answer(i18n.t(lang, "not_your_conversation"), show_alert=True)
        return

    await asyncio.to_thread(set_anon_blocked, conv["owner_user_id"], conv["follower_user_id"], True)
    await query.answer(i18n.t(lang, "blocked_answer"))
    kb = InlineKeyboardMarkup(
        [[InlineKeyboardButton(i18n.t(lang, "unblock_button"), callback_data=f"aq_unblockc:{conversation_id}")]]
    )
    try:
        await query.edit_message_reply_markup(reply_markup=kb)
    except BadRequest:
        pass
    await context.bot.send_message(
        chat_id=update.effective_user.id,
        text=i18n.t(lang, "blocked_notice", conv_number=conv["conv_number"]),
    )


async def unblock_from_conversation_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    lang = await i18n.get_lang(update.effective_user.id, context)
    conversation_id = int(query.data.split(":", 1)[1])
    conv = await asyncio.to_thread(get_conversation, conversation_id)
    if not conv or conv["owner_user_id"] != update.effective_user.id:
        await query.answer(i18n.t(lang, "not_your_conversation"), show_alert=True)
        return

    await asyncio.to_thread(set_anon_blocked, conv["owner_user_id"], conv["follower_user_id"], False)
    await query.answer(i18n.t(lang, "unblocked_answer"))
    try:
        await query.edit_message_reply_markup(reply_markup=_incoming_keyboard(conversation_id, lang))
    except BadRequest:
        pass


async def unblock_from_list_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    lang = await i18n.get_lang(update.effective_user.id, context)
    follower_id = int(query.data.split(":", 1)[1])
    owner_id = update.effective_user.id
    await asyncio.to_thread(set_anon_blocked, owner_id, follower_id, False)
    await query.answer(i18n.t(lang, "unblocked_answer"))
    text, kb = await _blocked_list_text_and_kb(owner_id, lang)
    await edit_in_place(query.message, context.bot, text, reply_markup=kb)


# ---------- the reply requirement, and the way past it ----------
# A guest's message used to go wherever their open session pointed, no matter
# what it was answering -- which in a chat holding a whole back-and-forth
# reads as "everything I type is a reply to the last thing said". Now a guest
# says which message they mean, the same way the owner always has, and a
# message that names nothing is held rather than guessed at.

PENDING_KEY = "anon_pending_message"


def _restore_pending(stored, bot):
    """The held message and its destination, or (None, None).

    Accepts only the dict form; anything else -- including the (Message,
    int) tuple older code parked here -- reads as nothing held, which is
    the same answer the user got before any of this was persisted."""
    if not isinstance(stored, dict):
        return None, None
    try:
        held = Message.de_json(stored["message"], bot)
        conversation_id = int(stored["conversation_id"])
    except (KeyError, TypeError, ValueError):
        return None, None
    return (held, conversation_id) if held is not None else (None, None)


async def _hold_for_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str, conversation_id: int | None):
    """Nothing was sent, because nothing said where it was going.

    `conversation_id` is the one destination this message could unambiguously
    have had, or None when there is more than one. The Send-it-anyway button
    only appears in the first case: offering it when several conversations
    are open would be the same guess this rule exists to stop, made by a
    button instead of by the router."""
    # The message itself, not its id: a bot cannot fetch a message back by
    # id, and Message.reply_text does not quote in private chats, so the
    # callback has no way to find it again otherwise.
    #
    # Kept as to_dict() rather than as the Message object, and as a dict
    # rather than as a tuple, because a tuple holding a Message is exactly
    # what lifecycle.PostgresPersistence declines to write -- and of
    # everything this bot parks in user_data, this is the one whose loss a
    # user actually sees, as "that message expired" on a button they were
    # looking at seconds earlier. to_dict() is plain JSON that survives the
    # round trip unchanged, and Message.de_json() rebuilds a working Message
    # from it in whichever process picks the tap up.
    if conversation_id is None:
        context.user_data.pop(PENDING_KEY, None)
        await update.message.reply_text(i18n.t(lang, "must_reply_ambiguous"), do_quote=True)
        return

    context.user_data[PENDING_KEY] = {
        "message": update.message.to_dict(),
        "conversation_id": conversation_id,
    }
    await update.message.reply_text(
        i18n.t(lang, "must_reply"),
        do_quote=True,
        reply_markup=InlineKeyboardMarkup([[
            InlineKeyboardButton(
                i18n.t(lang, "must_reply_button"), callback_data="aq_sendanyway"
            )
        ]]),
    )


async def send_anyway_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    lang = await i18n.get_lang(update.effective_user.id, context)
    held, conversation_id = _restore_pending(
        context.user_data.pop(PENDING_KEY, None), context.bot
    )
    if held is None:
        await query.answer(i18n.t(lang, "must_reply_expired"), show_alert=True)
        return
    await query.answer()
    try:
        await query.edit_message_reply_markup(reply_markup=None)
    except BadRequest:
        pass

    # The held message may have crossed a redeploy to get here, so re-read
    # the conversation rather than trusting it to still describe the world.
    active = await asyncio.to_thread(get_active_conversation_for_follower, update.effective_user.id)
    if not active or active["id"] != conversation_id:
        await query.message.reply_text(i18n.t(lang, "must_reply_expired"))
        return
    await _deliver_follower_message(update, context, active, message=held)


# ---------- the actual message routing: owner replies vs. follower questions ----------

async def _deliver_follower_message(update: Update, context: ContextTypes.DEFAULT_TYPE, active: dict, message=None):
    """`message` is normally the one that just arrived; the Send-it-anyway
    button passes the earlier, held one instead."""
    message = message or update.message
    follower = update.effective_user
    owner_id = active["owner_user_id"]
    follower_lang = await i18n.get_lang(follower.id, context)

    # "Is the sender blocked, does the inbox still exist, and what language
    # does the owner read?" -- one query, where it used to be three separate
    # round trips on the hot path of every anonymous message.
    blocked, inbox_exists, owner_lang = await asyncio.to_thread(
        get_delivery_context, owner_id, follower.id
    )
    if blocked:
        await message.reply_text(i18n.t(follower_lang, "delivery_blocked"))
        return
    if not inbox_exists:
        await message.reply_text(i18n.t(follower_lang, "inbox_gone"))
        return


    owner_lang = owner_lang or "en"
    header = i18n.t(owner_lang, "incoming_header", conv_number=active["conv_number"])
    kb = _incoming_keyboard(active["id"], owner_lang)

    try:
        sent = await relay_content(
            context.bot, message, owner_id,
            reply_to_message_id=active.get("last_owner_msg_id"),
            reply_markup=kb, header=header,
        )
    except Forbidden:
        await message.reply_text(i18n.t(follower_lang, "delivery_forbidden"))
        return
    except BadRequest as exc:
        logger.exception("Failed relaying follower message")
        await message.reply_text(i18n.t(follower_lang, "delivery_failed", error=exc))
        return

    # Both anchors move: the owner-side copy anchors the OWNER's next reply
    # chain, and the follower's own message anchors what the owner's reply
    # will quote on the way back (see _deliver_owner_reply below).
    await asyncio.to_thread(
        record_relay_and_touch, owner_id, [m.message_id for m in sent], active["id"],
        sent[-1].message_id, message.message_id,
    )

    if active.get("follower_first_msg_at") is None:
        await asyncio.to_thread(mark_follower_opened, active["id"])

    await message.reply_text(i18n.t(follower_lang, "sent_confirmation"))
    nudge = await maybe_donation_nudge(follower.id, follower_lang)
    if nudge:
        await message.reply_text(nudge)


async def _deliver_owner_reply(update: Update, context: ContextTypes.DEFAULT_TYPE, conversation_id: int):
    message = update.message
    owner = update.effective_user
    owner_lang = await i18n.get_lang(owner.id, context)
    conv = await asyncio.to_thread(get_conversation, conversation_id)
    if not conv or conv["owner_user_id"] != owner.id:
        # anon_relay rows for a chat are only ever written for that chat's
        # real owner, so this shouldn't normally trip -- but never guess and
        # risk sending a reply to the wrong chat.
        await message.reply_text(i18n.t(owner_lang, "reply_no_match"))
        return

    follower_id = conv["follower_user_id"]
    follower_lang = await asyncio.to_thread(get_user_language, follower_id) or "en"
    try:
        sent = await relay_content(
            context.bot, message, follower_id,
            reply_to_message_id=conv.get("last_follower_msg_id"),
            header=i18n.t(follower_lang, "incoming_header_follower", conv_number=conv["conv_number"]),
            reply_markup=_follower_keyboard(conversation_id, follower_lang),
        )
    except Forbidden:
        await message.reply_text(i18n.t(owner_lang, "reply_forbidden"))
        return
    except BadRequest as exc:
        logger.exception("Failed relaying owner reply")
        await message.reply_text(i18n.t(owner_lang, "reply_failed", error=exc))
        return

    # The owner's own sent message is a valid anchor too, so the NEXT
    # incoming message in this conversation threads off of it in the
    # owner's chat, keeping the back-and-forth visually connected there too.
    await asyncio.to_thread(
        record_relay_and_touch, owner.id, [message.message_id], conversation_id,
        message.message_id, sent[-1].message_id,
    )
    # ...and the same rows on the guest's side. Without these, a guest who
    # swipe-replies to the answer they just received is told their reply
    # matches no conversation -- the relay table only ever had rows for the
    # owner's chat, so the guest's own chat looked untracked from here.
    await asyncio.to_thread(
        record_anon_relays, follower_id, [m.message_id for m in sent], conversation_id
    )

    await message.reply_text(i18n.t(owner_lang, "delivered_confirmation"))
    nudge = await maybe_donation_nudge(owner.id, owner_lang)
    if nudge:
        await message.reply_text(nudge)


async def _reply_prompt_pending(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Whether there is an unanswered Reply prompt to back out of.

    A Reply prompt is recognised by /cancel being sent *as a reply to it*,
    which means it can only be spotted while that reply link exists -- and
    the answer to /cancel's question arrives as a button tap on a different
    message, where it does not. So the finding is stashed on the way past
    and read back on the tap.
    """
    if update.callback_query is not None:
        return bool(context.user_data.get("cancel_reply_prompt"))
    replied_to = update.message.reply_to_message if update.message else None
    if replied_to is None:
        context.user_data.pop("cancel_reply_prompt", None)
        return False
    pending = bool(await asyncio.to_thread(
        get_conversation_for_relay, update.effective_chat.id, replied_to.message_id
    ))
    context.user_data["cancel_reply_prompt"] = pending
    return pending


async def _cancel_items(update: Update, context: ContextTypes.DEFAULT_TYPE, lang: str) -> list[CancelItem]:
    """Everything this bot could be waiting on.

    The open ask session -- what tapping someone's inbox link leaves behind
    -- is the one that matters most, because it lives in the database rather
    than in memory: every ordinary message you send keeps going to that
    person until something clears it. It is also the one most worth being
    asked about rather than swept up, since someone who typed /cancel to
    escape a Reply prompt did not mean to walk out of the conversation.
    """
    items = cancel_items(context, lang)
    if await _reply_prompt_pending(update, context):
        items.append(CancelItem("reply_prompt",
                                i18n.t(lang, "cancel_item_reply_prompt"),
                                i18n.t(lang, "cancel_button_reply_prompt")))
    if await asyncio.to_thread(get_active_conversation_for_follower, update.effective_user.id):
        items.append(CancelItem("anon_session",
                                i18n.t(lang, "cancel_item_anon_session"),
                                i18n.t(lang, "cancel_button_anon_session")))
    return items


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Asks which of the things it is waiting on to stop, then stops that
    one -- see _cancel_items for what they are."""
    lang = await i18n.get_lang(update.effective_user.id, context)
    items = await _cancel_items(update, context, lang)
    if await ask_cancel_choice(update, context, items, lang):
        return
    await finish_cancel(update, context, lang, [])


async def cancel_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """A tap on one of /cancel's buttons."""
    query = update.callback_query
    lang = await i18n.get_lang(update.effective_user.id, context)
    key = cancel_choice_key(update)
    await query.answer()
    if key == CANCEL_PICK_NONE:
        context.user_data.pop("cancel_reply_prompt", None)
        await keep_going(update, context, lang)
        return

    items = {item.key: item for item in await _cancel_items(update, context, lang)}
    keys = list(items) if key == CANCEL_PICK_ALL else [key]
    stopped = []
    for chosen in keys:
        item = items.get(chosen)
        if item is None:
            continue
        if chosen == "anon_session":
            await asyncio.to_thread(clear_follower_state, update.effective_user.id)
            stopped.append(item.label)
        elif chosen == "reply_prompt":
            # Nothing to undo in the database -- the prompt is a message, and
            # finish_cancel_choice is what takes it down.
            context.user_data.pop("cancel_reply_prompt", None)
            stopped.append(item.label)
        elif cancel_shared_item(context, lang, chosen):
            stopped.append(item.label)
    await finish_cancel_choice(update, context, lang, stopped)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = update.effective_user
    chat_id = message.chat_id

    # 1. Is this a reply landing on a message we're tracking? That's an
    #    owner answering one specific conversation -- via the Reply button's
    #    forced reply, or an ordinary swipe-reply, both resolve identically.
    #    Checked FIRST and unconditionally, so it's correct even for someone
    #    who's simultaneously an owner (of their own link) and a follower
    #    (of someone else's) -- explicit reply intent always wins.
    #
    #    Crucially: a reply that DOESN'T match anything tracked stops right
    #    here instead of falling through to step 2 below. Using Telegram's
    #    reply feature is an explicit, deliberate signal -- "this is meant
    #    for the conversation I'm replying to" -- so if that conversation
    #    can't be found, the right answer is to say so, never to silently
    #    reinterpret the message as something else (e.g. a fresh anonymous
    #    message to whatever OTHER inbox this user happens to still have an
    #    open session with, which is exactly how a stray reply on old chat
    #    history could otherwise land somewhere unintended).
    if message.reply_to_message:
        conversation_id = await asyncio.to_thread(
            get_conversation_for_relay, chat_id, message.reply_to_message.message_id
        )
        if conversation_id:
            # Both chats carry relay rows now, so a matched row says *which*
            # conversation, not which direction. The sender's own id is what
            # says that -- owner one way, guest the other.
            conv = await asyncio.to_thread(get_conversation, conversation_id)
            if conv and conv["owner_user_id"] == user.id:
                return await _deliver_owner_reply(update, context, conversation_id)
            if conv and conv["follower_user_id"] == user.id:
                active = await asyncio.to_thread(get_active_conversation_for_follower, user.id)
                if active and active["id"] == conversation_id:
                    return await _deliver_follower_message(update, context, active)
                # Replying inside a conversation the guest has since moved on
                # from (tapping the link again starts a new one) would put the
                # message somewhere they are not looking. Say so.
                lang = await i18n.get_lang(user.id, context)
                await message.reply_text(i18n.t(lang, "reply_stale"))
                return
        lang = await i18n.get_lang(user.id, context)
        await message.reply_text(i18n.t(lang, "reply_stale"))
        return

    # 2. A message that says nothing about where it is going.
    #
    #    Exactly one message in a conversation is allowed to: the guest's
    #    opening one, which has nothing above it to answer. Everything after
    #    it, from either side, has to name what it replies to -- an inbox
    #    link is posted somewhere public and one person ends up answering
    #    several, so "whichever thread was most recently touched" is not a
    #    guess worth making. It is also not a guess this bot got right: an
    #    owner answering a new arrival, while still holding an open session
    #    from a link they had tapped themselves, had their answer delivered
    #    to that other conversation entirely -- and told "Sent".
    active = await asyncio.to_thread(get_active_conversation_for_follower, user.id)
    if active and active.get("follower_first_msg_at") is None:
        return await _deliver_follower_message(update, context, active)

    owned = await asyncio.to_thread(count_owner_conversations, user.id)
    if active or owned:
        lang = await i18n.get_lang(user.id, context)
        # One open session and no inbox of their own is the only case with a
        # single possible destination.
        target = active["id"] if (active and not owned) else None
        return await _hold_for_reply(update, context, lang, target)

    # 3. Neither -- generic nudge instead of silently swallowing the message.
    lang = await i18n.get_lang(user.id, context)
    await message.reply_text(i18n.t(lang, "generic_nudge"))


async def unknown_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = await i18n.get_lang(update.effective_user.id, context)
    await update.message.reply_text(i18n.t(lang, "unknown_command"))


async def _post_init(application):
    await tune_runtime(application)
    # Before the first getUpdates -- see lifecycle.py: two containers polling
    # one token is 409 Conflict and split updates, not a graceful overlap.
    await lifecycle.on_start(BOT_NAME)
    await application.bot.set_my_commands(BOT_COMMANDS)


async def _post_stop(application):
    # Before flush_on_shutdown, which closes the pool lifecycle writes through.
    await lifecycle.on_stop(application)
    await flush_on_shutdown(application)


def main():
    if not BOT_TOKEN or not BOT_USERNAME:
        raise SystemExit("Set ABOT_TOKEN and ABOT_USERNAME environment variables first.")

    init_db()
    builder = (
        ApplicationBuilder().token(BOT_TOKEN)
        .post_init(_post_init).post_stop(_post_stop)
    )
    # Open conversations kept in Postgres, so a redeploy is not the end of
    # somebody's half-written message. See lifecycle.py.
    state = lifecycle.persistence()
    if state is not None:
        builder = builder.persistence(state)
    app = builder.build()
    lifecycle.install(app, BOT_NAME)
    app.add_error_handler(error_handler)
    app.add_handler(TypeHandler(Update, track_activity), group=-1)
    # Runs after track_activity but before every other handler (including the
    # anonymous-relay handle_message below) -- a no-op unless a "Custom" donate
    # button was just tapped, in which case it consumes the reply and stops it
    # from also being relayed as an anonymous message (see
    # donate_custom_amount_received's docstring).
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, donate_custom_amount_received), group=-1)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("cancel", cancel_command))
    app.add_handler(CommandHandler("link", link_command))
    app.add_handler(CommandHandler("newlink", newlink_command))
    app.add_handler(CommandHandler("pause", pause_command))
    app.add_handler(CommandHandler("resume", resume_command))
    app.add_handler(CommandHandler("blocked", blocked_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("dbdump", dbdump_command))  # owner-only
    app.add_handler(CommandHandler("messageas", messageas_command))  # owner-only
    app.add_handler(CommandHandler("status", status_command))  # owner-only

    # ---- language: /en, /uz, /rus -- pick at first /start, change anytime ----
    app.add_handler(CommandHandler("language", language_command))
    app.add_handler(CommandHandler("en", set_language_en))
    app.add_handler(CommandHandler("uz", set_language_uz))
    app.add_handler(CommandHandler("rus", set_language_rus))

    app.add_handler(CallbackQueryHandler(language_chosen, pattern=r"^setlang:"))
    app.add_handler(CallbackQueryHandler(cancel_choice_callback, pattern=r"^cancelpick:"))
    app.add_handler(CallbackQueryHandler(anonlink_toggle_callback, pattern=r"^anonlink:toggle$"))
    app.add_handler(CallbackQueryHandler(anonlink_newlink_callback, pattern=r"^anonlink:newlink$"))
    app.add_handler(CallbackQueryHandler(reply_button_callback, pattern=r"^aq_reply:"))
    app.add_handler(CallbackQueryHandler(send_anyway_callback, pattern=r"^aq_sendanyway$"))
    app.add_handler(CallbackQueryHandler(block_callback, pattern=r"^aq_block:"))
    app.add_handler(CallbackQueryHandler(unblock_from_conversation_callback, pattern=r"^aq_unblockc:"))
    app.add_handler(CallbackQueryHandler(unblock_from_list_callback, pattern=r"^aq_unblockg:"))

    # ---- donations (Telegram Stars) -- this bot's only Stars usage ----
    app.add_handler(CommandHandler("donate", donate_command))
    app.add_handler(CallbackQueryHandler(donate_amount_chosen, pattern="^donate:"))
    app.add_handler(CallbackQueryHandler(donate_fiat_amount_chosen, pattern="^donatefiat:"))
    app.add_handler(CallbackQueryHandler(donate_custom_button_chosen, pattern="^donatecustom:"))
    app.add_handler(PreCheckoutQueryHandler(donation_precheckout_callback))
    app.add_handler(MessageHandler(filters.SUCCESSFUL_PAYMENT, donation_payment_callback))

    # Everything else non-command in a private chat is either an owner's
    # reply or a follower's question -- handle_message() tells them apart.
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, handle_message))
    # Registered last so every real command above gets first shot -- only
    # reached by a slash-command this bot doesn't actually have.
    app.add_handler(MessageHandler(filters.COMMAND, unknown_command))

    # ParentBot's link: heartbeats, crash/donation events, and the queue it
    # uses to run this bot's owner-only commands remotely. Never raises --
    # with no shared database reachable the bot just runs on its own.
    family_link.attach(app, BOT_NAME, "AnonBot", START_TIME)
    attach_maintenance(app)

    logger.info("Bot starting (polling)...")
    # A 30-second long poll is the same latency as the default 10 -- Telegram
    # answers the moment an update exists -- for a third of the HTTP requests.
    # allowed_updates lists every kind this bot has a handler for, so Telegram
    # stops sending the rest rather than this process parsing and dropping it.
    app.run_polling(**lifecycle.polling_kwargs(
        timeout=POLL_TIMEOUT,
        allowed_updates=[Update.MESSAGE, Update.CALLBACK_QUERY, Update.PRE_CHECKOUT_QUERY],
    ))


if __name__ == "__main__":
    main()