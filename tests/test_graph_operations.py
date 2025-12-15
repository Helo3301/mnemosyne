"""Tests for graph operations."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from mnemosyne.db.database import Database
from mnemosyne.graph.operations import GraphOperations
from mnemosyne.models.entities import EntityType, RelationshipType, Tier


class TestGraphOperations(unittest.TestCase):
    """Test graph operations."""

    def setUp(self):
        """Set up test database."""
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = Path(self.temp_dir) / "test.db"
        Database.initialize(self.db_path)
        self.ops = GraphOperations()

    def tearDown(self):
        """Clean up test database."""
        if self.db_path.exists():
            os.unlink(self.db_path)
        os.rmdir(self.temp_dir)

    def test_get_user_entity(self):
        """Test getting/creating user entity."""
        user = self.ops.get_user_entity()
        self.assertIsNotNone(user)
        self.assertEqual(user.entity_type, EntityType.USER)
        self.assertEqual(user.tier, Tier.CORE)

        # Should return same entity on second call
        user2 = self.ops.get_user_entity()
        self.assertEqual(user.id, user2.id)

    def test_record_project(self):
        """Test recording a project."""
        project = self.ops.record_project("TestProject")
        self.assertIsNotNone(project)
        self.assertEqual(project.entity_type, EntityType.PROJECT)
        self.assertEqual(project.name, "TestProject")

        # Check WORKS_ON relationship exists
        projects = self.ops.get_user_projects()
        self.assertEqual(len(projects), 1)
        self.assertEqual(projects[0][0].name, "TestProject")

    def test_record_technology(self):
        """Test recording a technology."""
        tech = self.ops.record_technology("Python", proficiency=0.8)
        self.assertIsNotNone(tech)
        self.assertEqual(tech.entity_type, EntityType.TECHNOLOGY)

        # Check KNOWS relationship
        techs = self.ops.get_user_technologies()
        self.assertEqual(len(techs), 1)
        self.assertEqual(techs[0][0].name, "Python")
        self.assertGreaterEqual(techs[0][1], 0.8)

    def test_record_technology_for_project(self):
        """Test recording a technology for a project."""
        project = self.ops.record_project("MyApp")
        tech = self.ops.record_technology("React", project_id=project.id)

        # Check project uses technology
        project_techs = self.ops.get_project_technologies(project.id)
        self.assertEqual(len(project_techs), 1)
        self.assertEqual(project_techs[0].name, "React")

    def test_record_preference(self):
        """Test recording a preference."""
        pref = self.ops.record_preference("dark mode", weight=0.9)
        self.assertIsNotNone(pref)
        self.assertEqual(pref.entity_type, EntityType.PREFERENCE)

        prefs = self.ops.get_user_preferences()
        self.assertEqual(len(prefs), 1)

    def test_record_goal(self):
        """Test recording a goal."""
        goal = self.ops.record_goal("Learn Rust", active=True)
        self.assertIsNotNone(goal)
        self.assertEqual(goal.entity_type, EntityType.GOAL)

        goals = self.ops.get_active_goals()
        self.assertEqual(len(goals), 1)

    def test_record_frustration(self):
        """Test recording a frustration."""
        frustration = self.ops.record_frustration("Docker networking")
        self.assertIsNotNone(frustration)
        self.assertEqual(frustration.entity_type, EntityType.FRUSTRATION)

        frustrations = self.ops.get_recent_frustrations()
        self.assertEqual(len(frustrations), 1)

    def test_get_or_create_relationship(self):
        """Test getting or creating relationships."""
        project = self.ops.record_project("App")
        tech = self.ops.record_technology("Python")

        rel1 = self.ops.get_or_create_relationship(
            project.id,
            tech.id,
            RelationshipType.USES,
            weight=0.5,
        )
        self.assertIsNotNone(rel1)

        # Getting again should return same relationship
        rel2 = self.ops.get_or_create_relationship(
            project.id,
            tech.id,
            RelationshipType.USES,
        )
        self.assertEqual(rel1.id, rel2.id)


if __name__ == "__main__":
    unittest.main()
