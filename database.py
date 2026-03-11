import sqlite3, hashlib, datetime, random

DB_FILE = "chat_app.db"

def get_db():
    return sqlite3.connect(DB_FILE)

def init_db():
    with get_db() as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password_hash TEXT, last_login TEXT, location TEXT)')
        conn.execute('CREATE TABLE IF NOT EXISTS chat_groups (group_name TEXT PRIMARY KEY)')
        conn.execute('''CREATE TABLE IF NOT EXISTS group_members (
                        group_name TEXT,
                        username TEXT,
                        PRIMARY KEY (group_name, username))''')

# Simple mock location data
LOCATIONS = ["South Africa", "Germany", "USA", "India", "UK"]

def verify_or_create_user(username, password):
    h = hashlib.sha256(password.encode()).hexdigest()
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute('SELECT password_hash FROM users WHERE username=?', (username,))
        row = cur.fetchone()
        if row:
            valid = row[0] == h
            if valid:
                conn.execute('UPDATE users SET last_login=?, location=? WHERE username=?',
                             (datetime.datetime.now().isoformat(), random.choice(LOCATIONS), username))
            return valid
        conn.execute('INSERT INTO users VALUES (?, ?, ?, ?)',
                     (username, h, datetime.datetime.now().isoformat(), random.choice(LOCATIONS)))
        return True

def add_to_group(username, group):
    with get_db() as conn:
        conn.execute('INSERT OR IGNORE INTO chat_groups VALUES (?)', (group,))
        conn.execute('INSERT OR IGNORE INTO group_members VALUES (?, ?)', (group, username))

def remove_from_group(username, group):
    with get_db() as conn:
        conn.execute('DELETE FROM group_members WHERE group_name=? AND username=?', (group, username))

def get_group_members(group):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute('SELECT username FROM group_members WHERE group_name=?', (group,))
        return [r[0] for r in cur.fetchall()]

def get_user_info(username):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute('SELECT username, last_login, location FROM users WHERE username=?', (username,))
        user = cur.fetchone()
        cur.execute('SELECT group_name FROM group_members WHERE username=?', (username,))
        groups = [g[0] for g in cur.fetchall()]
        return user, groups