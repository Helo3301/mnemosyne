"""Tests for temporal decay."""
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from mnemosyne.db.database import Database
from mnemosyne.graph.decay import (
    compute_relevance,
    compute_half_life,
    DecayManager,
    DECAY_RATES,
)
from mnemosyne.graph.operations import GraphOperations
from mnemosyne.models.entities import Entity, EntityType, Tier


class TestTemporalDecay(unittest.TestCase):
    """Test temporal decay calculations."""

    def test_compute_relevance_no_decay(self):
        """Test relevance with no time elapsed."""
        now = datetime.now()
        entity = Entity(
            id=1,
            entity_type=EntityType.CONCEPT,
            name="test",
            tier=Tier.STABLE,
            confidence=1.0,
            last_activated_at=now,
        )

        relevance = compute_relevance(entity, now)
        self.assertAlmostEqual(relevance, 1.0, places=5)

    def test_compute_relevance_with_decay(self):
        """Test relevance decay over time."""
        now = datetime.now()
        past = now - timedelta(days=7)

        entity = Entity(
            id=1,
            entity_type=EntityType.CONCEPT,
            name="test",
            tier=Tier.EPHEMERAL,  # Fast decay
            confidence=1.0,
            last_activated_at=past,
        )

        relevance = compute_relevance(entity, now)

        # With EPHEMERAL decay rate (0.1) and 7 days:
        # expected = 1.0 * e^(-0.1 * 7) = e^(-0.7) ≈ 0.497
        self.assertLess(relevance, 0.6)
        self.assertGreater(relevance, 0.4)

    def test_tier_decay_rates(self):
        """Test that different tiers decay at different rates."""
        now = datetime.now()
        past = now - timedelta(days=30)

        entities = []
        for tier in [Tier.CORE, Tier.STABLE, Tier.EPHEMERAL]:
            entity = Entity(
                id=1,
                entity_type=EntityType.CONCEPT,
                name="test",
                tier=tier,
                confidence=1.0,
                last_activated_at=past,
            )
            entities.append((tier, compute_relevance(entity, now)))

        # CORE should have highest relevance (slowest decay)
        # EPHEMERAL should have lowest relevance (fastest decay)
        self.assertGreater(entities[0][1], entities[1][1])  # CORE > STABLE
        self.assertGreater(entities[1][1], entities[2][1])  # STABLE > EPHEMERAL

    def test_compute_half_life(self):
        """Test half-life calculation."""
        # Half-life = ln(2) / λ
        core_half_life = compute_half_life(Tier.CORE)
        stable_half_life = compute_half_life(Tier.STABLE)
        ephemeral_half_life = compute_half_life(Tier.EPHEMERAL)

        # CORE should have longest half-life
        self.assertGreater(core_half_life, stable_half_life)
        self.assertGreater(stable_half_life, ephemeral_half_life)

        # Check approximate values
        # CORE: ln(2) / 0.01 ≈ 69 days
        self.assertAlmostEqual(core_half_life, 69.3, places=0)

        # EPHEMERAL: ln(2) / 0.1 ≈ 6.9 days
        self.assertAlmostEqual(ephemeral_half_life, 6.9, places=0)


class TestDecayManager(unittest.TestCase):
    """Test decay manager."""

    def setUp(self):
        """Set up test database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test.db"
        Database.initialize(self.db_path)
        self.ops = GraphOperations()
        self.manager = DecayManager()

    def tearDown(self):
        """Clean up."""
        if self.db_path.exists():
            os.unlink(self.db_path)
        os.rmdir(self.temp_dir)

    def test_get_decay_stats(self):
        """Test getting decay statistics."""
        # Create some entities
        self.ops.record_technology("Python")
        self.ops.record_concept("RAG")

        stats = self.manager.get_decay_stats()

        self.assertIn("by_tier", stats)
        self.assertIn("total_entities", stats)
        self.assertGreater(stats["total_entities"], 0)

    def test_refresh_entity(self):
        """Test refreshing an entity."""
        tech = self.ops.record_technology("Python")
        original_confidence = tech.confidence

        refreshed = self.manager.refresh_entity(tech.id, boost=0.2)

        self.assertIsNotNone(refreshed)
        self.assertGreater(refreshed.confidence, original_confidence)


if __name__ == "__main__":
    unittest.main()
