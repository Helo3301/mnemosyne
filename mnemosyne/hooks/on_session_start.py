from __future__ import annotations

#!/usr/bin/env python3
"""
Claude Code hook: on_session_start

This hook is called when a new Claude Code session starts.
It initializes a Mnemosyne session and returns the user's core summary.
"""
import json
import os
import sys
from pathlib import Path

import httpx

MNEMOSYNE_URL = os.getenv("MNEMOSYNE_URL", "http://localhost:8781")
TIMEOUT = 10.0


def get_project_context() -> str | None:
    """Try to determine the current project from the working directory."""
    cwd = Path.cwd()

    # Check for common project indicators
    indicators = [".git", "package.json", "pyproject.toml", "Cargo.toml", "go.mod"]

    for indicator in indicators:
        if (cwd / indicator).exists():
            return cwd.name

    # Check if we're in a known project directory
    if cwd.name not in ("~", "", "/"):
        return cwd.name

    return None


def start_session() -> dict:
    """Start a new Mnemosyne session."""
    project = get_project_context()

    try:
        response = httpx.post(
            f"{MNEMOSYNE_URL}/session/start",
            json={"project_context": project},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return response.json()
    except httpx.RequestError as e:
        return {"error": f"Failed to connect to Mnemosyne: {e}"}
    except httpx.HTTPStatusError as e:
        return {"error": f"Mnemosyne error: {e.response.text}"}


def main():
    """Main entry point."""
    result = start_session()

    if "error" in result:
        # Mnemosyne is not available, continue without it
        print(f"[Mnemosyne] {result['error']}", file=sys.stderr)
        return

    # Output the core summary as context for Claude
    session_id = result.get("session_id", "unknown")
    core_summary = result.get("core_summary", "")
    context = result.get("context", {})

    # Print summary to stderr (goes to Claude Code logs)
    print(f"[Mnemosyne] Session started: {session_id}", file=sys.stderr)

    # Output context that can be used by Claude
    if core_summary:
        output = {
            "type": "mnemosyne_context",
            "session_id": session_id,
            "core_summary": core_summary,
            "user_context": context,
        }
        print(json.dumps(output))


if __name__ == "__main__":
    main()
