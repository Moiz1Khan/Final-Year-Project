"""
Background Context Monitor - tracks active app, window, idle status.
Runs in a daemon thread, logs to SQLite. Does not block main application.
"""

import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from synq.context_monitoring.activity_logger import ActivityLogger
from synq.context_monitoring.idle_tracker import is_idle
from synq.context_monitoring.utils import get_active_window


class ContextMonitor:
    """
    Monitors user activity: active app, window title, idle status.
    Runs in background thread. Logs only on state change or at log_interval.
    """

    def __init__(
        self,
        poll_interval_seconds: float = 5,
        idle_threshold_seconds: float = 60,
        log_interval_seconds: float = 10,
        auth_check_fn: Optional[Callable[[], bool]] = None,
        db_path: Optional[Path] = None,
        verbose: bool = False,
        truncate_window_title: int = 0,
        exclude_apps: Optional[List[str]] = None,
    ):
        self.poll_interval = poll_interval_seconds
        self.idle_threshold = idle_threshold_seconds
        self.log_interval = log_interval_seconds
        self.auth_check_fn = auth_check_fn or (lambda: True)
        self.verbose = verbose

        self._logger = ActivityLogger(
            db_path,
            truncate_window_title=truncate_window_title,
            exclude_apps=exclude_apps or [],
        )
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._last_logged: Optional[tuple] = None  # (app, title, status)
        self._last_log_time: float = 0

    def start(self) -> None:
        """Start monitoring in a daemon thread."""
        if self._thread and self._thread.is_alive():
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Stop monitoring (thread exits on next iteration)."""
        self._running = False

    def _run_loop(self) -> None:
        """Main loop: poll activity, log on change or interval."""
        while self._running:
            try:
                if not self.auth_check_fn():
                    time.sleep(self.poll_interval)
                    continue

                app, title = get_active_window()
                user_idle = is_idle(self.idle_threshold)
                status = "idle" if user_idle else "active"
                now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
                t = time.time()

                should_log = False
                current = (app, title, status)
                if self._last_logged != current:
                    should_log = True
                if not should_log and (t - self._last_log_time) >= self.log_interval:
                    should_log = True

                if should_log:
                    self._logger.log(
                        timestamp=now,
                        active_app=app,
                        window_title=title,
                        status=status,
                    )
                    self._last_logged = current
                    self._last_log_time = t

                    if self.verbose:
                        print(f"[ContextMonitor] {now} | {app} | {title} | {status}")

            except Exception as e:
                if self.verbose:
                    print(f"[ContextMonitor] Error: {e}")

            time.sleep(self.poll_interval)
