from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import re
import yaml
from synq.memory.db import get_db_path


@dataclass
class ActionResult:
    ok: bool
    message: str


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _config() -> Dict[str, Any]:
    cfg_path = _project_root() / "config" / "config.yaml"
    try:
        data = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data.get("desktop_actions", {}) or {}


def _log_action(action: str, params: Dict[str, Any], result: ActionResult) -> None:
    log_path = get_db_path().parent / "desktop_actions.log"
    payload = {
        "ts": int(time.time()),
        "action": action,
        "params": params,
        "ok": result.ok,
        "message": result.message,
    }
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=True) + "\n")
    except Exception:
        pass


def _mode() -> str:
    return str(_config().get("mode", "ask")).strip().lower() or "ask"


def _enabled() -> bool:
    return bool(_config().get("enabled", True))


def _trusted() -> Dict[str, Any]:
    c = _config()
    return {
        "apps": set(str(x).lower() for x in (c.get("trusted_apps") or [])),
        "domains": [str(x).lower() for x in (c.get("trusted_domains") or [])],
        "paths": [str(x) for x in (c.get("trusted_paths") or [])],
        "routines": c.get("routines") or {},
    }


def normalize_app_name(app: str) -> str:
    """Public alias for skill layer / tests."""
    return _normalize_app_name(app)


def _normalize_app_name(app: str) -> str:
    a = (app or "").strip().lower()
    aliases = {
        "google chrome": "chrome",
        "chrome browser": "chrome",
        "vscode": "code",
        "vs code": "code",
        "visual studio code": "code",
        "file explorer": "explorer",
        "spotify music": "spotify",
    }
    return aliases.get(a, a)


def _win_app_candidates(app: str) -> List[List[str]]:
    """Return launch candidates (command arrays) for common Windows apps."""
    app = _normalize_app_name(app)
    local = os.environ.get("LOCALAPPDATA", "")
    program_files = os.environ.get("ProgramFiles", r"C:\Program Files")
    program_files_x86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    mapping: Dict[str, List[List[str]]] = {
        "chrome": [
            [os.path.join(program_files, "Google", "Chrome", "Application", "chrome.exe")],
            [os.path.join(program_files_x86, "Google", "Chrome", "Application", "chrome.exe")],
            ["cmd", "/c", "start", "", "chrome"],
        ],
        "code": [
            [os.path.join(local, "Programs", "Microsoft VS Code", "Code.exe")],
            [os.path.join(program_files, "Microsoft VS Code", "Code.exe")],
            ["cmd", "/c", "start", "", "code"],
        ],
        "notepad": [["notepad.exe"]],
        "explorer": [["explorer.exe"]],
        "spotify": [
            [os.path.join(os.environ.get("APPDATA", ""), "Spotify", "Spotify.exe")],
            [os.path.join(local, "Spotify", "Spotify.exe")],
            ["cmd", "/c", "start", "", "spotify:"],
        ],
    }
    return mapping.get(app, [["cmd", "/c", "start", "", app]])


def _domain_allowed(url: str, domains: List[str]) -> bool:
    u = (url or "").lower()
    return any(d and d in u for d in domains)


def _path_allowed(path: str, allowed_prefixes: List[str]) -> bool:
    p = Path(path).expanduser().resolve()
    for prefix in allowed_prefixes:
        try:
            if str(p).lower().startswith(str(Path(prefix).expanduser().resolve()).lower()):
                return True
        except Exception:
            continue
    return False


def _guard(action: str, params: Dict[str, Any], requires_trust: bool) -> Optional[ActionResult]:
    if not _enabled():
        return ActionResult(False, "Desktop actions are disabled in config.")
    mode = _mode()
    if mode == "dry_run":
        return ActionResult(True, f"[dry-run] Would execute {action}.")
    if requires_trust and mode == "ask":
        return ActionResult(
            False,
            f"Action '{action}' needs confirmation mode. Set desktop_actions.mode to auto_trusted.",
        )
    return None


