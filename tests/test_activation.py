"""Tests for spreading activation."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from mnemosyne.db.database import Database
from mnemosyne.graph.activation import SpreadingActivation
from mnemosyne.graph.operations import GraphOperations
from mnemosyne.models.entities import EntityType, RelationshipType


class TestSpreadingActivation(unittest.TestCase):
    """Test spreading activation."""

    def setUp(self):
        """Set up test database with sample data."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test.db"
        Database.initialize(self.db_path)

        # Create sample graph
        self.ops = GraphOperations()
        self.user = self.ops.get_user_entity()

        # Create technologies
        self.python = self.ops.record_technology("Python", proficiency=0.8)
        self.fastapi = self.ops.record_technology("FastAPI", proficiency=0.7)
        self.react = self.ops.record_technology("React", proficiency=0.5)

        # Create relationships between technologies
        self.ops.get_or_create_relationship(
            self.fastapi.id,
            self.python.id,
            RelationshipType.RELATED_TO,
            weight=0.9,  # FastAPI is Python-based
        )

        # Create project
        self.project = self.ops.record_project("MyApp")
        self.ops.get_or_create_relationship(
            self.project.id,
            self.fastapi.id,
            RelationshipType.USES,
            weight=0.8,
        )
        self.ops.get_or_create_relationship(
            self.project.id,
            self.react.id,
            RelationshipType.USES,
            weight=0.7,
        )

    def tearDown(self):
        """Clean up."""
        if self.db_path.exists():
            os.unlink(self.db_path)
        os.rmdir(self.temp_dir)

    def test_spread_from_single_seed(self):
        """Test spreading from a single entity."""
        activator = SpreadingActivation()
        activated = activator.spread([self.python.id], depth=2)

        # Should activate Python with strength 1.0
        self.assertIn(self.python.id, activated)
        self.assertEqual(activated[self.python.id], 1.0)

        # Should activate related entities with decayed strength
        self.assertTrue(len(activated) > 1)

    def test_spread_respects_budget(self):
        """Test that spreading respects budget."""
        activator = SpreadingActivation(budget=3)
        activated = activator.spread([self.user.id], depth=3)

        self.assertLessEqual(len(activated), 3)

    def test_spread_respects_depth(self):
        """Test that spreading respects depth limit."""
        activator = SpreadingActivation()
        activated_d1 = activator.spread([self.python.id], depth=1)
        activated_d2 = activator.spread([self.python.id], depth=2)

        # Depth 2 should activate more (or equal) entities
        self.assertGreaterEqual(len(activated_d2), len(activated_d1))

    def test_spread_decay(self):
        """Test that activation decays with distance."""
        activator = SpreadingActivation(decay_factor=0.5)
        activated = activator.spread([self.project.id], depth=2)

        # Project should have highest activation (1.0)
        self.assertEqual(activated[self.project.id], 1.0)

        # Direct neighbors should have decayed activation
        for entity_id, strength in activated.items():
            if entity_id != self.project.id:
                self.assertLess(strength, 1.0)

    def test_spread_from_query(self):
        """Test spreading from entity names."""
        activator = SpreadingActivation()
        activated = activator.spread_from_query(["Python"], depth=2)

        self.assertGreater(len(activated), 0)

    def test_get_activated_entities(self):
        """Test getting entity objects from activation."""
        activator = SpreadingActivation()
        activated = activator.spread([self.python.id], depth=2)

        entities = activator.get_activated_entities(activated)

        self.assertGreater(len(entities), 0)
        # Should be sorted by strength
        strengths = [s for _, s in entities]
        self.assertEqual(strengths, sorted(strengths, reverse=True))


if __name__ == "__main__":
    unittest.main()
