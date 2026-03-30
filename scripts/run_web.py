"""Start Synq web console (multi-user setup & credentials)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("synq.web.app:app", host="127.0.0.1", port=8765, reload=False)