def open_app(app: str) -> ActionResult:
    app = (app or "").strip()
    if not app:
        return ActionResult(False, "No app name provided.")
    normalized = _normalize_app_name(app)
    trust = _trusted()
    trusted_norm = {_normalize_app_name(x) for x in trust["apps"]}
    if trusted_norm and normalized not in trusted_norm:
        return ActionResult(False, f"App '{app}' is not in trusted_apps.")
    blocked = _guard("open_app", {"app": app}, requires_trust=False)
    if blocked:
        return blocked
    if os.name == "nt":
        errs: List[str] = []
        for cmd in _win_app_candidates(normalized):
            try:
                if cmd and (cmd[0].endswith(".exe") or "\\" in cmd[0]):
                    if not os.path.exists(cmd[0]):
                        continue
                elif cmd and shutil.which(cmd[0]) is None and cmd[0] not in {"cmd", "explorer.exe"}:
                    continue
                subprocess.Popen(cmd, shell=False)
                return ActionResult(True, f"Opened {normalized}.")
            except Exception as e:
                errs.append(str(e))
        return ActionResult(False, f"Could not open {normalized}.")
    try:
        if shutil.which(normalized) is None:
            return ActionResult(False, f"App '{normalized}' is not installed or not on PATH.")
        subprocess.Popen([normalized], shell=False)
        return ActionResult(True, f"Opened {normalized}.")
    except Exception as e:
        return ActionResult(False, f"Could not open app: {e}")


def open_chrome_url(url: str) -> ActionResult:
    """Open a URL in Google Chrome (Windows). Falls back to default browser."""
    url = (url or "").strip()
    if not url:
        return ActionResult(False, "No URL provided.")
    if not (url.startswith("http://") or url.startswith("https://")):
        url = "https://" + url
    trust = _trusted()
    if trust["domains"] and not _domain_allowed(url, trust["domains"]):
        return ActionResult(False, "URL domain is not in trusted_domains.")
    blocked = _guard("open_chrome_url", {"url": url}, requires_trust=False)
    if blocked:
        return blocked
    if os.name == "nt":
        for cmd in _win_app_candidates("chrome"):
            exe = cmd[0] if cmd else ""
            if exe.endswith("chrome.exe") and os.path.exists(exe):
                try:
                    subprocess.Popen([exe, url], shell=False)
                    return ActionResult(True, f"Opened {url} in Chrome.")
                except Exception as e:
                    return ActionResult(False, f"Could not open Chrome: {e}")
    try:
        webbrowser.open(url)
        return ActionResult(True, f"Opened {url}.")
    except Exception as e:
        return ActionResult(False, f"Could not open URL: {e}")


def vscode_new_file(filename: str) -> ActionResult:
    """Create a .py file under trusted_paths and open it in VS Code."""
    raw = (filename or "").strip()
    if not raw:
        raw = f"synq_{int(time.time())}.py"
    base_name = Path(raw).name
    if not base_name.lower().endswith(".py"):
        base_name = f"{base_name}.py"
    if not re.match(r"^[A-Za-z0-9_\-]+\.py$", base_name):
        return ActionResult(False, "Use a simple filename like hello.py.")
    trust = _trusted()
    prefixes = trust["paths"]
    if not prefixes:
        return ActionResult(False, "Configure desktop_actions.trusted_paths for new files.")
    dest: Optional[Path] = None
    for prefix in prefixes:
        try:
            p = Path(prefix).expanduser().resolve() / base_name
            if _path_allowed(str(p), prefixes):
                dest = p
                break
        except Exception:
            continue
    if dest is None:
        return ActionResult(False, "Could not resolve a trusted folder for the new file.")
    blocked = _guard("vscode_new_file", {"path": str(dest)}, requires_trust=False)
    if blocked:
        return blocked
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if not dest.exists():
            dest.write_text("# Synq - new Python file\n", encoding="utf-8")
    except Exception as e:
        return ActionResult(False, f"Could not create file: {e}")
    if os.name == "nt":
        for cmd in _win_app_candidates("code"):
            exe = cmd[0] if cmd else ""
            if exe.endswith("Code.exe") and os.path.exists(exe):
                try:
                    subprocess.Popen([exe, str(dest)], shell=False)
                    return ActionResult(
                        True,
                        f"Created {dest.name} and opened it in VS Code. "
                        "I can't type your code for you yet - start editing in the editor.",
                    )
                except Exception as e:
                    return ActionResult(False, f"File created but could not launch VS Code: {e}")
    return ActionResult(True, f"Created {dest.name} - add VS Code to PATH or open it manually.")


