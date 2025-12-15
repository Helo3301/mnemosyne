from __future__ import annotations

"""Context retrieval API routes for Mnemosyne."""
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...db.database import get_db
from ...graph.activation import ContextualActivation, SpreadingActivation
from ...graph.decay import DecayManager, compute_relevance
from ...graph.operations import GraphOperations
from ...models.entities import EntityType

logger = logging.getLogger(__name__)

router = APIRouter()


# ==================== Request/Response Models ====================

class ActivationRequest(BaseModel):
    """Request for spreading activation."""
    seed_entities: list[str]
    depth: int = 2
    budget: int = 50


class ContextRequest(BaseModel):
    """Request for contextual retrieval."""
    project: str | None = None
    technologies: list[str] | None = None
    concepts: list[str] | None = None


# ==================== Context Endpoints ====================

@router.get("/project/{project_name}")
async def get_project_context(project_name: str):
    """
    Get context for a specific project.

    Returns:
    - Project details
    - Technologies used
    - Related concepts
    - Recent events
    """
    db = get_db()
    ops = GraphOperations()

    project = db.get_entity_by_name(EntityType.PROJECT, project_name)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project not found: {project_name}")

    # Get technologies
    technologies = ops.get_project_technologies(project.id)

    # Get related concepts via spreading activation
    activator = SpreadingActivation()
    activated = activator.spread([project.id], depth=2, budget=30)
    activated_entities = activator.get_activated_entities(activated)

    related_concepts = [
        {"name": e.name, "strength": s}
        for e, s in activated_entities
        if e.entity_type == EntityType.CONCEPT
    ][:10]

    # Get recent events
    events = []
    for entity, rel in db.get_neighbors(project.id, direction="in"):
        if entity.entity_type == EntityType.EVENT:
            events.append({
                "name": entity.name,
                "when": entity.last_activated_at.isoformat(),
            })
    events = sorted(events, key=lambda x: x["when"], reverse=True)[:5]

    return {
        "project": {
            "name": project.name,
            "confidence": project.confidence,
            "tier": project.tier.value,
        },
        "technologies": [t.name for t in technologies],
        "related_concepts": related_concepts,
        "recent_events": events,
    }


@router.post("/relevant")
async def get_relevant_context(request: ContextRequest):
    """
    Get context relevant to the current conversation.

    Uses contextual activation to find related entities.
    """
    activator = ContextualActivation()

    from ..main import current_session_id
    activated = activator.activate_for_context(
        project_name=request.project,
        technologies=request.technologies,
        concepts=request.concepts,
        session_id=current_session_id,
    )

    spreader = SpreadingActivation()
    entities = spreader.get_activated_entities(activated)

    # Group by type
    by_type = {}
    for entity, strength in entities:
        type_name = entity.entity_type.value
        if type_name not in by_type:
            by_type[type_name] = []
        by_type[type_name].append({
            "name": entity.name,
            "strength": strength,
            "tier": entity.tier.value,
        })

    return {
        "activated_count": len(activated),
        "by_type": by_type,
    }


@router.post("/activate")
async def run_spreading_activation(request: ActivationRequest):
    """
    Run spreading activation from seed entities.

    Returns activated entities with their strengths.
    """
    activator = SpreadingActivation(budget=request.budget)

    from ..main import current_session_id
    activated = activator.spread_from_query(
        request.seed_entities,
        depth=request.depth,
        session_id=current_session_id,
    )

    entities = activator.get_activated_entities(activated)

    return {
        "seed_count": len(request.seed_entities),
        "activated_count": len(activated),
        "entities": [
            {
                "id": e.id,
                "name": e.name,
                "type": e.entity_type.value,
                "strength": strength,
            }
            for e, strength in entities
        ],
    }


# ==================== Decay & Relevance ====================

@router.get("/decay/stats")
async def get_decay_stats():
    """Get decay statistics across all entities."""
    manager = DecayManager()
    return manager.get_decay_stats()


@router.get("/decay/forgotten")
async def get_forgotten_entities():
    """Get entities that have decayed below threshold."""
    manager = DecayManager()
    forgotten = manager.get_forgotten_entities()

    return {
        "count": len(forgotten),
        "entities": [
            {
                "id": e.id,
                "name": e.name,
                "type": e.entity_type.value,
                "tier": e.tier.value,
                "relevance": compute_relevance(e),
            }
            for e in forgotten
        ],
    }


