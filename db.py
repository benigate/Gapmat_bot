import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor

DATABASE_URL = os.getenv("DATABASE_URL")
logger = logging.getLogger(__name__)

def db():
    return psycopg2.connect(DATABASE_URL, sslmode="require", cursor_factory=RealDictCursor)

def init_db():
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("CREATE TABLE IF NOT EXISTS users (user_id BIGINT PRIMARY KEY, nickname TEXT)")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS age INTEGER")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS gender TEXT")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS province TEXT")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS city TEXT")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS bio TEXT")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS lat DOUBLE PRECISION")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS lon DOUBLE PRECISION")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS stars INTEGER DEFAULT 6")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS is_vip BOOLEAN DEFAULT FALSE")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS profile_visible BOOLEAN DEFAULT TRUE")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS photos TEXT DEFAULT ''")
        
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS req_gender TEXT DEFAULT 'any'")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS req_province BOOLEAN DEFAULT FALSE")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS req_city BOOLEAN DEFAULT FALSE")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS req_min_age INTEGER DEFAULT 18")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS req_max_age INTEGER DEFAULT 99")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS alarm_seen BOOLEAN DEFAULT TRUE")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS silent_until TIMESTAMP")
        
        cur.execute("CREATE TABLE IF NOT EXISTS likes (user_id BIGINT, target_id BIGINT, PRIMARY KEY (user_id, target_id))")
        cur.execute("CREATE TABLE IF NOT EXISTS passes (user_id BIGINT, target_id BIGINT, PRIMARY KEY (user_id, target_id))")
        cur.execute("CREATE TABLE IF NOT EXISTS blocks (user_id BIGINT, blocked_id BIGINT, PRIMARY KEY (user_id, blocked_id))")
        cur.execute("CREATE TABLE IF NOT EXISTS reports (id SERIAL PRIMARY KEY, reporter_id BIGINT, target_id BIGINT, reason TEXT)")
        cur.execute("CREATE TABLE IF NOT EXISTS chats (user1 BIGINT, user2 BIGINT, active BOOLEAN DEFAULT TRUE, PRIMARY KEY (user1, user2))")
        cur.execute("CREATE TABLE IF NOT EXISTS contacts (user_id BIGINT, contact_id BIGINT, PRIMARY KEY (user_id, contact_id))")
        cur.execute("CREATE TABLE IF NOT EXISTS direct_requests (id SERIAL PRIMARY KEY, sender_id BIGINT, receiver_id BIGINT, message TEXT, status TEXT DEFAULT 'pending')")
        cur.execute("UPDATE users SET stars = 6 WHERE stars = 250")
        conn.commit()
    except: conn.rollback()
    finally: cur.close(); conn.close()

def get_user(uid):
    conn = db(); cur = conn.cursor()
    try:
        cur.execute("SELECT * FROM users WHERE user_id=%s", (uid,))
        return cur.fetchone()
    finally: cur.close(); conn.close()

def is_reg(uid):
    u = get_user(uid)
    return bool(u and u["nickname"])

def dist(a,b,c,d):
    import math
    R=6371; dl=math.radians(c-a); dn=math.radians(d-b)
    x=math.sin(dl/2)**2+math.cos(math.radians(a))*math.cos(math.radians(c))*math.sin(dn/2)**2
    return R*2*math.atan2(math.sqrt(x),math.sqrt(1-x))