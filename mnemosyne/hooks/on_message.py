#!/usr/bin/env python3
"""
Claude Code hook: on_message

This hook processes conversation messages to extract entities,
infer proficiency, and update the memory graph.

Can be called with message content via stdin or as argument.
"""
import json
import os
import sys
from typing import Any

import httpx

MNEMOSYNE_URL = os.getenv("MNEMOSYNE_URL", "http://localhost:8781")
TIMEOUT = 15.0


def process_message(content: str, role: str = "user") -> dict[str, Any]:
    """Process a message through Mnemosyne."""
    try:
        response = httpx.post(
            f"{MNEMOSYNE_URL}/process",
            json={
                "turns": [{"role": role, "content": content}]
            },
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
    # Get message content from argument or stdin
    if len(sys.argv) > 1:
        content = sys.argv[1]
        role = sys.argv[2] if len(sys.argv) > 2 else "user"
    else:
        # Read from stdin
        content = sys.stdin.read().strip()
        role = "user"

    if not content:
        print("[Mnemosyne] No message content provided", file=sys.stderr)
        return

    result = process_message(content, role)

    if "error" in result:
        print(f"[Mnemosyne] {result['error']}", file=sys.stderr)
        return

    # Log extraction results
    entities = result.get("entities_extracted", [])
    prof_signals = result.get("proficiency_signals", [])
    goal_signals = result.get("goal_signals", [])

    if entities:
        print(f"[Mnemosyne] Extracted {len(entities)} entities", file=sys.stderr)

    if prof_signals:
        for signal in prof_signals:
            print(f"[Mnemosyne] Proficiency signal: {signal['technology']} ({signal['signal']})", file=sys.stderr)

    if goal_signals:
        for signal in goal_signals:
            print(f"[Mnemosyne] Goal signal: {signal['goal']} ({signal['type']})", file=sys.stderr)

    # Output structured result
    print(json.dumps(result))


if __name__ == "__main__":
    main()
