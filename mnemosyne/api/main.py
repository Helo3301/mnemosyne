from __future__ import annotations

"""FastAPI application for Mnemosyne."""
import logging
import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ..db.database import Database
from ..graph.consolidation import run_end_of_session_consolidation
from ..models.entities import Session
from .routes.context import router as context_router
from .routes.memory import router as memory_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def load_config() -> dict:
    """Load configuration from config.yaml."""
    config_paths = [
        Path("/app/config.yaml"),
        Path(__file__).parent.parent.parent / "config.yaml",
        Path.home() / "mnemosyne" / "config.yaml",
    ]

    for path in config_paths:
        if path.exists():
            with open(path) as f:
                return yaml.safe_load(f)

    # Default config
    return {
        "server": {"host": "0.0.0.0", "port": 8781},
        "database": {"path": "/data/mnemosyne.db"},
        "hermes": {"host": "http://hermes:8780", "timeout": 30},
    }


# Global state
config = load_config()
current_session_id: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    logger.info("Starting Mnemosyne...")

    # Initialize database
    db_path = config.get("database", {}).get("path", "/data/mnemosyne.db")
    Database.initialize(db_path)
    logger.info(f"Database initialized at {db_path}")

    yield

    # Shutdown
    logger.info("Shutting down Mnemosyne...")


