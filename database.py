import sqlite3
import datetime

class Database:
    def __init__(self):
        self.conn = sqlite3.connect('cafe_bot.db', check_same_thread=False)
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
            last_claim TEXT,
            streak     INTEGER DEFAULT 0
        )''')
        # Add streak column to existing databases
        try:
            c.execute('ALTER TABLE daily_claims ADD COLUMN streak INTEGER DEFAULT 0')
        except Exception:
            pass
        c.execute('''CREATE TABLE IF NOT EXISTS vc_milestones (
            user_id   INTEGER,
            milestone INTEGER,
            PRIMARY KEY (user_id, milestone)
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

    def check_new_milestones(self, user_id, old_seconds, new_seconds):
        """Returns list of milestone hours newly crossed (e.g. [10, 50])."""
        milestones = [10, 50, 100, 250, 500]
        crossed = []
        for m in milestones:
            threshold = m * 3600
            if old_seconds < threshold <= new_seconds:
                c = self.conn.cursor()
                try:
                    c.execute('INSERT INTO vc_milestones (user_id, milestone) VALUES (?, ?)', (user_id, m))
                    self.conn.commit()
                    crossed.append(m)
                except sqlite3.IntegrityError:
                    pass  # Already recorded
        return crossed

    def reset_voice_time(self):
        """Reset all users' voice_time to 0."""
        c = self.conn.cursor()
        c.execute('UPDATE users SET voice_time = 0')
        self.conn.commit()

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

    def get_user_wins(self, user_id):
        """Total completed duel wins for a specific user."""
        c = self.conn.cursor()
        c.execute('''
            SELECT COUNT(*) as wins FROM duels
            WHERE winner_id = ? AND status = 'completed'
        ''', (user_id,))
        row = c.fetchone()
        return row['wins'] if row else 0

    def get_duel_rank(self, user_id):
        """1-based rank of a user on the duel wins leaderboard. Returns 0 if unranked (0 wins)."""
        wins = self.get_user_wins(user_id)
        if wins == 0:
            return 0
        c = self.conn.cursor()
        c.execute('''
            SELECT COUNT(DISTINCT winner_id) as cnt FROM duels
            WHERE status = 'completed'
            GROUP BY winner_id
            HAVING COUNT(*) > ?
        ''', (wins,))
        rows = c.fetchall()
        return len(rows) + 1

    def get_xp_rank(self, user_id):
        """1-based rank of a user on the XP leaderboard."""
        c = self.conn.cursor()
        user = self.get_user(user_id)
        c.execute('SELECT COUNT(*) as cnt FROM users WHERE xp > ?', (user['xp'],))
        row = c.fetchone()
        return (row['cnt'] if row else 0) + 1

    def get_gold_rank(self, user_id):
        """1-based rank of a user on the gold leaderboard. Returns 0 if they have no gold."""
        user = self.get_user(user_id)
        if user['gold'] == 0:
            return 0
        c = self.conn.cursor()
        c.execute('SELECT COUNT(*) as cnt FROM users WHERE gold > ?', (user['gold'],))
        row = c.fetchone()
        return (row['cnt'] if row else 0) + 1

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
        """Returns ('already_claimed', streak) or ('claimed', new_streak)."""
        c = self.conn.cursor()
        today     = datetime.date.today()
        today_str = today.isoformat()
        yesterday = (today - datetime.timedelta(days=1)).isoformat()

        c.execute('SELECT last_claim, streak FROM daily_claims WHERE user_id = ?', (user_id,))
        row = c.fetchone()

        if row and row['last_claim'] == today_str:
            return ('already_claimed', row['streak'])

        if row:
            # Continue streak if claimed yesterday, otherwise reset
            new_streak = (row['streak'] + 1) if row['last_claim'] == yesterday else 1
            c.execute(
                'UPDATE daily_claims SET last_claim = ?, streak = ? WHERE user_id = ?',
                (today_str, new_streak, user_id)
            )
        else:
            new_streak = 1
            c.execute(
                'INSERT INTO daily_claims (user_id, last_claim, streak) VALUES (?, ?, ?)',
                (user_id, today_str, new_streak)
            )

        self.conn.commit()
        return ('claimed', new_streak)

    def spend_gold(self, user_id, amount) -> bool:
        """Deduct gold if user has enough. Returns True on success."""
        user = self.get_user(user_id)
        if user['gold'] < amount:
            return False
        c = self.conn.cursor()
        c.execute('UPDATE users SET gold = gold - ? WHERE user_id = ?', (amount, user_id))
        self.conn.commit()
        return True

    def get_streak(self, user_id):
        c = self.conn.cursor()
        today     = datetime.date.today().isoformat()
        yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
        c.execute('SELECT last_claim, streak FROM daily_claims WHERE user_id = ?', (user_id,))
        row = c.fetchone()
        if not row:
            return 0
        # Streak is only alive if claimed today or yesterday
        if row['last_claim'] in (today, yesterday):
            return row['streak']
        return 0
