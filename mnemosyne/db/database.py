from __future__ import annotations

"""Database connection and operations for Mnemosyne."""
import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Generator, Optional, List, Dict, Tuple

from ..models.entities import (
    Activation,
    ActivationType,
    Entity,
    EntityType,
    Feedback,
    FeedbackType,
    Relationship,
    RelationshipType,
    Session,
    Tier,
)

logger = logging.getLogger(__name__)

# Module-level database instance
_db_instance: Optional["Database"] = None


def get_db() -> "Database":
    """Get the global database instance."""
    global _db_instance
    if _db_instance is None:
        raise RuntimeError("Database not initialized. Call Database.initialize() first.")
    return _db_instance


class Database:
    """SQLite database for Mnemosyne memory graph."""

    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @classmethod
    def initialize(cls, db_path) -> "Database":
        """Initialize the global database instance."""
        global _db_instance
        _db_instance = cls(db_path)
        return _db_instance

    def _init_schema(self) -> None:
        """Initialize database schema."""
        schema_path = Path(__file__).parent / "schema.sql"
        with open(schema_path) as f:
            schema = f.read()

        with self.connection() as conn:
            conn.executescript(schema)
            conn.commit()
        logger.info(f"Database initialized at {self.db_path}")

    @contextmanager
    def connection(self) -> Generator[sqlite3.Connection, None, None]:
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    # ==================== Entity Operations ====================

    def create_entity(self, entity: Entity) -> Entity:
        """Create a new entity."""
        with self.connection() as conn:
            # First try to insert
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO entities (entity_type, name, normalized_name, tier, confidence, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    entity.entity_type.value,
                    entity.name,
                    entity.normalized_name,
                    entity.tier.value,
                    entity.confidence,
                    json.dumps(entity.metadata) if entity.metadata else None,
                ),
            )

            if cursor.rowcount == 0:
                # Entity already exists, update it
                conn.execute(
                    """
                    UPDATE entities SET
                        confidence = MAX(confidence, ?),
                        activation_count = activation_count + 1,
                        last_activated_at = CURRENT_TIMESTAMP
                    WHERE entity_type = ? AND normalized_name = ?
                    """,
                    (entity.confidence, entity.entity_type.value, entity.normalized_name),
                )

            conn.commit()

            # Fetch the result
            cursor = conn.execute(
                "SELECT * FROM entities WHERE entity_type = ? AND normalized_name = ?",
                (entity.entity_type.value, entity.normalized_name),
            )
            row = cursor.fetchone()
            return self._row_to_entity(row)

    def get_entity(self, entity_id: int) -> Optional[Entity]:
        """Get an entity by ID."""
        with self.connection() as conn:
            cursor = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,))
            row = cursor.fetchone()
            return self._row_to_entity(row) if row else None

    def get_entity_by_name(
        self, entity_type: EntityType, name: str
    ) -> Optional[Entity]:
        """Get an entity by type and normalized name."""
        normalized = name.lower().strip()
        with self.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM entities WHERE entity_type = ? AND normalized_name = ?",
                (entity_type.value, normalized),
            )
            row = cursor.fetchone()
            return self._row_to_entity(row) if row else None

    def get_entities_by_type(self, entity_type: EntityType) -> List[Entity]:
        """Get all entities of a given type."""
        with self.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM entities WHERE entity_type = ? ORDER BY last_activated_at DESC",
                (entity_type.value,),
            )
            return [self._row_to_entity(row) for row in cursor.fetchall()]

    def get_entities_by_tier(self, tier: Tier) -> List[Entity]:
        """Get all entities in a given tier."""
        with self.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM entities WHERE tier = ? ORDER BY last_activated_at DESC",
                (tier.value,),
            )
            return [self._row_to_entity(row) for row in cursor.fetchall()]

    def update_entity(self, entity: Entity) -> Entity:
        """Update an existing entity."""
        if entity.id is None:
            raise ValueError("Entity must have an ID to update")

        with self.connection() as conn:
            conn.execute(
                """
                UPDATE entities SET
                    entity_type = ?,
                    name = ?,
                    normalized_name = ?,
                    tier = ?,
                    confidence = ?,
                    last_activated_at = ?,
                    activation_count = ?,
                    metadata = ?
                WHERE id = ?
                """,
                (
                    entity.entity_type.value,
                    entity.name,
                    entity.normalized_name,
                    entity.tier.value,
                    entity.confidence,
                    entity.last_activated_at.isoformat(),
                    entity.activation_count,
                    json.dumps(entity.metadata) if entity.metadata else None,
                    entity.id,
                ),
            )
            conn.commit()

            # Fetch updated
            cursor = conn.execute("SELECT * FROM entities WHERE id = ?", (entity.id,))
            row = cursor.fetchone()
            return self._row_to_entity(row)

    def activate_entity(
        self,
        entity_id: int,
        session_id: Optional[str] = None,
        activation_type: ActivationType = ActivationType.EXPLICIT,
        strength: float = 1.0,
    ) -> Optional[Entity]:
        """Activate an entity and record the activation."""
        with self.connection() as conn:
            # Update entity
            conn.execute(
                """
                UPDATE entities SET
                    last_activated_at = CURRENT_TIMESTAMP,
                    activation_count = activation_count + 1
                WHERE id = ?
                """,
                (entity_id,),
            )

            # Record activation
            conn.execute(
                """
                INSERT INTO activations (entity_id, session_id, activation_type, activation_strength)
                VALUES (?, ?, ?, ?)
                """,
                (entity_id, session_id, activation_type.value, strength),
            )

            conn.commit()

            # Return updated entity
            cursor = conn.execute("SELECT * FROM entities WHERE id = ?", (entity_id,))
            row = cursor.fetchone()
            return self._row_to_entity(row) if row else None

    def delete_entity(self, entity_id: int) -> bool:
        """Delete an entity (cascades to relationships and activations)."""
        with self.connection() as conn:
            cursor = conn.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
            conn.commit()
            return cursor.rowcount > 0

    def _row_to_entity(self, row: sqlite3.Row) -> Entity:
        """Convert a database row to an Entity."""
        return Entity(
            id=row["id"],
            entity_type=EntityType(row["entity_type"]),
            name=row["name"],
            normalized_name=row["normalized_name"],
            tier=Tier(row["tier"]),
            confidence=row["confidence"],
            created_at=datetime.fromisoformat(row["created_at"]),
            last_activated_at=datetime.fromisoformat(row["last_activated_at"]),
            activation_count=row["activation_count"],
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    # ==================== Relationship Operations ====================

    def create_relationship(self, relationship: Relationship) -> Relationship:
        """Create a new relationship."""
        with self.connection() as conn:
            # Try to insert
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO relationships (source_id, target_id, relationship_type, weight, confidence, metadata)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    relationship.source_id,
                    relationship.target_id,
                    relationship.relationship_type.value,
                    relationship.weight,
                    relationship.confidence,
                    json.dumps(relationship.metadata) if relationship.metadata else None,
                ),
            )

            if cursor.rowcount == 0:
                # Relationship already exists, update it
                conn.execute(
                    """
                    UPDATE relationships SET
                        weight = MIN(1.0, weight + 0.1),
                        confidence = MAX(confidence, ?),
                        evidence_count = evidence_count + 1,
                        last_strengthened_at = CURRENT_TIMESTAMP
                    WHERE source_id = ? AND target_id = ? AND relationship_type = ?
                    """,
                    (
                        relationship.confidence,
                        relationship.source_id,
                        relationship.target_id,
                        relationship.relationship_type.value,
                    ),
                )

            conn.commit()

            # Fetch result
            cursor = conn.execute(
                "SELECT * FROM relationships WHERE source_id = ? AND target_id = ? AND relationship_type = ?",
                (relationship.source_id, relationship.target_id, relationship.relationship_type.value),
            )
            row = cursor.fetchone()
            return self._row_to_relationship(row)

    def get_relationship(self, relationship_id: int) -> Optional[Relationship]:
        """Get a relationship by ID."""
        with self.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM relationships WHERE id = ?", (relationship_id,)
            )
            row = cursor.fetchone()
            return self._row_to_relationship(row) if row else None

    def get_relationships_from(
        self,
        entity_id: int,
        relationship_type: Optional[RelationshipType] = None,
    ) -> List[Relationship]:
        """Get all relationships from an entity."""
        with self.connection() as conn:
            if relationship_type:
                cursor = conn.execute(
                    "SELECT * FROM relationships WHERE source_id = ? AND relationship_type = ?",
                    (entity_id, relationship_type.value),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM relationships WHERE source_id = ?", (entity_id,)
                )
            return [self._row_to_relationship(row) for row in cursor.fetchall()]

    def get_relationships_to(
        self,
        entity_id: int,
        relationship_type: Optional[RelationshipType] = None,
    ) -> List[Relationship]:
        """Get all relationships to an entity."""
        with self.connection() as conn:
            if relationship_type:
                cursor = conn.execute(
                    "SELECT * FROM relationships WHERE target_id = ? AND relationship_type = ?",
                    (entity_id, relationship_type.value),
                )
            else:
                cursor = conn.execute(
                    "SELECT * FROM relationships WHERE target_id = ?", (entity_id,)
                )
            return [self._row_to_relationship(row) for row in cursor.fetchall()]

    def get_neighbors(
        self,
        entity_id: int,
        direction: str = "both",
    ) -> List[Tuple[Entity, Relationship]]:
        """Get neighboring entities with their relationships."""
        neighbors = []
        with self.connection() as conn:
            if direction in ("out", "both"):
                cursor = conn.execute(
                    """
                    SELECT e.*, r.id as rel_id, r.source_id, r.target_id, r.relationship_type,
                           r.weight, r.confidence as rel_confidence, r.evidence_count,
                           r.created_at as rel_created_at, r.last_strengthened_at, r.metadata as rel_metadata
                    FROM relationships r
                    JOIN entities e ON r.target_id = e.id
                    WHERE r.source_id = ?
                    """,
                    (entity_id,),
                )
                for row in cursor.fetchall():
                    entity = self._row_to_entity(row)
                    rel = Relationship(
                        id=row["rel_id"],
                        source_id=row["source_id"],
                        target_id=row["target_id"],
                        relationship_type=RelationshipType(row["relationship_type"]),
                        weight=row["weight"],
                        confidence=row["rel_confidence"],
                        evidence_count=row["evidence_count"],
                        created_at=datetime.fromisoformat(row["rel_created_at"]),
                        last_strengthened_at=datetime.fromisoformat(row["last_strengthened_at"]),
                        metadata=json.loads(row["rel_metadata"]) if row["rel_metadata"] else {},
                    )
                    neighbors.append((entity, rel))

            if direction in ("in", "both"):
                cursor = conn.execute(
                    """
                    SELECT e.*, r.id as rel_id, r.source_id, r.target_id, r.relationship_type,
                           r.weight, r.confidence as rel_confidence, r.evidence_count,
                           r.created_at as rel_created_at, r.last_strengthened_at, r.metadata as rel_metadata
                    FROM relationships r
                    JOIN entities e ON r.source_id = e.id
                    WHERE r.target_id = ?
                    """,
                    (entity_id,),
                )
                for row in cursor.fetchall():
                    entity = self._row_to_entity(row)
                    rel = Relationship(
                        id=row["rel_id"],
                        source_id=row["source_id"],
                        target_id=row["target_id"],
                        relationship_type=RelationshipType(row["relationship_type"]),
                        weight=row["weight"],
                        confidence=row["rel_confidence"],
                        evidence_count=row["evidence_count"],
                        created_at=datetime.fromisoformat(row["rel_created_at"]),
                        last_strengthened_at=datetime.fromisoformat(row["last_strengthened_at"]),
                        metadata=json.loads(row["rel_metadata"]) if row["rel_metadata"] else {},
                    )
                    neighbors.append((entity, rel))

        return neighbors

    def update_relationship(self, relationship: Relationship) -> Relationship:
        """Update an existing relationship."""
        if relationship.id is None:
            raise ValueError("Relationship must have an ID to update")

        with self.connection() as conn:
            conn.execute(
                """
                UPDATE relationships SET
                    weight = ?,
                    confidence = ?,
                    evidence_count = ?,
                    last_strengthened_at = ?,
                    metadata = ?
                WHERE id = ?
                """,
                (
                    relationship.weight,
                    relationship.confidence,
                    relationship.evidence_count,
                    relationship.last_strengthened_at.isoformat(),
                    json.dumps(relationship.metadata) if relationship.metadata else None,
                    relationship.id,
                ),
            )
            conn.commit()

            # Fetch updated
            cursor = conn.execute("SELECT * FROM relationships WHERE id = ?", (relationship.id,))
            row = cursor.fetchone()
            return self._row_to_relationship(row)

    def delete_relationship(self, relationship_id: int) -> bool:
        """Delete a relationship."""
        with self.connection() as conn:
            cursor = conn.execute(
                "DELETE FROM relationships WHERE id = ?", (relationship_id,)
            )
            conn.commit()
            return cursor.rowcount > 0

    def _row_to_relationship(self, row: sqlite3.Row) -> Relationship:
        """Convert a database row to a Relationship."""
        return Relationship(
            id=row["id"],
            source_id=row["source_id"],
            target_id=row["target_id"],
            relationship_type=RelationshipType(row["relationship_type"]),
            weight=row["weight"],
            confidence=row["confidence"],
            evidence_count=row["evidence_count"],
            created_at=datetime.fromisoformat(row["created_at"]),
            last_strengthened_at=datetime.fromisoformat(row["last_strengthened_at"]),
            metadata=json.loads(row["metadata"]) if row["metadata"] else {},
        )

    # ==================== Session Operations ====================

    def create_session(self, session: Session) -> Session:
        """Create a new session."""
        with self.connection() as conn:
            conn.execute(
                """
                INSERT INTO sessions (id, started_at, project_context)
                VALUES (?, ?, ?)
                """,
                (session.id, session.started_at.isoformat(), session.project_context),
            )
            conn.commit()
            return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID."""
        with self.connection() as conn:
            cursor = conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
            row = cursor.fetchone()
            if not row:
                return None
            return Session(
                id=row["id"],
                started_at=datetime.fromisoformat(row["started_at"]),
                ended_at=datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None,
                project_context=row["project_context"],
                summary=row["summary"],
            )

    def end_session(self, session_id: str, summary: Optional[str] = None) -> Optional[Session]:
        """End a session and optionally add a summary."""
        with self.connection() as conn:
            conn.execute(
                """
                UPDATE sessions SET
                    ended_at = CURRENT_TIMESTAMP,
                    summary = ?
                WHERE id = ?
                """,
                (summary, session_id),
            )
            conn.commit()
            return self.get_session(session_id)

    def get_recent_sessions(self, limit: int = 10) -> List[Session]:
        """Get recent sessions."""
        with self.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM sessions ORDER BY started_at DESC LIMIT ?", (limit,)
            )
            sessions = []
            for row in cursor.fetchall():
                sessions.append(
                    Session(
                        id=row["id"],
                        started_at=datetime.fromisoformat(row["started_at"]),
                        ended_at=datetime.fromisoformat(row["ended_at"]) if row["ended_at"] else None,
                        project_context=row["project_context"],
                        summary=row["summary"],
                    )
                )
            return sessions

    # ==================== Feedback Operations ====================

    def record_feedback(self, feedback: Feedback) -> Feedback:
        """Record a feedback signal."""
        with self.connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO feedback (session_id, entity_id, signal_type, signal_text)
                VALUES (?, ?, ?, ?)
                """,
                (
                    feedback.session_id,
                    feedback.entity_id,
                    feedback.signal_type.value,
                    feedback.signal_text,
                ),
            )
            feedback_id = cursor.lastrowid
            conn.commit()

            # Fetch result
            cursor = conn.execute("SELECT * FROM feedback WHERE id = ?", (feedback_id,))
            row = cursor.fetchone()
            return Feedback(
                id=row["id"],
                session_id=row["session_id"],
                entity_id=row["entity_id"],
                signal_type=FeedbackType(row["signal_type"]),
                signal_text=row["signal_text"],
                captured_at=datetime.fromisoformat(row["captured_at"]),
            )

    def get_feedback_for_entity(self, entity_id: int) -> List[Feedback]:
        """Get all feedback for an entity."""
        with self.connection() as conn:
            cursor = conn.execute(
                "SELECT * FROM feedback WHERE entity_id = ? ORDER BY captured_at DESC",
                (entity_id,),
            )
            feedbacks = []
            for row in cursor.fetchall():
                feedbacks.append(
                    Feedback(
                        id=row["id"],
                        session_id=row["session_id"],
                        entity_id=row["entity_id"],
                        signal_type=FeedbackType(row["signal_type"]),
                        signal_text=row["signal_text"],
                        captured_at=datetime.fromisoformat(row["captured_at"]),
                    )
                )
            return feedbacks

    # ==================== Activation Queries ====================

    def get_activation_count(self, entity_id: int, days: int = 14) -> int:
        """Get activation count for an entity in the last N days."""
        with self.connection() as conn:
            cursor = conn.execute(
                """
                SELECT COUNT(*) as count FROM activations
                WHERE entity_id = ? AND activated_at >= datetime('now', ?)
                """,
                (entity_id, f"-{days} days"),
            )
            row = cursor.fetchone()
            return row["count"] if row else 0

    def get_entities_for_consolidation(self) -> List[Entity]:
        """Get ephemeral entities that may be ready for consolidation."""
        with self.connection() as conn:
            cursor = conn.execute(
                """
                SELECT e.* FROM entities e
                JOIN recent_activations ra ON e.id = ra.entity_id
                WHERE e.tier = 'EPHEMERAL' AND ra.activation_count_14d >= 5
                """
            )
            return [self._row_to_entity(row) for row in cursor.fetchall()]

    # ==================== Stats and Queries ====================

    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        with self.connection() as conn:
            stats = {}

            # Entity counts by type
            cursor = conn.execute(
                "SELECT entity_type, COUNT(*) as count FROM entities GROUP BY entity_type"
            )
            stats["entities_by_type"] = {row["entity_type"]: row["count"] for row in cursor.fetchall()}

            # Entity counts by tier
            cursor = conn.execute(
                "SELECT tier, COUNT(*) as count FROM entities GROUP BY tier"
            )
            stats["entities_by_tier"] = {row["tier"]: row["count"] for row in cursor.fetchall()}

            # Relationship counts by type
            cursor = conn.execute(
                "SELECT relationship_type, COUNT(*) as count FROM relationships GROUP BY relationship_type"
            )
            stats["relationships_by_type"] = {row["relationship_type"]: row["count"] for row in cursor.fetchall()}

            # Total counts
            cursor = conn.execute("SELECT COUNT(*) as count FROM entities")
            stats["total_entities"] = cursor.fetchone()["count"]

            cursor = conn.execute("SELECT COUNT(*) as count FROM relationships")
            stats["total_relationships"] = cursor.fetchone()["count"]

            cursor = conn.execute("SELECT COUNT(*) as count FROM sessions")
            stats["total_sessions"] = cursor.fetchone()["count"]

            cursor = conn.execute("SELECT COUNT(*) as count FROM activations")
            stats["total_activations"] = cursor.fetchone()["count"]

            return stats
