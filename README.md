# AnonBot

A Telegram bot that gives each of its users a permanent personal link.
Anyone who opens that link can send the owner an anonymous message, and the
owner can answer — as a real, threaded, two-way conversation, with the
sender's identity never revealed to them.

The owner is not anonymous; it is their own chat. Only the person writing to
them is.

Runs as its own process, its own repository and its own deployment, and can
be run entirely standalone. It shares a Postgres database with four sibling
bots only in the sense that its tables live in a schema of their own inside
it (`DB_SCHEMA`); no other bot reads or writes them. The one shared area is
`family.*`, where the bot posts a heartbeat and any crash so a monitoring bot
can watch it — `FAMILY_BUS=off` disables that entirely.

---

## Commands

| command | what it does |
|---|---|
| `/start` | Instructions. The first `/start` from a new user asks which language to use, once; afterwards it prints the instructions in the language on record. |
| `/link` | The user's permanent inbox link. Carries Pause / Resume and New-link buttons, so the three commands below are rarely typed. |
| `/newlink` | Issues a new link and invalidates the old one. Conversations already open keep working — they are routed by conversation, not by token. |
| `/pause`, `/resume` | Stop or allow *new* conversations. Open ones are unaffected. |
| `/blocked` | Lists blocked senders by conversation number, each with an Undo button. |
| `/stats` | How many distinct people have written, and how many conversations. |
| `/cancel` | Asks which of the things the bot is waiting on should stop, one button each, and stops nothing until one is chosen. |
| `/donate` | Voluntary contribution towards hosting, paid in Telegram Stars. |
| `/language`, `/en`, `/uz`, `/rus` | Switch language. Each reprints the instructions in the language chosen. |
| `/help` | The instructions on their own. |

Opening somebody's link is `/start q_<token>`, which the bot handles
automatically; it is not a command anyone types.

Three further commands — `/dbdump`, `/messageas` and `/status` — are
restricted to the account ids in `ABOT_ADMIN_ID`. To everyone else they
answer exactly as a misspelt command does, so their existence is not
disclosed.

---

## How a conversation is routed

The problem this bot solves is that one person's inbox link is posted
somewhere public, so a single chat ends up holding conversations with many
different strangers at once. Every message therefore has to say which
conversation it belongs to, and the bot has to be certain before it delivers
anything — a message sent to the wrong stranger is the one failure that
cannot be taken back.

**Every message is a reply, and Telegram's own reply feature is what says
so.** A swipe-reply and the ↩️ Reply button under each message resolve
identically: both produce a Telegram reply, which carries the id of the
message being answered.

**`anon_relay` maps `(chat_id, message_id) → conversation_id`** for every
message the bot delivers, into either chat. A reply is resolved through that
lookup rather than through "whichever button was tapped last", so it is
correct with several conversations interleaved and several Reply prompts
outstanding at once. A matched row says which *conversation*; the sender's
own account id says which *direction*.

**Both sides are held to the same rule.** Either party may answer any
conversation they are part of, for as long as its rows live — 180 days of
silence in that conversation.

**One message per conversation is exempt: the one that opens it.** It has
nothing above it to answer. The bot attaches a forced reply to the line that
announces a new conversation, so in practice even that message arrives as a
proper reply; the exemption is the fallback for clients that drop it, and it
applies only while the conversation just opened is still the newest thing in
the chat.

**An album is one message.** Several photos sharing a `media_group_id` are
routed by the first of them and announced once, rather than being treated as
three unrelated messages.

**Nothing is delivered on a guess.** A message that names no conversation is
held, not sent. Where exactly one destination is possible it is offered as a
*Send it anyway* button; where more than one is, the bot says so and sends
nothing.

**Whose words are whose.** Everything a person wrote arrives in italics;
everything the bot says for itself stays upright. Both land in the same
stream of bubbles, and that one difference separates them at a glance.

**No pseudonyms, no identifiers.** Threads are identified by number only.
Nothing shown to either side is derived from the other's account — including
the data inside buttons, which travels to the client.

### Limits

An inbox link is meant to be posted publicly, so both a per-minute message
limit and a cooldown between opening conversations apply per account, and a
ceiling on updates per minute applies before any handler runs. All are
configurable; see `.env.example`.

---

## Running it

```bash
pip install -r requirements.txt
cp .env.example .env          # fill in ABOT_TOKEN and ABOT_USERNAME
python bot.py
```

`ABOT_TOKEN` and `ABOT_USERNAME` come from
[@BotFather](https://t.me/BotFather). `ABOT_ADMIN_ID` is optional and takes
one or more numeric account ids.

The bot needs a Postgres database. `DATABASE_URL` points at it and
`DB_SCHEMA` (default `anon_bot`) selects the schema; the schema and its
tables are created on first run.

### Deploying

Set the same values as environment variables on the host and run
`python bot.py`. `railway.json` and `nixpacks.toml` configure a Railway
deployment; neither is required elsewhere.

A deployment replaces the running container, and the bot is built so that
costs nothing visible. The new process waits on a Postgres advisory lock
until the old one has stopped polling, so Telegram never sees two consumers
of one token. Open conversations and half-written state are restored from a
`runtime_state` table. Anyone whose message was mid-flight is told, rather
than left waiting. Updates sent during the gap are held by Telegram and
delivered on the first poll — nothing is lost. `DEPLOY_SAFETY=off` disables
all of it.

### Keeping two databases in sync

`db_merge.py` reconciles a local database with a remote one additively —
it never deletes or overwrites. It also remaps `anon_conversations`' internal
ids across the two so the tables that reference them stay correct.

```bash
python db_merge.py --from local --into cloud --dry-run
python db_merge.py --from local --into cloud
```

---

## Files

| file | |
|---|---|
| `bot.py` | Handlers, and the router that decides where a message goes |
| `anon_logic.py` | Message relaying, text splitting, styling, flood control |
| `db.py` | This bot's schema, queries and connection pool |
| `i18n.py` | English, Uzbek and Russian strings |
| `family_link.py` | Heartbeats, crash reporting, and the command queue a monitoring bot uses |
| `lifecycle.py` | Surviving a redeploy: one poller at a time, state in Postgres |
| `live_message.py` | When a bot message may keep evolving in place |
| `shared_features.py` | Donations, logging, activity tracking, flood control |
| `db_merge.py` | Reconciles two databases, additively |

`family_link.py`, `lifecycle.py`, `live_message.py` and `shared_features.py`
are shared with the sibling bots by being copied rather than imported: each
bot is a separate deployment, so nothing crosses a repository boundary.

## Requirements

Python 3.11 or newer, and Postgres 16 or newer.