# Create FastAPI app
app = FastAPI(
    title="Mnemosyne",
    description="Graph-Based Associative Memory System for Claude Code",
    version="0.1.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(memory_router, prefix="/memory", tags=["memory"])
app.include_router(context_router, prefix="/context", tags=["context"])


# ==================== Health & Status ====================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "mnemosyne"}


@app.get("/stats")
async def get_stats():
    """Get database statistics."""
    from ..db.database import get_db
    db = get_db()
    stats = db.get_stats()
    stats["current_session"] = current_session_id
    return stats


# ==================== Session Management ====================

class SessionStartRequest(BaseModel):
    """Request to start a new session."""
    project_context: str | None = None


class SessionStartResponse(BaseModel):
    """Response from session start."""
    session_id: str
    core_summary: str
    context: dict


class SessionEndRequest(BaseModel):
    """Request to end a session."""
    summary: str | None = None


@app.post("/session/start", response_model=SessionStartResponse)
async def start_session(request: SessionStartRequest = None):
    """
    Start a new session.

    Returns the core summary and relevant context for the session.
    """
    global current_session_id

    from ..db.database import get_db
    from ..summary.generator import CoreSummaryGenerator

    db = get_db()

    # Generate session ID
    session_id = str(uuid.uuid4())[:8]
    current_session_id = session_id

    # Create session
    project_context = request.project_context if request else None
    session = Session(
        id=session_id,
        started_at=datetime.now(),
        project_context=project_context,
    )
    db.create_session(session)

    # Generate core summary
    generator = CoreSummaryGenerator()
    core_summary = generator.generate()

    # Get context
    context = generator.get_session_context(project_context)

    logger.info(f"Session started: {session_id}")

    return SessionStartResponse(
        session_id=session_id,
        core_summary=core_summary,
        context=context,
    )


@app.post("/session/end")
async def end_session(request: SessionEndRequest = None):
    """
    End the current session.

    Runs consolidation and saves session summary.
    """
    global current_session_id

    if not current_session_id:
        return {"status": "no_active_session"}

    from ..db.database import get_db
    db = get_db()

    # End session
    summary = request.summary if request else None
    db.end_session(current_session_id, summary)

    # Run consolidation
    consolidation_results = run_end_of_session_consolidation(current_session_id)

    session_id = current_session_id
    current_session_id = None

    logger.info(f"Session ended: {session_id}")

    return {
        "status": "ended",
        "session_id": session_id,
        "consolidation": consolidation_results,
    }


@app.get("/session/current")
async def get_current_session():
    """Get current session info."""
    if not current_session_id:
        return {"status": "no_active_session"}

    from ..db.database import get_db
    db = get_db()

    session = db.get_session(current_session_id)
    if not session:
        return {"status": "session_not_found"}

    return {
        "session_id": session.id,
        "started_at": session.started_at.isoformat(),
        "project_context": session.project_context,
    }


# ==================== Quick Access Endpoints ====================

@app.get("/user/model")
async def get_user_model():
    """Get the current user model (core summary)."""
    from ..summary.generator import CoreSummaryGenerator

    generator = CoreSummaryGenerator()
    return {
        "summary": generator.generate(),
        "context": generator.get_session_context(),
    }


@app.post("/activate")
async def trigger_activation(seed_entities: list[str], depth: int = 2):
    """
    Trigger spreading activation from seed entities.

    Args:
        seed_entities: Names of entities to start from
        depth: Maximum traversal depth
    """
    from ..graph.activation import SpreadingActivation

    activator = SpreadingActivation()
    activated = activator.spread_from_query(
        seed_entities,
        depth=depth,
        session_id=current_session_id,
    )

    # Get entity details
    entities = activator.get_activated_entities(activated)

    return {
        "activated_count": len(activated),
        "entities": [
            {
                "name": e.name,
                "type": e.entity_type.value,
                "strength": strength,
            }
            for e, strength in entities[:20]
        ],
    }


# ==================== Process Conversation ====================

class ConversationTurn(BaseModel):
    """A single conversation turn."""
    role: str = "user"
    content: str


class ProcessConversationRequest(BaseModel):
    """Request to process conversation turns."""
    turns: list[ConversationTurn]


@app.post("/process")
async def process_conversation(request: ProcessConversationRequest):
    """
    Process conversation turns to extract entities and update memory.

    This is the main integration point for Claude Code hooks.
    """
    from ..extraction.extractor import ConversationExtractor
    from ..graph.operations import GraphOperations
    from ..inference.goals import GoalInferrer
    from ..inference.preferences import PreferenceInferrer
    from ..inference.proficiency import ProficiencyInferrer

    extractor = ConversationExtractor()
    ops = GraphOperations()
    prof_inferrer = ProficiencyInferrer()
    pref_inferrer = PreferenceInferrer()
    goal_inferrer = GoalInferrer()

    results = {
        "entities_extracted": [],
        "relationships_inferred": [],
        "proficiency_signals": [],
        "preference_signals": [],
        "goal_signals": [],
    }

    for turn in request.turns:
        # Extract entities
        extraction = extractor.process_turn(turn.content, turn.role)

        for entity in extraction.entities:
            results["entities_extracted"].append({
                "name": entity.name,
                "type": entity.entity_type.value,
                "confidence": entity.confidence,
            })

        for rel in extraction.relationships:
            results["relationships_inferred"].append({
                "source": rel.source_name,
                "target": rel.target_name,
                "type": rel.relationship_type.value,
            })

        # Infer proficiency (only from user turns)
        if turn.role == "user":
            prof_signals = prof_inferrer.infer_from_conversation(turn.content)
            for tech, signal_type, weight in prof_signals:
                prof_inferrer.record_signal(tech, signal_type, current_session_id)
                results["proficiency_signals"].append({
                    "technology": tech,
                    "signal": signal_type,
                    "weight": weight,
                })

            # Infer preferences
            pref_signals = pref_inferrer.infer_from_message(turn.content)
            pref_inferrer.apply_signals(pref_signals)
            for signal in pref_signals:
                results["preference_signals"].append({
                    "item": signal.item,
                    "sentiment": signal.sentiment,
                })

            # Infer goals
            goal_signals = goal_inferrer.infer_from_message(turn.content)
            goal_inferrer.apply_signals(goal_signals)
            for signal in goal_signals:
                results["goal_signals"].append({
                    "goal": signal.goal_text,
                    "type": signal.signal_type,
                })

    # Store extracted entities in the graph
    session_summary = extractor.get_session_summary()
    for entity in session_summary.entities:
        ops.get_or_create_entity(
            entity.entity_type,
            entity.name,
            confidence=entity.confidence,
        )

    return results


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "mnemosyne.api.main:app",
        host=config.get("server", {}).get("host", "0.0.0.0"),
        port=config.get("server", {}).get("port", 8781),
        reload=True,
    )
