
import os
import math
import logging
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL")
logger = logging.getLogger(__name__)


def db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is missing")

    return psycopg2.connect(
        DATABASE_URL,
        sslmode="require",
        cursor_factory=RealDictCursor
    )


def init_db():
    conn = db()
    cur = conn.cursor()

    try:
        # Users
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                nickname TEXT
            )
        """)

        user_columns = {
            "age": "INTEGER",
            "gender": "TEXT",
            "province": "TEXT",
            "city": "TEXT",
            "bio": "TEXT",
            "lat": "DOUBLE PRECISION",
            "lon": "DOUBLE PRECISION",
            "stars": "INTEGER DEFAULT 6",
            "is_vip": "BOOLEAN DEFAULT FALSE",
            "profile_visible": "BOOLEAN DEFAULT TRUE",
            "location_visible": "BOOLEAN DEFAULT TRUE",
            "photos": "TEXT DEFAULT ''",
            "req_gender": "TEXT DEFAULT 'any'",
            "req_province": "BOOLEAN DEFAULT FALSE",
            "req_city": "BOOLEAN DEFAULT FALSE",
            "req_min_age": "INTEGER DEFAULT 18",
            "req_max_age": "INTEGER DEFAULT 99",
            "alarm_seen": "BOOLEAN DEFAULT TRUE",
            "silent_until": "TIMESTAMP",
            "chat_requests_allowed": "BOOLEAN DEFAULT TRUE",
            "direct_messages_allowed": "BOOLEAN DEFAULT TRUE",
            "visit_alerts_enabled": "BOOLEAN DEFAULT TRUE"
        }

        for column, definition in user_columns.items():
            cur.execute(
                f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {column} {definition}"
            )

        # Likes
        cur.execute("""
            CREATE TABLE IF NOT EXISTS likes (
                user_id BIGINT,
                target_id BIGINT,
                PRIMARY KEY (user_id, target_id)
            )
        """)

        # Passed profiles
        cur.execute("""
            CREATE TABLE IF NOT EXISTS passes (
                user_id BIGINT,
                target_id BIGINT,
                PRIMARY KEY (user_id, target_id)
            )
        """)

        # Blocks
        cur.execute("""
            CREATE TABLE IF NOT EXISTS blocks (
                user_id BIGINT,
                blocked_id BIGINT,
                PRIMARY KEY (user_id, blocked_id)
            )
        """)

        # Reports
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id SERIAL PRIMARY KEY,
                reporter_id BIGINT,
                target_id BIGINT,
                reason TEXT
            )
        """)

        # Chats
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chats (
                user1 BIGINT,
                user2 BIGINT,
                active BOOLEAN DEFAULT TRUE,
                PRIMARY KEY (user1, user2)
            )
        """)

        cur.execute("""
            ALTER TABLE chats
            ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        """)

        # Contacts
        cur.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                user_id BIGINT,
                contact_id BIGINT,
                PRIMARY KEY (user_id, contact_id)
            )
        """)

        # Direct chat requests
        cur.execute("""
            CREATE TABLE IF NOT EXISTS direct_requests (
                id SERIAL PRIMARY KEY,
                sender_id BIGINT,
                receiver_id BIGINT,
                message TEXT,
                status TEXT DEFAULT 'pending'
            )
        """)

        cur.execute("""
            ALTER TABLE direct_requests
            ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        """)

        cur.execute("""
            ALTER TABLE direct_requests
            ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP
        """)

        # Indexes
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_users_location
            ON users(province, city)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_requests_receiver_status
            ON direct_requests(receiver_id, status)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_requests_sender_created
            ON direct_requests(sender_id, created_at)
        """)

        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_chats_active
            ON chats(user1, user2, active)
        """)

        conn.commit()
        logger.info("Database initialized successfully")

    except Exception:
        conn.rollback()
        logger.exception("Database initialization failed")
        raise

    finally:
        cur.close()
        conn.close()


def get_user(uid):
    conn = db()
    cur = conn.cursor()

    try:
        cur.execute(
            "SELECT * FROM users WHERE user_id = %s",
            (uid,)
        )
        return cur.fetchone()

    finally:
        cur.close()
        conn.close()


def is_reg(uid):
    user = get_user(uid)
    return bool(user and user.get("nickname"))


def dist(a, b, c, d):
    R = 6371

    dl = math.radians(c - a)
    dn = math.radians(d - b)

    x = (
        math.sin(dl / 2) ** 2
        + math.cos(math.radians(a))
        * math.cos(math.radians(c))
        * math.sin(dn / 2) ** 2
    )

    x = max(0, min(1, x))

    return 2 * R * math.atan2(
        math.sqrt(x),
        math.sqrt(1 - x)
    )


def is_silent(user):
    if not user:
        return False

    silent_until = user.get("silent_until")

    if not silent_until:
        return False

    from datetime import datetime

    return silent_until > datetime.now()


def expire_requests():
    conn = db()
    cur = conn.cursor()

    try:
        cur.execute("""
            UPDATE direct_requests
            SET status = 'expired'
            WHERE status = 'pending'
              AND expires_at IS NOT NULL
              AND expires_at <= CURRENT_TIMESTAMP
        """)

        expired_count = cur.rowcount
        conn.commit()

        return expired_count

    except Exception:
        conn.rollback()
        logger.exception("Request expiration failed")
        raise

    finally:
        cur.close()
        conn.close()
def create_direct_request(sender_id, receiver_id, message):
    conn = db()
    cur = conn.cursor()

    try:
        # جلوگیری از ثبت هم‌زمان درخواست‌های بیش از حد
        cur.execute(
            "SELECT pg_advisory_xact_lock(%s)",
            (sender_id,)
        )

        cur.execute("""
            SELECT COUNT(*) AS total
            FROM direct_requests
            WHERE sender_id = %s
              AND created_at > CURRENT_TIMESTAMP - INTERVAL '1 hour'
        """, (sender_id,))

        total = cur.fetchone()["total"]

        if total >= 20:
            conn.rollback()
            return {"ok": False, "reason": "hourly_limit"}

        cur.execute("""
            INSERT INTO direct_requests (
                sender_id,
                receiver_id,
                message,
                status,
                created_at,
                expires_at
            )
            VALUES (
                %s,
                %s,
                %s,
                'pending',
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP + INTERVAL '5 minutes'
            )
            RETURNING id
        """, (sender_id, receiver_id, message))

        request_id = cur.fetchone()["id"]
        conn.commit()

        return {"ok": True, "request_id": request_id}

    except Exception:
        conn.rollback()
        logger.exception("Creating direct request failed")
        raise

    finally:
        cur.close()
        conn.close()                                     
