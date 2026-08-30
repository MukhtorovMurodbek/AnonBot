"""Pure-ish logic for AnonBot -- StickerBot-family sibling #4 (see
ARCHITECTURE.md). Same split as image_utils.py / convert_utils.py / video.py
in the other bots: this file owns the parts that don't need to know about
ApplicationBuilder/handlers, and bot.py owns the Telegram wiring.

relay_content() delivers one message's content into another chat as a plain
(non-forwarded) message, optionally as a native reply-to and/or with a header
line, and optionally with buttons. It is the one piece that makes a reply
"look like they actually replied" on the receiving end -- and it is also what
lets either side's chat thread several simultaneous conversations via
Telegram's native reply-quote instead of one flat, confusing feed.

Everything a *person* wrote is relayed in italics; everything the bot says
for itself (headers, confirmations, prompts) stays upright. In a chat where
both arrive in the same bubble stream, that one difference is what tells you
at a glance which words are somebody else's.
"""
import html

from telegram.constants import ParseMode
from telegram.error import BadRequest


def italicize(text: str) -> str:
    """Someone else's words, marked as theirs. Escaped first: a guest who
    types <b>hi</b> should see <b>hi</b> arrive, not bold text, and should
    certainly not be able to close the tag this wraps them in."""
    return f"<i>{html.escape(text)}</i>"


async def relay_content(
    bot, message, to_chat_id,
    reply_to_message_id=None, reply_markup=None, header=None, italic=True,
):
    """Delivers `message`'s content into `to_chat_id`, preserving whatever it
    is (text, photo, video, voice, sticker, document, ...) with no "Forwarded
    from" tag -- copy_message handles every content type Telegram lets a bot
    copy, so there is no need to branch on message.photo / message.video /
    etc. here, the way convert_bot's file handling does.

    Plain text gets its own path (send_message, not copy_message) purely so
    `header` can be prepended into the SAME bubble -- copy_message has no way
    to alter a text message's body. A captioned media message keeps one
    bubble too: copy_message *can* replace a caption, so the header and the
    italicised caption go together underneath it. Only media with no caption
    of its own needs the header as a separate line above.

    `reply_to_message_id` is what makes the delivered message show up as a
    genuine Telegram reply on the receiving end. If that anchor message was
    since deleted, Telegram rejects the whole send -- so this retries once
    without it rather than losing the message entirely.

    Returns the list of Message/MessageId objects actually sent, in send
    order (normally one; two for uncaptioned media with a header).
    """

    def _compose(body: str | None) -> str:
        """Bot's own header upright, the person's own words in italics."""
        parts = []
        if header:
            parts.append(html.escape(header))
        if body:
            parts.append(italicize(body) if italic else html.escape(body))
        return "\n\n".join(parts)

    async def _send_text(text, reply_to, markup):
        try:
            return await bot.send_message(
                chat_id=to_chat_id, text=text, reply_to_message_id=reply_to,
                reply_markup=markup, parse_mode=ParseMode.HTML,
            )
        except BadRequest as exc:
            if reply_to and "repl" in str(exc).lower():
                return await bot.send_message(
                    chat_id=to_chat_id, text=text, reply_markup=markup,
                    parse_mode=ParseMode.HTML,
                )
            raise

    async def _copy(reply_to, markup, caption=None):
        kwargs = {}
        if caption is not None:
            kwargs = {"caption": caption, "parse_mode": ParseMode.HTML}
        try:
            return await bot.copy_message(
                chat_id=to_chat_id,
                from_chat_id=message.chat_id,
                message_id=message.message_id,
                reply_to_message_id=reply_to,
                reply_markup=markup,
                **kwargs,
            )
        except BadRequest as exc:
            if reply_to and "repl" in str(exc).lower():
                return await bot.copy_message(
                    chat_id=to_chat_id, from_chat_id=message.chat_id,
                    message_id=message.message_id, reply_markup=markup, **kwargs,
                )
            raise

    if message.text is not None:
        return [await _send_text(_compose(message.text), reply_to_message_id, reply_markup)]

    if message.caption is not None:
        return [await _copy(reply_to_message_id, reply_markup, caption=_compose(message.caption))]

    sent = []
    if header:
        sent.append(await _send_text(_compose(None), reply_to_message_id, None))
        reply_to_message_id = None  # already visually anchored by the header line right above

    sent.append(await _copy(reply_to_message_id, reply_markup))
    return sent
