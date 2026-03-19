"""
Context Monitoring Demo - run monitor, print logs to terminal.

Verifies: app switching, idle detection, persistence.
Run for ~30 seconds or until Ctrl+C, then shows get_recent_activity().
"""
import sys
import time
from pathlib import Path

if sys.platform != "win32":
    print("Context monitoring is Windows-only. Skipping.")
    sys.exit(0)

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synq.context_monitoring import get_recent_activity, start_monitor, stop_monitor


def main():
    print("=" * 60)
    print("Context Monitoring Demo")
    print("=" * 60)
    print("Monitoring: active app, window title, idle status")
    print("Switch apps or stay idle 60+ seconds to see changes.")
    print("Press Ctrl+C to stop and view recent activity.\n")

    # Start with verbose=True to see logs in terminal
    start_monitor(
        poll_interval_seconds=5,
        idle_threshold_seconds=60,
        log_interval_seconds=10,
        verbose=True,
    )

    try:
        while True:
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nStopping...")
        stop_monitor()
        time.sleep(1)  # Let thread exit

    print("\n" + "=" * 60)
    print("Recent activity (last 5 entries):")
    print("=" * 60)
    recent = get_recent_activity(limit=5)
    for i, entry in enumerate(recent, 1):
        title = (entry.get("window_title") or "")[:50]
        print(
            f"  {i}. {entry['timestamp']} | {entry['active_app']} | "
            f"{title} | {entry['status']}"
        )
    print("\nDone.")


if __name__ == "__main__":
    main()
