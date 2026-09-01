# AnonBot

Telegram bot for a one-sided anonymous inbox: an **owner** gets one
permanent link (`/link`) and posts it somewhere public; anyone who taps it
— a **follower** — can send the owner an anonymous message right there in
the bot chat. The owner's identity is never hidden (it's their own chat);
only the follower's is. Both sides answer the same way: reply to the message
you're answering, by swipe or by the Reply button under it.

This bot is its own process, its own repo and its own deployment — it can
be run entirely on its own. It shares one Postgres database with the rest
of the family, but only in the sense that its tables live in their own
schema inside it (`DB_SCHEMA` in `.env`); no other bot reads or writes
them. The exception is `family.*`, where this bot posts a heartbeat and
any crash so that ParentBot can watch it — see `family_link.py`, and
ARCHITECTURE.md in the family monorepo for why it is arranged this way. Set `FAMILY_BUS=off`
to opt out of that entirely.

## Commands

- `/link` — get your permanent inbox link
- `/newlink` — reset it (invalidates the old one; conversations already in
  progress keep working)
- `/pause` / `/resume` — stop/allow new conversations (open ones keep working)
- `/blocked` — review + undo who you've blocked
- `/stats` — distinct-follower and total-conversation counts for your inbox
- `/donate` — chip in for hosting costs (voluntary, Telegram Stars)
- `/cancel` — asks which of the things it is waiting on you for to stop,
  as one button each, and stops nothing until you pick. With nothing pending
  it says so straight away, as it always did — an open anonymous chat, or a reply
  it asked you for. Typing /cancel to escape a Reply prompt no longer walks
  you out of the conversation as well
- `/start` — the full instructions. The first `/start` from a brand-new
  user asks for a language before printing them, which is the one and only
  time it asks; after that it prints them in the language on record. A
  `/start q_<token>` inbox link goes straight to the inbox either way
- `/language` — the picker on demand: a short greeting in all three
  languages and one row of buttons, with a tick on the language in force.
  Choosing one (even the one already set) reprints the instructions in it
- `/en`, `/uz`, `/rus` — switch language directly, skipping the picker;
  each also reprints the instructions in the language just chosen
- `/help` — the instructions on their own

`/link`'s message also carries Pause/Resume and New-link buttons, so the
common case doesn't need `/pause`/`/resume`/`/newlink` typed out at all.

Tapping someone's link is `/start q_<token>` — handled automatically, not a
command you type.

Owner-only (requires `ABOT_ADMIN_ID` in `.env` — silently do nothing for
everyone else):
- `/messageas <user_id> <text>` — send a message to that user as this bot
- `/dbdump` — export this bot's tables as a zip of CSVs
- `/status` — uptime, host, crashes since this process started, active users

## How the threading works (for anyone reading the code)

- **Conversations, not just messages** (`anon_conversations`): every time
  someone taps an owner's link, that's a brand-new row — tapping the same
  link again *always* starts a fresh conversation, never continues an old
  one. `conv_number` counts per (owner, follower) pair.
- **Reply-threading, both directions** (`anon_logic.relay_content()`):
  every message relays through `copy_message` (no "Forwarded from" tag)
  with `reply_to_message_id` set to the relevant rolling anchor, so both
  sides see a real, visibly-threaded back-and-forth via Telegram's own
  reply-quote UI — even with several conversations interleaved in the same
  chat.
- **Knowing which reply goes where** (`anon_relay`): every message this bot
  delivers — into either chat — gets one row here, `(chat_id, message_id) ->
  conversation_id`. A reply, native swipe or the Reply button's forced
  prompt, resolves through this lookup rather than through "whichever button
  was tapped most recently", so it is correct even with several Reply prompts
  outstanding at once. A matched row says which *conversation*; the sender's
  own id says which *direction*.
- **Every message says what it answers, except the one that opens a thread.**
  Exactly one message per conversation may be sent without naming what it
  replies to: the guest's opening one, which has nothing above it —
  `follower_first_msg_at` marks that exemption spent. Everything after it,
  from either side, has to be a reply. A link is posted somewhere public and
  one person ends up answering several, so "whichever thread was touched most
  recently" is not a guess worth making: an owner who was also mid-session
  with somebody else's inbox used to have their answer delivered to that other
  conversation entirely, and be told "Sent".
