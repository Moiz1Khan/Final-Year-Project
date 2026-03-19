"""Activity logging to SQLite - structured logs for Proactive Assistance."""

import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Optional, Set

# Path to context_monitoring.db in data/
_ROOT = Path(__file__).resolve().parents[2]
_DATA_DIR = _ROOT / "data"
_DB_PATH = _DATA_DIR / "context_monitoring.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS activity_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    active_app TEXT,
    window_title TEXT,
    status TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_activity_timestamp ON activity_logs(timestamp);
CREATE INDEX IF NOT EXISTS idx_activity_created ON activity_logs(created_at);
"""


def get_db_path() -> Path:
    """Get path to context monitoring SQLite DB."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    return _DB_PATH


def _sanitize_window_title(title: str, max_length: int) -> str:
    """Truncate window title for privacy."""
    if not title or max_length <= 0:
        return title or ""
    if len(title) <= max_length:
        return title
    return title[: max_length - 3] + "..."


class ActivityLogger:
    """
    Logs user activity (app, window, status) to SQLite.
    Supports sensitive data handling: truncate titles, exclude apps.
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        truncate_window_title: int = 0,
        exclude_apps: Optional[List[str]] = None,
    ):
        self.db_path = db_path or get_db_path()
        self.truncate_window_title = truncate_window_title
        self._exclude_apps: Set[str] = {
            a.strip().lower() for a in (exclude_apps or []) if a
        }
        self._init_schema()

    def _init_schema(self) -> None:
        """Create tables if they don't exist."""
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.executescript(SCHEMA)
            conn.commit()
        finally:
            conn.close()

    def _should_exclude(self, active_app: str) -> bool:
        """Check if app is in exclude list."""
        if not active_app:
            return False
        return active_app.lower() in self._exclude_apps

    def log(
        self,
        timestamp: str,
        active_app: str,
        window_title: str,
        status: str,
    ) -> None:
        """Insert one activity log entry. Skips excluded apps, truncates titles."""
        if self._should_exclude(active_app):
            return
        window_title = _sanitize_window_title(
            window_title or "", self.truncate_window_title
        )
        conn = sqlite3.connect(str(self.db_path))
        try:
            conn.execute(
                """
                INSERT INTO activity_logs (timestamp, active_app, window_title, status)
                VALUES (?, ?, ?, ?)
                """,
                (timestamp, active_app, window_title, status),
            )
            conn.commit()
        finally:
            conn.close()

    def get_recent_activity(self, limit: int = 50, truncate: bool = True) -> List[dict]:
        """
        Return recent activity logs for Proactive Assistance.
        Returns list of dicts: {timestamp, active_app, window_title, status}
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            cur = conn.execute(
                """
                SELECT timestamp, active_app, window_title, status
                FROM activity_logs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cur.fetchall()
            result = []
            for r in rows:
                title = r["window_title"] or ""
                if truncate and self.truncate_window_title > 0 and title:
                    title = _sanitize_window_title(title, self.truncate_window_title)
                result.append({
                    "timestamp": r["timestamp"],
                    "active_app": r["active_app"] or "",
                    "window_title": title,
                    "status": r["status"],
                })
            return result
        finally:
            conn.close()

    def get_activity_summary(
        self, hours: int = 24, poll_interval_approx_sec: float = 6
    ) -> dict:
        """
        Return aggregated activity summary for the last N hours.
        Useful for "what was I doing?" voice queries.
        Returns: {by_app: {app: approx_minutes}, total_active_rows, total_idle_rows}
        """
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            since = (datetime.utcnow() - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
            cur = conn.execute(
                """
                SELECT active_app, status
                FROM activity_logs
                WHERE timestamp >= ?
                ORDER BY created_at ASC
                """,
                (since,),
            )
            rows = cur.fetchall()
        finally:
            conn.close()

        by_app: dict = defaultdict(float)
        total_active = 0
        total_idle = 0
        for r in rows:
            app = r["active_app"] or "unknown"
            if r["status"] == "idle":
                total_idle += 1
            else:
                total_active += 1
            by_app[app] += 1

        approx_min = poll_interval_approx_sec / 60.0
        return {
            "by_app": {k: round(v * approx_min, 1) for k, v in sorted(by_app.items(), key=lambda x: -x[1])},
            "total_active_rows": total_active,
            "total_idle_rows": total_idle,
        }


# Module-level logger and config (set by start_monitor)
_logger: Optional[ActivityLogger] = None
_sanitize_config: dict = {}


def _get_logger() -> ActivityLogger:
    global _logger, _sanitize_config
    if _logger is None:
        _logger = ActivityLogger(
            truncate_window_title=_sanitize_config.get("truncate_window_title", 0),
            exclude_apps=_sanitize_config.get("exclude_apps") or [],
        )
    return _logger


def set_sanitize_config(truncate_window_title: int = 0, exclude_apps: Optional[List[str]] = None) -> None:
    """Set sanitization options (used by start_monitor)."""
    global _sanitize_config
    _sanitize_config = {
        "truncate_window_title": truncate_window_title,
        "exclude_apps": exclude_apps or [],
    }
    global _logger
    _logger = None  # Reset so next _get_logger() uses new config


def get_recent_activity(limit: int = 50) -> List[dict]:
    """
    Public API: get recent activity logs. Used by Proactive Assistance (UC-04).
    """
    return _get_logger().get_recent_activity(limit)


def get_activity_summary(hours: int = 24, poll_interval_approx_sec: float = 6) -> dict:
    """
    Public API: aggregated activity summary. Used by activity skill for voice.
    """
    return _get_logger().get_activity_summary(hours, poll_interval_approx_sec)
