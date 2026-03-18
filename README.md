<<<<<<< HEAD
Final-Year-Project
=======
Synq Voice Agent
Production-ready voice agent. API mode (OpenAI) or local mode.
Modes
Mode	STT	NLU	TTS
api (production)	OpenAI Whisper	GPT-4o-mini + Skills	ElevenLabs (streaming) or OpenAI
local (offline)	faster-whisper	Pattern matching	pyttsx3
Architecture
Skills – Modular, voice-accessible. Add modules in `synq/skills/` – they become voice-accessible.
Gate: Face recognition or wake word "Hey Synq"
Recording: PyAudio (record until silence)
Playback: pygame (interrupt on speech)
Quick Start
1. Create virtual environment (Python 3.10)
```bash
python -m venv venv
venv\Scripts\activate   # Windows
# source venv/bin/activate  # macOS/Linux
```
2. Install dependencies
```bash
pip install -r requirements.txt
```
3. Run
```bash
python main.py
```
4. API mode (production, low-latency)
Copy `.env.example` to `.env`
Add `OPENAI_API_KEY=sk-...` and `ELEVENLABS_API_KEY=...`
Set `mode: "api"` in `config/config.yaml`
ElevenLabs = streaming TTS (plays as it generates, like professional agents)
Run – fast reply, minimal delay
5. Gate modes
`gate.mode: "none"` – Always listening
`gate.mode: "wake_word"` – Say "Hey Synq" first
`gate.mode: "face"` – Face recognition (add `face_recognition/`)
6. Adding modules (skills)
See `synq/skills/ADDING_MODULES.md`. Each skill you add is voice-accessible.
Say "Hey Synq" then ask something like "What time is it?" or "What can you do?".
Project Structure
```
synq/
├── agent/          # Main voice agent orchestrator
├── wake_word/      # Wake word detection (voice; face later)
├── stt/            # Speech-to-Text
├── tts/            # Text-to-Speech
├── nlu/            # Intent handling
config/
└── config.yaml     # Configuration
```
Configuration
Edit `config/config.yaml`:
wake_word.mode: `whisper` (default, best accuracy), `keyword` (Vosk), or `porcupine`
wake_word.phrases: Custom wake phrases
whisper.model_size: `tiny` (fast), `base` (balanced), or `small` (most accurate)
Optional: Porcupine (better wake word)
Sign up at Picovoice Console
Create custom wake words: "Hey Synq", "Hi Synq", "Synq"
Download `.ppn` files for your platform
Set `PICOVOICE_ACCESS_KEY` in `.env` and `porcupine.keyword_paths` in config
Troubleshooting
Wake word not detected
Enable debug: `python main.py --debug` to see live transcriptions
Lower VAD threshold if mic is quiet: `vad_energy_threshold: 150` in config
Try "base" model for wake word: set `whisper.model_size: "base"` (more accurate, slightly slower)
Check microphone: `python scripts/list_devices.py` and set `audio.device` in config
Face Recognition (Later)
The wake word system uses a `WakeWordDetector` base class. A face-recognition-based detector can be added later that emits `WakeWordEvent(source=WakeWordSource.FACE)` when a recognized user looks at the device.
>>>>>>> cc0a47f (Initial commit - Final Year Project)
