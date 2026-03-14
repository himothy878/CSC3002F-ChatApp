import sqlite3, hashlib

DB_FILE = "chat_app.db"
users = {"A": "1234", "B": "abcd", "C": "pass"}

conn = sqlite3.connect(DB_FILE)
cur = conn.cursor()
cur.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password_hash TEXT, last_login TEXT, location TEXT)')
for u, p in users.items():
    h = hashlib.sha256(p.encode()).hexdigest()
    cur.execute('INSERT OR IGNORE INTO users (username, password_hash, last_login, location) VALUES (?, ?, NULL, "South Africa")', (u, h))
conn.commit()
conn.close()
print("✅ Demo users added:")
for n, pw in users.items():
    print(f"  {n} | password: {pw}")