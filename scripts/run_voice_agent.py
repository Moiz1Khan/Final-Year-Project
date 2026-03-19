"""
Run the Synq Voice Agent with cleaner startup.
Suppresses pygame deprecation warning for clearer output.
"""
import os
import sys
import warnings
from pathlib import Path

# Suppress pygame/pkg_resources warning
warnings.filterwarnings("ignore", message="pkg_resources is deprecated")

# Suppress HuggingFace symlinks warning on Windows
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from synq.agent.voice_agent import create_agent_from_config

if __name__ == "__main__":
    agent = create_agent_from_config()
    agent.run()
