import sqlite3
import os
from datetime import datetime, timedelta
from typing import List, Tuple, Optional


class Database:
    def __init__(self, db_path: str = "nyuklabot.db"):
        self.db_path = db_path
        self._init_db()

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id     INTEGER PRIMARY KEY,
                    username    TEXT,
                    full_name   TEXT,
                    joined_at   TEXT DEFAULT (datetime('now'))
                );

                CREATE TABLE IF NOT EXISTS admins (
                    user_id     INTEGER PRIMARY KEY
                );

                CREATE TABLE IF NOT EXISTS required_channels (
                    channel_id  TEXT PRIMARY KEY
                );
            """)
            conn.commit()

    # ─── Users ────────────────────────────────────────────────
    def add_user(self, user_id: int, username: Optional[str], full_name: Optional[str]):
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)",
                (user_id, username, full_name)
            )
            conn.commit()

    def get_all_users(self, limit: int = None) -> List[Tuple]:
        with self._get_conn() as conn:
            if limit:
                rows = conn.execute(
                    "SELECT user_id, username, full_name FROM users ORDER BY joined_at DESC LIMIT ?",
                    (limit,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT user_id, username, full_name FROM users"
                ).fetchall()
        return [(r['user_id'], r['username'], r['full_name']) for r in rows]

    def get_stats(self) -> dict:
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        week_ago = (now - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
        month_ago = (now - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")

        with self._get_conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            today_count = conn.execute(
                "SELECT COUNT(*) FROM users WHERE date(joined_at) = ?", (today,)
            ).fetchone()[0]
            week_count = conn.execute(
                "SELECT COUNT(*) FROM users WHERE joined_at >= ?", (week_ago,)
            ).fetchone()[0]
            month_count = conn.execute(
                "SELECT COUNT(*) FROM users WHERE joined_at >= ?", (month_ago,)
            ).fetchone()[0]

        return {
            "total": total,
            "today": today_count,
            "week": week_count,
            "month": month_count
        }

    # ─── Admins ───────────────────────────────────────────────
    def get_admins(self) -> List[int]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT user_id FROM admins").fetchall()
        return [r['user_id'] for r in rows]

    def add_admin(self, user_id: int):
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO admins (user_id) VALUES (?)",
                (user_id,)
            )
            conn.commit()

    def remove_admin(self, user_id: int):
        with self._get_conn() as conn:
            conn.execute("DELETE FROM admins WHERE user_id = ?", (user_id,))
            conn.commit()

    # ─── Channels ─────────────────────────────────────────────
    def get_required_channels(self) -> List[str]:
        with self._get_conn() as conn:
            rows = conn.execute("SELECT channel_id FROM required_channels").fetchall()
        return [r['channel_id'] for r in rows]

    def add_required_channel(self, channel_id: str):
        with self._get_conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO required_channels (channel_id) VALUES (?)",
                (channel_id,)
            )
            conn.commit()

    def remove_required_channel(self, channel_id: str):
        with self._get_conn() as conn:
            conn.execute(
                "DELETE FROM required_channels WHERE channel_id = ?",
                (channel_id,)
            )
            conn.commit()
