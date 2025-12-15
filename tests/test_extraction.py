"""Tests for entity extraction."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from mnemosyne.extraction.extractor import EntityExtractor, ConversationExtractor
from mnemosyne.models.entities import EntityType


class TestEntityExtractor(unittest.TestCase):
    """Test entity extraction."""

    def setUp(self):
        """Set up extractor."""
        self.extractor = EntityExtractor()

    def test_extract_technologies(self):
        """Test extracting technologies from text."""
        text = "I'm working with Python and React for this project."
        result = self.extractor.extract(text)

        tech_names = [e.normalized_name for e in result.entities
                      if e.entity_type == EntityType.TECHNOLOGY]

        self.assertIn("python", tech_names)
        self.assertIn("react", tech_names)

    def test_extract_concepts(self):
        """Test extracting concepts from text."""
        text = "We're implementing microservices with REST APIs."
        result = self.extractor.extract(text)

        concept_names = [e.normalized_name for e in result.entities
                         if e.entity_type == EntityType.CONCEPT]

        self.assertTrue(any("microservice" in c for c in concept_names))
        self.assertIn("rest", concept_names)

    def test_extract_goals(self):
        """Test extracting goals from text."""
        text = "I want to learn Rust this year. My goal is to build a CLI tool."
        result = self.extractor.extract(text)

        goal_entities = [e for e in result.entities
                         if e.entity_type == EntityType.GOAL]

        self.assertGreater(len(goal_entities), 0)

    def test_extract_frustrations(self):
        """Test extracting frustrations from text."""
        text = "I'm frustrated with Docker networking. Can't figure out the ports."
        result = self.extractor.extract(text)

        frustration_entities = [e for e in result.entities
                                 if e.entity_type == EntityType.FRUSTRATION]

        self.assertGreater(len(frustration_entities), 0)

    def test_extract_proficiency_signals(self):
        """Test extracting proficiency signals."""
        # High proficiency
        text1 = "Let me explain how Python decorators work in detail."
        result1 = self.extractor.extract(text1)
        # Should indicate high proficiency in Python

        # Low proficiency
        text2 = "I'm new to Rust, what is a borrow checker?"
        result2 = self.extractor.extract(text2)

        self.assertIn("rust", result2.proficiency_signals)
        self.assertLess(result2.proficiency_signals["rust"], 0.5)

    def test_extract_preference_signals(self):
        """Test extracting preference signals."""
        text = "I prefer TypeScript over JavaScript. I love using VS Code."
        result = self.extractor.extract(text)

        self.assertGreater(len(result.preference_signals), 0)


class TestConversationExtractor(unittest.TestCase):
    """Test conversation-level extraction."""

    def test_process_multiple_turns(self):
        """Test processing multiple conversation turns."""
        extractor = ConversationExtractor()

        extractor.process_turn("I'm building an app with React and FastAPI.", "user")
        extractor.process_turn("Let me help you with that.", "assistant")
        extractor.process_turn("I prefer using TypeScript for the frontend.", "user")

        summary = extractor.get_session_summary()

        # Should have accumulated entities
        self.assertGreater(len(summary.entities), 0)

        # Check for expected technologies
        tech_names = [e.normalized_name for e in summary.entities
                      if e.entity_type == EntityType.TECHNOLOGY]

        self.assertIn("react", tech_names)
        self.assertIn("fastapi", tech_names)
        self.assertIn("typescript", tech_names)

    def test_repeated_mentions_increase_confidence(self):
        """Test that repeated mentions increase confidence."""
        extractor = ConversationExtractor()

        extractor.process_turn("I'm using Python for this.", "user")
        extractor.process_turn("Python is great for scripting.", "user")
        extractor.process_turn("Let me write some more Python code.", "user")

        summary = extractor.get_session_summary()

        python_entities = [e for e in summary.entities
                          if e.normalized_name == "python"]

        # Should have only one Python entity with boosted confidence
        self.assertEqual(len(python_entities), 1)
        self.assertGreater(python_entities[0].confidence, 0.7)


if __name__ == "__main__":
    unittest.main()
