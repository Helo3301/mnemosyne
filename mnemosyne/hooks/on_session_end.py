from __future__ import annotations

#!/usr/bin/env python3
"""
Claude Code hook: on_session_end

This hook is called when a Claude Code session ends.
It ends the Mnemosyne session and runs consolidation.
"""
import json
import os
import sys

import httpx

MNEMOSYNE_URL = os.getenv("MNEMOSYNE_URL", "http://localhost:8781")
TIMEOUT = 30.0  # Longer timeout for consolidation


def generate_session_summary() -> str | None:
    """Generate a summary of the session (placeholder)."""
    # In a real implementation, this could analyze the conversation
    # and generate a summary. For now, we'll leave it to the API.
    return None


def end_session(summary: str | None = None) -> dict:
    """End the current Mnemosyne session."""
    try:
        response = httpx.post(
            f"{MNEMOSYNE_URL}/session/end",
            json={"summary": summary},
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
    # Get optional summary from argument
    summary = sys.argv[1] if len(sys.argv) > 1 else generate_session_summary()

    result = end_session(summary)

    if "error" in result:
        print(f"[Mnemosyne] {result['error']}", file=sys.stderr)
        return

    # Log results
    session_id = result.get("session_id", "unknown")
    status = result.get("status", "unknown")
    consolidation = result.get("consolidation", {})

    print(f"[Mnemosyne] Session {session_id} {status}", file=sys.stderr)

    promoted = consolidation.get("promoted", [])
    if promoted:
        print(f"[Mnemosyne] Consolidated {len(promoted)} entities", file=sys.stderr)
        for item in promoted:
            print(f"  - {item['entity']}: {item['old_tier']} -> {item['new_tier']}", file=sys.stderr)

    candidates = consolidation.get("candidates_stable_to_core", [])
    if candidates:
        print(f"[Mnemosyne] {len(candidates)} entities ready for CORE promotion (manual review)", file=sys.stderr)

    # Output result
    print(json.dumps(result))


if __name__ == "__main__":
    main()
