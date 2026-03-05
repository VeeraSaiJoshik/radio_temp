"""
Radiology Copilot — SQLite Storage
Logs every screenshot, AI response, and radiologist action for end-of-day diff review.
"""

import sqlite3
from datetime import datetime, date
from pathlib import Path

import config


class CopilotDB:
    """SQLite database for logging all reads and disagreements."""

    def __init__(self, db_path: str = None):
        self.db_path = db_path or config.DB_PATH
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = __import__('threading').Lock()
        self._create_tables()

    def _create_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS reads (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp   TEXT NOT NULL,
                session_id  TEXT NOT NULL,
                image_hash  TEXT NOT NULL,
                ai_finding  TEXT NOT NULL,
                confidence  TEXT NOT NULL,
                specialist_flags TEXT DEFAULT '',
                recommended_action TEXT DEFAULT '',
                action      TEXT NOT NULL DEFAULT 'pending',
                override_note TEXT DEFAULT '',
                created_at  TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE INDEX IF NOT EXISTS idx_reads_date
                ON reads (timestamp);

            CREATE INDEX IF NOT EXISTS idx_reads_action
                ON reads (action);
        """)
        self._conn.commit()

    # ── Write ────────────────────────────────────────────────────────────

    def log_read(
        self,
        session_id: str,
        image_hash: str,
        ai_finding: str,
        confidence: str,
        specialist_flags: list[str] = None,
        recommended_action: str = "",
    ) -> int:
        """Log an AI analysis result. Returns the row id."""
        cur = self._conn.execute(
            """INSERT INTO reads
               (timestamp, session_id, image_hash, ai_finding, confidence,
                specialist_flags, recommended_action, action)
               VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')""",
            (
                datetime.now().isoformat(),
                session_id,
                image_hash,
                ai_finding,
                confidence,
                ",".join(specialist_flags or []),
                recommended_action,
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def mark_accepted(self, read_id: int):
        """Mark a read as accepted/dismissed by the radiologist."""
        self._conn.execute(
            "UPDATE reads SET action = 'accepted' WHERE id = ?", (read_id,)
        )
        self._conn.commit()

    def mark_flagged(self, read_id: int, override_note: str = ""):
        """Mark a read as flagged/disagreed by the radiologist."""
        self._conn.execute(
            "UPDATE reads SET action = 'flagged', override_note = ? WHERE id = ?",
            (override_note, read_id),
        )
        self._conn.commit()

    def mark_flagged_by_hash(self, image_hash: str, override_note: str = ""):
        """Mark the most recent read with this image_hash as flagged."""
        self._conn.execute(
            """UPDATE reads SET action = 'flagged', override_note = ?
               WHERE id = (
                   SELECT id FROM reads WHERE image_hash = ? ORDER BY id DESC LIMIT 1
               )""",
            (override_note, image_hash),
        )
        self._conn.commit()

    # ── Read / Diff ──────────────────────────────────────────────────────

    def get_today_reads(self) -> list[dict]:
        """Get all reads from today."""
        today = date.today().isoformat()
        rows = self._conn.execute(
            "SELECT * FROM reads WHERE timestamp LIKE ? ORDER BY timestamp",
            (f"{today}%",),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_today_disagreements(self) -> list[dict]:
        """Get only flagged/disagreed reads from today."""
        today = date.today().isoformat()
        rows = self._conn.execute(
            "SELECT * FROM reads WHERE timestamp LIKE ? AND action = 'flagged' ORDER BY timestamp",
            (f"{today}%",),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_today_stats(self) -> dict:
        """Get summary stats for today."""
        today = date.today().isoformat()
        rows = self._conn.execute(
            """SELECT
                   COUNT(*) as total,
                   SUM(CASE WHEN action = 'accepted' THEN 1 ELSE 0 END) as accepted,
                   SUM(CASE WHEN action = 'flagged' THEN 1 ELSE 0 END) as flagged,
                   SUM(CASE WHEN action = 'pending' THEN 1 ELSE 0 END) as pending
               FROM reads WHERE timestamp LIKE ?""",
            (f"{today}%",),
        ).fetchone()
        return dict(rows)

    def close(self):
        self._conn.close()


# ── CLI Diff Printer ─────────────────────────────────────────────────────────

def print_diff(db_path: str = None):
    """Print today's disagreement log in a clean readable format."""
    db = CopilotDB(db_path)
    stats = db.get_today_stats()
    disagreements = db.get_today_disagreements()
    all_reads = db.get_today_reads()
    db.close()

    today = date.today().isoformat()

    print(f"\n{'='*60}")
    print(f"  RADIOLOGY COPILOT — DAILY DIFF REPORT")
    print(f"  {today}")
    print(f"{'='*60}\n")

    print(f"  Total reads:    {stats['total']}")
    print(f"  Accepted:       {stats['accepted']}")
    print(f"  Flagged:        {stats['flagged']}")
    print(f"  Pending:        {stats['pending']}")

    if not disagreements:
        print(f"\n  No disagreements today.\n")
    else:
        print(f"\n{'─'*60}")
        print(f"  DISAGREEMENTS ({len(disagreements)})")
        print(f"{'─'*60}\n")

        for i, d in enumerate(disagreements, 1):
            ts = d['timestamp'].split('T')[1].split('.')[0] if 'T' in d['timestamp'] else d['timestamp']
            print(f"  [{i}]  {ts}  |  Confidence: {d['confidence'].upper()}")
            print(f"       AI said:      {d['ai_finding']}")
            if d['override_note']:
                print(f"       Doctor said:  {d['override_note']}")
            else:
                print(f"       Doctor said:  (no note provided)")
            print(f"       Image hash:   {d['image_hash']}")
            print()

    # Full log
    if all_reads:
        print(f"{'─'*60}")
        print(f"  FULL LOG ({len(all_reads)} reads)")
        print(f"{'─'*60}\n")

        for r in all_reads:
            ts = r['timestamp'].split('T')[1].split('.')[0] if 'T' in r['timestamp'] else r['timestamp']
            action_icon = {"accepted": "✓", "flagged": "✗", "pending": "·"}.get(r['action'], "?")
            print(f"  {action_icon}  {ts}  [{r['confidence'].upper():>6}]  {r['ai_finding'][:60]}")

    print(f"\n{'='*60}\n")