def open_url(url: str) -> ActionResult:
    url = (url or "").strip()
    if not url:
        return ActionResult(False, "No URL provided.")
    if not (url.startswith("http://") or url.startswith("https://")):
        url = "https://" + url
    trust = _trusted()
    if trust["domains"] and not _domain_allowed(url, trust["domains"]):
        return ActionResult(False, "URL domain is not in trusted_domains.")
    blocked = _guard("open_url", {"url": url}, requires_trust=False)
    if blocked:
        return blocked
    try:
        webbrowser.open(url)
        return ActionResult(True, f"Opened {url}.")
    except Exception as e:
        return ActionResult(False, f"Could not open URL: {e}")


def web_search(query: str) -> ActionResult:
    q = (query or "").strip()
    if not q:
        return ActionResult(False, "No search query provided.")
    return open_url(f"https://www.google.com/search?q={quote_plus(q)}")


def open_path(path: str) -> ActionResult:
    p = (path or "").strip()
    if not p:
        return ActionResult(False, "No path provided.")
    trust = _trusted()
    if trust["paths"] and not _path_allowed(p, trust["paths"]):
        return ActionResult(False, "Path is not in trusted_paths.")
    blocked = _guard("open_path", {"path": p}, requires_trust=False)
    if blocked:
        return blocked
    try:
        os.startfile(p)  # type: ignore[attr-defined]
        return ActionResult(True, f"Opened {p}.")
    except Exception as e:
        return ActionResult(False, f"Could not open path: {e}")


def type_text(text: str) -> ActionResult:
    blocked = _guard("type_text", {"text_len": len(text or "")}, requires_trust=True)
    if blocked:
        return blocked
    try:
        import pyautogui  # type: ignore

        pyautogui.write(text or "", interval=0.01)
        return ActionResult(True, "Typed text.")
    except Exception as e:
        return ActionResult(False, f"Typing unavailable: {e}")


def key_press(keys: List[str]) -> ActionResult:
    blocked = _guard("key_press", {"keys": keys}, requires_trust=True)
    if blocked:
        return blocked
    try:
        import pyautogui  # type: ignore

        keys = [str(k).lower().strip() for k in keys if str(k).strip()]
        if not keys:
            return ActionResult(False, "No keys provided.")
        if len(keys) == 1:
            pyautogui.press(keys[0])
        else:
            pyautogui.hotkey(*keys)
        return ActionResult(True, f"Pressed {'+'.join(keys)}.")
    except Exception as e:
        return ActionResult(False, f"Key press unavailable: {e}")


def clipboard_set(text: str) -> ActionResult:
    blocked = _guard("clipboard_set", {"text_len": len(text or "")}, requires_trust=True)
    if blocked:
        return blocked
    try:
        import pyperclip  # type: ignore

        pyperclip.copy(text or "")
        return ActionResult(True, "Clipboard updated.")
    except Exception as e:
        return ActionResult(False, f"Clipboard unavailable: {e}")


