#!/usr/bin/env python3
"""
Install Mnemosyne hooks for Claude Code.

This script sets up the necessary hooks in ~/.claude/settings.yaml
to integrate Mnemosyne with Claude Code.
"""
import os
import sys
from pathlib import Path

import yaml


def get_hooks_dir() -> Path:
    """Get the directory containing hook scripts."""
    return Path(__file__).parent


def get_claude_settings_path() -> Path:
    """Get the path to Claude Code settings."""
    return Path.home() / ".claude" / "settings.yaml"


def load_settings(path: Path) -> dict:
    """Load existing settings or create new."""
    if path.exists():
        with open(path) as f:
            return yaml.safe_load(f) or {}
    return {}


def save_settings(path: Path, settings: dict) -> None:
    """Save settings to file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(settings, f, default_flow_style=False)


def install_hooks(mnemosyne_url: str = "http://localhost:8781") -> bool:
    """Install Mnemosyne hooks into Claude Code settings."""
    hooks_dir = get_hooks_dir()
    settings_path = get_claude_settings_path()

    # Define hook commands
    hooks_config = {
        "hooks": {
            "session_start": [
                {
                    "command": f"MNEMOSYNE_URL={mnemosyne_url} python3 {hooks_dir}/on_session_start.py",
                    "description": "Start Mnemosyne session and load user context",
                }
            ],
            "message": [
                {
                    "command": f"MNEMOSYNE_URL={mnemosyne_url} python3 {hooks_dir}/on_message.py",
                    "description": "Process message through Mnemosyne",
                }
            ],
            "session_end": [
                {
                    "command": f"MNEMOSYNE_URL={mnemosyne_url} python3 {hooks_dir}/on_session_end.py",
                    "description": "End Mnemosyne session and run consolidation",
                }
            ],
        }
    }

    # Load existing settings
    settings = load_settings(settings_path)

    # Merge hooks (don't overwrite existing non-mnemosyne hooks)
    if "hooks" not in settings:
        settings["hooks"] = {}

    for hook_type, hook_list in hooks_config["hooks"].items():
        if hook_type not in settings["hooks"]:
            settings["hooks"][hook_type] = []

        # Remove any existing mnemosyne hooks
        settings["hooks"][hook_type] = [
            h for h in settings["hooks"][hook_type]
            if "mnemosyne" not in h.get("command", "").lower()
        ]

        # Add new mnemosyne hooks
        settings["hooks"][hook_type].extend(hook_list)

    # Save settings
    save_settings(settings_path, settings)
    print(f"Hooks installed to {settings_path}")
    return True


def uninstall_hooks() -> bool:
    """Remove Mnemosyne hooks from Claude Code settings."""
    settings_path = get_claude_settings_path()

    if not settings_path.exists():
        print("No Claude Code settings found")
        return True

    settings = load_settings(settings_path)

    if "hooks" not in settings:
        print("No hooks configured")
        return True

    # Remove mnemosyne hooks
    for hook_type in list(settings["hooks"].keys()):
        settings["hooks"][hook_type] = [
            h for h in settings["hooks"][hook_type]
            if "mnemosyne" not in h.get("command", "").lower()
        ]

        # Remove empty hook lists
        if not settings["hooks"][hook_type]:
            del settings["hooks"][hook_type]

    # Remove empty hooks section
    if not settings["hooks"]:
        del settings["hooks"]

    save_settings(settings_path, settings)
    print(f"Mnemosyne hooks removed from {settings_path}")
    return True


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Install/uninstall Mnemosyne hooks for Claude Code")
    parser.add_argument("action", choices=["install", "uninstall"], help="Action to perform")
    parser.add_argument("--url", default="http://localhost:8781", help="Mnemosyne API URL")

    args = parser.parse_args()

    if args.action == "install":
        success = install_hooks(args.url)
    else:
        success = uninstall_hooks()

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
