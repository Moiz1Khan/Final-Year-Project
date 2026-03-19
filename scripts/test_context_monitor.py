"""
Quick automated test for Context Monitoring.
Runs ~15 seconds, no user interaction. Exits 0 on pass, 1 on fail.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def main():
    if sys.platform != "win32":
        print("SKIP: Context monitoring is Windows-only.")
        return 0

    from synq.context_monitoring import get_recent_activity, start_monitor, stop_monitor

    # Run monitor for 15 seconds
    start_monitor(poll_interval_seconds=3, idle_threshold_seconds=8, log_interval_seconds=6, verbose=False)
    time.sleep(15)
    stop_monitor()
    time.sleep(1.5)

    recent = get_recent_activity(limit=20)
    if len(recent) < 2:
        print("FAIL: Expected at least 2 log entries, got", len(recent))
        return 1

    # Check structure
    entry = recent[0]
    required = ["timestamp", "active_app", "window_title", "status"]
    for k in required:
        if k not in entry:
            print(f"FAIL: Missing key '{k}' in entry")
            return 1

    valid_status = {e["status"] for e in recent}
    if not valid_status.issubset({"active", "idle"}):
        print("FAIL: Invalid status values:", valid_status)
        return 1

    print("PASS: Context monitoring OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
