from __future__ import annotations

"""Memory management API routes for Mnemosyne."""
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...db.database import get_db
from ...graph.operations import GraphOperations
from ...models.entities import EntityType, FeedbackType, RelationshipType, Tier

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== Request/Response Models ====================

class EntityRequest(BaseModel):
    """Request to create/update an entity."""
    entity_type: str
    name: str
    confidence: float = 0.5
    tier: str = "EPHEMERAL"
    metadata: dict[str, Any] | None = None


class EntityResponse(BaseModel):
    """Entity response."""
    id: int
    entity_type: str
    name: str
    normalized_name: str
    tier: str
    confidence: float
    activation_count: int
    metadata: dict[str, Any]


class RelationshipRequest(BaseModel):
    """Request to create a relationship."""
    source_type: str
    source_name: str
    target_type: str
    target_name: str
    relationship_type: str
    weight: float = 0.5
    metadata: dict[str, Any] | None = None


class FeedbackRequest(BaseModel):
    """Request to record feedback."""
    signal_type: str  # POSITIVE, NEGATIVE, CORRECTION
    signal_text: str | None = None
    entity_name: str | None = None
    entity_type: str | None = None


# ==================== Entity Endpoints ====================

@router.post("/entities", response_model=EntityResponse)
async def create_entity(request: EntityRequest):
    """Create or update an entity."""
    try:
        entity_type = EntityType(request.entity_type)
        tier = Tier(request.tier)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    ops = GraphOperations()
    entity = ops.get_or_create_entity(
        entity_type=entity_type,
        name=request.name,
        confidence=request.confidence,
        tier=tier,
        metadata=request.metadata,
    )

    return EntityResponse(
        id=entity.id,
        entity_type=entity.entity_type.value,
        name=entity.name,
        normalized_name=entity.normalized_name,
        tier=entity.tier.value,
        confidence=entity.confidence,
        activation_count=entity.activation_count,
        metadata=entity.metadata,
    )


@router.get("/entities/{entity_id}", response_model=EntityResponse)
async def get_entity(entity_id: int):
    """Get an entity by ID."""
    db = get_db()
    entity = db.get_entity(entity_id)

    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    return EntityResponse(
        id=entity.id,
        entity_type=entity.entity_type.value,
        name=entity.name,
        normalized_name=entity.normalized_name,
        tier=entity.tier.value,
        confidence=entity.confidence,
        activation_count=entity.activation_count,
        metadata=entity.metadata,
    )


@router.get("/entities")
async def list_entities(
    entity_type: str | None = None,
    tier: str | None = None,
    limit: int = 50,
):
    """List entities with optional filters."""
    db = get_db()

    if entity_type:
        try:
            et = EntityType(entity_type)
            entities = db.get_entities_by_type(et)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid entity type: {entity_type}")
    elif tier:
        try:
            t = Tier(tier)
            entities = db.get_entities_by_tier(t)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid tier: {tier}")
    else:
        # Get all entities (limited)
        entities = []
        for et in EntityType:
            entities.extend(db.get_entities_by_type(et))

    entities = sorted(entities, key=lambda e: e.last_activated_at, reverse=True)[:limit]

    return {
        "count": len(entities),
        "entities": [
            {
                "id": e.id,
                "type": e.entity_type.value,
                "name": e.name,
                "tier": e.tier.value,
                "confidence": e.confidence,
                "activation_count": e.activation_count,
            }
            for e in entities
        ],
    }


@router.post("/entities/{entity_id}/activate")
async def activate_entity(entity_id: int):
    """Activate an entity."""
    db = get_db()
    entity = db.activate_entity(entity_id)

    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    return {
        "status": "activated",
        "entity_id": entity_id,
        "activation_count": entity.activation_count,
    }


@router.delete("/entities/{entity_id}")
async def delete_entity(entity_id: int):
    """Delete an entity."""
    db = get_db()
    success = db.delete_entity(entity_id)

    if not success:
        raise HTTPException(status_code=404, detail="Entity not found")

    return {"status": "deleted", "entity_id": entity_id}


# ==================== Relationship Endpoints ====================