- **The way past it, only where it cannot go wrong.** A held message gets a
  *Send it anyway* button when there is exactly one place it could have gone —
  an open session and no inbox of your own. With several conversations in play
  the bot says so and sends nothing, rather than making by button the same
  guess the rule exists to stop.
- **Whose words are whose** (`anon_logic.italicize()`): everything a person
  wrote arrives in italics; everything the bot says for itself stays upright.
  Both land in the same chat, and that one difference is what separates them
  at a glance.
- **No pseudonyms.** Messages and `/blocked` identify a thread by its
  conversation number only. Nothing shown to either side is derived from the
  other's account.

## Setup

1. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and fill in `ABOT_TOKEN`/`ABOT_USERNAME`
   (from [@BotFather](https://t.me/BotFather)). Optionally set `ABOT_ADMIN_ID`
   to your own numeric user id(s) to unlock `/dbdump`.
3. Start the family's shared Postgres, from the monorepo root:
   ```
   docker compose up -d
   ```
   That is one database (`botfamily`) for all five bots, with a schema
   each — this one uses `DB_SCHEMA=anon_bot`. No Docker? Install
   Postgres directly and point `DATABASE_URL` at it instead.
4. Run it:
   ```
   python bot.py
   ```

## Deploying (e.g. Railway)

The short version is below; DEPLOY.md in the family monorepo covers all five in one
pass, which is easier than doing five of these separately.

1. Point `DATABASE_URL` at the family's Postgres, and set `DB_SCHEMA` to
   `anon_bot`. On Railway that first one is a reference variable,
   `${{Postgres.DATABASE_URL}}`, so several services can share one database.
2. Set `ABOT_TOKEN`, `ABOT_USERNAME`, and the rest of `.env` as environment
   variables on the service.
3. Deploy — `pip install -r requirements.txt` then `python bot.py`.

### Updating a running bot

Pushing an update replaces the container, and the bots are set up so nobody
notices: the new process waits on a Postgres advisory lock until the old one
has stopped polling (no 409 Conflict, no split updates), open conversations
and half-finished sessions are restored from the `runtime_state` table in
this bot's own schema, and anyone whose upload was mid-flight is told to send
it again rather than left waiting. Updates sent during the gap are held by
Telegram and delivered on the first poll.

`../UPDATES.md` has the whole picture, including what to check after a push.
`DEPLOY_SAFETY=off` turns all of it off and restores the old behaviour.

## Keeping a local and cloud database in sync

If you ever run this bot from both your laptop and the cloud at different
times, `db_merge.py` reconciles the two additively (never deletes or
overwrites anything). It also handles the one tricky part here —
`anon_conversations`' internal id is remapped safely across the two
databases so `anon_follower_state`/`anon_relay` still point at the right
place afterwards:
```
python db_merge.py --from local --into cloud --dry-run   # preview first
python db_merge.py --from local --into cloud             # actually do it
```
Read the script's docstring for exactly how conflicts are handled.

## Optional: cross-promoting sibling bots

If you're running this alongside other bots and want each to mention the
others in `/start`/`/help`, set `SIBLING_BOTS` in `.env` — see the comment
in `shared_features.py`. Purely cosmetic (display text + link buttons); no
database or file is shared.

## Files

- `bot.py` — handlers and the owner/follower message router
- `anon_logic.py` — the reply-relay logic and the italic styling
- `db.py` — this bot's own Postgres schema and queries
- `family_link.py` — heartbeats, crash reporting, and the queue ParentBot
  uses to run this bot's owner-only commands (identical in every bot)
- `live_message.py` — the rule that a bot message only keeps evolving while
  it is still the last thing in the chat (identical in every bot)
- `lifecycle.py` — surviving a redeploy: one poller at a time, state kept in
  Postgres, in-flight work announced (identical in every bot)
- `shared_features.py` — `/donate` (Telegram Stars) + sibling-bot cross-promotion
- `db_merge.py` — reconciles a laptop database with the cloud one, additively (see above)
