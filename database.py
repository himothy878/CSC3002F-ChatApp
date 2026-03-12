import sqlite3
import hashlib
import datetime
import random

DB_FILE = "chat_app.db"


def get_db():
    return sqlite3.connect(DB_FILE)


def init_db():
    with get_db() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS users ("  # username primary key
            "username TEXT PRIMARY KEY, "
            "password_hash TEXT, "
            "last_login TEXT, "
            "location TEXT)"
        )

        conn.execute("CREATE TABLE IF NOT EXISTS chat_groups (group_name TEXT PRIMARY KEY)")

        conn.execute(
            """CREATE TABLE IF NOT EXISTS group_members (
            group_name TEXT,
            username TEXT,
            PRIMARY KEY (group_name, username)
        )"""
        )

        # Message history (private + group)
        conn.execute(
            """CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT,
            sender TEXT,
            target TEXT,
            channel TEXT,
            body TEXT
        )"""
        )


# Simple mock location data
LOCATIONS = ["South Africa", "Germany", "USA", "India", "UK"]


def verify_or_create_user(username, password):
    h = hashlib.sha256(password.encode()).hexdigest()
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT password_hash FROM users WHERE username=?", (username,))
        row = cur.fetchone()
        if row:
            valid = row[0] == h
            if valid:
                conn.execute(
                    "UPDATE users SET last_login=?, location=? WHERE username=?",
                    (datetime.datetime.now().isoformat(), random.choice(LOCATIONS), username),
                )
            return valid

        # create new user
        conn.execute(
            "INSERT INTO users VALUES (?, ?, ?, ?)",
            (username, h, datetime.datetime.now().isoformat(), random.choice(LOCATIONS)),
        )
        return True


def add_to_group(username, group):
    with get_db() as conn:
        conn.execute("INSERT OR IGNORE INTO chat_groups VALUES (?)", (group,))
        conn.execute("INSERT OR IGNORE INTO group_members VALUES (?, ?)", (group, username))


def remove_from_group(username, group):
    with get_db() as conn:
        conn.execute(
            "DELETE FROM group_members WHERE group_name=? AND username=?",
            (group, username),
        )


def get_group_members(group):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT username FROM group_members WHERE group_name=?", (group,))
        return [r[0] for r in cur.fetchall()]


def get_user_info(username):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT username, last_login, location FROM users WHERE username=?",
            (username,),
        )
        user = cur.fetchone()

        cur.execute("SELECT group_name FROM group_members WHERE username=?", (username,))
        groups = [g[0] for g in cur.fetchall()]
        return user, groups


def get_group_memberships(username):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT group_name FROM group_members WHERE username=? ORDER BY group_name",
            (username,),
        )
        return [g[0] for g in cur.fetchall()]


# --------- message history helpers ---------

def save_message(sender: str, target: str, channel: str, body: str):
    """Store a chat message (PRIVATE or GROUP)."""
    ts = datetime.datetime.now().isoformat()
    with get_db() as conn:
        conn.execute(
            "INSERT INTO messages (ts, sender, target, channel, body) VALUES (?, ?, ?, ?, ?)",
            (ts, sender, target, channel, body),
        )


def get_private_history(user_a: str, user_b: str, limit: int = 200):
    """Return ordered private history between two users (oldest first)."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT ts, sender, target, channel, body
               FROM messages
               WHERE channel = "PRIVATE" AND
                     ((sender = ? AND target = ?) OR (sender = ? AND target = ?))
               ORDER BY ts ASC
               LIMIT ?""",
            (user_a, user_b, user_b, user_a, limit),
        )
        return cur.fetchall()


def get_group_history(group: str, limit: int = 200):
    """Return ordered group history for a group (oldest first)."""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT ts, sender, target, channel, body
               FROM messages
               WHERE channel = "GROUP" AND target = ?
               ORDER BY ts ASC
               LIMIT ?""",
            (group, limit),
        )
        return cur.fetchall()