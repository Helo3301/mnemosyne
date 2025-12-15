from __future__ import annotations

"""High-level graph operations for Mnemosyne."""
import logging
from typing import Any

from ..db.database import get_db
from ..models.entities import (
    Entity,
    EntityType,
    Relationship,
    RelationshipType,
    Tier,
    ActivationType,
)

logger = logging.getLogger(__name__)


class GraphOperations:
    """High-level operations on the memory graph."""

    def __init__(self):
        self.db = get_db()

    # ==================== Entity Operations ====================

    def get_or_create_entity(
        self,
        entity_type: EntityType,
        name: str,
        confidence: float = 0.5,
        tier: Tier = Tier.EPHEMERAL,
        metadata: dict[str, Any] | None = None,
    ) -> Entity:
        """Get an existing entity or create a new one."""
        existing = self.db.get_entity_by_name(entity_type, name)
        if existing:
            # Activate the existing entity
            self.db.activate_entity(existing.id, activation_type=ActivationType.EXPLICIT)
            return self.db.get_entity(existing.id)

        entity = Entity(
            entity_type=entity_type,
            name=name,
            confidence=confidence,
            tier=tier,
            metadata=metadata or {},
        )
        return self.db.create_entity(entity)

    def get_user_entity(self) -> Entity:
        """Get or create the singleton USER entity."""
        return self.get_or_create_entity(
            EntityType.USER,
            "user",
            confidence=1.0,
            tier=Tier.CORE,
        )

    def record_project(self, name: str, confidence: float = 0.7) -> Entity:
        """Record a project the user works on."""
        project = self.get_or_create_entity(
            EntityType.PROJECT,
            name,
            confidence=confidence,
            tier=Tier.STABLE,
        )

        # Create WORKS_ON relationship from user
        user = self.get_user_entity()
        self.get_or_create_relationship(
            user.id,
            project.id,
            RelationshipType.WORKS_ON,
            weight=0.7,
        )

        return project

    def record_technology(
        self,
        name: str,
        proficiency: float = 0.5,
        project_id: int | None = None,
    ) -> Entity:
        """Record a technology the user knows or a project uses."""
        tech = self.get_or_create_entity(
            EntityType.TECHNOLOGY,
            name,
            confidence=0.8,
            tier=Tier.STABLE,
            metadata={"proficiency": proficiency},
        )

        # Create KNOWS relationship from user
        user = self.get_user_entity()
        self.get_or_create_relationship(
            user.id,
            tech.id,
            RelationshipType.KNOWS,
            weight=proficiency,
            metadata={"proficiency": proficiency},
        )

        # If project specified, create USES relationship
        if project_id:
            self.get_or_create_relationship(
                project_id,
                tech.id,
                RelationshipType.USES,
                weight=0.7,
            )

        return tech

    def record_concept(self, name: str, related_to: list[int] | None = None) -> Entity:
        """Record a concept the user is working with."""
        concept = self.get_or_create_entity(
            EntityType.CONCEPT,
            name,
            confidence=0.6,
            tier=Tier.EPHEMERAL,
        )

        # Create RELATED_TO relationships
        if related_to:
            for other_id in related_to:
                self.get_or_create_relationship(
                    concept.id,
                    other_id,
                    RelationshipType.RELATED_TO,
                    weight=0.5,
                )

        return concept

    def record_preference(self, name: str, weight: float = 0.7) -> Entity:
        """Record a user preference."""
        pref = self.get_or_create_entity(
            EntityType.PREFERENCE,
            name,
            confidence=0.7,
            tier=Tier.STABLE,
        )

        user = self.get_user_entity()
        self.get_or_create_relationship(
            user.id,
            pref.id,
            RelationshipType.PREFERS,
            weight=weight,
        )

        return pref

    def record_goal(self, name: str, active: bool = True) -> Entity:
        """Record a user goal."""
        goal = self.get_or_create_entity(
            EntityType.GOAL,
            name,
            confidence=0.8,
            tier=Tier.STABLE,
            metadata={"active": active},
        )

        user = self.get_user_entity()
        self.get_or_create_relationship(
            user.id,
            goal.id,
            RelationshipType.PURSUING,
            weight=0.8 if active else 0.3,
        )

        return goal

    def record_frustration(self, name: str, context: str | None = None) -> Entity:
        """Record something that frustrated the user."""
        frustration = self.get_or_create_entity(
            EntityType.FRUSTRATION,
            name,
            confidence=0.9,
            tier=Tier.EPHEMERAL,
            metadata={"context": context} if context else {},
        )

        user = self.get_user_entity()
        self.get_or_create_relationship(
            user.id,
            frustration.id,
            RelationshipType.FRUSTRATED_BY,
            weight=0.8,
        )

        return frustration

    def record_event(
        self,
        name: str,
        session_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> Entity:
        """Record a notable event."""
        event = self.get_or_create_entity(
            EntityType.EVENT,
            name,
            confidence=0.9,
            tier=Tier.EPHEMERAL,
            metadata=metadata or {},
        )

        if session_id:
            # Find or create session entity
            session_entity = self.get_or_create_entity(
                EntityType.SESSION,
                session_id,
                confidence=1.0,
                tier=Tier.EPHEMERAL,
            )
            self.get_or_create_relationship(
                event.id,
                session_entity.id,
                RelationshipType.OCCURRED_IN,
                weight=1.0,
            )

        return event

    # ==================== Relationship Operations ====================

    def get_or_create_relationship(
        self,
        source_id: int,
        target_id: int,
        relationship_type: RelationshipType,
        weight: float = 0.5,
        confidence: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> Relationship:
        """Get an existing relationship or create a new one."""
        # Check if exists
        existing = self.db.get_relationships_from(source_id, relationship_type)
        for rel in existing:
            if rel.target_id == target_id:
                return rel

        # Create new
        relationship = Relationship(
            source_id=source_id,
            target_id=target_id,
            relationship_type=relationship_type,
            weight=weight,
            confidence=confidence,
            metadata=metadata or {},
        )
        return self.db.create_relationship(relationship)

    def strengthen_relationship(self, relationship_id: int, amount: float = 0.1) -> Relationship:
        """Strengthen a relationship by increasing its weight."""
        rel = self.db.get_relationship(relationship_id)
        if not rel:
            raise ValueError(f"Relationship {relationship_id} not found")

        rel.weight = min(1.0, rel.weight + amount)
        rel.evidence_count += 1
        return self.db.update_relationship(rel)

    def weaken_relationship(self, relationship_id: int, amount: float = 0.1) -> Relationship:
        """Weaken a relationship by decreasing its weight."""
        rel = self.db.get_relationship(relationship_id)
        if not rel:
            raise ValueError(f"Relationship {relationship_id} not found")

        rel.weight = max(0.0, rel.weight - amount)
        return self.db.update_relationship(rel)

    # ==================== Query Operations ====================

    def get_user_projects(self) -> list[tuple[Entity, float]]:
        """Get all projects the user works on with their weights."""
        user = self.get_user_entity()
        projects = []
        for entity, rel in self.db.get_neighbors(user.id, direction="out"):
            if entity.entity_type == EntityType.PROJECT:
                projects.append((entity, rel.weight))
        return sorted(projects, key=lambda x: x[1], reverse=True)

    def get_user_technologies(self) -> list[tuple[Entity, float]]:
        """Get all technologies the user knows with proficiency."""
        user = self.get_user_entity()
        techs = []
        for entity, rel in self.db.get_neighbors(user.id, direction="out"):
            if entity.entity_type == EntityType.TECHNOLOGY:
                proficiency = rel.metadata.get("proficiency", rel.weight)
                techs.append((entity, proficiency))
        return sorted(techs, key=lambda x: x[1], reverse=True)

    def get_user_preferences(self) -> list[tuple[Entity, float]]:
        """Get all user preferences with their weights."""
        user = self.get_user_entity()
        prefs = []
        for entity, rel in self.db.get_neighbors(user.id, direction="out"):
            if entity.entity_type == EntityType.PREFERENCE:
                prefs.append((entity, rel.weight))
        return sorted(prefs, key=lambda x: x[1], reverse=True)

    def get_active_goals(self) -> list[Entity]:
        """Get user's active goals."""
        user = self.get_user_entity()
        goals = []
        for entity, rel in self.db.get_neighbors(user.id, direction="out"):
            if entity.entity_type == EntityType.GOAL:
                if entity.metadata.get("active", True):
                    goals.append(entity)
        return goals

    def get_recent_frustrations(self, limit: int = 5) -> list[Entity]:
        """Get recent frustrations."""
        user = self.get_user_entity()
        frustrations = []
        for entity, rel in self.db.get_neighbors(user.id, direction="out"):
            if entity.entity_type == EntityType.FRUSTRATION:
                frustrations.append(entity)
        return sorted(frustrations, key=lambda x: x.last_activated_at, reverse=True)[:limit]

    def get_project_technologies(self, project_id: int) -> list[Entity]:
        """Get technologies used by a project."""
        techs = []
        for entity, rel in self.db.get_neighbors(project_id, direction="out"):
            if entity.entity_type == EntityType.TECHNOLOGY:
                techs.append(entity)
        return techs

    def get_related_concepts(self, entity_id: int, max_hops: int = 2) -> list[tuple[Entity, float]]:
        """Get related concepts via graph traversal."""
        from .activation import SpreadingActivation

        activator = SpreadingActivation()
        activated = activator.spread(
            seed_ids=[entity_id],
            depth=max_hops,
            budget=20,
        )

        concepts = []
        for entity_id, strength in activated.items():
            entity = self.db.get_entity(entity_id)
            if entity and entity.entity_type == EntityType.CONCEPT:
                concepts.append((entity, strength))

        return sorted(concepts, key=lambda x: x[1], reverse=True)
