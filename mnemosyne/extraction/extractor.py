from __future__ import annotations

"""Entity extraction from conversation text."""
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from ..models.entities import EntityType, RelationshipType, Tier
from .patterns import (
    COMPILED_PATTERNS,
    PREFERENCE_INDICATORS,
    PROFICIENCY_INDICATORS,
    normalize_concept,
    normalize_technology,
)

logger = logging.getLogger(__name__)


@dataclass
class ExtractedEntity:
    """An entity extracted from text."""
    entity_type: EntityType
    name: str
    normalized_name: str
    confidence: float
    source_text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedRelationship:
    """A relationship extracted from text."""
    source_type: EntityType
    source_name: str
    target_type: EntityType
    target_name: str
    relationship_type: RelationshipType
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractionResult:
    """Result of extraction from a piece of text."""
    entities: list[ExtractedEntity] = field(default_factory=list)
    relationships: list[ExtractedRelationship] = field(default_factory=list)
    proficiency_signals: dict[str, float] = field(default_factory=dict)  # tech -> proficiency
    preference_signals: dict[str, float] = field(default_factory=dict)  # item -> weight (-1 to 1)


class EntityExtractor:
    """
    Extracts entities and relationships from conversation text.

    Uses pattern matching to identify:
    - Technologies mentioned
    - Projects being worked on
    - Concepts discussed
    - Goals stated
    - Frustrations expressed
    - Events mentioned
    - Preferences indicated
    - Proficiency signals
    """

    def __init__(self):
        self.patterns = COMPILED_PATTERNS

    def extract(self, text: str) -> ExtractionResult:
        """
        Extract all entities and relationships from text.

        Args:
            text: The text to extract from

        Returns:
            ExtractionResult with entities, relationships, and signals
        """
        result = ExtractionResult()

        # Extract entities by type
        for entity_type, patterns in self.patterns.items():
            for pattern in patterns:
                for match in pattern.pattern.finditer(text):
                    name = match.group(1) if match.groups() else match.group(0)
                    normalized = pattern.normalizer(name) if pattern.normalizer else name.lower().strip()

                    # Skip very short or common words
                    if len(normalized) < 2:
                        continue

                    entity = ExtractedEntity(
                        entity_type=entity_type,
                        name=name,
                        normalized_name=normalized,
                        confidence=pattern.confidence,
                        source_text=match.group(0),
                    )

                    # Avoid duplicates
                    if not any(e.normalized_name == entity.normalized_name and e.entity_type == entity.entity_type
                               for e in result.entities):
                        result.entities.append(entity)

        # Extract proficiency signals
        result.proficiency_signals = self._extract_proficiency_signals(text)

        # Extract preference signals
        result.preference_signals = self._extract_preference_signals(text)

        # Infer relationships between entities
        result.relationships = self._infer_relationships(text, result.entities)

        logger.debug(f"Extracted {len(result.entities)} entities, {len(result.relationships)} relationships")
        return result

    def _extract_proficiency_signals(self, text: str) -> dict[str, float]:
        """Extract proficiency signals from text."""
        signals = {}

        # Check for high proficiency indicators
        for pattern in PROFICIENCY_INDICATORS["high"]:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                tech = normalize_technology(match.group(1))
                signals[tech] = max(signals.get(tech, 0), 0.8)

        # Check for low proficiency indicators
        for pattern in PROFICIENCY_INDICATORS["low"]:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                tech = normalize_technology(match.group(1))
                signals[tech] = min(signals.get(tech, 1.0), 0.2)

        return signals

    def _extract_preference_signals(self, text: str) -> dict[str, float]:
        """Extract preference signals from text."""
        signals = {}

        # Check for positive preferences
        for pattern in PREFERENCE_INDICATORS["positive"]:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                item = match.group(1).strip().lower()
                signals[item] = max(signals.get(item, 0), 0.8)

        # Check for negative preferences
        for pattern in PREFERENCE_INDICATORS["negative"]:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                item = match.group(1).strip().lower()
                signals[item] = min(signals.get(item, 0), -0.8)

        return signals

    def _infer_relationships(
        self,
        text: str,
        entities: list[ExtractedEntity],
    ) -> list[ExtractedRelationship]:
        """Infer relationships between extracted entities."""
        relationships = []

        # Group entities by type for easier lookup
        by_type = {}
        for entity in entities:
            if entity.entity_type not in by_type:
                by_type[entity.entity_type] = []
            by_type[entity.entity_type].append(entity)

        # Project USES Technology
        projects = by_type.get(EntityType.PROJECT, [])
        technologies = by_type.get(EntityType.TECHNOLOGY, [])
        for project in projects:
            for tech in technologies:
                # Check if they appear near each other in text
                if self._entities_near_each_other(text, project.name, tech.name, window=100):
                    relationships.append(
                        ExtractedRelationship(
                            source_type=EntityType.PROJECT,
                            source_name=project.normalized_name,
                            target_type=EntityType.TECHNOLOGY,
                            target_name=tech.normalized_name,
                            relationship_type=RelationshipType.USES,
                            confidence=0.6,
                        )
                    )

        # Concept RELATED_TO Concept
        concepts = by_type.get(EntityType.CONCEPT, [])
        for i, concept1 in enumerate(concepts):
            for concept2 in concepts[i + 1:]:
                if self._entities_near_each_other(text, concept1.name, concept2.name, window=50):
                    relationships.append(
                        ExtractedRelationship(
                            source_type=EntityType.CONCEPT,
                            source_name=concept1.normalized_name,
                            target_type=EntityType.CONCEPT,
                            target_name=concept2.normalized_name,
                            relationship_type=RelationshipType.RELATED_TO,
                            confidence=0.5,
                        )
                    )

        return relationships

    def _entities_near_each_other(
        self,
        text: str,
        name1: str,
        name2: str,
        window: int = 100,
    ) -> bool:
        """Check if two entity names appear within a character window of each other."""
        text_lower = text.lower()
        name1_lower = name1.lower()
        name2_lower = name2.lower()

        # Find all positions of each name
        pos1 = [m.start() for m in re.finditer(re.escape(name1_lower), text_lower)]
        pos2 = [m.start() for m in re.finditer(re.escape(name2_lower), text_lower)]

        # Check if any pair is within window
        for p1 in pos1:
            for p2 in pos2:
                if abs(p1 - p2) <= window:
                    return True

        return False


