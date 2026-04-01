# Synq — Final Year Project

Voice-native assistant with a **web console**, **JWT API**, and **Google OAuth** (Sign in with Google + Gmail/Calendar). Supports **cloud voice** (`synq_cloud`: mic/speaker only, STT/chat/TTS on the server) or **local** pipelines.

**Repository:** [github.com/Moiz1Khan/Final-Year-Project](https://github.com/Moiz1Khan/Final-Year-Project) (private)

## Features

- **Web UI** (`scripts/run_web.py`): signup/login, **Continue with Google**, credentials (display name, Google connect, optional local API keys), JWT for `synq_cloud` voice clients.
- **REST API** (`/api/v1/...`): chat, transcribe, TTS, auth register/login — shared keys on the server via `.env`.
- **Skills**: modular modules under `synq/skills/` (e.g. productivity: tasks, reminders, calendar, email).
- **Desktop actions (Phase 1)**: open apps/sites, web search, open folder/file, shortcuts, media keys, and routines with safe allowlists.
- **Gate**: none / wake word / face (configurable).
- **Audio**: PyAudio record, pygame playback with interrupt.

## Modes

| Voice backend | Role |
|---------------|------|
| **`synq_cloud`** (recommended) | Client records audio → API transcribes/LLM/TTS → JWT in `data/auth_token.json` after web login. |
| **`local`** | STT/NLU/TTS on the machine using `.env` / per-user stored keys (see `config/config.yaml`). |

| `mode` in YAML | When `voice.backend` is local |
|----------------|-------------------------------|
| **api** | OpenAI (+ optional ElevenLabs STT/TTS) |
| **local** | faster-whisper + pattern NLU + pyttsx3 |

## Quick start (Windows)

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

### Run voice agent

```powershell
python main.py
# or: python scripts/run_voice_agent.py
```

### Run web console + API

```powershell
python scripts/run_web.py
```

Default: `http://127.0.0.1:8765` — set `voice.synq_cloud.base_url` in `config/config.yaml` to match.

## Configuration

1. **`.env`** — copy from `.env.example` locally (this file is **not** in git: GitHub **push protection** blocks commits that contain API keys). Set `OPENAI_API_KEY`, `ELEVENLABS_*` as needed for API mode, `SYNQ_GOOGLE_OAUTH_CLIENT_SECRETS_PATH` or `GOOGLE_CLIENT_SECRETS_PATH` for Google login + integrations, session/JWT secrets as in `.env.example`.
2. **`config/config.yaml`** — `voice.backend`, `synq_cloud.base_url`, `mode`, `gate`, `tts`, etc.

### Google OAuth (web “Sign in with Google”)

1. Create an OAuth **Web** client in Google Cloud; add redirect URI `http://127.0.0.1:8765/auth/google/callback` (adjust host/port if needed).
2. Point `SYNQ_GOOGLE_OAUTH_CLIENT_SECRETS_PATH` (or `GOOGLE_CLIENT_SECRETS_PATH`) to the downloaded JSON.
3. Add test users while the consent screen is in **Testing**, or complete verification for production.

### Desktop actions config

`config/config.yaml` includes `desktop_actions`:
- `mode: ask | auto_trusted | dry_run`
- `trusted_apps`, `trusted_domains`, `trusted_paths`
- reusable `routines` (example included: `morning routine`)

Commands examples:
- “open chrome”
- “search web for Python async queue”
- “press ctrl s”
- “run routine morning routine”

### First-time install

- If the database has no accounts yet, open **`/setup`** once to create the owner (password). Alternatively, with Google OAuth configured, use **Continue with Google** from **`/login`** so the default user row is claimed via Google.

## Project layout

```
synq/
├── agent/           # Voice agent (local + remote/synq_cloud)
├── api/             # FastAPI routes for chat/tts/transcribe/auth
├── web/             # Jinja templates, static assets, Google OAuth routes
├── auth/            # Users, JWT, encrypted credentials
├── skills/          # Voice-accessible modules (see synq/skills/ADDING_MODULES.md)
├── integrations/    # Gmail, Calendar, Google OAuth helpers
config/
└── config.yaml
scripts/
├── run_web.py
└── run_voice_agent.py
```

## Productivity & email

Skill: `productivity` — tasks, reminders, calendar, email (needs Google tokens from web OAuth or legacy token upload).

Optional: `email_monitoring` in `config/config.yaml` for Gmail polling notifications.

## Context monitoring

Optional: logs foreground app/window to `data/context_monitoring.db` (see `config/config.yaml`).

## Adding skills

See `synq/skills/ADDING_MODULES.md`.

---

*FYP — Synq voice agent with web console and Google-integrated productivity.*
