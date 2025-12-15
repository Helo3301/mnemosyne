"""Tests for memory consolidation."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from mnemosyne.db.database import Database, get_db
from mnemosyne.graph.consolidation import ConsolidationManager
from mnemosyne.graph.operations import GraphOperations
from mnemosyne.models.entities import EntityType, Tier, ActivationType


class TestConsolidation(unittest.TestCase):
    """Test memory consolidation."""

    def setUp(self):
        """Set up test database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test.db"
        Database.initialize(self.db_path)
        self.ops = GraphOperations()
        self.manager = ConsolidationManager()
        self.db = get_db()

    def tearDown(self):
        """Clean up."""
        if self.db_path.exists():
            os.unlink(self.db_path)
        os.rmdir(self.temp_dir)

    def test_ephemeral_to_stable_promotion(self):
        """Test promoting ephemeral entity to stable."""
        # Create ephemeral entity
        concept = self.ops.record_concept("RAG")
        self.assertEqual(concept.tier, Tier.EPHEMERAL)

        # Simulate 5 activations (threshold for promotion)
        for _ in range(5):
            self.db.activate_entity(
                concept.id,
                activation_type=ActivationType.EXPLICIT,
            )

        # Check if qualifies for promotion
        new_tier = self.manager.check_entity_for_promotion(concept)
        self.assertEqual(new_tier, Tier.STABLE)

        # Actually promote
        promoted = self.manager.promote_entity(concept.id, Tier.STABLE)
        self.assertEqual(promoted.tier, Tier.STABLE)

    def test_no_promotion_without_activations(self):
        """Test that entities don't promote without sufficient activations."""
        concept = self.ops.record_concept("test concept")

        # Only activate once (not enough for promotion)
        self.db.activate_entity(concept.id)

        new_tier = self.manager.check_entity_for_promotion(concept)
        self.assertIsNone(new_tier)

    def test_run_consolidation(self):
        """Test running consolidation pass."""
        # Create entities with varying activation counts
        high_activity = self.ops.record_concept("frequently used")
        for _ in range(6):
            self.db.activate_entity(high_activity.id)

        low_activity = self.ops.record_concept("rarely used")

        # Run consolidation
        results = self.manager.run_consolidation(auto_promote=True)

        # high_activity should be promoted
        promoted_names = [p["entity"] for p in results["promoted"]]
        self.assertIn("frequently used", promoted_names)

    def test_demote_entity(self):
        """Test demoting an entity."""
        # Create stable entity
        tech = self.ops.record_technology("Python")  # Technologies start as STABLE

        # Demote to ephemeral
        demoted = self.manager.demote_entity(tech.id, Tier.EPHEMERAL)

        self.assertEqual(demoted.tier, Tier.EPHEMERAL)

    def test_consolidation_stats(self):
        """Test getting consolidation statistics."""
        self.ops.record_technology("Python")
        self.ops.record_concept("testing")

        stats = self.manager.get_consolidation_stats()

        self.assertIn("by_tier", stats)
        self.assertIn("promotion_candidates", stats)


if __name__ == "__main__":
    unittest.main()