@router.get("/decay/at-risk")
async def get_at_risk_entities(days: int = 7):
    """Get entities that will decay below threshold soon."""
    manager = DecayManager()
    at_risk = manager.get_at_risk_entities(days_ahead=days)

    return {
        "count": len(at_risk),
        "look_ahead_days": days,
        "entities": [
            {
                "id": e.id,
                "name": e.name,
                "type": e.entity_type.value,
                "current_relevance": rel,
            }
            for e, rel in at_risk
        ],
    }


@router.post("/decay/refresh/{entity_id}")
async def refresh_entity(entity_id: int, boost: float = 0.2):
    """Refresh an entity to prevent decay."""
    manager = DecayManager()
    entity = manager.refresh_entity(entity_id, boost=boost)

    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    return {
        "status": "refreshed",
        "entity": {
            "id": entity.id,
            "name": entity.name,
            "confidence": entity.confidence,
            "relevance": compute_relevance(entity),
        },
    }


# ==================== Consolidation ====================

@router.get("/consolidation/stats")
async def get_consolidation_stats():
    """Get consolidation statistics."""
    from ...graph.consolidation import ConsolidationManager
    manager = ConsolidationManager()
    return manager.get_consolidation_stats()


@router.post("/consolidation/run")
async def run_consolidation(auto_promote: bool = True):
    """Run consolidation pass."""
    from ...graph.consolidation import ConsolidationManager
    manager = ConsolidationManager()
    results = manager.run_consolidation(auto_promote=auto_promote)
    return results


@router.post("/consolidation/promote/{entity_id}")
async def promote_entity(entity_id: int, target_tier: str):
    """Manually promote an entity to a new tier."""
    from ...graph.consolidation import ConsolidationManager
    from ...models.entities import Tier

    try:
        tier = Tier(target_tier)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid tier: {target_tier}")

    manager = ConsolidationManager()
    entity = manager.promote_entity(entity_id, tier)

    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    return {
        "status": "promoted",
        "entity": {
            "id": entity.id,
            "name": entity.name,
            "tier": entity.tier.value,
        },
    }


# ==================== Knowledge Integration ====================

@router.get("/knowledge/{concept}")
async def get_knowledge_for_concept(concept: str, top_k: int = 5):
    """
    Get knowledge from HERMES for a concept.

    Returns related papers and concepts.
    """
    from ...integrations.knowledge import KnowledgeBridge

    bridge = KnowledgeBridge()

    try:
        # Check if HERMES is available
        if not await bridge.hermes.health_check():
            return {
                "status": "hermes_unavailable",
                "concept": concept,
            }

        # Get knowledge context
        contexts = await bridge.get_knowledge_context([concept], top_k_per_concept=top_k)

        if not contexts:
            return {
                "status": "no_results",
                "concept": concept,
            }

        ctx = contexts[0]
        return {
            "concept": concept,
            "papers": [
                {
                    "paper_id": p.paper_id,
                    "title": p.title,
                    "score": p.score,
                }
                for p in ctx.papers
            ],
            "related_concepts": ctx.related_concepts,
        }

    finally:
        await bridge.close()


@router.get("/knowledge/suggestions/{technology}")
async def get_learning_suggestions(technology: str):
    """
    Get learning resource suggestions based on proficiency.
    """
    from ...inference.proficiency import ProficiencyInferrer
    from ...integrations.knowledge import KnowledgeBridge

    prof_inferrer = ProficiencyInferrer()
    proficiency = prof_inferrer.get_proficiency(technology)

    bridge = KnowledgeBridge()

    try:
        if not await bridge.hermes.health_check():
            return {
                "status": "hermes_unavailable",
                "technology": technology,
                "proficiency": proficiency,
            }

        resources = await bridge.suggest_learning_resources(technology, proficiency)

        return {
            "technology": technology,
            "proficiency": proficiency,
            "proficiency_level": "expert" if proficiency >= 0.7 else "intermediate" if proficiency >= 0.3 else "beginner",
            "suggestions": [
                {
                    "paper_id": r.paper_id,
                    "title": r.title,
                    "score": r.score,
                }
                for r in resources
            ],
        }

    finally:
        await bridge.close()
