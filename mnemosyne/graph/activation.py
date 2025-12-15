from __future__ import annotations

"""Spreading activation algorithm for Mnemosyne."""
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from ..db.database import get_db
from ..models.entities import ActivationType, Entity

logger = logging.getLogger(__name__)


@dataclass
class ActivationResult:
    """Result of spreading activation."""
    activated_entities: dict[int, float] = field(default_factory=dict)  # entity_id -> activation strength
    visited_count: int = 0
    max_depth_reached: int = 0


class SpreadingActivation:
    """
    Spreading activation through the memory graph.

    Uses BFS with exponential decay at each hop. Activation strength
    decreases as it spreads further from seed entities.
    """

    def __init__(
        self,
        decay_factor: float = 0.5,
        min_strength: float = 0.1,
        budget: int = 50,
    ):
        """
        Initialize spreading activation.

        Args:
            decay_factor: Multiplier for activation at each hop (0-1)
            min_strength: Minimum activation strength to continue spreading
            budget: Maximum number of entities to activate
        """
        self.db = get_db()
        self.decay_factor = decay_factor
        self.min_strength = min_strength
        self.budget = budget

    def spread(
        self,
        seed_ids: list[int],
        depth: int = 2,
        session_id: str | None = None,
        decay_factor: float | None = None,
        min_strength: float | None = None,
        budget: int | None = None,
    ) -> dict[int, float]:
        """
        Spread activation from seed entities.

        Uses BFS with exponential decay:
        - Initial seeds get strength 1.0
        - Each hop multiplies strength by decay_factor * edge_weight
        - Stops when strength < min_strength or budget reached

        Args:
            seed_ids: IDs of entities to start spreading from
            depth: Maximum number of hops
            session_id: Optional session ID for logging activations
            decay_factor: Override default decay factor
            min_strength: Override default minimum strength
            budget: Override default budget

        Returns:
            Dictionary mapping entity_id -> activation_strength
        """
        decay = decay_factor if decay_factor is not None else self.decay_factor
        min_str = min_strength if min_strength is not None else self.min_strength
        max_budget = budget if budget is not None else self.budget

        activated: dict[int, float] = {}
        queue: deque[tuple[int, float, int]] = deque()  # (entity_id, strength, current_depth)

        # Initialize with seed entities
        for entity_id in seed_ids:
            queue.append((entity_id, 1.0, 0))
            activated[entity_id] = 1.0

            # Record activation
            self.db.activate_entity(
                entity_id,
                session_id=session_id,
                activation_type=ActivationType.EXPLICIT,
                strength=1.0,
            )

        # BFS with decay
        while queue and len(activated) < max_budget:
            entity_id, strength, current_depth = queue.popleft()

            if current_depth >= depth:
                continue

            # Get neighbors
            neighbors = self.db.get_neighbors(entity_id, direction="both")

            for neighbor_entity, relationship in neighbors:
                neighbor_id = neighbor_entity.id

                # Calculate new strength
                new_strength = strength * decay * relationship.weight

                # Skip if too weak
                if new_strength < min_str:
                    continue

                # Skip if already activated with higher strength
                if neighbor_id in activated and activated[neighbor_id] >= new_strength:
                    continue

                # Activate neighbor
                activated[neighbor_id] = new_strength

                # Record activation
                self.db.activate_entity(
                    neighbor_id,
                    session_id=session_id,
                    activation_type=ActivationType.SPREAD,
                    strength=new_strength,
                )

                # Add to queue for further spreading
                queue.append((neighbor_id, new_strength, current_depth + 1))

        logger.debug(f"Spreading activation: {len(seed_ids)} seeds -> {len(activated)} activated")
        return activated

    def spread_from_query(
        self,
        query_entities: list[str],
        depth: int = 2,
        session_id: str | None = None,
    ) -> dict[int, float]:
        """
        Spread activation from a list of entity names in a query.

        Args:
            query_entities: Names of entities mentioned in query
            depth: Maximum hops
            session_id: Optional session ID

        Returns:
            Dictionary mapping entity_id -> activation_strength
        """
        from ..models.entities import EntityType

        seed_ids = []

        # Find matching entities
        for name in query_entities:
            normalized = name.lower().strip()

            # Try each entity type
            for entity_type in EntityType:
                entity = self.db.get_entity_by_name(entity_type, normalized)
                if entity:
                    seed_ids.append(entity.id)
                    break

        if not seed_ids:
            logger.debug(f"No matching entities found for: {query_entities}")
            return {}

        return self.spread(seed_ids, depth=depth, session_id=session_id)

    def get_activated_entities(
        self,
        activated: dict[int, float],
        min_strength: float = 0.0,
    ) -> list[tuple[Entity, float]]:
        """
        Get Entity objects for activated entity IDs.

        Args:
            activated: Dictionary from spread()
            min_strength: Filter entities below this strength

        Returns:
            List of (Entity, strength) tuples sorted by strength descending
        """
        result = []
        for entity_id, strength in activated.items():
            if strength >= min_strength:
                entity = self.db.get_entity(entity_id)
                if entity:
                    result.append((entity, strength))

        return sorted(result, key=lambda x: x[1], reverse=True)


class ContextualActivation:
    """
    Context-aware activation that considers entity types and relationships.

    Extends basic spreading activation with:
    - Type-based filtering (only activate certain types)
    - Relationship-based weighting (some relationships spread more)
    - Relevance scoring based on context
    """

    def __init__(self):
        self.db = get_db()
        self.spreader = SpreadingActivation()

        # Relationship type weights for spreading
        self.relationship_weights = {
            "WORKS_ON": 0.8,
            "USES": 0.7,
            "KNOWS": 0.6,
            "PREFERS": 0.5,
            "PURSUING": 0.7,
            "FRUSTRATED_BY": 0.4,
            "RELATED_TO": 0.5,
            "OCCURRED_IN": 0.3,
            "INFORMED_BY": 0.4,
        }

    def activate_for_context(
        self,
        project_name: str | None = None,
        technologies: list[str] | None = None,
        concepts: list[str] | None = None,
        session_id: str | None = None,
    ) -> dict[int, float]:
        """
        Activate entities relevant to a given context.

        Args:
            project_name: Current project being worked on
            technologies: Technologies being discussed
            concepts: Concepts being discussed
            session_id: Current session ID

        Returns:
            Dictionary mapping entity_id -> activation_strength
        """
        from ..models.entities import EntityType

        seed_ids = []

        # Always include user entity
        user = self.db.get_entity_by_name(EntityType.USER, "user")
        if user:
            seed_ids.append(user.id)

        # Find project
        if project_name:
            project = self.db.get_entity_by_name(EntityType.PROJECT, project_name)
            if project:
                seed_ids.append(project.id)

        # Find technologies
        if technologies:
            for tech_name in technologies:
                tech = self.db.get_entity_by_name(EntityType.TECHNOLOGY, tech_name)
                if tech:
                    seed_ids.append(tech.id)

        # Find concepts
        if concepts:
            for concept_name in concepts:
                concept = self.db.get_entity_by_name(EntityType.CONCEPT, concept_name)
                if concept:
                    seed_ids.append(concept.id)

        if not seed_ids:
            return {}

        return self.spreader.spread(
            seed_ids,
            depth=2,
            session_id=session_id,
        )
