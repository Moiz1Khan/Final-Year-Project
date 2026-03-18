"""Synq Voice Agent - Entry point."""

import argparse
import os
import sys
from pathlib import Path

# Suppress HuggingFace symlinks warning on Windows
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from synq.agent.voice_agent import create_agent_from_config


def main():
    """Run the Synq voice agent."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Show live transcriptions (for tuning wake word)",
    )
    args = parser.parse_args()

    agent = create_agent_from_config(debug_override=args.debug)
    if args.debug:
        print("[Debug mode] You'll see transcriptions below. Say 'Hey Synq' to test.\n")
    agent.run()


if __name__ == "__main__":
    main()
