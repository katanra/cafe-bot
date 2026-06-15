import sqlite3
import datetime

class Database:
    def __init__(self):
        self.conn = sqlite3.connect('cafe_bot.db')
        self.conn.row_factory = sqlite3.Row
        self.create_tables()

    def create_tables(self):
        c = self.conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            gold        INTEGER DEFAULT 0,
            xp          INTEGER DEFAULT 0,
            voice_time  INTEGER DEFAULT 0
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS duels (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            challenger_id INTEGER,
            opponent_id   INTEGER,
            channel_id    INTEGER,
            winner_id     INTEGER,
            status        TEXT DEFAULT 'pending',
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS daily_claims (
            user_id    INTEGER PRIMARY KEY,
            last_claim TEXT
        )''')
        # Add voice_time column to existing databases that don't have it yet
        try:
            c.execute('ALTER TABLE users ADD COLUMN voice_time INTEGER DEFAULT 0')
        except Exception:
            pass
        self.conn.commit()

    # ── Users ──────────────────────────────────────────────────────────────────

    def get_user(self, user_id):
        c = self.conn.cursor()
        c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        row = c.fetchone()
        if not row:
            c.execute('INSERT INTO users (user_id) VALUES (?)', (user_id,))
            self.conn.commit()
            c.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
            row = c.fetchone()
        return dict(row)

    def add_gold(self, user_id, amount):
        self.get_user(user_id)
        c = self.conn.cursor()
        c.execute('UPDATE users SET gold = gold + ? WHERE user_id = ?', (amount, user_id))
        self.conn.commit()

    def remove_gold(self, user_id, amount):
        self.get_user(user_id)
        c = self.conn.cursor()
        c.execute('UPDATE users SET gold = MAX(0, gold - ?) WHERE user_id = ?', (amount, user_id))
        self.conn.commit()

    def add_xp(self, user_id, amount):
        self.get_user(user_id)
        c = self.conn.cursor()
        c.execute('UPDATE users SET xp = xp + ? WHERE user_id = ?', (amount, user_id))
        self.conn.commit()

    def add_voice_time(self, user_id, seconds):
        self.get_user(user_id)
        c = self.conn.cursor()
        c.execute('UPDATE users SET voice_time = voice_time + ? WHERE user_id = ?', (seconds, user_id))
        self.conn.commit()

    # ── Leaderboards ──────────────────────────────────────────────────────────

    def get_leaderboard(self, column, limit=10):
        c = self.conn.cursor()
        c.execute(f'SELECT * FROM users ORDER BY {column} DESC LIMIT ?', (limit,))
        return [dict(r) for r in c.fetchall()]

    def get_voice_leaderboard(self, limit=10):
        c = self.conn.cursor()
        c.execute('SELECT * FROM users ORDER BY voice_time DESC LIMIT ?', (limit,))
        return [dict(r) for r in c.fetchall()]

    def get_daily_wins(self, user_id):
        """Count how many duel wins this user has recorded today."""
        c = self.conn.cursor()
        today = datetime.date.today().isoformat()
        c.execute('''
            SELECT COUNT(*) as cnt FROM duels
            WHERE winner_id = ? AND status = 'completed'
            AND DATE(created_at) = ?
        ''', (user_id, today))
        row = c.fetchone()
        return row['cnt'] if row else 0

    def get_duel_leaderboard(self, limit=10):
        c = self.conn.cursor()
        c.execute('''
            SELECT winner_id, COUNT(*) as wins
            FROM duels
            WHERE status = 'completed'
            GROUP BY winner_id
            ORDER BY wins DESC
            LIMIT ?
        ''', (limit,))
        return [dict(r) for r in c.fetchall()]

    # ── Duels ─────────────────────────────────────────────────────────────────

    def create_duel(self, challenger_id, opponent_id, channel_id):
        c = self.conn.cursor()
        # Clear any existing pending duels for these users
        c.execute('''DELETE FROM duels WHERE status = 'pending'
            AND (challenger_id IN (?,?) OR opponent_id IN (?,?))''',
            (challenger_id, opponent_id, challenger_id, opponent_id))
        c.execute(
            'INSERT INTO duels (challenger_id, opponent_id, channel_id) VALUES (?, ?, ?)',
            (challenger_id, opponent_id, channel_id)
        )
        self.conn.commit()
        return c.lastrowid

    def accept_duel(self, duel_id):
        c = self.conn.cursor()
        c.execute("UPDATE duels SET status = 'active' WHERE id = ?", (duel_id,))
        self.conn.commit()

    def complete_duel(self, duel_id, winner_id):
        c = self.conn.cursor()
        c.execute("UPDATE duels SET status = 'completed', winner_id = ? WHERE id = ?",
                  (winner_id, duel_id))
        self.conn.commit()

    def cancel_duel_by_id(self, duel_id):
        c = self.conn.cursor()
        c.execute("UPDATE duels SET status = 'cancelled' WHERE id = ?", (duel_id,))
        self.conn.commit()

    def get_pending_duel(self, user_id):
        c = self.conn.cursor()
        c.execute('''SELECT * FROM duels WHERE status = 'pending'
            AND (challenger_id = ? OR opponent_id = ?)''', (user_id, user_id))
        row = c.fetchone()
        return dict(row) if row else None

    def get_active_duel(self, user_id):
        c = self.conn.cursor()
        c.execute('''SELECT * FROM duels WHERE status = 'active'
            AND (challenger_id = ? OR opponent_id = ?)''', (user_id, user_id))
        row = c.fetchone()
        return dict(row) if row else None

    # ── Daily Claims ──────────────────────────────────────────────────────────

    def claim_daily(self, user_id):
        c = self.conn.cursor()
        today = datetime.date.today().isoformat()
        c.execute('SELECT last_claim FROM daily_claims WHERE user_id = ?', (user_id,))
        row = c.fetchone()
        if row and row['last_claim'] == today:
            return 'already_claimed'
        if row:
            c.execute('UPDATE daily_claims SET last_claim = ? WHERE user_id = ?', (today, user_id))
        else:
            c.execute('INSERT INTO daily_claims (user_id, last_claim) VALUES (?, ?)', (user_id, today))
        self.conn.commit()
        return 'claimed'