class ConversationExtractor:
    """
    Extracts entities from a full conversation, handling multiple turns.

    Tracks context across turns and deduplicates entities.
    """

    def __init__(self):
        self.extractor = EntityExtractor()
        self.session_entities: dict[str, ExtractedEntity] = {}  # normalized_name -> entity
        self.session_relationships: list[ExtractedRelationship] = []

    def process_turn(self, text: str, role: str = "user") -> ExtractionResult:
        """
        Process a single conversation turn.

        Args:
            text: The text of the turn
            role: "user" or "assistant"

        Returns:
            ExtractionResult for this turn
        """
        result = self.extractor.extract(text)

        # Update session state
        for entity in result.entities:
            key = f"{entity.entity_type.value}:{entity.normalized_name}"
            if key in self.session_entities:
                # Increase confidence for repeated mentions
                existing = self.session_entities[key]
                existing.confidence = min(1.0, existing.confidence + 0.1)
            else:
                self.session_entities[key] = entity

        self.session_relationships.extend(result.relationships)

        return result

    def get_session_summary(self) -> ExtractionResult:
        """
        Get a summary of all extractions in this session.

        Returns:
            ExtractionResult with all session entities and relationships
        """
        return ExtractionResult(
            entities=list(self.session_entities.values()),
            relationships=self.session_relationships,
        )

    def reset(self):
        """Reset session state."""
        self.session_entities.clear()
        self.session_relationships.clear()


def extract_from_conversation(messages: list[dict[str, str]]) -> ExtractionResult:
    """
    Extract entities from a list of conversation messages.

    Args:
        messages: List of {"role": "user"|"assistant", "content": "..."}

    Returns:
        ExtractionResult with all extracted entities
    """
    extractor = ConversationExtractor()

    for message in messages:
        extractor.process_turn(message["content"], message.get("role", "user"))

    return extractor.get_session_summary()
