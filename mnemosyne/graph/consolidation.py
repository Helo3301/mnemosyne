from __future__ import annotations

"""Memory consolidation for Mnemosyne - tier promotion logic."""
import logging
from datetime import datetime
from typing import Any

from ..db.database import get_db
from ..models.entities import Entity, Tier

logger = logging.getLogger(__name__)

# Consolidation thresholds
EPHEMERAL_TO_STABLE_ACTIVATIONS = 5  # Activations in window to promote
EPHEMERAL_TO_STABLE_DAYS = 14         # Window for counting activations
STABLE_TO_CORE_ACTIVATIONS = 20       # Higher bar for core promotion
STABLE_TO_CORE_DAYS = 30              # Longer window for core


class ConsolidationManager:
    """
    Manages memory consolidation - promoting entities between tiers.

    Consolidation rules:
    - EPHEMERAL → STABLE: 5+ activations in 14 days
    - STABLE → CORE: 20+ activations in 30 days (manual review recommended)
    - CORE entities are never auto-demoted (but can be manually)
    """

    def __init__(self):
        self.db = get_db()

    def check_entity_for_promotion(self, entity: Entity) -> Tier | None:
        """
        Check if an entity qualifies for promotion.

        Args:
            entity: Entity to check

        Returns:
            New tier if promotion warranted, None otherwise
        """
        if entity.tier == Tier.CORE:
            # Core entities cannot be promoted further
            return None

        if entity.tier == Tier.EPHEMERAL:
            # Check for EPHEMERAL → STABLE
            activation_count = self.db.get_activation_count(
                entity.id,
                days=EPHEMERAL_TO_STABLE_DAYS
            )
            if activation_count >= EPHEMERAL_TO_STABLE_ACTIVATIONS:
                logger.info(
                    f"Entity '{entity.name}' qualifies for EPHEMERAL → STABLE "
                    f"({activation_count} activations in {EPHEMERAL_TO_STABLE_DAYS} days)"
                )
                return Tier.STABLE

        if entity.tier == Tier.STABLE:
            # Check for STABLE → CORE
            activation_count = self.db.get_activation_count(
                entity.id,
                days=STABLE_TO_CORE_DAYS
            )
            if activation_count >= STABLE_TO_CORE_ACTIVATIONS:
                logger.info(
                    f"Entity '{entity.name}' qualifies for STABLE → CORE "
                    f"({activation_count} activations in {STABLE_TO_CORE_DAYS} days)"
                )
                return Tier.CORE

        return None

    def promote_entity(self, entity_id: int, new_tier: Tier) -> Entity | None:
        """
        Promote an entity to a new tier.

        Args:
            entity_id: ID of entity to promote
            new_tier: Tier to promote to

        Returns:
            Updated entity or None if not found
        """
        entity = self.db.get_entity(entity_id)
        if not entity:
            return None

        old_tier = entity.tier
        entity.tier = new_tier

        # Boost confidence on promotion
        if new_tier == Tier.STABLE:
            entity.confidence = max(entity.confidence, 0.7)
        elif new_tier == Tier.CORE:
            entity.confidence = max(entity.confidence, 0.9)

        updated = self.db.update_entity(entity)
        logger.info(f"Promoted entity '{entity.name}' from {old_tier.value} to {new_tier.value}")

        return updated

    def demote_entity(self, entity_id: int, new_tier: Tier) -> Entity | None:
        """
        Demote an entity to a lower tier.

        Args:
            entity_id: ID of entity to demote
            new_tier: Tier to demote to

        Returns:
            Updated entity or None if not found
        """
        entity = self.db.get_entity(entity_id)
        if not entity:
            return None

        old_tier = entity.tier
        entity.tier = new_tier

        updated = self.db.update_entity(entity)
        logger.info(f"Demoted entity '{entity.name}' from {old_tier.value} to {new_tier.value}")

        return updated

    def run_consolidation(self, auto_promote: bool = True) -> dict[str, Any]:
        """
        Run consolidation pass across all entities.

        Args:
            auto_promote: If True, automatically promote qualifying entities.
                         If False, just report what would be promoted.

        Returns:
            Dictionary with consolidation results
        """
        results = {
            "checked": 0,
            "promoted": [],
            "candidates_stable_to_core": [],  # Manual review recommended
        }

        # Get entities that might be ready for consolidation
        candidates = self.db.get_entities_for_consolidation()
        results["checked"] = len(candidates)

        for entity in candidates:
            new_tier = self.check_entity_for_promotion(entity)
            if new_tier:
                if new_tier == Tier.STABLE:
                    if auto_promote:
                        self.promote_entity(entity.id, new_tier)
                        results["promoted"].append({
                            "entity": entity.name,
                            "type": entity.entity_type.value,
                            "old_tier": entity.tier.value,
                            "new_tier": new_tier.value,
                        })
                    else:
                        results["promoted"].append({
                            "entity": entity.name,
                            "type": entity.entity_type.value,
                            "old_tier": entity.tier.value,
                            "new_tier": new_tier.value,
                            "status": "candidate",
                        })
                elif new_tier == Tier.CORE:
                    # Core promotion always requires manual review
                    results["candidates_stable_to_core"].append({
                        "entity": entity.name,
                        "type": entity.entity_type.value,
                        "activation_count": self.db.get_activation_count(entity.id, days=30),
                    })

        # Also check stable entities for core promotion
        stable_entities = self.db.get_entities_by_tier(Tier.STABLE)
        for entity in stable_entities:
            new_tier = self.check_entity_for_promotion(entity)
            if new_tier == Tier.CORE:
                results["candidates_stable_to_core"].append({
                    "entity": entity.name,
                    "type": entity.entity_type.value,
                    "activation_count": self.db.get_activation_count(entity.id, days=30),
                })

        return results

    def get_consolidation_stats(self) -> dict[str, Any]:
        """
        Get statistics about consolidation status.

        Returns:
            Dictionary with consolidation statistics
        """
        stats = {
            "by_tier": {},
            "promotion_candidates": {
                "ephemeral_to_stable": 0,
                "stable_to_core": 0,
            },
        }

        for tier in Tier:
            entities = self.db.get_entities_by_tier(tier)
            stats["by_tier"][tier.value] = len(entities)

        # Count promotion candidates
        ephemeral_entities = self.db.get_entities_by_tier(Tier.EPHEMERAL)
        for entity in ephemeral_entities:
            if self.check_entity_for_promotion(entity) == Tier.STABLE:
                stats["promotion_candidates"]["ephemeral_to_stable"] += 1

        stable_entities = self.db.get_entities_by_tier(Tier.STABLE)
        for entity in stable_entities:
            if self.check_entity_for_promotion(entity) == Tier.CORE:
                stats["promotion_candidates"]["stable_to_core"] += 1

        return stats


def run_end_of_session_consolidation(session_id: str | None = None) -> dict[str, Any]:
    """
    Run consolidation at the end of a session.

    This is the main entry point for session-end consolidation.

    Args:
        session_id: Optional session ID for logging

    Returns:
        Consolidation results
    """
    manager = ConsolidationManager()
    results = manager.run_consolidation(auto_promote=True)

    if session_id:
        logger.info(f"Session {session_id} consolidation: {len(results['promoted'])} promotions")

    return results
