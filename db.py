"""Postgres layer for AnonBot -- these tables are this bot's
alone. The family shares one Postgres database now, but each bot gets its
own schema in it (DB_SCHEMA below), and no bot reads or writes another's
tables; the only shared tables are `family.*`, which family_link.py owns.

Owns the anonymous-inbox links, conversations,
and reply-routing (who owns which link, which conversation a follower's next
message belongs to, which owner-chat message maps to which conversation for
reply-swipes, and who's blocked whom), plus a Telegram Stars ledger +
donation-reminder cooldown for this bot's own /donate flow.

Postgres was chosen (over SQLite) so this survives an ephemeral cloud
container redeploy -- see DEPLOY.md.
"""
import logging
import os
import time
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timezone

from urllib.parse import urlsplit

import psycopg
from psycopg_pool import ConnectionPool

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/anonbot"
)


# --- one shared database, one schema per bot ---------------------------------
# The whole family now lives in ONE Postgres database, with a schema per bot
# (family_link.py has the full layout). DB_SCHEMA is the one this bot owns.
# Nothing else in this file had to change: every statement below is still
# written against bare table names, and search_path resolves them into this
# bot's own schema, so the four bots' identically-named tables
# (user_settings, star_transactions, activity_events, ...) never collide.
# Leaving DB_SCHEMA unset keeps the old behaviour -- "public" in a database
# this bot has entirely to itself.
DB_SCHEMA = os.environ.get("DB_SCHEMA", "public")

# ---------------------------------------------------------------------------
# Connection-string sanity check
# ---------------------------------------------------------------------------
# Two ways of pointing a bot at a cloud Postgres fail *quietly* rather than
# loudly, so both are worth catching at startup instead of in the data:
#
#   Transaction pooling -- Supabase/Supavisor on port 6543, or PgBouncer in
#   transaction mode -- multiplexes many clients over a few server
#   connections, so per-connection startup options do not survive from one
#   transaction to the next. The pool below passes search_path as exactly
#   such an option, which means the bot would read and write "public"
#   instead of its own schema, while still heartbeating perfectly. That
#   surfaces as wrong data rather than as a broken bot, which is the worst
#   way to find out. The session pooler (port 5432) keeps one server
#   connection per client and is the right one here.
#
#   An unencoded "@" or ":" in the password splits the URL in the wrong
#   place, so libpq ends up resolving a hostname that is really the tail of
#   the password -- a DNS error that says nothing about the real cause.
#
# These warn rather than refuse: an unusual setup is the owner's business,
# and a bot that will not start is worse than one that says why it might
# misbehave.
TRANSACTION_POOLER_PORTS = {6543}


def check_database_url(dsn: str = DATABASE_URL) -> list[str]:
    """Human-readable warnings about `dsn`; empty when it looks sane."""
    problems: list[str] = []
    try:
        parts = urlsplit(dsn)
    except ValueError as exc:
        return [f"DATABASE_URL could not be parsed ({exc})."]

    if parts.netloc.count("@") > 1:
        problems.append(
            "DATABASE_URL contains more than one '@'. If that is a literal "
            "'@' in the password, percent-encode it (@ -> %40, : -> %3A, "
            "/ -> %2F, # -> %23); otherwise the host is read from the wrong "
            "part of the string."
        )

    try:
        port = parts.port
    except ValueError:
        problems.append(
            "DATABASE_URL's port is not a number -- an unencoded ':' or '@' "
            "in the password is the usual reason."
        )
        port = None

    if port in TRANSACTION_POOLER_PORTS:
        problems.append(
            f"DATABASE_URL points at port {port}, which is a TRANSACTION "
            f"pooler. search_path is passed as a connection option and "
            f"transaction pooling discards it, so this bot would silently "
            f"use the 'public' schema instead of {DB_SCHEMA!r}. Use the "
            f"session pooler (port 5432)."
        )

    return problems



# ---------------------------------------------------------------------------
# One pooled connection per process
# ---------------------------------------------------------------------------
# Every function below used to open -- and immediately throw away -- its own
# Postgres connection. On a small shared cloud database that is by far the
# most expensive thing this bot does: a TCP round trip, a TLS handshake and a
# freshly forked backend process on the server, all to run one INSERT that
# takes microseconds. At one connection per Telegram update (plus one per
# heartbeat, per command poll, per donation check) it is also what decides
# how big the database instance has to be.
#
# A pool keeps a warm connection open instead and hands it out. Sized for
# cheap: one connection held, a couple more only while several things happen
# at once, and any extra handed back to the server after DB_POOL_MAX_IDLE
# seconds -- so an idle bot costs the database exactly one backend.
POOL_MIN = int(os.environ.get("DB_POOL_MIN", "1"))
POOL_MAX = int(os.environ.get("DB_POOL_MAX", "3"))
POOL_MAX_IDLE = float(os.environ.get("DB_POOL_MAX_IDLE", "120"))
POOL_TIMEOUT = float(os.environ.get("DB_POOL_TIMEOUT", "15"))

