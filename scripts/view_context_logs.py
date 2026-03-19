"""View recent context monitoring activity - no sqlite3 CLI needed."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from synq.context_monitoring.activity_logger import get_db_path

DB = get_db_path()
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 20

conn = sqlite3.connect(str(DB))
conn.row_factory = sqlite3.Row
cur = conn.execute(
    "SELECT timestamp, active_app, window_title, status FROM activity_logs ORDER BY created_at DESC LIMIT ?",
    (LIMIT,),
)
rows = cur.fetchall()
conn.close()

print(f"Last {len(rows)} activity logs from {DB}\n")
for r in rows:
    title = (r["window_title"] or "")[:50]
    print(f"  {r['timestamp']} | {r['active_app'] or '?'} | {title} | {r['status']}")
