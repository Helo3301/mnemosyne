# Mnemosyne (Mneme)

A graph-based associative memory system for Claude Code, providing persistent context across sessions.

## Overview

Mnemosyne (self-named "Mneme" after the Greek Muse of Memory) is a knowledge graph that:

- **Extracts entities** from conversations (projects, technologies, preferences, goals)
- **Builds relationships** between concepts
- **Provides context** at session start based on what's relevant
- **Consolidates memories** promoting frequently-accessed items to permanent storage
- **Decays unused memories** to keep context fresh and relevant

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Claude Code                          │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐ │
│  │SessionStart │    │  Conversation│    │ SessionEnd  │ │
│  │   Hook      │    │  Processing  │    │    Hook     │ │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘ │
└─────────┼──────────────────┼──────────────────┼────────┘
          │                  │                  │
          ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────┐
│                    Mnemosyne API                        │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐ │
│  │   Session   │    │  Extraction │    │Consolidation│ │
│  │  Manager    │    │   Engine    │    │   Engine    │ │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘ │
└─────────┼──────────────────┼──────────────────┼────────┘
          │                  │                  │
          ▼                  ▼                  ▼
┌─────────────────────────────────────────────────────────┐
│                  Knowledge Graph (SQLite)               │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐ │
│  │  Entities   │    │Relationships│    │  Sessions   │ │
│  │  (nodes)    │◄──►│   (edges)   │    │   (logs)    │ │
│  └─────────────┘    └─────────────┘    └─────────────┘ │
└─────────────────────────────────────────────────────────┘
```

## Memory Tiers

| Tier | Decay Rate | Description |
|------|------------|-------------|
| **CORE** | 0.01/day | Permanent memories (identity, key preferences) |
| **STABLE** | 0.03/day | Important but not critical (active projects) |
| **EPHEMERAL** | 0.1/day | Recent/temporary (mentioned once) |

Memories are promoted based on activation frequency and time.

## API Endpoints

### Session Management
- `POST /session/start` - Start session, get context
- `POST /session/end` - End session, run consolidation
- `GET /session/current` - Get current session info

### Memory Operations
- `POST /memory/entities` - Create entity
- `GET /memory/entities` - List entities
- `POST /memory/relationships` - Create relationship
- `POST /process` - Process conversation turns

### Context Retrieval
- `GET /user/model` - Get user summary and context
- `POST /context/relevant` - Get relevant context for query
- `POST /activate` - Spreading activation from seed entities

## Quick Start

```bash
# Start with Docker Compose
docker compose up -d

# Check health
curl http://localhost:8781/health

# Start a session
curl -X POST http://localhost:8781/session/start

# Process a conversation
curl -X POST http://localhost:8781/process \
  -H "Content-Type: application/json" \
  -d '{"turns": [{"role": "user", "content": "I am working on myproject with Python"}]}'
```

## Claude Code Integration

Add hooks to `~/.claude/settings.json`:

```json
{
  "hooks": {
    "SessionStart": [{
      "matcher": "",
      "hooks": [{"type": "command", "command": "/path/to/claude-review-memory"}]
    }],
    "SessionEnd": [{
      "matcher": "",
      "hooks": [{"type": "command", "command": "/path/to/claude-save-memory"}]
    }]
  }
}
```

## Configuration

See `config.yaml` for settings including:
- Decay rates per tier
- Consolidation thresholds
- Spreading activation parameters
- Core summary generation

## License

Apache License 2.0 - See [LICENSE](LICENSE) for details.