# How long a pooled connection may sit unused before it is worth spending a
# round trip proving it is still alive. See _check_if_idle: the check was
# unconditional, and against a database on the other side of the world an
# unconditional check is the single most expensive thing about a small query.
POOL_CHECK_AFTER_IDLE = float(os.environ.get("DB_POOL_CHECK_AFTER_IDLE", "45"))

_pool: "ConnectionPool | None" = None
# id(connection) -> when it was last known good. Bounded by max_size. An id
# can be reused after a connection is closed, and the worst that costs is a
# skipped check on a connection that was only just opened -- which is alive
# by construction.
_last_known_good: "dict[int, float]" = {}


def _check_if_idle(conn) -> None:
    """The pool's checkout check, but only for connections that have actually
    been sitting there.

    A connection idle across a cloud provider's own network timeout comes back
    dead, and `ConnectionPool.check_connection` is the guard against handing
    one out. It is also a full round trip, and it was being paid on every
    checkout -- including the checkout half a second after the last one, on a
    connection that could not possibly have gone stale in between.

    That is most of them. It cost a quarter of a second each back when this
    bot's database was in ap-northeast-2 and the container in EU West -- a
    third of the cost of every read. Since v1.2.0 the database is in
    eu-central-1, beside the containers, which cuts the absolute cost by an
    order of magnitude but leaves the ratio alone: the check is still a whole
    extra round trip per read. A connection used within the last
    POOL_CHECK_AFTER_IDLE seconds is taken as alive, and everything quieter
    than that is still proved before use.
    """
    key = id(conn)
    now = time.monotonic()
    seen = _last_known_good.get(key)
    if seen is None or now - seen > POOL_CHECK_AFTER_IDLE:
        ConnectionPool.check_connection(conn)
    _last_known_good[key] = now
    if len(_last_known_good) > 4 * max(POOL_MAX, 1):
        for stale in [k for k, t in _last_known_good.items() if now - t > 3600]:
            _last_known_good.pop(stale, None)


