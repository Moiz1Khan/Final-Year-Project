"""Download Vosk model for offline STT. Run once before first use."""

import os
import sys
import urllib.request
import zipfile
from pathlib import Path

# Small English model - ~40MB
MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
MODEL_NAME = "vosk-model-small-en-us-0.15"


def main():
    root = Path(__file__).resolve().parents[1]
    models_dir = root / "models"
    model_path = models_dir / MODEL_NAME

    if model_path.exists():
        print(f"Model already exists at {model_path}")
        return

    models_dir.mkdir(parents=True, exist_ok=True)
    zip_path = models_dir / f"{MODEL_NAME}.zip"

    print(f"Downloading {MODEL_NAME} (~40MB)...")
    try:
        urllib.request.urlretrieve(MODEL_URL, zip_path)
    except Exception as e:
        print(f"Download failed: {e}")
        print("Manual download: extract to models/ folder")
        sys.exit(1)

    print("Extracting...")
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(models_dir)

    zip_path.unlink()
    print(f"Done. Model at {model_path}")


if __name__ == "__main__":
    main()