@router.post("/relationships")
async def create_relationship(request: RelationshipRequest):
    """Create or strengthen a relationship."""
    try:
        source_type = EntityType(request.source_type)
        target_type = EntityType(request.target_type)
        rel_type = RelationshipType(request.relationship_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    db = get_db()
    ops = GraphOperations()

    # Get or create source and target entities
    source = ops.get_or_create_entity(source_type, request.source_name)
    target = ops.get_or_create_entity(target_type, request.target_name)

    # Create relationship
    rel = ops.get_or_create_relationship(
        source.id,
        target.id,
        rel_type,
        weight=request.weight,
        metadata=request.metadata,
    )

    return {
        "id": rel.id,
        "source_id": rel.source_id,
        "target_id": rel.target_id,
        "relationship_type": rel.relationship_type.value,
        "weight": rel.weight,
        "evidence_count": rel.evidence_count,
    }


@router.get("/relationships")
async def list_relationships(
    entity_id: int | None = None,
    relationship_type: str | None = None,
):
    """List relationships."""
    db = get_db()

    if entity_id:
        rel_type = None
        if relationship_type:
            try:
                rel_type = RelationshipType(relationship_type)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid relationship type: {relationship_type}")

        outgoing = db.get_relationships_from(entity_id, rel_type)
        incoming = db.get_relationships_to(entity_id, rel_type)

        return {
            "outgoing": [
                {
                    "id": r.id,
                    "target_id": r.target_id,
                    "type": r.relationship_type.value,
                    "weight": r.weight,
                }
                for r in outgoing
            ],
            "incoming": [
                {
                    "id": r.id,
                    "source_id": r.source_id,
                    "type": r.relationship_type.value,
                    "weight": r.weight,
                }
                for r in incoming
            ],
        }

    # Without entity_id, return limited results
    return {"error": "entity_id parameter required"}


# ==================== Feedback Endpoints ====================

@router.post("/feedback")
async def record_feedback(request: FeedbackRequest):
    """Record user feedback."""
    try:
        signal_type = FeedbackType(request.signal_type)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid signal type: {request.signal_type}")

    db = get_db()
    from ...models.entities import Feedback

    # Find entity if specified
    entity_id = None
    if request.entity_name and request.entity_type:
        try:
            entity_type = EntityType(request.entity_type)
            entity = db.get_entity_by_name(entity_type, request.entity_name)
            if entity:
                entity_id = entity.id
        except ValueError:
            pass

    # Record feedback
    from ...api.main import current_session_id
    feedback = Feedback(
        session_id=current_session_id,
        entity_id=entity_id,
        signal_type=signal_type,
        signal_text=request.signal_text,
    )
    saved = db.record_feedback(feedback)

    return {
        "id": saved.id,
        "signal_type": saved.signal_type.value,
        "entity_id": saved.entity_id,
        "captured_at": saved.captured_at.isoformat(),
    }


# ==================== User Model Endpoints ====================

@router.get("/user/projects")
async def get_user_projects():
    """Get projects the user works on."""
    ops = GraphOperations()
    projects = ops.get_user_projects()

    return {
        "projects": [
            {
                "name": p.name,
                "weight": w,
                "technologies": [t.name for t in ops.get_project_technologies(p.id)],
            }
            for p, w in projects
        ],
    }


@router.get("/user/technologies")
async def get_user_technologies():
    """Get technologies the user knows."""
    ops = GraphOperations()
    from ...inference.proficiency import ProficiencyInferrer

    techs = ops.get_user_technologies()
    prof_inferrer = ProficiencyInferrer()

    return {
        "technologies": [
            {
                "name": t.name,
                "proficiency": prof,
            }
            for t, prof in techs
        ],
        "expertise_areas": prof_inferrer.get_expertise_areas(),
        "learning_areas": prof_inferrer.get_learning_areas(),
    }


@router.get("/user/preferences")
async def get_user_preferences():
    """Get user preferences."""
    ops = GraphOperations()
    prefs = ops.get_user_preferences()

    from ...inference.preferences import PreferenceInferrer
    pref_inferrer = PreferenceInferrer()

    return {
        "preferences": [
            {"item": p.name, "weight": w}
            for p, w in prefs
        ],
        "strong_preferences": pref_inferrer.get_strong_preferences(),
    }


@router.get("/user/goals")
async def get_user_goals():
    """Get user goals."""
    from ...inference.goals import GoalInferrer

    goal_inferrer = GoalInferrer()
    history = goal_inferrer.get_goal_history()

    return {
        "active": [g.name for g in history["active"]],
        "completed": [g.name for g in history["completed"]],
        "abandoned": [g.name for g in history["abandoned"]],
    }


@router.get("/user/frustrations")
async def get_user_frustrations():
    """Get recent frustrations."""
    ops = GraphOperations()
    frustrations = ops.get_recent_frustrations(limit=10)

    return {
        "frustrations": [
            {
                "name": f.name,
                "context": f.metadata.get("context"),
                "last_activated": f.last_activated_at.isoformat(),
            }
            for f in frustrations
        ],
    }
