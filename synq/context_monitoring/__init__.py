"""Context Monitoring - tracks user activity for Proactive Assistance."""

from typing import TYPE_CHECKING, Optional, Optional

from synq.context_monitoring.activity_logger import (
    ActivityLogger,
    get_activity_summary,
    get_recent_activity,
    set_sanitize_config,
)
from synq.context_monitoring.monitor import ContextMonitor

if TYPE_CHECKING:
    pass

__all__ = [
    "ContextMonitor",
    "ActivityLogger",
    "get_recent_activity",
    "get_activity_summary",
    "start_monitor",
    "stop_monitor",
]

_monitor: "ContextMonitor | None" = None


def start_monitor(
    poll_interval_seconds: float = 5,
    idle_threshold_seconds: float = 60,
    log_interval_seconds: float = 10,
    auth_check_fn=None,
    verbose: bool = False,
    truncate_window_title: int = 0,
    exclude_apps: Optional[list] = None,
) -> None:
    """Start the context monitor in a background thread."""
    global _monitor
    set_sanitize_config(
        truncate_window_title=truncate_window_title,
        exclude_apps=exclude_apps or [],
    )
    _monitor = ContextMonitor(
        poll_interval_seconds=poll_interval_seconds,
        idle_threshold_seconds=idle_threshold_seconds,
        log_interval_seconds=log_interval_seconds,
        auth_check_fn=auth_check_fn,
        verbose=verbose,
        truncate_window_title=truncate_window_title,
        exclude_apps=exclude_apps or [],
    )
    _monitor.start()


def stop_monitor() -> None:
    """Stop the context monitor."""
    global _monitor
    if _monitor:
        _monitor.stop()
        _monitor = None