def media_key(name: str) -> ActionResult:
    blocked = _guard("media_key", {"name": name}, requires_trust=False)
    if blocked:
        return blocked
    mapping = {
        "play_pause": "playpause",
        "next": "nexttrack",
        "prev": "prevtrack",
        "mute_toggle": "volumemute",
        "volume_up": "volumeup",
        "volume_down": "volumedown",
    }
    key = mapping.get((name or "").strip().lower())
    if not key:
        return ActionResult(False, "Unknown media key.")
    try:
        import pyautogui  # type: ignore

        pyautogui.press(key)
        return ActionResult(True, f"Sent media key {name}.")
    except Exception as e:
        return ActionResult(False, f"Media key unavailable: {e}")


def wait_ms(ms: int) -> ActionResult:
    ms = max(0, min(int(ms), 15000))
    time.sleep(ms / 1000.0)
    return ActionResult(True, f"Waited {ms}ms.")


def window_switch(direction: str = "next") -> ActionResult:
    keys = ["alt", "tab"] if direction != "prev" else ["alt", "shift", "tab"]
    return key_press(keys)


def run_routine(name: str) -> ActionResult:
    routines = _trusted()["routines"]
    steps = routines.get(name) if isinstance(routines, dict) else None
    if not isinstance(steps, list) or not steps:
        return ActionResult(False, f"Routine '{name}' not found.")
    blocked = _guard("run_routine", {"name": name}, requires_trust=True)
    if blocked:
        return blocked
    handlers = {
        "open_app": lambda p: open_app(str(p.get("app", ""))),
        "open_url": lambda p: open_url(str(p.get("url", ""))),
        "open_chrome_url": lambda p: open_chrome_url(str(p.get("url", ""))),
        "vscode_new_file": lambda p: vscode_new_file(str(p.get("filename", ""))),
        "search_web": lambda p: web_search(str(p.get("query", ""))),
        "open_path": lambda p: open_path(str(p.get("path", ""))),
        "wait_ms": lambda p: wait_ms(int(p.get("ms", 500))),
        "key_press": lambda p: key_press(list(p.get("keys") or [])),
        "media_key": lambda p: media_key(str(p.get("name", ""))),
    }
    for idx, s in enumerate(steps, start=1):
        if not isinstance(s, dict):
            return ActionResult(False, f"Routine step {idx} invalid.")
        a = str(s.get("action", "")).strip()
        fn = handlers.get(a)
        if fn is None:
            return ActionResult(False, f"Routine step {idx}: unsupported action '{a}'.")
        res = fn(s)
        _log_action(a, s, res)
        if not res.ok:
            return ActionResult(False, f"Routine stopped at step {idx}: {res.message}")
    return ActionResult(True, f"Routine '{name}' completed.")


def execute_action(action: str, params: Dict[str, Any]) -> ActionResult:
    action = (action or "").strip().lower()
    params = params or {}
    handlers = {
        "open_app": lambda: open_app(str(params.get("app", ""))),
        "open_url": lambda: open_url(str(params.get("url", ""))),
        "open_chrome_url": lambda: open_chrome_url(str(params.get("url", ""))),
        "vscode_new_file": lambda: vscode_new_file(str(params.get("filename", ""))),
        "search_web": lambda: web_search(str(params.get("query", ""))),
        "open_path": lambda: open_path(str(params.get("path", ""))),
        "type_text": lambda: type_text(str(params.get("text", ""))),
        "key_press": lambda: key_press(list(params.get("keys") or [])),
        "window_switch": lambda: window_switch(str(params.get("direction", "next"))),
        "media_key": lambda: media_key(str(params.get("name", ""))),
        "clipboard_set": lambda: clipboard_set(str(params.get("text", ""))),
        "wait_ms": lambda: wait_ms(int(params.get("ms", 500))),
        "run_routine": lambda: run_routine(str(params.get("name", ""))),
    }
    fn = handlers.get(action)
    if fn is None:
        res = ActionResult(False, f"Unsupported desktop action '{action}'.")
        _log_action(action, params, res)
        return res
    res = fn()
    _log_action(action, params, res)
    return res

