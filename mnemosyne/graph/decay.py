from __future__ import annotations

"""Temporal decay calculations for Mnemosyne."""
import logging
import math
from datetime import datetime, timedelta
from typing import Any

from ..db.database import get_db
from ..models.entities import Entity, Tier

logger = logging.getLogger(__name__)

# Decay rates per day for each tier
DECAY_RATES = {
    Tier.CORE: 0.01,       # Very slow - core knowledge persists (~69 days to half-life)
    Tier.STABLE: 0.03,     # Moderate - stable memories fade slowly (~23 days to half-life)
    Tier.EPHEMERAL: 0.1,   # Fast - ephemeral memories decay quickly (~7 days to half-life)
}


def compute_relevance(
    entity: Entity,
    current_time: datetime | None = None,
) -> float:
    """
    Compute current relevance of an entity based on temporal decay.

    Uses exponential decay: relevance = confidence × e^(-λ × days)

    Args:
        entity: The entity to compute relevance for
        current_time: Current time (defaults to now)

    Returns:
        Current relevance score (0-1)
    """
    if current_time is None:
        current_time = datetime.now()

    days_since_activation = (current_time - entity.last_activated_at).total_seconds() / 86400
    decay_rate = DECAY_RATES.get(entity.tier, DECAY_RATES[Tier.EPHEMERAL])

    relevance = entity.confidence * math.exp(-decay_rate * days_since_activation)
    return max(0.0, min(1.0, relevance))


def compute_half_life(tier: Tier) -> float:
    """
    Compute the half-life (in days) for a given tier.

    Half-life is when relevance = 0.5 × initial_relevance
    For e^(-λt) = 0.5, t = ln(2) / λ

    Args:
        tier: Memory tier

    Returns:
        Half-life in days
    """
    decay_rate = DECAY_RATES.get(tier, DECAY_RATES[Tier.EPHEMERAL])
    return math.log(2) / decay_rate


def get_decay_threshold_date(
    tier: Tier,
    threshold: float = 0.1,
    initial_confidence: float = 1.0,
) -> timedelta:
    """
    Calculate how long until an entity decays below a threshold.

    Args:
        tier: Memory tier
        threshold: Relevance threshold (default 0.1)
        initial_confidence: Starting confidence

    Returns:
        Timedelta until threshold reached
    """
    decay_rate = DECAY_RATES.get(tier, DECAY_RATES[Tier.EPHEMERAL])

    # Solve: threshold = initial_confidence × e^(-λ × days)
    # days = -ln(threshold / initial_confidence) / λ
    days = -math.log(threshold / initial_confidence) / decay_rate
    return timedelta(days=days)


class DecayManager:
    """Manages temporal decay across all entities."""

    def __init__(self, threshold: float = 0.05):
        """
        Initialize decay manager.

        Args:
            threshold: Minimum relevance before entity is considered "forgotten"
        """
        self.db = get_db()
        self.threshold = threshold

    def get_current_relevances(self) -> dict[int, float]:
        """
        Get current relevance scores for all entities.

        Returns:
            Dictionary mapping entity_id -> current_relevance
        """
        relevances = {}
        current_time = datetime.now()

        with self.db.connection() as conn:
            cursor = conn.execute("SELECT * FROM entities")
            for row in cursor.fetchall():
                entity = self.db._row_to_entity(row)
                relevances[entity.id] = compute_relevance(entity, current_time)

        return relevances

    def get_forgotten_entities(self) -> list[Entity]:
        """
        Get entities that have decayed below the threshold.

        Returns:
            List of entities with relevance below threshold
        """
        forgotten = []
        current_time = datetime.now()

        with self.db.connection() as conn:
            cursor = conn.execute("SELECT * FROM entities WHERE tier = 'EPHEMERAL'")
            for row in cursor.fetchall():
                entity = self.db._row_to_entity(row)
                if compute_relevance(entity, current_time) < self.threshold:
                    forgotten.append(entity)

        return forgotten

    def get_at_risk_entities(self, days_ahead: int = 7) -> list[tuple[Entity, float]]:
        """
        Get entities that will decay below threshold soon.

        Args:
            days_ahead: Look-ahead window in days

        Returns:
            List of (entity, current_relevance) that will decay below threshold
        """
        at_risk = []
        current_time = datetime.now()
        future_time = current_time + timedelta(days=days_ahead)

        with self.db.connection() as conn:
            cursor = conn.execute("SELECT * FROM entities")
            for row in cursor.fetchall():
                entity = self.db._row_to_entity(row)
                current_rel = compute_relevance(entity, current_time)
                future_rel = compute_relevance(entity, future_time)

                if current_rel >= self.threshold and future_rel < self.threshold:
                    at_risk.append((entity, current_rel))

        return sorted(at_risk, key=lambda x: x[1])

    def cleanup_forgotten(self, dry_run: bool = True) -> list[Entity]:
        """
        Remove forgotten entities from the database.

        Args:
            dry_run: If True, don't actually delete, just report

        Returns:
            List of entities that were/would be deleted
        """
        forgotten = self.get_forgotten_entities()

        if not dry_run:
            for entity in forgotten:
                self.db.delete_entity(entity.id)
                logger.info(f"Deleted forgotten entity: {entity.name} ({entity.entity_type.value})")

        return forgotten

    def refresh_entity(self, entity_id: int, boost: float = 0.2) -> Entity | None:
        """
        Refresh an entity by boosting its confidence and updating activation time.

        Args:
            entity_id: ID of entity to refresh
            boost: Amount to boost confidence (capped at 1.0)

        Returns:
            Updated entity or None if not found
        """
        entity = self.db.get_entity(entity_id)
        if not entity:
            return None

        entity.confidence = min(1.0, entity.confidence + boost)
        entity.last_activated_at = datetime.now()
        entity.activation_count += 1

        return self.db.update_entity(entity)

    def get_decay_stats(self) -> dict[str, Any]:
        """
        Get statistics about entity decay across the system.

        Returns:
            Dictionary with decay statistics
        """
        current_time = datetime.now()
        stats = {
            "by_tier": {},
            "total_entities": 0,
            "forgotten_count": 0,
            "at_risk_count": 0,
            "average_relevance": 0.0,
        }

        relevances = []

        for tier in Tier:
            entities = self.db.get_entities_by_tier(tier)
            tier_relevances = [compute_relevance(e, current_time) for e in entities]

            stats["by_tier"][tier.value] = {
                "count": len(entities),
                "avg_relevance": sum(tier_relevances) / len(tier_relevances) if tier_relevances else 0,
                "half_life_days": compute_half_life(tier),
            }
            relevances.extend(tier_relevances)

        stats["total_entities"] = len(relevances)
        stats["average_relevance"] = sum(relevances) / len(relevances) if relevances else 0
        stats["forgotten_count"] = len(self.get_forgotten_entities())
        stats["at_risk_count"] = len(self.get_at_risk_entities())

        return stats