def _get_pool() -> ConnectionPool:
    """Created on first use, never at import time -- init_db() has to be able
    to create the schema before anything connects into it."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            DATABASE_URL,
            min_size=POOL_MIN,
            max_size=POOL_MAX,
            max_idle=POOL_MAX_IDLE,
            timeout=POOL_TIMEOUT,
            kwargs={
                "options": f"-c search_path={DB_SCHEMA},public",
                # Keep an idle connection alive at the TCP level rather than
                # discovering it is dead on the next checkout. Cheaper than
                # the check it saves, and it happens while nobody is waiting.
                "keepalives": 1, "keepalives_idle": 30,
                "keepalives_interval": 10, "keepalives_count": 5,
            },
            check=_check_if_idle,
            name=f"{DB_SCHEMA}",
            open=True,
        )
    return _pool


def pooled():
    """A connection from the pool, as a context manager. The transaction is
    committed on a clean exit and rolled back on an exception; the connection
    itself goes back to the pool either way rather than being closed.

    For anything that writes. Reads should use pooled_read(), which is the
    same connection without the transaction around it."""
    return _get_pool().connection()


@contextmanager
def pooled_read():
    """A pooled connection in autocommit, for statements that only read.

    A read through pooled() costs three round trips to the database: the
    implicit BEGIN that psycopg opens with the first statement, the statement
    itself, and the COMMIT the context manager sends on the way out. Two of
    those exist to make a transaction nobody needed -- a single SELECT is
    atomic on its own.

    Measured against the family's actual database, one read: 28 ms through
    pooled(), 9 ms through this. The same shape holds wherever the database
    is; it is round trips, so it scales with the distance rather than washing
    out. Everything that writes -- and anything reading several statements
    that have to agree with each other -- still goes through pooled().
    """
    with _get_pool().connection() as conn:
        conn.set_autocommit(True)
        try:
            yield conn
        finally:
            # Back to the pool as it was found, so pooled() still gets a
            # connection that opens a transaction.
            try:
                conn.set_autocommit(False)
            except Exception:
                logging.getLogger(__name__).debug("Could not restore transaction mode", exc_info=True)


def close_pool() -> None:
    """Shutdown hook -- lets the process exit without waiting on the pool's
    own worker threads."""
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None


def connect(dsn: str = DATABASE_URL):
    """A brand-new, unpooled connection to an arbitrary database. Only the
    offline tools (db_merge.py) need this, because they hold two databases
    open at once and drive the transaction by hand. Everything in this module
    goes through pooled() instead."""
    return psycopg.connect(dsn, options=f"-c search_path={DB_SCHEMA},public")


def ensure_schema(dsn: str = DATABASE_URL) -> None:
    """Deliberately connects *without* the search_path option -- the schema
    it is about to create may not exist yet, and libpq would not complain
    but every later CREATE TABLE would land in public instead."""
    with closing(psycopg.connect(dsn)) as conn:
        conn.execute(f'CREATE SCHEMA IF NOT EXISTS "{DB_SCHEMA}"')
        conn.commit()


def init_db(dsn: str = DATABASE_URL) -> None:
    for _problem in check_database_url(dsn):
        logging.getLogger(__name__).warning("%s", _problem)

    # Deliberately on a plain connection rather than the pool: the offline
    # tools (db_merge.py, migrate_to_shared_db.py) call this against a
    # *different* database than the one this process serves, and the pool
    # is bound to DATABASE_URL. It runs once, so there is nothing to save.
    ensure_schema(dsn)
    with closing(connect(dsn)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS star_transactions (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                username TEXT,
                amount_stars BIGINT NOT NULL,
                item TEXT NOT NULL,
                status TEXT NOT NULL,
                payload TEXT NOT NULL UNIQUE,
                charge_id TEXT,
                currency TEXT NOT NULL DEFAULT 'XTR',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        # Both safe to re-run on an existing table -- widens amount_stars
        # since some fiat currencies' minor-unit amounts can exceed a plain
        # INTEGER's range, and adds currency for bots migrating from
        # Stars-only donations (see shared_features.py's FIAT_CURRENCIES).
        conn.execute("ALTER TABLE star_transactions ALTER COLUMN amount_stars TYPE BIGINT")
        conn.execute("ALTER TABLE star_transactions ADD COLUMN IF NOT EXISTS currency TEXT NOT NULL DEFAULT 'XTR'")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS donation_prompts (
                user_id BIGINT PRIMARY KEY,
                action_count INTEGER NOT NULL DEFAULT 0,
                last_shown_at TEXT
            )
            """
        )
        # Nullable, no default -- NULL means "hasn't picked a language yet",
        # which is what gates the first-run picker in bot.py's /start.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_settings (
                user_id BIGINT PRIMARY KEY,
                language TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS anon_links (
                owner_user_id BIGINT PRIMARY KEY,
                token TEXT NOT NULL UNIQUE,
                is_paused INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS anon_conversations (
                id BIGSERIAL PRIMARY KEY,
                owner_user_id BIGINT NOT NULL,
                follower_user_id BIGINT NOT NULL,
                conv_number INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                last_activity_at TEXT NOT NULL,
                last_owner_msg_id BIGINT,
                last_follower_msg_id BIGINT
            )
            """
        )
        # Set when the guest sends their FIRST message in a conversation.
        # That one message is the only one either side may send without
        # saying what it answers -- it is the one that opens the thread, and
        # there is genuinely nothing above it. See handle_message.
        conn.execute("ALTER TABLE anon_conversations ADD COLUMN IF NOT EXISTS follower_first_msg_at TEXT")
        # Replaced by the column above. It asked "has the owner answered
        # yet?", which exempted every message a guest sent to an owner who
        # never answered -- so a guest's whole side of a one-way conversation
        # was still being routed by session state rather than by what it
        # replied to.
        conn.execute("ALTER TABLE anon_conversations DROP COLUMN IF EXISTS owner_replied_at")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_anon_conversations_pair "
            "ON anon_conversations (owner_user_id, follower_user_id)"
        )
        # Natural key for a conversation -- also what scripts/db_merge.py
        # matches on when reconciling a local DB with a cloud one.
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_anon_conversations_natural "
            "ON anon_conversations (owner_user_id, follower_user_id, conv_number)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS anon_follower_state (
                follower_user_id BIGINT PRIMARY KEY,
                owner_user_id BIGINT NOT NULL,
                conversation_id BIGINT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS anon_relay (
                chat_id BIGINT NOT NULL,
                message_id BIGINT NOT NULL,
                conversation_id BIGINT NOT NULL,
                PRIMARY KEY (chat_id, message_id)
            )
            """
        )
        # True for the Reply button's ForceReply prompt, and only for that.
        # The prompt is scaffolding: it exists to pin the reply box to one
        # conversation, and once the reply it asked for has arrived it has
        # nothing left to say. Knowing which rows are prompts is what lets
        # bot.py take them back down again -- and it has to be knowable from
        # the database rather than from user_data, because the tap and the
        # reply can land in different processes.
        conn.execute("ALTER TABLE anon_relay ADD COLUMN IF NOT EXISTS is_prompt BOOLEAN NOT NULL DEFAULT FALSE")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS anon_blocks (
                owner_user_id BIGINT NOT NULL,
                follower_user_id BIGINT NOT NULL,
                blocked_at TEXT NOT NULL,
                PRIMARY KEY (owner_user_id, follower_user_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS activity_events (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                occurred_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_activity_events_occurred_at ON activity_events (occurred_at)"
        )
        conn.commit()


# ---------- /status active-user tracking ----------

def record_activity_batch(user_ids) -> None:
    """One row per user per flush window -- see shared_features.py's
    track_activity, which buffers them. Sent as a single statement whatever
    the batch size: both readers of this table are COUNT(DISTINCT user_id)
    over a time window, so nothing depends on a row per update."""
    ids = list(user_ids)
    if not ids:
        return
    with pooled() as conn:
        conn.execute(
            "INSERT INTO activity_events (user_id, occurred_at) "
            "SELECT unnest(%s::bigint[]), now()",
            (ids,),
        )
        conn.commit()


def count_active_users_since(since) -> int:
    with pooled_read() as conn:
        cur = conn.execute(
            "SELECT COUNT(DISTINCT user_id) FROM activity_events WHERE occurred_at >= %s",
            (since,),
        )
        return cur.fetchone()[0]


def list_all_users() -> list[int]:
    """Everyone this bot could send an unprompted message to.

    The union of two tables because neither is the whole answer on its own:
    user_settings has a row per person who has ever picked a setting and is never
    pruned, while activity_events reaches people who only ever used the bot
    without changing anything -- but is pruned at ACTIVITY_RETENTION_DAYS.
    Together they are "everyone we still know about", which is the honest
    scope of a broadcast.
    """
    with pooled_read() as conn:
        cur = conn.execute(
            "SELECT user_id FROM user_settings "
            "UNION "
            "SELECT DISTINCT user_id FROM activity_events"
        )
        return [int(r[0]) for r in cur.fetchall()]


def get_user_language(user_id: int) -> str | None:
    """None means the user hasn't picked a language yet (no row, or a row
    with no language set)."""
    with pooled_read() as conn:
        cur = conn.execute("SELECT language FROM user_settings WHERE user_id = %s", (user_id,))
        row = cur.fetchone()
        return row[0] if row else None


def set_user_language(user_id: int, language: str) -> None:
    with pooled() as conn:
        conn.execute(
            """
            INSERT INTO user_settings (user_id, language) VALUES (%s, %s)
            ON CONFLICT (user_id) DO UPDATE SET language = excluded.language
            """,
            (user_id, language),
        )
        conn.commit()


# ---------- Telegram Stars ledger (this bot's /donate only) ----------

def record_star_invoice(
    user_id: int,
    username: str | None,
    amount_stars: int,
    item: str,
    payload: str,
    status: str = "invoiced",
    currency: str = "XTR",
) -> None:
    """amount_stars is in the currency's smallest unit for fiat currencies
    (see shared_features.py's FIAT_CURRENCIES), or a plain Stars count for
    the default currency="XTR"."""
    now = datetime.now(timezone.utc).isoformat()
    with pooled() as conn:
        conn.execute(
            """
            INSERT INTO star_transactions
                (user_id, username, amount_stars, item, status, payload, currency, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (user_id, username, amount_stars, item, status, payload, currency, now, now),
        )
        conn.commit()


def update_star_transaction(payload: str, status: str, charge_id: str | None = None) -> None:
    with pooled() as conn:
        conn.execute(
            "UPDATE star_transactions SET status = %s, charge_id = COALESCE(%s, charge_id), updated_at = %s WHERE payload = %s",
            (status, charge_id, datetime.now(timezone.utc).isoformat(), payload),
        )
        conn.commit()


# ---------- donation-reminder cooldown ----------

def bump_donation_action(user_id: int) -> tuple[int, str | None]:
    """Increments this user's action counter and returns (new total, when the
    nudge was last shown). One statement, because this runs on the success
    path of every completed action and the two halves were previously two
    separate round trips."""
    with pooled() as conn:
        cur = conn.execute(
            """
            INSERT INTO donation_prompts (user_id, action_count, last_shown_at)
            VALUES (%s, 1, NULL)
            ON CONFLICT (user_id) DO UPDATE SET action_count = donation_prompts.action_count + 1
            RETURNING action_count, last_shown_at
            """,
            (user_id,),
        )
        row = cur.fetchone()
        conn.commit()
        return row[0], row[1]


def reset_donation_prompt(user_id: int) -> None:
    """Zeroes the action counter and stamps 'last_shown_at' -- call right
    after actually showing the nudge, not on every check."""
    now = datetime.now(timezone.utc).isoformat()
    with pooled() as conn:
        conn.execute(
            """
            INSERT INTO donation_prompts (user_id, action_count, last_shown_at)
            VALUES (%s, 0, %s)
            ON CONFLICT (user_id) DO UPDATE SET action_count = 0, last_shown_at = excluded.last_shown_at
            """,
            (user_id, now),
        )
        conn.commit()


# ---------- AnonBot: anonymous-inbox links, conversations, reply routing, blocks ----------

def get_or_create_anon_link(owner_user_id: int) -> tuple[str, bool]:
    """(token, is_paused) for this owner, creating the row on first use. The
    token never changes on its own -- only regenerate_anon_link() rolls it.

    One statement: an upsert that does nothing on conflict still RETURNINGs
    nothing, so the read comes first and the insert only runs for a genuinely
    new owner. /link used to call this and then get_anon_link_state, which
    was two round trips for two columns of the same row."""
    with pooled() as conn:
        cur = conn.execute(
            "SELECT token, is_paused FROM anon_links WHERE owner_user_id = %s", (owner_user_id,)
        )
        row = cur.fetchone()
        if row:
            return row[0], bool(row[1])
        token = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO anon_links (owner_user_id, token, is_paused, created_at) "
            "VALUES (%s, %s, 0, %s) ON CONFLICT (owner_user_id) DO NOTHING",
            (owner_user_id, token, datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
        return token, False


def regenerate_anon_link(owner_user_id: int) -> tuple[str, bool]:
    """Fresh token -- invalidates the old link for NEW conversations.
    Conversations already in progress keep working since they're routed by
    conversation_id, not by the token.

    Returns (token, is_paused). The paused flag is deliberately left alone --
    a new link on a paused inbox is still paused -- and returned so the
    caller can redraw the screen without a second query for it."""
    token = uuid.uuid4().hex
    with pooled() as conn:
        cur = conn.execute(
            """
            INSERT INTO anon_links (owner_user_id, token, is_paused, created_at) VALUES (%s, %s, 0, %s)
            ON CONFLICT (owner_user_id) DO UPDATE SET token = excluded.token
            RETURNING token, is_paused
            """,
            (owner_user_id, token, datetime.now(timezone.utc).isoformat()),
        )
        row = cur.fetchone()
        conn.commit()
    return row[0], bool(row[1])


def get_link_view(token: str, follower_user_id: int) -> tuple[int | None, bool, bool]:
    """Everything the "someone tapped a link" path needs to decide what to
    do: (owner id or None, is the inbox paused, has this follower been
    blocked). One query where there used to be three, on a path that runs
    every time anyone opens anyone's inbox link."""
    with pooled_read() as conn:
        cur = conn.execute(
            """
            SELECT l.owner_user_id, l.is_paused,
                   EXISTS (SELECT 1 FROM anon_blocks b
                           WHERE b.owner_user_id = l.owner_user_id
                             AND b.follower_user_id = %s)
            FROM anon_links l WHERE l.token = %s
            """,
            (follower_user_id, token),
        )
        row = cur.fetchone()
        if not row:
            return None, False, False
        return row[0], bool(row[1]), bool(row[2])


def get_delivery_context(owner_user_id: int, follower_user_id: int) -> tuple[bool, bool, str | None]:
    """(is this follower blocked, does the inbox still exist, the owner's
    language). One query on the hot path of every anonymous message -- it was
    three, and the third of them was a whole extra connection just to look up
    which language to write the header in."""
    with pooled_read() as conn:
        cur = conn.execute(
            """
            SELECT EXISTS (SELECT 1 FROM anon_blocks
                           WHERE owner_user_id = %s AND follower_user_id = %s),
                   EXISTS (SELECT 1 FROM anon_links WHERE owner_user_id = %s),
                   (SELECT language FROM user_settings WHERE user_id = %s)
            """,
            (owner_user_id, follower_user_id, owner_user_id, owner_user_id),
        )
        blocked, inbox_exists, language = cur.fetchone()
        return bool(blocked), bool(inbox_exists), language



def set_anon_link_paused(owner_user_id: int, paused: bool) -> None:
    with pooled() as conn:
        conn.execute(
            "UPDATE anon_links SET is_paused = %s WHERE owner_user_id = %s", (int(paused), owner_user_id)
        )
        conn.commit()


def get_anon_link_state(owner_user_id: int) -> dict | None:
    with pooled_read() as conn:
        cur = conn.execute(
            "SELECT token, is_paused, created_at FROM anon_links WHERE owner_user_id = %s", (owner_user_id,)
        )
        row = cur.fetchone()
        if not row:
            return None
        return {"token": row[0], "is_paused": bool(row[1]), "created_at": row[2]}


def start_new_anon_conversation(owner_user_id: int, follower_user_id: int) -> dict:
    """Always creates a brand-new conversation row -- this is what makes
    tapping the link again 'the start of a new conversation' -- and points
    the follower's active-routing state at it, so their very next un-replied
    message lands here instead of wherever they left off before."""
    with pooled() as conn:
        # Numbered per OWNER, not per (owner, follower) pair. The number is
        # the only thing either side is ever told about a thread, and per-pair
        # numbering restarted it at 1 for every new person -- so three
        # different strangers all arrived in the owner's chat as
        # "Conversation #1", and /blocked listed two separate guests both
        # described as "#1". Existing rows are left exactly as they are: the
        # owner has already read those numbers in their own chat and
        # renumbering would rewrite what they saw. Because this takes the
        # owner's highest number rather than the pair's, every number issued
        # from here on is above all of them, so no NEW collision can appear.
        cur = conn.execute(
            "SELECT COALESCE(MAX(conv_number), 0) FROM anon_conversations "
            "WHERE owner_user_id = %s",
            (owner_user_id,),
        )
        conv_number = cur.fetchone()[0] + 1
        now = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            """
            INSERT INTO anon_conversations
                (owner_user_id, follower_user_id, conv_number, started_at, last_activity_at,
                 last_owner_msg_id, last_follower_msg_id)
            VALUES (%s, %s, %s, %s, %s, NULL, NULL)
            RETURNING id
            """,
            (owner_user_id, follower_user_id, conv_number, now, now),
        )
        conversation_id = cur.fetchone()[0]
        conn.execute(
            """
            INSERT INTO anon_follower_state (follower_user_id, owner_user_id, conversation_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (follower_user_id) DO UPDATE SET
                owner_user_id = excluded.owner_user_id, conversation_id = excluded.conversation_id
            """,
            (follower_user_id, owner_user_id, conversation_id),
        )
        conn.commit()
        return {
            "id": conversation_id, "conv_number": conv_number,
            "owner_user_id": owner_user_id, "follower_user_id": follower_user_id,
            "last_owner_msg_id": None, "last_follower_msg_id": None,
        }


def get_active_conversation_for_follower(follower_user_id: int) -> dict | None:
    """Where a follower's next un-prompted message should be routed --
    'active' meaning 'the conversation their most recent /start link tap
    pointed at', see start_new_anon_conversation()."""
    with pooled_read() as conn:
        cur = conn.execute(
            "SELECT owner_user_id, conversation_id FROM anon_follower_state WHERE follower_user_id = %s",
            (follower_user_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        owner_user_id, conversation_id = row
        cur = conn.execute(
            "SELECT conv_number, last_owner_msg_id, last_follower_msg_id, follower_first_msg_at "
            "FROM anon_conversations WHERE id = %s",
            (conversation_id,),
        )
        conv_row = cur.fetchone()
        if not conv_row:
            return None
        return {
            "id": conversation_id, "owner_user_id": owner_user_id, "follower_user_id": follower_user_id,
            "conv_number": conv_row[0], "last_owner_msg_id": conv_row[1], "last_follower_msg_id": conv_row[2], "follower_first_msg_at": conv_row[3],
        }


def get_conversation(conversation_id: int) -> dict | None:
    with pooled_read() as conn:
        cur = conn.execute(
            """
            SELECT owner_user_id, follower_user_id, conv_number, last_owner_msg_id,
                   last_follower_msg_id, follower_first_msg_at
            FROM anon_conversations WHERE id = %s
            """,
            (conversation_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "id": conversation_id, "owner_user_id": row[0], "follower_user_id": row[1],
            "conv_number": row[2], "last_owner_msg_id": row[3], "last_follower_msg_id": row[4],
            "follower_first_msg_at": row[5],
        }



def record_anon_relays(chat_id: int, message_ids, conversation_id: int, is_prompt: bool = False) -> None:
    """Remembers 'these messages, in this chat, belong to this conversation'
    so a later reply -- a native swipe-reply, or the Reply button's forced
    reply prompt -- can be traced back to the right thread even with many
    conversations interleaved in the same chat.

    Takes a list because a media message with a header goes out as two, and
    both are valid reply anchors; one statement covers however many.

    `is_prompt` marks the Reply button's own prompt, which is the one kind of
    row that is meant to be deleted again once it has been answered."""
    ids = list(message_ids)
    if not ids:
        return
    with pooled() as conn:
        conn.execute(
            "INSERT INTO anon_relay (chat_id, message_id, conversation_id, is_prompt) "
            "SELECT %s, unnest(%s::bigint[]), %s, %s "
            "ON CONFLICT (chat_id, message_id) DO UPDATE SET "
            "conversation_id = excluded.conversation_id, is_prompt = excluded.is_prompt",
            (chat_id, ids, conversation_id, is_prompt),
        )
        conn.commit()


def forget_anon_relay(chat_id: int, message_id: int) -> None:
    """Drop one relay row -- for a Reply prompt that has been answered and
    deleted, so nothing is left pointing at a message that no longer exists."""
    with pooled() as conn:
        conn.execute(
            "DELETE FROM anon_relay WHERE chat_id = %s AND message_id = %s",
            (chat_id, message_id),
        )
        conn.commit()


def record_relay_and_touch(
    chat_id: int, message_ids, conversation_id: int,
    last_owner_msg_id: int, last_follower_msg_id: int,
) -> None:
    """The two writes that follow every relayed message, in one transaction.

    Both always happen together -- the relay rows are what let a later reply
    find this conversation, the anchors are what make that reply quote the
    right message -- so doing them separately meant two round trips and a
    window where one had landed and the other had not."""
    ids = list(message_ids)
    now = datetime.now(timezone.utc).isoformat()
    with pooled() as conn:
        if ids:
            conn.execute(
                "INSERT INTO anon_relay (chat_id, message_id, conversation_id, is_prompt) "
                "SELECT %s, unnest(%s::bigint[]), %s, FALSE "
                "ON CONFLICT (chat_id, message_id) DO UPDATE SET "
                "conversation_id = excluded.conversation_id, is_prompt = FALSE",
                (chat_id, ids, conversation_id),
            )
        conn.execute(
            "UPDATE anon_conversations SET last_owner_msg_id = %s, last_follower_msg_id = %s, "
            "last_activity_at = %s WHERE id = %s",
            (last_owner_msg_id, last_follower_msg_id, now, conversation_id),
        )
        conn.commit()


def mark_follower_opened(conversation_id: int) -> None:
    """Records that the guest has now sent their opening message, which is
    what spends this conversation's one exemption from the reply rule."""
    with pooled() as conn:
        conn.execute(
            "UPDATE anon_conversations SET follower_first_msg_at = %s "
            "WHERE id = %s AND follower_first_msg_at IS NULL",
            (datetime.now(timezone.utc).isoformat(), conversation_id),
        )
        conn.commit()


def count_owner_conversations(owner_user_id: int) -> int:
    """How many conversations this user is the inbox owner of, counting only
    the ones something was actually said in. A bare message from someone with
    any at all is ambiguous -- it could be meant for any of them -- which is
    exactly what the reply rule exists to resolve.

    A link tap creates a row whether or not the guest ever writes, so counting
    rows counted people who opened the link and left. That pushed an owner
    into the ambiguous branch on the strength of conversations that had never
    contained a word."""
    with pooled_read() as conn:
        cur = conn.execute(
            "SELECT count(*) FROM anon_conversations WHERE owner_user_id = %s "
            "AND (follower_first_msg_at IS NOT NULL OR last_owner_msg_id IS NOT NULL)",
            (owner_user_id,),
        )
        return cur.fetchone()[0]


def get_routing_context(user_id: int, chat_id: int) -> dict:
    """Everything handle_message needs to route one un-replied message, in a
    single round trip.

    This used to be two queries and, once the opening-message exemption had to
    start checking for other live threads, would have been three. The database
    is a long way from the containers -- a bare SELECT 1 measures about a
    second -- so three sequential round trips on the hot path of every message
    is the most expensive thing this bot does. All three answers come from
    different tables and none depends on another, so one statement does.

    Returns:
      active        -- the conversation an un-replied message would go to, or None
      owned         -- how many live conversations this user owns an inbox for
      other_threads -- whether this chat holds any conversation OTHER than
                       `active` that a message might have been meant for
    """
    with pooled_read() as conn:
        cur = conn.execute(
            """
            WITH state AS (
                SELECT owner_user_id, conversation_id
                FROM anon_follower_state WHERE follower_user_id = %(uid)s
            )
            SELECT
              s.owner_user_id, s.conversation_id,
              c.conv_number, c.last_owner_msg_id, c.last_follower_msg_id, c.follower_first_msg_at,
              (SELECT count(*) FROM anon_conversations o
                WHERE o.owner_user_id = %(uid)s
                  AND (o.follower_first_msg_at IS NOT NULL OR o.last_owner_msg_id IS NOT NULL)),
              EXISTS (SELECT 1 FROM anon_relay r
                       WHERE r.chat_id = %(chat)s
                         AND r.conversation_id IS DISTINCT FROM s.conversation_id)
            FROM (SELECT 1) AS one
            LEFT JOIN state s ON TRUE
            LEFT JOIN anon_conversations c ON c.id = s.conversation_id
            """,
            {"uid": user_id, "chat": chat_id},
        )
        row = cur.fetchone()
        owner_id, conversation_id = row[0], row[1]
        active = None
        if conversation_id is not None and row[2] is not None:
            active = {
                "id": conversation_id, "owner_user_id": owner_id, "follower_user_id": user_id,
                "conv_number": row[2], "last_owner_msg_id": row[3],
                "last_follower_msg_id": row[4], "follower_first_msg_at": row[5],
            }
        return {"active": active, "owned": row[6] or 0, "other_threads": bool(row[7])}


def get_conversation_for_relay(chat_id: int, message_id: int) -> tuple[int | None, bool]:
    """(conversation_id, was_this_a_reply_prompt) for one message in one chat.

    The second half is what lets bot.py delete a Reply prompt once the reply
    it asked for has arrived -- see record_anon_relays."""
    with pooled_read() as conn:
        cur = conn.execute(
            "SELECT conversation_id, is_prompt FROM anon_relay WHERE chat_id = %s AND message_id = %s",
            (chat_id, message_id),
        )
        row = cur.fetchone()
        return (row[0], bool(row[1])) if row else (None, False)



def clear_follower_state(follower_user_id: int) -> bool:
    """Forgets where this follower's next un-replied message was going to be
    routed, which is what /cancel does to an open ask session. The
    conversation row itself is left alone -- it is a record of messages that
    really were sent, and both sides can still reply into it by replying to
    a message from it. Returns whether there was anything to forget.

    Tapping the inbox link again starts a fresh conversation, exactly as it
    did before; see start_new_anon_conversation."""
    with pooled() as conn:
        cur = conn.execute(
            "DELETE FROM anon_follower_state WHERE follower_user_id = %s",
            (follower_user_id,),
        )
        conn.commit()
        return cur.rowcount > 0


def set_anon_blocked(owner_user_id: int, follower_user_id: int, blocked: bool) -> None:
    with pooled() as conn:
        if blocked:
            conn.execute(
                "INSERT INTO anon_blocks (owner_user_id, follower_user_id, blocked_at) VALUES (%s, %s, %s) "
                "ON CONFLICT (owner_user_id, follower_user_id) DO NOTHING",
                (owner_user_id, follower_user_id, datetime.now(timezone.utc).isoformat()),
            )
        else:
            conn.execute(
                "DELETE FROM anon_blocks WHERE owner_user_id = %s AND follower_user_id = %s",
                (owner_user_id, follower_user_id),
            )
        conn.commit()


def list_anon_blocks_with_conversations(owner_user_id: int) -> list[tuple[int | None, list[int]]]:
    """Blocked guests, each as (a conversation id to address them by, the
    conversation numbers they used).

    /blocked used to identify people by a hashed pseudonym. Conversation
    numbers do the same job with something the owner has actually seen in
    their chat -- and unlike the pseudonym they carry no identity at all,
    stable or otherwise. One query rather than one per blocked guest.

    The first element used to be the guest's Telegram user id, which bot.py
    then put in the unblock button's callback_data. Callback data is part of
    the keyboard Telegram hands to the client, so anything able to read a
    message's markup could read it -- and in a bot whose whole premise is
    that the owner never learns who is writing, that is the one field that
    must not leave the server. A conversation id says the same thing to the
    bot and nothing at all about the person.
    """
    with pooled_read() as conn:
        cur = conn.execute(
            """
            SELECT MIN(c.id),
                   COALESCE(ARRAY_AGG(c.conv_number ORDER BY c.conv_number)
                            FILTER (WHERE c.conv_number IS NOT NULL), '{}')
            FROM anon_blocks b
            LEFT JOIN anon_conversations c
                   ON c.owner_user_id = b.owner_user_id
                  AND c.follower_user_id = b.follower_user_id
            WHERE b.owner_user_id = %s
            GROUP BY b.follower_user_id, b.blocked_at
            ORDER BY b.blocked_at DESC
            """,
            (owner_user_id,),
        )
        return [(row[0], list(row[1])) for row in cur.fetchall()]


def get_anon_stats(owner_user_id: int) -> dict:
    """Counts only conversations something was actually said in -- a link tap
    that never became a message is not a conversation anybody had."""
    with pooled_read() as conn:
        cur = conn.execute(
            "SELECT COUNT(DISTINCT follower_user_id), COUNT(*) FROM anon_conversations "
            "WHERE owner_user_id = %s "
            "AND (follower_first_msg_at IS NOT NULL OR last_owner_msg_id IS NOT NULL)",
            (owner_user_id,),
        )
        distinct_followers, conversations = cur.fetchone()
        return {"distinct_followers": distinct_followers or 0, "conversations": conversations or 0}


# ---------- housekeeping ----------
# Two tables here grow without limit if nobody prunes them: activity_events
# (one row per active user per flush window) and anon_relay (one row per
# relayed message, forever). anon_relay is what lets a swipe-reply on an old
# message still resolve, so it is pruned on conversation activity rather than
# on the row's own age -- a long-running conversation keeps all of its
# anchors, a conversation nobody has touched in months keeps none.
ACTIVITY_RETENTION_DAYS = int(os.environ.get("ACTIVITY_RETENTION_DAYS", "90"))
RELAY_RETENTION_DAYS = int(os.environ.get("RELAY_RETENTION_DAYS", "180"))


def prune_old_data() -> int:
    """Returns how many rows were removed. Safe to run at any time."""
    with pooled() as conn:
        cur = conn.execute(
            "DELETE FROM activity_events WHERE occurred_at < now() - make_interval(days => %s)",
            (ACTIVITY_RETENTION_DAYS,),
        )
        removed = cur.rowcount
        cur = conn.execute(
            """
            DELETE FROM anon_relay WHERE conversation_id IN (
                SELECT id FROM anon_conversations
                WHERE last_activity_at < to_char(
                    now() - make_interval(days => %s), 'YYYY-MM-DD"T"HH24:MI:SS'
                )
            )
            """,
            (RELAY_RETENTION_DAYS,),
        )
        removed += cur.rowcount
        conn.commit()
    return removed

# ---------- admin: full database export ----------

def dump_database_csv_zip() -> bytes:
    """Exports every table in this bot's own schema to one CSV per table,
    zipped together -- this bot's data only, never a sibling's. Deliberately not pg_dump-based -- that binary
    isn't guaranteed to exist wherever this bot ends up hosted, while this
    only needs the psycopg connection already used everywhere else here."""
    import csv
    import io
    import zipfile

    buf = io.BytesIO()
    with pooled() as conn, zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        cur = conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = %s AND table_type = 'BASE TABLE' ORDER BY table_name",
            (DB_SCHEMA,),
        )
        tables = [row[0] for row in cur.fetchall()]
        for table in tables:
            cur = conn.execute(f'SELECT * FROM "{table}"')
            columns = [desc.name for desc in cur.description]
            rows = cur.fetchall()
            csv_buf = io.StringIO()
            writer = csv.writer(csv_buf)
            writer.writerow(columns)
            writer.writerows(rows)
            zf.writestr(f"{table}.csv", csv_buf.getvalue())
    return buf.getvalue()
