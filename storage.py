import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "library.db"


class LibraryStorage:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS playlists (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                is_system INTEGER DEFAULT 0
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS playlist_tracks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                playlist_id INTEGER NOT NULL,
                video_id TEXT NOT NULL,
                title TEXT NOT NULL,
                artist TEXT NOT NULL,
                duration TEXT NOT NULL,
                thumbnail TEXT DEFAULT '',
                UNIQUE(playlist_id, video_id),
                FOREIGN KEY (playlist_id) REFERENCES playlists(id) ON DELETE CASCADE
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS history (
                video_id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                artist TEXT NOT NULL,
                duration TEXT NOT NULL,
                thumbnail TEXT DEFAULT '',
                played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        # Safe migration if upgrading from older library.db
        try:
            cur.execute("ALTER TABLE playlist_tracks ADD COLUMN thumbnail TEXT DEFAULT ''")
        except sqlite3.OperationalError:
            pass

        cur.execute(
            "INSERT OR IGNORE INTO playlists (name, is_system) VALUES ('Liked Songs', 1)"
        )
        self.conn.commit()

    def get_liked_playlist_id(self) -> int:
        row = self.conn.execute(
            "SELECT id FROM playlists WHERE is_system = 1 LIMIT 1"
        ).fetchone()
        return row["id"]

    def is_liked(self, video_id: str) -> bool:
        liked_id = self.get_liked_playlist_id()
        row = self.conn.execute(
            "SELECT 1 FROM playlist_tracks WHERE playlist_id = ? AND video_id = ?",
            (liked_id, video_id),
        ).fetchone()
        return row is not None

    def toggle_like(self, song: dict) -> bool:
        liked_id = self.get_liked_playlist_id()
        if self.is_liked(song["video_id"]):
            self.remove_track(liked_id, song["video_id"])
            return False
        self.add_track(liked_id, song)
        return True

    def record_play(self, song: dict):
        self.conn.execute(
            """
            INSERT INTO history (video_id, title, artist, duration, thumbnail, played_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(video_id) DO UPDATE SET played_at = CURRENT_TIMESTAMP
            """,
            (
                song["video_id"],
                song["title"],
                song["artist"],
                song.get("duration", "0:00"),
                song.get("thumbnail") or "",
            ),
        )
        self.conn.commit()

    def get_recent_tracks(self, limit: int = 20) -> list[dict]:
        cur = self.conn.execute(
            "SELECT video_id, title, artist, duration, thumbnail FROM history ORDER BY played_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in cur.fetchall()]

    def get_playlists(self) -> list[dict]:
        cur = self.conn.execute(
            "SELECT id, name, is_system FROM playlists ORDER BY is_system DESC, id ASC"
        )
        return [dict(row) for row in cur.fetchall()]

    def create_playlist(self, name: str) -> int | None:
        name = name.strip()
        if not name:
            return None
        try:
            cur = self.conn.execute(
                "INSERT INTO playlists (name, is_system) VALUES (?, 0)", (name,)
            )
            self.conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None

    def delete_playlist(self, playlist_id: int):
        self.conn.execute("DELETE FROM playlist_tracks WHERE playlist_id = ?", (playlist_id,))
        self.conn.execute("DELETE FROM playlists WHERE id = ? AND is_system = 0", (playlist_id,))
        self.conn.commit()

    def get_tracks(self, playlist_id: int) -> list[dict]:
        cur = self.conn.execute(
            """
            SELECT video_id, title, artist, duration, thumbnail
            FROM playlist_tracks
            WHERE playlist_id = ?
            ORDER BY id ASC
            """,
            (playlist_id,),
        )
        return [dict(row) for row in cur.fetchall()]

    def add_track(self, playlist_id: int, song: dict):
        self.conn.execute(
            """
            INSERT OR IGNORE INTO playlist_tracks (playlist_id, video_id, title, artist, duration, thumbnail)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                playlist_id,
                song["video_id"],
                song["title"],
                song["artist"],
                song.get("duration", "0:00"),
                song.get("thumbnail") or "",
            ),
        )
        self.conn.commit()

    def remove_track(self, playlist_id: int, video_id: str):
        self.conn.execute(
            "DELETE FROM playlist_tracks WHERE playlist_id = ? AND video_id = ?",
            (playlist_id, video_id),
        )
        self.conn.commit()